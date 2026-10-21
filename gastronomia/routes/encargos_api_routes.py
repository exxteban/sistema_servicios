"""API de encargos de Gastronomia (pasteleria / cafeteria).

Con `encargos_activo` apagado los endpoints responden 404, salvo borrar una
foto: si el local apaga los encargos, tiene que poder limpiar lo que subio.
"""
from datetime import date

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.adelanto_service import cancelar_encargo, registrar_adelanto, sena_vigente
from gastronomia.services.delivery_privacy import ocultar_localizacion_pedido
from gastronomia.services.encargo_foto_service import (
    agregar_foto_encargo,
    eliminar_foto_encargo,
    listar_fotos_encargo,
)
from gastronomia.services.encargo_service import (
    EncargosDeshabilitadosError,
    actualizar_encargo,
    enviar_a_produccion,
    encargos_habilitados,
    obtener_encargo,
)
from gastronomia.services.encargo_tablero_service import crear_encargo_desde_tablero, tablero_encargos
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_POS,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)


gastronomia_encargos_api_bp = Blueprint('gastronomia_encargos_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _no_encontrado():
    return jsonify({'error': 'not_found'}), 404


def _payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _pedido_data(pedido) -> dict:
    return ocultar_localizacion_pedido(pedido.to_dict(), current_user)


def _ejecutar(accion, *, status=200):
    """Corre una accion de encargo y traduce los errores del servicio a HTTP."""
    try:
        resultado = accion()
    except EncargosDeshabilitadosError:
        return _no_encontrado()
    except ValueError as exc:
        if str(exc) in {'Encargo no encontrado.', 'Pedido no encontrado.'}:
            return _no_encontrado()
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, **resultado}), status


@gastronomia_encargos_api_bp.route('/encargos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def tablero():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        desde = date.fromisoformat(request.args['desde']) if request.args.get('desde') else None
    except ValueError:
        return jsonify({'error': 'validation_error', 'mensaje': 'Fecha invalida.'}), 400
    dias = request.args.get('dias', type=int) or 7
    return _ejecutar(lambda: {
        **tablero_encargos(cliente_id, desde=desde, dias=dias),
        'puede_resolver_senas': tiene_permiso_gastronomia(PERMISO_CAJA),
    })


@gastronomia_encargos_api_bp.route('/encargos', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def crear():
    cliente_id, error = _cliente_o_error()
    if error:
        return error

    def accion():
        pedido, aviso = crear_encargo_desde_tablero(cliente_id, current_user.id_usuario, _payload())
        return {'pedido': _pedido_data(pedido), 'aviso': aviso}

    return _ejecutar(accion, status=201)


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def actualizar(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return _ejecutar(lambda: {'pedido': _pedido_data(actualizar_encargo(cliente_id, pedido_id, _payload()))})


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>/sena', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def cobrar_sena(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error

    def accion():
        registrar_adelanto(cliente_id, current_user.id_usuario, pedido_id, _payload())
        return {'pedido': _pedido_data(obtener_encargo(cliente_id, pedido_id))}

    return _ejecutar(accion, status=201)


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>/produccion', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def enviar_produccion(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return _ejecutar(lambda: {'pedido': _pedido_data(enviar_a_produccion(cliente_id, pedido_id))})


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def cancelar(pedido_id):
    """Cancelar sin sena alcanza con POS; devolver o retener una sena exige permiso de caja."""
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    pedido = obtener_encargo(cliente_id, pedido_id)
    if not pedido:
        return _no_encontrado()
    if sena_vigente(pedido) > 0 and not tiene_permiso_gastronomia(PERMISO_CAJA):
        return jsonify({
            'error': 'Sin permisos',
            'mensaje': 'Para devolver o retener una sena hace falta permiso de caja.',
        }), 403
    data = _payload()
    return _ejecutar(lambda: {'pedido': _pedido_data(cancelar_encargo(
        cliente_id,
        current_user.id_usuario,
        pedido_id,
        opcion=data.get('opcion') or None,
        monto_retenido=data.get('monto_retenido'),
        motivo=data.get('motivo') or '',
    ))})


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>/fotos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def listar_fotos(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    pedido = obtener_encargo(cliente_id, pedido_id) if encargos_habilitados(cliente_id) else None
    if not pedido:
        return _no_encontrado()
    return jsonify({'ok': True, 'fotos': [foto.to_dict() for foto in listar_fotos_encargo(pedido)]})


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>/fotos', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def subir_foto(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        foto = agregar_foto_encargo(
            cliente_id,
            current_user.id_usuario,
            pedido_id,
            request.files.get('foto'),
            current_app.static_folder,
        )
    except EncargosDeshabilitadosError:
        return _no_encontrado()
    except ValueError as exc:
        if str(exc) == 'Encargo no encontrado.':
            return _no_encontrado()
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'foto': foto.to_dict()}), 201


@gastronomia_encargos_api_bp.route('/encargos/<int:pedido_id>/fotos/<int:foto_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def borrar_foto(pedido_id, foto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        eliminar_foto_encargo(cliente_id, pedido_id, foto_id, current_app.static_folder)
    except ValueError:
        return _no_encontrado()
    return jsonify({'ok': True})
