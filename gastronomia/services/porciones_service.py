"""Torta entera -> porciones: relacion entre productos y accion "abrir torta".

Abrir resta 1 al stock del entero y suma N al de la porcion, de forma atomica.
No toca el camino de venta. Diseno en docs/pasteleria_fase3_diseno.md.
"""
from __future__ import annotations

from uuid import uuid4

from app import db
from gastronomia.produccion_models import TIPO_APERTURA, TIPO_PORCIONES, GastronomiaProductoPorcion
from gastronomia.services.inteligencia_margen import costos_unitarios_receta
from gastronomia.services.produccion_service import (
    exigir_produccion_habilitada,
    mover_stock_producto,
    obtener_producto_con_stock,
)
from gastronomia.services.stock_service import _bloquear_producto_menu


PORCIONES_MAX = 100


def relaciones_por_entero(cliente_id: int) -> dict[int, GastronomiaProductoPorcion]:
    return {
        int(rel.producto_entero_id): rel
        for rel in GastronomiaProductoPorcion.query.filter_by(cliente_id=int(cliente_id), activo=True).all()
    }


def guardar_relacion(cliente_id: int, producto_entero_id: int, data: dict) -> GastronomiaProductoPorcion:
    exigir_produccion_habilitada(cliente_id)
    entero = obtener_producto_con_stock(cliente_id, producto_entero_id)
    porcion = obtener_producto_con_stock(cliente_id, data.get('producto_porcion_id'))
    if entero.id_producto == porcion.id_producto:
        raise ValueError('El producto porcion tiene que ser distinto del entero.')
    porciones = _porciones(data.get('porciones'))

    activas = GastronomiaProductoPorcion.query.filter_by(cliente_id=int(cliente_id), activo=True)
    if activas.filter_by(producto_porcion_id=entero.id_producto).first():
        raise ValueError(f'"{entero.nombre}" ya es porcion de otro producto: no puede abrirse en porciones.')
    if activas.filter_by(producto_entero_id=porcion.id_producto).first():
        raise ValueError(f'"{porcion.nombre}" ya se abre en porciones: no puede ser porcion de otro.')

    relacion = GastronomiaProductoPorcion.query.filter_by(
        cliente_id=int(cliente_id), producto_entero_id=int(entero.id_producto),
    ).first()
    if not relacion:
        relacion = GastronomiaProductoPorcion(cliente_id=int(cliente_id), producto_entero_id=int(entero.id_producto))
        db.session.add(relacion)
    relacion.producto_porcion_id = int(porcion.id_producto)
    relacion.porciones = porciones
    relacion.activo = True
    db.session.commit()
    return relacion


def eliminar_relacion(cliente_id: int, producto_entero_id: int) -> bool:
    exigir_produccion_habilitada(cliente_id)
    relacion = GastronomiaProductoPorcion.query.filter_by(
        cliente_id=int(cliente_id), producto_entero_id=int(producto_entero_id), activo=True,
    ).first()
    if not relacion:
        return False
    # Se desactiva (no se borra): los registros de aperturas viejas siguen explicando el stock.
    relacion.activo = False
    db.session.commit()
    return True


def abrir_entero(cliente_id: int, usuario_id: int | None, producto_entero_id: int) -> dict:
    """Abre un entero: entero -1, porcion +N. Rechaza si el entero no tiene stock."""
    exigir_produccion_habilitada(cliente_id)
    entero = obtener_producto_con_stock(cliente_id, producto_entero_id)
    relacion = GastronomiaProductoPorcion.query.filter_by(
        cliente_id=int(cliente_id), producto_entero_id=int(entero.id_producto), activo=True,
    ).first()
    if not relacion:
        raise ValueError(f'"{entero.nombre}" no tiene porciones configuradas.')
    porcion = obtener_producto_con_stock(cliente_id, relacion.producto_porcion_id)

    # Bloqueo en orden de id para que dos aperturas cruzadas no se traben.
    # populate_existing refresca las mismas instancias del identity map.
    for producto in sorted((entero, porcion), key=lambda p: int(p.id_producto)):
        _bloquear_producto_menu(producto)
    if int(entero.stock_disponible or 0) < 1:
        db.session.rollback()
        raise ValueError(f'No hay "{entero.nombre}" en stock para abrir.')

    referencia = f'apertura-{uuid4().hex[:12]}'
    costos = costos_unitarios_receta(cliente_id, [int(entero.id_producto), int(porcion.id_producto)])
    salida = mover_stock_producto(
        entero, -1, TIPO_APERTURA, usuario_id=usuario_id, referencia=referencia,
        costo_unitario=costos.get(int(entero.id_producto)) or None,
    )
    entrada = mover_stock_producto(
        porcion, int(relacion.porciones), TIPO_PORCIONES, usuario_id=usuario_id, referencia=referencia,
        costo_unitario=costos.get(int(porcion.id_producto)) or None,
    )
    db.session.commit()
    return {
        'referencia': referencia,
        'entero': {'producto_id': int(entero.id_producto), 'stock': int(salida.stock_nuevo)},
        'porcion': {'producto_id': int(porcion.id_producto), 'stock': int(entrada.stock_nuevo)},
        'porciones': int(relacion.porciones),
    }


def _porciones(valor) -> int:
    try:
        porciones = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError('Cantidad de porciones invalida.')
    if porciones < 1 or porciones > PORCIONES_MAX:
        raise ValueError(f'Las porciones tienen que estar entre 1 y {PORCIONES_MAX}.')
    return porciones
