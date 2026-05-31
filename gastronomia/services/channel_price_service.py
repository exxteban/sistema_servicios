"""Gestion de precios independientes para plataformas externas."""
from __future__ import annotations

from decimal import Decimal

from app import db
from gastronomia.channel_models import GastronomiaProductoPrecioCanal


CANALES_PRECIOS = {
    'pedidosya': 'PedidosYa',
    'monchis': 'Monchis',
}


def normalizar_canal_precio(canal: str | None, *, permitir_vacio: bool = True) -> str | None:
    value = (canal or '').strip().lower()
    if not value and permitir_vacio:
        return None
    if value not in CANALES_PRECIOS:
        raise ValueError('Canal de precio invalido.')
    return value


def validar_canal_items_pedido(items: list[dict]) -> str | None:
    canales = {
        normalizar_canal_precio(item.get('canal_precio'))
        for item in items
        if isinstance(item, dict)
    }
    if len(canales) > 1:
        raise ValueError('Un pedido no puede mezclar precios normales, de PedidosYa y de Monchis.')
    return next(iter(canales), None)


def asegurar_precios_producto(producto, *, commit: bool = True) -> list[GastronomiaProductoPrecioCanal]:
    existentes = {
        item.canal: item
        for item in GastronomiaProductoPrecioCanal.query.filter_by(
            cliente_id=int(producto.cliente_id),
            producto_id=int(producto.id_producto),
        ).all()
    }
    for canal in CANALES_PRECIOS:
        if canal in existentes:
            continue
        item = GastronomiaProductoPrecioCanal(
            cliente_id=int(producto.cliente_id),
            producto_id=int(producto.id_producto),
            canal=canal,
            precio=Decimal(str(producto.precio or 0)),
        )
        db.session.add(item)
        existentes[canal] = item
    if commit:
        db.session.commit()
    return [existentes[canal] for canal in CANALES_PRECIOS]


def asegurar_precios_productos(productos) -> None:
    for producto in productos:
        asegurar_precios_producto(producto, commit=False)
    db.session.commit()


def obtener_precio_canal(producto, canal: str | None) -> Decimal:
    canal_normalizado = normalizar_canal_precio(canal)
    if not canal_normalizado:
        return Decimal(str(producto.precio or 0))
    precio = GastronomiaProductoPrecioCanal.query.filter_by(
        cliente_id=int(producto.cliente_id),
        producto_id=int(producto.id_producto),
        canal=canal_normalizado,
    ).first()
    return Decimal(str(precio.precio if precio else producto.precio or 0))


def listar_precios_canal(cliente_id: int, canal: str, productos) -> list[dict]:
    canal_normalizado = normalizar_canal_precio(canal, permitir_vacio=False)
    asegurar_precios_productos(productos)
    precios = {
        int(item.producto_id): item
        for item in GastronomiaProductoPrecioCanal.query.filter_by(
            cliente_id=int(cliente_id),
            canal=canal_normalizado,
        ).all()
    }
    return [
        {
            'producto': producto,
            'precio_canal': precios[int(producto.id_producto)],
        }
        for producto in productos
    ]


def guardar_precio_canal(cliente_id: int, producto, canal: str, precio) -> GastronomiaProductoPrecioCanal:
    from gastronomia.services.menu_service import parse_price

    canal_normalizado = normalizar_canal_precio(canal, permitir_vacio=False)
    item = GastronomiaProductoPrecioCanal.query.filter_by(
        cliente_id=int(cliente_id),
        producto_id=int(producto.id_producto),
        canal=canal_normalizado,
    ).first()
    if not item:
        item = GastronomiaProductoPrecioCanal(
            cliente_id=int(cliente_id),
            producto_id=int(producto.id_producto),
            canal=canal_normalizado,
        )
    item.precio = parse_price(precio)
    db.session.add(item)
    db.session.commit()
    return item


def aplicar_precio_canal(producto, data: dict, canal: str | None) -> dict:
    canal_normalizado = normalizar_canal_precio(canal)
    if not canal_normalizado:
        return data
    precio = float(obtener_precio_canal(producto, canal_normalizado))
    data.update({
        'canal_precio': canal_normalizado,
        'precio': precio,
        'precio_base': precio,
        'precio_anterior': None,
        'ahorro': None,
        'descuento_porcentaje': None,
        'es_oferta': False,
        'promocion_activa': None,
    })
    return data
