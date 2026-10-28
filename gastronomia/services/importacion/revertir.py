"""Deshace una importacion completa y lista las importaciones hechas."""
from __future__ import annotations

from datetime import datetime

from app import db
from app.models.caja import MovimientoCaja, SesionCaja
from app.models.venta import Ticket, Venta
from gastronomia.importacion_models import GastronomiaImportacion
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago


def listar_importaciones(cliente_id: int) -> list[dict]:
    return [
        item.to_dict()
        for item in GastronomiaImportacion.query
        .filter_by(cliente_id=int(cliente_id))
        .order_by(GastronomiaImportacion.id_importacion.desc())
        .limit(50)
        .all()
    ]


def revertir_importacion(cliente_id: int, importacion_id: int) -> dict:
    importacion = GastronomiaImportacion.query.filter_by(
        cliente_id=int(cliente_id), id_importacion=int(importacion_id),
    ).first()
    if not importacion:
        raise ValueError('Importacion no encontrada.')
    if importacion.estado != 'aplicada':
        raise ValueError('Esta importacion ya fue deshecha.')

    try:
        borrados = 0
        # Sin autoflush cada consulta no vuelca la sesion: con cientos de ventas es varias veces mas rapido.
        with db.session.no_autoflush:
            for registro in importacion.registros.all():
                pedido = GastronomiaPedido.query.filter_by(
                    id_pedido=int(registro.pedido_id), cliente_id=int(cliente_id), origen_pedido='importado',
                ).first()
                # El pago apunta a la venta y al movimiento de caja: se borra primero.
                if pedido:
                    GastronomiaPedidoPago.query.filter_by(pedido_id=pedido.id_pedido).delete(synchronize_session=False)
                _borrar_venta(registro.venta_id)
                if pedido:
                    db.session.delete(pedido)
                    borrados += 1
                db.session.delete(registro)
        db.session.flush()
        for sesion_id in importacion.sesiones_ids:
            _borrar_sesion_si_vacia(sesion_id)
        importacion.estado = 'revertida'
        importacion.fecha_reversion = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {**importacion.to_dict(), 'pedidos_borrados': borrados}


def _borrar_venta(venta_id: int | None) -> None:
    if not venta_id:
        return
    venta = db.session.get(Venta, int(venta_id))
    if not venta:
        return
    Ticket.query.filter_by(id_venta=venta.id_venta).delete(synchronize_session=False)
    MovimientoCaja.query.filter_by(referencia_tipo='venta', referencia_id=venta.id_venta).delete(synchronize_session=False)
    db.session.delete(venta)


def _borrar_sesion_si_vacia(sesion_id: int) -> None:
    sesion = db.session.get(SesionCaja, int(sesion_id))
    if not sesion:
        return
    if sesion.ventas.count() or sesion.movimientos.count():
        return
    db.session.delete(sesion)
