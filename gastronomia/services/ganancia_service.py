"""Ganancia estimada dia a dia: ventas cobradas - costo estimado de lo vendido - gastos."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import or_

from app import db
from app.models import MovimientoCaja
from app.models.caja import REFERENCIA_COMPRA_INSUMOS
from app.models.compra import Compra
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates, utc_naive_to_local
from control_de_empleados.models import EmpleadoPago
from gastos_corrientes.models import PagoGastoCorriente
from gastronomia.models import GastronomiaPedidoItem, GastronomiaPedidoPago
from gastronomia.services.costos_service import costo_total_por_plato


MAX_DIAS = 93
CAMPOS_SUMABLES = (
    'ventas', 'pedidos', 'costo', 'gastos', 'gastos_caja', 'gastos_fijos', 'sueldos', 'insumos_caja',
    'unidades', 'unidades_sin_costo',
)


def ganancia_estimada(cliente_id: int, fecha_desde: str | None = None, fecha_hasta: str | None = None) -> dict:
    desde, hasta = _rango(fecha_desde, fecha_hasta)
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    dias = {desde + timedelta(days=n): _dia_vacio(desde + timedelta(days=n)) for n in range((hasta - desde).days + 1)}

    pagos = (
        GastronomiaPedidoPago.query
        .filter(
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .all()
    )
    dia_por_pedido = {}
    for pago in pagos:
        dia = _dia_local(pago.fecha_pago)
        if dia not in dias:
            continue
        dia_por_pedido[int(pago.pedido_id)] = dia
        dias[dia]['ventas'] += float(pago.total_cobrado or 0)
        dias[dia]['pedidos'] += 1

    platos = _platos_vendidos(cliente_id, dia_por_pedido, dias)
    detalle_gastos = defaultdict(lambda: {'monto': 0.0, 'veces': 0})
    _sumar_gastos(cliente_id, inicio, fin, desde, hasta, dias, detalle_gastos)

    filas = [_cerrar_dia(dia) for dia in dias.values()]
    totales = _cerrar_dia({
        **_dia_vacio(None),
        **{campo: sum(fila[campo] for fila in filas) for campo in CAMPOS_SUMABLES},
    })
    return {
        'periodo': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()},
        'totales': totales,
        'dias': filas,
        'platos': sorted(platos.values(), key=lambda item: -item['ganancia']),
        'platos_sin_costo': sorted(
            (item for item in platos.values() if item['costo_unitario'] <= 0),
            key=lambda item: -item['cantidad'],
        ),
        'compras': _compras_periodo(desde, hasta),
        'gastos_detalle': [
            {'concepto': concepto, 'tipo': tipo, **valores}
            for (tipo, concepto), valores in sorted(detalle_gastos.items(), key=lambda kv: -kv[1]['monto'])
        ],
    }


def _platos_vendidos(cliente_id: int, dia_por_pedido: dict, dias: dict) -> dict:
    if not dia_por_pedido:
        return {}
    items = (
        GastronomiaPedidoItem.query
        .filter(
            GastronomiaPedidoItem.cliente_id == int(cliente_id),
            GastronomiaPedidoItem.pedido_id.in_(list(dia_por_pedido)),
        )
        .all()
    )
    costos = costo_total_por_plato(cliente_id, sorted({int(item.producto_id) for item in items}))
    platos = {}
    for item in items:
        cantidad = int(item.cantidad or 0)
        costo_unitario = costos.get(int(item.producto_id), 0.0)
        dia = dias[dia_por_pedido[int(item.pedido_id)]]
        dia['costo'] += costo_unitario * cantidad
        dia['unidades'] += cantidad
        if costo_unitario <= 0:
            dia['unidades_sin_costo'] += cantidad
        plato = platos.setdefault(int(item.producto_id), {
            'producto_id': int(item.producto_id),
            'nombre': item.nombre_producto,
            'cantidad': 0,
            'ventas': 0.0,
            'costo': 0.0,
            'costo_unitario': costo_unitario,
        })
        plato['cantidad'] += cantidad
        plato['ventas'] += float(item.subtotal or 0)
        plato['costo'] += costo_unitario * cantidad
    for plato in platos.values():
        plato['ganancia'] = plato['ventas'] - plato['costo']
        plato['ganancia_pct'] = round(plato['ganancia'] / plato['ventas'] * 100, 1) if plato['ventas'] > 0 else 0.0
    return platos


def _sumar_gastos(cliente_id: int, inicio, fin, desde: date, hasta: date, dias: dict, detalle: dict) -> None:
    # Egresos manuales de caja: gas, delivery, etc. Los marcados como compra de
    # insumos no se restan: esa mercaderia ya esta en el costo de receta.
    egresos = (
        MovimientoCaja.query
        .filter(
            MovimientoCaja.tipo == 'egreso',
            or_(
                MovimientoCaja.referencia_tipo.is_(None),
                MovimientoCaja.referencia_tipo.in_(('', REFERENCIA_COMPRA_INSUMOS)),
            ),
            MovimientoCaja.fecha_movimiento >= inicio,
            MovimientoCaja.fecha_movimiento < fin,
        )
        .all()
    )
    for mov in egresos:
        dia = _dia_local(mov.fecha_movimiento)
        if mov.referencia_tipo == REFERENCIA_COMPRA_INSUMOS:
            if dia in dias:
                dias[dia]['insumos_caja'] += float(mov.monto or 0)
            continue
        if _sumar_gasto(dias, dia, 'gastos_caja', mov.monto):
            _anotar(detalle, 'caja', _concepto(mov.motivo, 'Gasto de caja'), mov.monto)

    # Gastos fijos pagados (alquiler, luz, sueldos), se paguen o no desde caja.
    pagos_fijos = (
        PagoGastoCorriente.query
        .filter(
            PagoGastoCorriente.estado == 'pagado',
            PagoGastoCorriente.fecha_pago >= desde,
            PagoGastoCorriente.fecha_pago <= hasta,
            or_(PagoGastoCorriente.cliente_id == int(cliente_id), PagoGastoCorriente.cliente_id.is_(None)),
        )
        .all()
    )
    for pago in pagos_fijos:
        if _sumar_gasto(dias, pago.fecha_pago, 'gastos_fijos', pago.monto_pagado):
            nombre = getattr(getattr(pago, 'gasto_corriente', None), 'nombre', None)
            _anotar(detalle, 'fijo', _concepto(nombre, 'Gasto fijo'), pago.monto_pagado)

    # Sueldos registrados en Control de empleados (no generan movimiento de caja).
    sueldos = (
        EmpleadoPago.query
        .filter(
            EmpleadoPago.fecha_pago >= desde,
            EmpleadoPago.fecha_pago <= hasta,
            or_(EmpleadoPago.cliente_id == int(cliente_id), EmpleadoPago.cliente_id.is_(None)),
        )
        .all()
    )
    for pago in sueldos:
        if _sumar_gasto(dias, pago.fecha_pago, 'sueldos', pago.total_pagado):
            _anotar(detalle, 'sueldo', 'Sueldos', pago.total_pagado)


def _sumar_gasto(dias: dict, dia: date | None, campo: str, monto) -> bool:
    if dia not in dias:
        return False
    dias[dia][campo] += float(monto or 0)
    dias[dia]['gastos'] += float(monto or 0)
    return True


def _anotar(detalle: dict, tipo: str, concepto: str, monto) -> None:
    item = detalle[(tipo, concepto)]
    item['monto'] = round(item['monto'] + float(monto or 0), 2)
    item['veces'] += 1


def _concepto(texto: str | None, por_defecto: str) -> str:
    # Agrupa "garrafa de gas" y "Garrafa de gas " bajo el mismo renglon.
    limpio = ' '.join((texto or '').split())
    return limpio[:1].upper() + limpio[1:] if limpio else por_defecto


def _compras_periodo(desde: date, hasta: date) -> float:
    # Informativo: lo que se pago en mercaderia. No se resta (ya esta en el costo estimado).
    total = (
        db.session.query(db.func.coalesce(db.func.sum(Compra.total), 0))
        .filter(
            Compra.fecha_compra >= desde,
            Compra.fecha_compra <= hasta,
            Compra.estado != 'anulada',
        )
        .scalar()
    )
    return float(total or 0)


def _dia_vacio(dia: date | None) -> dict:
    return {
        'fecha': dia.isoformat() if dia else None,
        'ventas': 0.0,
        'pedidos': 0,
        'costo': 0.0,
        'gastos': 0.0,
        'gastos_caja': 0.0,
        'gastos_fijos': 0.0,
        'sueldos': 0.0,
        'insumos_caja': 0.0,
        'unidades': 0,
        'unidades_sin_costo': 0,
    }


def _cerrar_dia(dia: dict) -> dict:
    ventas = dia['ventas']
    ganancia_bruta = ventas - dia['costo']
    return {
        **{clave: (round(valor, 2) if isinstance(valor, float) else valor) for clave, valor in dia.items()},
        'ganancia_bruta': round(ganancia_bruta, 2),
        'ganancia_neta': round(ganancia_bruta - dia['gastos'], 2),
        'costo_pct': round(dia['costo'] / ventas * 100, 1) if ventas > 0 else 0.0,
        'margen_pct': round(ganancia_bruta / ventas * 100, 1) if ventas > 0 else 0.0,
    }


def _dia_local(fecha_utc) -> date | None:
    local = utc_naive_to_local(fecha_utc)
    return local.date() if local else None


def _rango(fecha_desde: str | None, fecha_hasta: str | None) -> tuple[date, date]:
    desde = parse_iso_date(fecha_desde) or today_local()
    hasta = parse_iso_date(fecha_hasta) or desde
    if hasta < desde:
        hasta = desde
    if (hasta - desde).days >= MAX_DIAS:
        desde = hasta - timedelta(days=MAX_DIAS - 1)
    return desde, hasta
