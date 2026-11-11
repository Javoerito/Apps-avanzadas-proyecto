"""Medición simple de rendimiento: tiempo de respuesta de consultas con 20 000 productos.
Uso:  python scripts/medir_rendimiento.py
Usa una base SQLite temporal; no toca tu base real."""
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TestConfig  # noqa: E402


class Cfg(TestConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "perf.db")


from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Producto, Rol, Usuario  # noqa: E402

app = create_app(Cfg)
with app.app_context():
    db.session.bulk_save_objects([Producto(sku=f"SKU-{i:06d}", nombre=f"Producto de prueba {i}") for i in range(20000)])
    u = Usuario(nombre="Perf", email="perf@test.com", rol=Rol.query.filter_by(nombre="admin").one())
    u.set_password("Clave1234")
    db.session.add(u)
    db.session.commit()

c = app.test_client()
c.post("/login", data={"email": "perf@test.com", "password": "Clave1234"})


def medir(nombre, url, veces=30):
    t = []
    for _ in range(veces):
        i = time.perf_counter()
        r = c.get(url)
        t.append((time.perf_counter() - i) * 1000)
        assert r.status_code == 200
    print(f"{nombre:<42} media {statistics.mean(t):6.1f} ms | p95 {sorted(t)[int(veces * .95) - 1]:6.1f} ms")


print("20 000 productos, 30 repeticiones por consulta")
medir("Listado paginado (página 1)", "/productos")
medir("Listado paginado (página 1500)", "/productos?page=1500")
medir("Búsqueda por prefijo de SKU", "/productos?q=SKU-0199")
medir("Búsqueda por nombre", "/productos?q=prueba%2019999")
medir("Detalle por identificador", "/productos/10000")
