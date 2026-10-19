"""API de plantillas de arranque para cargar el menu gastronomico."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.menu_plantillas_service import aplicar_plantilla, crear_promo_sugerida
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


gastronomia_menu_plantillas_api_bp = Blueprint('gastronomia_menu_plantillas_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


@gastronomia_menu_plantillas_api_bp.route('/menu-plantillas/aplicar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def aplicar():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        resultado = aplicar_plantilla(cliente_id, data.get('productos'))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    resultado['promo_creada'] = None
    promo = data.get('promo')
    if isinstance(promo, dict) and _puede_gestionar_promociones():
        resultado['promo_creada'] = crear_promo_sugerida(
            cliente_id,
            str(promo.get('plantilla') or ''),
            str(promo.get('producto') or ''),
        )
    return jsonify({'ok': True, **resultado})


def _puede_gestionar_promociones() -> bool:
    # Mismo criterio que la pestana Promociones de menu_config.
    return bool(current_user.es_admin() or current_user.tiene_permiso('editar_configuracion'))
