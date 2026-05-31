"""
Servicios de promociones de tienda.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import selectinload

from app import db
from app.models.producto import Producto
from app.models.tienda import TiendaConfig
from app.models.tienda_promocion import (
    PROMOTION_TYPES,
    TiendaPromocion,
    TiendaPromocionGastronomiaProducto,
    TiendaPromocionProducto,
)
from app.services.promociones_calculo import calculate_promotion_totals, money
from app.services.tienda_promociones_public import is_public_store_product, store_promotion_catalog_type
from app.utils.helpers import get_app_timezone, utc_naive_to_local


def promotion_label(tipo: str) -> str:
    labels = {
        'porcentaje': 'Descuento %',
        'monto_fijo': 'Monto fijo',
        'precio_promocional': 'Precio promo',
        'cantidad': 'Promo por cantidad',
    }
    return labels.get((tipo or '').strip(), 'Promoción')


def round_decimal(value: Decimal | float | int | str) -> Decimal:
    return money(value)


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
            selectinload(TiendaPromocion.productos_rel).selectinload(TiendaPromocionProducto.producto),
            selectinload(TiendaPromocion.gastronomia_productos_rel).selectinload(
                TiendaPromocionGastronomiaProducto.producto
            ),
        )
        .order_by(TiendaPromocion.fecha_fin.asc(), TiendaPromocion.nombre.asc())
    )


def list_admin_promotions(client_id: int):
    return (
        TiendaPromocion.query
        .filter(TiendaPromocion.id_cliente == client_id)
        .options(
            selectinload(TiendaPromocion.productos_rel).selectinload(TiendaPromocionProducto.producto),
            selectinload(TiendaPromocion.gastronomia_productos_rel).selectinload(
                TiendaPromocionGastronomiaProducto.producto
            ),
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
    metrics = calculate_promotion_totals(base_price, 1, promotion)
    final_price = metrics['subtotal_base']
    ahorro = metrics['descuento_linea']
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
    catalog_type: str | None = None,
) -> dict:
    products = []
    if include_products and catalog_type != 'gastronomia':
        for rel in promotion.productos_rel[:product_limit]:
            if is_public_store_product(rel.producto, 'producto', promotion.id_cliente):
                products.append({
                    'id': rel.producto.id_producto,
                    'nombre': rel.producto.nombre,
                    'tipo_catalogo': 'producto',
                })
    if include_products and catalog_type != 'producto':
        remaining = max(0, product_limit - len(products))
        for rel in promotion.gastronomia_productos_rel[:remaining]:
            if is_public_store_product(rel.producto, 'gastronomia', promotion.id_cliente):
                products.append({
                    'id': rel.producto.id_producto,
                    'nombre': rel.producto.nombre,
                    'tipo_catalogo': 'gastronomia',
                })

    return {
        'id': promotion.id_promocion,
        'nombre': promotion.nombre,
        'descripcion': promotion.descripcion_corta or '',
        'tipo': promotion.tipo,
        'tipo_label': promotion_label(promotion.tipo),
        'valor': float(round_decimal(promotion.valor or 0)),
        'cantidad_lleva': promotion.cantidad_lleva,
        'cantidad_paga': promotion.cantidad_paga,
        'etiqueta': _promotion_badge(promotion),
        'fecha_inicio': promotion.fecha_inicio.isoformat(),
        'fecha_fin': promotion.fecha_fin.isoformat(),
        'productos': products,
    }


def serialize_admin_promotion(promotion: TiendaPromocion, now: datetime | None = None) -> dict:
    products = [
        {
            'id_producto': rel.id_producto,
            'nombre': rel.producto.nombre if rel.producto else f'Producto {rel.id_producto}',
            'codigo': rel.producto.codigo if rel.producto else '',
            'tipo_catalogo': 'producto',
        }
        for rel in promotion.productos_rel
    ]
    products.extend([
        {
            'id_producto': rel.id_producto,
            'nombre': rel.producto.nombre if rel.producto else f'Producto gastronomico {rel.id_producto}',
            'codigo': 'GASTRO',
            'tipo_catalogo': 'gastronomia',
        }
        for rel in promotion.gastronomia_productos_rel
    ])
    return {
        'id_promocion': promotion.id_promocion,
        'nombre': promotion.nombre,
        'descripcion_corta': promotion.descripcion_corta or '',
        'tipo': promotion.tipo,
        'tipo_label': promotion_label(promotion.tipo),
        'valor': float(round_decimal(promotion.valor or 0)),
        'cantidad_lleva': promotion.cantidad_lleva,
        'cantidad_paga': promotion.cantidad_paga,
        'fecha_inicio': _serialize_local_datetime(promotion.fecha_inicio),
        'fecha_fin': _serialize_local_datetime(promotion.fecha_fin),
        'activa': bool(promotion.activa),
        'estado': admin_status(promotion, now=now),
        'productos': products,
    }


def _promotion_badge(promotion: TiendaPromocion) -> str:
    if promotion.tipo == 'cantidad':
        return f'{promotion.cantidad_lleva}x{promotion.cantidad_paga}'
    if promotion.tipo == 'porcentaje':
        return f'-{float(round_decimal(promotion.valor or 0)):g}%'
    return promotion.nombre


def _parse_local_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    aware = parsed.replace(tzinfo=get_app_timezone()) if parsed.tzinfo is None else parsed
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize_local_datetime(value: datetime) -> str:
    return utc_naive_to_local(value).replace(tzinfo=None).isoformat()


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


def get_active_product_promotion_map_any_client(
    product_ids: list[int] | set[int],
    now: datetime | None = None,
) -> dict[int, TiendaPromocion]:
    ids = [int(pid) for pid in product_ids if pid]
    if not ids:
        return {}
    now = now or datetime.utcnow()
    rows = (
        TiendaPromocion.query
        .join(TiendaPromocionProducto, TiendaPromocionProducto.id_promocion == TiendaPromocion.id_promocion)
        .filter(
            TiendaPromocion.activa.is_(True),
            TiendaPromocion.fecha_inicio <= now,
            TiendaPromocion.fecha_fin >= now,
            TiendaPromocionProducto.id_producto.in_(ids),
        )
        .order_by(TiendaPromocion.fecha_fin.asc(), TiendaPromocion.nombre.asc())
        .with_entities(TiendaPromocion, TiendaPromocionProducto.id_producto)
        .all()
    )
    mapping: dict[int, TiendaPromocion] = {}
    for promotion, product_id in rows:
        mapping.setdefault(int(product_id), promotion)
    return mapping


def get_active_gastronomia_product_promotion_map(
    client_id: int,
    product_ids: list[int] | set[int],
    now: datetime | None = None,
) -> dict[int, TiendaPromocion]:
    ids = [int(pid) for pid in product_ids if pid]
    if not ids:
        return {}
    rows = (
        active_promotions_query(client_id, now=now)
        .join(
            TiendaPromocionGastronomiaProducto,
            TiendaPromocionGastronomiaProducto.id_promocion == TiendaPromocion.id_promocion,
        )
        .filter(TiendaPromocionGastronomiaProducto.id_producto.in_(ids))
        .with_entities(TiendaPromocion, TiendaPromocionGastronomiaProducto.id_producto)
        .all()
    )
    mapping: dict[int, TiendaPromocion] = {}
    for promotion, product_id in rows:
        mapping.setdefault(int(product_id), promotion)
    return mapping


def get_active_gastronomia_product_promotion(
    client_id: int,
    product_id: int,
    now: datetime | None = None,
) -> TiendaPromocion | None:
    return get_active_gastronomia_product_promotion_map(client_id, [product_id], now=now).get(int(product_id))


def get_active_promotions_for_store(config: TiendaConfig, now: datetime | None = None) -> list[TiendaPromocion]:
    if not config or not config.id_cliente:
        return []
    catalog_type = store_promotion_catalog_type(config)
    relation_name = 'gastronomia_productos_rel' if catalog_type == 'gastronomia' else 'productos_rel'
    return [
        promotion
        for promotion in active_promotions_query(int(config.id_cliente), now=now).all()
        if any(is_public_store_product(rel.producto, catalog_type, promotion.id_cliente)
               for rel in getattr(promotion, relation_name))
    ]


def serialize_context_promotions(config: TiendaConfig, limit: int = 8) -> list[dict]:
    promotions = get_active_promotions_for_store(config)[:limit]
    catalog_type = store_promotion_catalog_type(config)
    return [
        serialize_public_promotion(promotion, include_products=True, product_limit=4, catalog_type=catalog_type)
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


def attach_gastronomia_promotion_to_product_data(
    producto: GastronomiaProducto,
    data: dict,
    promotion: TiendaPromocion | None,
) -> dict:
    if not promotion:
        data['promocion_activa'] = None
        return data
    metrics = calculate_promotion_totals(producto.precio or 0, 1, promotion)
    base_price = metrics['precio_base']
    final_price = metrics['subtotal_base']
    saving = metrics['descuento_linea']
    data['precio_base'] = float(base_price)
    data['precio'] = float(final_price)
    data['precio_anterior'] = float(base_price) if saving > 0 else None
    data['ahorro'] = float(saving) if saving > 0 else None
    data['descuento_porcentaje'] = int((saving / base_price) * 100) if base_price and saving > 0 else None
    data['es_oferta'] = True
    data['promocion_activa'] = serialize_public_promotion(promotion, include_products=False)
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
        'productos_gastronomia': data.get('productos_gastronomia') or [],
        'cantidad_lleva': data.get('cantidad_lleva'),
        'cantidad_paga': data.get('cantidad_paga'),
    }

    if not normalized['nombre']:
        return normalized, 'nombre_requerido'
    if normalized['tipo'] not in PROMOTION_TYPES:
        return normalized, 'tipo_invalido'

    if normalized['tipo'] == 'cantidad':
        try:
            normalized['cantidad_lleva'] = int(normalized['cantidad_lleva'])
            normalized['cantidad_paga'] = int(normalized['cantidad_paga'])
        except (TypeError, ValueError):
            return normalized, 'cantidades_invalidas'
        if normalized['cantidad_lleva'] <= normalized['cantidad_paga'] or normalized['cantidad_paga'] < 1:
            return normalized, 'cantidades_invalidas'
        normalized['valor'] = Decimal('1.00')
    else:
        try:
            normalized['valor'] = round_decimal(normalized['valor'])
        except Exception:
            return normalized, 'valor_invalido'
        if normalized['valor'] <= Decimal('0'):
            return normalized, 'valor_invalido'
        if normalized['tipo'] == 'porcentaje' and normalized['valor'] > Decimal('100'):
            return normalized, 'valor_invalido'
        normalized['cantidad_lleva'] = None
        normalized['cantidad_paga'] = None

    try:
        normalized['fecha_inicio'] = _parse_local_datetime(normalized['fecha_inicio'])
        normalized['fecha_fin'] = _parse_local_datetime(normalized['fecha_fin'])
    except Exception:
        return normalized, 'fecha_invalida'

    if normalized['fecha_fin'] <= normalized['fecha_inicio']:
        return normalized, 'rango_fechas_invalido'

    try:
        normalized['productos'] = sorted({int(product_id) for product_id in normalized['productos'] if product_id})
        normalized['productos_gastronomia'] = sorted({
            int(product_id)
            for product_id in normalized['productos_gastronomia']
            if product_id
        })
    except Exception:
        return normalized, 'productos_invalidos'

    if not normalized['productos'] and not normalized['productos_gastronomia']:
        return normalized, 'productos_requeridos'

    return normalized, None


def ensure_products_belong_to_client(product_ids: list[int], client_id: int) -> tuple[list[Producto], str | None]:
    if not product_ids:
        return [], None
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


def ensure_gastronomia_products_belong_to_client(
    product_ids: list[int],
    client_id: int,
) -> tuple[list[GastronomiaProducto], str | None]:
    from gastronomia.models import GastronomiaProducto

    if not product_ids:
        return [], None
    products = GastronomiaProducto.query.filter(
        GastronomiaProducto.id_producto.in_(product_ids),
        GastronomiaProducto.cliente_id == int(client_id),
    ).all()
    if len(products) != len(product_ids):
        return [], 'productos_gastronomia_invalidos'
    return products, None


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


def find_overlapping_gastronomia_promotion(
    *,
    client_id: int,
    product_ids: list[int],
    fecha_inicio: datetime,
    fecha_fin: datetime,
    exclude_promotion_id: int | None = None,
) -> TiendaPromocion | None:
    if not product_ids:
        return None
    query = (
        TiendaPromocion.query
        .join(
            TiendaPromocionGastronomiaProducto,
            TiendaPromocionGastronomiaProducto.id_promocion == TiendaPromocion.id_promocion,
        )
        .filter(
            TiendaPromocion.id_cliente == client_id,
            TiendaPromocion.activa.is_(True),
            TiendaPromocionGastronomiaProducto.id_producto.in_(product_ids),
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
    gastro_products, error = ensure_gastronomia_products_belong_to_client(
        normalized['productos_gastronomia'],
        client_id,
    )
    if error:
        return None, error

    promotion_id = getattr(promotion, 'id_promocion', None)
    overlap = find_overlapping_promotion(
        client_id=client_id,
        product_ids=[product.id_producto for product in products],
        fecha_inicio=normalized['fecha_inicio'],
        fecha_fin=normalized['fecha_fin'],
        exclude_promotion_id=promotion_id,
    )
    overlap = overlap or find_overlapping_gastronomia_promotion(
        client_id=client_id,
        product_ids=[product.id_producto for product in gastro_products],
        fecha_inicio=normalized['fecha_inicio'],
        fecha_fin=normalized['fecha_fin'],
        exclude_promotion_id=promotion_id,
    )
    if overlap:
        return None, 'promo_superpuesta'

    promotion = promotion or TiendaPromocion(id_cliente=client_id)
    promotion.id_cliente = client_id
    promotion.nombre = normalized['nombre']
    promotion.descripcion_corta = normalized['descripcion_corta'] or None
    promotion.tipo = normalized['tipo']
    promotion.valor = normalized['valor']
    promotion.cantidad_lleva = normalized['cantidad_lleva']
    promotion.cantidad_paga = normalized['cantidad_paga']
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
    promotion.gastronomia_productos_rel[:] = [
        TiendaPromocionGastronomiaProducto(id_producto=product.id_producto)
        for product in gastro_products
    ]
    db.session.flush()
    return promotion, None
