"""Carga rapida del menu a partir de plantillas por rubro."""
from __future__ import annotations

from datetime import datetime, timedelta

from app import db
from app.utils.helpers import get_app_timezone
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.menu_plantillas_data import PLANTILLAS
from gastronomia.services.menu_service import guardar_categoria, guardar_producto, parse_price
from gastronomia.services.modificadores_service import (
    sincronizar_adicionales_precio,
    sincronizar_ingredientes_removibles,
)


MAX_PRODUCTOS_POR_CARGA = 200
DIAS_PROMO_SUGERIDA = 30


def listar_plantillas() -> list[dict]:
    return [
        {
            'clave': clave,
            'nombre': plantilla['nombre'],
            'icono': plantilla['icono'],
            'promo': plantilla.get('promo'),
            'categorias': [
                {
                    'nombre': categoria['nombre'],
                    'productos': [
                        {
                            'nombre': producto['nombre'],
                            'removibles': producto.get('removibles', ''),
                            'adicionales': producto.get('adicionales', ''),
                        }
                        for producto in categoria['productos']
                    ],
                }
                for categoria in plantilla['categorias']
            ],
        }
        for clave, plantilla in PLANTILLAS.items()
    ]


def aplicar_plantilla(cliente_id: int, productos: list) -> dict:
    """Crea categorias y productos elegidos. Los que ya existen se omiten."""
    items = _validar_items(productos)
    categorias = _por_nombre(GastronomiaCategoria.query.filter_by(cliente_id=int(cliente_id)).all())
    existentes = _por_nombre(GastronomiaProducto.query.filter_by(cliente_id=int(cliente_id)).all())
    siguiente_orden = _siguiente_orden_categoria(categorias.values())
    resultado = {'creados': [], 'omitidos': [], 'categorias_creadas': []}

    for item in items:
        categoria = categorias.get(_clave(item['categoria']))
        if categoria is None or not categoria.activo:
            categoria = _activar_o_crear_categoria(cliente_id, item['categoria'], categoria, siguiente_orden)
            categorias[_clave(categoria.nombre)] = categoria
            resultado['categorias_creadas'].append(categoria.nombre)
            siguiente_orden += 10

        producto = existentes.get(_clave(item['nombre']))
        if producto is not None and producto.activo:
            resultado['omitidos'].append(item['nombre'])
            continue
        if producto is not None:
            producto.activo = True
        producto = guardar_producto(cliente_id, {
            'categoria_id': categoria.id_categoria,
            'nombre': item['nombre'],
            'precio': item['precio'],
        }, producto=producto)
        existentes[_clave(producto.nombre)] = producto
        sincronizar_ingredientes_removibles(cliente_id, producto.id_producto, item['removibles'])
        sincronizar_adicionales_precio(cliente_id, producto.id_producto, item['adicionales'])
        resultado['creados'].append(producto.nombre)
    return resultado


def crear_promo_sugerida(cliente_id: int, plantilla_clave: str, nombre_producto: str) -> str | None:
    """Crea la promo de la plantilla pausada; devuelve su nombre o None si no aplica."""
    from app.models.tienda_promocion import TiendaPromocion
    from app.services.tienda_promociones import save_promotion

    promo = (PLANTILLAS.get(plantilla_clave) or {}).get('promo')
    if not promo:
        return None
    producto = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.activo.is_(True),
        db.func.lower(GastronomiaProducto.nombre) == _clave(nombre_producto),
    ).first()
    if producto is None:
        return None
    nombre = f"{promo['lleva']}x{promo['paga']} en {producto.nombre}"[:160]
    if TiendaPromocion.query.filter_by(id_cliente=int(cliente_id), nombre=nombre).first():
        return None
    inicio = datetime.now(get_app_timezone()).replace(tzinfo=None, microsecond=0)
    promocion, error = save_promotion(promotion=None, client_id=int(cliente_id), data={
        'nombre': nombre,
        'tipo': 'cantidad',
        'cantidad_lleva': promo['lleva'],
        'cantidad_paga': promo['paga'],
        'fecha_inicio': inicio.isoformat(),
        'fecha_fin': (inicio + timedelta(days=DIAS_PROMO_SUGERIDA)).isoformat(),
        'activa': False,
        'productos_gastronomia': [producto.id_producto],
    })
    if error:
        db.session.rollback()
        return None
    db.session.commit()
    return promocion.nombre


def _validar_items(productos) -> list[dict]:
    if not isinstance(productos, list) or not productos:
        raise ValueError('Elegi al menos un producto para cargar.')
    if len(productos) > MAX_PRODUCTOS_POR_CARGA:
        raise ValueError(f'Se pueden cargar hasta {MAX_PRODUCTOS_POR_CARGA} productos por vez.')
    items = []
    for producto in productos:
        if not isinstance(producto, dict):
            raise ValueError('Los productos recibidos no son validos.')
        nombre = str(producto.get('nombre') or '').strip()[:160]
        categoria = str(producto.get('categoria') or '').strip()[:120]
        if not nombre or not categoria:
            raise ValueError('Cada producto necesita nombre y categoria.')
        try:
            precio = parse_price(producto.get('precio'))
        except ValueError as exc:
            raise ValueError(f'Revisa el precio de "{nombre}".') from exc
        if precio <= 0:
            raise ValueError(f'Falta el precio de "{nombre}".')
        items.append({
            'nombre': nombre,
            'categoria': categoria,
            'precio': precio,
            'removibles': str(producto.get('removibles') or ''),
            'adicionales': str(producto.get('adicionales') or ''),
        })
    return items


def _activar_o_crear_categoria(cliente_id: int, nombre: str, categoria, orden: int) -> GastronomiaCategoria:
    if categoria is not None:
        # Existia borrada: el nombre es unico por cliente, se reactiva.
        categoria.activo = True
        categoria.visible = True
        db.session.commit()
        return categoria
    return guardar_categoria(cliente_id, {'nombre': nombre, 'orden': orden, 'visible': True})


def _siguiente_orden_categoria(categorias) -> int:
    ordenes = [int(categoria.orden or 0) for categoria in categorias if categoria.activo]
    return (max(ordenes) if ordenes else 0) + 10


def _por_nombre(registros) -> dict:
    return {_clave(registro.nombre): registro for registro in registros}


def _clave(nombre: str | None) -> str:
    return (nombre or '').strip().lower()
