"""
Sanity checks para el informe de cierre de caja.

Centraliza las alertas cruzadas que detectan descuadres silenciosos
(metodo efectivo mal configurado, pagos sin movimiento espejo, etc.).

No altera numeros ni bloquea el cierre: solo produce una lista de alertas
que la UI y los logs pueden mostrar.
"""
from __future__ import annotations

from app.services.caja_metodos import diagnostico_metodo_efectivo


# Tolerancia en guaranies para absorber redondeos inocuos.
TOLERANCIA_GS = 1.0


def calcular_alertas_cuadre_sesion(
    *,
    sesion,
    efectivo_id,
    pagos_ventas_agg,
    movimientos,
    anulaciones_efectivo_esperado,
    anulaciones_efectivo_mov,
):
    """Chequeos cruzados de integridad para una sesion de caja.

    Cada alerta tiene:
      { 'nivel': 'warning'|'error', 'codigo': str, 'mensaje': str, 'detalle': dict }
    """
    alertas = []

    # 1) Diagnostico del metodo efectivo: config mal hecha, multiples candidatos, etc.
    diag = diagnostico_metodo_efectivo()
    for advertencia in diag.get('advertencias', []):
        alertas.append({
            'nivel': 'error' if diag.get('origen') == 'no_resuelto' else 'warning',
            'codigo': 'metodo_efectivo_config',
            'mensaje': advertencia,
            'detalle': {
                'origen': diag.get('origen'),
                'id_resuelto': diag.get('metodo_resuelto_id'),
                'nombre_resuelto': diag.get('metodo_resuelto_nombre'),
            },
        })

    if efectivo_id is None:
        alertas.append({
            'nivel': 'error',
            'codigo': 'efectivo_no_resuelto',
            'mensaje': (
                'No se pudo identificar el metodo "Efectivo". '
                'El cuadre de caja puede ser inexacto. Configure la clave '
                '`metodo_pago_efectivo_id` en Configuracion.'
            ),
            'detalle': {},
        })
        return alertas

    # 2) Efectivo de ventas por dos vias:
    #    - suma de PagoVenta con metodo=efectivo
    #    - suma de MovimientoCaja ingreso ref=venta
    # En operacion sana deben ser iguales (POS crea MovimientoCaja espejo).
    ventas_efectivo_por_pagos = _to_float(_row_total(pagos_ventas_agg.get(int(efectivo_id))))
    ventas_efectivo_por_mov = _sumar_movimientos_ingreso_venta(movimientos)

    diff_ventas = ventas_efectivo_por_pagos - ventas_efectivo_por_mov
    if abs(diff_ventas) > TOLERANCIA_GS:
        alertas.append({
            'nivel': 'error',
            'codigo': 'ventas_efectivo_desbalance',
            'mensaje': (
                'Desbalance entre pagos en efectivo de ventas y movimientos '
                f'de caja espejo: Gs. {diff_ventas:,.0f}. Esto indica que '
                'algun MovimientoCaja no se genero o fue borrado manualmente.'
            ),
            'detalle': {
                'ventas_efectivo_por_pagos': ventas_efectivo_por_pagos,
                'ventas_efectivo_por_mov': ventas_efectivo_por_mov,
                'diferencia': diff_ventas,
            },
        })

    # 3) Anulaciones en efectivo: si el sistema tuvo que "absorber" el
    # faltante en `calcular_total_efectivo`, lo reportamos como warning.
    faltante_anulaciones = (
        float(anulaciones_efectivo_esperado or 0.0)
        - float(anulaciones_efectivo_mov or 0.0)
    )
    if faltante_anulaciones > TOLERANCIA_GS:
        alertas.append({
            'nivel': 'warning',
            'codigo': 'anulaciones_efectivo_faltante',
            'mensaje': (
                f'Faltan Gs. {faltante_anulaciones:,.0f} en movimientos de '
                'reversa de anulaciones en efectivo. El cuadre los aplica '
                'igual como descuento, pero revise que las anulaciones '
                'hayan generado el egreso correspondiente.'
            ),
            'detalle': {
                'esperado': float(anulaciones_efectivo_esperado or 0.0),
                'registrado_en_movimientos': float(anulaciones_efectivo_mov or 0.0),
                'faltante': faltante_anulaciones,
            },
        })

    return alertas


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _row_total(agg_row):
    if agg_row is None:
        return 0
    return getattr(agg_row, 'total', 0) or 0


def _sumar_movimientos_ingreso_venta(movimientos) -> float:
    """Suma ingresos de caja con referencia_tipo='venta' (cobros en efectivo).

    Excluye explícitamente los vueltos aunque tengan referencia_tipo='venta'
    en registros históricos (tipo='egreso'), ya que solo sumamos ingresos.
    Los vueltos nuevos usan referencia_tipo='vuelto' y tampoco se incluyen.
    """
    total = 0.0
    for mov in movimientos:
        if (getattr(mov, 'tipo', '') or '').strip().lower() != 'ingreso':
            continue
        if (getattr(mov, 'referencia_tipo', '') or '').strip().lower() != 'venta':
            continue
        total += _to_float(getattr(mov, 'monto', 0))
    return total
