"""
CRM - Panel Asesor
Tomar, responder, devolver, cerrar conversaciones + notas internas + plantillas
"""
import logging
from datetime import datetime

from flask import render_template, request, jsonify, redirect, url_for, abort
from flask_login import login_required, current_user

from app import db
from app.models.whatsapp import (
    WhatsAppConversacion, WhatsAppMensaje, WhatsAppEstadoAsesor,
    WhatsAppAsignacionConversacion, WhatsAppConversacionEvento
)
from app.models.crm_contacto import CrmContacto
from app.models.crm_nota_interna import CrmNotaInterna
from app.models.crm_plantilla import CrmPlantilla
from app.services.whatsapp.conversacion_manager import enviar_mensaje_asesor
from app.services.whatsapp.auditoria_service import serializar_evento, registrar_evento_conversacion
from app.services.whatsapp.contexto_service import bloquear_reingreso_bandeja
from app.services.whatsapp.inbox_service import should_surface_bot_conversation_in_queue
from app.services.whatsapp.asesor_panel_service import (
    count_store_web_histories,
    get_paginated_conversation_timeline,
    paginate_store_web_histories,
    serialize_panel_conversation,
)
from app.services.whatsapp.asignacion_service import (
    aceptar_conversacion, devolver_conversacion, cerrar_conversacion,
    toggle_online, heartbeat, verificar_timeouts, tomar_conversacion
)
from app.routes.crm import crm_bp

logger = logging.getLogger(__name__)


def _usuario_control():
    if current_user.es_admin():
        return True
    if current_user.tiene_permiso('crm_operar_como_asesor'):
        return False
    if current_user.es_supervisor():
        return True
    return current_user.tiene_permiso('ver_auditoria')


def _bloquear_roles_no_asesor(permitir_solo_lectura=False):
    if _usuario_control():
        if permitir_solo_lectura and request.method == 'GET':
            return None
        if request.path.startswith('/crm/api/') or request.is_json:
            return jsonify({'ok': False, 'error': 'Perfil de control: solo lectura en panel asesor'}), 403
        return redirect(url_for('crm.dashboard'))
    return None


def _obtener_asignacion_activa(id_conv: int, *, permitir_control_lectura: bool = False):
    conv = db.session.get(WhatsAppConversacion, id_conv)
    if not conv:
        abort(404)
    if permitir_control_lectura and _usuario_control() and request.method == 'GET':
        return conv, conv.asignacion

    query = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv,
        id_asesor=current_user.id_usuario,
    )
    if request.method == 'GET':
        asig = query.order_by(
            WhatsAppAsignacionConversacion.asignado_at.desc(),
            WhatsAppAsignacionConversacion.id.desc(),
        ).first()
    else:
        asig = query.filter(
            WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
        ).first()
    if not asig:
        return None, None
    return conv, asig


@crm_bp.route('/asesor', methods=['GET'])
@login_required
def panel_asesor():
    """Panel principal del asesor CRM."""
    bloqueo = _bloquear_roles_no_asesor(permitir_solo_lectura=True)
    if bloqueo is not None:
        return bloqueo
    plantillas = CrmPlantilla.query.filter_by(activa=True).order_by(
        CrmPlantilla.categoria, CrmPlantilla.orden, CrmPlantilla.titulo
    ).all()
    return render_template(
        'crm/asesor/panel.html',
        plantillas=[p.to_dict() for p in plantillas],
        puede_operar_panel=not _usuario_control(),
    )


# ─── Conversaciones del asesor ───────────────────────────────────────────────

@crm_bp.route('/api/asesor/conversaciones', methods=['GET'])
@login_required
def api_conversaciones_asesor():
    """Conversaciones asignadas al asesor actual + pendientes."""
    from sqlalchemy import desc
    bloqueo = _bloquear_roles_no_asesor(permitir_solo_lectura=True)
    if bloqueo is not None:
        return bloqueo
    verificar_timeouts()
    es_control = _usuario_control()

    asignaciones_q = WhatsAppAsignacionConversacion.query
    if es_control:
        asignaciones_visibles = asignaciones_q.order_by(
            desc(WhatsAppAsignacionConversacion.asignado_at),
            desc(WhatsAppAsignacionConversacion.id),
        ).all()
    else:
        asignaciones_visibles = asignaciones_q.filter(
            WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
        ).filter_by(
            id_asesor=current_user.id_usuario
        ).all()

    mis_ids = {a.id_conversacion for a in asignaciones_visibles}
    mis_convs = WhatsAppConversacion.query.filter(
        WhatsAppConversacion.id.in_(mis_ids)
    ).all() if mis_ids else []

    estado = db.session.get(WhatsAppEstadoAsesor, current_user.id_usuario)
    online = estado.online if estado else False
    pendientes = []

    if online or es_control:
        pendientes_derivacion = WhatsAppConversacion.query.filter_by(activa=True, modo='derivacion').order_by(
            desc(WhatsAppConversacion.ultima_actividad)
        ).all()
        bot_candidatas = WhatsAppConversacion.query.filter_by(activa=True, modo='bot').order_by(
            desc(WhatsAppConversacion.ultima_actividad)
        ).limit(200).all()

        ids_pendientes = set()
        for c in pendientes_derivacion:
            if c.id in mis_ids:
                continue
            pendientes.append(c)
            ids_pendientes.add(c.id)

        for c in bot_candidatas:
            if c.id in mis_ids or c.id in ids_pendientes:
                continue
            if should_surface_bot_conversation_in_queue(c):
                pendientes.append(c)
                ids_pendientes.add(c.id)

    conv_map = {c.id: c for c in mis_convs}
    mis_serializadas = [
        serialize_panel_conversation(
            conv_map[a.id_conversacion],
            estado_asignacion=a.estado,
            asesor_nombre=a.asesor.nombre_completo if a.asesor else None,
        )
        for a in asignaciones_visibles
        if a.id_conversacion in conv_map
    ]
    historiales_total = count_store_web_histories(excluded_ids=mis_ids) if es_control else 0

    return jsonify({
        'pendientes': [serialize_panel_conversation(c) for c in pendientes],
        'mis_conversaciones': mis_serializadas,
        'historiales_web': [],
        'historiales_total': historiales_total,
        'total_pendientes': len(pendientes),
        'panel_mode': 'control' if es_control else 'asesor',
        'estado_asesor': {
            'online': online,
            'conversaciones_activas': int(estado.conversaciones_activas or 0) if estado else 0,
            'max_conversaciones': int(estado.max_conversaciones or 0) if estado else 5,
        }
    })


@crm_bp.route('/api/asesor/historiales-web', methods=['GET'])
@login_required
def api_historiales_web():
    bloqueo = _bloquear_roles_no_asesor(permitir_solo_lectura=True)
    if bloqueo is not None:
        return bloqueo
    if not _usuario_control():
        return jsonify({'ok': False, 'error': 'Solo disponible en modo control'}), 403

    asignaciones_visibles = WhatsAppAsignacionConversacion.query.order_by(
        WhatsAppAsignacionConversacion.asignado_at.desc(),
        WhatsAppAsignacionConversacion.id.desc(),
    ).all()
    excluded_ids = {a.id_conversacion for a in asignaciones_visibles}
    payload = paginate_store_web_histories(
        excluded_ids=excluded_ids,
        page=request.args.get('page', 1, type=int),
        per_page=request.args.get('per_page', 20, type=int),
        search=request.args.get('q', '', type=str),
        estado=request.args.get('estado', 'activas', type=str),
        periodo=request.args.get('periodo', '30', type=str),
    )
    return jsonify(payload)


@crm_bp.route('/api/asesor/conversacion/<int:id_conv>/mensajes', methods=['GET'])
@login_required
def api_mensajes_conversacion(id_conv):
    """Historial de mensajes de una conversación."""
    from sqlalchemy import asc
    bloqueo = _bloquear_roles_no_asesor(permitir_solo_lectura=True)
    if bloqueo is not None:
        return bloqueo
    conv, _asig = _obtener_asignacion_activa(id_conv, permitir_control_lectura=True)
    if not conv:
        return jsonify({'ok': False, 'error': 'No tenés acceso a esta conversación'}), 403
    timeline_limit = request.args.get('limit', type=int)
    timeline_cursor = request.args.get('cursor', '', type=str)
    if timeline_limit:
        timeline = get_paginated_conversation_timeline(
            id_conv,
            limit=timeline_limit,
            cursor=timeline_cursor,
        )
        notas = CrmNotaInterna.query.filter_by(id_conversacion=id_conv).order_by(
            CrmNotaInterna.created_at
        ).all()
        return jsonify({
            'conversacion': {
                'id': conv.id,
                'telefono': conv.telefono,
                'nombre': conv.nombre_contacto or conv.telefono,
                'modo': conv.modo,
                'activa': conv.activa,
            },
            'items': timeline['items'],
            'has_more': timeline['has_more'],
            'next_cursor': timeline['next_cursor'],
            'notas': [n.to_dict() for n in notas],
        })

    mensajes = conv.mensajes.order_by(asc(WhatsAppMensaje.created_at)).all()
    eventos = conv.eventos.order_by(asc(WhatsAppConversacionEvento.created_at)).all()
    notas = CrmNotaInterna.query.filter_by(id_conversacion=id_conv).order_by(
        CrmNotaInterna.created_at
    ).all()

    return jsonify({
        'conversacion': {
            'id': conv.id,
            'telefono': conv.telefono,
            'nombre': conv.nombre_contacto or conv.telefono,
            'modo': conv.modo,
            'activa': conv.activa,
        },
        'mensajes': [
            {
                'id': m.id,
                'direccion': m.direccion,
                'remitente': m.remitente,
                'contenido': m.contenido,
                'tipo': m.tipo_mensaje,
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'asesor': m.asesor.nombre_completo if m.asesor else None,
            }
            for m in mensajes
        ],
        'eventos': [serializar_evento(e) for e in eventos],
        'notas': [n.to_dict() for n in notas],
    })


# ─── Acciones sobre conversaciones ───────────────────────────────────────────

@crm_bp.route('/api/asesor/tomar/<int:id_conv>', methods=['POST'])
@login_required
def api_tomar_conversacion(id_conv):
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    resultado = tomar_conversacion(id_conv, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify({'ok': True, 'id_asignacion': resultado.get('id_asignacion')})
    return jsonify({'ok': False, 'error': resultado.get('error', 'No se pudo tomar la conversación')}), 400


@crm_bp.route('/api/asesor/aceptar/<int:id_conv>', methods=['POST'])
@login_required
def api_aceptar_conversacion(id_conv):
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv,
        id_asesor=current_user.id_usuario
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()
    if not asig:
        return jsonify({'ok': False, 'error': 'No tenés una asignación activa para esta conversación'}), 400
    resultado = aceptar_conversacion(asig.id, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': resultado.get('error', 'No se pudo aceptar')}), 400


@crm_bp.route('/api/asesor/devolver/<int:id_conv>', methods=['POST'])
@login_required
def api_devolver_conversacion(id_conv):
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv,
        id_asesor=current_user.id_usuario
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()
    if not asig:
        return jsonify({'ok': False, 'error': 'No tenés una asignación activa para esta conversación'}), 400
    data = request.get_json(silent=True) or {}
    destino = (data.get('destino') or 'cola_asesores').strip().lower()
    if destino not in ('cola_asesores', 'pool_ia'):
        return jsonify({'ok': False, 'error': 'Destino inválido'}), 400

    if destino == 'pool_ia':
        asig.estado = 'devuelta'
        asig.cerrado_at = datetime.utcnow()
        asig.motivo_devolucion = 'manual_pool_ia'

        estado = db.session.get(WhatsAppEstadoAsesor, current_user.id_usuario)
        if estado and (estado.conversaciones_activas or 0) > 0:
            estado.conversaciones_activas -= 1

        if asig.conversacion:
            asig.conversacion.modo = 'bot'
            bloquear_reingreso_bandeja(asig.conversacion, 'manual_pool_ia')
            registrar_evento_conversacion(asig.conversacion, 'asesor_devolvio_conversacion', actor='asesor', id_usuario=current_user.id_usuario, detalle={'motivo': 'manual_pool_ia'})

        db.session.commit()
        return jsonify({'ok': True, 'destino': 'pool_ia'})

    resultado = devolver_conversacion(asig.id, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify({'ok': True, 'destino': 'cola_asesores'})
    return jsonify({'ok': False, 'error': resultado.get('error', 'No se pudo devolver')}), 400


@crm_bp.route('/api/asesor/cerrar/<int:id_conv>', methods=['POST'])
@login_required
def api_cerrar_conversacion(id_conv):
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv,
        id_asesor=current_user.id_usuario
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()
    if not asig:
        return jsonify({'ok': False, 'error': 'No tenés una asignación activa para esta conversación'}), 400
    resultado = cerrar_conversacion(asig.id, current_user.id_usuario)
    if resultado.get('ok'):
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': resultado.get('error', 'No se pudo cerrar')}), 400


@crm_bp.route('/api/asesor/responder/<int:id_conv>', methods=['POST'])
@login_required
def api_responder(id_conv):
    """Enviar mensaje como asesor."""
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    data = request.get_json(silent=True) or {}
    mensaje = (data.get('mensaje') or '').strip()
    if not mensaje:
        return jsonify({'ok': False, 'error': 'mensaje vacío'}), 400

    conv, _asig = _obtener_asignacion_activa(id_conv)
    if not conv:
        return jsonify({'ok': False, 'error': 'No tenés una asignación activa para esta conversación'}), 403
    try:
        resultado = enviar_mensaje_asesor(conv.id, mensaje, current_user.id_usuario)
        if resultado.get('ok'):
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': resultado.get('error', 'No se pudo enviar')}), 400
    except Exception as e:
        logger.exception(f"Error enviando mensaje asesor conv={id_conv}")
        return jsonify({'ok': False, 'error': str(e)}), 500


# ─── Notas internas en conversación ──────────────────────────────────────────

@crm_bp.route('/api/asesor/conversacion/<int:id_conv>/notas', methods=['POST'])
@login_required
def api_nota_conversacion(id_conv):
    """Agregar nota interna a una conversación."""
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    conv, _asig = _obtener_asignacion_activa(id_conv)
    if not conv:
        return jsonify({'ok': False, 'error': 'No tenés una asignación activa para esta conversación'}), 403
    data = request.get_json(silent=True) or {}
    contenido = (data.get('contenido') or '').strip()
    if not contenido:
        return jsonify({'error': 'contenido requerido'}), 400

    contacto = CrmContacto.query.filter_by(telefono=conv.telefono).first()
    if not contacto:
        contacto = _obtener_o_crear_contacto(conv.telefono, conv.nombre_contacto)

    nota = CrmNotaInterna(
        id_contacto=contacto.id,
        id_conversacion=id_conv,
        id_usuario=current_user.id_usuario,
        contenido=contenido,
    )
    db.session.add(nota)
    db.session.commit()
    return jsonify({'ok': True, 'nota': nota.to_dict()}), 201


# ─── Estado online/offline ────────────────────────────────────────────────────

@crm_bp.route('/api/asesor/online', methods=['POST'])
@login_required
def api_toggle_online():
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    data = request.get_json(silent=True) or {}
    online = data.get('online', True)
    return jsonify(toggle_online(current_user.id_usuario, online))


@crm_bp.route('/api/asesor/heartbeat', methods=['POST'])
@login_required
def api_heartbeat():
    bloqueo = _bloquear_roles_no_asesor()
    if bloqueo is not None:
        return bloqueo
    verificar_timeouts()
    return jsonify(heartbeat(current_user.id_usuario))


# ─── Plantillas ───────────────────────────────────────────────────────────────

@crm_bp.route('/api/plantillas', methods=['GET'])
@login_required
def api_plantillas():
    """Lista de plantillas activas."""
    plantillas = CrmPlantilla.query.filter_by(activa=True).order_by(
        CrmPlantilla.categoria, CrmPlantilla.orden, CrmPlantilla.titulo
    ).all()
    return jsonify({'plantillas': [p.to_dict() for p in plantillas]})


# ─── Helper ───────────────────────────────────────────────────────────────────

def _obtener_o_crear_contacto(telefono: str, nombre: str | None = None) -> CrmContacto:
    contacto = CrmContacto.query.filter_by(telefono=telefono).first()
    if not contacto:
        contacto = CrmContacto(telefono=telefono, nombre=nombre)
        db.session.add(contacto)
        db.session.flush()
    return contacto
