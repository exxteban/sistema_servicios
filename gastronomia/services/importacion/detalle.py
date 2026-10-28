"""Detalle venta por venta de una importacion: que decia el Excel y como quedo cargado."""
from __future__ import annotations

import re

from app import db
from app.utils.helpers import utc_naive_to_local
from gastronomia.importacion_models import GastronomiaImportacion, GastronomiaImportacionRegistro
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem

# Ver nota_origen en aplicar.py: 'Importado de Excel - hoja "X", fila N: texto'.
ORIGEN = re.compile(r'hoja "(?P<hoja>.*)", fila (?P<fila>\d+): (?P<texto>.*)$', re.DOTALL)


def detalle_importacion(cliente_id: int, importacion_id: int) -> dict:
    importacion = GastronomiaImportacion.query.filter_by(
        cliente_id=int(cliente_id), id_importacion=int(importacion_id),
    ).first()
    if not importacion:
        raise ValueError('Importacion no encontrada.')

    filas = (
        db.session.query(GastronomiaImportacionRegistro, GastronomiaPedido, GastronomiaPedidoItem)
        .join(GastronomiaPedido, GastronomiaPedido.id_pedido == GastronomiaImportacionRegistro.pedido_id)
        .join(GastronomiaPedidoItem, GastronomiaPedidoItem.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaImportacionRegistro.importacion_id == importacion.id_importacion,
            GastronomiaPedido.cliente_id == int(cliente_id),
        )
        .order_by(GastronomiaPedido.fecha_creacion.asc(), GastronomiaPedido.id_pedido.asc())
        .all()
    )
    return {
        'importacion': importacion.to_dict(),
        'ventas': [_venta(registro, pedido, item) for registro, pedido, item in filas],
    }


def _venta(registro, pedido, item) -> dict:
    origen = ORIGEN.search(pedido.notas or '')
    fecha = utc_naive_to_local(pedido.fecha_creacion)
    return {
        'id_pedido': int(pedido.id_pedido),
        'id_venta': int(registro.venta_id) if registro.venta_id else None,
        'fecha': fecha.date().isoformat() if fecha else None,
        'hoja': origen.group('hoja') if origen else '',
        'fila': int(origen.group('fila')) if origen else None,
        'texto_excel': origen.group('texto').strip() if origen else (pedido.notas or ''),
        'producto': item.nombre_producto,
        'cantidad': int(item.cantidad or 1),
        'monto': float(item.subtotal or 0),
        'nota': item.notas or '',
    }
