import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaGrupoOpciones,
    GastronomiaOpcionProducto,
    GastronomiaProducto,
)
from gastronomia.services.modificadores_service import sincronizar_ingredientes_removibles
from gastronomia.services.pedido_service import crear_pedido


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


def _crear_producto_base(app, nombre_cliente: str, username: str):
    with app.app_context():
        cliente = Cliente(nombre=nombre_cliente, ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {nombre_cliente}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Pizzas')
        db.session.add_all([
            usuario,
            categoria,
            GastronomiaClienteConfig(
                cliente_id=cliente.id_cliente,
                modo_operacion='gastronomia',
                gastronomia_activo=True,
            ),
        ])
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Pizza muzzarella',
            precio=30000,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto


def test_modificadores_crea_grupos_opciones_y_valida_total():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto_base(app, 'Resto Uno', 'resto_uno')
    _loguear(client, app, 'resto_uno')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    grupo_resp = client.post(
        f'/api/gastronomia/productos/{producto_id}/grupos-opciones',
        json={
            'nombre': 'Tamano',
            'tipo': 'variante',
            'obligatorio': True,
            'min_selecciones': 1,
            'max_selecciones': 1,
        },
        headers={'X-CSRFToken': csrf},
    )
    assert grupo_resp.status_code == 201
    grupo_id = grupo_resp.get_json()['grupo']['id_grupo']

    grande_resp = client.post(
        f'/api/gastronomia/grupos-opciones/{grupo_id}/opciones',
        json={'nombre': 'Grande', 'precio_delta': '5000'},
        headers={'X-CSRFToken': csrf},
    )
    assert grande_resp.status_code == 201
    opcion_grande_id = grande_resp.get_json()['opcion']['id_opcion']

    extra_resp = client.post(
        f'/api/gastronomia/productos/{producto_id}/grupos-opciones',
        json={'nombre': 'Extras', 'tipo': 'extra', 'max_selecciones': 2},
        headers={'X-CSRFToken': csrf},
    )
    assert extra_resp.status_code == 201
    extra_id = extra_resp.get_json()['grupo']['id_grupo']

    queso_resp = client.post(
        f'/api/gastronomia/grupos-opciones/{extra_id}/opciones',
        json={'nombre': 'Queso extra', 'precio_delta': 2000},
        headers={'X-CSRFToken': csrf},
    )
    assert queso_resp.status_code == 201
    queso_id = queso_resp.get_json()['opcion']['id_opcion']

    validar_resp = client.post(
        f'/api/gastronomia/productos/{producto_id}/validar-selecciones',
        json={'opciones': [opcion_grande_id, queso_id]},
        headers={'X-CSRFToken': csrf},
    )
    assert validar_resp.status_code == 200
    data = validar_resp.get_json()
    assert data['total_modificadores'] == 7000
    assert data['total'] == 37000

    detalle_resp = client.get(f'/api/gastronomia/productos/{producto_id}', query_string={'modificadores': '1'})
    assert detalle_resp.status_code == 200
    grupos = detalle_resp.get_json()['producto']['grupos_opciones']
    assert [grupo['nombre'] for grupo in grupos] == ['Extras', 'Tamano']
    assert any(opcion['nombre'] == 'Grande' for grupo in grupos for opcion in grupo['opciones'])


def test_modificadores_rechaza_requisitos_y_acceso_otro_cliente():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, producto_uno_id = _crear_producto_base(app, 'Resto Uno', 'resto_uno')
    _cliente_dos_id, _producto_dos_id = _crear_producto_base(app, 'Resto Dos', 'resto_dos')

    with app.app_context():
        grupo_uno = GastronomiaGrupoOpciones(
            cliente_id=_cliente_uno_id,
            producto_id=producto_uno_id,
            nombre='Tamano',
            tipo='variante',
            obligatorio=True,
            min_selecciones=1,
            max_selecciones=1,
        )
        db.session.add(grupo_uno)
        db.session.commit()
        grupo_uno_id = grupo_uno.id_grupo

    _loguear(client_uno, app, 'resto_uno')
    csrf_uno = _csrf(client_uno.get('/gastronomia/menu').get_data(as_text=True))
    validar_resp = client_uno.post(
        f'/api/gastronomia/productos/{producto_uno_id}/validar-selecciones',
        json={'opciones': []},
        headers={'X-CSRFToken': csrf_uno},
    )
    assert validar_resp.status_code == 400
    assert 'al menos 1' in validar_resp.get_json()['mensaje']

    _loguear(client_dos, app, 'resto_dos')
    csrf_dos = _csrf(client_dos.get('/gastronomia/menu').get_data(as_text=True))
    ajeno_resp = client_dos.post(
        f'/api/gastronomia/grupos-opciones/{grupo_uno_id}/opciones',
        json={'nombre': 'Intento ajeno', 'precio_delta': 1},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert ajeno_resp.status_code == 400
    assert 'no existe para este cliente' in ajeno_resp.get_json()['mensaje']


def test_ingrediente_removible_admite_descuento_configurable():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto_base(app, 'Resto Descuentos', 'resto_descuentos')

    with app.app_context():
        grupo = sincronizar_ingredientes_removibles(
            cliente_id,
            producto_id,
            'Lechuga\nCarne | 8.000',
        )
        carne = GastronomiaOpcionProducto.query.filter_by(
            grupo_id=grupo.id_grupo,
            nombre='Carne',
            activo=True,
        ).one()
        carne_id = carne.id_opcion
        assert float(carne.precio_delta) == -8000

    _loguear(client, app, 'resto_descuentos')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    validar_resp = client.post(
        f'/api/gastronomia/productos/{producto_id}/validar-selecciones',
        json={'opciones': [carne_id]},
        headers={'X-CSRFToken': csrf},
    )
    assert validar_resp.status_code == 200
    assert validar_resp.get_json()['total_modificadores'] == -8000
    assert validar_resp.get_json()['total'] == 22000

    repetida_resp = client.post(
        f'/api/gastronomia/productos/{producto_id}/validar-selecciones',
        json={'opciones': [carne_id, carne_id]},
        headers={'X-CSRFToken': csrf},
    )
    assert repetida_resp.status_code == 400
    assert 'solo se puede quitar una vez' in repetida_resp.get_json()['mensaje']

    detalle_resp = client.get(f'/api/gastronomia/productos/{producto_id}', query_string={'modificadores': '1'})
    producto = detalle_resp.get_json()['producto']
    assert producto['ingredientes_removibles'] == 'Lechuga\nCarne | 8000'

    with app.app_context():
        usuario = Usuario.query.filter_by(username='resto_descuentos').one()
        pedido = crear_pedido(cliente_id, usuario.id_usuario, {
            'tipo_pedido': 'mostrador',
            'items': [{
                'producto_id': producto_id,
                'cantidad': 1,
                'opciones': [carne_id],
            }],
        })
        assert float(pedido.total) == 22000
        assert float(pedido.items.one().precio_unitario) == 22000


def test_ingrediente_removible_repara_formato_guardado_como_nombre():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto_base(app, 'Resto Legado', 'resto_legado')

    with app.app_context():
        producto = GastronomiaProducto.query.get(producto_id)
        producto.precio = 35000
        grupo = GastronomiaGrupoOpciones(
            cliente_id=cliente_id,
            producto_id=producto_id,
            nombre='Ingredientes removibles',
            tipo='ingrediente_removible',
            max_selecciones=1,
        )
        db.session.add(grupo)
        db.session.flush()
        opcion = GastronomiaOpcionProducto(
            cliente_id=cliente_id,
            grupo_id=grupo.id_grupo,
            nombre='Carne | 8000',
            precio_delta=0,
        )
        db.session.add(opcion)
        grupo_extra = GastronomiaGrupoOpciones(
            cliente_id=cliente_id,
            producto_id=producto_id,
            nombre='Adicionales',
            tipo='extra',
            max_selecciones=1,
            orden=1,
        )
        db.session.add(grupo_extra)
        db.session.flush()
        extra = GastronomiaOpcionProducto(
            cliente_id=cliente_id,
            grupo_id=grupo_extra.id_grupo,
            nombre='Lechuga Repollada Extra',
            precio_delta=4000,
        )
        db.session.add(extra)
        db.session.commit()
        opcion_id = opcion.id_opcion
        extra_id = extra.id_opcion

    _loguear(client, app, 'resto_legado')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    detalle = client.get(f'/api/gastronomia/productos/{producto_id}', query_string={'modificadores': '1'})
    grupo_carne = next(
        grupo
        for grupo in detalle.get_json()['producto']['grupos_opciones']
        if grupo['tipo'] == 'ingrediente_removible'
    )
    carne = grupo_carne['opciones'][0]
    assert carne['nombre'] == 'Carne'
    assert carne['precio_delta'] == -8000

    validacion = client.post(
        f'/api/gastronomia/productos/{producto_id}/validar-selecciones',
        json={'opciones': [opcion_id, extra_id]},
        headers={'X-CSRFToken': csrf},
    )
    assert validacion.status_code == 200
    assert validacion.get_json()['total_modificadores'] == -4000
    assert validacion.get_json()['total'] == 31000
