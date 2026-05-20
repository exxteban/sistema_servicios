"""
CRM - Monitor IA
Historial de tool calls, contexto JSON, actividad del bot
"""
import logging
import json

from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import desc

from app.models.whatsapp import WhatsAppConversacion, WhatsAppMensaje, WhatsAppConversacionEvento
from app.services.whatsapp.auditoria_service import serializar_evento
from app.routes.crm import crm_bp

logger = logging.getLogger(__name__)


def _require_monitor():
    if not current_user.es_admin() and not current_user.es_supervisor():
        abort(403)


@crm_bp.route('/monitor', methods=['GET'])
@login_required
def monitor_ia():
    """Página del Monitor IA."""
    _require_monitor()
    return render_template('crm/monitor/index.html')


@crm_bp.route('/api/monitor/conversaciones', methods=['GET'])
@login_required
def api_monitor_conversaciones():
    """Lista de conversaciones recientes con actividad del bot."""
    _require_monitor()
    page = request.args.get('page', type=int) or request.args.get('pagina', 1, type=int)
    per_page = min(request.args.get('per_page', type=int) or request.args.get('por_pagina', 20, type=int), 100)

    query = WhatsAppConversacion.query.order_by(WhatsAppConversacion.ultima_actividad.desc())

    modo = request.args.get('modo')
    if modo and modo != 'todos':
        query = query.filter_by(modo=modo)

    activa = request.args.get('activa')
    if activa is not None and activa != '':
        query = query.filter_by(activa=str(activa).lower() in ('1', 'true'))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    resultado = []
    for c in pagination.items:
        ultimo_msg = WhatsAppMensaje.query.filter_by(
            id_conversacion=c.id
        ).order_by(WhatsAppMensaje.created_at.desc(), WhatsAppMensaje.id.desc()).first()

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
            'ultimo_mensaje_remitente': ultimo_msg.remitente if ultimo_msg else None,
            'total_mensajes': total_msgs,
            'tool_calls_count': tool_calls_count,
        })

    return jsonify({
        'conversaciones': resultado,
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
        'per_page': per_page,
        'items': resultado,
        'pagina': page,
        'paginas': pagination.pages,
    })


@crm_bp.route('/api/monitor/conversacion/<int:id_conv>', methods=['GET'])
@login_required
def api_monitor_detalle(id_conv):
    """Detalle completo de una conversación para el monitor."""
    _require_monitor()
    from sqlalchemy import asc
    conv = WhatsAppConversacion.query.get_or_404(id_conv)
    mensajes = conv.mensajes.order_by(asc(WhatsAppMensaje.created_at)).all()
    eventos = conv.eventos.order_by(asc(WhatsAppConversacionEvento.created_at)).all()

    msgs_data = []
    for m in mensajes:
        tool_data = None
        if m.tool_call:
            try:
                tool_data = json.loads(m.tool_call)
            except Exception:
                tool_data = {'raw': m.tool_call}

        msgs_data.append({
            'id': m.id,
            'direccion': m.direccion,
            'remitente': m.remitente,
            'contenido': m.contenido,
            'tipo': m.tipo_mensaje,
            'tool_call': tool_data,
            'wa_status': m.wa_status,
            'created_at': m.created_at.isoformat() if m.created_at else None,
        })

    contexto = _parse_contexto(conv.contexto)
    return jsonify({
        'conversacion': {
            'id': conv.id,
            'telefono': conv.telefono,
            'nombre_contacto': conv.nombre_contacto or conv.telefono,
            'modo': conv.modo,
            'activa': conv.activa,
            'inicio': conv.inicio_sesion.isoformat() if conv.inicio_sesion else None,
            'ultima_actividad': conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
            'mensajes_hora': conv.mensajes_hora,
            'bloqueado_hasta': conv.bloqueado_hasta.isoformat() if conv.bloqueado_hasta else None,
        },
        'mensajes': msgs_data,
        'eventos': [serializar_evento(e) for e in eventos],
        'contexto': contexto,
    })


def _parse_contexto(raw: str) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {'raw': raw}
