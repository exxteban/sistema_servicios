import re
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from app import create_app, db
from app.models import Categoria, Cliente, Producto, Usuario
from gastronomia.models import (
    GastronomiaClienteConfig,
    GastronomiaCategoria,
    GastronomiaGrupoOpciones,
    GastronomiaOpcionProducto,
    GastronomiaProducto,
)
from PIL import Image


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html: str) -> str:
    match = re.search(r'id="csrf-token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_restaurante(app, nombre: str, username: str):
    with app.app_context():
        cliente = Cliente(nombre=nombre, ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {nombre}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.add(GastronomiaClienteConfig(
            cliente_id=cliente.id_cliente,
            modo_operacion='gastronomia',
            gastronomia_activo=True,
        ))
        db.session.commit()
        return cliente.id_cliente


def _imagen_png(color: str = 'red') -> BytesIO:
    stream = BytesIO()
    Image.new('RGB', (24, 24), color=color).save(stream, format='PNG')
    stream.seek(0)
    return stream


def test_api_menu_crea_categoria_y_producto_con_cliente_de_sesion():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Uno', 'resto_uno')
    _loguear(client, app, 'resto_uno')

    page = client.get('/gastronomia/menu')
    assert page.status_code == 200
    csrf = _csrf(page.get_data(as_text=True))

    categoria_resp = client.post(
        '/api/gastronomia/categorias',
        json={'nombre': 'Hamburguesas', 'descripcion': 'Linea principal', 'orden': 1},
        headers={'X-CSRFToken': csrf},
    )
    assert categoria_resp.status_code == 201
    categoria_id = categoria_resp.get_json()['categoria']['id_categoria']

    categoria_update_resp = client.put(
        f'/api/gastronomia/categorias/{categoria_id}',
        json={'nombre': 'Hamburguesas premium', 'descripcion': 'Linea principal editada', 'orden': 2, 'visible': True},
        headers={'X-CSRFToken': csrf},
    )
    assert categoria_update_resp.status_code == 200
    categoria_editada = categoria_update_resp.get_json()['categoria']
    assert categoria_editada['nombre'] == 'Hamburguesas premium'
    assert categoria_editada['descripcion'] == 'Linea principal editada'
    assert categoria_editada['orden'] == 2
    assert categoria_editada['visible'] is True

    producto_resp = client.post(
        '/api/gastronomia/productos',
        json={
            'categoria_id': categoria_id,
            'nombre': 'Clasica',
            'descripcion': 'Pan, carne y queso',
            'precio': '12500.50',
            'imagen_url': 'https://cdn.example.com/clasica.jpg',
            'disponible': True,
            'visible': True,
            'visible_en_tv': False,
            'control_stock_venta': True,
            'stock_disponible': 5,
            'ingredientes_removibles': 'Lechuga\nTomate\nCebolla',
            'adicionales_precio': 'Carne extra | 8000\nTomate extra | 2000',
        },
        headers={'X-CSRFToken': csrf},
    )

    assert producto_resp.status_code == 201
    producto = producto_resp.get_json()['producto']
    assert producto['precio'] == 12500.5
    assert producto['imagen_url'] == 'https://cdn.example.com/clasica.jpg'
    assert producto['visible_en_tv'] is False
    assert producto['publicado_tienda'] is True
    assert producto['control_stock_venta'] is True
    assert producto['stock_disponible'] == 5
    producto_publico = client.get(
        '/api/gastronomia/productos',
        query_string={'publico': '1', 'modificadores': '1'},
    )
    assert producto_publico.status_code == 200
    producto_pos = producto_publico.get_json()['productos'][0]
    assert producto_pos['imagen_url'] == 'https://cdn.example.com/clasica.jpg'
    grupos = producto_pos['grupos_opciones']
    assert grupos[0]['tipo'] == 'ingrediente_removible'
    assert [opcion['nombre'] for opcion in grupos[0]['opciones']] == ['Lechuga', 'Tomate', 'Cebolla']
    grupo_adicionales = next(grupo for grupo in grupos if grupo['nombre'] == 'Adicionales')
    assert [opcion['nombre'] for opcion in grupo_adicionales['opciones']] == ['Carne extra', 'Tomate extra']
    assert [opcion['precio_delta'] for opcion in grupo_adicionales['opciones']] == [8000, 2000]
    with app.app_context():
        assert GastronomiaCategoria.query.filter_by(cliente_id=cliente_id).count() == 1
        assert GastronomiaProducto.query.filter_by(cliente_id=cliente_id).count() == 1
        grupo = GastronomiaGrupoOpciones.query.filter_by(
            cliente_id=cliente_id,
            producto_id=producto['id_producto'],
            tipo='ingrediente_removible',
            activo=True,
        ).one()
        opciones = GastronomiaOpcionProducto.query.filter_by(grupo_id=grupo.id_grupo, activo=True).order_by(
            GastronomiaOpcionProducto.orden.asc(),
        ).all()
        assert [opcion.nombre for opcion in opciones] == ['Lechuga', 'Tomate', 'Cebolla']

    editar_resp = client.put(
        f'/api/gastronomia/productos/{producto["id_producto"]}',
        json={
            'categoria_id': categoria_id,
            'nombre': 'Clasica editada',
            'descripcion': 'Pan, carne y queso cheddar',
            'precio': '14000',
            'disponible': True,
            'visible': True,
            'visible_en_tv': True,
            'control_stock_venta': False,
            'ingredientes_removibles': 'Lechuga\nCebolla morada',
            'adicionales_precio': 'Carne extra | 9000',
        },
        headers={'X-CSRFToken': csrf},
    )

    assert editar_resp.status_code == 200
    producto_editado = client.get(
        f'/api/gastronomia/productos/{producto["id_producto"]}',
        query_string={'modificadores': '1'},
    ).get_json()['producto']
    assert producto_editado['nombre'] == 'Clasica editada'
    assert producto_editado['precio'] == 14000
    assert producto_editado['adicionales_precio'] == 'Carne extra | 9000'
    assert producto_editado['visible_en_tv'] is True
    assert producto_editado['control_stock_venta'] is False
    assert producto_editado['stock_disponible'] is None
    grupo_removible = next(
        grupo for grupo in producto_editado['grupos_opciones'] if grupo['tipo'] == 'ingrediente_removible'
    )
    assert [opcion['nombre'] for opcion in grupo_removible['opciones']] == ['Lechuga', 'Cebolla morada']
    grupo_adicionales_editado = next(grupo for grupo in producto_editado['grupos_opciones'] if grupo['nombre'] == 'Adicionales')
    assert [opcion['precio_delta'] for opcion in grupo_adicionales_editado['opciones']] == [9000]

    toggle_resp = client.put(
        f'/api/gastronomia/productos/{producto["id_producto"]}/estado',
        json={'visible': False, 'visible_en_tv': False, 'publicado_tienda': False},
        headers={'X-CSRFToken': csrf},
    )
    assert toggle_resp.status_code == 200
    producto_toggle = toggle_resp.get_json()['producto']
    assert producto_toggle['visible'] is False
    assert producto_toggle['visible_en_tv'] is False
    assert producto_toggle['publicado_tienda'] is False

    borrar_categoria_resp = client.delete(
        f'/api/gastronomia/categorias/{categoria_id}',
        headers={'X-CSRFToken': csrf},
    )
    assert borrar_categoria_resp.status_code == 200
    with app.app_context():
        categoria_db = db.session.get(GastronomiaCategoria, categoria_id)
        producto_db = db.session.get(GastronomiaProducto, producto['id_producto'])
        assert categoria_db is not None
        assert producto_db is not None
        assert categoria_db.activo is False
        assert producto_db.activo is False


def test_menu_promociones_filtra_catalogo_gastronomico_y_respeta_cliente():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Promos', 'resto_promos')
    otro_cliente_id = _crear_restaurante(app, 'Resto Ajeno', 'resto_ajeno')

    with app.app_context():
        categoria_menu = GastronomiaCategoria(cliente_id=cliente_id, nombre='Combos')
        categoria_inventario = Categoria(nombre='Inventario promociones', activo=True)
        db.session.add_all([categoria_menu, categoria_inventario])
        db.session.flush()
        producto_gastronomico = GastronomiaProducto(
                cliente_id=cliente_id,
                categoria_id=categoria_menu.id_categoria,
                nombre='Combo gastronomico',
                precio=45000,
                activo=True,
            )
        db.session.add_all([
            producto_gastronomico,
            Producto(
                id_cliente=cliente_id,
                id_categoria=categoria_inventario.id_categoria,
                codigo='INV-PROMO-001',
                nombre='Producto de inventario',
                precio_compra=10000,
                precio_venta=20000,
                stock_actual=5,
                stock_minimo=0,
                activo=True,
            ),
        ])
        db.session.commit()
        producto_gastronomico_id = producto_gastronomico.id_producto

    _loguear(client, app, 'resto_promos')

    page = client.get('/gastronomia/menu')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    csrf = _csrf(html)
    assert 'data-menu-tab="promociones"' in html
    assert f'name="cliente_id_gastronomia" value="{cliente_id}"' in html
    assert 'name="catalogo_promocion" value="gastronomia"' in html

    response = client.get('/api/tienda/admin/promociones/productos', query_string={
        'cliente_id_gastronomia': cliente_id,
        'tipo_catalogo': 'gastronomia',
    })
    assert response.status_code == 200
    productos = response.get_json()['productos']
    assert [producto['nombre'] for producto in productos] == ['Combo gastronomico']
    assert productos[0]['tipo_catalogo'] == 'gastronomia'

    create_promotion = client.post(
        '/api/tienda/admin/promociones',
        json={
            'cliente_id_gastronomia': cliente_id,
            'nombre': 'Promo combo',
            'tipo': 'porcentaje',
            'valor': 15,
            'fecha_inicio': (datetime.now() - timedelta(hours=1)).isoformat(timespec='minutes'),
            'fecha_fin': (datetime.now() + timedelta(hours=1)).isoformat(timespec='minutes'),
            'productos_gastronomia': [producto_gastronomico_id],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert create_promotion.status_code == 201, create_promotion.get_json()
    promo_data = create_promotion.get_json()['promocion']
    assert promo_data['productos'][0]['nombre'] == 'Combo gastronomico'
    assert promo_data['productos'][0]['tipo_catalogo'] == 'gastronomia'

    update_promotion = client.put(
        f"/api/tienda/admin/promociones/{promo_data['id_promocion']}",
        json={
            'cliente_id_gastronomia': cliente_id,
            'nombre': 'Promo combo editada',
            'tipo': 'porcentaje',
            'valor': 20,
            'fecha_inicio': (datetime.now() - timedelta(hours=1)).isoformat(timespec='minutes'),
            'fecha_fin': (datetime.now() + timedelta(hours=1)).isoformat(timespec='minutes'),
            'productos_gastronomia': [producto_gastronomico_id],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert update_promotion.status_code == 200, update_promotion.get_data(as_text=True)
    assert update_promotion.get_json()['promocion']['nombre'] == 'Promo combo editada'

    cross_tenant = client.get('/api/tienda/admin/promociones/productos', query_string={
        'cliente_id_gastronomia': otro_cliente_id,
        'tipo_catalogo': 'gastronomia',
    })
    assert cross_tenant.status_code == 404


def test_parsea_precio_con_punto_de_miles_en_menu():
    app = create_app('testing')
    client = app.test_client()
    _crear_restaurante(app, 'Resto Miles', 'resto_miles')
    _loguear(client, app, 'resto_miles')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    categoria = client.post(
        '/api/gastronomia/categorias',
        json={'nombre': 'Hamburguesas'},
        headers={'X-CSRFToken': csrf},
    ).get_json()['categoria']

    response = client.post(
        '/api/gastronomia/productos',
        json={
            'categoria_id': categoria['id_categoria'],
            'nombre': 'Big Cheese',
            'precio': '35.000',
            'disponible': True,
            'visible': True,
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 201
    assert response.get_json()['producto']['precio'] == 35000


def test_api_menu_no_filtra_datos_entre_clientes():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    cliente_uno_id = _crear_restaurante(app, 'Resto Uno', 'resto_uno')
    cliente_dos_id = _crear_restaurante(app, 'Resto Dos', 'resto_dos')

    with app.app_context():
        categoria_uno = GastronomiaCategoria(cliente_id=cliente_uno_id, nombre='Pizzas')
        categoria_dos = GastronomiaCategoria(cliente_id=cliente_dos_id, nombre='Pastas')
        db.session.add_all([categoria_uno, categoria_dos])
        db.session.commit()
        categoria_uno_id = categoria_uno.id_categoria

    _loguear(client_dos, app, 'resto_dos')
    page_dos = client_dos.get('/gastronomia/menu')
    csrf_dos = _csrf(page_dos.get_data(as_text=True))

    listado = client_dos.get('/api/gastronomia/categorias')
    assert listado.status_code == 200
    nombres = [item['nombre'] for item in listado.get_json()['categorias']]
    assert nombres == ['Pastas']

    update_resp = client_dos.put(
        f'/api/gastronomia/categorias/{categoria_uno_id}',
        json={'nombre': 'Pizzas editadas'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert update_resp.status_code == 404

    _loguear(client_uno, app, 'resto_uno')
    listado_uno = client_uno.get('/api/gastronomia/categorias')
    assert [item['nombre'] for item in listado_uno.get_json()['categorias']] == ['Pizzas']


def test_api_menu_reordena_categorias_y_prioriza_comidas_por_defecto():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Orden', 'resto_orden')

    with app.app_context():
        categorias = [
            GastronomiaCategoria(cliente_id=cliente_id, nombre='Bebidas con gas'),
            GastronomiaCategoria(cliente_id=cliente_id, nombre='Hamburguesas'),
            GastronomiaCategoria(cliente_id=cliente_id, nombre='Cervezas'),
            GastronomiaCategoria(cliente_id=cliente_id, nombre='Sandwiches'),
        ]
        db.session.add_all(categorias)
        db.session.commit()
        ids_por_nombre = {categoria.nombre: categoria.id_categoria for categoria in categorias}

    _loguear(client, app, 'resto_orden')
    listado = client.get('/api/gastronomia/categorias')
    assert listado.status_code == 200
    assert [item['nombre'] for item in listado.get_json()['categorias']] == [
        'Hamburguesas',
        'Sandwiches',
        'Bebidas con gas',
        'Cervezas',
    ]

    page = client.get('/gastronomia/menu')
    csrf = _csrf(page.get_data(as_text=True))
    nuevo_orden = [
        ids_por_nombre['Cervezas'],
        ids_por_nombre['Bebidas con gas'],
        ids_por_nombre['Hamburguesas'],
        ids_por_nombre['Sandwiches'],
    ]
    reordenar_resp = client.put(
        '/api/gastronomia/categorias/orden',
        json={'categorias': nuevo_orden},
        headers={'X-CSRFToken': csrf},
    )

    assert reordenar_resp.status_code == 200
    categorias_reordenadas = reordenar_resp.get_json()['categorias']
    assert [item['id_categoria'] for item in categorias_reordenadas] == nuevo_orden
    assert [item['orden'] for item in categorias_reordenadas] == [10, 20, 30, 40]

    listado_actualizado = client.get('/api/gastronomia/categorias')
    assert [item['id_categoria'] for item in listado_actualizado.get_json()['categorias']] == nuevo_orden


def test_api_menu_guarda_imagen_subida_y_reemplaza_archivo_anterior():
    app = create_app('testing')
    client = app.test_client()
    _crear_restaurante(app, 'Resto Imagen', 'resto_imagen')
    _loguear(client, app, 'resto_imagen')

    page = client.get('/gastronomia/menu')
    csrf = _csrf(page.get_data(as_text=True))

    categoria_resp = client.post(
        '/api/gastronomia/categorias',
        json={'nombre': 'Sandwiches', 'descripcion': 'Linea fria', 'orden': 1},
        headers={'X-CSRFToken': csrf},
    )
    categoria_id = categoria_resp.get_json()['categoria']['id_categoria']

    with TemporaryDirectory() as static_dir:
        app.static_folder = static_dir

        crear_resp = client.post(
            '/api/gastronomia/productos',
            data={
                'categoria_id': str(categoria_id),
                'nombre': 'Mbeju burger',
                'descripcion': 'Con queso',
                'precio': '18000',
                'disponible': '1',
                'visible': '1',
                'visible_en_tv': '1',
                'publicado_tienda': '1',
                'imagen_archivo': (_imagen_png('red'), 'burger.png'),
            },
            headers={'X-CSRFToken': csrf},
        )

        assert crear_resp.status_code == 201
        producto = crear_resp.get_json()['producto']
        ruta_uno = Path(static_dir, *producto['imagen_url'].replace('/static/', '').split('/'))
        assert producto['imagen_url'].startswith('/static/tienda_uploads/gastronomia/menu/')
        assert ruta_uno.is_file()

        actualizar_resp = client.put(
            f"/api/gastronomia/productos/{producto['id_producto']}",
            data={
                'categoria_id': str(categoria_id),
                'nombre': 'Mbeju burger',
                'descripcion': 'Con queso y huevo',
                'precio': '19000',
                'disponible': '1',
                'visible': '1',
                'visible_en_tv': '0',
                'publicado_tienda': '0',
                'imagen_archivo': (_imagen_png('blue'), 'burger-2.png'),
            },
            headers={'X-CSRFToken': csrf},
        )

        assert actualizar_resp.status_code == 200
        producto_actualizado = actualizar_resp.get_json()['producto']
        ruta_dos = Path(static_dir, *producto_actualizado['imagen_url'].replace('/static/', '').split('/'))
        assert ruta_dos.is_file()
        assert producto_actualizado['imagen_url'] != producto['imagen_url']
        assert producto_actualizado['visible_en_tv'] is False
        assert producto_actualizado['publicado_tienda'] is False
        assert not ruta_uno.exists()
