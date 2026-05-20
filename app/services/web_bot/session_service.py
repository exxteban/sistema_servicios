"""
Servicios de sesión para el bot web de tienda.
"""
import json
import re
import secrets
from datetime import datetime

from app import db
from app.models.cliente import Cliente
from app.models.crm_contacto import CrmContacto
from app.models.tienda import TiendaConfig
from app.models.web_bot import WebBotMensaje, WebBotSesion
from app.services.asistente.context_builder import build_store_assistant_context, parse_session_metadata
from app.services.asistente.prompt_builder import build_web_bot_prompt
from app.services.asistente.response_engine import generar_dialogo_asistente
from app.services.asistente.tools_adapter import WEB_BOT_TOOLS, execute_web_tool
from app.services.web_bot.crm_sync_service import sync_session_messages_to_crm
from app.services.web_bot.handoff_service import ensure_handoff_whatsapp, registrar_mensaje_cliente_desde_web
from app.services.web_bot.safety_policy import (
    COMMERCIAL_REDIRECT_REPLY,
    evaluate_user_message_guardrail,
    enforce_assistant_output_guardrail,
)
from app.services.whatsapp.asignacion_service import distribuir_conversaciones_pendientes
from app.services.web_bot.session_policy import is_session_expired
from app.services.web_bot.serializer import build_bot_config
from app.utils.phone_utils import formatear_telefono_display, normalizar_telefono


EMAIL_RE = re.compile(r'([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})', re.IGNORECASE)
PHONE_RE = re.compile(r'(\+?\d[\d\s-]{7,}\d)')
ALLOWED_ORIGINS = {'tienda_widget', 'robot_link'}


def get_store_config(slug: str) -> TiendaConfig | None:
    normalized_slug = (slug or '').strip().lower()
    if not normalized_slug:
        return None
    return TiendaConfig.query.filter_by(slug=normalized_slug, activa=True).first()


def _build_session_token() -> str:
    return secrets.token_urlsafe(32)


def _safe_origin(origen: str | None) -> str:
    value = (origen or 'tienda_widget').strip().lower()
    return value if value in ALLOWED_ORIGINS else 'tienda_widget'


def _capture_contact_data(session: WebBotSesion, texto: str):
    text = (texto or '').strip()
    if not text:
        return
    email_match = EMAIL_RE.search(text)
    if email_match and not session.email_visitante:
        session.email_visitante = email_match.group(1).strip()
    phone_match = PHONE_RE.search(text)
    if phone_match and not session.telefono_visitante:
        session.telefono_visitante = phone_match.group(1).strip()


def _save_session_metadata(session: WebBotSesion, metadata: dict):
    session.metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)


def _extract_normalized_phone(texto: str) -> str | None:
    candidates = [(texto or '').strip()]
    match = PHONE_RE.search(texto or '')
    if match:
        candidates.append(match.group(1).strip())
    for value in candidates:
        telefono = normalizar_telefono(value)
        if telefono:
            return telefono
    return None


def _find_known_visitor(telefono: str) -> dict:
    digits = re.sub(r'\D', '', telefono or '')
    crm = CrmContacto.query.filter_by(telefono=telefono).first()
    if crm:
        return {
            'nombre': (crm.nombre or '').strip(),
            'id_cliente': crm.id_cliente,
            'crm_contacto_id': crm.id,
            'source': 'crm',
        }
    conditions = [Cliente.telefono == telefono]
    if digits:
        conditions.append(Cliente.telefono == digits)
        conditions.append(Cliente.telefono.ilike(f'%{digits}%'))
    cliente = (
        Cliente.query
        .filter(Cliente.activo == True, db.or_(*conditions))
        .order_by(Cliente.id_cliente.desc())
        .first()
    )
    if not cliente:
        return {
            'nombre': '',
            'id_cliente': None,
            'crm_contacto_id': None,
            'source': '',
        }
    return {
        'nombre': (cliente.nombre or '').strip(),
        'id_cliente': cliente.id_cliente,
        'crm_contacto_id': None,
        'source': 'cliente',
    }


def _sync_web_contact(session: WebBotSesion, telefono: str, identity: dict, metadata: dict):
    now = datetime.utcnow()
    crm_contacto = None
    crm_contacto_id = identity.get('crm_contacto_id')
    if crm_contacto_id:
        crm_contacto = CrmContacto.query.get(crm_contacto_id)
    if crm_contacto is None:
        crm_contacto = CrmContacto.query.filter_by(telefono=telefono).first()
    if crm_contacto is None:
        crm_contacto = CrmContacto(
            telefono=telefono,
            nombre=identity.get('nombre') or session.nombre_visitante or '',
            id_cliente=identity.get('id_cliente'),
            primer_contacto=now,
            ultimo_contacto=now,
            total_conversaciones=1,
        )
        db.session.add(crm_contacto)
        db.session.flush()
    else:
        crm_contacto.ultimo_contacto = now
        crm_contacto.total_conversaciones = max(1, int(crm_contacto.total_conversaciones or 0))
        if identity.get('id_cliente') and not crm_contacto.id_cliente:
            crm_contacto.id_cliente = identity['id_cliente']
        if session.nombre_visitante and not crm_contacto.nombre:
            crm_contacto.nombre = session.nombre_visitante
    visitante = {
        'telefono': telefono,
        'telefono_display': formatear_telefono_display(telefono),
        'telefono_confirmado': True,
        'nombre': session.nombre_visitante or '',
        'id_cliente': identity.get('id_cliente'),
        'crm_contacto_id': crm_contacto.id,
        'source': identity.get('source') or 'web',
    }
    metadata['visitante'] = visitante
    _save_session_metadata(session, metadata)


def _append_message(
    session: WebBotSesion,
    direccion: str,
    remitente: str,
    contenido: str,
    tipo_mensaje: str = 'text',
    tool_call: dict | None = None,
) -> WebBotMensaje:
    message = WebBotMensaje(
        id_sesion=session.id_sesion,
        direccion=direccion,
        remitente=remitente,
        tipo_mensaje=tipo_mensaje,
        contenido=contenido,
        tool_call_json=json.dumps(tool_call, ensure_ascii=False, default=str) if tool_call else None,
        created_at=datetime.utcnow(),
    )
    session.ultima_actividad = datetime.utcnow()
    db.session.add(message)
    return message


def _initial_greeting(config: TiendaConfig) -> str:
    return build_bot_config(config)['greeting']


def get_session_for_store(
    config: TiendaConfig,
    session_token: str,
    *,
    include_expired: bool = False,
) -> WebBotSesion | None:
    token = (session_token or '').strip()
    if not token:
        return None
    session = WebBotSesion.query.filter_by(
        session_token=token,
        slug_tienda=config.slug,
        id_cliente=config.id_cliente,
    ).first()
    if not session:
        return None
    if not include_expired and is_session_expired(session):
        return None
    return session


def get_session_status_for_store(config: TiendaConfig, session_token: str) -> tuple[WebBotSesion | None, str]:
    token = (session_token or '').strip()
    if not token:
        return None, 'missing'
    session = get_session_for_store(config, token, include_expired=True)
    if not session:
        return None, 'missing'
    if is_session_expired(session):
        return session, 'expired'
    return session, 'ok'


def create_or_recover_session(config: TiendaConfig, origen: str, session_token: str | None = None) -> WebBotSesion:
    existing = get_session_for_store(config, session_token or '')
    if existing:
        existing.ultima_actividad = datetime.utcnow()
        return existing

    session = WebBotSesion(
        id_cliente=config.id_cliente,
        slug_tienda=config.slug,
        session_token=_build_session_token(),
        origen=_safe_origin(origen),
        estado='bot',
        metadata_json=json.dumps({'visitante': {'telefono_confirmado': False}}, ensure_ascii=False),
        ultima_actividad=datetime.utcnow(),
    )
    db.session.add(session)
    db.session.flush()
    _append_message(session, 'saliente', 'bot', _initial_greeting(config))
    db.session.commit()
    return session


def _build_history_for_assistant(session: WebBotSesion) -> list[dict]:
    history = []
    messages = session.mensajes.order_by(WebBotMensaje.created_at.asc(), WebBotMensaje.id_mensaje.asc()).all()
    for message in messages:
        if message.remitente == 'cliente':
            history.append({'role': 'user', 'content': message.contenido})
            continue
        if message.remitente == 'bot' and message.tipo_mensaje == 'text':
            history.append({'role': 'assistant', 'content': message.contenido})
            continue
        if not message.tool_call_json:
            continue
        try:
            payload = json.loads(message.tool_call_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if payload.get('raw_message'):
            history.append(payload['raw_message'])
        elif payload.get('tool_result') is not None:
            history.append({
                'role': 'tool',
                'tool_call_id': payload.get('tool_call_id') or '',
                'content': json.dumps(payload.get('tool_result'), ensure_ascii=False, default=str),
            })
    return history[-16:]


def _ensure_phone_onboarding(config: TiendaConfig, session: WebBotSesion, metadata: dict, clean_message: str) -> dict | None:
    visitante = metadata.get('visitante') if isinstance(metadata.get('visitante'), dict) else {}
    if visitante.get('telefono_confirmado') and session.telefono_visitante:
        return None

    telefono = _extract_normalized_phone(clean_message)
    if not telefono:
        texto = (
            f'Antes de seguir con {config.nombre_tienda or "la tienda"}, pasame tu número de teléfono '
            'así el asesor ve quién escribe y puede continuar la atención.'
        )
        _append_message(session, 'saliente', 'bot', texto)
        return {'texto': texto, 'acciones': []}

    identity = _find_known_visitor(telefono)
    session.telefono_visitante = telefono
    if identity.get('nombre') and not session.nombre_visitante:
        session.nombre_visitante = identity['nombre']
    if identity.get('id_cliente') and session.id_cliente != identity['id_cliente']:
        metadata['visitante_cliente_id'] = identity['id_cliente']
    _sync_web_contact(session, telefono, identity, metadata)

    nombre = (session.nombre_visitante or '').strip()
    telefono_display = formatear_telefono_display(telefono)
    if nombre:
        texto = (
            f'Gracias, {nombre}. Ya te identifiqué con el {telefono_display}. '
            'Contame qué producto o consulta querés resolver y si necesitás asesor te paso con uno.'
        )
    else:
        texto = (
            f'Gracias, ya registré tu número {telefono_display}. '
            'Contame qué producto o consulta querés resolver y si necesitás asesor te paso con uno.'
        )
    _append_message(session, 'saliente', 'bot', texto)
    return {'texto': texto, 'acciones': []}


def process_user_message(config: TiendaConfig, session: WebBotSesion, mensaje: str) -> dict:
    clean_message = (mensaje or '').strip()
    if not clean_message:
        return {
            'texto': 'Escribime qué producto o dato de la tienda querés consultar.',
            'acciones': [],
        }

    metadata = parse_session_metadata(session.metadata_json)
    _capture_contact_data(session, clean_message)
    _append_message(session, 'entrante', 'cliente', clean_message)
    sync_session_messages_to_crm(session, metadata=metadata)

    if registrar_mensaje_cliente_desde_web(session, clean_message):
        _save_session_metadata(session, metadata)
        db.session.commit()
        return {
            'texto': '',
            'acciones': [],
        }

    guardrail = evaluate_user_message_guardrail(clean_message, metadata)
    if guardrail.get('blocked'):
        texto = guardrail.get('reply') or COMMERCIAL_REDIRECT_REPLY
        if guardrail.get('should_block_session'):
            session.estado = 'blocked'
        _append_message(session, 'saliente', 'bot', texto)
        sync_session_messages_to_crm(session, metadata=metadata)
        _save_session_metadata(session, metadata)
        db.session.commit()
        return {
            'texto': texto,
            'acciones': [],
        }

    onboarding_result = _ensure_phone_onboarding(config, session, metadata, clean_message)
    if onboarding_result:
        sync_session_messages_to_crm(session, metadata=metadata)
        db.session.commit()
        return onboarding_result

    assistant_context = build_store_assistant_context(config, metadata=metadata)
    assistant_context['sesion'] = {
        'origen': session.origen,
        'estado': session.estado,
    }
    assistant_context['visitante'] = metadata.get('visitante') or {}
    system_prompt = build_web_bot_prompt(assistant_context)
    history = _build_history_for_assistant(session)

    def _tool_executor(nombre: str, argumentos: dict):
        return execute_web_tool(
            nombre,
            argumentos,
            {
                'config': config,
                'slug': config.slug,
                'session': session,
                'assistant_context': assistant_context,
            },
        )

    result = generar_dialogo_asistente(
        historial=history,
        contexto_ia=assistant_context,
        system_prompt=system_prompt,
        tools=WEB_BOT_TOOLS,
        tool_executor=_tool_executor,
    )

    for event in result.get('tool_events', []):
        if event.get('kind') == 'assistant_tool_call':
            _append_message(
                session,
                'saliente',
                'bot',
                '[tool_call]',
                tipo_mensaje='tool',
                tool_call={'raw_message': event.get('raw_message')},
            )
            continue
        _append_message(
            session,
            'saliente',
            'sistema',
            '[tool_result]',
            tipo_mensaje='tool',
            tool_call={
                'tool_call_id': event.get('tool_call_id'),
                'tool_name': event.get('tool_name'),
                'tool_result': event.get('tool_result'),
            },
        )

    safe_text = enforce_assistant_output_guardrail(result.get('texto') or '')
    _append_message(session, 'saliente', 'bot', safe_text)
    handoff_action = next(
        (
            action for action in (result.get('acciones') or [])
            if (action.get('type') or '').strip().lower() == 'handoff_whatsapp'
        ),
        None,
    )
    if handoff_action and (config.telefono_whatsapp or '').strip():
        ensure_handoff_whatsapp(
            session,
            config,
            (handoff_action.get('motivo') or 'usuario_solicita_whatsapp').strip(),
        )
        distribuir_conversaciones_pendientes(commit=False)
    sync_session_messages_to_crm(session, metadata=metadata)
    _save_session_metadata(session, metadata)
    db.session.commit()
    return {
        'texto': safe_text,
        'acciones': result.get('acciones') or [],
    }
