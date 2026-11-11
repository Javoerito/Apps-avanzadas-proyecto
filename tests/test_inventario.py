from datetime import date, timedelta

from app import services
from app.extensions import db
from app.models import Lote, Movimiento, Producto, SolicitudReposicion, Usuario

PROD = {"sku": "abc-100", "nombre": "Arroz 1kg", "descripcion": "", "stock_minimo": 5, "unidad": "unidad", "estado": "activo"}


def test_crud_producto_completo(login, app):
    c = login("admin")
    assert c.post("/productos/nuevo", data=PROD).status_code == 302
    with app.app_context():
        p = Producto.query.one()
        assert p.sku == "ABC-100"  # se normaliza a mayúsculas
        pid = p.id
    assert b"Ya existe" in c.post("/productos/nuevo", data=PROD).data          # SKU único
    assert b"Entre 3 y 120" in c.post("/productos/nuevo", data=dict(PROD, sku="X-1", nombre="ab")).data
    assert b"Arroz 1kg" in c.get(f"/productos/{pid}").data                     # consulta por id
    assert c.post(f"/productos/{pid}/editar", data=dict(PROD, nombre="Arroz Premium")).status_code == 302
    with app.app_context():
        assert db.session.get(Producto, pid).nombre == "Arroz Premium"
    assert c.post(f"/productos/{pid}/eliminar").status_code == 302
    with app.app_context():
        assert Producto.query.count() == 0
    assert c.get(f"/productos/{pid}").status_code == 404


def test_listado_paginado_y_busqueda(login, app):
    c = login("admin")
    with app.app_context():
        db.session.add_all(Producto(sku=f"SKU-{i:03d}", nombre=f"Producto {i}") for i in range(25))
        db.session.add(Producto(sku="ZZZ-1", nombre="Café especial"))
        db.session.commit()
    p1 = c.get("/productos").data
    assert b"Siguiente" in p1 and b"de 26 registros" in p1
    assert p1.count(b"Ver</a>") == 10 and c.get("/productos?page=3").data.count(b"Ver</a>") == 6
    r = c.get("/productos?q=caf%C3%A9")
    assert b"Caf" in r.data and b"SKU-001" not in r.data
    assert b"No se encontraron" in c.get("/productos?q=%25%27%3B--").data  # entrada maliciosa: sin error


def test_salida_aplica_fefo_y_excluye_vencidos(login, app, datos):
    c = login("admin")
    pid = datos["producto_id"]
    with app.app_context():  # lote vencido con stock: no debe venderse
        db.session.add(Lote(codigo="OLD", producto_id=pid, proveedor_id=datos["proveedor_id"], cantidad_inicial=50,
                            cantidad_disponible=50, costo_unitario=1, fecha_ingreso=date.today() - timedelta(days=90),
                            fecha_caducidad=date.today() - timedelta(days=1)))
        db.session.commit()
    assert c.post(f"/productos/{pid}/salida", data={"cantidad": 15}).status_code == 302
    with app.app_context():
        lotes = {l.codigo: l.cantidad_disponible for l in Lote.query.all()}
        assert lotes == {"A": 0, "B": 15, "OLD": 50}          # A (caduca antes) se agota primero
        assert Lote.query.filter_by(codigo="A").one().estado == "agotado"
        assert Movimiento.query.filter_by(tipo="SALIDA").count() == 2


def test_salida_con_stock_insuficiente(login, app, datos):
    c = login("admin")
    r = c.post(f"/productos/{datos['producto_id']}/salida", data={"cantidad": 31})
    assert r.status_code == 200 and b"Stock insuficiente" in r.data
    with app.app_context():
        assert sum(l.cantidad_disponible for l in Lote.query.all()) == 30


def test_entrada_de_lote_valida_fechas_y_duplicados(login, app, datos):
    c = login("bodega")
    url = f"/productos/{datos['producto_id']}/entrada"
    base = {"codigo": "n1", "proveedor_id": datos["proveedor_id"], "cantidad": 10, "costo": "2.50",
            "fecha_ingreso": date.today().isoformat(), "fecha_caducidad": (date.today() + timedelta(days=90)).isoformat()}
    assert c.post(url, data=base).status_code == 302
    assert b"ya existe" in c.post(url, data=base).data                                   # código repetido
    ayer = (date.today() - timedelta(days=1)).isoformat()
    assert b"caducado" in c.post(url, data=dict(base, codigo="n2", fecha_caducidad=ayer)).data
    assert b"obligatorio" not in c.post(url, data=dict(base, codigo="n3", cantidad=0)).data  # cantidad 0 rechazada
    with app.app_context():
        assert Lote.query.filter_by(codigo="N1").one().cantidad_disponible == 10


def test_roles_restringen_acciones(login, app, datos):
    c = login("ventas")
    assert c.get("/productos/nuevo").status_code == 403
    assert c.post(f"/productos/{datos['producto_id']}/eliminar").status_code == 403
    assert c.get(f"/productos/{datos['producto_id']}/entrada").status_code == 403
    assert c.get(f"/productos/{datos['producto_id']}/salida").status_code == 200


def test_eliminar_producto_con_lotes_se_bloquea(login, app, datos):
    c = login("admin")
    c.post(f"/productos/{datos['producto_id']}/eliminar")
    with app.app_context():
        assert Producto.query.count() == 1
