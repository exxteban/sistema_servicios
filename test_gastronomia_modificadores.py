import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaGrupoOpciones,
    GastronomiaProducto,
)


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
