"""BI-01: pedido valido, canal, identidad por telefono, semanas y lista de activacion.

Datos ficticios. Las fechas se fijan en la semana del 5/10/2026 (lunes) para no depender de la hora de ejecucion.
"""
import re
from datetime import date, timedelta

import pytest

from app import create_app, db
from app.models import Cliente, Usuario
from app.models.tienda import TiendaConfig
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.customer_models import GastronomiaClienteFinal
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaProducto,
)
from gastronomia.services.bi.activacion import lista_activacion, marcar_paso_manual
from gastronomia.services.bi.canales import indicadores_canales
from gastronomia.services.bi.crecer import resumen_crecer_seguro
from gastronomia.services.bi.identidad import cobertura_identidad
from gastronomia.services.bi.pedidos_validos import (
    GRUPO_DESCONOCIDO,
    GRUPO_PLATAFORMA,
    GRUPO_PROPIO,
    clasificar_canal,
    filas_pedidos_validos,
    grupo_canal,
)

LUNES = date(2026, 10, 5)


def _periodo(dias: int = 14) -> dict:
    return {'desde': LUNES, 'hasta': LUNES + timedelta(days=dias - 1)}


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html: str) -> str:
    match = re.search(r'id="csrf-token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_negocio(app, nombre: str, username: str):
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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='General BI')
        db.session.add_all([
            usuario,
            categoria,
            GastronomiaClienteConfig(
                cliente_id=cliente.id_cliente,
                modo_operacion='gastronomia',
                gastronomia_activo=True,
            ),
        ])
        db.session.commit()
        return cliente.id_cliente, usuario.id_usuario, categoria.id_categoria


def _crear_producto(app, cliente_id: int, categoria_id: int, nombre: str, precio=25000, imagen_url=None) -> int:
    with app.app_context():
        producto = GastronomiaProducto(
            cliente_id=cliente_id,
            categoria_id=categoria_id,
            nombre=nombre,
            precio=precio,
            imagen_url=imagen_url,
            disponible=True,
            visible=True,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto.id_producto


def _crear_tienda(app, cliente_id: int, slug: str, activa: bool = True):
    with app.app_context():
        db.session.add(TiendaConfig(id_cliente=cliente_id, slug=slug, activa=activa))
        db.session.commit()


def _crear_cliente_final(app, cliente_id: int, telefono: str) -> int:
    with app.app_context():
        cliente_final = GastronomiaClienteFinal(
            cliente_id=cliente_id,
            telefono_normalizado=telefono,
            nombre='Cliente tienda',
            celular=telefono,
            token_publico=f'token-{telefono}',
        )
        db.session.add(cliente_final)
        db.session.commit()
        return cliente_final.id_cliente_final


def _crear_pedido(
    app,
    cliente_id: int,
    usuario_id: int,
    producto_id: int,
    dia: date,
    *,
    origen: str = 'pos',
    estado: str = 'cobrado',
    celular: str | None = None,
    nombre: str = 'Cliente',
    cliente_final_id: int | None = None,
    es_encargo: bool = False,
    canales_item: tuple = (None,),
) -> int:
    inicio_utc, _ = utc_bounds_for_local_dates(dia, dia)
    with app.app_context():
        pedido = GastronomiaPedido(
            cliente_id=cliente_id,
            usuario_id=usuario_id,
            tipo_pedido='mostrador',
            origen_pedido=origen,
            estado=estado,
            nombre_cliente=nombre,
            celular_cliente=celular,
            cliente_final_id=cliente_final_id,
            es_encargo=es_encargo,
            fecha_creacion=inicio_utc + timedelta(hours=12),
            subtotal=25000,
            total=25000,
        )
        db.session.add(pedido)
        db.session.flush()
        for canal in canales_item:
            db.session.add(GastronomiaPedidoItem(
                pedido_id=pedido.id_pedido,
                cliente_id=cliente_id,
                producto_id=producto_id,
                canal_precio=canal,
                nombre_producto='Pizza BI',
                cantidad=1,
                precio_unitario=25000,
                precio_original=25000,
                subtotal=25000,
            ))
        db.session.commit()
        return pedido.id_pedido


def _paso(activacion: dict, paso_id: str) -> dict:
    return next(paso for paso in activacion['pasos'] if paso['id'] == paso_id)


def test_clasificar_canal_separa_propio_plataformas_y_desconocidos():
    assert clasificar_canal('pos') == 'pos'
    assert clasificar_canal('tienda_online') == 'tienda_online'
    assert clasificar_canal('pos', ['pedidosya']) == 'pedidosya'
    assert clasificar_canal('pos', ['monchis']) == 'monchis'
    assert clasificar_canal('importado') == 'desconocido'
    assert clasificar_canal(None) == 'desconocido'

    assert grupo_canal('pedidosya') == GRUPO_PLATAFORMA
    assert grupo_canal('monchis') == GRUPO_PLATAFORMA
    assert grupo_canal('pos') == GRUPO_PROPIO
    assert grupo_canal('tienda_online') == GRUPO_PROPIO
    assert grupo_canal('desconocido') == GRUPO_DESCONOCIDO


def test_pedidos_validos_excluyen_cancelados_importados_y_encargos():
    app = create_app('testing')
    cliente_id, usuario_id, categoria_id = _crear_negocio(app, 'BI Validos', 'bi01_validos')
    producto_id = _crear_producto(app, cliente_id, categoria_id, 'Milanesa BI')

    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES)
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, estado='cancelado')
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, origen='importado')
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, es_encargo=True)

    with app.app_context():
        filas = filas_pedidos_validos(cliente_id, _periodo())

    assert len(filas) == 1
    assert filas[0]['canal'] == 'pos'
    assert filas[0]['grupo'] == GRUPO_PROPIO


def test_pedido_con_varios_items_de_plataforma_cuenta_una_vez_con_su_canal():
    app = create_app('testing')
    cliente_id, usuario_id, categoria_id = _crear_negocio(app, 'BI Plataforma', 'bi01_plataforma')
    producto_id = _crear_producto(app, cliente_id, categoria_id, 'Hamburguesa BI')
    _crear_pedido(
        app, cliente_id, usuario_id, producto_id, LUNES,
        canales_item=('pedidosya', 'pedidosya'),
    )

    with app.app_context():
        indicadores = indicadores_canales(cliente_id, _periodo())

    assert indicadores['total_pedidos'] == 1
    assert indicadores['grupos']['plataforma']['pedidos'] == 1
    assert indicadores['grupos']['propio']['pedidos'] == 0
    assert indicadores['grupos']['propio']['participacion'] == 0


def test_identidad_usa_telefono_y_nunca_el_nombre():
    app = create_app('testing')
    cliente_id, usuario_id, categoria_id = _crear_negocio(app, 'BI Identidad', 'bi01_identidad')
    producto_id = _crear_producto(app, cliente_id, categoria_id, 'Empanada BI')
    cliente_final_id = _crear_cliente_final(app, cliente_id, '+595981123456')

    # Dos personas con el mismo nombre: no se mezclan ni se atribuyen entre si.
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, nombre='Ana', celular='0981 123 456')
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, nombre='Ana', celular='0971 555 000')
    # Sin telefono ni cliente final: desconocido.
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, nombre='Sin dato')
    # Telefono invalido: no crea identidad.
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, celular='12')
    # Pedido de tienda con cliente final: identificado.
    _crear_pedido(
        app, cliente_id, usuario_id, producto_id, LUNES,
        origen='tienda_online', celular='0981 123 456', cliente_final_id=cliente_final_id,
    )

    with app.app_context():
        filas = filas_pedidos_validos(cliente_id, _periodo())
        cobertura = cobertura_identidad(filas)

    assert len(filas) == 5
    assert cobertura['total'] == 5
    assert cobertura['identificados'] == 3
    assert cobertura['telefonos_invalidos'] == 1
    assert cobertura['porcentaje'] == 60.0


def test_cobertura_sin_pedidos_es_desconocida_y_no_cero():
    assert cobertura_identidad([])['porcentaje'] is None


def test_indicadores_por_semana_separan_propio_y_plataforma():
    app = create_app('testing')
    cliente_id, usuario_id, categoria_id = _crear_negocio(app, 'BI Semanas', 'bi01_semanas')
    producto_id = _crear_producto(app, cliente_id, categoria_id, 'Pasta BI')
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES)
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES + timedelta(days=2), canales_item=('pedidosya',))
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES + timedelta(days=7), origen='tienda_online')

    with app.app_context():
        indicadores = indicadores_canales(cliente_id, _periodo())

    semanas = indicadores['semanas']
    assert [semana['inicio'] for semana in semanas] == [LUNES, LUNES + timedelta(days=7)]
    assert semanas[0][GRUPO_PROPIO] == 1
    assert semanas[0][GRUPO_PLATAFORMA] == 1
    assert semanas[1][GRUPO_PROPIO] == 1
    assert semanas[1][GRUPO_PLATAFORMA] == 0
    assert indicadores['grupos'][GRUPO_PROPIO]['participacion'] == 66.7


def test_activacion_negocio_nuevo_muestra_siguiente_paso():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI Nuevo', 'bi01_nuevo')

    with app.app_context():
        activacion = lista_activacion(cliente_id)

    assert _paso(activacion, 'platos')['hecho'] is False
    assert _paso(activacion, 'tienda')['hecho'] is False
    assert activacion['completados'] == 0
    assert activacion['completa'] is False
    assert activacion['siguiente']['id'] == 'platos'


def test_activacion_detecta_fotos_precios_y_tienda_publicada():
    app = create_app('testing')
    cliente_id, _, categoria_id = _crear_negocio(app, 'BI Fotos', 'bi01_fotos')
    _crear_producto(app, cliente_id, categoria_id, 'Con foto', precio=30000, imagen_url='/img/a.jpg')
    _crear_producto(app, cliente_id, categoria_id, 'Sin foto', precio=20000)
    _crear_producto(app, cliente_id, categoria_id, 'Gratis', precio=0, imagen_url='/img/b.jpg')
    _crear_tienda(app, cliente_id, 'bi01-fotos', activa=True)

    with app.app_context():
        activacion = lista_activacion(cliente_id)

    assert _paso(activacion, 'platos')['hecho'] is True
    assert _paso(activacion, 'tienda')['hecho'] is True
    assert _paso(activacion, 'fotos')['hecho'] is False
    assert _paso(activacion, 'fotos')['detalle'] == '1 sin foto'
    assert _paso(activacion, 'precios')['detalle'] == '1 sin precio'
    assert _paso(activacion, 'horario')['hecho'] is False


def test_pasos_manuales_se_guardan_por_cliente_y_validan_el_paso():
    app = create_app('testing')
    cliente_a, _, _ = _crear_negocio(app, 'BI Manual A', 'bi01_manual_a')
    cliente_b, _, _ = _crear_negocio(app, 'BI Manual B', 'bi01_manual_b')

    with app.app_context():
        marcar_paso_manual(cliente_a, 'qr_impreso', True)
        assert _paso(lista_activacion(cliente_a), 'qr_impreso')['hecho'] is True
        assert _paso(lista_activacion(cliente_b), 'qr_impreso')['hecho'] is False

        marcar_paso_manual(cliente_a, 'qr_impreso', False)
        assert _paso(lista_activacion(cliente_a), 'qr_impreso')['hecho'] is False

        with pytest.raises(ValueError):
            marcar_paso_manual(cliente_a, 'platos', True)


def test_tab_gastronomia_muestra_crecer_y_registra_paso_manual():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _, categoria_id = _crear_negocio(app, 'BI Panel', 'bi01_panel')
    _crear_producto(app, cliente_id, categoria_id, 'Pizza BI', imagen_url='/img/p.jpg')
    _loguear(client, app, 'bi01_panel')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    assert 'Activación comercial' in html
    assert 'Canal propio frente a apps' in html
    assert 'Sin pedidos válidos' in html
    assert 'Marcar hecho' in html

    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    respuesta = client.post(
        '/gastronomia/bi/activacion/qr_impreso',
        data={'hecho': '1'},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta.status_code == 302
    assert '/inteligencia' in respuesta.headers['Location']

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    assert 'Desmarcar' in html

    respuesta_invalida = client.post(
        '/gastronomia/bi/activacion/platos',
        data={'hecho': '1'},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta_invalida.status_code == 404


def test_bloque_crecer_se_degrada_sin_romper_el_panel(monkeypatch):
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI Degradado', 'bi01_degradado')

    def _falla(*args, **kwargs):
        raise RuntimeError('fallo simulado')

    monkeypatch.setattr('gastronomia.services.bi.crecer.indicadores_canales', _falla)
    with app.app_context():
        resultado = resumen_crecer_seguro(cliente_id, _periodo())

    assert resultado == {'disponible': False}
