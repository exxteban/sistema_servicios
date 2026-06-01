from datetime import datetime, timedelta
import io
from urllib.parse import parse_qs, unquote, urlparse

from app import create_app, db
from app.models import (
    Categoria,
    Cliente,
    Configuracion,
    Producto,
    TiendaConfig,
    TiendaPromocion,
    TiendaPromocionGastronomiaProducto,
    TiendaPromocionProducto,
    Usuario,
)
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaGrupoOpciones,
    GastronomiaOpcionProducto,
    GastronomiaProducto,
)
from gastronomia.services.modo_operacion import (
    CLAVE_MODO_OPERACION_PRINCIPAL,
    MODO_GASTRONOMIA,
    MODO_SERVICIOS,
)


def _crear_tienda_gastronomia(slug='gastro-presupuesto-test'):
    cliente = Cliente(nombre=f'Cliente {slug}', tipo='minorista', activo=True)
    db.session.add(cliente)
    db.session.flush()

    config_gastro = GastronomiaClienteConfig(
        cliente_id=cliente.id_cliente,
        modo_operacion=MODO_GASTRONOMIA,
        gastronomia_activo=True,
    )
    categoria = GastronomiaCategoria(
        cliente_id=cliente.id_cliente,
        nombre='Bebidas para eventos',
        visible=True,
        activo=True,
    )
    db.session.add_all([config_gastro, categoria])
    db.session.flush()

    tienda = TiendaConfig(
        id_cliente=cliente.id_cliente,
        slug=slug,
        nombre_tienda='Catering Demo',
        telefono_whatsapp='595981000000',
        mensaje_whatsapp_producto='Hola, vengo de la tienda web y me interesa el producto: {producto}',
        activa=True,
    )
    producto = GastronomiaProducto(
        cliente_id=cliente.id_cliente,
        categoria_id=categoria.id_categoria,
        nombre='Combo de bebidas',
        descripcion='Bebidas para eventos.',
        precio=150000,
        imagen_url='https://cdn.example.com/combo-bebidas.jpg',
        disponible=True,
        visible=True,
        publicado_tienda=True,
        activo=True,
    )
    oculto_tienda = GastronomiaProducto(
        cliente_id=cliente.id_cliente,
        categoria_id=categoria.id_categoria,
        nombre='Menú interno',
        descripcion='No debe aparecer en tienda online.',
        precio=99000,
        disponible=True,
        visible=True,
        publicado_tienda=False,
        activo=True,
    )
    db.session.add_all([tienda, producto, oculto_tienda])
    db.session.commit()
    return tienda, producto


def _loguear_admin(client, app, cliente_id=None):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        if cliente_id is not None:
            admin.id_cliente = cliente_id
            db.session.commit()
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def _whatsapp_message(url):
    query = parse_qs(urlparse(url).query)
    return unquote(query.get('text', [''])[0])


def test_tienda_gastronomia_adapta_cta_y_mensaje_de_presupuesto():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        config_response = client.get(f'/api/tienda/{slug}/config')
        assert config_response.status_code == 200
        config_data = config_response.get_json()
        assert config_data['es_gastronomia'] is True
        assert config_data['texto_cta_catalogo'] == 'Pedir presupuesto'
        assert config_data['texto_cta_producto'] == 'Solicitar presupuesto'

        bootstrap_response = client.get(f'/api/tienda/{slug}/bootstrap')
        assert bootstrap_response.status_code == 200
        bootstrap = bootstrap_response.get_json()
        assert bootstrap['categorias'][0]['nombre'] == 'Bebidas para eventos'
        catalog_product = bootstrap['catalogo']['productos'][0]
        assert bootstrap['catalogo']['total'] == 1
        assert catalog_product['tipo_catalogo'] == 'gastronomia'
        assert catalog_product['nombre'] == 'Combo de bebidas'
        assert catalog_product['precio'] == 150000
        assert catalog_product['imagenes'][0]['url'] == 'https://cdn.example.com/combo-bebidas.jpg'

        producto_response = client.get(f'/api/tienda/{slug}/producto/{producto_id}')
        assert producto_response.status_code == 200
        producto_data = producto_response.get_json()
        assert producto_data['descripcion'] == 'Bebidas para eventos.'
        mensaje = _whatsapp_message(producto_data['whatsapp_link'])
        assert 'solicitar un presupuesto para gastronomia' in mensaje
        assert 'Combo de bebidas' in mensaje
        assert 'Cantidad requerida:' in mensaje
        assert 'Bebidas, adicionales o servicio de atencion:' in mensaje
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_tienda_gastronomia_expone_promociones_activas_como_ofertas():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-ofertas-test')
        promocion = TiendaPromocion(
            id_cliente=tienda.id_cliente,
            nombre='Promo bebidas',
            tipo='porcentaje',
            valor=10,
            fecha_inicio=datetime.utcnow() - timedelta(hours=1),
            fecha_fin=datetime.utcnow() + timedelta(hours=1),
            activa=True,
        )
        db.session.add(promocion)
        db.session.flush()
        db.session.add(TiendaPromocionGastronomiaProducto(
            id_promocion=promocion.id_promocion,
            id_producto=producto.id_producto,
        ))
        oculto_tienda = GastronomiaProducto.query.filter_by(
            cliente_id=tienda.id_cliente,
            publicado_tienda=False,
        ).one()
        db.session.add(TiendaPromocionGastronomiaProducto(
            id_promocion=promocion.id_promocion,
            id_producto=oculto_tienda.id_producto,
        ))
        categoria_inventario = Categoria(nombre='Inventario ajeno al menu', activo=True)
        db.session.add(categoria_inventario)
        db.session.flush()
        producto_inventario = Producto(
            id_cliente=tienda.id_cliente,
            id_categoria=categoria_inventario.id_categoria,
            codigo='INV-AJENO-MENU',
            nombre='Producto de inventario ajeno al menu',
            precio_compra=50000,
            precio_venta=100000,
            stock_actual=5,
            stock_minimo=0,
            activo=True,
            publicado_tienda=True,
        )
        promocion_inventario = TiendaPromocion(
            id_cliente=tienda.id_cliente,
            nombre='Promo inventario ajena al menu',
            tipo='porcentaje',
            valor=10,
            fecha_inicio=datetime.utcnow() - timedelta(hours=1),
            fecha_fin=datetime.utcnow() + timedelta(hours=1),
            activa=True,
        )
        db.session.add_all([producto_inventario, promocion_inventario])
        db.session.flush()
        db.session.add(TiendaPromocionProducto(
            id_promocion=promocion_inventario.id_promocion,
            id_producto=producto_inventario.id_producto,
        ))
        db.session.add(TiendaPromocionProducto(
            id_promocion=promocion.id_promocion,
            id_producto=producto_inventario.id_producto,
        ))
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        response = client.get(f'/api/tienda/{slug}/productos')
        assert response.status_code == 200
        ofertas = response.get_json()['ofertas']
        assert [oferta['nombre'] for oferta in ofertas] == ['Combo de bebidas']
        assert ofertas[0]['precio'] == 135000
        assert ofertas[0]['precio_anterior'] == 150000
        assert ofertas[0]['promocion_activa']['etiqueta'] == '-10%'
        promociones_response = client.get(f'/api/tienda/{slug}/promociones')
        assert promociones_response.status_code == 200
        promociones = promociones_response.get_json()
        assert [item['nombre'] for item in promociones] == ['Promo bebidas']
        assert promociones[0]['productos'] == [{
            'id': producto_id,
            'nombre': 'Combo de bebidas',
            'tipo_catalogo': 'gastronomia',
        }]
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_tienda_gastronomia_expone_modificadores_con_foto_y_precio():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-extras-test')
        grupo = GastronomiaGrupoOpciones(
            cliente_id=tienda.id_cliente,
            producto_id=producto.id_producto,
            nombre='Extras',
            tipo='extra',
            max_selecciones=3,
            visible=True,
            activo=True,
        )
        db.session.add(grupo)
        db.session.flush()
        db.session.add(GastronomiaOpcionProducto(
            cliente_id=tienda.id_cliente,
            grupo_id=grupo.id_grupo,
            nombre='Carne extra',
            precio_delta=8000,
            imagen_url='/static/tienda_uploads/gastronomia/menu/carne-extra.webp',
            disponible=True,
            visible=True,
            activo=True,
        ))
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        response = client.get(f'/api/tienda/{slug}/producto/{producto_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['grupos_opciones'][0]['nombre'] == 'Extras'
        opcion = data['grupos_opciones'][0]['opciones'][0]
        assert opcion['nombre'] == 'Carne extra'
        assert opcion['precio_delta'] == 8000
        assert opcion['imagen_url'].endswith('carne-extra.webp')
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_tienda_gastronomia_hereda_imagenes_de_menu_para_modificadores_sin_foto():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-extras-fallback-test')
        db.session.add_all([
            GastronomiaProducto(
                cliente_id=tienda.id_cliente,
                categoria_id=producto.categoria_id,
                nombre='Lechuga repollada',
                descripcion='Ingrediente base con foto propia.',
                precio=4000,
                imagen_url='https://cdn.example.com/lechuga-repollada.webp',
                disponible=True,
                visible=True,
                publicado_tienda=True,
                activo=True,
            ),
            GastronomiaProducto(
                cliente_id=tienda.id_cliente,
                categoria_id=producto.categoria_id,
                nombre='Medallon carne',
                descripcion='Extra del menu con foto propia.',
                precio=10000,
                imagen_url='https://cdn.example.com/medallon-carne.webp',
                disponible=True,
                visible=True,
                publicado_tienda=True,
                activo=True,
            ),
        ])
        db.session.flush()
        grupo_removibles = GastronomiaGrupoOpciones(
            cliente_id=tienda.id_cliente,
            producto_id=producto.id_producto,
            nombre='Ingredientes removibles',
            tipo='ingrediente_removible',
            max_selecciones=4,
            visible=True,
            activo=True,
        )
        grupo_adicionales = GastronomiaGrupoOpciones(
            cliente_id=tienda.id_cliente,
            producto_id=producto.id_producto,
            nombre='Adicionales',
            tipo='extra',
            max_selecciones=3,
            visible=True,
            activo=True,
        )
        db.session.add_all([grupo_removibles, grupo_adicionales])
        db.session.flush()
        db.session.add_all([
            GastronomiaOpcionProducto(
                cliente_id=tienda.id_cliente,
                grupo_id=grupo_removibles.id_grupo,
                nombre='Lechuga repollada',
                precio_delta=0,
                imagen_url=None,
                disponible=True,
                visible=True,
                activo=True,
            ),
            GastronomiaOpcionProducto(
                cliente_id=tienda.id_cliente,
                grupo_id=grupo_adicionales.id_grupo,
                nombre='Medallon carne extra',
                precio_delta=10000,
                imagen_url=None,
                disponible=True,
                visible=True,
                activo=True,
            ),
        ])
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        response = client.get(f'/api/tienda/{slug}/producto/{producto_id}')
        assert response.status_code == 200
        data = response.get_json()
        grupo_removibles = next(grupo for grupo in data['grupos_opciones'] if grupo['tipo'] == 'ingrediente_removible')
        grupo_adicionales = next(grupo for grupo in data['grupos_opciones'] if grupo['nombre'] == 'Adicionales')
        assert grupo_removibles['opciones'][0]['imagen_url'] == 'https://cdn.example.com/lechuga-repollada.webp'
        assert grupo_adicionales['opciones'][0]['imagen_url'] == 'https://cdn.example.com/medallon-carne.webp'
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_panel_tienda_gastronomia_muestra_menu_y_permite_guardar_config():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-admin-test')
        cliente_id = tienda.id_cliente
        config_id = tienda.id_config

    _loguear_admin(client, app, cliente_id=cliente_id)

    try:
        response = client.get('/tienda-admin')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'Menú Gastronomía' in html
        assert 'Cargar menÃº' in html
        assert 'Combo de bebidas' in html
        assert '/tienda/gastro-admin-test' in html

        save_response = client.post('/api/tienda/admin/config', json={
            'id_config': config_id,
            'slug_actual': 'gastro-admin-test',
            'slug': 'gastro-admin-test',
            'nombre_tienda': 'Gastro Admin Test',
            'telefono_whatsapp': '595981000000',
        })
        assert save_response.status_code == 200
        assert save_response.get_json()['ok'] is True
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_panel_tienda_gastronomia_rechaza_extension_no_permitida_en_portada():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, _producto = _crear_tienda_gastronomia(slug='gastro-portada-extension-test')
        cliente_id = tienda.id_cliente
        config_id = tienda.id_config
        slug = tienda.slug

    _loguear_admin(client, app, cliente_id=cliente_id)

    try:
        response = client.post('/api/tienda/admin/config', data={
            'id_config': str(config_id),
            'slug_actual': slug,
            'slug': slug,
            'nombre_tienda': 'Gastro Admin Test',
            'telefono_whatsapp': '595981000000',
            'imagen_portada_file': (io.BytesIO(b'contenido-no-valido'), 'portada.heic'),
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'extension_portada_no_permitida'
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_tienda_gastronomia_usa_cliente_del_menu_si_config_quedo_desfasada():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        cliente_tienda = Cliente(nombre='Cliente tienda desfasada', tipo='minorista', activo=True)
        cliente_menu = Cliente(nombre='Cliente menu gastronomico', tipo='minorista', activo=True)
        db.session.add_all([cliente_tienda, cliente_menu])
        db.session.flush()

        config_gastro = GastronomiaClienteConfig(
            cliente_id=cliente_menu.id_cliente,
            modo_operacion=MODO_GASTRONOMIA,
            gastronomia_activo=True,
        )
        categoria = GastronomiaCategoria(
            cliente_id=cliente_menu.id_cliente,
            nombre='Hamburguesas',
            visible=True,
            activo=True,
        )
        tienda = TiendaConfig(
            id_cliente=cliente_tienda.id_cliente,
            slug='gastro-config-desfasada',
            nombre_tienda='Gastro Config Desfasada',
            telefono_whatsapp='595981000000',
            activa=True,
        )
        db.session.add_all([config_gastro, categoria, tienda])
        db.session.flush()

        producto = GastronomiaProducto(
            cliente_id=cliente_menu.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Big Cheese',
            precio=35000,
            disponible=True,
            visible=True,
            publicado_tienda=True,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        tienda_id = tienda.id_config
        tienda_cliente_id = cliente_tienda.id_cliente
        menu_cliente_id = cliente_menu.id_cliente
        slug = tienda.slug

    _loguear_admin(client, app, cliente_id=tienda_cliente_id)

    try:
        bootstrap_response = client.get(f'/api/tienda/{slug}/bootstrap')
        assert bootstrap_response.status_code == 200
        bootstrap = bootstrap_response.get_json()
        assert bootstrap['catalogo']['total'] == 1
        assert bootstrap['catalogo']['productos'][0]['nombre'] == 'Big Cheese'
        assert bootstrap['categorias'][0]['nombre'] == 'Hamburguesas'

        panel_response = client.get('/tienda-admin')
        assert panel_response.status_code == 200
        html = panel_response.get_data(as_text=True)
        assert 'Big Cheese' in html
        assert '/tienda/gastro-config-desfasada' in html

        save_response = client.post('/api/tienda/admin/config', json={
            'id_config': tienda_id,
            'slug_actual': slug,
            'slug': slug,
            'nombre_tienda': 'Gastro Config Reparada',
            'telefono_whatsapp': '595981000000',
        })
        assert save_response.status_code == 200
        assert save_response.get_json()['ok'] is True

        with app.app_context():
            tienda_actualizada = db.session.get(TiendaConfig, tienda_id)
            assert tienda_actualizada.id_cliente == menu_cliente_id
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)
