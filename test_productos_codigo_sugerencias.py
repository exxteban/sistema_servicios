from app import create_app, db
from app.models import Categoria, Producto, Usuario
from app.utils.productos_errors import mensaje_codigo_duplicado


def _crear_app_con_admin():
    app = create_app('testing')
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
    return app


def test_sugerencias_codigos_incluye_productos_inactivos():
    app = _crear_app_con_admin()
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        categoria = Categoria.query.first()
        producto = Producto(
            codigo='COD-INACTIVO-TEST',
            nombre='Producto archivado',
            id_categoria=categoria.id_categoria,
            precio_compra=0,
            precio_venta=100,
            stock_actual=0,
            stock_minimo=0,
            activo=False,
        )
        db.session.add(producto)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(admin.id_usuario)
            session['_fresh'] = True

        response = client.get('/productos/codigos/sugerencias?q=COD-INACTIVO-TEST')
        data = response.get_json()

    assert response.status_code == 200
    assert data['exacto']['codigo'] == 'COD-INACTIVO-TEST'
    assert data['exacto']['activo'] is False
    assert data['sugerencia'] == 'COD-INACTIVO-TEST-02'


def test_mensaje_codigo_duplicado_muestra_estado_del_producto():
    app = _crear_app_con_admin()
    with app.app_context():
        categoria = Categoria.query.first()
        producto = Producto(
            codigo='COD-ACTIVO-TEST',
            nombre='Producto visible',
            id_categoria=categoria.id_categoria,
            precio_compra=0,
            precio_venta=100,
            stock_actual=1,
            stock_minimo=0,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()

        mensaje = mensaje_codigo_duplicado('COD-ACTIVO-TEST')

    assert 'Producto visible' in mensaje
    assert '(activo)' in mensaje
    assert 'COD-ACTIVO-TEST-02' in mensaje
