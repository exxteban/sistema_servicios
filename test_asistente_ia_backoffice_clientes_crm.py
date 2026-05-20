from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app import create_app, db
from app.models import Caja, Categoria, Cliente, CrmPlantilla, DetalleVenta, Producto, SesionCaja, Usuario, Venta
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def _crear_venta(cliente, sesion, producto, fecha, total):
    venta = Venta(
        id_cliente=cliente.id_cliente,
        id_sesion_caja=sesion.id_sesion,
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


def _crear_escenario_clientes_crm():
    suffix = uuid4().hex[:8]
    admin = Usuario.query.filter_by(username='admin').first()
    caja = Caja.query.first()
    categoria = Categoria(nombre=f'IA Clientes Categoria {suffix}', activo=True)
    cliente_premium = Cliente(
        nombre=f'Cliente Premium Dormido {suffix}',
        telefono='0981123456',
        tipo='minorista',
        activo=True,
    )
    cliente_activo = Cliente(
        nombre=f'Cliente Activo CRM {suffix}',
        telefono='0981987654',
        tipo='minorista',
        activo=True,
    )
    db.session.add_all([categoria, cliente_premium, cliente_activo])
    db.session.flush()
    producto = Producto(
        codigo=f'IA-CLI-{suffix}',
        nombre=f'Producto Cliente IA {suffix}',
        id_categoria=categoria.id_categoria,
        precio_compra=5000,
        precio_venta=20000,
        stock_actual=10,
    )
    db.session.add(producto)
    db.session.flush()
    sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, monto_inicial=0, estado='cerrada')
    db.session.add(sesion)
    db.session.flush()

    _crear_venta(cliente_premium, sesion, producto, datetime(2026, 1, 4, 10, 0, 0), 200000)
    _crear_venta(cliente_premium, sesion, producto, datetime(2026, 1, 10, 10, 0, 0), 220000)
    _crear_venta(cliente_premium, sesion, producto, datetime(2026, 1, 20, 10, 0, 0), 240000)
    _crear_venta(cliente_activo, sesion, producto, datetime(2026, 4, 20, 10, 0, 0), 90000)
    db.session.add(CrmPlantilla(
        titulo=f'Reactivacion IA {suffix}',
        contenido='Hola {nombre}, vimos que {motivo} Tenemos una propuesta para vos.',
        categoria='reactivacion',
        activa=True,
        orden=1,
        id_usuario_creador=admin.id_usuario,
    ))
    db.session.commit()
    return admin, cliente_premium


def test_catalogo_habilita_tools_de_clientes_y_crm():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'clientes_resumen_inteligencia',
        'clientes_top_valor',
        'clientes_para_contactar',
        'crm_sugerir_mensaje',
    }.issubset(nombres)


def test_tools_clientes_resumen_top_valor_y_contactos():
    app = create_app('testing')

    with app.app_context():
        admin, cliente_premium = _crear_escenario_clientes_crm()
        args = {'periodo': 'custom', 'desde': '2026-01-01', 'hasta': '2026-04-30', 'top_n': 5}

        resumen = ejecutar_tool_backoffice('clientes_resumen_inteligencia', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['total_para_activar'] >= 1
        assert resumen['data']['segmentos']['dormidos'] >= 1

        top_valor = ejecutar_tool_backoffice('clientes_top_valor', args, usuario=admin)
        assert top_valor['ok'] is True
        assert top_valor['data']['clientes'][0]['id_cliente'] == cliente_premium.id_cliente
        assert top_valor['data']['clientes'][0]['total_gastado'] == 660000

        contactar = ejecutar_tool_backoffice('clientes_para_contactar', args, usuario=admin)
        assert contactar['ok'] is True
        assert contactar['data']['clientes'][0]['id_cliente'] == cliente_premium.id_cliente
        assert contactar['data']['clientes'][0]['canal_sugerido'] == 'whatsapp'


def test_tool_crm_sugerir_mensaje_genera_borrador_sin_enviar():
    app = create_app('testing')

    with app.app_context():
        admin, cliente_premium = _crear_escenario_clientes_crm()
        mensaje = ejecutar_tool_backoffice(
            'crm_sugerir_mensaje',
            {'periodo': 'custom', 'desde': '2026-01-01', 'hasta': '2026-04-30', 'id_cliente': cliente_premium.id_cliente},
            usuario=admin,
        )
        assert mensaje['ok'] is True
        assert mensaje['data']['encontrado'] is True
        assert mensaje['data']['envio_automatico'] is False
        assert mensaje['data']['requiere_confirmacion_envio'] is True
        assert cliente_premium.nombre in mensaje['data']['borrador']


def test_tools_clientes_y_crm_respetan_permisos():
    sin_permisos = SimpleNamespace(
        is_authenticated=True,
        es_admin=lambda: False,
        tiene_permiso=lambda _codigo: False,
    )
    solo_clientes = SimpleNamespace(
        is_authenticated=True,
        es_admin=lambda: False,
        tiene_permiso=lambda codigo: codigo == 'ver_clientes',
    )

    assert ejecutar_tool_backoffice('clientes_resumen_inteligencia', {}, usuario=sin_permisos)['error'] == 'sin_permiso_clientes'
    assert ejecutar_tool_backoffice('crm_sugerir_mensaje', {}, usuario=solo_clientes)['error'] == 'sin_permiso_crm'
