"""
CRM - Admin: configuración, métricas, asignaciones, plantillas, etiquetas
"""
import logging
import os
import json
from datetime import datetime, timedelta

from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import func, desc, and_, select, or_

from app import db
from app.models import Usuario
from app.models.whatsapp import (
    WhatsAppConversacion, WhatsAppMensaje, WhatsAppAsignacionConversacion,
    WhatsAppEstadoAsesor, WhatsAppConfiguracion
)
from app.models.crm_contacto import CrmContacto
from app.models.crm_etiqueta import CrmEtiqueta
from app.models.crm_plantilla import CrmPlantilla
from app.routes.crm import crm_bp
from app.services.bot_context import (
    BOT_CONTEXT_CONFIG_KEY,
    BOT_CONTEXT_FIELDS,
    normalize_bot_context,
    load_bot_context,
)
from app.services.whatsapp.asignacion_service import _max_conversaciones

logger = logging.getLogger(__name__)


def _require_admin():
    """Permite acceso a admin/supervisor. El usuario demo puede ver (GET) pero no modificar."""
    from flask import request as _req
    if current_user.es_admin() or current_user.es_supervisor():
        return  # acceso total
    if getattr(current_user, 'modo_demo', False):
        if _req.method == 'GET':
            return  # solo lectura para demo
        abort(403)  # demo no puede escribir
    abort(403)


def _get_config(clave: str) -> WhatsAppConfiguracion | None:
    return WhatsAppConfiguracion.query.filter_by(clave=clave).first()


def _get_config_json(clave: str, default):
    c = _get_config(clave)
    if not c or not c.valor:
        return default
    try:
        return json.loads(c.valor)
    except Exception:
        return default


def _set_config_json(clave: str, payload, descripcion: str = '', categoria: str = 'general'):
    valor = json.dumps(payload, ensure_ascii=False)
    c = _get_config(clave)
    if c:
        c.valor = valor
        c.descripcion = descripcion or c.descripcion
        c.categoria = categoria or c.categoria
        c.updated_at = datetime.utcnow()
    else:
        c = WhatsAppConfiguracion(
            clave=clave,
            valor=valor,
            descripcion=descripcion,
            categoria=categoria,
        )
        db.session.add(c)
    db.session.commit()


def _save_bot_context(payload: dict) -> dict:
    contexto = normalize_bot_context(payload)
    _set_config_json(
        BOT_CONTEXT_CONFIG_KEY,
        contexto,
        descripcion='Contexto operativo compartido para el bot de WhatsApp y el bot web.',
        categoria='general',
    )
    return contexto


def _safe_int(value, default: int, min_value: int | None = None) -> int:
    try:
        n = int(value)
    except Exception:
        n = int(default)
    if min_value is not None and n < min_value:
        return int(min_value)
    return n


def _normalizar_timeout_config(payload, default_minutos: int, default_accion: str) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    return {
        'enabled': bool(payload.get('enabled', True)),
        'minutos': _safe_int(payload.get('minutos', default_minutos), default_minutos, min_value=1),
        'accion': 'reasignar',
    }


def _normalizar_metodo_distribucion(value) -> str:
    raw = '' if value is None else str(value).strip().lower()
    canonical = raw.replace('-', '_').replace(' ', '_')
    aliases = {
        'least_busy': 'least_busy',
        'menor_carga': 'least_busy',
        'menos_carga': 'least_busy',
        'round_robin': 'round_robin',
        'roundrobin': 'round_robin',
        'circular': 'round_robin',
        'rotativa': 'round_robin',
        'distribucion_circular': 'round_robin',
    }
    return aliases.get(canonical, 'least_busy')


def _normalizar_distribucion_config(payload) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    default_max = _safe_int(os.environ.get('WHATSAPP_ASESOR_MAX_CONVERSACIONES', '5'), 5, min_value=1)
    default_heartbeat_min = max(1, (_safe_int(os.environ.get('WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS', '10'), 10, min_value=1) * 2 + 59) // 60)
    heartbeat_min = payload.get('heartbeat_timeout_minutos')
    if heartbeat_min is None and payload.get('heartbeat_timeout_segundos') is not None:
        heartbeat_min = (_safe_int(payload.get('heartbeat_timeout_segundos', 0), default_heartbeat_min * 60, min_value=1) + 59) // 60
    return {
        'enabled': bool(payload.get('enabled', True)),
        'metodo': _normalizar_metodo_distribucion(payload.get('metodo', 'least_busy')),
        'max_conversaciones': _safe_int(payload.get('max_conversaciones', default_max), default_max, min_value=1),
        'heartbeat_auto_offline': bool(payload.get('heartbeat_auto_offline', True)),
        'heartbeat_timeout_minutos': _safe_int(
            heartbeat_min if heartbeat_min is not None else default_heartbeat_min,
            default_heartbeat_min,
            min_value=1
        ),
        'timeout_segundos': _safe_int(payload.get('timeout_segundos', 180), 180, min_value=1),
        'timeout_no_aceptado': _normalizar_timeout_config(
            payload.get('timeout_no_aceptado'),
            default_minutos=5,
            default_accion='reasignar',
        ),
        'timeout_sin_respuesta': _normalizar_timeout_config(
            payload.get('timeout_sin_respuesta'),
            default_minutos=15,
            default_accion='reasignar',
        ),
    }


def _label_metodo_distribucion(value) -> str:
    metodo = _normalizar_metodo_distribucion(value)
    if metodo == 'round_robin':
        return 'Circular / Equitativa (Round Robin)'
    return 'Menor Carga (Least Busy)'


# ─── Dashboard de métricas ────────────────────────────────────────────────────

@crm_bp.route('/admin/dashboard', methods=['GET'])
@login_required
def dashboard():
    """Dashboard de métricas CRM."""
    _require_admin()
    return render_template('crm/admin/dashboard.html')


@crm_bp.route('/api/admin/metricas', methods=['GET'])
@login_required
def api_metricas():
    """API: métricas del CRM."""
    _require_admin()
    dias = request.args.get('dias', 7, type=int)
    desde = datetime.utcnow() - timedelta(days=dias)

    # Conversaciones por día
    convs_por_dia = db.session.query(
        func.date(WhatsAppConversacion.inicio_sesion).label('fecha'),
        func.count(WhatsAppConversacion.id).label('total')
    ).filter(
        WhatsAppConversacion.inicio_sesion >= desde
    ).group_by(
        func.date(WhatsAppConversacion.inicio_sesion)
    ).order_by('fecha').all()

    # Mensajes por modo (bot vs asesor)
    msgs_bot = WhatsAppMensaje.query.filter(
        WhatsAppMensaje.created_at >= desde,
        WhatsAppMensaje.remitente == 'bot',
        WhatsAppMensaje.direccion == 'saliente'
    ).count()

    msgs_asesor = WhatsAppMensaje.query.filter(
        WhatsAppMensaje.created_at >= desde,
        WhatsAppMensaje.remitente == 'asesor',
        WhatsAppMensaje.direccion == 'saliente'
    ).count()

    # Conversaciones activas ahora
    ahora = datetime.utcnow()
    limite_bot = ahora - timedelta(hours=8)
    activas_bot = WhatsAppConversacion.query.filter(
        WhatsAppConversacion.activa == True,
        WhatsAppConversacion.modo == 'bot',
        WhatsAppConversacion.ultima_actividad >= limite_bot,
    ).count()
    activas_asesor = WhatsAppConversacion.query.filter_by(activa=True, modo='asesor').count()
    activas_derivacion = WhatsAppConversacion.query.filter_by(activa=True, modo='derivacion').count()
    activas_cliente = activas_asesor + activas_derivacion

    # Total contactos
    total_contactos = CrmContacto.query.count()

    # Tiempo promedio de respuesta asesor (en minutos)
    tiempo_respuesta = _calcular_tiempo_respuesta(desde)

    # Métricas por asesor (mensajes y tiempo de respuesta)
    por_asesor = _calcular_metricas_por_asesor(desde)
    distribucion_config = _normalizar_distribucion_config(
        _get_config_json('distribucion_config', default={})
    )
    distribucion_metodo = distribucion_config.get('metodo', 'least_busy')

    return jsonify({
        'convs_por_dia': [{'fecha': str(r.fecha), 'total': r.total} for r in convs_por_dia],
        'msgs_bot': msgs_bot,
        'msgs_asesor': msgs_asesor,
        'activas': {
            'bot': activas_bot,
            'cliente': activas_cliente,
            'asesor': activas_asesor,
            'derivacion': activas_derivacion,
            'total': activas_bot + activas_cliente,
        },
        'total_contactos': total_contactos,
        'tiempo_respuesta_promedio_min': tiempo_respuesta,
        'por_asesor': por_asesor,
        'periodo_dias': dias,
        'distribucion_metodo': distribucion_metodo,
        'distribucion_metodo_label': _label_metodo_distribucion(distribucion_metodo),
    })


def _calcular_tiempo_respuesta(desde: datetime) -> float:
    """Calcula tiempo promedio hasta el primer mensaje del asesor (minutos)."""
    try:
        first_msg_at_sq = select(func.min(WhatsAppMensaje.created_at)).where(
            and_(
                WhatsAppMensaje.id_conversacion == WhatsAppAsignacionConversacion.id_conversacion,
                WhatsAppMensaje.remitente == 'asesor',
                WhatsAppMensaje.direccion == 'saliente',
                WhatsAppMensaje.id_asesor == WhatsAppAsignacionConversacion.id_asesor,
                WhatsAppMensaje.created_at >= WhatsAppAsignacionConversacion.asignado_at,
            )
        ).scalar_subquery()

        filas = db.session.query(
            WhatsAppAsignacionConversacion.asignado_at,
            first_msg_at_sq.label('first_msg_at'),
        ).filter(
            WhatsAppAsignacionConversacion.asignado_at >= desde,
            WhatsAppAsignacionConversacion.aceptado_at.isnot(None),
        ).all()

        tiempos = []
        for asignado_at, first_msg_at in filas:
            if not first_msg_at or not asignado_at:
                continue
            delta = (first_msg_at - asignado_at).total_seconds() / 60
            if 0 <= delta <= 1440:
                tiempos.append(delta)

        return round(sum(tiempos) / len(tiempos), 1) if tiempos else 0.0
    except Exception:
        return 0.0


def _calcular_metricas_por_asesor(desde: datetime) -> list:
    """Calcula mensajes enviados y tiempo de respuesta por asesor."""
    try:
        # Agrupar mensajes enviados por asesor
        msgs_por_asesor = db.session.query(
            WhatsAppMensaje.id_asesor,
            func.count(WhatsAppMensaje.id).label('total_mensajes')
        ).filter(
            WhatsAppMensaje.created_at >= desde,
            WhatsAppMensaje.remitente == 'asesor',
            WhatsAppMensaje.direccion == 'saliente',
            WhatsAppMensaje.id_asesor.isnot(None)
        ).group_by(WhatsAppMensaje.id_asesor).all()

        msgs_dict = {r.id_asesor: r.total_mensajes for r in msgs_por_asesor}

        first_msg_at_sq = select(func.min(WhatsAppMensaje.created_at)).where(
            and_(
                WhatsAppMensaje.id_conversacion == WhatsAppAsignacionConversacion.id_conversacion,
                WhatsAppMensaje.remitente == 'asesor',
                WhatsAppMensaje.direccion == 'saliente',
                WhatsAppMensaje.id_asesor == WhatsAppAsignacionConversacion.id_asesor,
                WhatsAppMensaje.created_at >= WhatsAppAsignacionConversacion.asignado_at,
            )
        ).scalar_subquery()

        filas = db.session.query(
            WhatsAppAsignacionConversacion.id_asesor,
            WhatsAppAsignacionConversacion.asignado_at,
            first_msg_at_sq.label('first_msg_at'),
        ).filter(
            WhatsAppAsignacionConversacion.asignado_at >= desde,
            WhatsAppAsignacionConversacion.aceptado_at.isnot(None),
        ).all()

        tiempos_dict = {}
        for id_asesor, asignado_at, first_msg_at in filas:
            if not id_asesor or not asignado_at or not first_msg_at:
                continue
            delta = (first_msg_at - asignado_at).total_seconds() / 60
            if 0 <= delta <= 1440:
                if id_asesor not in tiempos_dict:
                    tiempos_dict[id_asesor] = []
                tiempos_dict[id_asesor].append(delta)

        # Construir lista combinada con nombre_completo del asesor
        Ids_asesores = list(set(list(msgs_dict.keys()) + list(tiempos_dict.keys())))
        
        if not Ids_asesores:
            return []
            
        usuarios = Usuario.query.filter(Usuario.id_usuario.in_(Ids_asesores)).all()
        nombres = {u.id_usuario: u.nombre_completo for u in usuarios}

        resultado = []
        for id_as in Ids_asesores:
            t_list = tiempos_dict.get(id_as, [])
            t_promedio = round(sum(t_list) / len(t_list), 1) if t_list else 0.0
            
            resultado.append({
                'id_asesor': id_as,
                'nombre': nombres.get(id_as, f'Asesor #{id_as}'),
                'mensajes': msgs_dict.get(id_as, 0),
                'tiempo_respuesta_min': t_promedio
            })
            
        # Ordenar por cantidad de mensajes (desc)
        resultado.sort(key=lambda x: x['mensajes'], reverse=True)
        return resultado
        
    except Exception as e:
        logger.error(f"Error calculando métricas por asesor: {e}")
        return []


# ─── Asignación manual ────────────────────────────────────────────────────────

@crm_bp.route('/api/admin/reasignar', methods=['POST'])
@login_required
def api_reasignar():
    """Reasignar conversación a otro asesor."""
    _require_admin()
    data = request.get_json(silent=True) or {}
    id_conv = data.get('id_conversacion')
    id_asesor = data.get('id_asesor')
    if not id_conv or not id_asesor:
        return jsonify({'error': 'id_conversacion e id_asesor requeridos'}), 400

    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conv
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()

    if asig:
        id_asesor_anterior = asig.id_asesor
        asig.id_asesor = id_asesor
        asig.estado = 'pendiente'
        asig.asignado_at = datetime.utcnow()
        asig.aceptado_at = None
        asig.cerrado_at = None
        asig.ultima_respuesta_asesor_at = None
        if id_asesor_anterior != id_asesor:
            estado_origen = db.session.get(WhatsAppEstadoAsesor, id_asesor_anterior)
            if estado_origen and (estado_origen.conversaciones_activas or 0) > 0:
                estado_origen.conversaciones_activas -= 1

            estado_destino = db.session.get(WhatsAppEstadoAsesor, id_asesor)
            if not estado_destino:
                estado_destino = WhatsAppEstadoAsesor(
                    id_usuario=id_asesor,
                    online=False,
                    conversaciones_activas=0,
                    max_conversaciones=_max_conversaciones(),
                )
                db.session.add(estado_destino)
            estado_destino.conversaciones_activas = (estado_destino.conversaciones_activas or 0) + 1
    else:
        asig = WhatsAppAsignacionConversacion(
            id_conversacion=id_conv,
            id_asesor=id_asesor,
            estado='pendiente',
        )
        db.session.add(asig)
        estado_destino = db.session.get(WhatsAppEstadoAsesor, id_asesor)
        if not estado_destino:
            estado_destino = WhatsAppEstadoAsesor(
                id_usuario=id_asesor,
                online=False,
                conversaciones_activas=0,
                max_conversaciones=_max_conversaciones(),
            )
            db.session.add(estado_destino)
        estado_destino.conversaciones_activas = (estado_destino.conversaciones_activas or 0) + 1

    conv = db.session.get(WhatsAppConversacion, id_conv)
    if conv:
        conv.modo = 'derivacion'

    db.session.commit()
    return jsonify({'ok': True})


@crm_bp.route('/api/admin/asesores', methods=['GET'])
@login_required
def api_admin_asesores():
    _require_admin()
    from app.services.whatsapp.asignacion_service import get_heartbeat_policy, verificar_timeouts
    verificar_timeouts()
    heartbeat_policy = get_heartbeat_policy()
    limite_heartbeat = datetime.utcnow() - timedelta(seconds=heartbeat_policy.get('timeout_segundos', 60))
    usuarios = [
        u for u in Usuario.query.filter_by(activo=True).order_by(Usuario.nombre_completo.asc()).all()
        if (not u.es_admin()) and u.tiene_permiso('crm_whatsapp') and u.tiene_permiso('crm_operar_como_asesor')
    ]
    ids = [u.id_usuario for u in usuarios]
    estados = {}
    if ids:
        for e in WhatsAppEstadoAsesor.query.filter(WhatsAppEstadoAsesor.id_usuario.in_(ids)).all():
            estados[e.id_usuario] = e

    items = []
    for u in usuarios:
        est = estados.get(u.id_usuario)
        online = bool(est and est.online)
        if online and heartbeat_policy.get('enabled', True):
            online = bool(est.ultimo_ping and est.ultimo_ping >= limite_heartbeat)
        items.append({
            'id_usuario': u.id_usuario,
            'nombre': u.nombre_completo,
            'online': online,
            'conversaciones_activas': int(est.conversaciones_activas or 0) if est else 0,
            'max_conversaciones': int(est.max_conversaciones or 0) if est else 0,
            'ultimo_ping': est.ultimo_ping.isoformat() if est and est.ultimo_ping else None,
            'conectado_desde': est.conectado_desde.isoformat() if est and est.conectado_desde else None,
        })

    return jsonify({'asesores': items})


# ─── Plantillas ───────────────────────────────────────────────────────────────

@crm_bp.route('/admin/plantillas', methods=['GET'])
@login_required
def admin_plantillas():
    """Página de gestión de plantillas."""
    _require_admin()
    return render_template('crm/admin/plantillas.html')


@crm_bp.route('/api/admin/plantillas', methods=['GET'])
@login_required
def api_admin_plantillas():
    _require_admin()
    plantillas = CrmPlantilla.query.order_by(
        CrmPlantilla.categoria, CrmPlantilla.orden, CrmPlantilla.titulo
    ).all()
    return jsonify({'plantillas': [p.to_dict() for p in plantillas]})


@crm_bp.route('/api/admin/plantillas', methods=['POST'])
@login_required
def api_crear_plantilla():
    _require_admin()
    data = request.get_json(silent=True) or {}
    titulo = (data.get('titulo') or '').strip()
    contenido = (data.get('contenido') or '').strip()
    if not titulo or not contenido:
        return jsonify({'error': 'titulo y contenido requeridos'}), 400

    p = CrmPlantilla(
        titulo=titulo,
        contenido=contenido,
        categoria=data.get('categoria', 'general'),
        orden=data.get('orden', 0),
        id_usuario_creador=current_user.id_usuario,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok': True, 'plantilla': p.to_dict()}), 201


@crm_bp.route('/api/admin/plantillas/<int:id_plantilla>', methods=['PATCH'])
@login_required
def api_editar_plantilla(id_plantilla):
    _require_admin()
    p = CrmPlantilla.query.get_or_404(id_plantilla)
    data = request.get_json(silent=True) or {}
    for campo in ('titulo', 'contenido', 'categoria', 'orden', 'activa'):
        if campo in data:
            setattr(p, campo, data[campo])
    db.session.commit()
    return jsonify({'ok': True, 'plantilla': p.to_dict()})


@crm_bp.route('/api/admin/plantillas/<int:id_plantilla>', methods=['DELETE'])
@login_required
def api_eliminar_plantilla(id_plantilla):
    _require_admin()
    p = CrmPlantilla.query.get_or_404(id_plantilla)
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True})


# ─── Etiquetas ────────────────────────────────────────────────────────────────

@crm_bp.route('/admin/config', methods=['GET'])
@login_required
def admin_config():
    """Página de configuración del CRM."""
    _require_admin()
    
    # Precargar etiquetas por defecto si no están presentes
    etiquetas = CrmEtiqueta.query.order_by(CrmEtiqueta.nombre).all()
    nombres_existentes = {e.nombre.lower() for e in etiquetas}
    etiquetas_default = [
        {'nombre': 'Nuevo Lead', 'color': '#3B82F6', 'descripcion': 'Cliente potencial nuevo'},
        {'nombre': 'En Seguimiento', 'color': '#F59E0B', 'descripcion': 'En proceso de venta'},
        {'nombre': 'Cerrado Ganado', 'color': '#10B981', 'descripcion': 'Venta concretada'},
        {'nombre': 'Cerrado Perdido', 'color': '#EF4444', 'descripcion': 'Venta no concretada'},
        {'nombre': 'Soporte', 'color': '#8B5CF6', 'descripcion': 'Consulta técnica o ayuda'},
        {'nombre': 'Reclamo', 'color': '#DC2626', 'descripcion': 'Queja o reclamo activo'}
    ]
    agregado_etiquetas = False
    for ed in etiquetas_default:
        if ed['nombre'].lower() not in nombres_existentes:
            nueva_etiqueta = CrmEtiqueta(
                nombre=ed['nombre'],
                color=ed['color'],
                descripcion=ed['descripcion']
            )
            db.session.add(nueva_etiqueta)
            agregado_etiquetas = True
    if agregado_etiquetas:
        db.session.commit()
        etiquetas = CrmEtiqueta.query.order_by(CrmEtiqueta.nombre).all()

    # Precargar listas de calidad por defecto
    calidad_listas = _get_config_json('calidad_listas', default=[])
    if not isinstance(calidad_listas, list):
        calidad_listas = []
        
    nombres_listas_existentes = {l.get('nombre', '').lower() for l in calidad_listas if isinstance(l, dict)}
    listas_default = [
        {
            'nombre': 'Positivo / Agradecimiento',
            'color': '#10B981',
            'peso': 5,
            'terminos': ['gracias', 'excelente', 'muy amable', 'perfecto', 'genial', 'me encanta', 'buen servicio', 'solucionado']
        },
        {
            'nombre': 'Negativo / Queja',
            'color': '#EF4444',
            'peso': -10,
            'terminos': ['mal', 'pesimo', 'horrible', 'no funciona', 'harto', 'estafa', 'mentira', 'denuncia', 'incompetente']
        },
        {
            'nombre': 'Insultos / Inapropiado',
            'color': '#991B1B',
            'peso': -20,
            'terminos': ['boludo', 'idiota', 'estupido', 'mierda', 'carajo', 'pelotudo', 'imbecil']
        },
        {
            'nombre': 'Urgencia',
            'color': '#F59E0B',
            'peso': 0,
            'terminos': ['urgente', 'rapido', 'ahora mismo', 'ayuda', 'por favor', 'emergencia', 'ya']
        }
    ]
    
    agregado_listas = False
    for ld in listas_default:
        if ld['nombre'].lower() not in nombres_listas_existentes:
            calidad_listas.append(ld)
            agregado_listas = True
            
    if agregado_listas:
        _set_config_json(
            'calidad_listas',
            calidad_listas,
            descripcion='Listas de palabras clave para análisis de calidad en chats',
            categoria='calidad',
        )

    # Configuración general
    bot_global_enabled = _get_config_json('bot_global_enabled', default=True)
    bot_contexto = load_bot_context()
    
    # Configuración de distribución
    distribucion_config = _normalizar_distribucion_config(
        _get_config_json('distribucion_config', default={})
    )

    return render_template(
        'crm/admin/config_tabs.html',
        etiquetas=[e.to_dict() for e in etiquetas],
        calidad_listas=calidad_listas,
        bot_global_enabled=bot_global_enabled,
        bot_contexto=bot_contexto,
        bot_contexto_campos=BOT_CONTEXT_FIELDS,
        distribucion_config=distribucion_config,
    )


@crm_bp.route('/admin/calidad', methods=['GET'])
@login_required
def admin_calidad():
    _require_admin()
    calidad_listas = _get_config_json('calidad_listas', default=[])
    if not isinstance(calidad_listas, list):
        calidad_listas = []

    nombres_listas_existentes = {l.get('nombre', '').lower() for l in calidad_listas if isinstance(l, dict)}
    listas_default = [
        {'nombre': 'Positivo / Agradecimiento', 'color': '#10B981', 'peso': 5, 'terminos': ['gracias', 'excelente', 'muy amable', 'perfecto', 'genial', 'me encanta', 'buen servicio', 'solucionado']},
        {'nombre': 'Negativo / Queja', 'color': '#EF4444', 'peso': -10, 'terminos': ['mal', 'pesimo', 'horrible', 'no funciona', 'harto', 'estafa', 'mentira', 'denuncia', 'incompetente']},
        {'nombre': 'Insultos / Inapropiado', 'color': '#991B1B', 'peso': -20, 'terminos': ['boludo', 'idiota', 'estupido', 'mierda', 'carajo', 'pelotudo', 'imbecil']},
        {'nombre': 'Urgencia', 'color': '#F59E0B', 'peso': 0, 'terminos': ['urgente', 'rapido', 'ahora mismo', 'ayuda', 'por favor', 'emergencia', 'ya']}
    ]
    agregado_listas = False
    for ld in listas_default:
        if ld['nombre'].lower() not in nombres_listas_existentes:
            calidad_listas.append(ld)
            agregado_listas = True
    if agregado_listas:
        _set_config_json('calidad_listas', calidad_listas, descripcion='Listas de palabras clave para análisis de calidad en chats', categoria='calidad')

    return render_template('crm/admin/calidad.html', calidad_listas=calidad_listas)


@crm_bp.route('/api/admin/calidad/config', methods=['GET'])
@login_required
def api_calidad_config_get():
    _require_admin()
    calidad_listas = _get_config_json('calidad_listas', default=[])
    if not isinstance(calidad_listas, list):
        calidad_listas = []

    nombres_listas_existentes = {l.get('nombre', '').lower() for l in calidad_listas if isinstance(l, dict)}
    listas_default = [
        {'nombre': 'Positivo / Agradecimiento', 'color': '#10B981', 'peso': 5, 'terminos': ['gracias', 'excelente', 'muy amable', 'perfecto', 'genial', 'me encanta', 'buen servicio', 'solucionado']},
        {'nombre': 'Negativo / Queja', 'color': '#EF4444', 'peso': -10, 'terminos': ['mal', 'pesimo', 'horrible', 'no funciona', 'harto', 'estafa', 'mentira', 'denuncia', 'incompetente']},
        {'nombre': 'Insultos / Inapropiado', 'color': '#991B1B', 'peso': -20, 'terminos': ['boludo', 'idiota', 'estupido', 'mierda', 'carajo', 'pelotudo', 'imbecil']},
        {'nombre': 'Urgencia', 'color': '#F59E0B', 'peso': 0, 'terminos': ['urgente', 'rapido', 'ahora mismo', 'ayuda', 'por favor', 'emergencia', 'ya']}
    ]
    agregado_listas = False
    for ld in listas_default:
        if ld['nombre'].lower() not in nombres_listas_existentes:
            calidad_listas.append(ld)
            agregado_listas = True
    if agregado_listas:
        _set_config_json('calidad_listas', calidad_listas, descripcion='Listas de palabras clave para análisis de calidad en chats', categoria='calidad')

    return jsonify({'listas': calidad_listas})


@crm_bp.route('/api/admin/calidad/config', methods=['PUT'])
@login_required
def api_calidad_config_set():
    _require_admin()
    data = request.get_json(silent=True) or {}
    listas = data.get('listas') or []
    if not isinstance(listas, list):
        return jsonify({'error': 'listas inválidas'}), 400

    normalizadas = []
    for item in listas:
        if not isinstance(item, dict):
            continue
        nombre = (item.get('nombre') or '').strip()
        if not nombre:
            continue
        color = (item.get('color') or '#14B8A6').strip() or '#14B8A6'
        terminos = item.get('terminos') or []
        if isinstance(terminos, str):
            terminos = [t.strip() for t in terminos.splitlines()]
        if not isinstance(terminos, list):
            terminos = []
        terminos = [str(t).strip() for t in terminos if str(t).strip()]
        terminos_unicos = []
        seen = set()
        for t in terminos:
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            terminos_unicos.append(t)
        normalizadas.append({'nombre': nombre, 'color': color, 'terminos': terminos_unicos, 'peso': int(item.get('peso') or 0)})

    _set_config_json(
        'calidad_listas',
        normalizadas,
        descripcion='Listas de palabras clave para análisis de calidad en chats',
        categoria='calidad',
    )
    return jsonify({'ok': True, 'listas': normalizadas})


@crm_bp.route('/api/admin/bot_toggle', methods=['POST'])
@login_required
def api_bot_toggle():
    _require_admin()
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', True))
    _set_config_json(
        'bot_global_enabled',
        enabled,
        descripcion='Activa o desactiva la respuesta automática de la IA globalmente',
        categoria='general'
    )
    return jsonify({'ok': True, 'enabled': enabled})


@crm_bp.route('/api/admin/bot_contexto', methods=['PUT'])
@login_required
def api_bot_contexto():
    _require_admin()
    data = request.get_json(silent=True) or {}
    contexto = _save_bot_context(data)
    return jsonify({'ok': True, 'contexto': contexto})


@crm_bp.route('/api/admin/distribucion_config', methods=['POST'])
@login_required
def api_distribucion_config():
    _require_admin()
    data = request.get_json(silent=True) or {}
    cfg = _normalizar_distribucion_config(data)

    _set_config_json(
        'distribucion_config',
        cfg,
        descripcion='Configuración de distribución automática de WhatsApp',
        categoria='general'
    )
    return jsonify({
        'ok': True,
        'config': cfg,
        'metodo_label': _label_metodo_distribucion(cfg.get('metodo')),
    })


@crm_bp.route('/api/admin/calidad/buscar', methods=['GET'])
@login_required
def api_calidad_buscar():
    _require_admin()
    desde_s = (request.args.get('desde') or '').strip()
    hasta_s = (request.args.get('hasta') or '').strip()
    modo = (request.args.get('modo') or 'asesor').strip().lower()
    limit = request.args.get('limit', 200, type=int)
    limit = max(1, min(limit, 500))

    hoy = datetime.utcnow().date()
    if not desde_s:
        desde_s = str(hoy - timedelta(days=7))
    if not hasta_s:
        hasta_s = str(hoy)

    try:
        desde = datetime.strptime(desde_s, '%Y-%m-%d')
        hasta = datetime.strptime(hasta_s, '%Y-%m-%d') + timedelta(days=1)
    except Exception:
        return jsonify({'error': 'rango de fechas inválido'}), 400

    listas_sel = (request.args.get('listas') or '').strip()
    seleccion = [s.strip() for s in listas_sel.split(',') if s.strip()] if listas_sel else []

    config_listas = _get_config_json('calidad_listas', default=[])
    if not isinstance(config_listas, list):
        config_listas = []

    listas = []
    for item in config_listas:
        if not isinstance(item, dict):
            continue
        nombre = (item.get('nombre') or '').strip()
        if not nombre:
            continue
        if seleccion and nombre not in seleccion:
            continue
        terminos = item.get('terminos') or []
        if not isinstance(terminos, list):
            terminos = []
        terminos = [str(t).strip() for t in terminos if str(t).strip()]
        if not terminos:
            continue
        listas.append({'nombre': nombre, 'color': (item.get('color') or '#14B8A6').strip() or '#14B8A6', 'terminos': terminos, 'peso': int(item.get('peso') or 0)})

    terminos_total = []
    terminos_por_lista: dict[str, list[str]] = {}
    seen = set()
    for l in listas:
        t_ok = []
        for t in l['terminos']:
            if len(t) < 2:
                continue
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            terminos_total.append(t)
            t_ok.append(t)
        if t_ok:
            terminos_por_lista[l['nombre']] = t_ok

    or_clauses = []
    if terminos_total:
        for t in terminos_total[:250]:
            # Usamos REGEXP con boundaries \b (word boundary) para MariaDB/MySQL 
            # para evitar falsos positivos como "normal" matchando "mal"
            escaped_term = t.replace('\\', '\\\\').replace('+', '\\+').replace('*', '\\*').replace('?', '\\?').replace('(', '\\(').replace(')', '\\)').replace('[', '\\[').replace(']', '\\]').replace('{', '\\{').replace('}', '\\}').replace('^', '\\^').replace('$', '\\$').replace('|', '\\|').replace('.', '\\.')
            or_clauses.append(WhatsAppMensaje.contenido.op('REGEXP')(rf'\b{escaped_term}\b'))

    q = WhatsAppMensaje.query.join(
        WhatsAppConversacion, WhatsAppConversacion.id == WhatsAppMensaje.id_conversacion
    ).filter(
        WhatsAppMensaje.created_at >= desde,
        WhatsAppMensaje.created_at < hasta,
    )
    if or_clauses:
        q = q.filter(or_(*or_clauses))

    if modo == 'asesor':
        q = q.filter(WhatsAppMensaje.remitente == 'asesor', WhatsAppMensaje.direccion == 'saliente')
    elif modo == 'cliente':
        q = q.filter(WhatsAppMensaje.remitente == 'cliente', WhatsAppMensaje.direccion == 'entrante')

    mensajes = q.order_by(WhatsAppMensaje.created_at.desc()).limit(limit).all()

    import re
    resultados = []
    for m in mensajes:
        contenido = m.contenido or ''
        matched = {}
        puntaje_mensaje = 0
        # Precompilar una lista rápida de apariciones para no iterar sobre todos si no hace falta
        for l in listas:
            nombre_lista = l['nombre']
            terms = l['terminos']
            hits = []
            for t in terms:
                # Armamos un regex para matchar palabras exactas (ignorando case)
                # python \b funciona para caracteres alfanuméricos
                escaped_term = re.escape(t)
                # Hay que tener cuidado con \b si el término empieza o termina con un carácter no verbal (ej. "?", "!")
                # Por simplicidad en este caso, podemos usar una expresión regular básica con \b 
                # o (\W|^)term(\W|$) para ser más robustos con palabras que no son puramente alfanuméricas
                pattern = r'(?i)(?:\b|\s|^)' + escaped_term + r'(?:\b|\s|$|[.?!,])'
                if re.search(pattern, contenido):
                    hits.append(t)
            
            if hits:
                matched[nombre_lista] = hits[:20]
                puntaje_mensaje += l.get('peso', 0)
        if terminos_total and not matched:
            continue
        conv = m.conversacion
        resultados.append({
            'id_mensaje': m.id,
            'id_conversacion': m.id_conversacion,
            'telefono': conv.telefono if conv else None,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'direccion': m.direccion,
            'remitente': m.remitente,
            'contenido': contenido,
            'matched': matched,
            'puntaje': puntaje_mensaje,
        })
    # Opcional: ordenar los resultados por peso absoluto para mostrar los más "fuertes" o simplemente dejar por fecha
    return jsonify({'resultados': resultados, 'listas': listas, 'total': len(resultados)})


@crm_bp.route('/api/admin/etiquetas', methods=['GET'])
@login_required
def api_admin_etiquetas():
    _require_admin()
    etiquetas = CrmEtiqueta.query.order_by(CrmEtiqueta.nombre).all()
    return jsonify({'etiquetas': [e.to_dict() for e in etiquetas]})


@crm_bp.route('/api/admin/etiquetas', methods=['POST'])
@login_required
def api_crear_etiqueta():
    _require_admin()
    data = request.get_json(silent=True) or {}
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'nombre requerido'}), 400
    if CrmEtiqueta.query.filter_by(nombre=nombre).first():
        return jsonify({'error': 'ya existe una etiqueta con ese nombre'}), 409

    e = CrmEtiqueta(
        nombre=nombre,
        color=data.get('color', '#6B7280'),
        descripcion=data.get('descripcion', ''),
    )
    db.session.add(e)
    db.session.commit()
    return jsonify({'ok': True, 'etiqueta': e.to_dict()}), 201


@crm_bp.route('/api/admin/etiquetas/<int:id_etiqueta>', methods=['PATCH'])
@login_required
def api_editar_etiqueta(id_etiqueta):
    _require_admin()
    e = CrmEtiqueta.query.get_or_404(id_etiqueta)
    data = request.get_json(silent=True) or {}
    for campo in ('nombre', 'color', 'descripcion', 'activa'):
        if campo in data:
            setattr(e, campo, data[campo])
    db.session.commit()
    return jsonify({'ok': True, 'etiqueta': e.to_dict()})


@crm_bp.route('/api/admin/etiquetas/<int:id_etiqueta>', methods=['DELETE'])
@login_required
def api_eliminar_etiqueta(id_etiqueta):
    _require_admin()
    e = CrmEtiqueta.query.get_or_404(id_etiqueta)
    db.session.delete(e)
    db.session.commit()
    return jsonify({'ok': True})
