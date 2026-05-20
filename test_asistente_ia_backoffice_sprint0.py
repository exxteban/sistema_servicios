import json
import re
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from werkzeug.datastructures import MultiDict

from app import create_app, db
from app.models import (
    AsistenteIABackofficeAudit,
    Caja,
    Categoria,
    Cliente,
    Configuracion,
    CuentaPorCobrar,
    DetalleVenta,
    PagoCuentaCobrar,
    Permiso,
    Producto,
    Rol,
    SesionCaja,
    Usuario,
    Venta,
)
from app.utils.helpers import today_local
from app.services.ia_backoffice.security import es_usuario_root
from app.services.ia_backoffice.response_engine import (
    _assistant_tool_message,
    _normalizar_respuesta_texto,
    _tool_calls_textuales,
    generar_respuesta_backoffice,
)
from app.services.ia_backoffice.settings import (
    CLAVE_DEEPSEEK_BASE_URL,
    CLAVE_ENABLED,
    CLAVE_MODEL,
    CLAVE_PROVIDER,
    obtener_configuracion_asistente,
)
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def _extraer_csrf(html):
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html or '')
    assert match is not None
    return match.group(1)


def _loguear(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _usuario(app, username):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        return usuario.id_usuario


def test_defaults_y_permisos_asistente_ia_backoffice_se_crean():
    app = create_app('testing')

    with app.app_context():
        codigos = {
            codigo
            for (codigo,) in db.session.query(Permiso.codigo)
            .filter(Permiso.codigo.in_(['usar_asistente_ia', 'gestionar_asistente_ia']))
            .all()
        }
        assert codigos == {'usar_asistente_ia', 'gestionar_asistente_ia'}
        assert Configuracion.obtener(CLAVE_PROVIDER) == 'deepseek'
        assert Configuracion.obtener(CLAVE_MODEL) == 'deepseek-v4-flash'
        assert Configuracion.obtener(CLAVE_DEEPSEEK_BASE_URL) == 'https://api.deepseek.com'
        assert obtener_configuracion_asistente().enabled is False


def test_admin_no_root_no_puede_habilitar_ia_backoffice():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, _usuario(app, 'admin'))

    response = client.get('/usuarios/configuracion')
    assert response.status_code == 200
    csrf = _extraer_csrf(response.get_data(as_text=True))

    response = client.post(
        '/usuarios/configuracion/ia-backoffice',
        data={'csrf_token': csrf, 'ia_backoffice_enabled': '1'},
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 403

    with app.app_context():
        assert Configuracion.obtener_bool(CLAVE_ENABLED, default=False) is False


def test_root_puede_habilitar_ia_backoffice_con_defaults_deepseek():
    app = create_app('testing')
    client = app.test_client()
    root_id = _usuario(app, 'root')
    _loguear(client, root_id)

    response = client.get('/usuarios/configuracion')
    assert response.status_code == 200
    csrf = _extraer_csrf(response.get_data(as_text=True))

    response = client.post(
        '/usuarios/configuracion/ia-backoffice',
        data={
            'csrf_token': csrf,
            'ia_backoffice_enabled': '1',
            'ia_backoffice_provider': 'deepseek',
            'ia_backoffice_model': '',
            'ia_backoffice_deepseek_base_url': 'https://api.deepseek.com',
        },
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200
    assert response.get_json()['model'] == 'deepseek-v4-flash'

    with app.app_context():
        root = db.session.get(Usuario, root_id)
        assert es_usuario_root(root) is True
        cfg = obtener_configuracion_asistente()
        assert cfg.enabled is True
        assert cfg.provider == 'deepseek'
        assert cfg.model == 'deepseek-v4-flash'
        assert cfg.deepseek_base_url == 'https://api.deepseek.com'


def test_root_puede_habilitar_ia_backoffice_desde_form_con_hidden_y_checkbox():
    app = create_app('testing')
    client = app.test_client()
    root_id = _usuario(app, 'root')
    _loguear(client, root_id)

    response = client.get('/usuarios/configuracion')
    assert response.status_code == 200
    csrf = _extraer_csrf(response.get_data(as_text=True))

    response = client.post(
        '/usuarios/configuracion/ia-backoffice',
        data=MultiDict([
            ('csrf_token', csrf),
            ('ia_backoffice_enabled', '0'),
            ('ia_backoffice_enabled', '1'),
            ('ia_backoffice_provider', 'deepseek'),
            ('ia_backoffice_model', 'deepseek-v4-flash'),
            ('ia_backoffice_deepseek_base_url', 'https://api.deepseek.com'),
        ]),
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200

    with app.app_context():
        assert Configuracion.obtener_bool(CLAVE_ENABLED, default=False) is True


def test_root_ve_panel_configuracion_asistente_ia_backoffice():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, _usuario(app, 'root'))

    response = client.get('/usuarios/configuracion')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Asistente IA interno' in html
    assert 'ia_backoffice_enabled' in html


def test_sprint2_catalogo_habilita_tools_de_ventas():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'ventas_resumen_periodo',
        'ventas_top_productos',
        'ventas_por_categoria',
        'ventas_tendencia',
        'ventas_por_vendedor',
    }.issubset(nombres)


def test_usuario_sin_permiso_no_puede_entrar_al_chat():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        rol = Rol.query.filter_by(nombre='Vendedor').first()
        assert rol is not None
        usuario = Usuario(
            username='sin_permiso_ia',
            nombre_completo='Sin Permiso IA',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()
        user_id = usuario.id_usuario

    _loguear(client, user_id)
    response = client.get('/asistente-ia/')
    assert response.status_code in (302, 303)

    response = client.post(
        '/asistente-ia/api/chat',
        json={'mensaje': 'Hola'},
        headers={'X-CSRFToken': client.get('/auth/csrf').get_json()['csrf_token']},
    )
    assert response.status_code == 403


def test_chat_con_ia_apagada_responde_fallback_y_audita():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, _usuario(app, 'admin'))
    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ENABLED, False)

    csrf = client.get('/auth/csrf').get_json()['csrf_token']
    response = client.post(
        '/asistente-ia/api/chat',
        json={'mensaje': 'Como van mis ventas?'},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['estado'] == 'desactivado'
    assert 'desactivado' in data['mensaje']

    with app.app_context():
        audit = AsistenteIABackofficeAudit.query.order_by(
            AsistenteIABackofficeAudit.id_audit.desc()
        ).first()
        assert audit is not None
        assert audit.estado == 'desactivado'
        assert audit.pregunta == 'Como van mis ventas?'


def test_chat_limpia_historial_de_sesion():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, _usuario(app, 'admin'))

    csrf = client.get('/auth/csrf').get_json()['csrf_token']
    response = client.post(
        '/asistente-ia/api/chat',
        json={'mensaje': 'Hola asistente'},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get('ia_backoffice_historial')

    response = client.post('/asistente-ia/api/limpiar', json={}, headers={'X-CSRFToken': csrf})
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert not sess.get('ia_backoffice_historial')


def test_response_engine_reenvia_reasoning_content_en_tool_call_de_deepseek():
    tool_call = SimpleNamespace(
        id='call_123',
        function=SimpleNamespace(name='ventas_resumen_periodo', arguments='{"periodo":"mes"}'),
    )
    message = SimpleNamespace(
        content='',
        tool_calls=[tool_call],
        reasoning_content='razonamiento interno devuelto por DeepSeek',
    )

    payload = _assistant_tool_message(message)

    assert payload['role'] == 'assistant'
    assert payload['reasoning_content'] == 'razonamiento interno devuelto por DeepSeek'
    assert payload['tool_calls'][0]['function']['name'] == 'ventas_resumen_periodo'


def test_response_engine_normaliza_montos_a_guaranies_y_limpia_markdown_basico():
    texto = '**Total vendido:** $21.239.529\n**Ticket promedio:** $1.061.976'

    normalizado = _normalizar_respuesta_texto(texto)

    assert '$' not in normalizado
    assert '**' not in normalizado
    assert 'Gs. 21.239.529' in normalizado
    assert 'Gs. 1.061.976' in normalizado


def test_response_engine_detecta_tool_call_dsml_textual():
    contenido = """
<| DSML | tool_calls>
<| DSML | invoke name="inventario_resumen">
{"top_n": 5}
</| DSML | invoke>
</| DSML | tool_calls>
"""

    calls = _tool_calls_textuales(contenido)

    assert len(calls) == 1
    assert calls[0].function.name == 'inventario_resumen'
    assert json.loads(calls[0].function.arguments)['top_n'] == 5


def test_response_engine_responde_listado_productos_sin_exponer_tool_call():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        categoria = Categoria(nombre=f'Celulares IA {suffix}', activo=True)
        db.session.add(categoria)
        db.session.flush()
        producto = Producto(
            codigo=f'CEL-IA-{suffix}',
            nombre=f'Celular Test IA {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=100000,
            precio_venta=150000,
            stock_actual=3,
            activo=True,
        )
        db.session.add(producto)
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        Configuracion.establecer('ia_api_key', 'test-key')
        db.session.commit()

        respuesta = generar_respuesta_backoffice(
            [{'role': 'user', 'content': f'que productos de Celular Test IA {suffix} hay?'}],
            admin,
        )

        assert respuesta['estado'] == 'ok'
        assert 'DSML' not in respuesta['contenido']
        assert producto.codigo in respuesta['contenido']
        assert 'buscar_entidad_backoffice' in respuesta['tools_usadas']


def test_tools_ventas_devuelven_agregados_compactos():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        cliente = Cliente(nombre=f'Cliente IA Ventas {suffix}', tipo='minorista', activo=True)
        categoria_a = Categoria(nombre=f'IA Categoria A {suffix}', activo=True)
        categoria_b = Categoria(nombre=f'IA Categoria B {suffix}', activo=True)
        db.session.add_all([cliente, categoria_a, categoria_b])
        db.session.flush()

        producto_a = Producto(
            codigo=f'IA-SALES-A-{suffix}',
            nombre=f'Producto IA A {suffix}',
            id_categoria=categoria_a.id_categoria,
            precio_compra=500,
            precio_venta=1000,
            stock_actual=10,
        )
        producto_b = Producto(
            codigo=f'IA-SALES-B-{suffix}',
            nombre=f'Producto IA B {suffix}',
            id_categoria=categoria_b.id_categoria,
            precio_compra=500,
            precio_venta=2000,
            stock_actual=10,
        )
        db.session.add_all([producto_a, producto_b])
        db.session.flush()

        sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, estado='cerrada')
        db.session.add(sesion)
        db.session.flush()

        def crear_venta(producto, fecha, total, cantidad=1):
            venta = Venta(
                id_cliente=cliente.id_cliente,
                id_sesion_caja=sesion.id_sesion,
                id_usuario_vendedor=admin.id_usuario,
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
                cantidad=cantidad,
                precio_unitario=total / cantidad,
                precio_original=total / cantidad,
                porcentaje_iva=10,
                monto_iva=0,
                subtotal=total,
            ))

        from datetime import datetime
        crear_venta(producto_a, datetime(2026, 4, 3, 10, 0, 0), 1000, cantidad=1)
        crear_venta(producto_b, datetime(2026, 4, 4, 10, 0, 0), 4000, cantidad=2)
        crear_venta(producto_a, datetime(2026, 3, 3, 10, 0, 0), 500, cantidad=1)
        db.session.commit()

        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}
        resumen = ejecutar_tool_backoffice('ventas_resumen_periodo', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['total_ventas'] == 5000
        assert resumen['data']['cantidad_ventas'] == 2

        top = ejecutar_tool_backoffice('ventas_top_productos', args, usuario=admin)
        assert top['ok'] is True
        assert top['data']['productos'][0]['codigo'] == f'IA-SALES-B-{suffix}'
        assert top['data']['productos'][0]['unidades'] == 2

        categorias = ejecutar_tool_backoffice('ventas_por_categoria', args, usuario=admin)
        assert categorias['ok'] is True
        assert categorias['data']['categorias'][0]['categoria'] == f'IA Categoria B {suffix}'

        tendencia = ejecutar_tool_backoffice('ventas_tendencia', args, usuario=admin)
        assert tendencia['ok'] is True
        assert len(tendencia['data']['serie']) == 30

        vendedores = ejecutar_tool_backoffice('ventas_por_vendedor', args, usuario=admin)
        assert vendedores['ok'] is True
        assert vendedores['data']['vendedores'][0]['username'] == 'admin'


def test_tools_cobranzas_devuelven_resumen_morosos_y_vencimientos():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        cliente_moroso = Cliente(nombre=f'Cliente Moroso IA {suffix}', tipo='minorista', activo=True)
        cliente_proximo = Cliente(nombre=f'Cliente Proximo IA {suffix}', tipo='minorista', activo=True)
        categoria = Categoria(nombre=f'IA Cobranzas Categoria {suffix}', activo=True)
        db.session.add_all([cliente_moroso, cliente_proximo, categoria])
        db.session.flush()
        producto = Producto(
            codigo=f'IA-COB-{suffix}',
            nombre=f'Producto Cobranzas {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=1000,
            precio_venta=2000,
            stock_actual=10,
        )
        db.session.add(producto)
        db.session.flush()
        sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, estado='cerrada')
        db.session.add(sesion)
        db.session.flush()

        hoy = today_local()

        def venta_credito(cliente, total):
            venta = Venta(
                id_cliente=cliente.id_cliente,
                id_sesion_caja=sesion.id_sesion,
                id_usuario_vendedor=admin.id_usuario,
                fecha_venta=datetime(2026, 4, 5, 12, 0, 0),
                subtotal=total,
                total=total,
                estado='completada',
                tipo_venta='credito',
                saldo_pendiente=total,
            )
            db.session.add(venta)
            db.session.flush()
            return venta

        venta_vencida = venta_credito(cliente_moroso, 3000)
        venta_proxima = venta_credito(cliente_proximo, 2000)
        cuenta_vencida = CuentaPorCobrar(
            id_venta=venta_vencida.id_venta,
            id_cliente=cliente_moroso.id_cliente,
            monto_total=3000,
            monto_cobrado=500,
            saldo_pendiente=2500,
            fecha_vencimiento=hoy - timedelta(days=5),
            estado='vencida',
            dias_vencido=5,
        )
        cuenta_proxima = CuentaPorCobrar(
            id_venta=venta_proxima.id_venta,
            id_cliente=cliente_proximo.id_cliente,
            monto_total=2000,
            monto_cobrado=0,
            saldo_pendiente=2000,
            fecha_vencimiento=hoy + timedelta(days=3),
            estado='pendiente',
            dias_vencido=0,
        )
        db.session.add_all([cuenta_vencida, cuenta_proxima])
        db.session.flush()
        db.session.add(PagoCuentaCobrar(
            id_cuenta_cobrar=cuenta_vencida.id_cuenta_cobrar,
            id_sesion_caja=sesion.id_sesion,
            id_usuario=admin.id_usuario,
            monto=500,
            id_metodo_pago=1,
            fecha_pago=datetime(2026, 4, 8, 10, 0, 0),
            estado='activo',
        ))
        db.session.commit()

        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}
        resumen = ejecutar_tool_backoffice('cobranzas_resumen', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['cuentas_vencidas'] >= 1
        assert resumen['data']['cobrado_periodo'] >= 500

        morosos = ejecutar_tool_backoffice('cobranzas_clientes_morosos', {'top_n': 5}, usuario=admin)
        assert morosos['ok'] is True
        assert any(item['nombre'] == f'Cliente Moroso IA {suffix}' for item in morosos['data']['clientes'])

        vencimientos = ejecutar_tool_backoffice('cobranzas_proximos_vencimientos', {'top_n': 10}, usuario=admin)
        assert vencimientos['ok'] is True
        assert any(item['cliente'] == f'Cliente Proximo IA {suffix}' for item in vencimientos['data']['vencimientos'])


def test_tools_inventario_resumen_reponer_e_inmovilizados():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        categoria = Categoria(nombre=f'IA Inventario Categoria {suffix}', activo=True)
        db.session.add(categoria)
        db.session.flush()
        reponer = Producto(
            codigo=f'IA-REP-{suffix}',
            nombre=f'Producto Reponer {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=1000,
            precio_venta=2000,
            stock_actual=0,
            stock_minimo=50,
        )
        inmovilizado = Producto(
            codigo=f'IA-INM-{suffix}',
            nombre=f'Producto Inmovilizado {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=999999,
            precio_venta=1200000,
            stock_actual=99,
            stock_minimo=1,
        )
        db.session.add_all([reponer, inmovilizado])
        db.session.commit()

        resumen = ejecutar_tool_backoffice('inventario_resumen', {}, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['productos_stock_bajo'] >= 1

        reposicion = ejecutar_tool_backoffice('inventario_productos_reponer', {'top_n': 10}, usuario=admin)
        assert reposicion['ok'] is True
        assert any(item['codigo'] == f'IA-REP-{suffix}' for item in reposicion['data']['productos'])

        inmovilizados = ejecutar_tool_backoffice(
            'inventario_productos_inmovilizados',
            {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 10},
            usuario=admin,
        )
        assert inmovilizados['ok'] is True
        assert any(item['codigo'] == f'IA-INM-{suffix}' for item in inmovilizados['data']['productos'])


def test_tools_respetan_permisos_por_modulo():
    app = create_app('testing')

    with app.app_context():
        rol = Rol.query.filter_by(nombre='Tecnico').first()
        usuario = Usuario(
            username=f'sin_modulos_ia_{uuid4().hex[:6]}',
            nombre_completo='Sin Modulos IA',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()

        assert ejecutar_tool_backoffice('cobranzas_resumen', {}, usuario=usuario)['error'] == 'sin_permiso_cobranzas'
        assert ejecutar_tool_backoffice('inventario_resumen', {}, usuario=usuario)['error'] == 'sin_permiso_inventario'
