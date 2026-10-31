"""BI-05: panel de salud de uso, solo para root, con semaforo, tendencia y funciones usadas (datos ficticios).

Las fechas salen del dia local de hoy para no depender de la hora de ejecucion.
"""
from app import create_app
from app.models import Configuracion
from app.services.ia_backoffice.settings import CLAVE_SYSTEM_ROOT_USER_ID
from gastronomia.services.bi.activacion import marcar_paso_manual
from gastronomia.services.bi.cola import hoy_local
from gastronomia.services.bi.cola_config import guardar_config
from gastronomia.services.bi.comision import guardar_porcentajes
from gastronomia.services.bi.salud_funciones import CHEQUEOS
from gastronomia.services.bi.salud_uso import (
    ACTIVO,
    EN_RIESGO,
    INACTIVO,
    clasificar_semaforo,
    resumen_salud_uso,
)
from test_gastronomia_bi_cola import (
    CONFIG_VALIDA,
    _crear_negocio,
    _habitual,
    _loguear,
    _pedido,
)


def _ajustar_root(app, usuario_id: int) -> str:
    """Hace root a ese usuario y devuelve el valor anterior para restaurarlo."""
    with app.app_context():
        anterior = Configuracion.obtener(CLAVE_SYSTEM_ROOT_USER_ID, '') or ''
        Configuracion.establecer(CLAVE_SYSTEM_ROOT_USER_ID, str(usuario_id))
    return anterior


def _restaurar_root(app, anterior: str) -> None:
    with app.app_context():
        Configuracion.establecer(CLAVE_SYSTEM_ROOT_USER_ID, anterior)


def _funciones(salud: dict) -> dict:
    return {funcion['nombre']: funcion['usada'] for funcion in salud['funciones']}


def test_semaforo_sigue_las_reglas_explicitas():
    assert clasificar_semaforo(0, 0) == ACTIVO
    assert clasificar_semaforo(7, 30) == ACTIVO
    assert clasificar_semaforo(8, 0) == EN_RIESGO
    assert clasificar_semaforo(3, 31) == EN_RIESGO
    assert clasificar_semaforo(3, None) == EN_RIESGO
    assert clasificar_semaforo(14, 0) == EN_RIESGO
    assert clasificar_semaforo(15, 0) == INACTIVO
    assert clasificar_semaforo(None, 0) == INACTIVO


def test_negocio_nuevo_queda_inactivo_y_lista_todas_las_funciones_sin_usar():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI05 Nuevo', 'bi05_nuevo')
    with app.app_context():
        salud = resumen_salud_uso(cliente_id)
    assert salud['semaforo'] == INACTIVO
    assert salud['pedidos']['ultimo'] is None
    assert salud['pedidos']['dias_sin_pedido'] is None
    assert salud['bi']['ultimo_uso'] is None
    assert salud['colas'] == {
        'en_cola': 0,
        'ultimo_contacto': None,
        'dias_sin_contacto': None,
        'sin_atender': False,
    }
    assert len(salud['tendencia']) == 6
    assert all(semana['pedidos'] == 0 for semana in salud['tendencia'])
    assert salud['funciones_sin_usar'] == [nombre for nombre, _ in CHEQUEOS]


def test_pedido_reciente_y_bi_usado_quedan_activos_y_marcan_las_funciones():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI05 Activo', 'bi05_activo')
    _pedido(app, cliente_id, usuario_id, producto_id, 1, celular='0981 510 001', nombre='Ana')
    with app.app_context():
        marcar_paso_manual(cliente_id, 'qr_impreso', True)
        salud = resumen_salud_uso(cliente_id)
    assert salud['semaforo'] == ACTIVO
    assert salud['semaforo_label'] == 'Activo'
    assert salud['pedidos']['dias_sin_pedido'] == 1
    assert salud['pedidos']['ultimo_pos'] == salud['pedidos']['ultimo']
    assert salud['pedidos']['ultimo_tienda'] is None
    assert salud['bi']['dias_sin_uso'] == 0
    funciones = _funciones(salud)
    assert funciones['Pedidos en el POS'] is True
    assert funciones['Teléfono del cliente en los pedidos'] is True
    assert funciones['Lista de activación comercial'] is True
    assert funciones['Cola de clientes que vuelven'] is False
    assert funciones['Pedidos desde la tienda online'] is False


def test_pedidos_recientes_sin_acciones_en_el_bi_quedan_en_riesgo():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI05 Riesgo', 'bi05_riesgo')
    _pedido(app, cliente_id, usuario_id, producto_id, 2, celular='0981 520 001', nombre='Beto')
    with app.app_context():
        salud = resumen_salud_uso(cliente_id)
    assert salud['semaforo'] == EN_RIESGO
    assert 'todavía no tiene acciones registradas' in salud['semaforo_motivo']


def test_pedido_de_hace_veinte_dias_queda_inactivo_con_motivo():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI05 Viejo', 'bi05_viejo')
    _pedido(app, cliente_id, usuario_id, producto_id, 20, celular='0981 530 001', nombre='Carla')
    with app.app_context():
        salud = resumen_salud_uso(cliente_id)
    assert salud['semaforo'] == INACTIVO
    assert salud['pedidos']['dias_sin_pedido'] == 20
    assert salud['semaforo_motivo'] == 'El último pedido fue hace 20 días.'


def test_cambios_del_bi_cuentan_como_uso_reciente():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI05 Cambios', 'bi05_cambios')
    with app.app_context():
        assert resumen_salud_uso(cliente_id)['bi']['dias_sin_uso'] is None
        guardar_porcentajes(cliente_id, {'comision_pedidosya': '25'})
        assert resumen_salud_uso(cliente_id)['bi']['dias_sin_uso'] == 0
        guardar_config(cliente_id, CONFIG_VALIDA)
        funciones = _funciones(resumen_salud_uso(cliente_id))
    assert funciones['Comisión evitada'] is True
    assert funciones['Configuración de la cola'] is True


def test_cola_con_contactos_y_sin_atender_se_informa():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI05 Cola', 'bi05_cola')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 540 001', 'Dani')
    with app.app_context():
        colas = resumen_salud_uso(cliente_id)['colas']
    assert colas['en_cola'] == 1
    assert colas['ultimo_contacto'] is None
    assert colas['sin_atender'] is True


def test_tendencia_cuenta_solo_las_seis_semanas_de_la_ventana():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI05 Tendencia', 'bi05_tendencia')
    _pedido(app, cliente_id, usuario_id, producto_id, 0, celular='0981 550 001', nombre='Edu')
    _pedido(app, cliente_id, usuario_id, producto_id, 60, celular='0981 550 002', nombre='Fer')
    with app.app_context():
        tendencia = resumen_salud_uso(cliente_id)['tendencia']
    assert len(tendencia) == 6
    assert sum(semana['pedidos'] for semana in tendencia) == 1
    assert tendencia[-1]['pedidos'] == 1
    assert tendencia[-1]['inicio'] <= hoy_local()


def test_la_salud_no_mezcla_datos_de_otra_instalacion():
    app = create_app('testing')
    cliente_a, usuario_a, producto_a = _crear_negocio(app, 'BI05 A', 'bi05_a')
    cliente_b, _, _ = _crear_negocio(app, 'BI05 B', 'bi05_b')
    _pedido(app, cliente_a, usuario_a, producto_a, 1, celular='0981 560 001', nombre='Gaby')
    with app.app_context():
        salud_b = resumen_salud_uso(cliente_b)
    assert salud_b['semaforo'] == INACTIVO
    assert salud_b['pedidos']['ultimo'] is None


def test_panel_solo_lo_ve_root_y_no_el_admin_del_negocio():
    app = create_app('testing')
    admin_client = app.test_client()
    root_client = app.test_client()
    _crear_negocio(app, 'BI05 Ruta', 'bi05_ruta')
    _, usuario_root, _ = _crear_negocio(app, 'BI05 Root', 'bi05_root')
    anterior = _ajustar_root(app, usuario_root)
    try:
        _loguear(admin_client, app, 'bi05_ruta')
        _loguear(root_client, app, 'bi05_root')
        assert admin_client.get('/gastronomia/bi/salud-uso').status_code == 403
        respuesta = root_client.get('/gastronomia/bi/salud-uso')
        assert respuesta.status_code == 200
        html = respuesta.get_data(as_text=True)
        assert 'Salud de uso' in html
        assert 'Estado de la instalación' in html
        assert 'Funciones usadas' in html
    finally:
        _restaurar_root(app, anterior)


def test_tablero_muestra_el_enlace_de_salud_solo_a_root():
    app = create_app('testing')
    admin_client = app.test_client()
    root_client = app.test_client()
    _crear_negocio(app, 'BI05 Tablero', 'bi05_tablero')
    _, usuario_root, _ = _crear_negocio(app, 'BI05 Tablero Root', 'bi05_tablero_root')
    anterior = _ajustar_root(app, usuario_root)
    try:
        _loguear(admin_client, app, 'bi05_tablero')
        _loguear(root_client, app, 'bi05_tablero_root')
        html_admin = admin_client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
        html_root = root_client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
        assert 'Salud de uso (solo root)' not in html_admin
        assert 'Salud de uso (solo root)' in html_root
    finally:
        _restaurar_root(app, anterior)


def test_panel_renderiza_con_csrf_y_datos_del_negocio():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI05 Render', 'bi05_render')
    _pedido(app, cliente_id, usuario_id, producto_id, 3, celular='0981 570 001', nombre='Hugo')
    # El root de una instalacion pertenece a esa instalacion: el panel muestra sus datos.
    anterior = _ajustar_root(app, usuario_id)
    try:
        _loguear(client, app, 'bi05_render')
        html = client.get('/gastronomia/bi/salud-uso').get_data(as_text=True)
        assert 'hace 3 días' in html
        assert 'En riesgo' in html
        assert 'Cómo se calcula' in html
        assert 'Pedidos por semana' in html
    finally:
        _restaurar_root(app, anterior)
