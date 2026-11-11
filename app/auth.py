from urllib.parse import urlparse

import bcrypt
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from . import services
from .extensions import db
from .forms import LoginForm, OlvideForm, RegistroForm, ResetForm
from .models import Rol, Usuario

bp = Blueprint("auth", __name__)
_HASH_FALSO = bcrypt.hashpw(b"no-importa", bcrypt.gensalt())  # iguala tiempos si el correo no existe


def _destino_seguro(destino):
    p = urlparse(destino or "")
    return destino if destino and not p.netloc and destino.startswith("/") and not destino.startswith("//") else None


@bp.route("/registro", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegistroForm()
    if form.validate_on_submit():
        u = Usuario(nombre=form.nombre.data, email=form.email.data,
                    rol=Rol.query.filter_by(nombre=form.area.data).one())
        u.set_password(form.password.data)
        db.session.add(u)
        db.session.commit()
        flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.signin"))
    return render_template("auth/registro.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def signin():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        u = Usuario.query.filter_by(email=form.email.data).first()
        if u and u.activo:
            ok = u.check_password(form.password.data)
        else:
            bcrypt.checkpw(b"x", _HASH_FALSO)
            ok = False
        if ok:
            login_user(u)
            return redirect(_destino_seguro(request.args.get("next")) or url_for("main.dashboard"))
        flash("Correo o contraseña incorrectos.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.signin"))


@bp.route("/olvide", methods=["GET", "POST"])
def olvide():
    form = OlvideForm()
    if form.validate_on_submit():
        u = Usuario.query.filter_by(email=form.email.data).first()
        if u and u.activo:
            token = services.crear_token_reset(u)
            # Envío de correo simulado: el enlace se registra en la consola del servidor.
            current_app.logger.warning("[CORREO SIMULADO] Para %s: %s", u.email,
                                       url_for("auth.reset", token=token, _external=True))
        flash("Si el correo existe, se envió un enlace de recuperación (revisa la consola del servidor).", "info")
        return redirect(url_for("auth.signin"))
    return render_template("auth/olvide.html", form=form)


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    registro = services.validar_token(token)
    if not registro:
        flash("El enlace no es válido, ya fue usado o expiró.", "danger")
        return redirect(url_for("auth.olvide"))
    form = ResetForm()
    if form.validate_on_submit():
        services.consumir_token(registro, form.password.data)
        flash("Contraseña actualizada. Inicia sesión.", "success")
        return redirect(url_for("auth.signin"))
    return render_template("auth/reset.html", form=form)
