"""
Rutas de WhatsApp:
- Webhook (verificacion + recepcion de mensajes)
- Endpoints para panel de asesor (online/offline, responder, devolver, cerrar)
- Endpoints admin (configuracion, metricas)
"""
import json
import os
import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, current_app, flash, render_template, redirect, url_for
from flask_login import login_required, current_user

from app import db
from app.models import Usuario
from app.models.crm_contacto import CrmContacto
from app.models.crm_nota_interna import CrmNotaInterna
from app.models.whatsapp import (
    WhatsAppConversacion, WhatsAppMensaje, WhatsAppConfiguracion,
    WhatsAppEstadoAsesor, WhatsAppAsignacionConversacion
)
from app.services.whatsapp.webhook_handler import procesar_webhook
from app.services.whatsapp.conversacion_manager import enviar_mensaje_asesor
from app.services.whatsapp.inbox_service import (
    build_advisor_inbox_payload,
    get_conversation_origin_meta,
)
from app.services.whatsapp.contexto_service import bloquear_reingreso_bandeja
from app.services.whatsapp.asignacion_service import (
    aceptar_conversacion, devolver_conversacion, cerrar_conversacion, transferir_conversacion,
    toggle_online, heartbeat, verificar_timeouts, tomar_conversacion, get_heartbeat_policy
)
from app.services.system_modules import CLAVE_MODULO_WHATSAPP, system_module_enabled

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint('whatsapp', __name__)


def _modulo_whatsapp_activo() -> bool:
    return system_module_enabled(CLAVE_MODULO_WHATSAPP, default=True)


@whatsapp_bp.before_request
def _require_whatsapp_conversaciones_permiso():
    endpoint = (request.endpoint or '')
    if endpoint in ('whatsapp.webhook_verify', 'whatsapp.webhook_receive'):
        return None
    if not current_user.is_authenticated:
        return None
    if not _modulo_whatsapp_activo():
        mensaje = 'El modulo de WhatsApp esta desactivado.'
        wants_json = (
            request.path.startswith('/whatsapp/asesor/')
            or request.path.startswith('/whatsapp/admin/')
            or request.is_json
            or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
        )
        if wants_json:
            return jsonify({'error': 'Modulo desactivado', 'mensaje': mensaje, 'modulo': 'whatsapp'}), 403
        flash(mensaje, 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.tiene_permiso('whatsapp_conversaciones'):
        return None

    modo_demo = bool(getattr(current_user, 'modo_demo', False))
    mensaje = 'Modo demo: esta acción está deshabilitada' if modo_demo else 'No tienes permiso para acceder a WhatsApp Conversaciones'
    wants_json = (
        request.path.startswith('/whatsapp/asesor/')
        or request.path.startswith('/whatsapp/admin/')
        or request.is_json
        or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
    )
    if wants_json:
        return jsonify({'error': 'Sin permisos', 'mensaje': mensaje, 'permiso_requerido': 'whatsapp_conversaciones', 'modo_demo': modo_demo}), 403
    return render_template('errores/403.html'), 403


# ─── Panel Asesor (Página HTML) ─────────────────────────────────────────────

@whatsapp_bp.route('/panel', methods=['GET'])
@login_required
def panel_asesor():
    """Página principal del panel de asesor WhatsApp."""
    return render_template('whatsapp/panel_asesor.html', es_monitor=False)


@whatsapp_bp.route('/monitor', methods=['GET'])
@login_required
def monitor_ia():
    """Página del Monitor IA (solo admin/supervisor)."""
    if not current_user.es_admin() and not current_user.es_supervisor():
        return render_template('errores/403.html'), 403
    return redirect(url_for('crm.monitor_ia'))


# ─── Webhook ────────────────────────────────────────────────────────────────

@whatsapp_bp.route('/webhook', methods=['GET'])
def webhook_verify():
    """Verificacion del webhook por Meta (challenge)."""
    mode = request.args.get('hub.mode', '')
    token = request.args.get('hub.verify_token', '')
    challenge = request.args.get('hub.challenge', '')

    verify_token = (
        os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN')
        or os.environ.get('WHATSAPP_VERIFY_TOKEN')
        or ''
    )

    if mode == 'subscribe' and token == verify_token:
        logger.info("Webhook verificado correctamente")
        return challenge, 200
    else:
        logger.warning(f"Webhook verificacion fallida: mode={mode}")
        return 'Forbidden', 403


@whatsapp_bp.route('/webhook', methods=['POST'])
def webhook_receive():
    """Recibe mensajes entrantes de WhatsApp."""
    enabled_raw = os.environ.get('WHATSAPP_ENABLED')
    if enabled_raw is None:
        token_present = bool((os.environ.get('WHATSAPP_ACCESS_TOKEN') or os.environ.get('WHATSAPP_TOKEN') or '').strip())
        phone_present = bool((os.environ.get('WHATSAPP_PHONE_NUMBER_ID') or os.environ.get('WHATSAPP_PHONE_ID') or '').strip())
        enabled = token_present and phone_present
    else:
        enabled = enabled_raw.strip().lower() in ('1', 'true', 'yes')

    if not enabled:
        logger.info("Webhook recibido pero WHATSAPP_ENABLED esta desactivado")
        return jsonify({'status': 'disabled'}), 200

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'status': 'no_payload'}), 400

    try:
        resultado = procesar_webhook(payload)
        logger.info(f"Webhook procesado: {resultado.get('procesados', 0)} mensajes")
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}", exc_info=True)
        # Siempre retornar 200 para que Meta no reintente
        return jsonify({'status': 'error'}), 200


# ─── Panel Asesor ───────────────────────────────────────────────────────────

@whatsapp_bp.route('/asesor/online', methods=['POST'])
@login_required
def asesor_toggle_online():
    """Toggle online/offline del asesor."""
    data = request.get_json(silent=True) or {}
    online = data.get('online', True)
    resultado = toggle_online(current_user.id_usuario, online)
    return jsonify(resultado)


@whatsapp_bp.route('/asesor/heartbeat', methods=['POST'])
@login_required
def asesor_heartbeat():
    """Heartbeat del asesor (cada 30s)."""
    verificar_timeouts()
    resultado = heartbeat(current_user.id_usuario)
    return jsonify(resultado)


@whatsapp_bp.route('/asesor/conversaciones', methods=['GET'])
@login_required
def asesor_conversaciones():
    """Lista conversaciones asignadas al asesor actual."""
    verificar_timeouts()
    inbox_payload = build_advisor_inbox_payload(current_user.id_usuario)

    # Estado del asesor
    estado = WhatsAppEstadoAsesor.query.get(current_user.id_usuario)

    return jsonify({
        'conversaciones': inbox_payload['conversaciones'],
        'cola': inbox_payload['cola'],
        'estado_asesor': {
            'online': estado.online if estado else False,
            'conversaciones_activas': estado.conversaciones_activas if estado else 0,
            'max_conversaciones': estado.max_conversaciones if estado else 5,
        }
    })


@whatsapp_bp.route('/asesor/conversacion/<int:id_conv>/tomar', methods=['POST'])
@login_required
def asesor_tomar_conversacion(id_conv):
    resultado = tomar_conversacion(id_conv, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify(resultado)
    return jsonify(resultado), 400


@whatsapp_bp.route('/asesor/conversacion/<int:id_conv>/mensajes', methods=['GET'])
@login_required
def asesor_mensajes(id_conv):
    """Obtiene mensajes de una conversacion (para el panel del asesor)."""
    # Verificar que la conversacion esta asignada a este asesor
    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv,
        id_asesor=current_user.id_usuario
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()

    if not asig:
        return jsonify({'error': 'No tenes acceso a esta conversacion'}), 403

    conv = asig.conversacion or WhatsAppConversacion.query.get_or_404(id_conv)

    mensajes = WhatsAppMensaje.query.filter_by(
        id_conversacion=id_conv
    ).order_by(WhatsAppMensaje.created_at.asc()).limit(100).all()

    resultado = []
    for msg in mensajes:
        resultado.append({
            'id': msg.id,
            'direccion': msg.direccion,
            'remitente': msg.remitente,
            'contenido': msg.contenido,
            'tipo_mensaje': msg.tipo_mensaje,
            'created_at': msg.created_at.isoformat(),
            'wa_status': msg.wa_status,
        })

    contacto = CrmContacto.query.filter_by(telefono=conv.telefono).first()

    notas_conversacion = CrmNotaInterna.query.filter_by(
        id_conversacion=id_conv
    ).order_by(CrmNotaInterna.created_at.asc()).all()

    notas_contacto = []
    if contacto:
        notas_contacto = CrmNotaInterna.query.filter_by(
            id_contacto=contacto.id,
            id_conversacion=None
        ).order_by(CrmNotaInterna.created_at.asc()).all()

    return jsonify({
        'conversacion': {
            'id': conv.id,
            'telefono': conv.telefono,
            'nombre_contacto': conv.nombre_contacto or conv.telefono,
            'modo': conv.modo,
            'activa': conv.activa,
            **get_conversation_origin_meta(conv),
        },
        'mensajes': resultado,
        'notas_conversacion': [n.to_dict() for n in notas_conversacion],
        'notas_contacto': [n.to_dict() for n in notas_contacto],
    })


def _obtener_o_crear_contacto(telefono: str, nombre: str | None = None) -> CrmContacto:
    contacto = CrmContacto.query.filter_by(telefono=telefono).first()
    if not contacto:
        contacto = CrmContacto(telefono=telefono, nombre=nombre)
        db.session.add(contacto)
        db.session.flush()
    return contacto


@whatsapp_bp.route('/asesor/conversacion/<int:id_conv>/notas', methods=['POST'])
@login_required
def asesor_agregar_nota(id_conv):
    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv,
        id_asesor=current_user.id_usuario
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()

    if not asig:
        return jsonify({'error': 'No tenes acceso a esta conversacion'}), 403

    conv = asig.conversacion or WhatsAppConversacion.query.get_or_404(id_conv)
    data = request.get_json(silent=True) or {}
    contenido = (data.get('contenido') or '').strip()
    scope = (data.get('scope') or 'conversacion')
    scope = (str(scope).strip().lower() if scope is not None else 'conversacion')

    if scope not in ('conversacion', 'contacto'):
        scope = 'conversacion'

    if not contenido:
        return jsonify({'error': 'contenido requerido'}), 400

    contacto = CrmContacto.query.filter_by(telefono=conv.telefono).first()
    if not contacto:
        contacto = _obtener_o_crear_contacto(conv.telefono, conv.nombre_contacto)

    nota = CrmNotaInterna(
        id_contacto=contacto.id,
        id_conversacion=(None if scope == 'contacto' else id_conv),
        id_usuario=current_user.id_usuario,
        contenido=contenido,
    )
    db.session.add(nota)
    db.session.commit()

    return jsonify({'ok': True, 'nota': nota.to_dict(), 'scope': scope}), 201


@whatsapp_bp.route('/asesor/conversacion/<int:id_conv>/responder', methods=['POST'])
@login_required
def asesor_responder(id_conv):
    """El asesor envia un mensaje al cliente."""
    data = request.get_json(silent=True) or {}
    texto = (data.get('texto') or '').strip()
    if not texto:
        return jsonify({'error': 'Texto requerido'}), 400

    resultado = enviar_mensaje_asesor(id_conv, texto, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify(resultado)
    return jsonify(resultado), 400


@whatsapp_bp.route('/asesor/asignacion/<int:id_asig>/aceptar', methods=['POST'])
@login_required
def asesor_aceptar(id_asig):
    """El asesor acepta una conversacion."""
    resultado = aceptar_conversacion(id_asig, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify(resultado)
    return jsonify(resultado), 400


@whatsapp_bp.route('/asesor/asignacion/<int:id_asig>/devolver', methods=['POST'])
@login_required
def asesor_devolver(id_asig):
    data = request.get_json(silent=True) or {}
    destino = (data.get('destino') or 'cola_asesores').strip().lower()
    if destino not in ('cola_asesores', 'pool_ia'):
        return jsonify({'ok': False, 'error': 'Destino inválido'}), 400

    if destino == 'pool_ia':
        asignacion = WhatsAppAsignacionConversacion.query.get(id_asig)
        if not asignacion:
            return jsonify({'ok': False, 'error': 'Asignacion no encontrada'}), 400
        if asignacion.id_asesor != current_user.id_usuario:
            return jsonify({'ok': False, 'error': 'Esta conversacion no te fue asignada'}), 400
        if asignacion.estado not in ('pendiente', 'activa'):
            return jsonify({'ok': False, 'error': f'La conversacion ya esta en estado: {asignacion.estado}'}), 400

        asignacion.estado = 'devuelta'
        asignacion.cerrado_at = datetime.utcnow()
        asignacion.motivo_devolucion = 'manual_pool_ia'

        estado = WhatsAppEstadoAsesor.query.get(current_user.id_usuario)
        if estado and (estado.conversaciones_activas or 0) > 0:
            estado.conversaciones_activas -= 1

        if asignacion.conversacion:
            asignacion.conversacion.modo = 'bot'
            bloquear_reingreso_bandeja(asignacion.conversacion, 'manual_pool_ia')

        db.session.commit()
        return jsonify({'ok': True, 'destino': 'pool_ia'})

    resultado = devolver_conversacion(id_asig, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify({'ok': True, 'destino': 'cola_asesores'})
    return jsonify(resultado), 400


@whatsapp_bp.route('/asesor/asignacion/<int:id_asig>/cerrar', methods=['POST'])
@login_required
def asesor_cerrar(id_asig):
    """El asesor cierra la conversacion."""
    resultado = cerrar_conversacion(id_asig, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify(resultado)
    return jsonify(resultado), 400


@whatsapp_bp.route('/asesor/asesores-online', methods=['GET'])
@login_required
def asesor_asesores_online():
    verificar_timeouts()
    heartbeat_policy = get_heartbeat_policy()
    estados_query = WhatsAppEstadoAsesor.query.filter(
        WhatsAppEstadoAsesor.online == True,
    )
    if heartbeat_policy.get('enabled', True):
        limite_heartbeat = datetime.utcnow() - timedelta(seconds=heartbeat_policy.get('timeout_segundos', 60))
        estados_query = estados_query.filter(
            WhatsAppEstadoAsesor.ultimo_ping.isnot(None),
            WhatsAppEstadoAsesor.ultimo_ping >= limite_heartbeat,
        )
    estados = estados_query.all()

    ids = [e.id_usuario for e in estados if e.id_usuario != current_user.id_usuario]
    usuarios = {}
    if ids:
        for u in Usuario.query.filter(Usuario.id_usuario.in_(ids), Usuario.activo == True).all():
            usuarios[u.id_usuario] = u

    items = []
    for e in estados:
        if e.id_usuario == current_user.id_usuario:
            continue
        u = usuarios.get(e.id_usuario)
        if not u:
            continue
        items.append({
            'id_usuario': u.id_usuario,
            'nombre': u.nombre_completo,
            'conversaciones_activas': int(e.conversaciones_activas or 0),
            'max_conversaciones': int(e.max_conversaciones or 0),
            'disponible': int(e.conversaciones_activas or 0) < int(e.max_conversaciones or 0),
        })

    items.sort(key=lambda x: (not x.get('disponible', False), x.get('conversaciones_activas', 0), x.get('nombre', '')))
    return jsonify({'asesores': items})


@whatsapp_bp.route('/asesor/asignacion/<int:id_asig>/transferir', methods=['POST'])
@login_required
def asesor_transferir(id_asig):
    data = request.get_json(silent=True) or {}
    id_asesor = data.get('id_asesor')
    try:
        id_asesor = int(id_asesor)
    except (TypeError, ValueError):
        id_asesor = None

    if not id_asesor:
        return jsonify({'ok': False, 'error': 'id_asesor requerido'}), 400

    resultado = transferir_conversacion(id_asig, current_user.id_usuario, id_asesor)
    if resultado.get('ok'):
        return jsonify(resultado)
    return jsonify(resultado), 400


# ─── Admin ──────────────────────────────────────────────────────────────────

@whatsapp_bp.route('/admin/dashboard', methods=['GET'])
@login_required
def admin_dashboard():
    """Metricas del sistema WhatsApp."""
    if not current_user.es_admin() and not current_user.es_supervisor():
        return jsonify({'error': 'Sin permisos'}), 403

    total_conv = WhatsAppConversacion.query.count()
    conv_activas = WhatsAppConversacion.query.filter_by(activa=True).count()
    total_mensajes = WhatsAppMensaje.query.count()
    asesores_online = WhatsAppEstadoAsesor.query.filter_by(online=True).count()
    conv_en_cola = WhatsAppConversacion.query.filter_by(modo='derivacion', activa=True).count()

    return jsonify({
        'total_conversaciones': total_conv,
        'conversaciones_activas': conv_activas,
        'total_mensajes': total_mensajes,
        'asesores_online': asesores_online,
        'conversaciones_en_cola': conv_en_cola,
    })

@whatsapp_bp.route('/admin/ia_config', methods=['GET'])
@login_required
def admin_ia_config():
    if not current_user.es_admin():
        return jsonify({'error': 'Sin permisos'}), 403

    from app.services.ia.gpt_service import _get_client_and_meta, _get_model_config

    client, meta = _get_client_and_meta()
    cfg = _get_model_config()

    return jsonify({
        'ok': True,
        'ia': {
            'enabled_raw': meta.get('ai_enabled_raw', ''),
            'provider': meta.get('provider', ''),
            'model': cfg.get('model', ''),
            'base_url': meta.get('base_url', ''),
            'base_url_source': meta.get('base_url_source', ''),
            'key_source': meta.get('key_source', ''),
            'client_ready': bool(client is not None),
        }
    })


@whatsapp_bp.route('/admin/configuracion', methods=['GET'])
@login_required
def admin_get_config():
    """Obtiene toda la configuracion editable."""
    if not current_user.es_admin():
        return jsonify({'error': 'Sin permisos'}), 403

    configs = WhatsAppConfiguracion.query.order_by(
        WhatsAppConfiguracion.categoria, WhatsAppConfiguracion.clave
    ).all()

    return jsonify({
        'configuracion': [{
            'id': c.id,
            'clave': c.clave,
            'valor': c.valor,
            'descripcion': c.descripcion,
            'categoria': c.categoria,
        } for c in configs]
    })


@whatsapp_bp.route('/admin/configuracion', methods=['POST'])
@login_required
def admin_set_config():
    """Actualiza una configuracion."""
    if not current_user.es_admin():
        return jsonify({'error': 'Sin permisos'}), 403

    data = request.get_json(silent=True) or {}
    clave = (data.get('clave') or '').strip()
    valor = (data.get('valor') or '').strip()

    if not clave or not valor:
        return jsonify({'error': 'Clave y valor requeridos'}), 400

    config = WhatsAppConfiguracion.query.filter_by(clave=clave).first()
    if config:
        config.valor = valor
        config.updated_at = datetime.utcnow()
    else:
        config = WhatsAppConfiguracion(
            clave=clave,
            valor=valor,
            descripcion=data.get('descripcion', ''),
            categoria=data.get('categoria', 'general'),
        )
        db.session.add(config)

    db.session.commit()
    return jsonify({'ok': True})


@whatsapp_bp.route('/admin/conversaciones', methods=['GET'])
@login_required
def admin_conversaciones():
    """Lista todas las conversaciones (historial)."""
    if not current_user.es_admin() and not current_user.es_supervisor():
        return jsonify({'error': 'Sin permisos'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = WhatsAppConversacion.query.order_by(
        WhatsAppConversacion.ultima_actividad.desc()
    )

    # Filtros opcionales
    modo = request.args.get('modo')
    if modo:
        query = query.filter_by(modo=modo)

    activa = request.args.get('activa')
    if activa is not None:
        query = query.filter_by(activa=activa.lower() in ('1', 'true'))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'conversaciones': [{
            'id': c.id,
            'telefono': c.telefono,
            'nombre_contacto': c.nombre_contacto,
            'modo': c.modo,
            'activa': c.activa,
            'ultima_actividad': c.ultima_actividad.isoformat() if c.ultima_actividad else None,
            'inicio_sesion': c.inicio_sesion.isoformat() if c.inicio_sesion else None,
        } for c in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
    })


@whatsapp_bp.route('/admin/timeouts', methods=['POST'])
@login_required
def admin_verificar_timeouts():
    """Ejecuta verificacion de timeouts manualmente."""
    if not current_user.es_admin():
        return jsonify({'error': 'Sin permisos'}), 403

    verificar_timeouts()
    return jsonify({'ok': True})


# ─── Monitor IA ─────────────────────────────────────────────────────────────

@whatsapp_bp.route('/admin/ia_conversaciones', methods=['GET'])
@login_required
def admin_ia_conversaciones():
    """Lista paginada de conversaciones para el monitor de IA (admin/supervisor)."""
    if not current_user.es_admin() and not current_user.es_supervisor():
        return jsonify({'error': 'Sin permisos'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = WhatsAppConversacion.query.order_by(
        WhatsAppConversacion.ultima_actividad.desc()
    )

    modo = request.args.get('modo')
    if modo and modo != 'todos':
        query = query.filter_by(modo=modo)

    activa = request.args.get('activa')
    if activa is not None and activa != '':
        query = query.filter_by(activa=activa.lower() in ('1', 'true'))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    resultado = []
    for c in pagination.items:
        ultimo_msg = WhatsAppMensaje.query.filter_by(
            id_conversacion=c.id, direccion='entrante'
        ).order_by(WhatsAppMensaje.created_at.desc()).first()

        total_msgs = WhatsAppMensaje.query.filter_by(id_conversacion=c.id).count()
        tool_calls_count = WhatsAppMensaje.query.filter(
            WhatsAppMensaje.id_conversacion == c.id,
            WhatsAppMensaje.tool_call.isnot(None),
            WhatsAppMensaje.contenido != '[tool_result]',
        ).count()

        resultado.append({
            'id': c.id,
            'telefono': c.telefono,
            'nombre_contacto': c.nombre_contacto or c.telefono,
            'modo': c.modo,
            'activa': c.activa,
            'ultima_actividad': c.ultima_actividad.isoformat() if c.ultima_actividad else None,
            'inicio_sesion': c.inicio_sesion.isoformat() if c.inicio_sesion else None,
            'ultimo_mensaje': ultimo_msg.contenido[:100] if ultimo_msg else '',
            'ultimo_mensaje_at': ultimo_msg.created_at.isoformat() if ultimo_msg else None,
            'total_mensajes': total_msgs,
            'tool_calls_count': tool_calls_count,
            **_web_bot_badge(c),
        })

    return jsonify({
        'conversaciones': resultado,
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
        'per_page': per_page,
    })


@whatsapp_bp.route('/admin/ia_conversacion/<int:id_conv>/mensajes', methods=['GET'])
@login_required
def admin_ia_conversacion_mensajes(id_conv):
    """Mensajes, tool_calls y contexto JSON de una conversacion (admin/supervisor)."""
    if not current_user.es_admin() and not current_user.es_supervisor():
        return jsonify({'error': 'Sin permisos'}), 403

    conv = WhatsAppConversacion.query.get(id_conv)
    if not conv:
        return jsonify({'error': 'Conversacion no encontrada'}), 404

    mensajes = WhatsAppMensaje.query.filter_by(
        id_conversacion=id_conv
    ).order_by(WhatsAppMensaje.created_at.asc()).all()

    resultado = []
    for msg in mensajes:
        item = {
            'id': msg.id,
            'direccion': msg.direccion,
            'remitente': msg.remitente,
            'contenido': msg.contenido,
            'tipo_mensaje': msg.tipo_mensaje,
            'created_at': msg.created_at.isoformat(),
            'wa_status': msg.wa_status,
            'tool_call': None,
        }
        if msg.tool_call:
            try:
                import json as _json
                item['tool_call'] = _json.loads(msg.tool_call)
            except Exception:
                item['tool_call'] = {'raw': msg.tool_call}
        resultado.append(item)

    import json as _json
    try:
        contexto = _json.loads(conv.contexto or '{}')
    except Exception:
        contexto = {}

    return jsonify({
        'conversacion': {
            'id': conv.id,
            'telefono': conv.telefono,
            'nombre_contacto': conv.nombre_contacto or conv.telefono,
            'modo': conv.modo,
            'activa': conv.activa,
            'inicio_sesion': conv.inicio_sesion.isoformat() if conv.inicio_sesion else None,
            'ultima_actividad': conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
            **_web_bot_badge(conv),
        },
        'mensajes': resultado,
        'contexto': contexto,
    })
