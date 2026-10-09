"""Contra-asiento de caja al anular una venta."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.models import MovimientoCaja, PagoVenta


def revertir_caja_de_venta(venta, id_usuario):
    """Revierte en la sesion de la venta cada movimiento de caja que genero."""
    # El vuelto ('vuelto'; historico: 'venta' + motivo "Vuelto") vuelve como
    # ingreso: si solo se revierte el cobro bruto, el arqueo queda con un
    # faltante igual al vuelto.
    movimientos_caja_venta = (
        MovimientoCaja.query.filter(
            MovimientoCaja.id_sesion_caja == venta.id_sesion_caja,
            MovimientoCaja.referencia_tipo.in_(('venta', 'vuelto')),
            MovimientoCaja.referencia_id == venta.id_venta,
        )
        .order_by(MovimientoCaja.id_movimiento_caja.asc())
        .all()
    )
    if movimientos_caja_venta:
        for mov in movimientos_caja_venta:
            tipo_original = (mov.tipo or '').strip().lower()
            if tipo_original not in {'ingreso', 'egreso'}:
                continue
            tipo_reverso = 'egreso' if tipo_original == 'ingreso' else 'ingreso'
            motivo_base = (mov.motivo or '').strip()
            motivo_reverso = f'Anulación venta #{venta.id_venta}: {motivo_base}'.strip()
            if len(motivo_reverso) > 200:
                motivo_reverso = motivo_reverso[:200]
            db.session.add(
                MovimientoCaja(
                    id_sesion_caja=mov.id_sesion_caja,
                    id_usuario=id_usuario,
                    tipo=tipo_reverso,
                    monto=mov.monto,
                    motivo=motivo_reverso or f'Anulación venta #{venta.id_venta}',
                    referencia_tipo='anulacion_venta',
                    referencia_id=venta.id_venta,
                    fecha_movimiento=datetime.utcnow(),
                )
            )
    else:
        from app.services.caja_metodos import obtener_metodo_efectivo_id

        efectivo_id = obtener_metodo_efectivo_id(solo_activos=False)
        if efectivo_id is not None:
            total_efectivo_pagado = (
                db.session.query(func.sum(PagoVenta.monto))
                .filter(PagoVenta.id_venta == venta.id_venta, PagoVenta.id_metodo_pago == efectivo_id)
                .scalar()
            )
            if total_efectivo_pagado and Decimal(str(total_efectivo_pagado)) > 0:
                motivo_reverso = f'Anulación venta #{venta.id_venta}: ajuste efectivo'.strip()
                if len(motivo_reverso) > 200:
                    motivo_reverso = motivo_reverso[:200]
                db.session.add(
                    MovimientoCaja(
                        id_sesion_caja=venta.id_sesion_caja,
                        id_usuario=id_usuario,
                        tipo='egreso',
                        monto=total_efectivo_pagado,
                        motivo=motivo_reverso,
                        referencia_tipo='anulacion_venta',
                        referencia_id=venta.id_venta,
                        fecha_movimiento=datetime.utcnow(),
                    )
                )
