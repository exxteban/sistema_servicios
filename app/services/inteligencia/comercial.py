from __future__ import annotations

from datetime import date, timedelta

from flask import current_app, has_app_context
from sqlalchemy import distinct, func

from app import db
from app.models import DetalleVenta, Producto, Venta
from app.services.inteligencia.campanas import obtener_sugerencias_campanas
from app.services.inteligencia.clientes import obtener_inteligencia_clientes
from app.services.inteligencia.common import DIAS_STOCK_INMOVILIZADO, formatear_rango
from app.services.inteligencia.inventario import obtener_inteligencia_inventario
from app.services.inteligencia.panel import construir_panel_inteligencia, construir_resumen_dashboard
from app.services.inteligencia.periodos import (
    normalizar_periodo,
    obtener_label_periodo,
    obtener_opciones_periodo,
    resolver_periodos,
)
from app.services.inteligencia.tienda import obtener_inteligencia_tienda
from app.services.inteligencia.ventas import obtener_inteligencia_ventas
from app.utils.helpers import today_local, utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.services.inteligencia_service import obtener_inteligencia_gastronomia


def obtener_panel_inteligencia_comercial(
    fecha_referencia: date | None = None,
    id_cliente_tienda: int | None = None,
    periodo: str | None = None,
) -> dict:
    fecha_corte = fecha_referencia or today_local()
    periodo_activo = normalizar_periodo(periodo)
    periodo_actual, periodo_anterior = resolver_periodos(fecha_corte, periodo_activo)
    facturacion_actual = _sumar_facturacion(periodo_actual['desde'], periodo_actual['hasta'])
    facturacion_anterior = _sumar_facturacion(periodo_anterior['desde'], periodo_anterior['hasta'])
    ticket_actual = _calcular_ticket_promedio(periodo_actual['desde'], periodo_actual['hasta'])
    ticket_anterior = _calcular_ticket_promedio(periodo_anterior['desde'], periodo_anterior['hasta'])
    clientes_activos_actual = _contar_clientes_activos(periodo_actual['desde'], periodo_actual['hasta'])
    clientes_activos_anterior = _contar_clientes_activos(periodo_anterior['desde'], periodo_anterior['hasta'])
    serie_clientes_activos = _armar_serie_comparada_clientes_activos(periodo_actual, periodo_anterior)
    clientes = obtener_inteligencia_clientes(fecha_corte)
    stock = _obtener_alertas_stock(fecha_corte)
    ventas = obtener_inteligencia_ventas(fecha_corte, periodo_actual, periodo_anterior)
    tienda = obtener_inteligencia_tienda(periodo_actual, id_cliente_tienda)
    inventario = obtener_inteligencia_inventario(fecha_corte, periodo_actual, id_cliente_tienda)
    gastronomia = _obtener_inteligencia_gastronomia_segura(periodo_actual, periodo_anterior, id_cliente_tienda)
    campanas = obtener_sugerencias_campanas(fecha_corte, periodo_actual, clientes, tienda, inventario)
    acciones = _construir_acciones(clientes, stock, ventas, tienda, inventario, gastronomia, campanas)
    return construir_panel_inteligencia(
        fecha_corte=fecha_corte,
        periodo_actual=periodo_actual,
        periodo_anterior=periodo_anterior,
        periodo_clave=periodo_activo,
        periodo_label=obtener_label_periodo(periodo_activo),
        periodos_disponibles=obtener_opciones_periodo(periodo_activo),
        facturacion_actual=facturacion_actual,
        facturacion_anterior=facturacion_anterior,
        ticket_actual=ticket_actual,
        ticket_anterior=ticket_anterior,
        clientes_activos_actual=clientes_activos_actual,
        clientes_activos_anterior=clientes_activos_anterior,
        serie_clientes_activos=serie_clientes_activos,
        clientes=clientes,
        stock=stock,
        inventario=inventario,
        gastronomia=gastronomia,
        campanas=campanas,
        ventas=ventas,
        tienda=tienda,
        acciones=acciones[:4],
        alertas_activas_total=len(acciones),
    )


def obtener_resumen_dashboard_inteligencia(
    fecha_referencia: date | None = None,
    id_cliente_tienda: int | None = None,
    periodo: str | None = None,
) -> dict:
    fecha_corte = fecha_referencia or today_local()
    periodo_actual, periodo_anterior = resolver_periodos(fecha_corte, periodo)
    clientes = obtener_inteligencia_clientes(fecha_corte)
    stock = _obtener_alertas_stock(fecha_corte)
    ventas = obtener_inteligencia_ventas(fecha_corte, periodo_actual, periodo_anterior)
    tienda = obtener_inteligencia_tienda(periodo_actual, id_cliente_tienda)
    inventario = obtener_inteligencia_inventario(fecha_corte, periodo_actual, id_cliente_tienda)
    gastronomia = _obtener_inteligencia_gastronomia_segura(periodo_actual, periodo_anterior, id_cliente_tienda)
    campanas = obtener_sugerencias_campanas(fecha_corte, periodo_actual, clientes, tienda, inventario)
    acciones = _construir_acciones(clientes, stock, ventas, tienda, inventario, gastronomia, campanas)
    return construir_resumen_dashboard(clientes, stock, campanas, len(acciones))


def _sumar_facturacion(desde: date, hasta: date) -> float:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    total = (
        db.session.query(func.coalesce(func.sum(Venta.total), 0))
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .scalar()
    )
    return float(total or 0)


def _calcular_ticket_promedio(desde: date, hasta: date) -> float:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    fila = (
        db.session.query(
            func.coalesce(func.sum(Venta.total), 0).label('total'),
            func.count(Venta.id_venta).label('cantidad'),
        )
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .first()
    )
    total = float(getattr(fila, 'total', 0) or 0)
    cantidad = int(getattr(fila, 'cantidad', 0) or 0)
    if cantidad <= 0:
        return 0.0
    return total / cantidad


def _contar_clientes_activos(desde: date, hasta: date) -> int:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    total = (
        db.session.query(func.count(distinct(Venta.id_cliente)))
        .filter(
            Venta.estado == 'completada',
            Venta.id_cliente != 1,
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .scalar()
    )
    return int(total or 0)


def _armar_serie_comparada_clientes_activos(periodo_actual: dict, periodo_anterior: dict) -> dict:
    dias = max((periodo_actual['hasta'] - periodo_actual['desde']).days + 1, 1)
    inicio_utc, fin_utc = utc_bounds_for_local_dates(periodo_anterior['desde'], periodo_actual['hasta'])
    filas = (
        db.session.query(Venta.fecha_venta, Venta.id_cliente)
        .filter(
            Venta.estado == 'completada',
            Venta.id_cliente != 1,
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .distinct()
        .all()
    )
    clientes_por_fecha = {}
    for fecha_venta, id_cliente in filas:
        fecha_local = utc_naive_to_local(fecha_venta)
        if not fecha_local:
            continue
        clientes_por_fecha.setdefault(fecha_local.date(), set()).add(int(id_cliente))

    actual = []
    anterior = []
    etiquetas = []
    for offset in range(dias):
        fecha_actual = periodo_actual['desde'] + timedelta(days=offset)
        fecha_anterior = periodo_anterior['desde'] + timedelta(days=offset)
        actual.append(len(clientes_por_fecha.get(fecha_actual, ())))
        anterior.append(len(clientes_por_fecha.get(fecha_anterior, ())))
        etiquetas.append({
            'indice': offset + 1,
            'actual': fecha_actual.strftime('%d/%m'),
            'anterior': fecha_anterior.strftime('%d/%m'),
        })
    return {
        'actual': actual,
        'anterior': anterior,
        'etiquetas': etiquetas,
    }


def _obtener_alertas_stock(fecha_corte: date) -> dict:
    query_riesgo = Producto.query.filter(
        Producto.activo.is_(True),
        Producto.es_servicio.is_(False),
        Producto.stock_actual <= Producto.stock_minimo,
    )
    riesgo_count = query_riesgo.count()
    riesgo_detalle = [
        _serializar_producto_stock_riesgo(producto)
        for producto in query_riesgo
        .order_by(
            (Producto.stock_actual - Producto.stock_minimo).asc(),
            Producto.stock_actual.asc(),
            Producto.nombre.asc(),
        )
        .limit(25)
        .all()
    ]

    desde_inmovilizado = fecha_corte - timedelta(days=DIAS_STOCK_INMOVILIZADO)
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde_inmovilizado, fecha_corte)
    ventas_recientes = (
        db.session.query(DetalleVenta.id_producto.label('id_producto'))
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(DetalleVenta.id_producto)
        .subquery()
    )

    query_inmovilizado = (
        Producto.query.filter(
            Producto.activo.is_(True),
            Producto.es_servicio.is_(False),
            Producto.stock_actual > 0,
        )
        .outerjoin(ventas_recientes, ventas_recientes.c.id_producto == Producto.id_producto)
        .filter(ventas_recientes.c.id_producto.is_(None))
    )
    inmovilizado_count = query_inmovilizado.count()
    inmovilizado_detalle = [
        _serializar_producto_stock_inmovilizado(producto)
        for producto in query_inmovilizado
        .order_by(Producto.stock_actual.desc(), Producto.nombre.asc())
        .limit(25)
        .all()
    ]

    return {
        'riesgo_count': riesgo_count,
        'inmovilizado_count': inmovilizado_count,
        'riesgo_detalle': riesgo_detalle,
        'inmovilizado_detalle': inmovilizado_detalle,
    }


def _serializar_producto_stock_riesgo(producto: Producto) -> dict:
    nombre = (producto.nombre or '').strip() or f'Producto #{producto.id_producto}'
    codigo = (producto.codigo or '').strip() or '-'
    stock_actual = int(producto.stock_actual or 0)
    stock_minimo = int(producto.stock_minimo or 0)
    diferencia = stock_actual - stock_minimo
    return {
        'id_producto': int(producto.id_producto),
        'nombre': nombre,
        'codigo': codigo,
        'stock_actual': stock_actual,
        'stock_minimo': stock_minimo,
        'diferencia_minimo': diferencia,
        'accion': 'Reponer o mover unidades para recuperar el stock mínimo.',
    }


def _serializar_producto_stock_inmovilizado(producto: Producto) -> dict:
    nombre = (producto.nombre or '').strip() or f'Producto #{producto.id_producto}'
    codigo = (producto.codigo or '').strip() or '-'
    stock_actual = int(producto.stock_actual or 0)
    return {
        'id_producto': int(producto.id_producto),
        'nombre': nombre,
        'codigo': codigo,
        'stock_actual': stock_actual,
        'dias_sin_salida': DIAS_STOCK_INMOVILIZADO,
        'accion': 'Liquidar, agrupar en promo o pausar compra hasta que vuelva a rotar.',
    }


def _obtener_inteligencia_gastronomia_segura(periodo_actual: dict, periodo_anterior: dict, cliente_id: int | None) -> dict:
    try:
        return obtener_inteligencia_gastronomia(periodo_actual, periodo_anterior, cliente_id)
    except Exception:
        if has_app_context():
            current_app.logger.exception('No se pudo construir inteligencia gastronomica.')
        return _panel_gastronomia_no_disponible(periodo_actual)


def _panel_gastronomia_no_disponible(periodo_actual: dict) -> dict:
    return {
        'activo': False,
        'cliente_id': None,
        'periodo_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': {
            'ventas_total': 0,
            'ventas_total_label': '₲ 0',
            'pedidos_cobrados': 0,
            'ticket_promedio': 0,
            'ticket_promedio_label': '₲ 0',
            'tiempo_preparacion_min': 0,
            'pedidos_cancelados': 0,
            'ventas_variacion_label': 'Sin cambios',
            'ventas_direccion': 'flat',
            'ticket_variacion_label': 'Sin cambios',
            'ticket_direccion': 'flat',
        },
        'productos_top': [],
        'categorias_top': [],
        'canales': [],
        'modificadores_top': [],
        'horarios_pico': [],
        'stock_menu_alertas': [],
        'promos_horario_bajo': [],
        'productos_bajo_margen': [],
        'clientes_frecuentes': [],
        'insights': [{
            'prioridad': 'baja',
            'titulo': 'Radar gastronomico no disponible',
            'detalle': 'No se pudo leer la informacion gastronomica en este momento.',
            'accion': 'Revisar migraciones o volver a intentar luego.',
        }],
    }


def _construir_acciones(
    clientes: dict,
    stock: dict,
    ventas: dict,
    tienda: dict,
    inventario: dict,
    gastronomia: dict,
    campanas: dict,
) -> list[dict]:
    acciones = []

    if clientes['valiosos_dormidos'] > 0:
        cantidad = clientes['valiosos_dormidos']
        acciones.append({
            'prioridad': 'alta',
            'titulo': f'Llamar a {cantidad} cliente' + ('' if cantidad == 1 else 's') + ' valioso' + ('' if cantidad == 1 else 's'),
            'detalle': 'Tienen buen gasto acumulado y ya están fuera de su ritmo normal de compra.',
            'modal': {
                'clave': 'valiosos_dormidos',
                'titulo': 'Clientes valiosos para contactar',
                'descripcion': 'Se priorizan clientes dormidos con gasto acumulado alto para llamar o escribir por WhatsApp.',
            },
        })

    if clientes['frecuentes_en_pausa'] > 0:
        cantidad = clientes['frecuentes_en_pausa']
        acciones.append({
            'prioridad': 'media',
            'titulo': f'Enviar reactivación a {cantidad} cliente' + ('' if cantidad == 1 else 's') + ' frecuente' + ('' if cantidad == 1 else 's'),
            'detalle': 'Conviene recuperar su recurrencia antes de que se enfríe la relación comercial.',
            'modal': {
                'clave': 'frecuentes_en_pausa',
                'titulo': 'Clientes frecuentes en pausa',
                'descripcion': 'Acá tenés la lista de clientes recurrentes que se enfriaron y conviene reactivar.',
            },
        })

    if stock['riesgo_count'] > 0:
        cantidad = stock['riesgo_count']
        acciones.append({
            'prioridad': 'alta',
            'titulo': f'Revisar {cantidad} producto' + ('' if cantidad == 1 else 's') + ' con riesgo de quiebre',
            'detalle': 'Hay stock al límite o por debajo del mínimo configurado.',
        })

    if stock['inmovilizado_count'] > 0:
        cantidad = stock['inmovilizado_count']
        acciones.append({
            'prioridad': 'media',
            'titulo': f'Mover {cantidad} producto' + ('' if cantidad == 1 else 's') + ' inmovilizado' + ('' if cantidad == 1 else 's'),
            'detalle': f'No registran salida en los últimos {DIAS_STOCK_INMOVILIZADO} días.',
        })

    for insight in inventario.get('insights', [])[:1]:
        acciones.append({
            'prioridad': insight['prioridad'],
            'titulo': insight['titulo'],
            'detalle': insight['accion'],
        })

    for campana in campanas.get('campanas', [])[:1]:
        acciones.append({
            'prioridad': campana['prioridad'],
            'titulo': campana['titulo'],
            'detalle': campana['accion'],
        })

    for insight in ventas.get('insights', [])[:2]:
        acciones.append({
            'prioridad': insight['prioridad'],
            'titulo': insight['titulo'],
            'detalle': insight['accion'],
        })

    for insight in tienda.get('insights', [])[:1]:
        acciones.append({
            'prioridad': insight['prioridad'],
            'titulo': insight['titulo'],
            'detalle': insight['accion'],
        })

    if gastronomia.get('activo'):
        for insight in gastronomia.get('insights', [])[:1]:
            acciones.append({
                'prioridad': insight['prioridad'],
                'titulo': insight['titulo'],
                'detalle': insight['accion'],
            })

    if not acciones:
        acciones.append({
            'prioridad': 'baja',
            'titulo': 'No hay alertas fuertes hoy',
            'detalle': 'El radar inicial no detecta clientes o stock que necesiten acción inmediata.',
        })

    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    acciones.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))
    return acciones
