"""
Servicio de asignacion de conversaciones a asesores.
Implementa asignacion exclusiva, heartbeat, timeout y reasignacion.
"""
import os
import logging
from datetime import datetime, timedelta
import math

import json
from app import db
from app.models.whatsapp import (
    WhatsAppConversacion, WhatsAppEstadoAsesor, WhatsAppAsignacionConversacion, WhatsAppConfiguracion
)
from app.services.whatsapp.auditoria_service import registrar_evento_conversacion
from app.services.whatsapp.contexto_service import (
    bloquear_reingreso_bandeja,
    limpiar_bloqueo_reingreso_bandeja,
)

logger = logging.getLogger(__name__)


def _get_distribucion_config() -> dict:
    config = WhatsAppConfiguracion.query.filter_by(clave='distribucion_config').first()
    default_heartbeat_minutos = max(1, math.ceil(_heartbeat_segundos() * 2 / 60))
    default_config = {
        'enabled': True,
        'metodo': 'least_busy',
        'max_conversaciones': int(os.environ.get('WHATSAPP_ASESOR_MAX_CONVERSACIONES', '5')),
        'heartbeat_auto_offline': True,
        'heartbeat_timeout_minutos': default_heartbeat_minutos,
        # Política A: chat asignado pero no aceptado por el asesor
        'timeout_no_aceptado': {
            'enabled': True,
            'minutos': 5,
            'accion': 'reasignar',   # 'reasignar' | 'cola_general'
        },
        # Política B: chat aceptado pero asesor sin responder
        'timeout_sin_respuesta': {
            'enabled': True,
            'minutos': 15,
            'accion': 'cola_general',
        },
    }
    if not config or not config.valor:
        return default_config
    try:
        saved = json.loads(config.valor)
        if (
            'heartbeat_timeout_minutos' not in saved
            and 'heartbeat_timeout_segundos' in saved
        ):
            try:
                saved['heartbeat_timeout_minutos'] = max(1, math.ceil(int(saved.get('heartbeat_timeout_segundos', 0)) / 60))
            except Exception:
                saved['heartbeat_timeout_minutos'] = default_heartbeat_minutos
        # Compatibilidad hacia atrás: si sólo tiene timeout_segundos, lo migramos
        if 'timeout_segundos' in saved and 'timeout_no_aceptado' not in saved:
            minutos = max(1, saved['timeout_segundos'] // 60)
            saved['timeout_no_aceptado'] = {'enabled': True, 'minutos': minutos, 'accion': 'reasignar'}
        merged = {**default_config, **saved}
        # Asegurar que los sub-dicts de timeout existan correctamente
        for key in ('timeout_no_aceptado', 'timeout_sin_respuesta'):
            if key in merged and isinstance(merged[key], dict):
                merged[key] = {**default_config[key], **merged[key]}
        default_heartbeat_timeout = default_config.get('heartbeat_timeout_minutos', 1)
        merged['heartbeat_auto_offline'] = bool(merged.get('heartbeat_auto_offline', True))
        try:
            merged['heartbeat_timeout_minutos'] = max(1, int(merged.get('heartbeat_timeout_minutos', default_heartbeat_timeout)))
        except Exception:
            merged['heartbeat_timeout_minutos'] = max(1, int(default_heartbeat_timeout))
        merged.pop('heartbeat_timeout_segundos', None)
        return merged
    except Exception:
        return default_config


def _timeout_segundos() -> int:
    """Compatibilidad hacia atrás (usado por código legado)."""
    cfg = _get_distribucion_config()
    na = cfg.get('timeout_no_aceptado', {})
    return na.get('minutos', 5) * 60


def _heartbeat_segundos() -> int:
    return int(os.environ.get('WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS', '10'))


def _heartbeat_policy(config: dict | None = None) -> dict:
    config = config or _get_distribucion_config()
    default_timeout_min = max(1, math.ceil(_heartbeat_segundos() * 2 / 60))
    try:
        timeout_min = int(config.get('heartbeat_timeout_minutos', default_timeout_min))
    except Exception:
        timeout_min = default_timeout_min
    timeout_min = max(1, timeout_min)
    return {
        'enabled': bool(config.get('heartbeat_auto_offline', True)),
        'timeout_minutos': timeout_min,
        'timeout_segundos': timeout_min * 60,
    }


def get_heartbeat_policy() -> dict:
    return _heartbeat_policy(_get_distribucion_config())


def _max_conversaciones() -> int:
    return _get_distribucion_config().get('max_conversaciones', 5)


def _asesores_disponibles(config: dict) -> list[WhatsAppEstadoAsesor]:
    heartbeat_policy = _heartbeat_policy(config)
    max_convs = config.get('max_conversaciones', 5)
    
    query = WhatsAppEstadoAsesor.query.filter(
        WhatsAppEstadoAsesor.online == True,
        db.func.coalesce(WhatsAppEstadoAsesor.conversaciones_activas, 0) < max_convs
    )
    if heartbeat_policy.get('enabled', True):
        limite_heartbeat = datetime.utcnow() - timedelta(seconds=heartbeat_policy.get('timeout_segundos', 20))
        query = query.filter(
            WhatsAppEstadoAsesor.ultimo_ping.isnot(None),
            WhatsAppEstadoAsesor.ultimo_ping >= limite_heartbeat,
        )
    
    metodo = config.get('metodo', 'least_busy')
    if metodo == 'round_robin':
        # Ordenar por el que hace más tiempo no recibe (nulls first -> los que nunca recibieron primero)
        # y segundo por menor carga, en caso de empate
        query = query.order_by(
            db.func.coalesce(WhatsAppEstadoAsesor.ultima_asignacion, datetime.min).asc(),
            WhatsAppEstadoAsesor.conversaciones_activas.asc(),
            WhatsAppEstadoAsesor.ultimo_ping.desc(),
        )
    else:
        # Default: least_busy
        query = query.order_by(
            WhatsAppEstadoAsesor.conversaciones_activas.asc(),
            WhatsAppEstadoAsesor.ultimo_ping.desc(),
        )

    return query.all()


def buscar_asesor_disponible(config: dict = None) -> WhatsAppEstadoAsesor | None:
    if config is None:
        config = _get_distribucion_config()
    asesores = _asesores_disponibles(config)
    return asesores[0] if asesores else None


def _asignar_conversacion_a_asesor(
    conv: WhatsAppConversacion,
    asesor: WhatsAppEstadoAsesor,
    *,
    estado: str = 'pendiente',
    ahora: datetime | None = None,
):
    ahora = ahora or datetime.utcnow()
    asignacion = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=conv.id
    ).first()

    id_asesor_anterior = asignacion.id_asesor if asignacion else None
    estado_anterior = asignacion.estado if asignacion else None

    if not asignacion:
        asignacion = WhatsAppAsignacionConversacion(id_conversacion=conv.id)
        db.session.add(asignacion)

    if id_asesor_anterior and id_asesor_anterior != asesor.id_usuario and estado_anterior in ('pendiente', 'activa'):
        asesor_anterior = WhatsAppEstadoAsesor.query.get(id_asesor_anterior)
        if asesor_anterior and (asesor_anterior.conversaciones_activas or 0) > 0:
            asesor_anterior.conversaciones_activas -= 1

    if id_asesor_anterior != asesor.id_usuario or estado_anterior not in ('pendiente', 'activa'):
        asesor.conversaciones_activas = (asesor.conversaciones_activas or 0) + 1
        asesor.ultima_asignacion = ahora

    asignacion.id_asesor = asesor.id_usuario
    asignacion.estado = estado
    asignacion.asignado_at = ahora
    asignacion.aceptado_at = ahora if estado == 'activa' else None
    asignacion.cerrado_at = None
    conv.modo = 'derivacion'
    limpiar_bloqueo_reingreso_bandeja(conv)
    registrar_evento_conversacion(
        conv,
        'asignacion_actualizada' if id_asesor_anterior else 'asignacion_creada',
        detalle={'id_asesor': asesor.id_usuario, 'id_asesor_anterior': id_asesor_anterior, 'estado': estado, 'estado_anterior': estado_anterior},
    )
    return asignacion


def distribuir_conversaciones_pendientes(*, commit: bool = True) -> int:
    config = _get_distribucion_config()
    if not config.get('enabled', True):
        return 0

    asignadas = 0
    candidatas = WhatsAppConversacion.query.filter_by(activa=True, modo='derivacion').order_by(
        WhatsAppConversacion.ultima_actividad.desc()
    ).all()

    for conv in candidatas:
        activa = WhatsAppAsignacionConversacion.query.filter_by(
            id_conversacion=conv.id
        ).filter(
            WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
        ).first()
        if activa:
            continue
        asesor = buscar_asesor_disponible(config)
        if not asesor:
            break
        _asignar_conversacion_a_asesor(conv, asesor, estado='pendiente')
        asignadas += 1

    if commit and asignadas > 0:
        db.session.commit()
    return asignadas


def asignar_conversacion(id_conversacion: int, motivo: str, prioridad: str = 'normal') -> dict:
    """
    Asigna una conversacion a un asesor disponible.
    Retorna dict con resultado de la asignacion.
    """
    conv = WhatsAppConversacion.query.get(id_conversacion)
    if not conv:
        return {'asignado': False, 'error': 'Conversacion no encontrada'}

    # Verificar si ya tiene asignacion activa
    asignacion_existente = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conversacion
    ).filter(
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).first()

    if asignacion_existente:
        return {
            'asignado': True,
            'ya_asignado': True,
            'nombre_asesor': asignacion_existente.asesor.nombre_completo if asignacion_existente.asesor else 'Asesor',
            'mensaje': 'Ya tenes un asesor asignado. En breve te responde.'
        }

    config = _get_distribucion_config()
    if not config.get('enabled', True):
        conv.modo = 'derivacion'
        limpiar_bloqueo_reingreso_bandeja(conv)
        registrar_evento_conversacion(conv, 'cola_asesores', detalle={'motivo': motivo, 'sin_asesores': True, 'distribucion_habilitada': False})
        db.session.commit()
        logger.info(f"Distribucion de mensajes deshabilitada via config, conv={id_conversacion} enviada a cola general")
        return {
            'asignado': False,
            'sin_asesores': True,
            'mensaje': 'En este momento te atenderemos por orden de llegada en la bandeja general.'
        }

    # Buscar asesor disponible
    asesor = buscar_asesor_disponible(config)
    if not asesor:
        # Cambiar modo a derivacion (en cola)
        conv.modo = 'derivacion'
        limpiar_bloqueo_reingreso_bandeja(conv)
        registrar_evento_conversacion(conv, 'cola_asesores', detalle={'motivo': motivo, 'sin_asesores': True})
        db.session.commit()

        logger.info(f"Sin asesores disponibles para conv={id_conversacion}")
        return {
            'asignado': False,
            'sin_asesores': True,
            'mensaje': 'En este momento no hay asesores disponibles. Tu consulta quedo registrada y te responderemos apenas podamos.'
        }

    _asignar_conversacion_a_asesor(conv, asesor, estado='pendiente')
    db.session.commit()

    nombre = asesor.usuario.nombre_completo if asesor.usuario else 'Asesor'
    logger.info(f"Conversacion {id_conversacion} asignada a asesor {asesor.id_usuario} ({nombre})")

    return {
        'asignado': True,
        'id_asesor': asesor.id_usuario,
        'nombre_asesor': nombre,
        'mensaje': f'Te atiende {nombre}. Ya puede escribirte. 👋'
    }


def tomar_conversacion(id_conversacion: int, id_asesor: int) -> dict:
    conv = WhatsAppConversacion.query.get(id_conversacion)
    if not conv:
        return {'ok': False, 'error': 'Conversacion no encontrada'}

    asignacion = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conversacion
    ).first()

    if asignacion and asignacion.estado in ('pendiente', 'activa'):
        if asignacion.id_asesor != id_asesor:
            return {'ok': False, 'error': 'La conversacion ya esta asignada a otro asesor'}
        if asignacion.estado != 'activa':
            ahora = datetime.utcnow()
            asignacion.estado = 'activa'
            asignacion.aceptado_at = ahora
            asignacion.ultima_respuesta_asesor_at = ahora  # baseline para Política B
            if asignacion.conversacion:
                asignacion.conversacion.modo = 'asesor'
                registrar_evento_conversacion(asignacion.conversacion, 'asesor_tomo_conversacion', actor='asesor', id_usuario=id_asesor)
            db.session.commit()
        return {'ok': True, 'id_asignacion': asignacion.id}

    estado_nuevo = WhatsAppEstadoAsesor.query.get(id_asesor)
    if not estado_nuevo:
        estado_nuevo = WhatsAppEstadoAsesor(
            id_usuario=id_asesor,
            online=False,
            max_conversaciones=_max_conversaciones(),
            conversaciones_activas=0,
            ultima_asignacion=datetime.utcnow()
        )
        db.session.add(estado_nuevo)

    if asignacion:
        if asignacion.id_asesor and asignacion.id_asesor != id_asesor:
            estado_anterior = WhatsAppEstadoAsesor.query.get(asignacion.id_asesor)
            if estado_anterior and (estado_anterior.conversaciones_activas or 0) > 0:
                estado_anterior.conversaciones_activas -= 1
        ahora = datetime.utcnow()
        asignacion.id_asesor = id_asesor
        asignacion.estado = 'activa'
        asignacion.asignado_at = ahora
        asignacion.aceptado_at = ahora
        asignacion.ultima_respuesta_asesor_at = ahora
        asignacion.cerrado_at = None
    else:
        ahora = datetime.utcnow()
        asignacion = WhatsAppAsignacionConversacion(
            id_conversacion=id_conversacion,
            id_asesor=id_asesor,
            estado='activa',
            asignado_at=ahora,
            aceptado_at=ahora,
            ultima_respuesta_asesor_at=ahora,
        )
        db.session.add(asignacion)

    estado_nuevo.conversaciones_activas = (estado_nuevo.conversaciones_activas or 0) + 1
    conv.modo = 'asesor'
    limpiar_bloqueo_reingreso_bandeja(conv)
    registrar_evento_conversacion(conv, 'asesor_tomo_conversacion', actor='asesor', id_usuario=id_asesor)
    db.session.commit()
    logger.info(f"Asesor {id_asesor} tomo conversacion {id_conversacion}")
    return {'ok': True, 'id_asignacion': asignacion.id}


def aceptar_conversacion(id_asignacion: int, id_asesor: int) -> dict:
    """El asesor acepta la conversacion asignada."""
    asignacion = WhatsAppAsignacionConversacion.query.get(id_asignacion)
    if not asignacion:
        return {'ok': False, 'error': 'Asignacion no encontrada'}

    if asignacion.id_asesor != id_asesor:
        return {'ok': False, 'error': 'Esta conversacion no te fue asignada'}

    if asignacion.estado != 'pendiente':
        return {'ok': False, 'error': f'La conversacion ya esta en estado: {asignacion.estado}'}

    ahora = datetime.utcnow()
    asignacion.estado = 'activa'
    asignacion.aceptado_at = ahora
    asignacion.ultima_respuesta_asesor_at = ahora  # baseline para Política B

    # Cambiar modo de la conversacion a asesor
    if asignacion.conversacion:
        asignacion.conversacion.modo = 'asesor'
        registrar_evento_conversacion(asignacion.conversacion, 'asesor_acepto_conversacion', actor='asesor', id_usuario=id_asesor)

    db.session.commit()
    logger.info(f"Asesor {id_asesor} acepto conversacion {asignacion.id_conversacion}")
    return {'ok': True}


def devolver_conversacion(id_asignacion: int, id_asesor: int) -> dict:
    """El asesor devuelve la conversacion al pool."""
    asignacion = WhatsAppAsignacionConversacion.query.get(id_asignacion)
    if not asignacion:
        return {'ok': False, 'error': 'Asignacion no encontrada'}

    if asignacion.id_asesor != id_asesor:
        return {'ok': False, 'error': 'Esta conversacion no te fue asignada'}

    asignacion.estado = 'devuelta'
    asignacion.cerrado_at = datetime.utcnow()
    asignacion.motivo_devolucion = 'manual'

    # Decrementar conteo del asesor
    estado = WhatsAppEstadoAsesor.query.get(id_asesor)
    if estado and estado.conversaciones_activas > 0:
        estado.conversaciones_activas -= 1

    if asignacion.conversacion:
        asignacion.conversacion.modo = 'derivacion'
        limpiar_bloqueo_reingreso_bandeja(asignacion.conversacion)
        registrar_evento_conversacion(asignacion.conversacion, 'asesor_devolvio_conversacion', actor='asesor', id_usuario=id_asesor, detalle={'motivo': 'manual'})

    distribuir_conversaciones_pendientes(commit=False)
    db.session.commit()
    logger.info(f"Asesor {id_asesor} devolvio conversacion {asignacion.id_conversacion}")
    return {'ok': True}


def cerrar_conversacion(id_asignacion: int, id_asesor: int) -> dict:
    """El asesor cierra la conversacion (vuelve a modo bot)."""
    asignacion = WhatsAppAsignacionConversacion.query.get(id_asignacion)
    if not asignacion:
        return {'ok': False, 'error': 'Asignacion no encontrada'}

    if asignacion.id_asesor != id_asesor:
        return {'ok': False, 'error': 'Esta conversacion no te fue asignada'}

    asignacion.estado = 'cerrada'
    asignacion.cerrado_at = datetime.utcnow()

    # Decrementar conteo del asesor
    estado = WhatsAppEstadoAsesor.query.get(id_asesor)
    if estado and estado.conversaciones_activas > 0:
        estado.conversaciones_activas -= 1

    # Volver a modo bot
    if asignacion.conversacion:
        asignacion.conversacion.modo = 'bot'
        bloquear_reingreso_bandeja(asignacion.conversacion, 'cierre_manual')
        registrar_evento_conversacion(asignacion.conversacion, 'asesor_cerro_conversacion', actor='asesor', id_usuario=id_asesor)

    db.session.commit()
    logger.info(f"Asesor {id_asesor} cerro conversacion {asignacion.id_conversacion}")
    return {'ok': True}


def transferir_conversacion(id_asignacion: int, id_asesor_origen: int, id_asesor_destino: int) -> dict:
    asignacion = WhatsAppAsignacionConversacion.query.get(id_asignacion)
    if not asignacion:
        return {'ok': False, 'error': 'Asignacion no encontrada'}

    if asignacion.id_asesor != id_asesor_origen:
        return {'ok': False, 'error': 'Esta conversacion no te fue asignada'}

    if asignacion.estado not in ('pendiente', 'activa'):
        return {'ok': False, 'error': f'La conversacion ya esta en estado: {asignacion.estado}'}

    if id_asesor_destino == id_asesor_origen:
        return {'ok': False, 'error': 'Seleccioná otro asesor para transferir'}

    estado_destino = WhatsAppEstadoAsesor.query.get(id_asesor_destino)
    if not estado_destino or not estado_destino.online:
        return {'ok': False, 'error': 'El asesor destino no está online'}
    heartbeat_policy = _heartbeat_policy()
    if heartbeat_policy.get('enabled', True):
        limite_heartbeat = datetime.utcnow() - timedelta(seconds=heartbeat_policy.get('timeout_segundos', 20))
        if not estado_destino.ultimo_ping or estado_destino.ultimo_ping < limite_heartbeat:
            return {'ok': False, 'error': 'El asesor destino no está online'}

    if (estado_destino.conversaciones_activas or 0) >= (estado_destino.max_conversaciones or _max_conversaciones()):
        return {'ok': False, 'error': 'El asesor destino no tiene capacidad disponible'}

    estado_origen = WhatsAppEstadoAsesor.query.get(id_asesor_origen)
    if estado_origen and (estado_origen.conversaciones_activas or 0) > 0:
        estado_origen.conversaciones_activas -= 1

    estado_destino.conversaciones_activas = (estado_destino.conversaciones_activas or 0) + 1

    asignacion.id_asesor = id_asesor_destino
    asignacion.estado = 'pendiente'
    asignacion.asignado_at = datetime.utcnow()
    asignacion.aceptado_at = None
    asignacion.cerrado_at = None

    if asignacion.conversacion:
        asignacion.conversacion.modo = 'derivacion'
        registrar_evento_conversacion(asignacion.conversacion, 'asignacion_transferida', actor='asesor', id_usuario=id_asesor_origen, detalle={'id_asesor_destino': id_asesor_destino})

    db.session.commit()
    nombre = estado_destino.usuario.nombre_completo if estado_destino.usuario else f'Asesor #{id_asesor_destino}'
    logger.info(f"Asesor {id_asesor_origen} transfirio conversacion {asignacion.id_conversacion} a asesor {id_asesor_destino} ({nombre})")
    return {'ok': True, 'nombre_asesor': nombre, 'id_asesor': id_asesor_destino}


def toggle_online(id_usuario: int, online: bool) -> dict:
    """Cambia estado online/offline de un asesor."""
    estado = WhatsAppEstadoAsesor.query.get(id_usuario)
    if not estado:
        estado = WhatsAppEstadoAsesor(
            id_usuario=id_usuario,
            online=online,
            max_conversaciones=_max_conversaciones()
        )
        db.session.add(estado)

    estado.online = online
    if online:
        estado.conectado_desde = datetime.utcnow()
        estado.ultimo_ping = datetime.utcnow()
        distribuir_conversaciones_pendientes(commit=False)
    else:
        estado.conectado_desde = None
        _devolver_conversaciones_asesor(id_usuario)

    db.session.commit()
    logger.info(f"Asesor {id_usuario} ahora {'online' if online else 'offline'}")
    return {'ok': True, 'online': online}


def heartbeat(id_usuario: int) -> dict:
    """Actualiza el heartbeat del asesor."""
    estado = WhatsAppEstadoAsesor.query.get(id_usuario)
    if not estado:
        return {'ok': False, 'error': 'Asesor no registrado'}

    estado.ultimo_ping = datetime.utcnow()
    if estado.online:
        distribuir_conversaciones_pendientes(commit=False)
    db.session.commit()
    return {'ok': True, 'conversaciones_activas': estado.conversaciones_activas}


def _aplicar_accion_timeout(
    asig: WhatsAppAsignacionConversacion,
    accion: str,
    motivo: str,
    ahora: datetime,
) -> bool:
    """
    Aplica la acción de timeout sobre una asignación.
    Retorna True si hubo cambio efectivo.
    """
    estado_anterior = WhatsAppEstadoAsesor.query.get(asig.id_asesor)
    if estado_anterior and (estado_anterior.conversaciones_activas or 0) > 0:
        estado_anterior.conversaciones_activas -= 1

    asig.estado = 'devuelta'
    asig.cerrado_at = ahora
    asig.motivo_devolucion = motivo

    nuevo_asesor = None
    if accion == 'reasignar':
        nuevo_asesor = buscar_asesor_disponible()
        # No reasignar al mismo asesor que ya no atendió
        if nuevo_asesor and nuevo_asesor.id_usuario == asig.id_asesor:
            nuevo_asesor = None

    if nuevo_asesor and asig.conversacion:
        _asignar_conversacion_a_asesor(asig.conversacion, nuevo_asesor, estado='pendiente', ahora=ahora)
        logger.info(
            f"[timeout] Conv {asig.id_conversacion} ({motivo}): "
            f"reasignada de asesor {asig.id_asesor} → asesor {nuevo_asesor.id_usuario}"
        )
    else:
        # Cae a cola_general (sin asesor)
        if asig.conversacion:
            asig.conversacion.modo = 'derivacion'
            limpiar_bloqueo_reingreso_bandeja(asig.conversacion)
        logger.info(
            f"[timeout] Conv {asig.id_conversacion} ({motivo}): enviada a cola general"
        )
    if asig.conversacion:
        registrar_evento_conversacion(asig.conversacion, 'timeout_asignacion', detalle={'accion': accion, 'motivo': motivo, 'id_asesor': asig.id_asesor})
    return True


def _accion_timeout_valida(accion) -> bool:
    return accion in ('reasignar', 'cola_general')


def verificar_timeouts():
    """
    Verifica asesores sin heartbeat y aplica las dos políticas de timeout.
    Llamar periódicamente (ej: cada 30 segundos).
    """
    ahora = datetime.utcnow()
    config = _get_distribucion_config()

    # ------------------------------------------------------------------ #
    # 0) Marcar offline asesores sin heartbeat                            #
    # ------------------------------------------------------------------ #
    heartbeat_policy = _heartbeat_policy(config)
    asesores_timeout = []
    if heartbeat_policy.get('enabled', True):
        limite_heartbeat = ahora - timedelta(seconds=heartbeat_policy.get('timeout_segundos', 20))
        asesores_timeout = WhatsAppEstadoAsesor.query.filter(
            WhatsAppEstadoAsesor.online == True,
            db.or_(
                WhatsAppEstadoAsesor.ultimo_ping.is_(None),
                WhatsAppEstadoAsesor.ultimo_ping < limite_heartbeat
            )
        ).all()

        for asesor in asesores_timeout:
            logger.warning(f"Asesor {asesor.id_usuario} sin heartbeat, marcando offline")
            asesor.online = False
            asesor.conectado_desde = None
            _devolver_conversaciones_asesor(asesor.id_usuario)

    hubo_cambios = bool(asesores_timeout)

    # ------------------------------------------------------------------ #
    # Política A: chat NO ACEPTADO (estado pendiente)                    #
    # ------------------------------------------------------------------ #
    cfg_a = config.get('timeout_no_aceptado', {})
    if cfg_a.get('enabled', True):
        limite_a = ahora - timedelta(minutes=cfg_a.get('minutos', 5))
        accion_a = cfg_a.get('accion') if 'accion' in cfg_a else 'reasignar'

        pendientes = WhatsAppAsignacionConversacion.query.filter(
            WhatsAppAsignacionConversacion.estado == 'pendiente',
            WhatsAppAsignacionConversacion.asignado_at < limite_a
        ).all()

        for asig in pendientes:
            logger.warning(
                f"Asignación {asig.id} Policy-A timeout "
                f"(no aceptada en {cfg_a.get('minutos')} min), accion={accion_a}"
            )
            if not _accion_timeout_valida(accion_a):
                continue
            _aplicar_accion_timeout(asig, accion_a, 'timeout_no_aceptado', ahora)
            hubo_cambios = True

    # ------------------------------------------------------------------ #
    # Política B: chat TOMADO sin respuesta del asesor                   #
    # ------------------------------------------------------------------ #
    cfg_b = config.get('timeout_sin_respuesta', {})
    if cfg_b.get('enabled', True):
        limite_b = ahora - timedelta(minutes=cfg_b.get('minutos', 15))
        accion_b = cfg_b.get('accion') if 'accion' in cfg_b else 'cola_general'

        activas = WhatsAppAsignacionConversacion.query.filter(
            WhatsAppAsignacionConversacion.estado == 'activa',
        ).all()

        for asig in activas:
            # Referencia de tiempo: última respuesta del asesor, o en su defecto cuando aceptó
            referencia = asig.ultima_respuesta_asesor_at or asig.aceptado_at
            if referencia and referencia < limite_b:
                logger.warning(
                    f"Asignación {asig.id} Policy-B timeout "
                    f"(sin respuesta en {cfg_b.get('minutos')} min), accion={accion_b}"
                )
                if not _accion_timeout_valida(accion_b):
                    continue
                _aplicar_accion_timeout(asig, accion_b, 'timeout_sin_respuesta', ahora)
                hubo_cambios = True

    redistributed = distribuir_conversaciones_pendientes(commit=False)
    if redistributed:
        hubo_cambios = True

    if hubo_cambios:
        db.session.commit()


def _devolver_conversaciones_asesor(id_usuario: int):
    """Devuelve todas las conversaciones activas/pendientes de un asesor (asesor_offline)."""
    asignaciones = WhatsAppAsignacionConversacion.query.filter(
        WhatsAppAsignacionConversacion.id_asesor == id_usuario,
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
    ).all()

    for asig in asignaciones:
        asig.estado = 'devuelta'
        asig.cerrado_at = datetime.utcnow()
        asig.motivo_devolucion = 'asesor_offline'
        if asig.conversacion:
            asig.conversacion.modo = 'derivacion'
            limpiar_bloqueo_reingreso_bandeja(asig.conversacion)
            registrar_evento_conversacion(asig.conversacion, 'asesor_offline', detalle={'id_asesor': id_usuario})

    estado = WhatsAppEstadoAsesor.query.get(id_usuario)
    if estado:
        estado.conversaciones_activas = 0
