from datetime import date, datetime, timezone

import bcrypt
from flask_login import UserMixin

from .extensions import db, login_manager


def ahora():
    """Fecha/hora UTC sin zona (se convierte a hora local solo al mostrar)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Rol(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(20), unique=True, nullable=False)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    rol_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, default=ahora, nullable=False)
    rol = db.relationship("Rol")

    def set_password(self, plano):
        # bcrypt genera una sal aleatoria por contraseña y la incluye en el hash.
        self.password_hash = bcrypt.hashpw(plano.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    def check_password(self, plano):
        try:
            return bcrypt.checkpw(plano.encode("utf-8"), self.password_hash.encode("ascii"))
        except ValueError:
            return False


@login_manager.user_loader
def cargar_usuario(user_id):
    u = db.session.get(Usuario, int(user_id))
    return u if u and u.activo else None


class TokenReset(db.Model):
    """Token de recuperación: solo se guarda su hash, caduca y es de un solo uso."""
    __tablename__ = "tokens_reset"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True, nullable=False)
    token_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)
    expira_en = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(db.DateTime, default=ahora, nullable=False)
    usuario = db.relationship("Usuario")


class Proveedor(db.Model):
    __tablename__ = "proveedores"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    ruc = db.Column(db.String(13), unique=True, nullable=False)
    telefono = db.Column(db.String(16))


class Producto(db.Model):
    __tablename__ = "productos"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(30), unique=True, index=True, nullable=False)
    nombre = db.Column(db.String(120), index=True, nullable=False)
    descripcion = db.Column(db.String(500))
    stock_minimo = db.Column(db.Integer, nullable=False, default=0)
    unidad = db.Column(db.String(10), nullable=False, default="unidad")
    estado = db.Column(db.String(10), index=True, nullable=False, default="activo")
    creado_en = db.Column(db.DateTime, default=ahora, nullable=False)
    lotes = db.relationship("Lote", back_populates="producto")

    @property
    def stock_disponible(self):
        return sum(l.cantidad_disponible for l in self.lotes if l.es_apto)


class Lote(db.Model):
    __tablename__ = "lotes"
    __table_args__ = (db.UniqueConstraint("producto_id", "codigo", name="uq_lote_producto_codigo"),)
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), index=True, nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), index=True, nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=False)
    cantidad_inicial = db.Column(db.Integer, nullable=False)
    cantidad_disponible = db.Column(db.Integer, nullable=False)
    costo_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_ingreso = db.Column(db.Date, nullable=False)
    fecha_caducidad = db.Column(db.Date, index=True)
    ubicacion = db.Column(db.String(60))
    estado = db.Column(db.String(12), nullable=False, default="disponible")  # disponible | agotado | bloqueado
    producto = db.relationship("Producto", back_populates="lotes")
    proveedor = db.relationship("Proveedor")

    @property
    def vencido(self):
        return self.fecha_caducidad is not None and self.fecha_caducidad < date.today()

    @property
    def es_apto(self):
        return self.estado == "disponible" and self.cantidad_disponible > 0 and not self.vencido


class Movimiento(db.Model):
    __tablename__ = "movimientos"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), index=True, nullable=False)  # ENTRADA | SALIDA
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), index=True, nullable=False)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    motivo = db.Column(db.String(120))
    fecha = db.Column(db.DateTime, default=ahora, index=True, nullable=False)
    producto = db.relationship("Producto")
    lote = db.relationship("Lote")
    usuario = db.relationship("Usuario")


class SolicitudReposicion(db.Model):
    __tablename__ = "solicitudes_reposicion"
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), index=True, nullable=False)
    cantidad_sugerida = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(10), index=True, nullable=False, default="pendiente")  # pendiente | atendida
    creada_en = db.Column(db.DateTime, default=ahora, nullable=False)
    atendida_en = db.Column(db.DateTime)
    producto = db.relationship("Producto")


class SalaChat(db.Model):
    __tablename__ = "salas_chat"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(40), unique=True, nullable=False)


class Mensaje(db.Model):
    __tablename__ = "mensajes"
    __table_args__ = (db.Index("ix_mensajes_sala_fecha", "sala_id", "creado_en"),)
    id = db.Column(db.Integer, primary_key=True)
    sala_id = db.Column(db.Integer, db.ForeignKey("salas_chat.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    contenido = db.Column(db.String(500), nullable=False)
    creado_en = db.Column(db.DateTime, default=ahora, nullable=False)
    usuario = db.relationship("Usuario")
