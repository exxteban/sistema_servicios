from datetime import date
from decimal import Decimal

from app.models import GastoCorriente, PagoGastoCorriente
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from gastos_corrientes.services.gasto_corriente_service import (
    gasto_aplica_en_periodo,
    resolver_fecha_vencimiento,
)


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _periodo(args: dict | None) -> dict:
    rango = resolver_rango(args)
    desde = rango['desde']
    return {
        **rango,
        'anio': int(desde.year),
        'mes': int(desde.month),
        'periodo': f'{desde.year:04d}-{desde.month:02d}',
    }


def _scope_cliente(usuario):
    try:
        cliente_id = int(getattr(usuario, 'id_cliente', 0) or 0)
    except Exception:
        cliente_id = 0
    return cliente_id or None


def _aplicar_scope(query, model, usuario):
    cliente_id = _scope_cliente(usuario)
    if cliente_id:
        return query.filter(model.cliente_id == cliente_id)
    if usuario and getattr(usuario, 'es_admin', lambda: False)():
        return query
    return query.filter(model.cliente_id.is_(None))


def _pagos_activos(anio: int, mes: int, usuario) -> dict[int, PagoGastoCorriente]:
    pagos = (
        _aplicar_scope(PagoGastoCorriente.query, PagoGastoCorriente, usuario)
        .filter(
            PagoGastoCorriente.periodo_anio == anio,
            PagoGastoCorriente.periodo_mes == mes,
            PagoGastoCorriente.estado != 'anulado',
        )
        .order_by(PagoGastoCorriente.id_pago_gasto_corriente.asc())
        .all()
    )
    por_gasto = {}
    for pago in pagos:
        por_gasto[int(pago.id_gasto_corriente)] = pago
    return por_gasto


def _estado_gasto(gasto, pago, vencimiento: date, hoy: date) -> str:
    if pago and (pago.estado or '').strip().lower() == 'pagado':
        return 'pagado'
    return 'vencido' if vencimiento <= hoy else 'pendiente'


def _items_periodo(args: dict | None, usuario) -> tuple[dict, list[dict]]:
    periodo = _periodo(args)
    hoy = date.today()
    gastos = (
        _aplicar_scope(GastoCorriente.query, GastoCorriente, usuario)
        .filter(GastoCorriente.activo.is_(True))
        .order_by(GastoCorriente.dia_vencimiento.asc(), GastoCorriente.nombre.asc())
        .all()
    )
    pagos = _pagos_activos(periodo['anio'], periodo['mes'], usuario)
    items = []
    for gasto in gastos:
        pago = pagos.get(int(gasto.id_gasto_corriente))
        if not gasto_aplica_en_periodo(gasto, periodo['anio'], periodo['mes']) and pago is None:
            continue
        vencimiento = resolver_fecha_vencimiento(gasto, periodo['anio'], periodo['mes'])
        estado = _estado_gasto(gasto, pago, vencimiento, hoy)
        estimado = _money(pago.monto_estimado if pago else gasto.monto_estimado)
        pagado = _money(pago.monto_pagado if pago else Decimal('0'))
        pendiente = 0.0 if estado == 'pagado' else estimado
        items.append({
            'id_gasto_corriente': int(gasto.id_gasto_corriente),
            'nombre': gasto.nombre,
            'categoria': (gasto.categoria or 'otros').strip().lower() or 'otros',
            'fecha_vencimiento': vencimiento,
            'estado': estado,
            'monto_estimado': estimado,
            'monto_pagado': pagado,
            'monto_pendiente': pendiente,
            'alerta_activa': bool(gasto.alerta_activa),
        })
    return periodo, items


def gastos_resumen_periodo(args: dict | None = None, usuario=None) -> dict:
    periodo, items = _items_periodo(args, usuario)
    return {
        'periodo_label': periodo['periodo_label'],
        'periodo': periodo['periodo'],
        'total_estimado': sum(item['monto_estimado'] for item in items),
        'total_pagado': sum(item['monto_pagado'] for item in items if item['estado'] == 'pagado'),
        'total_pendiente': sum(item['monto_pendiente'] for item in items),
        'vencidos': sum(1 for item in items if item['estado'] == 'vencido'),
        'alertas_activas': sum(1 for item in items if item['estado'] != 'pagado' and item['alerta_activa']),
        'cantidad_items': len(items),
        'cantidad_pagados': sum(1 for item in items if item['estado'] == 'pagado'),
        'cantidad_pendientes': sum(1 for item in items if item['estado'] in {'pendiente', 'vencido'}),
    }


def gastos_por_categoria(args: dict | None = None, usuario=None) -> dict:
    periodo, items = _items_periodo(args, usuario)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    categorias = {}
    for item in items:
        bucket = categorias.setdefault(item['categoria'], {
            'categoria': item['categoria'],
            'cantidad': 0,
            'pagados': 0,
            'pendientes': 0,
            'vencidos': 0,
            'total_estimado': 0.0,
            'total_pagado': 0.0,
            'total_pendiente': 0.0,
        })
        bucket['cantidad'] += 1
        bucket['total_estimado'] += item['monto_estimado']
        bucket['total_pagado'] += item['monto_pagado'] if item['estado'] == 'pagado' else 0.0
        bucket['total_pendiente'] += item['monto_pendiente']
        bucket['pagados'] += 1 if item['estado'] == 'pagado' else 0
        bucket['pendientes'] += 1 if item['estado'] in {'pendiente', 'vencido'} else 0
        bucket['vencidos'] += 1 if item['estado'] == 'vencido' else 0
    salida = sorted(
        categorias.values(),
        key=lambda item: (-item['total_pendiente'], -item['total_estimado'], item['categoria']),
    )
    return {'periodo_label': periodo['periodo_label'], 'periodo': periodo['periodo'], 'categorias': salida[:top_n]}


def gastos_vencidos(args: dict | None = None, usuario=None) -> dict:
    periodo, items = _items_periodo(args, usuario)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    vencidos = [item for item in items if item['estado'] == 'vencido']
    vencidos.sort(key=lambda item: (item['fecha_vencimiento'], -item['monto_pendiente'], item['nombre']))
    return {
        'periodo_label': periodo['periodo_label'],
        'periodo': periodo['periodo'],
        'top_n': top_n,
        'gastos': [
            {**item, 'fecha_vencimiento': item['fecha_vencimiento'].isoformat()}
            for item in vencidos[:top_n]
        ],
    }
