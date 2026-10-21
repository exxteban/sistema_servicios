"""Columnas de venta por peso (tortas por kilo) para producto e item de pedido.

Por mixin para no engordar `gastronomia/models.py`. Un producto comun queda en
`unidad` y un item comun con peso NULL. Diseno en docs/pasteleria_fase2_diseno.md.
"""
from app import db
from app.utils.unidades_venta import UNIDAD_VENTA_KG, UNIDAD_VENTA_UNIDAD


UNIDADES_VENTA_MENU = (UNIDAD_VENTA_UNIDAD, UNIDAD_VENTA_KG)


class ProductoPesoMixin:
    """`unidad_venta = 'kg'`: el `precio` del producto es precio por kilo."""

    unidad_venta = db.Column(
        db.String(10), nullable=False, default=UNIDAD_VENTA_UNIDAD, server_default=UNIDAD_VENTA_UNIDAD,
    )

    @property
    def se_vende_por_peso(self) -> bool:
        return (self.unidad_venta or UNIDAD_VENTA_UNIDAD) == UNIDAD_VENTA_KG

    def datos_peso(self) -> dict:
        return {'unidad_venta': self.unidad_venta or UNIDAD_VENTA_UNIDAD}


class PedidoItemPesoMixin:
    """Peso y precio por kilo congelados en la linea (NULL en items por unidad)."""

    peso_kg = db.Column(db.Numeric(10, 3), nullable=True)
    precio_por_kg = db.Column(db.Numeric(15, 2), nullable=True)

    def datos_peso(self) -> dict:
        return {
            'peso_kg': float(self.peso_kg) if self.peso_kg is not None else None,
            'precio_por_kg': float(self.precio_por_kg) if self.precio_por_kg is not None else None,
        }
