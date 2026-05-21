"""
Rutas de reportes
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import text, literal
from sqlalchemy.orm import joinedload, aliased
from app import db
from app.models import Venta, DetalleVenta, Producto, Categoria, SesionCaja, Reparacion, Usuario, Rol, Cliente
from app.routes.reportes_ventas_diarias import construir_contexto_ventas_diarias
from app.utils.helpers import today_local, parse_iso_date, utc_bounds_for_local_dates, local_strftime

reportes_bp = Blueprint('reportes', __name__)
ROLES_VENDEDOR_CAJERO = {'vendedor', 'cajero'}
_FECHAS_REPARACIONES_NORMALIZADAS = False


def _usuarios_vendedores_cajeros_activos():
    return (
        Usuario.query
        .join(Rol, Usuario.id_rol == Rol.id_rol)
        .filter(
            Usuario.activo == True,
            Rol.activo == True,
            db.func.lower(Rol.nombre).in_(ROLES_VENDEDOR_CAJERO)
        )
        .order_by(Usuario.nombre_completo.asc())
        .all()
    )


def _nombre_vendedor_venta(venta):
    if getattr(venta, 'vendedor', None):
        return venta.vendedor.nombre_completo
    if getattr(venta, 'sesion_caja', None) and getattr(venta.sesion_caja, 'usuario', None):
        return venta.sesion_caja.usuario.nombre_completo
    return 'Desconocido'


def _normalizar_fechas_reparaciones_invalidas():
    """Limpia fechas vacías legacy en reparaciones para evitar fallos de parseo ORM."""
    global _FECHAS_REPARACIONES_NORMALIZADAS
    if _FECHAS_REPARACIONES_NORMALIZADAS:
        return

    try:
        db.session.execute(text(
            """
            UPDATE reparaciones
            SET fecha_ingreso = NULL
            WHERE fecha_ingreso IS NOT NULL
              AND (
                TRIM(fecha_ingreso) = ''
                OR TRIM(fecha_ingreso) = '0000-00-00'
                OR TRIM(fecha_ingreso) = '0000-00-00 00:00:00'
              )
            """
        ))
        db.session.execute(text(
            """
            UPDATE reparaciones
            SET fecha_estimada = NULL
            WHERE fecha_estimada IS NOT NULL
              AND (
                TRIM(fecha_estimada) = ''
                OR TRIM(fecha_estimada) = '0000-00-00'
                OR TRIM(fecha_estimada) = '0000-00-00 00:00:00'
              )
            """
        ))
        db.session.execute(text(
            """
            UPDATE reparaciones
            SET fecha_entrega = NULL
            WHERE fecha_entrega IS NOT NULL
              AND (
                TRIM(fecha_entrega) = ''
                OR TRIM(fecha_entrega) = '0000-00-00'
                OR TRIM(fecha_entrega) = '0000-00-00 00:00:00'
              )
            """
        ))
        db.session.commit()
        _FECHAS_REPARACIONES_NORMALIZADAS = True
    except Exception:
        db.session.rollback()


def _parsear_filtros_historial_vendedores():
    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')
    id_vendedor = request.args.get('id_vendedor', 0, type=int)
    historial_page = request.args.get('historial_page', 1, type=int)

    desde = parse_iso_date(raw_desde) or (today_local() - timedelta(days=30))
    hasta = parse_iso_date(raw_hasta) or today_local()
    if desde > hasta:
        desde, hasta = hasta, desde
    if not historial_page or historial_page < 1:
        historial_page = 1
    return desde, hasta, int(id_vendedor or 0), int(historial_page)


def _construir_contexto_historial_vendedores(desde, hasta, id_vendedor, historial_page=1):
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)

    vendedores = _usuarios_vendedores_cajeros_activos()
    vendedores_por_id = {int(u.id_usuario): u for u in vendedores}
    vendedores_ids = set(vendedores_por_id.keys())
    vendedores_ids_list = list(vendedores_ids)
    filtro_vendedor_invalido = False
    if id_vendedor and vendedores_ids and id_vendedor not in vendedores_ids:
        filtro_vendedor_invalido = True
        id_vendedor = 0

    _normalizar_fechas_reparaciones_invalidas()

    vid_expr = db.func.coalesce(Venta.id_usuario_vendedor, SesionCaja.id_usuario)

    ventas_agg_q = (
        db.session.query(
            vid_expr.label('vid'),
            db.func.count(Venta.id_venta).label('ventas'),
            db.func.coalesce(db.func.sum(Venta.total), 0).label('total_ventas'),
        )
        .join(SesionCaja, Venta.id_sesion_caja == SesionCaja.id_sesion)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc
        )
    )
    if vendedores_ids_list:
        ventas_agg_q = ventas_agg_q.filter(vid_expr.in_(vendedores_ids_list))
    if id_vendedor:
        ventas_agg_q = ventas_agg_q.filter(vid_expr == id_vendedor)
    ventas_agg_rows = ventas_agg_q.group_by(vid_expr).all()

    reps_agg_q = (
        db.session.query(
            Reparacion.id_usuario_vendedor.label('vid'),
            db.func.count(Reparacion.id_reparacion).label('reparaciones'),
        )
        .filter(
            Reparacion.id_usuario_vendedor.isnot(None),
            Reparacion.fecha_ingreso >= start_utc,
            Reparacion.fecha_ingreso < end_utc
        )
    )
    if vendedores_ids_list:
        reps_agg_q = reps_agg_q.filter(Reparacion.id_usuario_vendedor.in_(vendedores_ids_list))
    if id_vendedor:
        reps_agg_q = reps_agg_q.filter(Reparacion.id_usuario_vendedor == id_vendedor)
    reps_agg_rows = reps_agg_q.group_by(Reparacion.id_usuario_vendedor).all()

    resumen = {}

    def _ensure_resumen(vid):
        row = resumen.get(int(vid))
        if row:
            return row
        vendedor_obj = vendedores_por_id.get(int(vid))
        row = {
            'id_usuario': int(vid),
            'nombre': (vendedor_obj.nombre_completo if vendedor_obj else 'Desconocido'),
            'rol': ((vendedor_obj.rol.nombre if vendedor_obj and vendedor_obj.rol else '') or '').strip(),
            'ventas': 0,
            'total_ventas': 0.0,
            'reparaciones': 0,
        }
        resumen[int(vid)] = row
        return row

    for r in ventas_agg_rows:
        if r.vid is None:
            continue
        row = _ensure_resumen(int(r.vid))
        row['ventas'] = int(r.ventas or 0)
        row['total_ventas'] = float(r.total_ventas or 0)

    for r in reps_agg_rows:
        if r.vid is None:
            continue
        row = _ensure_resumen(int(r.vid))
        row['reparaciones'] = int(r.reparaciones or 0)

    ranking = sorted(
        resumen.values(),
        key=lambda r: (float(r['total_ventas'] or 0), int(r['ventas'] or 0), int(r['reparaciones'] or 0)),
        reverse=True
    )

    usuario_vendedor = aliased(Usuario)
    usuario_caja = aliased(Usuario)
    HISTORIAL_PER_PAGE = 20

    ventas_hist_q = (
        db.session.query(
            Venta.fecha_venta.label('fecha'),
            literal('Venta').label('tipo'),
            db.func.coalesce(usuario_vendedor.nombre_completo, usuario_caja.nombre_completo, 'Desconocido').label('vendedor'),
            Cliente.nombre.label('cliente_nombre'),
            Venta.id_venta.label('id_ref'),
            Venta.total.label('monto'),
            Venta.tipo_venta.label('tipo_venta'),
            Venta.saldo_pendiente.label('saldo_pendiente'),
        )
        .join(Cliente, Venta.id_cliente == Cliente.id_cliente)
        .join(SesionCaja, Venta.id_sesion_caja == SesionCaja.id_sesion)
        .outerjoin(usuario_vendedor, usuario_vendedor.id_usuario == Venta.id_usuario_vendedor)
        .outerjoin(usuario_caja, usuario_caja.id_usuario == SesionCaja.id_usuario)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc
        )
    )
    if vendedores_ids_list:
        ventas_hist_q = ventas_hist_q.filter(vid_expr.in_(vendedores_ids_list))
    if id_vendedor:
        ventas_hist_q = ventas_hist_q.filter(vid_expr == id_vendedor)
    reps_hist_q = (
        db.session.query(
            Reparacion.fecha_ingreso.label('fecha'),
            literal('Recepción').label('tipo'),
            db.func.coalesce(Usuario.nombre_completo, 'Desconocido').label('vendedor'),
            Cliente.nombre.label('cliente_nombre'),
            Reparacion.id_reparacion.label('id_ref'),
            literal(0.0).label('monto'),
            literal('').label('tipo_venta'),
            literal(0.0).label('saldo_pendiente'),
        )
        .join(Cliente, Reparacion.cliente_id == Cliente.id_cliente)
        .outerjoin(Usuario, Reparacion.id_usuario_vendedor == Usuario.id_usuario)
        .filter(
            Reparacion.id_usuario_vendedor.isnot(None),
            Reparacion.fecha_ingreso >= start_utc,
            Reparacion.fecha_ingreso < end_utc
        )
    )
    if vendedores_ids_list:
        reps_hist_q = reps_hist_q.filter(Reparacion.id_usuario_vendedor.in_(vendedores_ids_list))
    if id_vendedor:
        reps_hist_q = reps_hist_q.filter(Reparacion.id_usuario_vendedor == id_vendedor)
    historial_union = ventas_hist_q.union_all(reps_hist_q).subquery(name='historial_vendedores_union')

    historial_total = int(db.session.query(db.func.count()).select_from(historial_union).scalar() or 0)
    historial_pages = max((historial_total + HISTORIAL_PER_PAGE - 1) // HISTORIAL_PER_PAGE, 1)
    if historial_page > historial_pages:
        historial_page = historial_pages
    historial_offset = (historial_page - 1) * HISTORIAL_PER_PAGE

    historial_rows = (
        db.session.query(
            historial_union.c.fecha,
            historial_union.c.tipo,
            historial_union.c.vendedor,
            historial_union.c.cliente_nombre,
            historial_union.c.id_ref,
            historial_union.c.monto,
            historial_union.c.tipo_venta,
            historial_union.c.saldo_pendiente,
        )
        .order_by(historial_union.c.fecha.desc(), historial_union.c.id_ref.desc())
        .offset(historial_offset)
        .limit(HISTORIAL_PER_PAGE)
        .all()
    )

    historial = []
    for r in historial_rows:
        es_venta = str(r.tipo or '').lower() == 'venta'
        id_ref = int(r.id_ref)
        tipo_venta = ((r.tipo_venta or 'contado') if es_venta else '').strip().lower()
        saldo_pendiente = float(r.saldo_pendiente or 0) if es_venta else 0.0
        historial.append({
            'tipo': r.tipo,
            'fecha': r.fecha,
            'vendedor': (r.vendedor or 'Desconocido'),
            'cliente': (r.cliente_nombre or '—'),
            'referencia': f'Venta #{id_ref}' if es_venta else f'Reparación #{id_ref}',
            'url': url_for('ventas.detalle', id=id_ref) if es_venta else url_for('reparaciones.detalle', id=id_ref),
            'monto': float(r.monto or 0),
            'condicion': 'Crédito' if es_venta and tipo_venta == 'credito' else ('Contado' if es_venta else '—'),
            'saldo_pendiente': saldo_pendiente,
        })

    totales = {
        'ventas': sum(int(r['ventas'] or 0) for r in ranking),
        'total_ventas': sum(float(r['total_ventas'] or 0) for r in ranking),
        'reparaciones': sum(int(r['reparaciones'] or 0) for r in ranking),
    }

    return {
        'desde': desde,
        'hasta': hasta,
        'id_vendedor': id_vendedor,
        'vendedores': vendedores,
        'ranking': ranking,
        'historial': historial,
        'historial_pag': {
            'page': historial_page,
            'pages': historial_pages,
            'has_prev': historial_page > 1,
            'has_next': historial_page < historial_pages,
            'prev_num': historial_page - 1 if historial_page > 1 else 1,
            'next_num': historial_page + 1 if historial_page < historial_pages else historial_pages,
            'per_page': HISTORIAL_PER_PAGE,
            'total': historial_total,
        },
        'totales': totales,
        'filtro_vendedor_invalido': filtro_vendedor_invalido,
        'historial_limit': HISTORIAL_PER_PAGE,
        'historial_truncado': False,
    }


@reportes_bp.route('/')
@login_required
def index():
    """Página principal de reportes"""
    if not current_user.tiene_permiso('ver_reportes'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reportes.', 'danger')
        return redirect(url_for('main.dashboard'))

    return render_template('reportes/index.html')


@reportes_bp.route('/ventas-diarias')
@login_required
def ventas_diarias():
    """Reporte de ventas del día"""
    if not current_user.tiene_permiso('ver_reporte_ventas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reporte de ventas.', 'danger')
        return redirect(url_for('reportes.index'))

    contexto = construir_contexto_ventas_diarias(
        raw_desde=request.args.get('desde'),
        raw_hasta=request.args.get('hasta'),
        raw_fecha=request.args.get('fecha'),
    )
    return render_template('reportes/ventas_diarias.html', **contexto)



@reportes_bp.route('/ventas/<int:id_venta>/detalle')
@login_required
def detalle_venta(id_venta):
    """Obtener detalles de una venta"""
    if not current_user.tiene_permiso('ver_reporte_ventas'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403
    
    venta = (
        Venta.query.options(
            joinedload(Venta.cliente),
            joinedload(Venta.cuenta_por_cobrar),
            joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
            joinedload(Venta.vendedor)
        )
        .get_or_404(id_venta)
    )
    
    detalles = []
    for detalle in venta.detalles:
        detalles.append({
            'producto': detalle.item_nombre,
            'cantidad': detalle.cantidad,
            'precio_unitario': float(detalle.precio_unitario),
            'subtotal': float(detalle.subtotal),
            'descuento': float(detalle.descuento_linea)
        })
        
    pagos = []
    for pago in venta.pagos:
        pagos.append({
            'metodo': pago.metodo.nombre,
            'monto': float(pago.monto)
        })

    vendedor = _nombre_vendedor_venta(venta)
    total_pagado_inmediato = sum(float(p.monto or 0) for p in venta.pagos)
    saldo_pendiente = float(
        getattr(getattr(venta, 'cuenta_por_cobrar', None), 'saldo_pendiente', venta.saldo_pendiente) or 0
    )
    tipo_venta = (venta.tipo_venta or 'contado').strip().lower()
    if saldo_pendiente <= 0:
        estado_cobro = 'Pagada'
    elif total_pagado_inmediato > 0:
        estado_cobro = 'Parcial'
    elif tipo_venta == 'credito':
        estado_cobro = 'Pendiente'
    else:
        estado_cobro = 'Pendiente'

    return jsonify({
        'id': venta.id_venta,
        'fecha': local_strftime(venta.fecha_venta, '%d/%m/%Y %H:%M'),
        'cliente': venta.cliente.nombre,
        'vendedor': vendedor,
        'tipo_venta': 'Credito' if tipo_venta == 'credito' else 'Contado',
        'estado_cobro': estado_cobro,
        'cobrado_al_momento': total_pagado_inmediato,
        'saldo_pendiente': saldo_pendiente,
        'descuento_manual_monto': float(getattr(venta, 'descuento_manual_monto', 0) or 0),
        'descuento_fidelizacion_monto': float(getattr(venta, 'descuento_fidelizacion_monto', 0) or 0),
        'beneficio_fidelizacion_tipo': (getattr(venta, 'beneficio_fidelizacion_tipo', '') or '').strip(),
        'beneficio_fidelizacion_descripcion': (getattr(venta, 'beneficio_fidelizacion_descripcion', '') or '').strip(),
        'items': detalles,
        'total': float(venta.total),
        'pagos': pagos
    })


@reportes_bp.route('/historial-vendedores')
@login_required
def historial_vendedores():
    """Historial y ranking de vendedores/cajeros."""
    if not current_user.tiene_permiso('ver_reporte_ventas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reporte de ventas.', 'danger')
        return redirect(url_for('reportes.index'))

    desde, hasta, id_vendedor, historial_page = _parsear_filtros_historial_vendedores()
    ctx = _construir_contexto_historial_vendedores(desde, hasta, id_vendedor, historial_page=historial_page)

    es_ajax = (
        request.args.get('historial_ajax') == '1'
        or request.args.get('ajax') == '1'
    )
    if ctx.get('filtro_vendedor_invalido') and not es_ajax:
        flash('Vendedor/Cajero inválido para el filtro.', 'warning')

    if es_ajax:
        return render_template('reportes/_historial_vendedores_resultados.html', **ctx)

    return render_template('reportes/historial_vendedores.html', **ctx)


@reportes_bp.route('/productos-vendidos')
@login_required
def productos_vendidos():
    """Reporte de productos más vendidos"""
    if not current_user.tiene_permiso('ver_reporte_ventas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reporte de ventas.', 'danger')
        return redirect(url_for('reportes.index'))

    fecha_desde = request.args.get('desde', (today_local() - timedelta(days=30)).isoformat())
    fecha_hasta = request.args.get('hasta', today_local().isoformat())
    
    desde = parse_iso_date(fecha_desde) or (today_local() - timedelta(days=30))
    hasta = parse_iso_date(fecha_hasta) or today_local()
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    
    # Consulta de productos más vendidos
    productos = db.session.query(
        Producto,
        db.func.sum(DetalleVenta.cantidad).label('cantidad_vendida'),
        db.func.sum(DetalleVenta.subtotal).label('total_vendido')
    ).join(
        DetalleVenta, Producto.id_producto == DetalleVenta.id_producto
    ).join(
        Venta, DetalleVenta.id_venta == Venta.id_venta
    ).filter(
        Venta.estado == 'completada',
        Venta.fecha_venta >= start_utc,
        Venta.fecha_venta < end_utc
    ).group_by(
        Producto.id_producto
    ).order_by(
        db.desc('cantidad_vendida')
    ).limit(50).all()
    
    return render_template('reportes/productos_vendidos.html',
        productos=productos,
        desde=desde,
        hasta=hasta
    )


@reportes_bp.route('/stock-bajo')
@login_required
def stock_bajo():
    """Reporte de productos con stock bajo"""
    if not current_user.tiene_permiso('ver_reporte_inventario'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reporte de inventario.', 'danger')
        return redirect(url_for('reportes.index'))

    productos = Producto.query.filter(
        Producto.activo == True,
        Producto.stock_actual <= Producto.stock_minimo
    ).order_by(
        (Producto.stock_minimo - Producto.stock_actual).desc()
    ).all()
    
    return render_template('reportes/stock_bajo.html', productos=productos)


@reportes_bp.route('/inventario')
@login_required
def inventario():
    """Reporte de inventario completo"""
    if not current_user.tiene_permiso('ver_reporte_inventario'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reporte de inventario.', 'danger')
        return redirect(url_for('reportes.index'))

    categoria_id = request.args.get('categoria', 0, type=int)
    
    query = Producto.query.filter_by(activo=True)
    
    if categoria_id:
        query = query.filter_by(id_categoria=categoria_id)
    
    productos = query.order_by(Producto.nombre).all()
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    
    # Calcular valor del inventario
    valor_total = sum(float(p.precio_compra or 0) * p.stock_actual for p in productos)
    valor_venta = sum(float(p.precio_venta) * p.stock_actual for p in productos)
    
    return render_template('reportes/inventario.html',
        productos=productos,
        categorias=categorias,
        categoria_id=categoria_id,
        valor_total=valor_total,
        valor_venta=valor_venta
    )
