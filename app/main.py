from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from . import services
from .extensions import db
from .forms import LoteForm, ProductoForm, ProveedorForm, SalidaForm
from .models import (Lote, Movimiento, Producto, Proveedor, SalaChat,
                     SolicitudReposicion, ahora)

bp = Blueprint("main", __name__)


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if current_user.rol.nombre not in roles:
                abort(403)
            return f(*args, **kwargs)
        return login_required(wrapper)
    return deco


def _pagina():
    return max(request.args.get("page", 1, type=int), 1)


def _like(texto):
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@bp.route("/")
def index():
    return redirect(url_for("main.dashboard" if current_user.is_authenticated else "auth.signin"))


@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        total_productos=Producto.query.filter_by(estado="activo").count(),
        stock_bajo=services.productos_stock_bajo(),
        por_caducar=services.lotes_por_caducar(),
        vencidos=services.lotes_vencidos_con_stock(),
        pendientes=SolicitudReposicion.query.filter_by(estado="pendiente").count())


# ---------- Productos ----------
@bp.route("/productos")
@login_required
def productos():
    q = request.args.get("q", "").strip()[:100]
    estado = request.args.get("estado", "")
    query = Producto.query
    if q:
        query = query.filter(or_(Producto.sku.ilike(f"{_like(q)}%", escape="\\"),
                                 Producto.nombre.ilike(f"%{_like(q)}%", escape="\\")))
    if estado in ("activo", "inactivo"):
        query = query.filter(Producto.estado == estado)
    pag = query.order_by(Producto.nombre).paginate(page=_pagina(), per_page=current_app.config["POR_PAGINA"],
                                                   error_out=False)
    return render_template("productos/lista.html", pag=pag, q=q, estado=estado,
                           filtros={k: v for k, v in (("q", q), ("estado", estado)) if v})


@bp.route("/productos/<int:id>")
@login_required
def producto_detalle(id):
    p = db.get_or_404(Producto, id)
    lotes = Lote.query.filter_by(producto_id=id).order_by(*services.orden_fefo()).all()
    movs = (Movimiento.query.filter_by(producto_id=id).options(joinedload(Movimiento.lote), joinedload(Movimiento.usuario))
            .order_by(Movimiento.id.desc()).limit(10).all())
    return render_template("productos/detalle.html", p=p, lotes=lotes, movs=movs)


@bp.route("/productos/nuevo", methods=["GET", "POST"])
@roles_required("admin", "bodega")
def producto_nuevo():
    form = ProductoForm()
    if form.validate_on_submit():
        p = Producto(sku=form.sku.data, nombre=form.nombre.data, descripcion=form.descripcion.data or None,
                     stock_minimo=form.stock_minimo.data, unidad=form.unidad.data, estado=form.estado.data)
        db.session.add(p)
        db.session.commit()
        flash("Producto creado.", "success")
        return redirect(url_for("main.producto_detalle", id=p.id))
    return render_template("productos/form.html", form=form, titulo="Nuevo producto")


@bp.route("/productos/<int:id>/editar", methods=["GET", "POST"])
@roles_required("admin", "bodega")
def producto_editar(id):
    p = db.get_or_404(Producto, id)
    form = ProductoForm(obj=p, producto_id=p.id)
    if form.validate_on_submit():
        p.sku, p.nombre, p.descripcion = form.sku.data, form.nombre.data, form.descripcion.data or None
        p.stock_minimo, p.unidad, p.estado = form.stock_minimo.data, form.unidad.data, form.estado.data
        db.session.commit()
        flash("Producto actualizado.", "success")
        return redirect(url_for("main.producto_detalle", id=p.id))
    return render_template("productos/form.html", form=form, titulo=f"Editar {p.nombre}")


@bp.route("/productos/<int:id>/eliminar", methods=["POST"])
@roles_required("admin", "bodega")
def producto_eliminar(id):
    p = db.get_or_404(Producto, id)
    if Lote.query.filter_by(producto_id=id).first():
        flash("No se puede eliminar: tiene lotes y movimientos registrados. Márcalo como inactivo.", "danger")
        return redirect(url_for("main.producto_detalle", id=id))
    SolicitudReposicion.query.filter_by(producto_id=id).delete()
    db.session.delete(p)
    db.session.commit()
    flash("Producto eliminado.", "success")
    return redirect(url_for("main.productos"))


# ---------- Lotes y movimientos ----------
@bp.route("/productos/<int:id>/entrada", methods=["GET", "POST"])
@roles_required("admin", "bodega")
def entrada(id):
    p = db.get_or_404(Producto, id)
    if not Proveedor.query.first():
        flash("Primero registra al menos un proveedor.", "warning")
        return redirect(url_for("main.proveedor_nuevo"))
    form = LoteForm(producto_id=id)
    if form.validate_on_submit():
        lote = services.registrar_entrada(p, {
            "codigo": form.codigo.data, "proveedor_id": form.proveedor_id.data, "cantidad": form.cantidad.data,
            "costo": form.costo.data, "fecha_ingreso": form.fecha_ingreso.data,
            "fecha_caducidad": form.fecha_caducidad.data, "ubicacion": form.ubicacion.data}, current_user)
        flash(f"Lote {lote.codigo} registrado (+{lote.cantidad_inicial}).", "success")
        return redirect(url_for("main.producto_detalle", id=id))
    return render_template("productos/lote_form.html", form=form, p=p)


@bp.route("/productos/<int:id>/salida", methods=["GET", "POST"])
@roles_required("admin", "ventas")
def salida(id):
    p = db.get_or_404(Producto, id)
    if p.estado != "activo":
        flash("El producto está inactivo y no admite salidas.", "danger")
        return redirect(url_for("main.producto_detalle", id=id))
    form = SalidaForm()
    if form.validate_on_submit():
        try:
            usados = services.registrar_salida(p, form.cantidad.data, current_user, form.motivo.data)
        except services.StockInsuficiente as e:
            form.cantidad.errors.append(str(e))
        else:
            detalle = ", ".join(f"{c}: {n}" for c, n in usados)
            flash(f"Salida registrada (FEFO). Lotes usados → {detalle}.", "success")
            return redirect(url_for("main.producto_detalle", id=id))
    lotes = (Lote.query.filter(Lote.producto_id == id, *services.conds_aptos()).order_by(*services.orden_fefo()).all())
    return render_template("productos/salida_form.html", form=form, p=p, lotes=lotes)


@bp.route("/movimientos")
@login_required
def movimientos():
    tipo = request.args.get("tipo", "")
    query = Movimiento.query.options(joinedload(Movimiento.producto), joinedload(Movimiento.lote),
                                     joinedload(Movimiento.usuario))
    if tipo in ("ENTRADA", "SALIDA"):
        query = query.filter(Movimiento.tipo == tipo)
    pag = query.order_by(Movimiento.id.desc()).paginate(page=_pagina(), per_page=current_app.config["POR_PAGINA"],
                                                        error_out=False)
    return render_template("movimientos.html", pag=pag, tipo=tipo, filtros={"tipo": tipo} if tipo else {})


# ---------- Proveedores ----------
@bp.route("/proveedores")
@login_required
def proveedores():
    pag = Proveedor.query.order_by(Proveedor.nombre).paginate(page=_pagina(), per_page=current_app.config["POR_PAGINA"],
                                                              error_out=False)
    return render_template("proveedores/lista.html", pag=pag, filtros={})


@bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@roles_required("admin", "bodega")
def proveedor_nuevo():
    form = ProveedorForm()
    if form.validate_on_submit():
        db.session.add(Proveedor(nombre=form.nombre.data, ruc=form.ruc.data, telefono=form.telefono.data or None))
        db.session.commit()
        flash("Proveedor registrado.", "success")
        return redirect(url_for("main.proveedores"))
    return render_template("proveedores/form.html", form=form)


# ---------- Reposiciones ----------
@bp.route("/reposiciones")
@login_required
def reposiciones():
    estado = request.args.get("estado", "pendiente")
    query = SolicitudReposicion.query.options(joinedload(SolicitudReposicion.producto))
    if estado in ("pendiente", "atendida"):
        query = query.filter_by(estado=estado)
    pag = query.order_by(SolicitudReposicion.id.desc()).paginate(page=_pagina(), per_page=current_app.config["POR_PAGINA"],
                                                                 error_out=False)
    return render_template("reposiciones.html", pag=pag, estado=estado, filtros={"estado": estado})


@bp.route("/reposiciones/<int:id>/atender", methods=["POST"])
@roles_required("admin", "bodega")
def reposicion_atender(id):
    s = db.get_or_404(SolicitudReposicion, id)
    s.estado, s.atendida_en = "atendida", ahora()
    db.session.commit()
    flash("Solicitud marcada como atendida.", "success")
    return redirect(url_for("main.reposiciones"))


# ---------- Chat ----------
@bp.route("/chat")
@login_required
def chat():
    return render_template("chat.html", salas=SalaChat.query.order_by(SalaChat.id).all())
