from app import create_app, db
from app.models import Categoria, Producto, ProductoPrecioOpcion, Servicio, Usuario


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def test_pos_catalogo_bootstrap_expone_productos_servicios_y_opciones():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        categoria = Categoria(nombre='POS Offline', activo=True)
        db.session.add(categoria)
        db.session.flush()

        producto = Producto(
            codigo='OFF-001',
            nombre='Producto Offline',
            id_categoria=categoria.id_categoria,
            precio_compra=1000,
            precio_venta=2500,
            porcentaje_iva=10,
            stock_actual=7,
            stock_minimo=2,
            activo=True,
        )
        db.session.add(producto)
        db.session.flush()
        db.session.add(ProductoPrecioOpcion(
            id_producto=producto.id_producto,
            etiqueta='Promo',
            precio=2200,
            orden=1,
            activo=True,
        ))

        servicio = Servicio(
            codigo='SRV-OFF',
            nombre='Servicio Offline',
            categoria='POS Offline',
            precio=5000,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.commit()

    response = client.get('/ventas/catalogo/bootstrap')

    assert response.status_code == 200
    data = response.get_json() or {}
    assert data.get('success') is True
    items = data.get('items') or []
    producto_item = next(item for item in items if item.get('codigo') == 'OFF-001')
    servicio_item = next(item for item in items if item.get('codigo') == 'SRV-OFF')

    assert producto_item['tipo'] == 'producto'
    assert producto_item['precio'] == 2500.0
    assert producto_item['stock'] == 7
    assert producto_item['precios_opciones'][0]['etiqueta'] == 'Promo'
    assert servicio_item['tipo'] == 'servicio'
    assert servicio_item['es_servicio'] is True
