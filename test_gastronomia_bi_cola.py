"""BI-02: cola de envio asistido, segmentos, limites, no quiere mensajes y atribucion.

Datos ficticios. Las fechas se calculan desde el dia local de hoy para no depender de la hora de ejecucion.
"""
import re
from datetime import datetime, timedelta

import pytest

from app import create_app, db
from app.models import Cliente, Usuario
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.bi_models import GastronomiaBiContacto, GastronomiaBiNoContactar
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaProducto,
)
from gastronomia.services.bi.cola import construir_cola, hoy_local, resumen_cola
from gastronomia.services.bi.cola_acciones import (
    MSG_LIMITE,
    abrir_contacto,
    marcar_enviado,
    no_quiere_mensajes,
    omitir_contacto,
)
from gastronomia.services.bi.cola_config import guardar_config, leer_config
from gastronomia.services.bi.clientes_vuelven import resumen_clientes_vuelven_seguro
from gastronomia.services.bi.historial import ClienteHistorial, historial_clientes
from gastronomia.services.bi.plantillas import renderizar
from gastronomia.services.bi.retorno import resumen_retorno
from gastronomia.services.bi.segmentos import HABITUAL_AUSENTE, SEGUNDA_COMPRA, clasificar_segmentos
from gastronomia.services.bi.whatsapp import url_wa_me

CONFIG_VALIDA = {
    'limite_dia': '20',
    'frecuencia_dias': '14',
    'segunda_min': '5',
    'segunda_max': '15',
    'pl_habitual_ausente': 'Hola {nombre}, te extrañamos en {negocio}. Pedí acá: {link}',
    'pl_segunda_compra': 'Hola {nombre}, gracias por tu pedido en {negocio}.',
}


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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Cola BI')
        db.session.add_all([
            usuario,
            categoria,
            GastronomiaClienteConfig(cliente_id=cliente.id_cliente, modo_operacion='gastronomia', gastronomia_activo=True),
        ])
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Milanesa BI',
            precio=30000,
            disponible=True,
            visible=True,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, usuario.id_usuario, producto.id_producto


def _pedido(app, cliente_id, usuario_id, producto_id, dias_atras: int, *, celular: str, nombre: str = 'Cliente',
            origen: str = 'pos', estado: str = 'cobrado') -> int:
    dia = hoy_local() - timedelta(days=dias_atras)
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
            fecha_creacion=inicio_utc + timedelta(hours=12),
            subtotal=30000,
            total=30000,
        )
        db.session.add(pedido)
        db.session.flush()
        db.session.add(GastronomiaPedidoItem(
            pedido_id=pedido.id_pedido,
            cliente_id=cliente_id,
            producto_id=producto_id,
            nombre_producto='Milanesa BI',
            cantidad=1,
            precio_unitario=30000,
            precio_original=30000,
            subtotal=30000,
        ))
        db.session.commit()
        return pedido.id_pedido


def _habitual(app, cliente_id, usuario_id, producto_id, celular: str, nombre: str) -> None:
    # Compras hace 30, 23, 16 y 9 dias: intervalo 7, ultima compra hace 9 dias (supera el intervalo).
    for dias in (30, 23, 16, 9):
        _pedido(app, cliente_id, usuario_id, producto_id, dias, celular=celular, nombre=nombre)


def _segunda(app, cliente_id, usuario_id, producto_id, celular: str, nombre: str, dias: int = 10) -> None:
    _pedido(app, cliente_id, usuario_id, producto_id, dias, celular=celular, nombre=nombre)


def _configurar(app, cliente_id, **cambios) -> None:
    datos = {**CONFIG_VALIDA, **{clave: str(valor) for clave, valor in cambios.items()}}
    with app.app_context():
        guardar_config(cliente_id, datos)


def _cliente_historial(telefono: str, dias: list[int]) -> ClienteHistorial:
    cliente = ClienteHistorial(telefono=telefono, nombre='Prueba', ultimo_pedido_id=1)
    cliente.dias = {hoy_local() - timedelta(days=d) for d in dias}
    return cliente


def test_segmentos_siguen_reglas_fijas_de_historial():
    hoy = hoy_local()
    historial = {
        'una_hace_10': _cliente_historial('+595981000001', [10]),
        'una_hace_3': _cliente_historial('+595981000002', [3]),
        'una_hace_20': _cliente_historial('+595981000003', [20]),
        'habitual_vencido': _cliente_historial('+595981000004', [30, 23, 16, 9]),
        'habitual_al_dia': _cliente_historial('+595981000005', [30, 23, 16, 6]),
        'dos_compras': _cliente_historial('+595981000006', [20, 10]),
    }

    candidatos = {
        c['telefono']: c
        for c in clasificar_segmentos(historial, hoy, segunda_min=5, segunda_max=15)
    }

    assert candidatos['+595981000001']['segmento'] == SEGUNDA_COMPRA
    assert '+595981000002' not in candidatos
    assert '+595981000003' not in candidatos
    assert candidatos['+595981000004']['segmento'] == HABITUAL_AUSENTE
    assert candidatos['+595981000004']['intervalo_dias'] == 7
    assert '+595981000005' not in candidatos
    assert '+595981000006' not in candidatos


def test_historial_incluye_fuera_de_periodo_y_no_mezcla_homonimos():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Historial', 'bi02_historial')
    _pedido(app, cliente_id, usuario_id, producto_id, 200, celular='0981 111 222', nombre='Ana')
    _pedido(app, cliente_id, usuario_id, producto_id, 190, celular='0971 333 444', nombre='Ana')
    _pedido(app, cliente_id, usuario_id, producto_id, 5, celular='0971 333 444', nombre='Ana')
    _pedido(app, cliente_id, usuario_id, producto_id, 4, celular='0971 333 444', nombre='Ana', estado='cancelado')
    _pedido(app, cliente_id, usuario_id, producto_id, 3, celular='0971 333 444', nombre='Ana', origen='importado')

    with app.app_context():
        historial = historial_clientes(cliente_id)

    assert set(historial) == {'+595981111222', '+595971333444'}
    assert len(historial['+595981111222'].dias) == 1
    assert len(historial['+595971333444'].dias) == 2
    assert historial['+595971333444'].plato_favorito == 'Milanesa BI'


def test_cola_ofrece_habitual_ausente_fuera_del_periodo_y_respeta_no_quiere_mensajes():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Cola', 'bi02_cola')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 555 111', 'Lucía')

    with app.app_context():
        resumen = resumen_cola(cliente_id)
        assert resumen['en_cola'] == 1
        assert resumen['siguiente']['segmento'] == HABITUAL_AUSENTE
        assert resumen['siguiente']['nombre'] == 'Lucía'
        assert resumen['siguiente']['intervalo_dias'] == 7
        assert resumen['siguiente']['mensaje'].startswith('Hola Lucía,')

        no_quiere_mensajes(cliente_id, {'telefono': '+595981555111'})
        resumen = resumen_cola(cliente_id)
        assert resumen['en_cola'] == 0
        assert resumen['siguiente'] is None
        assert GastronomiaBiNoContactar.query.filter_by(cliente_id=cliente_id).count() == 1


def test_abrir_no_marca_enviado_y_el_limite_diario_frena_la_cola():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Limite', 'bi02_limite')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 600 100', 'Marta')
    _segunda(app, cliente_id, usuario_id, producto_id, '0981 600 200', 'Pablo')
    _configurar(app, cliente_id, limite_dia=1)

    with app.app_context():
        primero = resumen_cola(cliente_id)['siguiente']
        datos = {'telefono': primero['telefono'], 'segmento': primero['segmento'], 'pedido': primero['ultimo_pedido_id']}

        url = abrir_contacto(cliente_id, datos)
        assert url.startswith('https://wa.me/')
        assert 'text=' in url
        resumen = resumen_cola(cliente_id)
        assert resumen['enviados_hoy'] == 0
        assert resumen['siguiente']['telefono'] == primero['telefono']

        marcar_enviado(cliente_id, datos)
        resumen = resumen_cola(cliente_id)
        assert resumen['enviados_hoy'] == 1
        assert resumen['limite_alcanzado'] is True
        assert resumen['siguiente'] is None

        # Pablo sigue en la cola, pero el limite diario ya se alcanzo.
        _, disponibles = construir_cola(cliente_id, hoy_local())
        pablo = next(c for c in disponibles if c['telefono'] == '+595981600200')
        with pytest.raises(ValueError) as error:
            marcar_enviado(cliente_id, {
                'telefono': pablo['telefono'],
                'segmento': pablo['segmento'],
                'pedido': pablo['ultimo_pedido_id'],
            })
        assert str(error.value) == MSG_LIMITE


def test_omitido_no_vuelve_a_la_cola():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Omitido', 'bi02_omitido')
    _segunda(app, cliente_id, usuario_id, producto_id, '0981 700 100', 'Rosa')

    with app.app_context():
        candidato = resumen_cola(cliente_id)['siguiente']
        datos = {'telefono': candidato['telefono'], 'segmento': candidato['segmento'], 'pedido': candidato['ultimo_pedido_id']}
        omitir_contacto(cliente_id, datos)
        assert resumen_cola(cliente_id)['en_cola'] == 0
        contacto = GastronomiaBiContacto.query.filter_by(cliente_id=cliente_id).one()
        assert contacto.estado == 'omitido'


def test_frecuencia_maxima_bloquea_y_luego_libera_al_mismo_telefono():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Frecuencia', 'bi02_frecuencia')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 800 100', 'Elena')
    with app.app_context():
        candidato = resumen_cola(cliente_id)['siguiente']
        db.session.add(GastronomiaBiContacto(
            cliente_id=cliente_id,
            telefono_normalizado=candidato['telefono'],
            nombre='Elena',
            segmento=HABITUAL_AUSENTE,
            ultimo_pedido_id=999999,
            estado='enviado',
            fecha_estado=datetime.utcnow() - timedelta(days=3),
        ))
        db.session.commit()
        assert resumen_cola(cliente_id)['en_cola'] == 0

    with app.app_context():
        GastronomiaBiContacto.query.filter_by(cliente_id=cliente_id).update(
            {'fecha_estado': datetime.utcnow() - timedelta(days=20)}
        )
        db.session.commit()
        assert resumen_cola(cliente_id)['en_cola'] == 1


def test_no_quiere_mensajes_solo_acepta_telefonos_del_historial():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Opt', 'bi02_opt')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 900 100', 'Hugo')

    with app.app_context():
        with pytest.raises(ValueError):
            no_quiere_mensajes(cliente_id, {'telefono': '+595999999999'})
        assert GastronomiaBiNoContactar.query.filter_by(cliente_id=cliente_id).count() == 0


def test_retorno_cuenta_compras_posteriores_al_envio_y_excluye_anulados():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Retorno', 'bi02_retorno')
    _pedido(app, cliente_id, usuario_id, producto_id, 17, celular='0981 910 100', nombre='Volvio')
    _pedido(app, cliente_id, usuario_id, producto_id, 17, celular='0981 910 200', nombre='Anulado', estado='cancelado')
    ahora = datetime.utcnow()
    with app.app_context():
        db.session.add_all([
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981910100', nombre='Volvio',
                segmento=SEGUNDA_COMPRA, ultimo_pedido_id=1, estado='enviado',
                fecha_estado=ahora - timedelta(days=20),
            ),
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981910200', nombre='Anulado',
                segmento=SEGUNDA_COMPRA, ultimo_pedido_id=2, estado='enviado',
                fecha_estado=ahora - timedelta(days=20),
            ),
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981910300', nombre='Reciente',
                segmento=SEGUNDA_COMPRA, ultimo_pedido_id=3, estado='enviado',
                fecha_estado=ahora - timedelta(days=2),
            ),
        ])
        db.session.commit()
        retorno = resumen_retorno(cliente_id)

    assert retorno['enviados_cerrados'] == 2
    assert retorno['volvieron'] == 1
    assert retorno['en_observacion'] == 1


def test_configuracion_rechaza_valores_fuera_de_rango():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI Config', 'bi02_config')
    with app.app_context():
        with pytest.raises(ValueError):
            guardar_config(cliente_id, {**CONFIG_VALIDA, 'limite_dia': '0'})
        with pytest.raises(ValueError):
            guardar_config(cliente_id, {**CONFIG_VALIDA, 'segunda_min': '20', 'segunda_max': '10'})
        with pytest.raises(ValueError):
            guardar_config(cliente_id, {**CONFIG_VALIDA, 'pl_segunda_compra': '   '})
        assert leer_config(cliente_id)['limite_dia'] == 20


def test_plantilla_renderiza_variables_y_quita_el_enlace_sin_tienda():
    con_enlace = renderizar(
        SEGUNDA_COMPRA, None, nombre='Ana', plato='Milanesa', negocio='Resto', link='https://tienda.test/x',
    )
    sin_enlace = renderizar(SEGUNDA_COMPRA, None, nombre='', plato=None, negocio='Resto', link='')

    assert 'Ana' in con_enlace and 'https://tienda.test/x' in con_enlace and '{' not in con_enlace
    assert sin_enlace.startswith('Hola amigo, gracias por tu pedido en Resto.')
    assert not sin_enlace.endswith(':')
    assert '{' not in sin_enlace


def test_url_wa_me_limpia_el_telefono():
    assert url_wa_me('+595 981 123 456', 'Hola') == 'https://wa.me/595981123456?text=Hola'
    assert url_wa_me(None, 'Hola') is None


def test_tab_gastronomia_muestra_la_cola_y_acepta_las_acciones():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Panel Cola', 'bi02_panel')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 950 100', 'Teresa')
    _loguear(client, app, 'bi02_panel')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    assert 'Clientes que vuelven' in html
    assert 'Teresa' in html
    assert 'Abrir WhatsApp' in html
    assert 'Marcar enviado' in html

    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    with app.app_context():
        _, disponibles = construir_cola(cliente_id, hoy_local())
    candidato = disponibles[0]
    datos = {
        'telefono': candidato['telefono'],
        'segmento': candidato['segmento'],
        'pedido': str(candidato['ultimo_pedido_id']),
    }

    respuesta_invalida = client.post(
        '/gastronomia/bi/cola/abrir',
        data={**datos, 'pedido': '999999'},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta_invalida.status_code == 302
    assert '/inteligencia' in respuesta_invalida.headers['Location']
    with app.app_context():
        assert GastronomiaBiContacto.query.filter_by(cliente_id=cliente_id).count() == 0

    respuesta = client.post('/gastronomia/bi/cola/abrir', data=datos, headers={'X-CSRFToken': csrf})
    assert respuesta.status_code == 302
    assert respuesta.headers['Location'].startswith('https://wa.me/')
    with app.app_context():
        contacto = GastronomiaBiContacto.query.filter_by(cliente_id=cliente_id).one()
        assert contacto.estado == 'abierto'


def test_tab_gastronomia_guarda_configuracion_valida_por_post():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _, _ = _crear_negocio(app, 'BI Post Config', 'bi02_post_config')
    _loguear(client, app, 'bi02_post_config')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    respuesta = client.post(
        '/gastronomia/bi/cola/configuracion',
        data={**CONFIG_VALIDA, 'limite_dia': '7', 'csrf_token': csrf},
        headers={'X-CSRFToken': csrf},
    )

    assert respuesta.status_code == 302
    with app.app_context():
        assert leer_config(cliente_id)['limite_dia'] == 7


def test_bloque_clientes_que_vuelven_se_degrada_sin_romper_el_panel(monkeypatch):
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI Degradado Cola', 'bi02_degradado')

    def _falla(*args, **kwargs):
        raise RuntimeError('fallo simulado')

    monkeypatch.setattr('gastronomia.services.bi.clientes_vuelven.resumen_cola', _falla)
    with app.app_context():
        assert resumen_clientes_vuelven_seguro(cliente_id) == {'disponible': False}


def test_construir_cola_no_aplica_el_limite_diario():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI Sin Limite', 'bi02_sin_limite')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 960 100', 'Nora')
    _configurar(app, cliente_id, limite_dia=1)
    with app.app_context():
        _, disponibles = construir_cola(cliente_id, hoy_local())
    assert len(disponibles) == 1
