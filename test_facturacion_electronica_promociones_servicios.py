"""[servicios] Líneas con promoción en la factura electrónica.

El POS (`parte3_helpers`) y la caja gastronómica (`venta_integration_service`)
guardan `precio_unitario` ya rebajado y además el descuento en `descuento_linea`.
Cada línea del DE tiene que declarar exactamente su `subtotal`.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.venta import DetalleVenta
from app.services.promociones_calculo import calculate_promotion_totals
from facturacion_electronica.services.data_builder import construir_items


def _neto(item):
    return item['cantidad'] * (item['precioUnitario'] - item['descuento'])


def _detalle_pos(precio_lista, cantidad, promocion):
    """Igual que el POS: precio efectivo + descuento_linea + subtotal cobrado."""
    m = calculate_promotion_totals(Decimal(precio_lista), cantidad, promocion)
    return DetalleVenta(
        id_producto=1,
        cantidad=cantidad,
        precio_unitario=m['precio_unitario_efectivo'],
        precio_original=Decimal(precio_lista),
        descuento_linea=m['descuento_linea'],
        subtotal=m['subtotal_base'],
        porcentaje_iva=10,
    )


@pytest.mark.parametrize('promocion, cantidad, cobrado', [
    (SimpleNamespace(tipo='porcentaje', valor=10), 2, 18000),
    (SimpleNamespace(tipo='monto_fijo', valor=1500), 2, 17000),
    (SimpleNamespace(tipo='precio_promocional', valor=8000), 3, 24000),
    (SimpleNamespace(tipo='cantidad', cantidad_lleva=3, cantidad_paga=2), 3, 20000),
])
def test_linea_con_promocion_declara_lo_cobrado(promocion, cantidad, cobrado):
    detalle = _detalle_pos('10000', cantidad, promocion)
    assert float(detalle.subtotal) == cobrado

    item = construir_items([detalle], total_objetivo=detalle.subtotal)[0]

    # El descuento de la promoción ya está en el precio: no se resta otra vez.
    assert _neto(item) == pytest.approx(cobrado)
    assert item['descuento'] < 1


def test_linea_sin_promocion_no_cambia():
    detalle = _detalle_pos('10000', 2, None)
    item = construir_items([detalle])[0]
    assert item['precioUnitario'] == 10000
    assert item['descuento'] == 0


def test_precio_redondeado_de_gastronomia_no_da_descuento_negativo():
    # 3 platos por 10.000: precio_unitario = 3333.33 (subtotal / cantidad redondeado).
    detalle = DetalleVenta(
        id_servicio=1, cantidad=3, precio_unitario=Decimal('3333.33'),
        descuento_linea=Decimal('0'), subtotal=Decimal('10000'), porcentaje_iva=10,
    )
    item = construir_items([detalle], total_objetivo=Decimal('10000'))[0]
    assert item['descuento'] == 0


def test_linea_liviana_sin_subtotal_usa_descuento_linea():
    """Las líneas de la nota de crédito no traen subtotal."""
    linea = SimpleNamespace(
        producto=None, servicio=None, id_producto=1, cantidad=2,
        precio_unitario=9000, descuento_linea=0, porcentaje_iva=10,
    )
    item = construir_items([linea])[0]
    assert _neto(item) == 18000
