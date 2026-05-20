from __future__ import annotations

import csv
from io import StringIO
from datetime import date, timedelta
from decimal import Decimal

from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente
from gastos_corrientes.services.gasto_corriente_service import (
    aplicar_scope_cliente,
    gasto_aplica_en_periodo,
    parse_periodo,
    resolver_fecha_vencimiento,
    sincronizar_pagos_periodo,
)


def _resolver_pago_activo(gasto: GastoCorriente, periodo_anio: int, periodo_mes: int) -> PagoGastoCorriente | None:
    return gasto.pagos.filter(
        PagoGastoCorriente.periodo_anio == periodo_anio,
        PagoGastoCorriente.periodo_mes == periodo_mes,
        PagoGastoCorriente.estado != 'anulado',
    ).order_by(PagoGastoCorriente.id_pago_gasto_corriente.desc()).first()


def _estado_panel(gasto: GastoCorriente, pago: PagoGastoCorriente | None, fecha_vencimiento: date, hoy: date) -> str:
    if pago and (pago.estado or '').strip().lower() == 'pagado':
        return 'pagado'
    if not gasto.activo:
        return 'inactivo'
    return 'vencido' if fecha_vencimiento <= hoy else 'pendiente'


def _alerta_panel(gasto: GastoCorriente, estado_panel: str, fecha_vencimiento: date, hoy: date) -> dict:
    if estado_panel == 'pagado':
        return {'texto': 'Pagado', 'clase': 'bg-sky-100 text-sky-700', 'activa': False}
    if estado_panel == 'inactivo':
        return {'texto': 'Inactivo', 'clase': 'bg-gray-100 text-gray-600', 'activa': False}
    if not gasto.alerta_activa:
        return {'texto': 'Sin alerta', 'clase': 'bg-gray-100 text-gray-500', 'activa': False}

    dias_aviso = max(int(gasto.dias_anticipacion_alerta_int()), 0)
    fecha_alerta = fecha_vencimiento - timedelta(days=dias_aviso)
    if fecha_vencimiento <= hoy:
        return {
            'texto': f'Vencido {fecha_vencimiento.strftime("%d/%m")}',
            'clase': 'bg-rose-100 text-rose-700',
            'activa': True,
        }
    if fecha_alerta <= hoy:
        return {
            'texto': f'Vence {fecha_vencimiento.strftime("%d/%m")}',
            'clase': 'bg-emerald-100 text-emerald-700',
            'activa': True,
        }
    return {'texto': 'En fecha', 'clase': 'bg-emerald-100 text-emerald-700', 'activa': False}


def _pagos_activos_por_gasto(
    gasto_ids: list[int],
    *,
    periodo_anio: int,
    periodo_mes: int,
) -> dict[int, PagoGastoCorriente]:
    if not gasto_ids:
        return {}

    pagos = (
        aplicar_scope_cliente(PagoGastoCorriente.query, PagoGastoCorriente)
        .filter(
            PagoGastoCorriente.id_gasto_corriente.in_(gasto_ids),
            PagoGastoCorriente.periodo_anio == periodo_anio,
            PagoGastoCorriente.periodo_mes == periodo_mes,
            PagoGastoCorriente.estado != 'anulado',
        )
        .order_by(PagoGastoCorriente.id_pago_gasto_corriente.desc())
        .all()
    )

    pagos_por_gasto: dict[int, PagoGastoCorriente] = {}
    for pago in pagos:
        gasto_id = int(pago.id_gasto_corriente or 0)
        if gasto_id and gasto_id not in pagos_por_gasto:
            pagos_por_gasto[gasto_id] = pago
    return pagos_por_gasto


def _categoria_label(categoria: str | None) -> str:
    return (categoria or 'otros').replace('_', ' ').title() or 'Otros'


def _construir_comparativo(
    *,
    total_estimado: Decimal,
    total_pagado: Decimal,
    total_pendiente: Decimal,
    items: list[dict],
) -> dict:
    porcentaje_pagado = Decimal('0.00')
    porcentaje_pendiente = Decimal('0.00')
    if total_estimado > 0:
        porcentaje_pagado = ((total_pagado / total_estimado) * Decimal('100')).quantize(Decimal('0.01'))
        porcentaje_pendiente = ((total_pendiente / total_estimado) * Decimal('100')).quantize(Decimal('0.01'))

    desviacion = (total_pagado - total_estimado).quantize(Decimal('0.01'))
    if desviacion > 0:
        estado_desviacion = 'sobre'
    elif desviacion < 0:
        estado_desviacion = 'bajo'
    else:
        estado_desviacion = 'exacto'

    return {
        'cantidad_items': len(items),
        'cantidad_pagados': sum(1 for item in items if item['estado_panel'] == 'pagado'),
        'cantidad_pendientes': sum(1 for item in items if item['estado_panel'] in {'pendiente', 'vencido'}),
        'porcentaje_pagado': porcentaje_pagado,
        'porcentaje_pendiente': porcentaje_pendiente,
        'desviacion': desviacion,
        'estado_desviacion': estado_desviacion,
    }


def _construir_resumen_categorias(items: list[dict], *, limit: int = 5) -> list[dict]:
    categorias: dict[str, dict] = {}
    for item in items:
        categoria = (item['gasto'].categoria or 'otros').strip().lower() or 'otros'
        bucket = categorias.setdefault(
            categoria,
            {
                'categoria': categoria,
                'label': _categoria_label(categoria),
                'cantidad': 0,
                'pagados': 0,
                'pendientes': 0,
                'vencidos': 0,
                'total_estimado': Decimal('0.00'),
                'total_pagado': Decimal('0.00'),
                'total_pendiente': Decimal('0.00'),
            },
        )
        bucket['cantidad'] += 1
        bucket['total_estimado'] += item['monto_estimado']
        if item['estado_panel'] == 'pagado':
            bucket['pagados'] += 1
            bucket['total_pagado'] += item['monto_pagado']
        if item['estado_panel'] in {'pendiente', 'vencido'}:
            bucket['pendientes'] += 1
            bucket['total_pendiente'] += item['monto_estimado']
        if item['estado_panel'] == 'vencido':
            bucket['vencidos'] += 1

    resumen = list(categorias.values())
    for item in resumen:
        item['porcentaje_pagado'] = Decimal('0.00')
        if item['total_estimado'] > 0:
            item['porcentaje_pagado'] = (
                (item['total_pagado'] / item['total_estimado']) * Decimal('100')
            ).quantize(Decimal('0.01'))

    resumen.sort(
        key=lambda item: (
            -item['total_pagado'],
            -item['total_estimado'],
            -item['cantidad'],
            item['label'].lower(),
        )
    )
    return resumen[: max(int(limit or 5), 1)]


def construir_panel_gastos_corrientes(
    *,
    periodo_raw: str | None,
    categoria: str | None = None,
    estado: str | None = None,
) -> dict:
    hoy = date.today()
    periodo_anio, periodo_mes, periodo = parse_periodo(periodo_raw, today=hoy)
    sincronizar_pagos_periodo(periodo_anio=periodo_anio, periodo_mes=periodo_mes)
    categoria_filtrada = (categoria or '').strip().lower()
    estado_filtrado = (estado or '').strip().lower()

    gastos_query = aplicar_scope_cliente(GastoCorriente.query, GastoCorriente)
    if categoria_filtrada:
        gastos_query = gastos_query.filter(GastoCorriente.categoria == categoria_filtrada)
    gastos = gastos_query.order_by(
        GastoCorriente.activo.desc(),
        GastoCorriente.dia_vencimiento.asc(),
        GastoCorriente.nombre.asc(),
    ).all()

    items = []
    total_estimado = Decimal('0.00')
    total_pagado = Decimal('0.00')
    total_pendiente = Decimal('0.00')
    vencidos = 0
    alertas_activas = 0

    for gasto in gastos:
        pago = _resolver_pago_activo(gasto, periodo_anio, periodo_mes)
        if not gasto_aplica_en_periodo(gasto, periodo_anio, periodo_mes) and pago is None:
            continue

        fecha_vencimiento = resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes)
        estado_panel = _estado_panel(gasto, pago, fecha_vencimiento, hoy)
        alerta = _alerta_panel(gasto, estado_panel, fecha_vencimiento, hoy)

        if estado_filtrado and estado_panel != estado_filtrado:
            continue

        monto_estimado = gasto.monto_estimado_decimal()
        monto_pagado = pago.monto_pagado_decimal() if pago else Decimal('0.00')
        total_estimado += monto_estimado
        if estado_panel == 'pagado':
            total_pagado += monto_pagado
        elif estado_panel in {'pendiente', 'vencido'}:
            total_pendiente += monto_estimado
        if estado_panel == 'vencido':
            vencidos += 1
        if alerta['activa']:
            alertas_activas += 1

        items.append(
            {
                'gasto': gasto,
                'pago': pago,
                'periodo': periodo,
                'fecha_vencimiento': fecha_vencimiento,
                'estado_panel': estado_panel,
                'alerta': alerta,
                'monto_estimado': monto_estimado,
                'monto_pagado': monto_pagado,
            }
        )

    comparativo = _construir_comparativo(
        total_estimado=total_estimado,
        total_pagado=total_pagado,
        total_pendiente=total_pendiente,
        items=items,
    )
    categorias_resumen = _construir_resumen_categorias(items)

    return {
        'periodo': periodo,
        'periodo_anio': periodo_anio,
        'periodo_mes': periodo_mes,
        'categoria': categoria_filtrada,
        'estado': estado_filtrado,
        'items': items,
        'total_estimado': total_estimado,
        'total_pagado': total_pagado,
        'total_pendiente': total_pendiente,
        'vencidos': vencidos,
        'alertas_activas': alertas_activas,
        'comparativo': comparativo,
        'categorias_resumen': categorias_resumen,
    }


def obtener_resumen_dashboard_gastos_corrientes(*, today: date | None = None) -> dict:
    hoy = today or date.today()
    periodo_anio, periodo_mes, periodo = parse_periodo(None, today=hoy)
    sincronizar_pagos_periodo(periodo_anio=periodo_anio, periodo_mes=periodo_mes)
    gastos = (
        aplicar_scope_cliente(GastoCorriente.query, GastoCorriente)
        .filter(GastoCorriente.activo.is_(True))
        .order_by(GastoCorriente.dia_vencimiento.asc(), GastoCorriente.nombre.asc())
        .all()
    )

    if not gastos:
        return {
            'periodo': periodo,
            'vencidos': 0,
            'por_vencer': 0,
            'pendientes': 0,
            'total_alertas': 0,
            'total_pendiente': Decimal('0.00'),
        }

    pagos_por_gasto = _pagos_activos_por_gasto(
        [int(gasto.id_gasto_corriente) for gasto in gastos],
        periodo_anio=periodo_anio,
        periodo_mes=periodo_mes,
    )

    vencidos = 0
    por_vencer = 0
    pendientes = 0
    total_alertas = 0
    total_pendiente = Decimal('0.00')

    for gasto in gastos:
        pago = pagos_por_gasto.get(int(gasto.id_gasto_corriente))
        if not gasto_aplica_en_periodo(gasto, periodo_anio, periodo_mes) and pago is None:
            continue

        if pago and (pago.estado or '').strip().lower() == 'pagado':
            continue

        fecha_vencimiento = resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes)
        monto_estimado = gasto.monto_estimado_decimal()
        total_pendiente += monto_estimado

        if fecha_vencimiento <= hoy:
            vencidos += 1
            if gasto.alerta_activa:
                total_alertas += 1
            continue

        pendientes += 1
        if not gasto.alerta_activa:
            continue

        dias_anticipacion = max(int(gasto.dias_anticipacion_alerta_int()), 0)
        fecha_alerta = fecha_vencimiento - timedelta(days=dias_anticipacion)
        if fecha_alerta <= hoy:
            por_vencer += 1
            total_alertas += 1

    return {
        'periodo': periodo,
        'vencidos': vencidos,
        'por_vencer': por_vencer,
        'pendientes': pendientes,
        'total_alertas': total_alertas,
        'total_pendiente': total_pendiente,
    }


def obtener_dashboard_detallado_gastos_corrientes(*, today: date | None = None) -> dict:
    hoy = today or date.today()
    periodo_raw = f'{hoy.year:04d}-{hoy.month:02d}'
    panel = construir_panel_gastos_corrientes(periodo_raw=periodo_raw)
    resumen = obtener_resumen_dashboard_gastos_corrientes(today=hoy)
    recordatorios = obtener_recordatorios_gastos_corrientes(today=hoy, limit=4)

    categorias_pendientes = [
        {
            'categoria': categoria['categoria'],
            'label': categoria['label'],
            'pendientes': categoria['pendientes'],
            'vencidos': categoria['vencidos'],
            'total_pendiente': categoria['total_pendiente'],
        }
        for categoria in sorted(
            panel.get('categorias_resumen') or [],
            key=lambda item: (
                -item['total_pendiente'],
                -item['vencidos'],
                item['label'].lower(),
            ),
        )
        if categoria['total_pendiente'] > 0
    ][:3]

    items_urgentes = []
    for item in recordatorios.get('items') or []:
        estado_alerta = (item.get('estado_alerta') or '').strip().lower()
        items_urgentes.append(
            {
                'id': item['id'],
                'nombre': item['nombre'],
                'categoria': item['categoria'],
                'detail_label': item['detail_label'],
                'badge_label': item['badge_label'],
                'estado_alerta': estado_alerta,
                'badge_class': (
                    'bg-rose-500/15 text-rose-100 ring-1 ring-rose-300/20'
                    if estado_alerta == 'overdue'
                    else 'bg-amber-500/15 text-amber-100 ring-1 ring-amber-300/20'
                ),
            }
        )

    comparativo = panel.get('comparativo') or {}
    return {
        **resumen,
        'periodo': panel.get('periodo') or resumen['periodo'],
        'total_estimado': panel.get('total_estimado', Decimal('0.00')),
        'total_pagado': panel.get('total_pagado', Decimal('0.00')),
        'total_pendiente': panel.get('total_pendiente', Decimal('0.00')),
        'cantidad_items': comparativo.get('cantidad_items', 0),
        'cantidad_pagados': comparativo.get('cantidad_pagados', 0),
        'cantidad_pendientes': comparativo.get('cantidad_pendientes', 0),
        'porcentaje_pagado': comparativo.get('porcentaje_pagado', Decimal('0.00')),
        'porcentaje_pendiente': comparativo.get('porcentaje_pendiente', Decimal('0.00')),
        'desviacion': comparativo.get('desviacion', Decimal('0.00')),
        'estado_desviacion': comparativo.get('estado_desviacion', 'exacto'),
        'items_urgentes': items_urgentes,
        'categorias_pendientes': categorias_pendientes,
    }


def obtener_recordatorios_gastos_corrientes(
    *,
    today: date | None = None,
    limit: int = 20,
) -> dict:
    hoy = today or date.today()
    periodo_anio, periodo_mes, periodo = parse_periodo(None, today=hoy)
    sincronizar_pagos_periodo(periodo_anio=periodo_anio, periodo_mes=periodo_mes)
    gastos = (
        aplicar_scope_cliente(GastoCorriente.query, GastoCorriente)
        .filter(
            GastoCorriente.activo.is_(True),
            GastoCorriente.alerta_activa.is_(True),
        )
        .order_by(GastoCorriente.dia_vencimiento.asc(), GastoCorriente.nombre.asc())
        .all()
    )

    pagos_por_gasto = _pagos_activos_por_gasto(
        [int(gasto.id_gasto_corriente) for gasto in gastos],
        periodo_anio=periodo_anio,
        periodo_mes=periodo_mes,
    )

    overdue_count = 0
    alert_count = 0
    items = []
    limite = min(max(int(limit or 20), 1), 100)

    for gasto in gastos:
        pago = pagos_por_gasto.get(int(gasto.id_gasto_corriente))
        if not gasto_aplica_en_periodo(gasto, periodo_anio, periodo_mes) and pago is None:
            continue

        if pago and (pago.estado or '').strip().lower() == 'pagado':
            continue

        fecha_vencimiento = resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes)
        dias_anticipacion = max(int(gasto.dias_anticipacion_alerta_int()), 0)
        fecha_alerta = fecha_vencimiento - timedelta(days=dias_anticipacion)

        estado_alerta = ''
        badge_label = ''
        detail_label = ''
        if fecha_vencimiento <= hoy:
            estado_alerta = 'overdue'
            badge_label = 'Vencido'
            detail_label = f'Vencido desde {fecha_vencimiento.strftime("%d/%m/%Y")}'
            overdue_count += 1
        elif fecha_alerta <= hoy:
            dias_restantes = (fecha_vencimiento - hoy).days
            estado_alerta = 'alert'
            badge_label = 'Por vencer'
            detail_label = (
                f'Vence hoy ({fecha_vencimiento.strftime("%d/%m/%Y")})'
                if dias_restantes == 0
                else f'Vence en {dias_restantes} día{"s" if dias_restantes != 1 else ""} ({fecha_vencimiento.strftime("%d/%m/%Y")})'
            )
            alert_count += 1
        else:
            continue

        items.append(
            {
                'id': int(gasto.id_gasto_corriente),
                'nombre': gasto.nombre,
                'categoria': (gasto.categoria or '').replace('_', ' ').title() or 'Otros',
                'fecha_vencimiento': fecha_vencimiento.isoformat(),
                'fecha_vencimiento_label': fecha_vencimiento.strftime('%d/%m/%Y'),
                'estado_alerta': estado_alerta,
                'badge_label': badge_label,
                'detail_label': detail_label,
                'periodo': periodo,
                'dias_restantes': (fecha_vencimiento - hoy).days,
                'alert_key': f'{int(gasto.id_gasto_corriente)}:{estado_alerta}:{periodo}:{fecha_vencimiento.isoformat()}',
            }
        )

    items.sort(
        key=lambda item: (
            0 if item['estado_alerta'] == 'overdue' else 1,
            item['fecha_vencimiento'],
            item['nombre'].lower(),
            item['id'],
        )
    )

    return {
        'count': overdue_count + alert_count,
        'has_alerts': (overdue_count + alert_count) > 0,
        'overdue_count': overdue_count,
        'alert_count': alert_count,
        'periodo': periodo,
        'server_date': hoy.isoformat(),
        'items': items[:limite],
    }


def obtener_historial_pagos(gasto: GastoCorriente) -> list[PagoGastoCorriente]:
    return gasto.pagos.order_by(
        PagoGastoCorriente.periodo_anio.desc(),
        PagoGastoCorriente.periodo_mes.desc(),
        PagoGastoCorriente.id_pago_gasto_corriente.desc(),
    ).all()


def generar_csv_panel_gastos_corrientes(panel: dict) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    comparativo = panel.get('comparativo') or {}

    writer.writerow(['Reporte de Gastos Corrientes'])
    writer.writerow(['Periodo', panel.get('periodo') or ''])
    writer.writerow(['Categoria', panel.get('categoria') or 'Todas'])
    writer.writerow(['Estado', panel.get('estado') or 'Todos'])
    writer.writerow(['Total estimado', f"{panel.get('total_estimado', Decimal('0.00')):.2f}"])
    writer.writerow(['Total pagado', f"{panel.get('total_pagado', Decimal('0.00')):.2f}"])
    writer.writerow(['Total pendiente', f"{panel.get('total_pendiente', Decimal('0.00')):.2f}"])
    writer.writerow(['Porcentaje pagado', f"{comparativo.get('porcentaje_pagado', Decimal('0.00')):.2f}"])
    writer.writerow(['Desviacion', f"{comparativo.get('desviacion', Decimal('0.00')):.2f}"])
    writer.writerow([])
    writer.writerow(
        [
            'Concepto',
            'Categoria',
            'Descripcion',
            'Periodo',
            'Vencimiento',
            'Estado',
            'Alerta',
            'Estimado',
            'Pagado',
            'Pendiente',
            'Pagado desde caja',
            'Comprobante',
            'Adjunto',
            'Observacion',
        ]
    )

    for item in panel.get('items') or []:
        pago = item.get('pago')
        monto_pagado = item.get('monto_pagado') or Decimal('0.00')
        monto_pendiente = item.get('monto_estimado') if item.get('estado_panel') in {'pendiente', 'vencido'} else Decimal('0.00')
        writer.writerow(
            [
                item['gasto'].nombre,
                _categoria_label(item['gasto'].categoria),
                item['gasto'].descripcion or '',
                item.get('periodo') or panel.get('periodo') or '',
                item['fecha_vencimiento'].isoformat() if item.get('fecha_vencimiento') else '',
                item.get('estado_panel') or '',
                item.get('alerta', {}).get('texto') or '',
                f"{item.get('monto_estimado', Decimal('0.00')):.2f}",
                f"{monto_pagado:.2f}",
                f"{monto_pendiente:.2f}",
                'Si' if pago and pago.pagado_desde_caja else 'No',
                pago.numero_comprobante if pago and pago.numero_comprobante else '',
                pago.comprobante_adjunto_nombre if pago and pago.comprobante_adjunto_nombre else '',
                pago.observacion if pago and pago.observacion else '',
            ]
        )

    return buffer.getvalue()
