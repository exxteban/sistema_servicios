from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from app import db
from app.models import AgendaActividad, Cliente, ClienteServicio, DetalleVenta, Servicio, Venta
from app.services.agenda_turnos_peluqueria import (
    TURNO_PELUQUERIA_TIPO_LABELS,
    infer_turno_peluqueria_tipo_from_title,
    is_turno_peluqueria_catalog_service_chargeable,
    resolve_turno_peluqueria_catalog_service,
)
from app.utils.helpers import local_strftime, now_local, today_local, utc_bounds_for_local_dates, utc_naive_to_local
from flask import url_for

SERVICIOS_REALIZADOS_BAR_CLASSES = (
    'bg-violet-500',
    'bg-indigo-500',
    'bg-blue-500',
    'bg-cyan-500',
    'bg-slate-400',
)


def _item_fecha_solicitud(item):
    if isinstance(item, dict):
        return item.get('fecha_solicitud')
    return getattr(item, 'fecha_solicitud', None)


def _item_id_orden(item):
    if isinstance(item, dict):
        return 0
    return int(getattr(item, 'id_cliente_servicio', 0) or 0)


def _agenda_sale_key(actividad, servicio):
    if actividad is None or servicio is None:
        return None
    try:
        cliente_id = int(actividad.cliente_id or 0)
        servicio_id = int(servicio.id_servicio or 0)
    except Exception:
        return None
    if not cliente_id or not servicio_id:
        return None
    return (cliente_id, servicio_id)


def _contar_servicios_agenda_vendidos(agenda_items, servicios_por_actividad, start_utc, end_utc):
    keys = {
        key
        for actividad in agenda_items
        for key in [_agenda_sale_key(actividad, servicios_por_actividad.get(int(actividad.id)))]
        if key
    }
    if not keys:
        return {}

    cliente_ids = sorted({cliente_id for cliente_id, _servicio_id in keys})
    servicio_ids = sorted({servicio_id for _cliente_id, servicio_id in keys})
    rows = (
        db.session.query(
            Venta.id_cliente,
            DetalleVenta.id_servicio,
            db.func.coalesce(db.func.sum(DetalleVenta.cantidad), 0),
        )
        .join(DetalleVenta, DetalleVenta.id_venta == Venta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
            Venta.id_cliente.in_(cliente_ids),
            DetalleVenta.id_servicio.in_(servicio_ids),
        )
        .group_by(Venta.id_cliente, DetalleVenta.id_servicio)
        .all()
    )
    vendidos = {}
    for cliente_id, servicio_id, cantidad in rows:
        key = (int(cliente_id or 0), int(servicio_id or 0))
        if key in keys:
            vendidos[key] = int(cantidad or 0)
    return vendidos


def _consumir_si_turno_ya_fue_cobrado(actividad, servicio, vendidos_por_key):
    key = _agenda_sale_key(actividad, servicio)
    if not key:
        return False
    cantidad = int(vendidos_por_key.get(key) or 0)
    if cantidad <= 0:
        return False
    vendidos_por_key[key] = cantidad - 1
    return True


def resolver_destino_cobros_pendientes_dashboard(
    *,
    can_crear_venta,
    can_ver_ventas,
    can_ver_caja,
    can_tomar_cola_cobro,
    modo_cobro_exclusivo_cajero,
    date_from,
    date_to,
):
    if can_tomar_cola_cobro:
        return {
            'endpoint': 'caja.cobros_pendientes',
            'params': {},
            'label': 'Abrir cobros',
            'tab_title': 'Pendientes de cobro',
            'tab_icon': 'fas fa-cash-register',
        }

    if can_crear_venta and modo_cobro_exclusivo_cajero and not can_tomar_cola_cobro:
        return {
            'endpoint': 'ventas.registro_vendedor_enviadas',
            'params': {'estado': 'pendiente'},
            'label': 'Ver enviadas',
            'tab_title': 'Pendientes enviados',
            'tab_icon': 'fas fa-clipboard-list',
        }

    if can_crear_venta:
        return {
            'endpoint': 'ventas.pos',
            'params': {},
            'label': 'Abrir POS',
            'tab_title': 'Cobrar servicio',
            'tab_icon': 'fas fa-cash-register',
        }

    if can_ver_ventas:
        return {
            'endpoint': 'ventas.listar',
            'params': {'desde': date_from, 'hasta': date_to},
            'label': 'Ver movimientos',
            'tab_title': 'Ventas',
            'tab_icon': 'fas fa-receipt',
        }

    return {
        'endpoint': 'main.dashboard',
        'params': {},
        'label': 'Seguir viendo',
        'tab_title': 'Dashboard',
        'tab_icon': 'fas fa-home',
    }


def _filtrar_query_ventas_dashboard_por_sesion(query, *, puede_ver_otras_cajas: bool, sesion_caja_id: int | None):
    if puede_ver_otras_cajas:
        return query
    if sesion_caja_id:
        return query.filter(Venta.id_sesion_caja == int(sesion_caja_id))
    return query.filter(False)


def obtener_resumen_servicios_realizados_dashboard(
    *,
    today,
    limit: int = 5,
    puede_ver_otras_cajas: bool,
    sesion_caja_id: int | None,
) -> dict[str, Any]:
    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    limit = max(int(limit or 0), 1)

    cantidad_expr = db.func.coalesce(db.func.sum(DetalleVenta.cantidad), 0)
    total_expr = db.func.coalesce(db.func.sum(DetalleVenta.subtotal), 0)

    resumen_query = (
        db.session.query(
            cantidad_expr.label('total_count'),
            total_expr.label('total_monto'),
        )
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            DetalleVenta.id_servicio.isnot(None),
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
    )
    resumen_query = _filtrar_query_ventas_dashboard_por_sesion(
        resumen_query,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=sesion_caja_id,
    )
    total_count, total_monto = resumen_query.one()

    servicios_query = (
        db.session.query(
            Servicio.id_servicio,
            Servicio.nombre,
            cantidad_expr.label('cantidad'),
            total_expr.label('total'),
        )
        .join(DetalleVenta, DetalleVenta.id_servicio == Servicio.id_servicio)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
    )
    servicios_query = _filtrar_query_ventas_dashboard_por_sesion(
        servicios_query,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=sesion_caja_id,
    )
    servicios_query = (
        servicios_query
        .group_by(Servicio.id_servicio, Servicio.nombre)
        .order_by(cantidad_expr.desc(), total_expr.desc(), Servicio.nombre.asc())
        .limit(limit)
    )
    rows = servicios_query.all()

    max_cantidad = max((int(row.cantidad or 0) for row in rows), default=0)
    items = []
    for index, row in enumerate(rows):
        cantidad = int(row.cantidad or 0)
        porcentaje = int(round((cantidad / max_cantidad) * 100)) if max_cantidad > 0 else 0
        items.append({
            'id_servicio': int(row.id_servicio),
            'nombre': row.nombre or 'Servicio',
            'cantidad': cantidad,
            'total': float(row.total or 0),
            'porcentaje': max(0, min(porcentaje, 100)),
            'color_class': SERVICIOS_REALIZADOS_BAR_CLASSES[index % len(SERVICIOS_REALIZADOS_BAR_CLASSES)],
        })

    return {
        'items': items,
        'total_count': int(total_count or 0),
        'total_monto': float(total_monto or 0),
    }


def obtener_resumen_cobros_pendientes_dashboard(limit=3) -> dict[str, Any]:
    query_base = (
        ClienteServicio.query
        .filter(
            ClienteServicio.id_venta.is_(None),
            ClienteServicio.estado != 'cancelado',
        )
    )

    items_cliente_servicio = (
        query_base.options(
            joinedload(ClienteServicio.cliente),
            joinedload(ClienteServicio.servicio),
        )
        .order_by(ClienteServicio.fecha_solicitud.asc(), ClienteServicio.id_cliente_servicio.asc())
        .all()
    )

    today = today_local()
    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    agenda_items = (
        AgendaActividad.query.options(joinedload(AgendaActividad.cliente).load_only(Cliente.id_cliente, Cliente.nombre))
        .filter(
            AgendaActividad.tipo == 'cita',
            AgendaActividad.cliente_id.isnot(None),
            AgendaActividad.cliente_servicio_id.is_(None),
            AgendaActividad.venta_id.is_(None),
            AgendaActividad.estado.in_(['pendiente', 'hecha']),
            AgendaActividad.fecha_inicio >= start_utc,
            AgendaActividad.fecha_inicio < end_utc,
        )
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .all()
    )

    servicios_por_actividad = {}
    for actividad in agenda_items:
        turno_tipo = infer_turno_peluqueria_tipo_from_title(actividad.titulo)
        servicios_por_actividad[int(actividad.id)] = resolve_turno_peluqueria_catalog_service(
            turno_tipo_id=turno_tipo,
            title=actividad.titulo,
        )
    vendidos_por_key = _contar_servicios_agenda_vendidos(
        agenda_items,
        servicios_por_actividad,
        start_utc,
        end_utc,
    )

    items_agenda = []
    for actividad in agenda_items:
        turno_tipo = infer_turno_peluqueria_tipo_from_title(actividad.titulo)
        servicio = servicios_por_actividad.get(int(actividad.id))
        if servicio is not None and not is_turno_peluqueria_catalog_service_chargeable(servicio):
            continue
        if _consumir_si_turno_ya_fue_cobrado(actividad, servicio, vendidos_por_key):
            continue
        params = {
            'agenda_turno_cliente_id': int(actividad.cliente_id),
            'agenda_turno_actividad_id': int(actividad.id),
        }
        if servicio is not None:
            params['agenda_turno_servicio_id'] = int(servicio.id_servicio)
        else:
            params['agenda_turno_titulo'] = actividad.titulo or TURNO_PELUQUERIA_TIPO_LABELS.get(turno_tipo, 'Turno')
        items_agenda.append({
            'id_cliente_servicio': None,
            'agenda_actividad_id': int(actividad.id),
            'cliente': {'nombre': actividad.cliente.nombre if actividad.cliente else 'Consumidor Final'},
            'servicio': {'nombre': (servicio.nombre if servicio is not None else TURNO_PELUQUERIA_TIPO_LABELS.get(turno_tipo, actividad.titulo or 'Turno'))},
            'estado_display': 'Turno sin cobrar',
            'subtotal': float(servicio.precio or 0) if servicio is not None else 0,
            'fecha_solicitud': actividad.fecha_inicio,
            'cobrar_url': url_for('ventas.pos', **params),
        })

    total_count = len(items_cliente_servicio) + len(items_agenda)
    total_monto = float(sum(float(item.subtotal or 0) for item in items_cliente_servicio) + sum(float(item.get('subtotal') or 0) for item in items_agenda))
    items = [*items_cliente_servicio, *items_agenda]
    items.sort(key=lambda item: (_item_fecha_solicitud(item), _item_id_orden(item)))
    if limit is not None:
        limit = max(int(limit or 0), 1)
        items = items[:limit]

    return {
        'items': items,
        'total_count': total_count,
        'total_monto': total_monto,
    }


def serializar_resumen_cobros_pendientes_dashboard(items) -> list[dict[str, Any]]:
    resultado = []
    for item in items or []:
        if isinstance(item, dict):
            cliente = item.get('cliente') or {}
            servicio = item.get('servicio') or {}
            resultado.append({
                'id_cliente_servicio': item.get('id_cliente_servicio'),
                'agenda_actividad_id': item.get('agenda_actividad_id'),
                'cliente_nombre': cliente.get('nombre') or 'Consumidor Final',
                'servicio_nombre': servicio.get('nombre') or 'Servicio eliminado',
                'estado_display': item.get('estado_display') or 'Pendiente',
                'subtotal': float(item.get('subtotal') or 0),
                'fecha_solicitud_label': local_strftime(item.get('fecha_solicitud'), '%d/%m %H:%M') if item.get('fecha_solicitud') else '',
                'cobrar_url': item.get('cobrar_url') or '',
            })
            continue

        cliente = getattr(getattr(item, 'cliente', None), 'nombre', None) or 'Consumidor Final'
        servicio = getattr(getattr(item, 'servicio', None), 'nombre', None) or 'Servicio eliminado'
        cliente_servicio_id = int(getattr(item, 'id_cliente_servicio', 0) or 0) or None
        cobrar_url = url_for('ventas.pos', cliente_servicio_id=cliente_servicio_id) if cliente_servicio_id else ''
        resultado.append({
            'id_cliente_servicio': cliente_servicio_id,
            'agenda_actividad_id': None,
            'cliente_nombre': cliente,
            'servicio_nombre': servicio,
            'estado_display': getattr(item, 'estado_display', None) or getattr(item, 'estado', None) or 'Pendiente',
            'subtotal': float(getattr(item, 'subtotal', 0) or 0),
            'fecha_solicitud_label': local_strftime(getattr(item, 'fecha_solicitud', None), '%d/%m %H:%M') if getattr(item, 'fecha_solicitud', None) else '',
            'cobrar_url': cobrar_url,
        })
    return resultado


def _duration_label(total_minutes: int | None) -> str:
    if total_minutes is None:
        return ''
    minutes = max(int(total_minutes or 0), 0)
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f'{hours} h {remainder} min'
    if hours:
        return f'{hours} h'
    return f'{remainder} min'


def _detalle_profesional_base(usuario) -> dict[str, Any]:
    return {
        'user_id': int(getattr(usuario, 'id_usuario', 0) or 0),
        'nombre': getattr(usuario, 'nombre_completo', None) or getattr(usuario, 'username', None) or 'Profesional',
        'rol_nombre': getattr(getattr(usuario, 'rol', None), 'nombre', None) or 'Profesional',
        'ocupado': False,
        'estado_label': 'Libre',
        'estado_color': 'emerald',
        'cliente_nombre': '',
        'servicio_nombre': '',
        'titulo': '',
        'inicio_label': '',
        'fin_label': '',
        'duracion_label': '',
        'transcurrido_label': '',
        'restante_label': '',
        'restante_caption': '',
        'sesiones_activas_count': 0,
        'cobrado': False,
        'cobrado_label': '',
        'actividad_id': None,
        'cliente_servicio_id': None,
        'sin_sesion_mensaje': 'No tiene un turno en atención en este momento.',
    }


def _detalle_profesional_activo(actividad, *, sesiones_activas_count: int) -> dict[str, Any]:
    asignacion = getattr(actividad, 'cliente_servicio', None)
    cliente = getattr(getattr(asignacion, 'cliente', None), 'nombre', None) or 'Consumidor Final'
    servicio = getattr(getattr(asignacion, 'servicio', None), 'nombre', None) or 'Servicio'
    inicio_local = utc_naive_to_local(getattr(actividad, 'fecha_inicio', None))
    fin_local = utc_naive_to_local(getattr(actividad, 'fecha_fin', None))
    referencia_local = now_local()

    duracion_minutos = None
    transcurrido_minutos = None
    restante_minutos = None
    restante_label = ''
    restante_caption = ''

    if inicio_local and fin_local and fin_local >= inicio_local:
        duracion_minutos = int((fin_local - inicio_local).total_seconds() // 60)
    if inicio_local:
        transcurrido_minutos = max(int((referencia_local - inicio_local).total_seconds() // 60), 0)
    if fin_local:
        delta_fin = int((fin_local - referencia_local).total_seconds() // 60)
        if delta_fin >= 0:
            restante_minutos = delta_fin
            restante_label = _duration_label(restante_minutos)
            restante_caption = 'Falta para terminar'
        else:
            restante_label = _duration_label(abs(delta_fin))
            restante_caption = 'Pasado del horario'

    return {
        'ocupado': True,
        'estado_label': 'Ocupado',
        'estado_color': 'blue',
        'cliente_nombre': cliente,
        'servicio_nombre': servicio,
        'titulo': getattr(actividad, 'titulo', None) or servicio,
        'inicio_label': local_strftime(getattr(actividad, 'fecha_inicio', None), '%H:%M'),
        'fin_label': local_strftime(getattr(actividad, 'fecha_fin', None), '%H:%M') if getattr(actividad, 'fecha_fin', None) else '',
        'duracion_label': _duration_label(duracion_minutos),
        'transcurrido_label': _duration_label(transcurrido_minutos),
        'restante_label': restante_label,
        'restante_caption': restante_caption,
        'sesiones_activas_count': max(int(sesiones_activas_count or 0), 1),
        'cobrado': bool(asignacion and getattr(asignacion, 'id_venta', None)),
        'cobrado_label': 'Cobrado' if asignacion and getattr(asignacion, 'id_venta', None) else 'Sin cobrar',
        'actividad_id': int(getattr(actividad, 'id', 0) or 0) or None,
        'cliente_servicio_id': int(getattr(actividad, 'cliente_servicio_id', 0) or 0) or None,
        'sin_sesion_mensaje': '',
    }


def obtener_estado_profesionales_dashboard(usuarios, *, can_ver_agenda: bool, today) -> tuple[set[int], dict[str, dict[str, Any]]]:
    detalles = {}
    user_ids = []
    for usuario in usuarios or []:
        user_id = int(getattr(usuario, 'id_usuario', 0) or 0)
        if user_id <= 0:
            continue
        user_ids.append(user_id)
        detalles[str(user_id)] = _detalle_profesional_base(usuario)

    if not can_ver_agenda or not user_ids:
        return set(), detalles

    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    actividades = (
        AgendaActividad.query.options(
            joinedload(AgendaActividad.cliente_servicio).joinedload(ClienteServicio.cliente).load_only(Cliente.id_cliente, Cliente.nombre),
            joinedload(AgendaActividad.cliente_servicio).joinedload(ClienteServicio.servicio),
        )
        .join(ClienteServicio, ClienteServicio.id_cliente_servicio == AgendaActividad.cliente_servicio_id)
        .filter(
            AgendaActividad.usuario_id.in_(user_ids),
            AgendaActividad.estado == 'pendiente',
            AgendaActividad.fecha_inicio >= start_utc,
            AgendaActividad.fecha_inicio < end_utc,
            ClienteServicio.estado == 'en_proceso',
        )
        .order_by(AgendaActividad.usuario_id.asc(), AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .all()
    )

    actividad_por_usuario = {}
    sesiones_por_usuario = {}
    for actividad in actividades:
        user_id = int(getattr(actividad, 'usuario_id', 0) or 0)
        if user_id <= 0:
            continue
        sesiones_por_usuario[user_id] = int(sesiones_por_usuario.get(user_id, 0) or 0) + 1
        actividad_por_usuario.setdefault(user_id, actividad)

    ocupados = set(actividad_por_usuario.keys())
    for user_id, actividad in actividad_por_usuario.items():
        key = str(user_id)
        if key not in detalles:
            continue
        detalles[key].update(
            _detalle_profesional_activo(
                actividad,
                sesiones_activas_count=sesiones_por_usuario.get(user_id, 1),
            )
        )

    return ocupados, detalles
