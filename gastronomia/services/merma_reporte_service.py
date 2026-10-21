"""Reporte de merma de producto terminado, valorizada al costo de receta congelado.

Solo producto terminado: la merma de insumos sigue en los ajustes de stock de
insumos y no se mezcla aca (plan_pasteleria.md, Fase 3).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app import db
from gastronomia.models import GastronomiaProducto
from gastronomia.produccion_models import MOTIVOS_MERMA, TIPO_MERMA, GastronomiaProduccionRegistro


RANGO_MAX_DIAS = 366


def reporte_merma(cliente_id: int, desde: date, hasta: date) -> dict:
    if hasta < desde:
        raise ValueError('La fecha final no puede ser anterior a la inicial.')
    if (hasta - desde) > timedelta(days=RANGO_MAX_DIAS):
        raise ValueError(f'El rango no puede superar {RANGO_MAX_DIAS} dias.')
    filas = (
        db.session.query(
            GastronomiaProduccionRegistro.producto_id,
            GastronomiaProducto.nombre,
            GastronomiaProduccionRegistro.motivo,
            func.coalesce(func.sum(GastronomiaProduccionRegistro.cantidad), 0),
            func.coalesce(func.sum(
                GastronomiaProduccionRegistro.cantidad * func.coalesce(GastronomiaProduccionRegistro.costo_unitario, 0)
            ), 0),
            func.min(func.coalesce(GastronomiaProduccionRegistro.costo_unitario, -1)),
        )
        .join(GastronomiaProducto, GastronomiaProducto.id_producto == GastronomiaProduccionRegistro.producto_id)
        .filter(
            GastronomiaProduccionRegistro.cliente_id == int(cliente_id),
            GastronomiaProduccionRegistro.tipo == TIPO_MERMA,
            GastronomiaProduccionRegistro.fecha >= desde,
            GastronomiaProduccionRegistro.fecha <= hasta,
        )
        .group_by(GastronomiaProduccionRegistro.producto_id, GastronomiaProducto.nombre, GastronomiaProduccionRegistro.motivo)
        .all()
    )
    productos: dict[int, dict] = {}
    for producto_id, nombre, motivo, cantidad, costo, marca_costo in filas:
        fila = productos.setdefault(int(producto_id), {
            'producto_id': int(producto_id),
            'nombre': nombre,
            'cantidad': 0,
            'costo': 0.0,
            'sin_costo': False,
            'motivos': [],
        })
        fila['cantidad'] += int(cantidad or 0)
        fila['costo'] += float(costo or 0)
        # Algun registro sin costo congelado (producto sin receta) deja la marca en -1.
        fila['sin_costo'] = fila['sin_costo'] or float(marca_costo or 0) < 0
        fila['motivos'].append({
            'motivo': motivo,
            'motivo_label': MOTIVOS_MERMA.get(motivo or '', motivo or 'Sin motivo'),
            'cantidad': int(cantidad or 0),
            'costo': round(float(costo or 0), 2),
        })
    lista = sorted(productos.values(), key=lambda fila: (-fila['costo'], -fila['cantidad'], fila['nombre']))
    for fila in lista:
        fila['costo'] = round(fila['costo'], 2)
        fila['motivos'].sort(key=lambda m: -m['cantidad'])
    return {
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'productos': lista,
        'total_unidades': sum(fila['cantidad'] for fila in lista),
        'total_costo': round(sum(fila['costo'] for fila in lista), 2),
    }
