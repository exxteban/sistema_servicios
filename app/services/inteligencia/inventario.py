from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app import db
from app.models import Categoria, DetalleVenta, Producto, TiendaLead, TiendaVisitaEvento, Venta
from app.services.inteligencia.common import DIAS_STOCK_INMOVILIZADO, calcular_variacion, formatear_rango
from app.utils.helpers import utc_bounds_for_local_dates

DIAS_COBERTURA_CRITICA = 14
MIN_UNIDADES_ROTACION = 3
MIN_VISITAS_ATENCION = 4


def obtener_inteligencia_inventario(
    fecha_corte: date,
    periodo_actual: dict,
    id_cliente_tienda: int | None = None,
) -> dict:
    dias_periodo = max((periodo_actual['hasta'] - periodo_actual['desde']).days + 1, 1)
    periodo_anterior = {
        'hasta': periodo_actual['desde'] - timedelta(days=1),
        'desde': periodo_actual['desde'] - timedelta(days=dias_periodo),
    }
    periodo_inmovilizado = {
        'desde': fecha_corte - timedelta(days=DIAS_STOCK_INMOVILIZADO - 1),
        'hasta': fecha_corte,
    }

    ventas_actual = _mapa_ventas_producto(periodo_actual['desde'], periodo_actual['hasta'])
    ventas_anterior = _mapa_ventas_producto(periodo_anterior['desde'], periodo_anterior['hasta'])
    ventas_inmovilizado = _mapa_ventas_producto(periodo_inmovilizado['desde'], periodo_inmovilizado['hasta'])
    atencion_tienda = _mapa_atencion_tienda(
        periodo_actual['desde'],
        periodo_actual['hasta'],
        id_cliente_tienda,
    )
    productos = _obtener_productos_base()

    riesgo_quiebre = []
    rotacion_rapida = []
    stock_inmovilizado = []
    atencion_sin_rotacion = []

    for producto in productos:
        id_producto = int(producto['id_producto'])
        ventas_producto_actual = ventas_actual.get(id_producto, {})
        ventas_producto_anterior = ventas_anterior.get(id_producto, {})
        ventas_producto_inmov = ventas_inmovilizado.get(id_producto, {})
        atencion_producto = atencion_tienda.get(id_producto, {})

        unidades_actual = int(ventas_producto_actual.get('unidades', 0))
        unidades_anterior = int(ventas_producto_anterior.get('unidades', 0))
        unidades_inmov = int(ventas_producto_inmov.get('unidades', 0))
        total_visitas = int(atencion_producto.get('total_visitas', 0))
        leads_generados = int(atencion_producto.get('leads_generados', 0))
        conversion_leads = _calcular_conversion(total_visitas, leads_generados)

        cobertura_dias = None
        if unidades_actual > 0:
            rotacion_diaria = unidades_actual / dias_periodo
            cobertura_dias = round(producto['stock_actual'] / rotacion_diaria, 1) if rotacion_diaria > 0 else None

        variacion = calcular_variacion(unidades_actual, unidades_anterior)

        base = {
            'id_producto': id_producto,
            'codigo': producto['codigo'],
            'nombre': producto['nombre'],
            'categoria': producto['categoria'],
            'stock_actual': producto['stock_actual'],
            'stock_minimo': producto['stock_minimo'],
            'unidades_actual': unidades_actual,
            'unidades_anterior': unidades_anterior,
            'variacion_label': variacion['label'],
            'variacion_direccion': variacion['direccion'],
            'cobertura_dias': cobertura_dias,
            'cobertura_dias_label': _formatear_cobertura(cobertura_dias),
        }

        if _es_riesgo_quiebre(base, unidades_inmov):
            riesgo_quiebre.append({
                **base,
                'accion': 'Reponer stock o redistribuir unidades antes de perder ventas.',
            })

        if _es_rotacion_rapida(base):
            rotacion_rapida.append({
                **base,
                'accion': 'Seguir este ritmo y preparar reposición para no cortar la salida.',
            })

        if producto['stock_actual'] > 0 and unidades_inmov <= 0:
            stock_inmovilizado.append({
                **base,
                'accion': 'Liquidar, reubicar o pausar compras hasta que vuelva a rotar.',
            })

        if producto['stock_actual'] > 0 and unidades_actual <= 0 and total_visitas >= MIN_VISITAS_ATENCION:
            atencion_sin_rotacion.append({
                **base,
                'total_visitas': total_visitas,
                'leads_generados': leads_generados,
                'conversion_leads': conversion_leads,
                'conversion_leads_label': f'{conversion_leads:.1f}%',
                'accion': 'Revisar precio, presentación o seguimiento porque genera interés sin salida.',
            })

    riesgo_quiebre.sort(
        key=lambda item: (
            item['cobertura_dias'] if item['cobertura_dias'] is not None else 9999,
            -item['unidades_actual'],
            item['nombre'].lower(),
        )
    )
    rotacion_rapida.sort(
        key=lambda item: (
            item['cobertura_dias'] if item['cobertura_dias'] is not None else 9999,
            -item['unidades_actual'],
            item['nombre'].lower(),
        )
    )
    stock_inmovilizado.sort(
        key=lambda item: (
            -item['stock_actual'],
            item['nombre'].lower(),
        )
    )
    atencion_sin_rotacion.sort(
        key=lambda item: (
            -item['total_visitas'],
            item['conversion_leads'],
            item['nombre'].lower(),
        )
    )

    insights = _construir_insights_inventario(
        riesgo_quiebre=riesgo_quiebre,
        rotacion_rapida=rotacion_rapida,
        stock_inmovilizado=stock_inmovilizado,
        atencion_sin_rotacion=atencion_sin_rotacion,
    )

    return {
        'periodo_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': {
            'riesgo_quiebre': len(riesgo_quiebre),
            'rotacion_rapida': len(rotacion_rapida),
            'stock_inmovilizado': len(stock_inmovilizado),
            'atencion_sin_rotacion': len(atencion_sin_rotacion),
        },
        'riesgo_quiebre': riesgo_quiebre[:4],
        'rotacion_rapida': rotacion_rapida[:4],
        'stock_inmovilizado': stock_inmovilizado[:4],
        'atencion_sin_rotacion': atencion_sin_rotacion[:4],
        'insights': insights,
        'hay_senales_tienda': bool(id_cliente_tienda),
    }


def _obtener_productos_base() -> list[dict]:
    filas = (
        db.session.query(
            Producto.id_producto,
            Producto.codigo,
            Producto.nombre,
            Producto.stock_actual,
            Producto.stock_minimo,
            Categoria.nombre.label('categoria_nombre'),
        )
        .join(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .filter(
            Producto.activo.is_(True),
            Producto.es_servicio.is_(False),
        )
        .all()
    )
    return [{
        'id_producto': int(fila.id_producto),
        'codigo': (fila.codigo or '').strip(),
        'nombre': (fila.nombre or '').strip() or f'Producto #{fila.id_producto}',
        'categoria': (fila.categoria_nombre or 'Sin categoría').strip() or 'Sin categoría',
        'stock_actual': int(fila.stock_actual or 0),
        'stock_minimo': int(fila.stock_minimo or 0),
    } for fila in filas]


def _mapa_ventas_producto(desde: date, hasta: date) -> dict[int, dict]:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    filas = (
        db.session.query(
            DetalleVenta.id_producto,
            func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades'),
            func.coalesce(func.sum(DetalleVenta.subtotal), 0).label('facturacion'),
        )
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(DetalleVenta.id_producto)
        .all()
    )
    return {
        int(fila.id_producto): {
            'unidades': int(fila.unidades or 0),
            'facturacion': float(fila.facturacion or 0),
        }
        for fila in filas
    }


def _mapa_atencion_tienda(desde: date, hasta: date, id_cliente_tienda: int | None) -> dict[int, dict]:
    if not id_cliente_tienda:
        return {}

    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    visitas = (
        db.session.query(
            TiendaVisitaEvento.id_producto,
            func.count(TiendaVisitaEvento.id_visita).label('total_visitas'),
        )
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente_tienda,
            TiendaVisitaEvento.fecha_evento >= inicio_utc,
            TiendaVisitaEvento.fecha_evento < fin_utc,
        )
        .group_by(TiendaVisitaEvento.id_producto)
        .all()
    )
    leads = (
        db.session.query(
            TiendaLead.id_producto,
            func.count(TiendaLead.id_lead).label('leads_generados'),
        )
        .filter(
            TiendaLead.id_cliente == id_cliente_tienda,
            TiendaLead.fecha_creacion >= inicio_utc,
            TiendaLead.fecha_creacion < fin_utc,
            TiendaLead.id_producto.isnot(None),
        )
        .group_by(TiendaLead.id_producto)
        .all()
    )

    resultado = {
        int(fila.id_producto): {
            'total_visitas': int(fila.total_visitas or 0),
            'leads_generados': 0,
        }
        for fila in visitas
    }
    for fila in leads:
        id_producto = int(fila.id_producto)
        item = resultado.setdefault(
            id_producto,
            {'total_visitas': 0, 'leads_generados': 0},
        )
        item['leads_generados'] = int(fila.leads_generados or 0)
    return resultado


def _es_riesgo_quiebre(producto: dict, unidades_inmov: int) -> bool:
    if unidades_inmov <= 0:
        return False
    if producto['stock_actual'] <= producto['stock_minimo']:
        return True
    cobertura_dias = producto['cobertura_dias']
    return cobertura_dias is not None and cobertura_dias <= DIAS_COBERTURA_CRITICA


def _es_rotacion_rapida(producto: dict) -> bool:
    if producto['unidades_actual'] < MIN_UNIDADES_ROTACION:
        return False
    cobertura_dias = producto['cobertura_dias']
    if cobertura_dias is not None and cobertura_dias <= 21:
        return True
    return producto['unidades_anterior'] > 0 and producto['unidades_actual'] > producto['unidades_anterior']


def _construir_insights_inventario(
    riesgo_quiebre: list[dict],
    rotacion_rapida: list[dict],
    stock_inmovilizado: list[dict],
    atencion_sin_rotacion: list[dict],
) -> list[dict]:
    insights = []

    if riesgo_quiebre:
        producto = riesgo_quiebre[0]
        insights.append({
            'prioridad': 'alta',
            'titulo': f"{producto['nombre']} puede quebrar en breve",
            'detalle': (
                f"Vendió {producto['unidades_actual']} unidad"
                f"{'' if producto['unidades_actual'] == 1 else 'es'} en el período y hoy tiene "
                f"{producto['stock_actual']} en stock."
            ),
            'accion': producto['accion'],
        })

    if stock_inmovilizado:
        cantidad = len(stock_inmovilizado)
        insights.append({
            'prioridad': 'media',
            'titulo': f'Hay {cantidad} producto' + ('' if cantidad == 1 else 's') + ' inmovilizado' + ('' if cantidad == 1 else 's'),
            'detalle': f"No registran salida en los últimos {DIAS_STOCK_INMOVILIZADO} días y siguen ocupando capital.",
            'accion': 'Conviene liquidarlos, reubicarlos o frenar nuevas compras de ese grupo.',
        })

    if atencion_sin_rotacion:
        producto = atencion_sin_rotacion[0]
        insights.append({
            'prioridad': 'media',
            'titulo': f"{producto['nombre']} atrae miradas pero no rota",
            'detalle': (
                f"Recibe {producto['total_visitas']} visita"
                f"{'' if producto['total_visitas'] == 1 else 's'} y no registra ventas en el período."
            ),
            'accion': producto['accion'],
        })
    elif rotacion_rapida:
        producto = rotacion_rapida[0]
        insights.append({
            'prioridad': 'baja',
            'titulo': f"{producto['nombre']} lidera la rotación actual",
            'detalle': (
                f"Movió {producto['unidades_actual']} unidad"
                f"{'' if producto['unidades_actual'] == 1 else 'es'} y su cobertura estimada es de "
                f"{producto['cobertura_dias_label'].lower()}."
            ),
            'accion': producto['accion'],
        })

    if not insights:
        insights.append({
            'prioridad': 'baja',
            'titulo': 'Todavía no hay señales fuertes de inventario',
            'detalle': 'El período actual no muestra rotación suficiente como para priorizar movimientos finos.',
            'accion': 'Seguir acumulando ventas para abrir este radar con más precisión.',
        })

    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    insights.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))
    return insights[:3]


def _calcular_conversion(total_visitas: int, leads_generados: int) -> float:
    if total_visitas <= 0:
        return 0.0
    return round((leads_generados / total_visitas) * 100, 1)


def _formatear_cobertura(cobertura_dias: float | None) -> str:
    if cobertura_dias is None:
        return 'Sin salida reciente'
    return f'{cobertura_dias:.1f} días'
