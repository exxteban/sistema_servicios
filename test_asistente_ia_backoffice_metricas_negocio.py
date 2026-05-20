from datetime import datetime
from uuid import uuid4

from app import create_app, db
from app.models import Caja, Categoria, Cliente, DetalleVenta, MovimientoCaja, Producto, SesionCaja, Usuario, Venta
from app.services.ia_backoffice.response_engine import generar_respuesta_backoffice
from app.services.ia_backoffice.settings import CLAVE_ENABLED
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def _crear_venta(cliente, sesion, usuario, producto, fecha, total):
    venta = Venta(
        id_cliente=cliente.id_cliente,
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=usuario.id_usuario,
        fecha_venta=fecha,
        subtotal=total,
        total=total,
        estado='completada',
    )
    db.session.add(venta)
    db.session.flush()
    db.session.add(DetalleVenta(
        id_venta=venta.id_venta,
        id_producto=producto.id_producto,
        cantidad=1,
        precio_unitario=total,
        precio_original=total,
        porcentaje_iva=10,
        monto_iva=0,
        subtotal=total,
    ))
    return venta


def _crear_datos_metricas():
    suffix = uuid4().hex[:8]
    admin = Usuario.query.filter_by(username='admin').first()
    caja = Caja.query.first()
    cliente = Cliente(nombre=f'Cliente Metricas IA {suffix}', tipo='minorista', activo=True)
    categoria = Categoria(nombre=f'IA Metricas Categoria {suffix}', activo=True)
    db.session.add_all([cliente, categoria])
    db.session.flush()
    producto = Producto(
        codigo=f'IA-MET-{suffix}',
        nombre=f'Producto Metricas {suffix}',
        id_categoria=categoria.id_categoria,
        precio_compra=1500,
        precio_venta=6000,
        stock_actual=10,
    )
    db.session.add(producto)
    db.session.flush()
    sesion = SesionCaja(
        id_caja=caja.id_caja,
        id_usuario=admin.id_usuario,
        estado='cerrada',
        fecha_apertura=datetime(2026, 5, 5, 8, 0, 0),
        fecha_cierre=datetime(2026, 5, 5, 18, 0, 0),
    )
    db.session.add(sesion)
    db.session.flush()
    _crear_venta(cliente, sesion, admin, producto, datetime(2026, 5, 5, 9, 0, 0), 6000)
    db.session.add(MovimientoCaja(
        id_sesion_caja=sesion.id_sesion,
        id_usuario=admin.id_usuario,
        tipo='ingreso',
        monto=7000,
        motivo='Ingreso manual metricas IA',
        fecha_movimiento=datetime(2026, 5, 5, 11, 0, 0),
    ))
    db.session.commit()
    return admin


def test_catalogo_habilita_tools_de_metricas_negocio():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'metricas_explicacion_negocio',
        'metricas_comparacion_negocio',
        'metricas_resumen_operativo',
    }.issubset(nombres)


def test_tool_metricas_explicacion_aclara_que_ganancia_neta_no_es_exacta():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        respuesta = ejecutar_tool_backoffice(
            'metricas_explicacion_negocio',
            {'concepto': 'ganancia_neta'},
            usuario=admin,
        )

    assert respuesta['ok'] is True
    assert respuesta['data']['encontrado'] is True
    assert respuesta['data']['disponible_en_sistema'] is False
    assert 'no calcula una ganancia neta contable exacta' in respuesta['data']['nota_sistema']


def test_tool_metricas_resumen_operativo_combina_ventas_y_caja():
    app = create_app('testing')

    with app.app_context():
        admin = _crear_datos_metricas()
        respuesta = ejecutar_tool_backoffice(
            'metricas_resumen_operativo',
            {'periodo': 'custom', 'desde': '2026-05-01', 'hasta': '2026-05-31'},
            usuario=admin,
        )

    assert respuesta['ok'] is True
    assert respuesta['data']['ventas_total'] == 6000
    assert respuesta['data']['ganancia_bruta_estimada'] == 4500
    assert respuesta['data']['resultado_caja_movimientos'] == 7000
    assert respuesta['data']['ganancia_neta_exacta_disponible'] is False


def test_generar_respuesta_backoffice_resuelve_metricas_con_respuesta_directa():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        from app.models import Configuracion

        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        respuesta = generar_respuesta_backoffice(
            [{'role': 'user', 'content': 'Cual es la diferencia entre ganancia neta y resultado de caja?'}],
            admin,
        )

    assert respuesta['estado'] == 'ok'
    assert respuesta['tools_usadas'] == ['metricas_comparacion_negocio']
    assert 'liquidez' in respuesta['contenido'].lower() or 'caja' in respuesta['contenido'].lower()
