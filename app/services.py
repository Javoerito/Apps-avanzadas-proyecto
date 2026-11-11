"""Lógica de negocio: lotes (FEFO), movimientos, alertas y tokens de recuperación."""
import hashlib
import secrets
from datetime import date, timedelta

from flask import current_app
from sqlalchemy import case, func, or_

from .extensions import db, socketio
from .models import (Lote, Movimiento, Producto, Rol, SalaChat,
                     SolicitudReposicion, TokenReset, ahora)


class StockInsuficiente(ValueError):
    pass


def asegurar_datos_base():
    for nombre in ("admin", "bodega", "ventas"):
        if not Rol.query.filter_by(nombre=nombre).first():
            db.session.add(Rol(nombre=nombre))
    for nombre in ("General", "Bodega", "Ventas"):
        if not SalaChat.query.filter_by(nombre=nombre).first():
            db.session.add(SalaChat(nombre=nombre))
    db.session.commit()


# ---------- Consultas de existencias ----------
def conds_aptos():
    """Un lote es apto para la venta si está disponible, tiene stock y no ha caducado."""
    return [
        Lote.estado == "disponible",
        Lote.cantidad_disponible > 0,
        or_(Lote.fecha_caducidad.is_(None), Lote.fecha_caducidad >= date.today()),
    ]


def stock_disponible(producto_id):
    return (db.session.query(func.coalesce(func.sum(Lote.cantidad_disponible), 0))
            .filter(Lote.producto_id == producto_id, *conds_aptos()).scalar())


def orden_fefo():
    # Primero el que caduca antes; los que no caducan al final.
    return (case((Lote.fecha_caducidad.is_(None), 1), else_=0),
            Lote.fecha_caducidad, Lote.fecha_ingreso, Lote.id)


def productos_stock_bajo(limite=10):
    sub = (db.session.query(Lote.producto_id.label("pid"), func.sum(Lote.cantidad_disponible).label("stock"))
           .filter(*conds_aptos()).group_by(Lote.producto_id).subquery())
    stock = func.coalesce(sub.c.stock, 0)
    return (db.session.query(Producto, stock.label("stock"))
            .outerjoin(sub, sub.c.pid == Producto.id)
            .filter(Producto.estado == "activo", stock <= Producto.stock_minimo)
            .order_by(stock).limit(limite).all())


def lotes_por_caducar(limite=10):
    tope = date.today() + timedelta(days=current_app.config["DIAS_ALERTA_CADUCIDAD"])
    return (Lote.query.join(Producto).filter(Producto.estado == "activo", *conds_aptos(),
                                             Lote.fecha_caducidad.isnot(None), Lote.fecha_caducidad <= tope)
            .order_by(Lote.fecha_caducidad).limit(limite).all())


def lotes_vencidos_con_stock(limite=10):
    return (Lote.query.filter(Lote.cantidad_disponible > 0, Lote.estado == "disponible",
                              Lote.fecha_caducidad < date.today())
            .order_by(Lote.fecha_caducidad).limit(limite).all())


# ---------- Movimientos ----------
def registrar_entrada(producto, datos, usuario):
    lote = Lote(producto_id=producto.id, codigo=datos["codigo"], proveedor_id=datos["proveedor_id"],
                cantidad_inicial=datos["cantidad"], cantidad_disponible=datos["cantidad"],
                costo_unitario=datos["costo"], fecha_ingreso=datos["fecha_ingreso"],
                fecha_caducidad=datos.get("fecha_caducidad"), ubicacion=datos.get("ubicacion") or None)
    db.session.add(lote)
    db.session.flush()
    db.session.add(Movimiento(tipo="ENTRADA", producto_id=producto.id, lote_id=lote.id,
                              cantidad=datos["cantidad"], usuario_id=usuario.id, motivo="Recepción de mercadería"))
    db.session.commit()
    evaluar_alertas(producto)
    return lote


def registrar_salida(producto, cantidad, usuario, motivo=None):
    """Descuenta stock con FEFO: primero los lotes aptos que caducan antes."""
    lotes = (Lote.query.filter(Lote.producto_id == producto.id, *conds_aptos())
             .order_by(*orden_fefo()).with_for_update().all())
    disponible = sum(l.cantidad_disponible for l in lotes)
    if cantidad > disponible:
        raise StockInsuficiente(f"Stock insuficiente: solo hay {disponible} disponible(s) para la venta.")
    restante, usados = cantidad, []
    for lote in lotes:
        if restante == 0:
            break
        tomar = min(lote.cantidad_disponible, restante)
        lote.cantidad_disponible -= tomar
        if lote.cantidad_disponible == 0:
            lote.estado = "agotado"
        db.session.add(Movimiento(tipo="SALIDA", producto_id=producto.id, lote_id=lote.id, cantidad=tomar,
                                  usuario_id=usuario.id, motivo=motivo or "Despacho"))
        usados.append((lote.codigo, tomar))
        restante -= tomar
    db.session.commit()
    evaluar_alertas(producto)
    return usados


# ---------- Alertas en tiempo real ----------
def evaluar_alertas(producto):
    """Tras cada movimiento: revisa stock mínimo y caducidad, y notifica por WebSocket."""
    alertas = []
    stock = stock_disponible(producto.id)
    if stock <= producto.stock_minimo:
        alertas.append({"tipo": "stock_minimo", "severidad": "danger", "producto_id": producto.id,
                        "titulo": "Stock mínimo alcanzado",
                        "mensaje": f"{producto.nombre} ({producto.sku}): quedan {stock}, mínimo {producto.stock_minimo}."})
        if not SolicitudReposicion.query.filter_by(producto_id=producto.id, estado="pendiente").first():
            db.session.add(SolicitudReposicion(producto_id=producto.id,
                                               cantidad_sugerida=max(producto.stock_minimo * 2 - stock, 1)))
            db.session.commit()
    tope = date.today() + timedelta(days=current_app.config["DIAS_ALERTA_CADUCIDAD"])
    por_caducar = (Lote.query.filter(Lote.producto_id == producto.id, *conds_aptos(),
                                     Lote.fecha_caducidad.isnot(None), Lote.fecha_caducidad <= tope)
                   .order_by(Lote.fecha_caducidad).all())
    for l in por_caducar:
        alertas.append({"tipo": "proximo_caducar", "severidad": "warning", "producto_id": producto.id,
                        "titulo": "Lote próximo a caducar",
                        "mensaje": f"Lote {l.codigo} de {producto.nombre} caduca el {l.fecha_caducidad:%d/%m/%Y}."})
    for a in alertas:
        socketio.emit("alerta", a)
    return alertas


# ---------- Recuperación de contraseña ----------
def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def crear_token_reset(usuario):
    TokenReset.query.filter_by(usuario_id=usuario.id, usado=False).update({"usado": True})
    token = secrets.token_urlsafe(32)
    db.session.add(TokenReset(usuario_id=usuario.id, token_hash=_hash_token(token),
                              expira_en=ahora() + timedelta(minutes=current_app.config["RESET_TOKEN_MINUTOS"])))
    db.session.commit()
    return token


def validar_token(token):
    t = TokenReset.query.filter_by(token_hash=_hash_token(token)).first()
    return t if t and not t.usado and t.expira_en > ahora() else None


def consumir_token(registro, nueva_password):
    registro.usuario.set_password(nueva_password)
    registro.usado = True
    db.session.commit()
