"""API de entregas gastronomicas."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.entregas_service import buscar_entregas
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_SALON,
    requiere_permiso_gastronomia,
)


gastronomia_entregas_api_bp = Blueprint('gastronomia_entregas_api', __name__)


@gastronomia_entregas_api_bp.route('/entregas', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA, PERMISO_COCINA, PERMISO_SALON)
def entregas_api():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'error': 'gastronomia_no_activa'}), 403
    data = buscar_entregas(cliente_id, request.args)
    return jsonify({'ok': True, **data})
