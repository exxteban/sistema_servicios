from urllib.parse import parse_qs, unquote, urlparse

from app import create_app, db
from app.models import Cliente, Configuracion, TiendaConfig
from gastronomia.models import GastronomiaCategoria, GastronomiaClienteConfig, GastronomiaProducto
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
        activo=True,
    )
    db.session.add_all([tienda, producto])
    db.session.commit()
    return tienda, producto


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
