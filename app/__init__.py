from zoneinfo import ZoneInfo
from datetime import timezone

from flask import Flask, render_template

from config import Config

from .extensions import csrf, db, login_manager, socketio


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app, async_mode="threading")  # mismos orígenes por defecto (anti-CSWSH)

    from . import sockets  # noqa: F401  (registra los eventos)
    from .auth import bp as auth_bp
    from .cli import register_cli
    from .main import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    register_cli(app)

    @app.template_filter("fecha")
    def fecha(d):
        return d.strftime("%d/%m/%Y") if d else "—"

    @app.template_filter("hora_local")
    def hora_local(dt):
        if not dt:
            return "—"
        return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(app.config["ZONA_HORARIA"])).strftime("%d/%m/%Y %H:%M")

    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    for codigo, titulo in ((403, "Acceso denegado"), (404, "Página no encontrada")):
        app.register_error_handler(codigo, lambda e, c=codigo, t=titulo: (render_template("error.html", codigo=c, titulo=t), c))

    with app.app_context():
        from .services import asegurar_datos_base
        db.create_all()
        asegurar_datos_base()
    return app
