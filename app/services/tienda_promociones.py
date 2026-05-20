"""
Servicios de promociones de tienda.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import selectinload

from app import db
from app.models.producto import Producto
from app.models.tienda import TiendaConfig
from app.models.tienda_promocion import (
    PROMOTION_TYPES,
    TiendaPromocion,
    TiendaPromocionProducto,
)


TWOPLACES = Decimal('0.01')


def promotion_label(tipo: str) -> str:
    labels = {
        'porcentaje': 'Descuento %',
        'monto_fijo': 'Monto fijo',
        'precio_promocional': 'Precio promo',
    }
    return labels.get((tipo or '').strip(), 'Promoción')


def round_decimal(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def active_promotions_query(client_id: int, now: datetime | None = None):
    now = now or datetime.utcnow()
    return (
        TiendaPromocion.query
        .filter(
            TiendaPromocion.id_cliente == client_id,
            TiendaPromocion.activa.is_(True),
            TiendaPromocion.fecha_inicio <= now,
            TiendaPromocion.fecha_fin >= now,
        )
        .options(
            selectinload(TiendaPromocion.productos_rel).selectinload(TiendaPromocionProducto.producto)
        )
        .order_by(TiendaPromocion.fecha_fin.asc(), TiendaPromocion.nombre.asc())
    )


def list_admin_promotions(client_id: int):
    return (
        TiendaPromocion.query
        .filter(TiendaPromocion.id_cliente == client_id)
        .options(
            selectinload(TiendaPromocion.productos_rel).selectinload(TiendaPromocionProducto.producto)
        )
        .order_by(TiendaPromocion.fecha_inicio.desc(), TiendaPromocion.fecha_creacion.desc())
        .all()
    )


def admin_status(promotion: TiendaPromocion, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    if not promotion.activa:
        return 'inactiva'
    if promotion.fecha_fin < now:
        return 'finalizada'
    if promotion.fecha_inicio > now:
        return 'programada'
    return 'activa'


def calculate_promotion_price(producto: Producto, promotion: TiendaPromocion) -> dict:
    base_price = round_decimal(producto.precio_venta or 0)
    promo_value = round_decimal(promotion.valor or 0)
    final_price = base_price

    if promotion.tipo == 'porcentaje':
        final_price = base_price - ((base_price * promo_value) / Decimal('100'))
    elif promotion.tipo == 'monto_fijo':
        final_price = base_price - promo_value
    elif promotion.tipo == 'precio_promocional':
        final_price = promo_value

    if final_price < Decimal('0'):
        final_price = Decimal('0')

    final_price = final_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    ahorro = (base_price - final_price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if ahorro <= Decimal('0'):
        return {
            'precio': float(base_price),
            'precio_anterior': None,
            'ahorro': None,
            'descuento_porcentaje': None,
        }

    descuento_porcentaje = None
    if base_price > 0:
        descuento_porcentaje = int(
            ((ahorro / base_price) * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        )

    return {
        'precio': float(final_price),
        'precio_anterior': float(base_price),
        'ahorro': float(ahorro),
        'descuento_porcentaje': descuento_porcentaje,
    }


def serialize_public_promotion(
    promotion: TiendaPromocion,
    *,
    include_products: bool = True,
    product_limit: int = 6,
) -> dict:
    products = []
    if include_products:
        for rel in promotion.productos_rel[:product_limit]:
            if rel.producto:
                products.append({
                    'id': rel.producto.id_producto,
                    'nombre': rel.producto.nombre,
                })

    return {
        'id': promotion.id_promocion,
        'nombre': promotion.nombre,
        'descripcion': promotion.descripcion_corta or '',
        'tipo': promotion.tipo,
        'tipo_label': promotion_label(promotion.tipo),
        'valor': float(round_decimal(promotion.valor or 0)),
        'fecha_inicio': promotion.fecha_inicio.isoformat(),
        'fecha_fin': promotion.fecha_fin.isoformat(),
        'productos': products,
    }


def serialize_admin_promotion(promotion: TiendaPromocion, now: datetime | None = None) -> dict:
    return {
        'id_promocion': promotion.id_promocion,
        'nombre': promotion.nombre,
        'descripcion_corta': promotion.descripcion_corta or '',
        'tipo': promotion.tipo,
        'tipo_label': promotion_label(promotion.tipo),
        'valor': float(round_decimal(promotion.valor or 0)),
        'fecha_inicio': promotion.fecha_inicio.isoformat(),
        'fecha_fin': promotion.fecha_fin.isoformat(),
        'activa': bool(promotion.activa),
        'estado': admin_status(promotion, now=now),
        'productos': [
            {
                'id_producto': rel.id_producto,
                'nombre': rel.producto.nombre if rel.producto else f'Producto {rel.id_producto}',
                'codigo': rel.producto.codigo if rel.producto else '',
            }
            for rel in promotion.productos_rel
        ],
    }


def get_active_product_promotion_map(
    client_id: int,
    product_ids: list[int] | set[int],
    now: datetime | None = None,
) -> dict[int, TiendaPromocion]:
    ids = [int(pid) for pid in product_ids if pid]
    if not ids:
        return {}

    rows = (
        active_promotions_query(client_id, now=now)
        .join(TiendaPromocionProducto, TiendaPromocionProducto.id_promocion == TiendaPromocion.id_promocion)
        .filter(TiendaPromocionProducto.id_producto.in_(ids))
        .with_entities(TiendaPromocion, TiendaPromocionProducto.id_producto)
        .all()
    )

    mapping: dict[int, TiendaPromocion] = {}
    for promotion, product_id in rows:
        mapping.setdefault(int(product_id), promotion)
    return mapping


def get_active_promotions_for_store(config: TiendaConfig, now: datetime | None = None) -> list[TiendaPromocion]:
    if not config or not config.id_cliente:
        return []
    return active_promotions_query(int(config.id_cliente), now=now).all()


def serialize_context_promotions(config: TiendaConfig, limit: int = 8) -> list[dict]:
    promotions = get_active_promotions_for_store(config)[:limit]
    return [
        serialize_public_promotion(promotion, include_products=True, product_limit=4)
        for promotion in promotions
    ]


def attach_promotion_to_product_data(
    producto: Producto,
    data: dict,
    promotion: TiendaPromocion | None,
    *,
    allow_discount_percentage: bool = True,
) -> dict:
    if not promotion:
        data['promocion_activa'] = None
        return data

    metrics = calculate_promotion_price(producto, promotion)
    data['precio'] = metrics['precio']
    data['precio_anterior'] = metrics['precio_anterior']
    data['ahorro'] = metrics['ahorro']
    data['descuento_porcentaje'] = metrics['descuento_porcentaje'] if allow_discount_percentage else None
    data['es_oferta'] = True
    data['promocion_activa'] = serialize_public_promotion(
        promotion,
        include_products=False,
    )
    return data


def product_ids_grouped_by_promotion(promotions: list[TiendaPromocion]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for promotion in promotions:
        grouped[promotion.id_promocion] = [rel.id_producto for rel in promotion.productos_rel]
    return grouped


def validate_promotion_payload(data: dict) -> tuple[dict, str | None]:
    normalized = {
        'nombre': str(data.get('nombre') or '').strip(),
        'descripcion_corta': str(data.get('descripcion_corta') or '').strip(),
        'tipo': str(data.get('tipo') or '').strip().lower(),
        'valor': data.get('valor'),
        'fecha_inicio': str(data.get('fecha_inicio') or '').strip(),
        'fecha_fin': str(data.get('fecha_fin') or '').strip(),
        'activa': bool(data.get('activa', True)),
        'productos': data.get('productos') or [],
    }

    if not normalized['nombre']:
        return normalized, 'nombre_requerido'
    if normalized['tipo'] not in PROMOTION_TYPES:
        return normalized, 'tipo_invalido'

    try:
        normalized['valor'] = round_decimal(normalized['valor'])
    except Exception:
        return normalized, 'valor_invalido'

    if normalized['valor'] <= Decimal('0'):
        return normalized, 'valor_invalido'

    try:
        normalized['fecha_inicio'] = datetime.fromisoformat(normalized['fecha_inicio'])
        normalized['fecha_fin'] = datetime.fromisoformat(normalized['fecha_fin'])
    except Exception:
        return normalized, 'fecha_invalida'

    if normalized['fecha_fin'] <= normalized['fecha_inicio']:
        return normalized, 'rango_fechas_invalido'

    try:
        normalized['productos'] = sorted({int(product_id) for product_id in normalized['productos'] if product_id})
    except Exception:
        return normalized, 'productos_invalidos'

    if not normalized['productos']:
        return normalized, 'productos_requeridos'

    return normalized, None


def ensure_products_belong_to_client(product_ids: list[int], client_id: int) -> tuple[list[Producto], str | None]:
    products = Producto.query.filter(Producto.id_producto.in_(product_ids)).all()
    if len(products) != len(product_ids):
        return [], 'productos_invalidos'

    valid_products = []
    for product in products:
        if product.id_cliente and int(product.id_cliente) != int(client_id):
            return [], 'producto_asociado_a_otro_cliente'
        if not product.id_cliente:
            product.id_cliente = client_id
        valid_products.append(product)
    return valid_products, None


def find_overlapping_promotion(
    *,
    client_id: int,
    product_ids: list[int],
    fecha_inicio: datetime,
    fecha_fin: datetime,
    exclude_promotion_id: int | None = None,
) -> TiendaPromocion | None:
    query = (
        TiendaPromocion.query
        .join(TiendaPromocionProducto, TiendaPromocionProducto.id_promocion == TiendaPromocion.id_promocion)
        .filter(
            TiendaPromocion.id_cliente == client_id,
            TiendaPromocion.activa.is_(True),
            TiendaPromocionProducto.id_producto.in_(product_ids),
            TiendaPromocion.fecha_inicio <= fecha_fin,
            TiendaPromocion.fecha_fin >= fecha_inicio,
        )
    )
    if exclude_promotion_id:
        query = query.filter(TiendaPromocion.id_promocion != exclude_promotion_id)
    return query.order_by(TiendaPromocion.fecha_inicio.asc()).first()


def save_promotion(
    *,
    promotion: TiendaPromocion | None,
    client_id: int,
    data: dict,
) -> tuple[TiendaPromocion | None, str | None]:
    normalized, error = validate_promotion_payload(data)
    if error:
        return None, error

    products, error = ensure_products_belong_to_client(normalized['productos'], client_id)
    if error:
        return None, error

    overlap = find_overlapping_promotion(
        client_id=client_id,
        product_ids=[product.id_producto for product in products],
        fecha_inicio=normalized['fecha_inicio'],
        fecha_fin=normalized['fecha_fin'],
        exclude_promotion_id=getattr(promotion, 'id_promocion', None),
    )
    if overlap:
        return None, 'promo_superpuesta'

    promotion = promotion or TiendaPromocion(id_cliente=client_id)
    promotion.id_cliente = client_id
    promotion.nombre = normalized['nombre']
    promotion.descripcion_corta = normalized['descripcion_corta'] or None
    promotion.tipo = normalized['tipo']
    promotion.valor = normalized['valor']
    promotion.fecha_inicio = normalized['fecha_inicio']
    promotion.fecha_fin = normalized['fecha_fin']
    promotion.activa = normalized['activa']

    if promotion.id_promocion is None:
        db.session.add(promotion)
        db.session.flush()

    promotion.productos_rel[:] = [
        TiendaPromocionProducto(id_producto=product.id_producto)
        for product in products
    ]
    db.session.flush()
    return promotion, None
