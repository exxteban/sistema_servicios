"""API de la casilla de consentimiento para recibir mensajes, llamada desde el POS al guardar (BI-04)."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.bi.consentimiento import registrar_casilla
from gastronomia.services.permisos import PERMISO_POS, requiere_permiso_gastronomia

gastronomia_bi_consentimiento_api_bp = Blueprint('gastronomia_bi_consentimiento_api', __name__)


@gastronomia_bi_consentimiento_api_bp.route('/bi/consentimiento', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def registrar():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'error': 'gastronomia_no_activa'}), 403
    data = request.get_json(silent=True) or {}
    try:
        resultado = registrar_casilla(cliente_id, data.get('celular'), data.get('acepta') is True)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'estado': resultado})
