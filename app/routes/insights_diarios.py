from flask import Blueprint, jsonify, request, url_for
from flask_login import current_user, login_required

from app import db
from app.services.ia_backoffice.daily_insights import generar_insights_diarios
from app.services.ia_backoffice.security import es_usuario_root, puede_usar_asistente_ia


insights_diarios_bp = Blueprint('insights_diarios', __name__, url_prefix='/insights-diarios')
PREF_VISTO_FECHA = 'daily_insights_seen_on'


def _primer_item(insight: dict, key: str) -> dict:
    source = insight.get('source_payload') if isinstance(insight, dict) else {}
    data = source.get('data') if isinstance(source, dict) else {}
    items = data.get(key) if isinstance(data, dict) else []
    return items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}


def _texto_limpio(value) -> str:
    return str(value or '').strip()


def _enlace_insight(insight: dict) -> dict | None:
    tool = _texto_limpio(insight.get('source_tool') if isinstance(insight, dict) else '')

    if tool == 'reparaciones_fallas_frecuentes':
        falla = _texto_limpio(_primer_item(insight, 'fallas').get('falla'))
        if not falla:
            return None
        return {
            'url': url_for('reparaciones.listar', q=falla),
            'label': 'Ver reparaciones filtradas',
            'tab_title': 'Reparaciones',
            'tab_icon': 'fas fa-tools',
        }

    if tool == 'clientes_top_valor':
        cliente = _primer_item(insight, 'clientes')
        cliente_id = cliente.get('id_cliente')
        if cliente_id:
            return {
                'url': url_for('clientes.detalle', id=cliente_id),
                'label': 'Ver ficha del cliente',
                'tab_title': 'Cliente',
                'tab_icon': 'fas fa-user',
            }
        nombre = _texto_limpio(cliente.get('nombre'))
        if nombre:
            return {
                'url': url_for('clientes.listar', buscar=nombre),
                'label': 'Ver clientes filtrados',
                'tab_title': 'Clientes',
                'tab_icon': 'fas fa-users',
            }

    if tool in {'ventas_top_productos', 'inventario_productos_baja_rotacion', 'inventario_productos_reponer'}:
        producto = _primer_item(insight, 'productos')
        nombre = _texto_limpio(producto.get('nombre') or producto.get('codigo'))
        if not nombre:
            return None
        return {
            'url': url_for('productos.listar', buscar=nombre, sort='stock', dir='asc'),
            'label': 'Ver producto filtrado',
            'tab_title': 'Productos',
            'tab_icon': 'fas fa-box-open',
        }

    return None


def _agregar_enlaces(payload: dict) -> dict:
    insights = payload.get('insights') if isinstance(payload, dict) else []
    if not isinstance(insights, list):
        return payload
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        enlace = _enlace_insight(insight)
        if enlace:
            insight['enlace'] = enlace
    return payload


def _bloqueo(status: int = 403):
    return jsonify({
        'ok': False,
        'error': 'sin_permisos',
        'mensaje': 'No tienes permiso para usar los insights diarios.',
    }), status


def _fecha_vista(usuario) -> str:
    try:
        return usuario.get_preferencia(PREF_VISTO_FECHA, '') or ''
    except Exception:
        return ''


@insights_diarios_bp.route('/api/hoy')
@login_required
def api_hoy():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo()
    usar_ia = (request.args.get('usar_ia') or '1').strip().lower() not in {'0', 'false', 'no'}
    preview = (request.args.get('preview') or '').strip() == '1' and (
        es_usuario_root(current_user) or getattr(current_user, 'es_admin', lambda: False)()
    )
    payload = generar_insights_diarios(current_user, usar_ia=usar_ia)
    _agregar_enlaces(payload)
    payload['ok'] = True
    payload['visto'] = False if preview else _fecha_vista(current_user) == payload['fecha']
    payload['pendientes'] = 0 if payload['visto'] else len(payload.get('insights') or [])
    payload['preview'] = preview
    return jsonify(payload)


@insights_diarios_bp.route('/api/marcar-visto', methods=['POST'])
@login_required
def api_marcar_visto():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo()
    data = request.get_json(silent=True) or {}
    fecha = (data.get('fecha') or '').strip()
    if not fecha:
        fecha = generar_insights_diarios(current_user, usar_ia=False)['fecha']
    current_user.set_preferencia(PREF_VISTO_FECHA, fecha)
    db.session.commit()
    return jsonify({'ok': True, 'fecha': fecha})
