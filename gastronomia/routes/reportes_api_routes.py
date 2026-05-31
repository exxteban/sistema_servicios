"""API de reportes para Gastronomia."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.utils.permisos import validar_autorizacion
from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.anulacion_service import anular_venta_gastronomica
from gastronomia.services.permisos import PERMISO_CAJA, PERMISO_REPORTES, requiere_permiso_gastronomia
from gastronomia.services.reportes_service import resumen_reportes


gastronomia_reportes_api_bp = Blueprint('gastronomia_reportes_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


@gastronomia_reportes_api_bp.route('/reportes/resumen', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
def reportes_resumen():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    data = resumen_reportes(
        cliente_id,
        fecha_desde=request.args.get('desde'),
        fecha_hasta=request.args.get('hasta'),
    )
    return jsonify({'ok': True, 'resumen': data})


@gastronomia_reportes_api_bp.route('/reportes/pedidos/<int:pedido_id>/anular-venta', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES, PERMISO_CAJA)
def reportes_anular_venta(pedido_id):
    if not (current_user.es_admin() or current_user.tiene_permiso('anular_venta')):
        return jsonify({'error': 'Sin permisos', 'mensaje': 'No tienes permisos para anular ventas.'}), 403
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        id_autorizacion = int(payload.get('id_autorizacion')) if payload.get('id_autorizacion') else None
    except (TypeError, ValueError):
        return jsonify({'error': 'validation_error', 'mensaje': 'Autorizacion invalida.'}), 400
    ok, autorizacion = validar_autorizacion(id_autorizacion, 'anular_venta')
    if not ok:
        return jsonify({'error': 'autorizacion_requerida', 'mensaje': str(autorizacion)}), 403
    try:
        pedido = anular_venta_gastronomica(
            cliente_id,
            pedido_id,
            current_user.id_usuario,
            motivo=payload.get('motivo'),
            id_autorizacion=getattr(autorizacion, 'id_autorizacion', None),
        )
    except ValueError as exc:
        if str(exc) == 'Pedido no encontrado.':
            return jsonify({'error': 'not_found'}), 404
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': pedido.to_dict()})
