from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Cliente,
    ClienteObservacion,
    CuentaPorCobrar,
    DetalleVenta,
    PagoCuentaCobrar,
    PagoVenta,
    Reparacion,
    SesionCaja,
    Venta,
)
from app.services.ia_backoffice.drilldown_shared import (
    ESTADOS_REPARACION_CERRADOS,
    _iso,
    _money,
    _puede_ver_clientes,
    _puede_ver_cobranzas,
    _puede_ver_inventario,
    _puede_ver_reparaciones,
    _puede_ver_ventas,
    _rango_con_default,
    _resolver_cliente,
    _resolver_producto,
    _resolver_venta,
    _venta_candidata_payload,
)
from app.utils.helpers import today_local, utc_bounds_for_local_dates, utc_naive_to_local


def cliente_detalle_360(args: dict | None = None, usuario=None) -> dict:
    cliente, candidatos = _resolver_cliente(args)
    if not cliente and candidatos:
        return {'encontrado': False, 'requiere_seleccion': True, 'candidatos': candidatos}
    if not cliente:
        return {'encontrado': False, 'error': 'cliente_no_encontrado'}

    rango = _rango_con_default(args, 'anio')
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    hoy = today_local()
    data = {
        'encontrado': True,
        'periodo_analisis': rango['periodo_label'],
        'cliente': {
            'id_cliente': int(cliente.id_cliente),
            'nombre': cliente.nombre,
            'ruc_ci': cliente.ruc_ci or '',
            'telefono': cliente.telefono or '',
            'email': cliente.email or '',
            'direccion': cliente.direccion or '',
            'tipo': cliente.tipo or '',
            'nivel_estrellas': int(cliente.nivel_estrellas_seguro),
            'activo': bool(cliente.activo),
            'limite_credito': _money(cliente.limite_credito),
            'saldo_pendiente': _money(cliente.saldo_pendiente),
            'credito_disponible': _money(cliente.credito_disponible),
            'fecha_creacion': _iso(cliente.fecha_creacion),
        },
        'secciones_incluidas': [],
    }

    if _puede_ver_clientes(usuario):
        observaciones = (
            ClienteObservacion.query
            .options(joinedload(ClienteObservacion.usuario))
            .filter(ClienteObservacion.id_cliente == cliente.id_cliente)
            .order_by(ClienteObservacion.fecha_observacion.desc(), ClienteObservacion.id_observacion.desc())
            .limit(3)
            .all()
        )
        data['ultimas_observaciones'] = [
            {
                'fecha': _iso(item.fecha_observacion),
                'usuario': item.usuario.username if item.usuario else '',
                'observacion': item.observacion,
            }
            for item in observaciones
        ]
        data['secciones_incluidas'].append('observaciones')

    if _puede_ver_ventas(usuario):
        ventas_base = Venta.query.filter(Venta.id_cliente == cliente.id_cliente, Venta.estado == 'completada')
        ventas_periodo = ventas_base.filter(Venta.fecha_venta >= inicio_utc, Venta.fecha_venta < fin_utc)
        resumen_historico = ventas_base.with_entities(
            func.coalesce(func.sum(Venta.total), 0).label('total'),
            func.count(Venta.id_venta).label('cantidad'),
        ).first()
        resumen_periodo = ventas_periodo.with_entities(
            func.coalesce(func.sum(Venta.total), 0).label('total'),
            func.count(Venta.id_venta).label('cantidad'),
        ).first()
        ultima_venta = ventas_base.order_by(Venta.fecha_venta.desc(), Venta.id_venta.desc()).first()
        ventas_recientes = ventas_base.order_by(Venta.fecha_venta.desc(), Venta.id_venta.desc()).limit(5).all()
        cantidad_hist = int(getattr(resumen_historico, 'cantidad', 0) or 0)
        total_hist = _money(getattr(resumen_historico, 'total', 0))
        cantidad_periodo = int(getattr(resumen_periodo, 'cantidad', 0) or 0)
        total_periodo = _money(getattr(resumen_periodo, 'total', 0))
        dias_desde_ultima = None
        if ultima_venta and ultima_venta.fecha_venta:
            local_dt = utc_naive_to_local(ultima_venta.fecha_venta)
            if local_dt:
                dias_desde_ultima = max((hoy - local_dt.date()).days, 0)
        data['ventas'] = {
            'historico': {
                'cantidad_ventas': cantidad_hist,
                'total_comprado': total_hist,
                'ticket_promedio': round(total_hist / cantidad_hist, 2) if cantidad_hist else 0,
            },
            'periodo': {
                'cantidad_ventas': cantidad_periodo,
                'total_comprado': total_periodo,
                'ticket_promedio': round(total_periodo / cantidad_periodo, 2) if cantidad_periodo else 0,
            },
            'ultima_venta': _venta_candidata_payload(ultima_venta) if ultima_venta else None,
            'dias_desde_ultima_venta': dias_desde_ultima,
            'ventas_recientes': [_venta_candidata_payload(item) for item in ventas_recientes],
        }
        data['secciones_incluidas'].append('ventas')

    if _puede_ver_cobranzas(usuario):
        hoy_local = today_local()
        base_cxc = CuentaPorCobrar.query.filter(
            CuentaPorCobrar.id_cliente == cliente.id_cliente,
            CuentaPorCobrar.estado != 'anulada',
        )
        saldo_total = base_cxc.with_entities(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0)).scalar()
        saldo_vencido = (
            base_cxc.filter(
                CuentaPorCobrar.saldo_pendiente > 0,
                CuentaPorCobrar.fecha_vencimiento.isnot(None),
                CuentaPorCobrar.fecha_vencimiento < hoy_local,
            )
            .with_entities(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0))
            .scalar()
        )
        ultimo_pago = (
            PagoCuentaCobrar.query
            .join(CuentaPorCobrar, CuentaPorCobrar.id_cuenta_cobrar == PagoCuentaCobrar.id_cuenta_cobrar)
            .filter(
                CuentaPorCobrar.id_cliente == cliente.id_cliente,
                PagoCuentaCobrar.estado != 'anulado',
            )
            .order_by(PagoCuentaCobrar.fecha_pago.desc(), PagoCuentaCobrar.id_pago_cuenta.desc())
            .first()
        )
        data['cobranzas'] = {
            'saldo_total': _money(saldo_total),
            'saldo_vencido': _money(saldo_vencido),
            'cuentas_abiertas': int(base_cxc.filter(CuentaPorCobrar.saldo_pendiente > 0).count()),
            'cuentas_vencidas': int(
                base_cxc.filter(
                    CuentaPorCobrar.saldo_pendiente > 0,
                    CuentaPorCobrar.fecha_vencimiento.isnot(None),
                    CuentaPorCobrar.fecha_vencimiento < hoy_local,
                ).count()
            ),
            'ultimo_pago': {
                'fecha_pago': _iso(ultimo_pago.fecha_pago),
                'monto': _money(ultimo_pago.monto),
                'referencia': ultimo_pago.referencia or '',
            } if ultimo_pago else None,
        }
        data['secciones_incluidas'].append('cobranzas')

    if _puede_ver_reparaciones(usuario):
        base_rep = Reparacion.query.filter(Reparacion.cliente_id == cliente.id_cliente)
        recientes = base_rep.order_by(Reparacion.fecha_ingreso.desc(), Reparacion.id_reparacion.desc()).limit(5).all()
        data['reparaciones'] = {
            'total_historico': int(base_rep.count()),
            'abiertas_actuales': int(base_rep.filter(~Reparacion.estado.in_(tuple(ESTADOS_REPARACION_CERRADOS))).count()),
            'listas_para_entrega': int(base_rep.filter(Reparacion.estado == 'listo').count()),
            'recientes': [
                {
                    'id_reparacion': int(item.id_reparacion),
                    'equipo': f'{item.tipo_equipo} {item.marca_modelo}'.strip(),
                    'estado': item.estado or '',
                    'prioridad': item.prioridad or 'normal',
                    'fecha_ingreso': _iso(item.fecha_ingreso),
                    'fecha_estimada': _iso(item.fecha_estimada),
                }
                for item in recientes
            ],
        }
        data['secciones_incluidas'].append('reparaciones')

    insights = []
    ventas_info = data.get('ventas') or {}
    cobranzas_info = data.get('cobranzas') or {}
    reparaciones_info = data.get('reparaciones') or {}
    dias_desde = ventas_info.get('dias_desde_ultima_venta')
    if dias_desde is not None and dias_desde >= 90:
        insights.append({'prioridad': 'media', 'titulo': 'Cliente dormido', 'detalle': f'La ultima compra fue hace {dias_desde} dias.'})
    if _money(cobranzas_info.get('saldo_vencido')) > 0:
        insights.append({'prioridad': 'alta', 'titulo': 'Cobranza pendiente', 'detalle': f'Tiene saldo vencido por {_money(cobranzas_info.get("saldo_vencido"))}.'})
    if int(reparaciones_info.get('abiertas_actuales') or 0) > 0:
        insights.append({'prioridad': 'media', 'titulo': 'Reparaciones activas', 'detalle': f'Tiene {int(reparaciones_info.get("abiertas_actuales") or 0)} reparaciones abiertas.'})
    data['insights'] = insights
    return data


def producto_detalle_360(args: dict | None = None, usuario=None) -> dict:
    producto, candidatos = _resolver_producto(args)
    if not producto and candidatos:
        return {'encontrado': False, 'requiere_seleccion': True, 'candidatos': candidatos}
    if not producto:
        return {'encontrado': False, 'error': 'producto_no_encontrado'}

    rango = _rango_con_default(args, '30d')
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    data = {
        'encontrado': True,
        'periodo_analisis': rango['periodo_label'],
        'producto': {
            'id_producto': int(producto.id_producto),
            'codigo': producto.codigo,
            'codigo_barras': producto.codigo_barras or '',
            'nombre': producto.nombre,
            'categoria': producto.categoria.nombre if producto.categoria else '',
            'marca': producto.marca or '',
            'modelo': producto.modelo or '',
            'activo': bool(producto.activo),
            'es_servicio': bool(producto.es_servicio),
            'es_kit': bool(producto.es_kit),
        },
        'secciones_incluidas': [],
    }

    if _puede_ver_inventario(usuario):
        data['inventario'] = {
            'stock_actual': int(producto.stock_actual or 0),
            'stock_minimo': int(producto.stock_minimo or 0),
            'stock_maximo': int(producto.stock_maximo or 0) if producto.stock_maximo is not None else None,
            'stock_bajo': bool(producto.stock_bajo),
            'valor_stock_costo': _money((producto.stock_actual or 0) * (producto.precio_compra or 0)),
            'precio_compra': _money(producto.precio_compra),
            'precio_venta': _money(producto.precio_venta),
            'precio_mayorista': _money(producto.precio_mayorista),
            'publicado_tienda': bool(producto.publicado_tienda),
            'vistas_tienda': int(producto.vistas_tienda or 0),
            'es_oferta_tienda': bool(producto.es_oferta_tienda),
            'es_destacado_tienda': bool(producto.es_destacado_tienda),
        }
        data['secciones_incluidas'].append('inventario')

    if _puede_ver_ventas(usuario):
        base = (
            db.session.query(
                func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades'),
                func.coalesce(func.sum(DetalleVenta.subtotal), 0).label('ingreso'),
                func.count(func.distinct(Venta.id_venta)).label('ventas'),
            )
            .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
            .filter(DetalleVenta.id_producto == producto.id_producto, Venta.estado == 'completada')
        )
        historico = base.first()
        periodo = base.filter(Venta.fecha_venta >= inicio_utc, Venta.fecha_venta < fin_utc).first()
        ultima_venta = (
            Venta.query
            .join(DetalleVenta, DetalleVenta.id_venta == Venta.id_venta)
            .filter(DetalleVenta.id_producto == producto.id_producto, Venta.estado == 'completada')
            .order_by(Venta.fecha_venta.desc(), Venta.id_venta.desc())
            .first()
        )
        ventas_recientes = (
            db.session.query(
                Venta.id_venta,
                Venta.fecha_venta,
                Venta.numero_comprobante,
                Venta.total,
                DetalleVenta.cantidad,
                DetalleVenta.subtotal,
                Cliente.nombre.label('cliente'),
            )
            .join(DetalleVenta, DetalleVenta.id_venta == Venta.id_venta)
            .outerjoin(Cliente, Cliente.id_cliente == Venta.id_cliente)
            .filter(DetalleVenta.id_producto == producto.id_producto, Venta.estado == 'completada')
            .order_by(Venta.fecha_venta.desc(), Venta.id_venta.desc())
            .limit(5)
            .all()
        )
        unidades_periodo = int(getattr(periodo, 'unidades', 0) or 0)
        ingreso_periodo = _money(getattr(periodo, 'ingreso', 0))
        costo_periodo = _money(unidades_periodo * float(producto.precio_compra or 0))
        data['ventas'] = {
            'historico': {
                'unidades': int(getattr(historico, 'unidades', 0) or 0),
                'ingreso': _money(getattr(historico, 'ingreso', 0)),
                'cantidad_ventas': int(getattr(historico, 'ventas', 0) or 0),
            },
            'periodo': {
                'unidades': unidades_periodo,
                'ingreso': ingreso_periodo,
                'cantidad_ventas': int(getattr(periodo, 'ventas', 0) or 0),
                'costo_estimado': costo_periodo,
                'ganancia_estimada': _money(ingreso_periodo - costo_periodo),
            },
            'ultima_venta': _venta_candidata_payload(ultima_venta) if ultima_venta else None,
            'ventas_recientes': [
                {
                    'id_venta': int(row.id_venta),
                    'fecha_venta': _iso(row.fecha_venta),
                    'numero_comprobante': row.numero_comprobante or '',
                    'cliente': row.cliente or '',
                    'cantidad': int(row.cantidad or 0),
                    'subtotal': _money(row.subtotal),
                    'total_documento': _money(row.total),
                }
                for row in ventas_recientes
            ],
        }
        data['secciones_incluidas'].append('ventas')

    data['relaciones'] = {
        'componentes_kit': int(producto.componentes.count()) if hasattr(producto.componentes, 'count') else 0,
        'repuestos_relacionados': int(producto.repuestos.count()) if hasattr(producto.repuestos, 'count') else 0,
    }

    insights = []
    inventario = data.get('inventario') or {}
    ventas = data.get('ventas') or {}
    ventas_periodo = ventas.get('periodo') or {}
    if bool(inventario.get('stock_bajo')):
        insights.append({'prioridad': 'alta', 'titulo': 'Stock bajo', 'detalle': 'El producto ya esta en o por debajo del minimo configurado.'})
    if int(ventas_periodo.get('unidades') or 0) == 0 and int(inventario.get('stock_actual') or 0) > 0:
        insights.append({'prioridad': 'media', 'titulo': 'Producto inmovilizado', 'detalle': 'Tiene stock pero no registra ventas en el periodo analizado.'})
    if _money(inventario.get('precio_compra')) <= 0 and int(ventas_periodo.get('cantidad_ventas') or 0) > 0:
        insights.append({'prioridad': 'media', 'titulo': 'Costo faltante', 'detalle': 'Se vende pero no tiene precio de compra cargado para medir margen.'})
    data['insights'] = insights
    return data


def detalle_venta_documento(args: dict | None = None, usuario=None) -> dict:
    venta, candidatos = _resolver_venta(args)
    if not venta and candidatos:
        return {'encontrado': False, 'requiere_seleccion': True, 'candidatos': candidatos}
    if not venta:
        return {'encontrado': False, 'error': 'venta_no_encontrada'}

    venta = (
        Venta.query.options(
            joinedload(Venta.cliente),
            joinedload(Venta.vendedor),
            joinedload(Venta.sesion_caja).joinedload(SesionCaja.caja),
            joinedload(Venta.detalles).joinedload(DetalleVenta.producto),
            joinedload(Venta.pagos).joinedload(PagoVenta.metodo),
            joinedload(Venta.cuenta_por_cobrar),
            joinedload(Venta.reparacion),
            joinedload(Venta.ticket),
        )
        .filter(Venta.id_venta == venta.id_venta)
        .first()
    )
    items = [
        {
            'id_producto': int(detalle.id_producto),
            'codigo': detalle.producto.codigo if detalle.producto else '',
            'producto': detalle.producto.nombre if detalle.producto else '',
            'cantidad': int(detalle.cantidad or 0),
            'precio_unitario': _money(detalle.precio_unitario),
            'descuento_linea': _money(detalle.descuento_linea),
            'subtotal': _money(detalle.subtotal),
            'porcentaje_iva': int(detalle.porcentaje_iva or 0),
            'monto_iva': _money(detalle.monto_iva),
            'es_kit': bool(detalle.es_kit),
        }
        for detalle in venta.detalles
    ]
    pagos = [
        {
            'id_pago': int(pago.id_pago),
            'metodo': pago.metodo.nombre if pago.metodo else '',
            'monto': _money(pago.monto),
            'referencia': pago.referencia or '',
            'fecha_pago': _iso(pago.fecha_pago),
        }
        for pago in venta.pagos
    ]
    return {
        'encontrado': True,
        'venta': {
            'id_venta': int(venta.id_venta),
            'tipo_comprobante': venta.tipo_comprobante or '',
            'numero_comprobante': venta.numero_comprobante or '',
            'timbrado': venta.timbrado or '',
            'client_request_id': venta.client_request_id or '',
            'fecha_venta': _iso(venta.fecha_venta),
            'estado': venta.estado or '',
            'tipo_venta': venta.tipo_venta or '',
            'subtotal': _money(venta.subtotal),
            'descuento_porcentaje': _money(venta.descuento_porcentaje),
            'descuento_monto': _money(venta.descuento_monto),
            'total_iva_10': _money(venta.total_iva_10),
            'total_iva_5': _money(venta.total_iva_5),
            'total_exenta': _money(venta.total_exenta),
            'total': _money(venta.total),
            'saldo_pendiente': _money(venta.saldo_pendiente),
            'observaciones': venta.observaciones or '',
        },
        'cliente': {
            'id_cliente': int(venta.id_cliente),
            'nombre': venta.cliente.nombre if venta.cliente else '',
            'ruc_ci': venta.cliente.ruc_ci if venta.cliente else '',
            'telefono': venta.cliente.telefono if venta.cliente else '',
        },
        'vendedor': {
            'id_usuario': int(venta.id_usuario_vendedor or 0) if venta.id_usuario_vendedor else None,
            'username': venta.vendedor.username if venta.vendedor else '',
            'nombre': venta.vendedor.nombre_completo if venta.vendedor else '',
        },
        'caja': {
            'id_sesion': int(venta.id_sesion_caja),
            'caja': venta.sesion_caja.caja.nombre if venta.sesion_caja and venta.sesion_caja.caja else '',
            'fecha_apertura': _iso(venta.sesion_caja.fecha_apertura) if venta.sesion_caja else None,
            'fecha_cierre': _iso(venta.sesion_caja.fecha_cierre) if venta.sesion_caja else None,
        },
        'ticket': {
            'numero_ticket': venta.ticket.numero_ticket if venta.ticket else '',
            'fecha_emision': _iso(venta.ticket.fecha_emision) if venta.ticket else None,
            'cantidad_impresiones': int(venta.ticket.cantidad_impresiones or 0) if venta.ticket else 0,
        },
        'cuenta_por_cobrar': {
            'id_cuenta_cobrar': int(venta.cuenta_por_cobrar.id_cuenta_cobrar),
            'saldo_pendiente': _money(venta.cuenta_por_cobrar.saldo_pendiente),
            'monto_total': _money(venta.cuenta_por_cobrar.monto_total),
            'fecha_vencimiento': _iso(venta.cuenta_por_cobrar.fecha_vencimiento),
            'estado': venta.cuenta_por_cobrar.estado or '',
        } if venta.cuenta_por_cobrar else None,
        'reparacion_relacionada': {
            'id_reparacion': int(venta.reparacion.id_reparacion),
            'equipo': f'{venta.reparacion.tipo_equipo} {venta.reparacion.marca_modelo}'.strip(),
            'estado': venta.reparacion.estado or '',
        } if venta.reparacion else None,
        'items': items,
        'pagos': pagos,
        'cantidad_items': int(venta.cantidad_items or 0),
        'total_pagado': _money(venta.total_pagado),
    }
