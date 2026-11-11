import re
from datetime import date
from decimal import Decimal

from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import (DateField, DecimalField, IntegerField, PasswordField,
                     SelectField, StringField, TextAreaField)
from wtforms.validators import (DataRequired, EqualTo, Length, NumberRange,
                                Optional, Regexp, ValidationError)

from .models import Lote, Producto, Proveedor, Usuario

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _strip(v):
    return v.strip() if isinstance(v, str) else v


def _lower(v):
    return v.strip().lower() if isinstance(v, str) else v


def _upper(v):
    return v.strip().upper() if isinstance(v, str) else v


def clave_valida(form, field):
    p = field.data or ""
    if not (re.search(r"[A-Za-z]", p) and re.search(r"\d", p)):
        raise ValidationError("La contraseña debe incluir letras y números.")
    if len(p.encode("utf-8")) > 72:
        raise ValidationError("La contraseña es demasiado larga.")


class RegistroForm(FlaskForm):
    nombre = StringField("Nombre completo", filters=[_strip], validators=[
        DataRequired("Ingresa tu nombre."), Length(3, 80, "Entre 3 y 80 caracteres."),
        Regexp(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]+$", message="Solo letras y espacios.")],
        render_kw={"autocomplete": "name"})
    email = StringField("Correo electrónico", filters=[_lower], validators=[
        DataRequired("Ingresa tu correo."), Length(max=120), Regexp(EMAIL_RE, message="Correo inválido.")],
        render_kw={"type": "email", "autocomplete": "email"})
    area = SelectField("Área", choices=[("bodega", "Bodega"), ("ventas", "Ventas")])
    password = PasswordField("Contraseña", validators=[
        DataRequired("Ingresa una contraseña."), Length(8, 64, "Entre 8 y 64 caracteres."), clave_valida],
        render_kw={"autocomplete": "new-password"})
    confirmar = PasswordField("Confirmar contraseña", validators=[
        DataRequired("Confirma la contraseña."), EqualTo("password", "Las contraseñas no coinciden.")],
        render_kw={"autocomplete": "new-password"})

    def validate_email(self, field):
        if Usuario.query.filter_by(email=field.data).first():
            raise ValidationError("Ese correo ya está registrado.")


class LoginForm(FlaskForm):
    email = StringField("Correo electrónico", filters=[_lower], validators=[
        DataRequired("Ingresa tu correo."), Length(max=120)], render_kw={"type": "email", "autocomplete": "email"})
    password = PasswordField("Contraseña", validators=[DataRequired("Ingresa tu contraseña."), Length(max=128)],
                             render_kw={"autocomplete": "current-password"})


class OlvideForm(FlaskForm):
    email = StringField("Correo electrónico", filters=[_lower], validators=[
        DataRequired("Ingresa tu correo."), Regexp(EMAIL_RE, message="Correo inválido.")],
        render_kw={"type": "email"})


class ResetForm(FlaskForm):
    password = PasswordField("Nueva contraseña", validators=[
        DataRequired("Ingresa una contraseña."), Length(8, 64, "Entre 8 y 64 caracteres."), clave_valida],
        render_kw={"autocomplete": "new-password"})
    confirmar = PasswordField("Confirmar contraseña", validators=[
        DataRequired("Confirma la contraseña."), EqualTo("password", "Las contraseñas no coinciden.")],
        render_kw={"autocomplete": "new-password"})


class ProductoForm(FlaskForm):
    sku = StringField("SKU", filters=[_upper], validators=[
        DataRequired("El SKU es obligatorio."), Length(3, 30, "Entre 3 y 30 caracteres."),
        Regexp(r"^[A-Z0-9-]+$", message="Solo letras, números y guiones.")],
        render_kw={"pattern": "[A-Za-z0-9\\-]+", "title": "Letras, números y guiones"})
    nombre = StringField("Nombre comercial", filters=[_strip], validators=[
        DataRequired("El nombre es obligatorio."), Length(3, 120, "Entre 3 y 120 caracteres.")])
    descripcion = TextAreaField("Descripción", filters=[_strip], validators=[Optional(), Length(max=500)])
    stock_minimo = IntegerField("Stock mínimo", validators=[
        NumberRange(0, 1_000_000, "Debe ser un número entre 0 y 1 000 000.")], default=0)
    unidad = SelectField("Unidad de medida", choices=[("unidad", "Unidad"), ("caja", "Caja"), ("kg", "Kilogramo"),
                                                      ("litro", "Litro"), ("paquete", "Paquete")])
    estado = SelectField("Estado", choices=[("activo", "Activo"), ("inactivo", "Inactivo")])

    def __init__(self, *args, producto_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.producto_id = producto_id

    def validate_sku(self, field):
        q = Producto.query.filter(func.upper(Producto.sku) == field.data)
        if self.producto_id:
            q = q.filter(Producto.id != self.producto_id)
        if q.first():
            raise ValidationError("Ya existe un producto con ese SKU.")


class LoteForm(FlaskForm):
    codigo = StringField("Código de lote", filters=[_upper], validators=[
        DataRequired("El código es obligatorio."), Length(2, 40),
        Regexp(r"^[A-Z0-9._-]+$", message="Solo letras, números, punto, guion y guion bajo.")])
    proveedor_id = SelectField("Proveedor", coerce=int, validators=[DataRequired("Selecciona un proveedor.")])
    cantidad = IntegerField("Cantidad recibida", validators=[
        DataRequired("Ingresa la cantidad."), NumberRange(1, 1_000_000, "Debe ser entre 1 y 1 000 000.")])
    costo = DecimalField("Costo unitario (USD)", places=2, validators=[
        DataRequired("Ingresa el costo."), NumberRange(Decimal("0.01"), Decimal("1000000"), "Costo inválido.")])
    fecha_ingreso = DateField("Fecha de ingreso", default=date.today, validators=[DataRequired("Fecha inválida.")])
    fecha_caducidad = DateField("Fecha de caducidad (si aplica)", validators=[Optional()])
    ubicacion = StringField("Ubicación en bodega", filters=[_strip], validators=[Optional(), Length(max=60)])

    def __init__(self, *args, producto_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.producto_id = producto_id
        self.proveedor_id.choices = [(p.id, p.nombre) for p in Proveedor.query.order_by(Proveedor.nombre)]

    def validate_codigo(self, field):
        if Lote.query.filter_by(producto_id=self.producto_id, codigo=field.data).first():
            raise ValidationError("Ese código de lote ya existe para este producto.")

    def validate_fecha_caducidad(self, field):
        if field.data:
            if field.data < date.today():
                raise ValidationError("El lote ya está caducado.")
            if self.fecha_ingreso.data and field.data < self.fecha_ingreso.data:
                raise ValidationError("No puede ser anterior a la fecha de ingreso.")


class SalidaForm(FlaskForm):
    cantidad = IntegerField("Cantidad a despachar", validators=[
        DataRequired("Ingresa la cantidad."), NumberRange(1, 1_000_000, "Debe ser entre 1 y 1 000 000.")])
    motivo = StringField("Motivo / referencia (opcional)", filters=[_strip], validators=[Optional(), Length(max=120)])


class ProveedorForm(FlaskForm):
    nombre = StringField("Nombre", filters=[_strip], validators=[
        DataRequired("El nombre es obligatorio."), Length(2, 120)])
    ruc = StringField("RUC (13 dígitos)", filters=[_strip], validators=[
        DataRequired("El RUC es obligatorio."), Regexp(r"^\d{13}$", message="Debe tener exactamente 13 dígitos.")],
        render_kw={"pattern": "\\d{13}", "inputmode": "numeric", "maxlength": 13})
    telefono = StringField("Teléfono", filters=[_strip], validators=[
        Optional(), Regexp(r"^\+?\d{7,15}$", message="Solo dígitos (7 a 15), puede iniciar con +.")])

    def validate_ruc(self, field):
        if Proveedor.query.filter_by(ruc=field.data).first():
            raise ValidationError("Ya existe un proveedor con ese RUC.")
