"""API de produccion diaria, porciones y merma (pasteleria / cafeteria).

Con `produccion_diaria_activa` apagado todos los endpoints responden 404.
"""
from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.merma_reporte_service import reporte_merma
from gastronomia.services.permisos import (
    PERMISO_COCINA,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_REPORTES,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)
from gastronomia.services.porciones_service import abrir_entero, eliminar_relacion, guardar_relacion
from gastronomia.services.produccion_service import (
    ProduccionDeshabilitadaError,
    cerrar_dia,
    hoy_local,
    produccion_habilitada,
    productos_menu_sin_control,
    registrar_merma,
    registrar_produccion,
    resumen_dia,
)


gastronomia_produccion_api_bp = Blueprint('gastronomia_produccion_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    if not produccion_habilitada(cliente_id):
        return None, (jsonify({'error': 'not_found'}), 404)
    return cliente_id, None


def _payload() -> dict:
    return request.get_json(silent=True) or {}


def _ejecutar(accion, *, status=200):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        resultado = accion(cliente_id)
    except ProduccionDeshabilitadaError:
        return jsonify({'error': 'not_found'}), 404
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, **resultado}), status


def _fecha(nombre: str, default: date) -> date:
    valor = request.args.get(nombre)
    if not valor:
        return default
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ValueError('Fecha invalida.')


@gastronomia_produccion_api_bp.route('/produccion/dia', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA)
def dia():
    return _ejecutar(lambda cliente_id: {
        **resumen_dia(cliente_id, _fecha('fecha', hoy_local())),
        'productos_sin_control': productos_menu_sin_control(cliente_id),
        'puede_configurar': tiene_permiso_gastronomia(PERMISO_MENU),
    })


@gastronomia_produccion_api_bp.route('/produccion/tandas', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA)
def tanda():
    return _ejecutar(
        lambda cliente_id: {'registro': registrar_produccion(cliente_id, current_user.id_usuario, _payload()).to_dict()},
        status=201,
    )


@gastronomia_produccion_api_bp.route('/produccion/mermas', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA)
def merma():
    return _ejecutar(
        lambda cliente_id: {'registro': registrar_merma(cliente_id, current_user.id_usuario, _payload()).to_dict()},
        status=201,
    )


@gastronomia_produccion_api_bp.route('/produccion/cierre', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA)
def cierre():
    return _ejecutar(lambda cliente_id: {
        'registros': [r.to_dict() for r in cerrar_dia(cliente_id, current_user.id_usuario, _payload())],
    })


@gastronomia_produccion_api_bp.route('/produccion/productos/<int:producto_id>/abrir', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA)
def abrir(producto_id):
    return _ejecutar(lambda cliente_id: abrir_entero(cliente_id, current_user.id_usuario, producto_id))


@gastronomia_produccion_api_bp.route('/produccion/productos/<int:producto_id>/porciones', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def porciones(producto_id):
    return _ejecutar(lambda cliente_id: {'relacion': guardar_relacion(cliente_id, producto_id, _payload()).to_dict()})


@gastronomia_produccion_api_bp.route('/produccion/productos/<int:producto_id>/porciones', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def quitar_porciones(producto_id):
    def accion(cliente_id):
        if not eliminar_relacion(cliente_id, producto_id):
            raise ValueError('Ese producto no tiene porciones configuradas.')
        return {}

    return _ejecutar(accion)


@gastronomia_produccion_api_bp.route('/produccion/merma', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES, PERMISO_MENU)
def reporte():
    hoy = hoy_local()
    return _ejecutar(lambda cliente_id: reporte_merma(
        cliente_id, _fecha('desde', hoy - timedelta(days=6)), _fecha('hasta', hoy),
    ))
