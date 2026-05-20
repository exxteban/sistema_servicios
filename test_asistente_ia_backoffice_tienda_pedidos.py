from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app import create_app, db
from app.models import (
    Categoria,
    Cliente,
    MetodoPago,
    Producto,
    TiendaLead,
    TiendaPromocion,
    TiendaPromocionProducto,
    TiendaVisitaEvento,
    Usuario,
)
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS
from pedidos.models import PedidoCliente, PedidoClientePago


def _crear_producto(categoria, suffix, codigo, nombre, precio=100000):
    producto = Producto(
        codigo=f'{codigo}-{suffix}',
        nombre=f'{nombre} {suffix}',
        id_categoria=categoria.id_categoria,
        precio_compra=precio / 2,
        precio_venta=precio,
        stock_actual=10,
        activo=True,
    )
    db.session.add(producto)
    db.session.flush()
    return producto


def _crear_escenario_tienda():
    suffix = uuid4().hex[:8]
    tenant = Cliente(nombre=f'Tenant Tienda IA {suffix}', tipo='minorista', activo=True)
    otro_tenant = Cliente(nombre=f'Otro Tenant IA {suffix}', tipo='minorista', activo=True)
    categoria = Categoria(nombre=f'Categoria Tienda IA {suffix}', activo=True)
    db.session.add_all([tenant, otro_tenant, categoria])
    db.session.flush()
    producto_visto = _crear_producto(categoria, suffix, 'IA-TIENDA-VISTO', 'Producto Muy Visto')
    producto_convierte = _crear_producto(categoria, suffix, 'IA-TIENDA-CONV', 'Producto Convierte')

    for idx in range(6):
        db.session.add(TiendaVisitaEvento(
            id_cliente=tenant.id_cliente,
            id_producto=producto_visto.id_producto,
            visitante_hash=f'vist-{suffix}-{idx}',
            user_agent='Mozilla/5.0 (Linux; Android 14; Mobile)',
            fecha_evento=datetime(2026, 4, 10, 10, idx, 0),
        ))
    for idx in range(3):
        db.session.add(TiendaVisitaEvento(
            id_cliente=tenant.id_cliente,
            id_producto=producto_convierte.id_producto,
            visitante_hash=f'conv-{suffix}-{idx}',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            fecha_evento=datetime(2026, 4, 11, 11, idx, 0),
        ))
    db.session.add(TiendaLead(
        id_cliente=tenant.id_cliente,
        id_producto=producto_convierte.id_producto,
        nombre_contacto='Consulta IA',
        telefono_contacto='0991000000',
        fecha_creacion=datetime(2026, 4, 11, 12, 0, 0),
    ))
    db.session.add(TiendaVisitaEvento(
        id_cliente=otro_tenant.id_cliente,
        id_producto=producto_visto.id_producto,
        visitante_hash=f'otro-{suffix}',
        fecha_evento=datetime(2026, 4, 12, 12, 0, 0),
    ))
    promo = TiendaPromocion(
        id_cliente=tenant.id_cliente,
        nombre=f'Oferta IA {suffix}',
        tipo='porcentaje',
        valor=10,
        fecha_inicio=datetime(2026, 4, 1, 0, 0, 0),
        fecha_fin=datetime(2026, 4, 30, 23, 59, 0),
        activa=True,
    )
    db.session.add(promo)
    db.session.flush()
    db.session.add(TiendaPromocionProducto(id_promocion=promo.id_promocion, id_producto=producto_visto.id_producto))
    db.session.commit()
    return tenant, producto_visto, promo


def _crear_escenario_pedidos():
    suffix = uuid4().hex[:8]
    admin = Usuario.query.filter_by(username='admin').first()
    cliente = Cliente(nombre=f'Cliente Pedido IA {suffix}', tipo='minorista', activo=True)
    db.session.add(cliente)
    db.session.flush()
    pedido_pendiente = PedidoCliente(
        numero_pedido=900001,
        id_cliente=cliente.id_cliente,
        id_usuario_creacion=admin.id_usuario,
        estado='pago_parcial',
        fecha_creacion=datetime(2026, 4, 14, 10, 0, 0),
        subtotal=500000,
        total=500000,
        total_pagado=150000,
        saldo_pendiente=350000,
    )
    pedido_pagado = PedidoCliente(
        numero_pedido=900002,
        id_cliente=cliente.id_cliente,
        id_usuario_creacion=admin.id_usuario,
        estado='pagado',
        fecha_creacion=datetime(2026, 4, 15, 10, 0, 0),
        subtotal=200000,
        total=200000,
        total_pagado=200000,
        saldo_pendiente=0,
    )
    db.session.add_all([pedido_pendiente, pedido_pagado])
    db.session.flush()
    metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
    db.session.add(PedidoClientePago(
        id_pedido=pedido_pendiente.id_pedido,
        id_metodo_pago=metodo.id_metodo_pago,
        id_usuario=admin.id_usuario,
        tipo_pago='sena',
        monto=150000,
        estado='activo',
        fecha_pago=datetime(2026, 4, 14, 11, 0, 0),
    ))
    db.session.commit()
    return pedido_pendiente


def test_catalogo_habilita_tools_de_tienda_y_pedidos():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'tienda_resumen_analytics',
        'tienda_productos_mucha_vista_poca_consulta',
        'tienda_ofertas_rendimiento',
        'pedidos_resumen',
        'pedidos_pagos_pendientes',
    }.issubset(nombres)


def test_tools_tienda_resumen_productos_y_ofertas_por_cliente():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        tenant, producto_visto, promo = _crear_escenario_tienda()
        args = {'id_cliente': tenant.id_cliente, 'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}

        resumen = ejecutar_tool_backoffice('tienda_resumen_analytics', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['resumen']['total_visitas'] == 9
        assert resumen['data']['resumen']['consultas_iniciadas'] == 1

        atencion = ejecutar_tool_backoffice('tienda_productos_mucha_vista_poca_consulta', args, usuario=admin)
        assert atencion['ok'] is True
        assert atencion['data']['productos'][0]['id_producto'] == producto_visto.id_producto
        assert atencion['data']['productos'][0]['consultas_iniciadas'] == 0

        ofertas = ejecutar_tool_backoffice('tienda_ofertas_rendimiento', args, usuario=admin)
        assert ofertas['ok'] is True
        assert ofertas['data']['ofertas'][0]['id_promocion'] == promo.id_promocion
        assert ofertas['data']['ofertas'][0]['visitas_productos'] == 6


def test_tools_tienda_exigen_id_cliente_para_evitar_cruce_tenant():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        respuesta = ejecutar_tool_backoffice('tienda_resumen_analytics', {'periodo': 'mes'}, usuario=admin)
        assert respuesta['ok'] is True
        assert respuesta['data']['encontrado'] is False
        assert respuesta['data']['error'] == 'id_cliente_requerido'


def test_tools_pedidos_resumen_y_pagos_pendientes():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        pedido = _crear_escenario_pedidos()
        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}

        resumen = ejecutar_tool_backoffice('pedidos_resumen', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['total_pedidos'] >= 2
        assert resumen['data']['saldo_pendiente'] >= 350000
        assert any(item['estado'] == 'pago_parcial' for item in resumen['data']['por_estado'])

        pendientes = ejecutar_tool_backoffice('pedidos_pagos_pendientes', {'top_n': 5}, usuario=admin)
        assert pendientes['ok'] is True
        assert any(item['id_pedido'] == pedido.id_pedido for item in pendientes['data']['pedidos'])
        assert pendientes['data']['saldo_pendiente_total'] >= 350000


def test_tools_tienda_y_pedidos_respetan_permisos():
    sin_permisos = SimpleNamespace(
        is_authenticated=True,
        es_admin=lambda: False,
        tiene_permiso=lambda _codigo: False,
    )
    solo_reportes = SimpleNamespace(
        is_authenticated=True,
        es_admin=lambda: False,
        tiene_permiso=lambda codigo: codigo == 'ver_reportes',
    )

    assert ejecutar_tool_backoffice('tienda_resumen_analytics', {}, usuario=sin_permisos)['error'] == 'sin_permiso_tienda'
    assert ejecutar_tool_backoffice('pedidos_resumen', {}, usuario=solo_reportes)['error'] == 'sin_permiso_pedidos'
