from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from app import db
from app.models import AgendaActividad, Cliente, ClienteServicio
from app.services.agenda_turnos_peluqueria import (
    TURNO_PELUQUERIA_TIPO_LABELS,
    infer_turno_peluqueria_tipo_from_title,
    resolve_turno_peluqueria_catalog_service,
)
from app.utils.helpers import local_strftime, today_local, utc_bounds_for_local_dates
from flask import url_for


def _item_fecha_solicitud(item):
    if isinstance(item, dict):
        return item.get('fecha_solicitud')
    return getattr(item, 'fecha_solicitud', None)


def _item_id_orden(item):
    if isinstance(item, dict):
        return 0
    return int(getattr(item, 'id_cliente_servicio', 0) or 0)


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
            AgendaActividad.estado.in_(['pendiente', 'hecha']),
            AgendaActividad.fecha_inicio >= start_utc,
            AgendaActividad.fecha_inicio < end_utc,
        )
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .all()
    )

    items_agenda = []
    for actividad in agenda_items:
        turno_tipo = infer_turno_peluqueria_tipo_from_title(actividad.titulo)
        servicio = resolve_turno_peluqueria_catalog_service(turno_tipo_id=turno_tipo, title=actividad.titulo)
        params = {'agenda_turno_cliente_id': int(actividad.cliente_id)}
        if servicio is not None:
            params['agenda_turno_servicio_id'] = int(servicio.id_servicio)
        items_agenda.append({
            'id_cliente_servicio': None,
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
            'cliente_nombre': cliente,
            'servicio_nombre': servicio,
            'estado_display': getattr(item, 'estado_display', None) or getattr(item, 'estado', None) or 'Pendiente',
            'subtotal': float(getattr(item, 'subtotal', 0) or 0),
            'fecha_solicitud_label': local_strftime(getattr(item, 'fecha_solicitud', None), '%d/%m %H:%M') if getattr(item, 'fecha_solicitud', None) else '',
            'cobrar_url': cobrar_url,
        })
    return resultado
