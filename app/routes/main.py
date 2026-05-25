"""
Rutas principales (Dashboard)
"""
from flask import Blueprint, render_template, request, jsonify, current_app, g, url_for, redirect
from datetime import timedelta
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from app import db
from app.models import (
    Configuracion,
    PagoCuentaCobrar,
    PedidoClientePago,
    PagoVenta,
    Producto,
    SesionCaja,
    Usuario,
    Venta,
)
from app.routes.agenda.visibilidad import query_usuarios_agenda_visibles
from app.utils.helpers import today_local, utc_bounds_for_local_dates, parse_iso_date
from app.services.dashboard_agenda import (
    obtener_resumen_agenda_dashboard,
    obtener_resumen_en_atencion_dashboard,
)
from app.services.dashboard_preferences import (
    set_dashboard_service_card_order,
    get_dashboard_service_cards,
    get_dashboard_quick_actions,
    get_dashboard_view_preference,
    set_dashboard_service_cards,
    set_dashboard_quick_actions,
    set_dashboard_view_preference,
)
from app.services.dashboard_negocio import obtener_dashboard_negocio_actual
from app.services.dashboard_clientes import obtener_resumen_clientes_dashboard
from app.services.dashboard_servicios import (
    obtener_estado_profesionales_dashboard,
    obtener_resumen_cobros_pendientes_dashboard,
    obtener_resumen_servicios_realizados_dashboard,
    resolver_destino_cobros_pendientes_dashboard,
    serializar_resumen_cobros_pendientes_dashboard,
)
from gastos_corrientes.services import (
    obtener_dashboard_detallado_gastos_corrientes,
    obtener_resumen_dashboard_gastos_corrientes,
)
from gastronomia.services.modo_operacion import gastronomia_activa

main_bp = Blueprint('main', __name__)


def _obtener_resumen_agenda_dashboard(can_ver_agenda, today):
    return obtener_resumen_agenda_dashboard(can_ver_agenda, today, usuario=current_user)


def _obtener_resumen_en_atencion_dashboard(can_ver_agenda, today):
    return obtener_resumen_en_atencion_dashboard(can_ver_agenda, today, usuario=current_user)


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
    if gastronomia_activa():
        return redirect(url_for('gastronomia.dashboard'))
    can_crear_venta = current_user.tiene_permiso('crear_venta')
    can_ver_ventas = current_user.tiene_permiso('ver_ventas')
    can_ver_reporte_ventas = current_user.tiene_permiso('ver_reporte_ventas')
    can_ver_inventario = current_user.tiene_permiso('ver_inventario')
    can_ver_reporte_inventario = current_user.tiene_permiso('ver_reporte_inventario')
    can_ver_caja = current_user.tiene_permiso('ver_caja')
    can_abrir_caja = current_user.tiene_permiso('abrir_caja')
    can_ver_reportes = current_user.tiene_permiso('ver_reportes')
    can_tomar_cola_cobro = current_user.es_admin() or current_user.tiene_permiso('tomar_cola_cobro')
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
            Producto.es_servicio.isnot(True),
            Producto.stock_actual <= Producto.stock_minimo
        ).count()
        productos_stock_bajo_lista = Producto.query.filter(
            Producto.activo == True,
            Producto.es_servicio.isnot(True),
            Producto.stock_actual <= Producto.stock_minimo
        ).order_by(Producto.stock_actual.asc()).limit(5).all()
    else:
        productos_stock_bajo_lista = []
    
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
    en_atencion_resumen = _obtener_resumen_en_atencion_dashboard(can_ver_agenda, today)
    gastos_corrientes_resumen = _obtener_resumen_gastos_dashboard(can_ver_gastos_corrientes, today)
    gastos_corrientes_dashboard = _obtener_dashboard_detallado_gastos(can_ver_gastos_corrientes, today)
    dashboard_quick_actions_available, dashboard_quick_actions_selected = get_dashboard_quick_actions(current_user)
    dashboard_service_cards_available, dashboard_service_cards_selected, dashboard_service_cards_order = get_dashboard_service_cards(current_user)
    dashboard_view_preference = get_dashboard_view_preference(current_user)
    dashboard_negocio = obtener_dashboard_negocio_actual()
    dashboard_cobros_pendientes_destino = resolver_destino_cobros_pendientes_dashboard(
        can_crear_venta=can_crear_venta,
        can_ver_ventas=can_ver_ventas,
        can_ver_caja=can_ver_caja,
        can_tomar_cola_cobro=can_tomar_cola_cobro,
        modo_cobro_exclusivo_cajero=modo_cobro_exclusivo_cajero,
        date_from=start_date.isoformat(),
        date_to=end_date.isoformat(),
    )
    dashboard_cobros_pendientes_url = url_for(
        dashboard_cobros_pendientes_destino['endpoint'],
        **dashboard_cobros_pendientes_destino['params'],
    )
    dashboard_servicios_cobros_pendientes = obtener_resumen_cobros_pendientes_dashboard(limit=3)
    dashboard_servicios_realizados = obtener_resumen_servicios_realizados_dashboard(
        today=today,
        limit=5,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=(int(sesion_caja.id_sesion) if sesion_caja else None),
    )
    dashboard_clientes_resumen = obtener_resumen_clientes_dashboard(
        today=today,
        can_ver_agenda=can_ver_agenda,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=(int(sesion_caja.id_sesion) if sesion_caja else None),
    )

    profesionales_activos = 0
    usuarios_activos_lista = []
    usuarios_ocupados_ids = set()
    dashboard_profesionales_detalle = {}
    if dashboard_negocio.get('full_template'):
        profesionales_query = query_usuarios_agenda_visibles()
        profesionales_activos = profesionales_query.count()
        usuarios_activos_lista = profesionales_query.options(joinedload(Usuario.rol)).limit(5).all()
        usuarios_ocupados_ids, dashboard_profesionales_detalle = obtener_estado_profesionales_dashboard(
            usuarios_activos_lista,
            can_ver_agenda=can_ver_agenda,
            today=today,
        )

    template_dashboard = dashboard_negocio.get('full_template') or 'dashboard.html'

    return render_template(template_dashboard,
        total_productos=total_productos,
        productos_stock_bajo=productos_stock_bajo,
        productos_stock_bajo_lista=productos_stock_bajo_lista,
        profesionales_activos=profesionales_activos,
        usuarios_activos_lista=usuarios_activos_lista,
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
        dashboard_negocio=dashboard_negocio,
        dashboard_quick_actions_available=dashboard_quick_actions_available,
        dashboard_quick_actions_selected=dashboard_quick_actions_selected,
        dashboard_service_cards_available=dashboard_service_cards_available,
        dashboard_service_cards_selected=dashboard_service_cards_selected,
        dashboard_service_cards_order=dashboard_service_cards_order,
        dashboard_cobros_pendientes_url=dashboard_cobros_pendientes_url,
        dashboard_cobros_pendientes_label=dashboard_cobros_pendientes_destino['label'],
        dashboard_cobros_pendientes_tab_title=dashboard_cobros_pendientes_destino['tab_title'],
        dashboard_cobros_pendientes_tab_icon=dashboard_cobros_pendientes_destino['tab_icon'],
        dashboard_servicios_cobros_pendientes=dashboard_servicios_cobros_pendientes['items'],
        dashboard_servicios_cobros_pendientes_total_count=dashboard_servicios_cobros_pendientes['total_count'],
        dashboard_servicios_cobros_pendientes_total_monto=dashboard_servicios_cobros_pendientes['total_monto'],
        dashboard_servicios_realizados=dashboard_servicios_realizados['items'],
        dashboard_servicios_realizados_total_count=dashboard_servicios_realizados['total_count'],
        dashboard_servicios_realizados_total_monto=dashboard_servicios_realizados['total_monto'],
        dashboard_clientes_resumen=dashboard_clientes_resumen,
        mostrar_alerta_sin_caja=mostrar_alerta_sin_caja,
        can_ver_agenda=can_ver_agenda,
        agenda_total_pendientes=agenda_resumen['total_pendientes'],
        agenda_pendientes_hoy=agenda_resumen['pendientes_hoy'],
        agenda_vencidas=agenda_resumen['vencidas'],
        agenda_proximas_actividades=agenda_resumen['proximas_actividades'],
        agenda_turnero_actividades=agenda_resumen.get('turnero_actividades', []),
        agenda_fecha_hoy_iso=agenda_resumen['fecha_hoy_iso'],
        dashboard_en_atencion_count=en_atencion_resumen['count'],
        dashboard_en_atencion_items=en_atencion_resumen['items'],
        usuarios_ocupados_ids=usuarios_ocupados_ids,
        dashboard_profesionales_detalle=dashboard_profesionales_detalle,
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

    if 'service_cards' in data:
        card_ids = data.get('service_cards')
        if not isinstance(card_ids, list):
            card_ids = []
        available, selected, order = set_dashboard_service_cards(current_user, card_ids)
        response['service_cards_available'] = available
        response['service_cards_selected'] = selected
        response['service_card_order'] = order

    if 'service_card_order' in data:
        order_ids = data.get('service_card_order')
        if not isinstance(order_ids, list):
            order_ids = []
        available, selected, order = set_dashboard_service_card_order(current_user, order_ids)
        response['service_cards_available'] = available
        response['service_cards_selected'] = selected
        response['service_card_order'] = order

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
    cobros_pendientes_resumen = obtener_resumen_cobros_pendientes_dashboard(limit=3)
    servicios_realizados_resumen = obtener_resumen_servicios_realizados_dashboard(
        today=today,
        limit=5,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=(int(sesion_caja.id_sesion) if sesion_caja else None),
    )

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
        'cobros_pendientes': {
            'items': serializar_resumen_cobros_pendientes_dashboard(cobros_pendientes_resumen['items']),
            'total_count': int(cobros_pendientes_resumen['total_count'] or 0),
            'total_monto': float(cobros_pendientes_resumen['total_monto'] or 0),
        },
        'servicios_realizados': {
            'items': servicios_realizados_resumen['items'],
            'total_count': int(servicios_realizados_resumen['total_count'] or 0),
            'total_monto': float(servicios_realizados_resumen['total_monto'] or 0),
        },
        'gastos_corrientes': (
            {
                **gastos_corrientes_resumen,
                'total_pendiente': float(gastos_corrientes_resumen['total_pendiente']),
            }
            if gastos_corrientes_resumen
            else None
        ),
    })
