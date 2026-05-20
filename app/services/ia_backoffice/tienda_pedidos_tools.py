from sqlalchemy import func

from app import db
from app.models import Cliente, Producto, TiendaLead, TiendaPromocion, TiendaPromocionProducto, TiendaVisitaEvento
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.services.tienda_estadisticas import obtener_resumen_estadisticas_tienda
from app.utils.helpers import utc_bounds_for_local_dates
from pedidos.models import PedidoCliente
from pedidos.schema import ESTADOS_LABELS


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _resolver_cliente_tienda(args: dict | None) -> int | None:
    try:
        id_cliente = int((args or {}).get('id_cliente') or 0)
    except Exception:
        return None
    return id_cliente if id_cliente > 0 else None


def _estadisticas_tienda(args: dict | None, per_page: int | None = None) -> tuple[dict, dict | None]:
    id_cliente = _resolver_cliente_tienda(args)
    if not id_cliente:
        return {'encontrado': False, 'error': 'id_cliente_requerido'}, None
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    data = obtener_resumen_estadisticas_tienda(
        id_cliente=id_cliente,
        desde=rango['desde'],
        hasta=rango['hasta'],
        page=1,
        per_page=per_page or top_n,
    )
    return {'encontrado': True, 'id_cliente': id_cliente, 'periodo_label': rango['periodo_label']}, data


def tienda_resumen_analytics(args: dict | None = None, usuario=None) -> dict:
    base, data = _estadisticas_tienda(args)
    if not data:
        return base
    resumen = data['summary']
    return {
        **base,
        'resumen': {
            'total_visitas': int(resumen['total_visitas']),
            'visitantes_unicos': int(resumen['visitantes_unicos']),
            'consultas_iniciadas': int(resumen['leads_generados']),
            'productos_con_visitas': int(resumen['productos_con_visitas']),
            'conversion_global_pct': float(resumen['conversion_global']),
        },
        'productos_mas_vistos': data['ranking'][:5],
        'horarios_pico': data['insights']['horarios_pico'][:5],
        'categorias_populares': data['insights']['categorias_populares'][:5],
    }


def tienda_productos_mucha_vista_poca_consulta(args: dict | None = None, usuario=None) -> dict:
    base, data = _estadisticas_tienda(args, per_page=20)
    if not data:
        return base
    top_n = normalizar_top_n((args or {}).get('top_n'))
    conversion_global = float(data['summary']['conversion_global'] or 0)
    productos = []
    for item in data['ranking']:
        visitas = int(item['total_visitas'] or 0)
        consultas = int(item['leads_generados'] or 0)
        conversion = float(item['conversion_leads'] or 0)
        if visitas <= 0:
            continue
        if consultas == 0 or conversion <= conversion_global:
            productos.append({
                'id_producto': item['id_producto'],
                'codigo': item.get('codigo') or '',
                'nombre': item['nombre'],
                'categoria': item['categoria'],
                'total_visitas': visitas,
                'consultas_iniciadas': consultas,
                'conversion_pct': conversion,
                'conversion_global_pct': conversion_global,
                'accion_sugerida': _accion_producto_tienda(consultas),
            })
    productos.sort(key=lambda item: (-item['total_visitas'], item['consultas_iniciadas'], item['conversion_pct']))
    return {**base, 'top_n': top_n, 'productos': productos[:top_n]}


def _accion_producto_tienda(consultas: int) -> str:
    if consultas <= 0:
        return 'Revisar precio, fotos, stock visible y llamada a consultar por WhatsApp.'
    return 'Comparar precio/oferta con productos similares y reforzar seguimiento comercial.'


def tienda_ofertas_rendimiento(args: dict | None = None, usuario=None) -> dict:
    id_cliente = _resolver_cliente_tienda(args)
    if not id_cliente:
        return {'encontrado': False, 'error': 'id_cliente_requerido'}
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    promociones = (
        TiendaPromocion.query
        .filter(
            TiendaPromocion.id_cliente == id_cliente,
            TiendaPromocion.activa.is_(True),
            TiendaPromocion.fecha_inicio < fin_utc,
            TiendaPromocion.fecha_fin >= inicio_utc,
        )
        .order_by(TiendaPromocion.fecha_inicio.desc(), TiendaPromocion.id_promocion.desc())
        .limit(top_n)
        .all()
    )
    return {
        'encontrado': True,
        'id_cliente': id_cliente,
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'ofertas': [_oferta_payload(promo, id_cliente, inicio_utc, fin_utc) for promo in promociones],
    }


def _oferta_payload(promo: TiendaPromocion, id_cliente: int, inicio_utc, fin_utc) -> dict:
    productos_ids = [rel.id_producto for rel in promo.productos_rel]
    visitas = 0
    consultas = 0
    if productos_ids:
        visitas = (
            TiendaVisitaEvento.query
            .filter(
                TiendaVisitaEvento.id_cliente == id_cliente,
                TiendaVisitaEvento.id_producto.in_(productos_ids),
                TiendaVisitaEvento.fecha_evento >= inicio_utc,
                TiendaVisitaEvento.fecha_evento < fin_utc,
            )
            .count()
        )
        consultas = (
            TiendaLead.query
            .filter(
                TiendaLead.id_cliente == id_cliente,
                TiendaLead.id_producto.in_(productos_ids),
                TiendaLead.fecha_creacion >= inicio_utc,
                TiendaLead.fecha_creacion < fin_utc,
            )
            .count()
        )
    return {
        'id_promocion': promo.id_promocion,
        'nombre': promo.nombre,
        'tipo': promo.tipo,
        'valor': _money(promo.valor),
        'productos_asociados': len(productos_ids),
        'visitas_productos': int(visitas or 0),
        'consultas_productos': int(consultas or 0),
        'conversion_pct': round((consultas / visitas) * 100, 2) if visitas else 0,
        'fecha_inicio': promo.fecha_inicio.isoformat() if promo.fecha_inicio else None,
        'fecha_fin': promo.fecha_fin.isoformat() if promo.fecha_fin else None,
    }


def pedidos_resumen(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    base = PedidoCliente.query.filter(PedidoCliente.fecha_creacion >= inicio_utc, PedidoCliente.fecha_creacion < fin_utc)
    por_estado = (
        base.with_entities(PedidoCliente.estado, func.count(PedidoCliente.id_pedido).label('cantidad'))
        .group_by(PedidoCliente.estado)
        .order_by(func.count(PedidoCliente.id_pedido).desc(), PedidoCliente.estado.asc())
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'total_pedidos': int(base.count()),
        'total_importe': _money(base.with_entities(func.coalesce(func.sum(PedidoCliente.total), 0)).scalar()),
        'total_pagado': _money(base.with_entities(func.coalesce(func.sum(PedidoCliente.total_pagado), 0)).scalar()),
        'saldo_pendiente': _money(base.with_entities(func.coalesce(func.sum(PedidoCliente.saldo_pendiente), 0)).scalar()),
        'por_estado': [
            {
                'estado': row.estado or '',
                'estado_label': ESTADOS_LABELS.get(row.estado, (row.estado or '').replace('_', ' ').title()),
                'cantidad': int(row.cantidad or 0),
            }
            for row in por_estado
        ],
    }


def pedidos_pagos_pendientes(args: dict | None = None, usuario=None) -> dict:
    top_n = normalizar_top_n((args or {}).get('top_n'))
    filas = (
        PedidoCliente.query
        .join(Cliente, Cliente.id_cliente == PedidoCliente.id_cliente)
        .filter(PedidoCliente.saldo_pendiente > 0)
        .with_entities(
            PedidoCliente.id_pedido,
            PedidoCliente.numero_pedido,
            PedidoCliente.estado,
            PedidoCliente.total,
            PedidoCliente.total_pagado,
            PedidoCliente.saldo_pendiente,
            PedidoCliente.fecha_creacion,
            Cliente.nombre.label('cliente'),
        )
        .order_by(PedidoCliente.saldo_pendiente.desc(), PedidoCliente.fecha_creacion.asc())
        .limit(top_n)
        .all()
    )
    return {
        'top_n': top_n,
        'saldo_pendiente_total': _money(
            PedidoCliente.query.with_entities(func.coalesce(func.sum(PedidoCliente.saldo_pendiente), 0)).filter(
                PedidoCliente.saldo_pendiente > 0
            ).scalar()
        ),
        'pedidos': [
            {
                'id_pedido': row.id_pedido,
                'numero_pedido': int(row.numero_pedido or row.id_pedido or 0),
                'cliente': row.cliente,
                'estado': row.estado or '',
                'estado_label': ESTADOS_LABELS.get(row.estado, (row.estado or '').replace('_', ' ').title()),
                'total': _money(row.total),
                'total_pagado': _money(row.total_pagado),
                'saldo_pendiente': _money(row.saldo_pendiente),
                'fecha_creacion': row.fecha_creacion.isoformat() if row.fecha_creacion else None,
            }
            for row in filas
        ],
    }
