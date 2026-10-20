"""Red de seguridad de la Fase 0 del plan de pasteleria (plan_pasteleria.md).

Con todos los flags apagados el modo gastronomia debe comportarse igual que
antes: pedido, cocina, stock, cobro y caja. Y la migracion de los flags debe
poder correr sobre una base vieja sin romper nada.
"""
import re

import pytest
from sqlalchemy import text

from app import create_app, db
from app.models import Caja, Cliente, MovimientoCaja, SesionCaja, Usuario, Venta
from gastronomia.config_flags import PASTELERIA_FLAGS, PasteleriaFlagsMixin
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaMesa,
    GastronomiaPedidoPago,
    GastronomiaProducto,
)
from gastronomia.schema import ensure_gastronomia_schema
from gastronomia.services.pasteleria_flags import flag_activo, flags_cliente


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


def _crear_local(app, nombre: str, username: str, stock: int | None = None):
    """Local gastronomico con config por defecto (sin tocar ningun flag)."""
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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Platos')
        db.session.add_all([
            usuario,
            categoria,
            GastronomiaMesa(cliente_id=cliente.id_cliente, nombre='M1'),
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
            nombre='Hamburguesa',
            precio=30000,
            control_stock_venta=stock is not None,
            stock_disponible=stock,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto


def _abrir_caja(app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        caja = Caja(nombre=f'Caja {username}', ubicacion='Gastronomia')
        db.session.add(caja)
        db.session.flush()
        sesion = SesionCaja(
            id_caja=caja.id_caja,
            id_usuario=usuario.id_usuario,
            monto_inicial=0,
            estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        return sesion.id_sesion


def _estado(client, csrf, pedido_id, estado):
    response = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': estado},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()['pedido']


def _crear_pedido(client, csrf, producto_id, cantidad, **extra):
    response = client.post(
        '/api/gastronomia/pedidos',
        json={'items': [{'producto_id': producto_id, 'cantidad': cantidad}], **extra},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()['pedido']


def _columnas_config() -> set[str]:
    return {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(gastronomia_cliente_config)')).fetchall()
    }


# --- Flujo existente sin flags -------------------------------------------------

def test_pedido_mesa_cocina_cobro_y_caja_sin_flags():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_local(app, 'Humo Mesa', 'humo_mesa', stock=5)
    _loguear(client, app, 'humo_mesa')
    id_sesion = _abrir_caja(app, 'humo_mesa')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))

    pedido = _crear_pedido(client, csrf, producto_id, 2, tipo_pedido='mesa', mesa='M1')
    pedido_id = pedido['id_pedido']
    assert pedido['estado'] == 'abierto'
    assert pedido['total'] == 60000

    with app.app_context():
        assert GastronomiaProducto.query.get(producto_id).stock_disponible == 3

    for estado in ('enviado_cocina', 'preparando', 'listo'):
        assert _estado(client, csrf, pedido_id, estado)['estado'] == estado

    cobro = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobro.status_code == 200, cobro.get_data(as_text=True)
    assert cobro.get_json()['pedido']['estado_pago'] == 'pagado'

    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).one()
        assert float(pago.total_cobrado) == 60000
        assert pago.id_sesion_caja == id_sesion
        venta = Venta.query.get(pago.id_venta)
        assert float(venta.total) == 60000
        movimiento = MovimientoCaja.query.get(pago.id_movimiento_caja)
        assert movimiento.id_sesion_caja == id_sesion
        assert movimiento.referencia_tipo == 'venta'
        assert float(movimiento.monto) == 60000
        # Cobrar no vuelve a tocar el stock.
        assert GastronomiaProducto.query.get(producto_id).stock_disponible == 3


def test_cancelar_pedido_restaura_stock_sin_flags():
    app = create_app('testing')
    client = app.test_client()
    _, producto_id = _crear_local(app, 'Humo Cancela', 'humo_cancela', stock=4)
    _loguear(client, app, 'humo_cancela')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))

    pedido_id = _crear_pedido(client, csrf, producto_id, 3, tipo_pedido='mostrador')['id_pedido']
    with app.app_context():
        assert GastronomiaProducto.query.get(producto_id).stock_disponible == 1

    _estado(client, csrf, pedido_id, 'cancelado')
    with app.app_context():
        assert GastronomiaProducto.query.get(producto_id).stock_disponible == 4

    # Reabrir un cancelado vuelve a consumir una sola vez.
    _estado(client, csrf, pedido_id, 'abierto')
    with app.app_context():
        assert GastronomiaProducto.query.get(producto_id).stock_disponible == 1


# --- Flags ---------------------------------------------------------------------

def test_flags_existen_y_estan_apagados_en_instalacion_existente():
    app = create_app('testing')
    cliente_id, _ = _crear_local(app, 'Humo Flags', 'humo_flags')

    with app.app_context():
        assert set(PASTELERIA_FLAGS) == {
            'encargos_activo',
            'venta_por_peso_activa',
            'produccion_diaria_activa',
            'venta_rapida_activa',
            'propina_activa',
        }
        assert set(PASTELERIA_FLAGS) <= _columnas_config()
        assert flags_cliente(cliente_id) == {flag: False for flag in PASTELERIA_FLAGS}
        for flag in PASTELERIA_FLAGS:
            assert flag_activo(cliente_id, flag) is False


def test_columnas_de_flags_son_seguras_para_bases_existentes():
    for flag in PASTELERIA_FLAGS:
        columna = getattr(PasteleriaFlagsMixin, flag)
        assert columna.nullable is False
        assert columna.default.arg is False
        assert str(columna.server_default.arg) == '0'


def test_flag_activo_es_estricto():
    app = create_app('testing')
    cliente_id, _ = _crear_local(app, 'Humo Flag Estricto', 'humo_flag_estricto')

    with app.app_context():
        assert flag_activo(None, 'encargos_activo') is False
        assert flag_activo(0, 'encargos_activo') is False
        assert flag_activo('abc', 'encargos_activo') is False
        assert flag_activo(99999999, 'encargos_activo') is False  # sin config
        with pytest.raises(ValueError):
            flag_activo(cliente_id, 'modo_operacion')

        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.encargos_activo = True
        db.session.commit()
        assert flag_activo(cliente_id, 'encargos_activo') is True
        assert flag_activo(cliente_id, 'propina_activa') is False


# --- Migracion -----------------------------------------------------------------

def test_ensure_schema_es_idempotente():
    app = create_app('testing')
    with app.app_context():
        antes = _columnas_config()
        ensure_gastronomia_schema()
        ensure_gastronomia_schema()
        assert _columnas_config() == antes


def test_migracion_agrega_flags_a_base_vieja_sin_perder_datos():
    app = create_app('testing')
    cliente_id, _ = _crear_local(app, 'Humo Base Vieja', 'humo_base_vieja')

    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.menu_tv_titulo = 'Titulo previo'
        db.session.commit()
        try:
            # Simula una base anterior a la Fase 0: sin las columnas de flags.
            for flag in PASTELERIA_FLAGS:
                db.session.execute(text(f'ALTER TABLE gastronomia_cliente_config DROP COLUMN {flag}'))
            db.session.commit()
            assert not set(PASTELERIA_FLAGS) & _columnas_config()

            ensure_gastronomia_schema()

            assert set(PASTELERIA_FLAGS) <= _columnas_config()
            db.session.expire_all()
            config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
            assert config.menu_tv_titulo == 'Titulo previo'
            assert config.modo_operacion == 'gastronomia'
            assert flags_cliente(cliente_id) == {flag: False for flag in PASTELERIA_FLAGS}
        finally:
            db.session.rollback()
            ensure_gastronomia_schema()
            assert set(PASTELERIA_FLAGS) <= _columnas_config()
