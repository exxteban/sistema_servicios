"""
Rutas principales (Dashboard)
"""
from flask import Blueprint, render_template, request, jsonify, current_app, g
from datetime import timedelta
from flask_login import login_required, current_user
from sqlalchemy import and_, case
from sqlalchemy.orm import load_only, noload
from app import db
from app.models import (
    AgendaActividad,
    Cliente,
    Configuracion,
    PagoCuentaCobrar,
    PedidoClientePago,
    PagoVenta,
    Producto,
    SesionCaja,
    Venta,
)
from app.routes.agenda.actividades import _filtro_mostrar_agenda_para_usuario
from app.utils.helpers import today_local, utc_bounds_for_local_dates, parse_iso_date, local_strftime
from app.services.dashboard_preferences import (
    get_dashboard_quick_actions,
    get_dashboard_view_preference,
    set_dashboard_quick_actions,
    set_dashboard_view_preference,
)
from gastos_corrientes.services import (
    obtener_dashboard_detallado_gastos_corrientes,
    obtener_resumen_dashboard_gastos_corrientes,
)

main_bp = Blueprint('main', __name__)


def _obtener_resumen_agenda_dashboard(can_ver_agenda, today):
    agenda_total_pendientes = 0
    agenda_pendientes_hoy = 0
    agenda_vencidas = 0
    agenda_proximas_actividades = []
    agenda_fecha_hoy_iso = today.isoformat()

    if not can_ver_agenda:
        return {
            'can_ver_agenda': False,
            'total_pendientes': agenda_total_pendientes,
            'pendientes_hoy': agenda_pendientes_hoy,
            'vencidas': agenda_vencidas,
            'proximas_actividades': agenda_proximas_actividades,
            'fecha_hoy_iso': agenda_fecha_hoy_iso,
        }

    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    agenda_pendiente_query = AgendaActividad.query.filter(AgendaActividad.estado == 'pendiente')
    if not (current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')):
        agenda_pendiente_query = agenda_pendiente_query.filter(
            _filtro_mostrar_agenda_para_usuario(current_user.id_usuario)
        )

    rango_hoy = and_(AgendaActividad.fecha_inicio >= start_utc, AgendaActividad.fecha_inicio < end_utc)
    agenda_total_pendientes, agenda_pendientes_hoy, agenda_vencidas = (
        agenda_pendiente_query.with_entities(
            db.func.count(AgendaActividad.id),
            db.func.coalesce(db.func.sum(case((rango_hoy, 1), else_=0)), 0),
            db.func.coalesce(db.func.sum(case((AgendaActividad.fecha_inicio < start_utc, 1), else_=0)), 0),
        ).one()
    )
    proximas_actividades = (
        agenda_pendiente_query
        .options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.titulo,
                AgendaActividad.tipo,
                AgendaActividad.prioridad,
                AgendaActividad.fecha_inicio,
            ),
            noload(AgendaActividad.usuarios_agenda),
            noload(AgendaActividad.usuarios_recordatorio),
        )
        .filter(rango_hoy)
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.desc())
        .limit(5)
        .all()
    )

    agenda_proximas_actividades = [
        {
            'id': actividad.id,
            'titulo': actividad.titulo or '',
            'tipo': actividad.tipo or '',
            'tipo_label': (actividad.tipo or '').replace('_', ' ').title(),
            'prioridad': actividad.prioridad or 'baja',
            'prioridad_label': (actividad.prioridad or 'baja').title(),
            'hora_label': local_strftime(actividad.fecha_inicio, '%H:%M'),
        }
        for actividad in proximas_actividades
    ]

    return {
        'can_ver_agenda': True,
        'total_pendientes': agenda_total_pendientes,
        'pendientes_hoy': agenda_pendientes_hoy,
        'vencidas': agenda_vencidas,
        'proximas_actividades': agenda_proximas_actividades,
        'fecha_hoy_iso': agenda_fecha_hoy_iso,
    }


def _obtener_resumen_gastos_dashboard(can_ver_gastos_corrientes, today):
    if not can_ver_gastos_corrientes:
        return None
    return obtener_resumen_dashboard_gastos_corrientes(today=today)


def _obtener_dashboard_detallado_gastos(can_ver_gastos_corrientes, today):
    if not can_ver_gastos_corrientes:
        return None
    return obtener_dashboard_detallado_gastos_corrientes(today=today)


def _filtrar_query_dashboard_por_sesion(query, *, puede_ver_otras_cajas, sesion_caja, columna_id_sesion):
    if puede_ver_otras_cajas:
        return query
    if sesion_caja:
        return query.filter(columna_id_sesion == sesion_caja.id_sesion)
    return query.filter(False)


def _obtener_totales_cobrados_dashboard(start_date, end_date, *, puede_ver_otras_cajas, sesion_caja):
    start_utc, end_utc = utc_bounds_for_local_dates(start_date, end_date)

    cobros_ventas_q = (
        db.session.query(db.func.sum(PagoVenta.monto))
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
    )
    cobros_ventas_q = _filtrar_query_dashboard_por_sesion(
        cobros_ventas_q,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja=sesion_caja,
        columna_id_sesion=Venta.id_sesion_caja,
    )
    cobrado_en_ventas = float(cobros_ventas_q.scalar() or 0)

    cobros_creditos_q = (
        db.session.query(db.func.sum(PagoCuentaCobrar.monto))
        .filter(
            PagoCuentaCobrar.estado != 'anulado',
            PagoCuentaCobrar.fecha_pago >= start_utc,
            PagoCuentaCobrar.fecha_pago < end_utc,
        )
    )
    cobros_creditos_q = _filtrar_query_dashboard_por_sesion(
        cobros_creditos_q,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja=sesion_caja,
        columna_id_sesion=PagoCuentaCobrar.id_sesion_caja,
    )
    cobrado_en_creditos = float(cobros_creditos_q.scalar() or 0)

    cobros_pedidos_q = (
        db.session.query(db.func.sum(PedidoClientePago.monto))
        .filter(
            PedidoClientePago.estado == 'activo',
            PedidoClientePago.fecha_pago >= start_utc,
            PedidoClientePago.fecha_pago < end_utc,
        )
    )
    cobros_pedidos_q = _filtrar_query_dashboard_por_sesion(
        cobros_pedidos_q,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja=sesion_caja,
        columna_id_sesion=PedidoClientePago.id_sesion_caja,
    )
    cobrado_en_pedidos = float(cobros_pedidos_q.scalar() or 0)

    return {
        'total_cobrado': cobrado_en_ventas + cobrado_en_creditos + cobrado_en_pedidos,
        'cobrado_en_ventas': cobrado_en_ventas,
        'cobrado_en_creditos': cobrado_en_creditos,
        'cobrado_en_pedidos': cobrado_en_pedidos,
    }

@main_bp.route('/health')
def health():
    return 'ok', 200, {'Content-Type': 'text/plain; charset=utf-8'}


@main_bp.route('/api/health')
def api_health():
    return jsonify({'ok': True}), 200


@main_bp.route('/')
@login_required
def dashboard():
    """Dashboard principal"""
    cierre_id = request.args.get('cierre_id', type=int)
    try:
        req_id = getattr(g, 'request_id', None)
        prefix = f'[{req_id}] ' if req_id else ''
        current_app.logger.info(f"{prefix}Dashboard: cierre_id={cierre_id} user_id={getattr(current_user, 'id_usuario', None)}")
    except Exception:
        pass
    can_crear_venta = current_user.tiene_permiso('crear_venta')
    can_ver_ventas = current_user.tiene_permiso('ver_ventas')
    can_ver_reporte_ventas = current_user.tiene_permiso('ver_reporte_ventas')
    can_ver_inventario = current_user.tiene_permiso('ver_inventario')
    can_ver_reporte_inventario = current_user.tiene_permiso('ver_reporte_inventario')
    can_ver_caja = current_user.tiene_permiso('ver_caja')
    can_abrir_caja = current_user.tiene_permiso('abrir_caja')
    can_ver_reportes = current_user.tiene_permiso('ver_reportes')
    can_tomar_cola_cobro = current_user.tiene_permiso('tomar_cola_cobro')
    can_ver_agenda = current_user.tiene_permiso('agenda_acceso')
    can_ver_gastos_corrientes = current_user.es_admin() or current_user.tiene_permiso('ver_gastos_corrientes')
    can_ver_inteligencia = current_user.es_admin() or can_ver_reportes
    modo_cobro_exclusivo_cajero = (
        Configuracion.obtener_bool('caja_flujo_enviado_desde_vendedor', default=False)
        and Configuracion.obtener_bool('caja_exigir_cajero_para_cobro', default=False)
    )
    mostrar_alerta_sin_caja = not (
        modo_cobro_exclusivo_cajero
        and can_crear_venta
        and not can_tomar_cola_cobro
    )

    total_productos = 0
    productos_stock_bajo = 0
    if can_ver_inventario or can_ver_reporte_inventario:
        total_productos = Producto.query.filter_by(activo=True).count()
        productos_stock_bajo = Producto.query.filter(
            Producto.activo == True,
            Producto.stock_actual <= Producto.stock_minimo
        ).count()
    
    # Sesión de caja actual
    puede_ver_otras_cajas = current_user.es_admin() or current_user.tiene_permiso('ver_otras_cajas')
    sesion_caja = None
    if can_crear_venta or can_ver_caja or can_abrir_caja:
        sesion_caja = SesionCaja.query.filter_by(
            id_usuario=current_user.id_usuario,
            estado='abierta'
        ).first()
    
    ventas_hoy = 0
    if can_ver_reporte_ventas:
        today = today_local()
        start_utc, end_utc = utc_bounds_for_local_dates(today, today)
        q_ventas_hoy = Venta.query.filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc
        )
        if not puede_ver_otras_cajas:
            if sesion_caja:
                q_ventas_hoy = q_ventas_hoy.filter(Venta.id_sesion_caja == sesion_caja.id_sesion)
            else:
                # Sin caja abierta y sin permiso para ver otras: no ve ventas de otros
                q_ventas_hoy = q_ventas_hoy.filter(False)
        ventas_hoy = q_ventas_hoy.count()

    # Total vendido con rango configurable
    # Usar preferencia guardada si no se especifica rango en URL
    range_type = request.args.get('range', current_user.dashboard_range_preference or 'hoy')
    
    today = today_local()
    
    custom_desde = request.args.get('desde')
    custom_hasta = request.args.get('hasta')

    if range_type == 'custom':
        start_date = parse_iso_date(custom_desde) or today
        end_date = parse_iso_date(custom_hasta) or start_date
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date
        range_label = f"{start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"
    elif range_type == 'semana':
        start_date = today - timedelta(days=today.weekday()) # Lunes de esta semana
        end_date = today
        range_label = "Esta Semana"
    elif range_type == 'mes':
        start_date = today.replace(day=1)
        end_date = today
        range_label = "Este Mes"
    else: # hoy
        start_date = today
        end_date = today
        range_label = "Hoy"
    
    total_cobrado_display = 0
    cobrado_en_ventas_display = 0
    cobrado_en_creditos_display = 0
    cobrado_en_pedidos_display = 0
    if can_ver_ventas:
        if range_type != current_user.dashboard_range_preference and range_type in ['hoy', 'semana', 'mes']:
            current_user.dashboard_range_preference = range_type
            db.session.commit()

        totales_cobro = _obtener_totales_cobrados_dashboard(
            start_date,
            end_date,
            puede_ver_otras_cajas=puede_ver_otras_cajas,
            sesion_caja=sesion_caja,
        )
        total_cobrado_display = totales_cobro['total_cobrado']
        cobrado_en_ventas_display = totales_cobro['cobrado_en_ventas']
        cobrado_en_creditos_display = totales_cobro['cobrado_en_creditos']
        cobrado_en_pedidos_display = totales_cobro['cobrado_en_pedidos']

    agenda_resumen = _obtener_resumen_agenda_dashboard(can_ver_agenda, today)
    gastos_corrientes_resumen = _obtener_resumen_gastos_dashboard(can_ver_gastos_corrientes, today)
    gastos_corrientes_dashboard = _obtener_dashboard_detallado_gastos(can_ver_gastos_corrientes, today)
    dashboard_quick_actions_available, dashboard_quick_actions_selected = get_dashboard_quick_actions(current_user)
    dashboard_view_preference = get_dashboard_view_preference(current_user)
    
    return render_template('dashboard.html',
        total_productos=total_productos,
        productos_stock_bajo=productos_stock_bajo,
        sesion_caja=sesion_caja,
        cierre_id=cierre_id,
        ventas_hoy=ventas_hoy,
        total_cobrado_display=total_cobrado_display,
        cobrado_en_ventas_display=cobrado_en_ventas_display,
        cobrado_en_creditos_display=cobrado_en_creditos_display,
        cobrado_en_pedidos_display=cobrado_en_pedidos_display,
        range_label=range_label,
        current_range=range_type,
        date_from=start_date.isoformat(),
        date_to=end_date.isoformat(),
        custom_desde=(start_date.isoformat() if range_type == 'custom' else (custom_desde or '')),
        custom_hasta=(end_date.isoformat() if range_type == 'custom' else (custom_hasta or '')),
        can_crear_venta=can_crear_venta,
        can_ver_ventas=can_ver_ventas,
        can_ver_reporte_ventas=can_ver_reporte_ventas,
        can_ver_inventario=can_ver_inventario,
        can_ver_reporte_inventario=can_ver_reporte_inventario,
        can_ver_caja=can_ver_caja,
        can_abrir_caja=can_abrir_caja,
        can_ver_reportes=can_ver_reportes,
        can_ver_inteligencia=can_ver_inteligencia,
        can_ver_gastos_corrientes=can_ver_gastos_corrientes,
        gastos_corrientes_resumen=gastos_corrientes_resumen,
        gastos_corrientes_dashboard=gastos_corrientes_dashboard,
        dashboard_view_preference=dashboard_view_preference,
        dashboard_quick_actions_available=dashboard_quick_actions_available,
        dashboard_quick_actions_selected=dashboard_quick_actions_selected,
        mostrar_alerta_sin_caja=mostrar_alerta_sin_caja,
        can_ver_agenda=can_ver_agenda,
        agenda_total_pendientes=agenda_resumen['total_pendientes'],
        agenda_pendientes_hoy=agenda_resumen['pendientes_hoy'],
        agenda_vencidas=agenda_resumen['vencidas'],
        agenda_proximas_actividades=agenda_resumen['proximas_actividades'],
        agenda_fecha_hoy_iso=agenda_resumen['fecha_hoy_iso'],
    )


@main_bp.route('/api/dashboard/preferencias', methods=['POST'])
@login_required
def api_dashboard_preferencias():
    data = request.get_json(silent=True) or {}
    response = {}

    if 'dashboard_view' in data:
        response['dashboard_view'] = set_dashboard_view_preference(
            current_user,
            data.get('dashboard_view'),
        )

    if 'quick_actions' in data:
        action_ids = data.get('quick_actions')
        if not isinstance(action_ids, list):
            action_ids = []
        available, selected = set_dashboard_quick_actions(current_user, action_ids)
        response['quick_actions_available'] = available
        response['quick_actions_selected'] = selected

    if response:
        db.session.commit()
    return jsonify({'ok': True, **response})


@main_bp.route('/api/dashboard/totales')
@login_required
def api_dashboard_totales():
    can_crear_venta = current_user.tiene_permiso('crear_venta')
    can_ver_ventas = current_user.tiene_permiso('ver_ventas')
    can_ver_reporte_ventas = current_user.tiene_permiso('ver_reporte_ventas')
    can_ver_caja = current_user.tiene_permiso('ver_caja')
    can_abrir_caja = current_user.tiene_permiso('abrir_caja')
    can_ver_agenda = current_user.tiene_permiso('agenda_acceso')
    can_ver_gastos_corrientes = current_user.es_admin() or current_user.tiene_permiso('ver_gastos_corrientes')

    puede_ver_otras_cajas = current_user.es_admin() or current_user.tiene_permiso('ver_otras_cajas')
    sesion_caja = None
    if can_crear_venta or can_ver_caja or can_abrir_caja:
        sesion_caja = SesionCaja.query.filter_by(
            id_usuario=current_user.id_usuario,
            estado='abierta'
        ).first()

    ventas_hoy = None
    if can_ver_reporte_ventas:
        today = today_local()
        start_utc, end_utc = utc_bounds_for_local_dates(today, today)
        q_ventas_hoy = Venta.query.filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc
        )
        if not puede_ver_otras_cajas:
            if sesion_caja:
                q_ventas_hoy = q_ventas_hoy.filter(Venta.id_sesion_caja == sesion_caja.id_sesion)
            else:
                q_ventas_hoy = q_ventas_hoy.filter(False)
        ventas_hoy = q_ventas_hoy.count()

    range_type = request.args.get('range') or (current_user.dashboard_range_preference or 'hoy')
    today = today_local()

    custom_desde = request.args.get('desde')
    custom_hasta = request.args.get('hasta')

    if range_type == 'custom':
        start_date = parse_iso_date(custom_desde) or today
        end_date = parse_iso_date(custom_hasta) or start_date
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date
        range_label = f"{start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"
    elif range_type == 'semana':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
        range_label = "Esta Semana"
    elif range_type == 'mes':
        start_date = today.replace(day=1)
        end_date = today
        range_label = "Este Mes"
    else:
        start_date = today
        end_date = today
        range_label = "Hoy"

    total_cobrado = None
    cobrado_en_ventas = None
    cobrado_en_creditos = None
    cobrado_en_pedidos = None
    if can_ver_ventas:
        totales_cobro = _obtener_totales_cobrados_dashboard(
            start_date,
            end_date,
            puede_ver_otras_cajas=puede_ver_otras_cajas,
            sesion_caja=sesion_caja,
        )
        total_cobrado = totales_cobro['total_cobrado']
        cobrado_en_ventas = totales_cobro['cobrado_en_ventas']
        cobrado_en_creditos = totales_cobro['cobrado_en_creditos']
        cobrado_en_pedidos = totales_cobro['cobrado_en_pedidos']

    total_cobrado_formatted = None
    if total_cobrado is not None:
        try:
            value = float(total_cobrado)
        except Exception:
            value = 0.0
        total_cobrado_formatted = "₲ " + "{:,.0f}".format(value).replace(",", ".")

    agenda_resumen = _obtener_resumen_agenda_dashboard(can_ver_agenda, today)
    gastos_corrientes_resumen = _obtener_resumen_gastos_dashboard(can_ver_gastos_corrientes, today)

    return jsonify({
        'ventas_hoy': ventas_hoy,
        'total_cobrado': (float(total_cobrado) if total_cobrado is not None else None),
        'total_cobrado_formatted': total_cobrado_formatted,
        'cobrado_en_ventas': (float(cobrado_en_ventas) if cobrado_en_ventas is not None else None),
        'cobrado_en_creditos': (float(cobrado_en_creditos) if cobrado_en_creditos is not None else None),
        'cobrado_en_pedidos': (float(cobrado_en_pedidos) if cobrado_en_pedidos is not None else None),
        'total_ventas': (float(total_cobrado) if total_cobrado is not None else None),
        'total_ventas_formatted': total_cobrado_formatted,
        'range_label': range_label,
        'current_range': range_type,
        'date_from': start_date.isoformat() if start_date else None,
        'date_to': end_date.isoformat() if end_date else None,
        'agenda': (agenda_resumen if can_ver_agenda else None),
        'gastos_corrientes': (
            {
                **gastos_corrientes_resumen,
                'total_pendiente': float(gastos_corrientes_resumen['total_pendiente']),
            }
            if gastos_corrientes_resumen
            else None
        ),
    })
