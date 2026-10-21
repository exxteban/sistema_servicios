"""Venta por peso: una pieza pesada es 1 unidad cuyo precio es peso x precio/kg.

`cantidad` sigue siendo 1, asi venta, factura, caja y stock no cambian. Ver
docs/pasteleria_fase2_diseno.md.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.utils.unidades_venta import UNIDAD_VENTA_KG, UNIDAD_VENTA_UNIDAD
from gastronomia.config_flags import FLAG_VENTA_POR_PESO, PESO_ATAJOS_DEFAULT
from app import db
from gastronomia.models import GastronomiaClienteConfig, GastronomiaProducto
from gastronomia.peso_models import UNIDADES_VENTA_MENU
from gastronomia.services.pasteleria_flags import flag_activo


PESO_MAX_KG = Decimal('50')
GRAMO = Decimal('0.001')
CENTAVOS = Decimal('0.01')


def venta_por_peso_habilitada(cliente_id: int | None) -> bool:
    return flag_activo(cliente_id, FLAG_VENTA_POR_PESO)


def es_por_peso(producto) -> bool:
    """Acepta el modelo o el dict serializado del producto."""
    unidad = producto.get('unidad_venta') if isinstance(producto, dict) else getattr(producto, 'unidad_venta', None)
    return (unidad or UNIDAD_VENTA_UNIDAD) == UNIDAD_VENTA_KG


def normalizar_unidad_menu(valor) -> str:
    unidad = str(valor or UNIDAD_VENTA_UNIDAD).strip().lower()
    if unidad not in UNIDADES_VENTA_MENU:
        raise ValueError('La unidad de venta tiene que ser "unidad" o "kg".')
    return unidad


def parsear_peso(valor) -> Decimal:
    texto = str(valor if valor is not None else '').strip().replace(',', '.')
    if not texto:
        raise ValueError('Ingresa el peso en kg.')
    try:
        peso = Decimal(texto)
    except InvalidOperation:
        raise ValueError('El peso no es valido.')
    if not peso.is_finite() or peso <= 0:
        raise ValueError('El peso tiene que ser mayor a cero.')
    if peso > PESO_MAX_KG:
        raise ValueError(f'El peso no puede superar {PESO_MAX_KG} kg.')
    if peso != peso.quantize(GRAMO):
        raise ValueError('El peso admite hasta 3 decimales (gramos).')
    return peso.quantize(GRAMO)


def importe_por_peso(precio_por_kg, peso: Decimal) -> Decimal:
    # Se redondea a centavos; en guaranies el precio ya viene sin decimales.
    return (Decimal(str(precio_por_kg or 0)) * peso).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def formatear_kg(peso) -> str:
    """1.25 -> '1,250 kg' (siempre 3 decimales, coma decimal)."""
    return f'{Decimal(str(peso)).quantize(GRAMO):.3f}'.replace('.', ',') + ' kg'


def nombre_con_peso(nombre: str, peso) -> str:
    return f'{nombre} · {formatear_kg(peso)}'[:160]


def linea_por_peso(producto: dict, item_data: dict, modificadores: Decimal) -> dict | None:
    """Campos de la linea para un producto por kilo; None si se vende por unidad.

    Sin promociones (asumen cantidades enteras). Los extras se cobran por pieza.
    """
    if not es_por_peso(producto):
        return None
    if _cantidad_pedida(item_data) > 1:
        raise ValueError(
            f'"{producto.get("nombre")}" se vende por peso: carga cada pieza como una linea con su peso.'
        )
    peso = parsear_peso(item_data.get('peso_kg'))
    precio_kg = Decimal(str(producto.get('precio_base', producto.get('precio')) or 0)).quantize(CENTAVOS)
    subtotal = (importe_por_peso(precio_kg, peso) + Decimal(str(modificadores or 0))).quantize(CENTAVOS)
    return {
        'cantidad': 1,
        'peso_kg': peso,
        'precio_por_kg': precio_kg,
        'subtotal': subtotal,
        'nombre_producto': nombre_con_peso(producto['nombre'], peso),
    }


def nombre_servicio_item(item) -> str:
    """Nombre del `Servicio` de venta de un item. El servicio es compartido por producto,
    asi que una pieza pesada no le deja su peso: si no, dos tortas de pesos distintos
    en una venta (y ventas viejas) mostrarian el de la ultima. Ver diseno Fase 2, hallazgo 1.
    """
    if item.peso_kg is None:
        return item.nombre_producto
    return nombre_base_item(item)[:200]


def nombre_base_item(item) -> str:
    """Nombre del producto sin el peso que se le agrego a la linea."""
    producto = db.session.get(GastronomiaProducto, int(item.producto_id))
    return producto.nombre if producto else (item.nombre_producto or '').split(' · ')[0]


def rechazar_por_peso_en_pedido_web(cliente_id: int, items: list[dict]) -> None:
    """El pedido web no carga peso: un producto por kilo se pide en el local (Fase 6: encargo web)."""
    ids = {int(item['producto_id']) for item in items if item.get('producto_id')}
    if not ids:
        return
    por_peso = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.id_producto.in_(ids),
        GastronomiaProducto.unidad_venta == UNIDAD_VENTA_KG,
    ).first()
    if por_peso:
        raise ValueError(f'"{por_peso.nombre}" se vende por peso: consultalo con el local.')


def atajos_peso(cliente_id: int | None) -> list[float]:
    config = GastronomiaClienteConfig.query.filter_by(cliente_id=int(cliente_id or 0)).first() if cliente_id else None
    return parsear_atajos(getattr(config, 'peso_atajos_kg', None) or PESO_ATAJOS_DEFAULT)


def parsear_atajos(texto: str) -> list[float]:
    """'1, 1,5 ; 2' no se admite: separador coma y punto decimal ('1,1.5,2')."""
    atajos = []
    for parte in str(texto or '').split(','):
        parte = parte.strip()
        if not parte:
            continue
        peso = parsear_peso(parte)
        if float(peso) not in atajos:
            atajos.append(float(peso))
    if len(atajos) > 6:
        raise ValueError('Hasta 6 atajos de peso.')
    return atajos


def _cantidad_pedida(item_data: dict) -> int:
    try:
        return int(item_data.get('cantidad') or 1)
    except (TypeError, ValueError):
        return 1
