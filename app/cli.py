import os
import secrets
from datetime import date, timedelta

import click

from .extensions import db
from .models import Lote, Movimiento, Producto, Proveedor, Rol, Usuario


def register_cli(app):
    @app.cli.command("seed")
    def seed():
        """Carga datos de demostración ficticios (usuarios, proveedores, productos y lotes)."""
        if Usuario.query.first():
            click.echo("Ya existen usuarios; no se cargó nada.")
            return
        clave = os.environ.get("SEED_PASSWORD") or ("Demo" + secrets.token_hex(4) + "9")
        usuarios = {}
        for nombre, email, rol in (("Administrador Demo", "admin@demo.local", "admin"),
                                   ("Bodega Demo", "bodega@demo.local", "bodega"),
                                   ("Ventas Demo", "ventas@demo.local", "ventas")):
            u = Usuario(nombre=nombre, email=email, rol=Rol.query.filter_by(nombre=rol).one())
            u.set_password(clave)
            db.session.add(u)
            usuarios[rol] = u
        provs = [Proveedor(nombre="Alimentos del Valle S.A.", ruc="1790000000001", telefono="022345678"),
                 Proveedor(nombre="Bebidas Andinas Cía. Ltda.", ruc="1790000000002", telefono="022456789")]
        db.session.add_all(provs)
        db.session.flush()
        hoy = date.today()
        catalogo = [("ARR-001", "Arroz blanco 1kg", 40, "unidad"), ("ACE-002", "Aceite de girasol 1L", 30, "unidad"),
                    ("AZU-003", "Azúcar 2kg", 25, "unidad"), ("LEC-004", "Leche entera 1L", 50, "unidad"),
                    ("ATU-005", "Atún en lata 170g", 60, "caja"), ("GAL-006", "Galletas de sal", 20, "paquete"),
                    ("JUG-007", "Jugo de naranja 500ml", 35, "unidad"), ("FID-008", "Fideo spaghetti 400g", 30, "unidad"),
                    ("CAF-009", "Café molido 250g", 15, "unidad"), ("AGU-010", "Agua sin gas 600ml", 80, "caja"),
                    ("SAL-011", "Sal yodada 1kg", 20, "unidad"), ("HAR-012", "Harina de trigo 1kg", 25, "unidad")]
        for i, (sku, nombre, minimo, unidad) in enumerate(catalogo):
            p = Producto(sku=sku, nombre=nombre, stock_minimo=minimo, unidad=unidad)
            db.session.add(p)
            db.session.flush()
            # Lote A: caduca pronto (para demostrar FEFO y alertas); Lote B: caduca más tarde.
            for j, (dias, cant) in enumerate(((10 + i * 3, 30 + i * 5), (180 + i * 10, 60 + i * 4))):
                lote = Lote(codigo=f"L{2026}{i:02d}{'AB'[j]}", producto_id=p.id, proveedor_id=provs[i % 2].id,
                            cantidad_inicial=cant, cantidad_disponible=cant, costo_unitario=round(0.5 + i * 0.35, 2),
                            fecha_ingreso=hoy - timedelta(days=15), fecha_caducidad=hoy + timedelta(days=dias),
                            ubicacion=f"Rack {chr(65 + i % 4)}-{j + 1}")
                db.session.add(lote)
                db.session.flush()
                db.session.add(Movimiento(tipo="ENTRADA", producto_id=p.id, lote_id=lote.id, cantidad=cant,
                                          usuario_id=usuarios["bodega"].id, motivo="Carga inicial"))
        db.session.commit()
        click.echo(f"Datos cargados. Usuarios: admin@demo.local, bodega@demo.local, ventas@demo.local\nContraseña: {clave}")
