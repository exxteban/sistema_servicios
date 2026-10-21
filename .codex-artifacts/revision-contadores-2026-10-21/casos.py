from datetime import date, datetime

import pytest
import test_talonario_facturas as soporte


@pytest.fixture
def caso():
    c = soporte.TestTalonarioFacturas()
    c.setUp()
    try:
        yield c
    finally:
        c.tearDown()


def test_nuevo_timbrado_reinicia_numeracion(caso):
    from app import db
    from app.models import TalonarioFactura
    from app.services.talonario_facturas import siguiente

    caso._talonario(desde=1, hasta=100, vence=date(2026, 9, 10))
    caso._venta('001-001-0000100', fecha=datetime(2026, 9, 8, 15), timbrado='12345678')
    nuevo = TalonarioFactura(
        timbrado='87654321', vigencia_desde=date(2026, 9, 11),
        vigencia_hasta=date(2027, 9, 30), establecimiento='001',
        punto_expedicion='001', numero_desde=1, numero_hasta=100, activo=True)
    db.session.add(nuevo)
    db.session.commit()
    assert siguiente(nuevo) == 1


def test_mismo_numero_distinto_timbrado_no_es_duplicado(caso):
    from app import db
    from app.models import TalonarioFactura
    from app.services.resumen_contadora import resumen_del_mes

    caso._talonario(desde=1, hasta=100, vence=date(2026, 9, 10))
    caso._venta('001-001-0000001', fecha=datetime(2026, 9, 8, 15), timbrado='12345678')
    db.session.add(TalonarioFactura(
        timbrado='87654321', vigencia_desde=date(2026, 9, 11),
        vigencia_hasta=date(2027, 9, 30), establecimiento='001',
        punto_expedicion='001', numero_desde=1, numero_hasta=100, activo=True))
    db.session.commit()
    caso._venta('001-001-0000001', fecha=datetime(2026, 9, 15, 15), timbrado='87654321')
    assert resumen_del_mes(date(2026, 9, 1), False)['en_papel']['repetidos'] == []


def test_cajero_puede_borrar_numero_de_pendiente(caso):
    from app.services.pos_numero_factura import numero_factura_del_pedido

    assert numero_factura_del_pedido({'numero_factura': ''}, {'numero_factura': '123'}) == (None, None)


def test_no_quitar_factura_deja_nota_credito_huerfana():
    import test_notas_credito_papel as soporte_nc
    from app import db
    from app.models import MovimientoCaja
    from app.services.resumen_contadora import resumen_del_mes

    c = soporte_nc.TestNotasCreditoPapel()
    c.setUp()
    try:
        venta = c._venta()
        devolucion = c._devolucion(venta, montos=[55000])
        assert c._nc(devolucion).status_code == 302
        antes = resumen_del_mes(date(2026, 9, 1), False)
        assert antes['debito'] == 5000
        movimientos = MovimientoCaja.query.count()
        respuesta = c.client.post(f'/contador/venta/{venta.id_venta}/numero-factura',
                                  data={'numero_factura': ''})
        db.session.refresh(venta)
        despues = resumen_del_mes(date(2026, 9, 1), False)
        print('HTTP', respuesta.status_code, 'numero', venta.numero_factura,
              'debito_antes', antes['debito'], 'debito_despues', despues['debito'])
        assert MovimientoCaja.query.count() == movimientos
        assert not (venta.numero_factura is None and despues['en_papel']['notas_credito']['cantidad'] == 1)
    finally:
        c.tearDown()


def test_migracion_legacy_preserva_ventas_y_caja(caso):
    from app import db
    from app.bootstrap.schema import initialize_database
    from app.models import MovimientoCaja, Venta
    from sqlalchemy import text, inspect

    venta = caso._venta(None)
    id_venta = venta.id_venta
    caja = MovimientoCaja(id_sesion_caja=caso.sesion.id_sesion,
                          id_usuario=caso.admin.id_usuario, tipo='ingreso',
                          monto=12345, motivo='Prueba migracion')
    db.session.add(caja)
    db.session.commit()
    id_caja = caja.id_movimiento_caja
    db.session.remove()
    # Simular el esquema anterior en la base aislada creada por la fixture.
    db.session.execute(text('ALTER TABLE ventas DROP COLUMN numero_factura'))
    db.session.execute(text('ALTER TABLE gastos_corrientes DROP COLUMN naturaleza_contable'))
    db.session.execute(text('ALTER TABLE pagos_gastos_corrientes DROP COLUMN naturaleza_contable'))
    db.session.commit()
    initialize_database(caso.app, db, config_name='testing')
    initialize_database(caso.app, db, config_name='testing')
    assert db.session.get(Venta, id_venta).total == 110000
    assert db.session.get(Venta, id_venta).numero_factura is None
    assert db.session.get(MovimientoCaja, id_caja).monto == 12345
    assert 'naturaleza_contable' in {c['name'] for c in inspect(db.engine).get_columns('pagos_gastos_corrientes')}
