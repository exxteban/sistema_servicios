"""API de reportes para Gastronomia."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.permisos import PERMISO_REPORTES, requiere_permiso_gastronomia
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
