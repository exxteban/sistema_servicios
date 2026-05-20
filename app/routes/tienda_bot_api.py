"""
API pública del bot web de la tienda.
"""
import os
from datetime import datetime
from threading import Lock

from flask import Blueprint, jsonify, request

from app import csrf, db
from app.services.web_bot.handoff_service import (
    build_whatsapp_url,
    ensure_handoff_whatsapp,
)
from app.services.web_bot.serializer import build_bot_config, serialize_session
from app.services.whatsapp.asignacion_service import distribuir_conversaciones_pendientes
from app.services.web_bot.session_service import (
    create_or_recover_session,
    get_session_status_for_store,
    get_store_config,
    process_user_message,
)


tienda_bot_api_bp = Blueprint('tienda_bot_api', __name__)
BOT_RATE_STATE = {}
BOT_RATE_LOCK = Lock()


def _resolve_store_or_404(slug: str):
    config = get_store_config(slug)
    if not config:
        return None, (jsonify({'error': 'tienda_no_encontrada'}), 404)
    return config, None


def _client_ip() -> str:
    forwarded = (request.headers.get('X-Forwarded-For') or '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()[:64]
    return (request.remote_addr or '').strip()[:64] or '-'


def _bot_rate_limit_settings(action: str) -> tuple[int, int]:
    defaults = {
        'create_session': (600, 12),
        'send_message': (300, 30),
        'handoff': (600, 6),
    }
    window_default, max_default = defaults.get(action, (300, 20))
    prefix = f'WEB_BOT_RATE_LIMIT_{action.upper()}'
    window_seconds = int(os.environ.get(f'{prefix}_WINDOW_SECONDS', str(window_default)))
    max_requests = int(os.environ.get(f'{prefix}_MAX', str(max_default)))
    return max(1, window_seconds), max(1, max_requests)


def _bot_rate_key(slug: str, action: str) -> str:
    user_agent = (request.headers.get('User-Agent', '') or '').strip().lower()[:120]
    return f'{action}|{slug}|{_client_ip()}|{user_agent}'


def _is_bot_rate_limited(slug: str, action: str) -> tuple[bool, int]:
    window_seconds, max_requests = _bot_rate_limit_settings(action)
    now_ts = int(datetime.utcnow().timestamp())
    min_ts = now_ts - window_seconds
    key = _bot_rate_key(slug, action)
    with BOT_RATE_LOCK:
        if len(BOT_RATE_STATE) > 5000:
            for state_key, values in list(BOT_RATE_STATE.items()):
                keep = [value for value in values if value > min_ts]
                if keep:
                    BOT_RATE_STATE[state_key] = keep
                else:
                    BOT_RATE_STATE.pop(state_key, None)
        bucket = [ts for ts in BOT_RATE_STATE.get(key, []) if ts > min_ts]
        if len(bucket) >= max_requests:
            retry_after = max(1, window_seconds - (now_ts - min(bucket)))
            BOT_RATE_STATE[key] = bucket
            return True, retry_after
        bucket.append(now_ts)
        BOT_RATE_STATE[key] = bucket
        return False, 0


def _rate_limit_response(slug: str, action: str):
    rate_limited, retry_after = _is_bot_rate_limited(slug, action)
    if not rate_limited:
        return None
    response = jsonify({'error': 'demasiadas_solicitudes', 'retry_after': retry_after})
    response.headers['Retry-After'] = str(retry_after)
    response.headers['Cache-Control'] = 'no-store'
    return response, 429


@tienda_bot_api_bp.route('/<slug>/bot/config', methods=['GET'])
def bot_config(slug: str):
    config, error_response = _resolve_store_or_404(slug)
    if error_response:
        return error_response
    return jsonify(build_bot_config(config))


@tienda_bot_api_bp.route('/<slug>/bot/session', methods=['POST'])
@csrf.exempt
def bot_create_session(slug: str):
    config, error_response = _resolve_store_or_404(slug)
    if error_response:
        return error_response
    limited_response = _rate_limit_response(slug, 'create_session')
    if limited_response:
        return limited_response

    payload = request.get_json(silent=True) or {}
    session = create_or_recover_session(
        config,
        origen=payload.get('origen'),
        session_token=payload.get('session_token'),
    )
    return jsonify(serialize_session(session, build_bot_config(config)))


@tienda_bot_api_bp.route('/<slug>/bot/session/<session_token>', methods=['GET'])
def bot_get_session(slug: str, session_token: str):
    config, error_response = _resolve_store_or_404(slug)
    if error_response:
        return error_response

    session, session_status = get_session_status_for_store(config, session_token)
    if session_status == 'expired':
        return jsonify({'error': 'sesion_expirada'}), 410
    if not session:
        return jsonify({'error': 'sesion_no_encontrada'}), 404
    return jsonify(serialize_session(session, build_bot_config(config)))


@tienda_bot_api_bp.route('/<slug>/bot/session/<session_token>/messages', methods=['POST'])
@csrf.exempt
def bot_send_message(slug: str, session_token: str):
    config, error_response = _resolve_store_or_404(slug)
    if error_response:
        return error_response
    limited_response = _rate_limit_response(slug, 'send_message')
    if limited_response:
        return limited_response

    session, session_status = get_session_status_for_store(config, session_token)
    if session_status == 'expired':
        return jsonify({'error': 'sesion_expirada'}), 410
    if not session:
        return jsonify({'error': 'sesion_no_encontrada'}), 404

    payload = request.get_json(silent=True) or {}
    mensaje = (payload.get('mensaje') or '').strip()
    if not mensaje:
        return jsonify({'error': 'mensaje_invalido'}), 400

    result = process_user_message(config, session, mensaje)
    return jsonify({
        'estado': session.estado,
        'respuesta': {'texto': result['texto']},
        'acciones': result.get('acciones') or [],
        'historial': serialize_session(session, build_bot_config(config))['historial'],
    })


@tienda_bot_api_bp.route('/<slug>/bot/session/<session_token>/handoff', methods=['POST'])
@csrf.exempt
def bot_create_handoff(slug: str, session_token: str):
    config, error_response = _resolve_store_or_404(slug)
    if error_response:
        return error_response
    limited_response = _rate_limit_response(slug, 'handoff')
    if limited_response:
        return limited_response

    session, session_status = get_session_status_for_store(config, session_token)
    if session_status == 'expired':
        return jsonify({'error': 'sesion_expirada'}), 410
    if not session:
        return jsonify({'error': 'sesion_no_encontrada'}), 404
    if (session.estado or '').strip().lower() == 'blocked':
        return jsonify({'error': 'sesion_bloqueada'}), 403

    if not (config.telefono_whatsapp or '').strip():
        return jsonify({'error': 'whatsapp_no_configurado'}), 400
    payload = request.get_json(silent=True) or {}
    motivo = (payload.get('motivo') or 'usuario_solicita_whatsapp').strip()
    handoff, _created = ensure_handoff_whatsapp(session, config, motivo)
    distribuir_conversaciones_pendientes(commit=False)
    db.session.commit()
    return jsonify({
        'estado': session.estado,
        'handoff_token': handoff.handoff_token,
        'whatsapp_url': build_whatsapp_url(config.telefono_whatsapp, handoff.texto_prefill or ''),
        'mensaje': 'Tu consulta ya quedó en cola para asesor. También podés seguir por WhatsApp para continuar desde tu celular.',
    })
