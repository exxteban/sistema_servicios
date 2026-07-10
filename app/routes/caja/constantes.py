"""
Constantes para tipos de referencia de movimientos de caja.

Usar estas constantes en lugar de strings literales para evitar typos
y facilitar búsquedas en el código.
"""

# ── Tipos de referencia (referencia_tipo en MovimientoCaja) ──────────────────

REF_VENTA = 'venta'
"""Ingreso por cobro en efectivo de una venta."""

REF_VUELTO = 'vuelto'
"""Egreso por vuelto entregado al cliente en una venta."""

REF_ANULACION_VENTA = 'anulacion_venta'
"""Egreso por devolución de efectivo al anular una venta."""

REF_COBRO_CREDITO = 'cobro_credito'
"""Ingreso por cobro de una cuenta por cobrar (crédito)."""

REF_ANULACION_COBRO_CREDITO = 'anulacion_cobro_credito'
"""Egreso por reversa de un cobro de crédito."""

REF_PAGO_PEDIDO = 'pago_pedido'
"""Ingreso por cobro de un pedido de cliente."""

REF_COMPRA = 'compra'
"""Egreso por pago de una compra a proveedor."""

REF_RECEPCION_COMPRA_USADO = 'recepcion_compra_usado'
"""Egreso por compra de artículo usado al público."""

REF_DEVOLUCION = 'devolucion'
"""Egreso por devolución/reembolso al cliente."""

REF_GASTO_CORRIENTE = 'gasto_corriente'
"""Egreso por gasto operativo registrado manualmente."""

REF_GASTO_CORRIENTE_REVERSA = 'gasto_corriente_reversa'
"""Ingreso por reversa de un gasto corriente."""

REF_AJUSTE_MANUAL = 'ajuste_manual'
"""Movimiento de ajuste manual de caja (ingreso o egreso)."""

REF_ABONO_REPARACION = 'reparacion_abono'
"""Ingreso (o egreso por ajuste) por la seña/abono cobrado al recibir una reparación."""
