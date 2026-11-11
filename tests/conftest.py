from datetime import date, timedelta

import pytest

from app import create_app, sockets
from app.extensions import db
from app.models import Lote, Producto, Proveedor, Rol, Usuario
from config import TestConfig

CLAVE = "Clave1234"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    sockets.conectados.clear()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def crear_usuario(app, email="admin@test.com", rol="admin"):
    with app.app_context():
        u = Usuario(nombre="Usuario Test", email=email, rol=Rol.query.filter_by(nombre=rol).one())
        u.set_password(CLAVE)
        db.session.add(u)
        db.session.commit()


@pytest.fixture
def login(app, client):
    def _login(rol="admin"):
        email = f"{rol}@test.com"
        crear_usuario(app, email, rol)
        r = client.post("/login", data={"email": email, "password": CLAVE})
        assert r.status_code == 302
        return client
    return _login


@pytest.fixture
def datos(app):
    """Producto con dos lotes: A caduca pronto (10 u.), B caduca después (20 u.)."""
    with app.app_context():
        prov = Proveedor(nombre="Proveedor Test", ruc="1790000000001")
        prod = Producto(sku="TEST-1", nombre="Producto de prueba", stock_minimo=5)
        db.session.add_all([prov, prod])
        db.session.flush()
        hoy = date.today()
        for cod, cant, dias in (("B", 20, 120), ("A", 10, 60)):  # A se inserta después pero caduca antes
            db.session.add(Lote(codigo=cod, producto_id=prod.id, proveedor_id=prov.id, cantidad_inicial=cant,
                                cantidad_disponible=cant, costo_unitario=1, fecha_ingreso=hoy,
                                fecha_caducidad=hoy + timedelta(days=dias)))
        db.session.commit()
        return {"producto_id": prod.id, "proveedor_id": prov.id}
