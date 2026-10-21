"""Casos de cálculo que no requieren una base de datos."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.contador_meses import _monto
from app.services.devoluciones import monto_reembolsable, precio_reembolsable
from app.services.resumen_contadora_ventas import totales_de_la_factura
from facturacion_electronica.services.nota_credito import precios_facturados
from facturacion_electronica.services.totales_xml import totales_declarados


@pytest.mark.parametrize('texto,esperado', [
    ('', '0'), ('0', '0'), ('150.000', '150000'), ('150000', '150000'),
    ('1.234,56', '1234.56'), ('9999999999999,99', '9999999999999.99'),
])
def test_importes_locales_validos(texto, esperado):
    assert _monto(texto) == Decimal(esperado)


def _venta(total, *lineas):
    """Venta sin base: cada línea es (precio_unitario, cantidad, descuento_linea)."""
    detalles = [
        SimpleNamespace(id_detalle_venta=i, producto=None, id_producto=i, cantidad=cantidad,
                        precio_unitario=precio, descuento_linea=descuento,
                        subtotal=precio * cantidad - descuento, porcentaje_iva=10)
        for i, (precio, cantidad, descuento) in enumerate(lineas, start=1)
    ]
    return SimpleNamespace(total=total, subtotal=sum(d.subtotal for d in detalles), detalles=detalles)


def test_fraccionar_devolucion_respeta_total_cobrado():
    venta = _venta(100, (100, 3, 0))
    precio = precio_reembolsable(venta, venta.detalles[0])
    montos = [monto_reembolsable(precio, 1, anterior) for anterior in (0, 1, 2)]
    assert montos == [Decimal('33'), Decimal('34'), Decimal('33')]
    assert sum(montos) == venta.total


def test_descuento_total_no_deja_iva_residual():
    totales = totales_de_la_factura(110, 0, 10, 0, 0)
    assert all(valor == 0 for valor in totales.values())
    venta = _venta(0, (110, 1, 0))
    assert precio_reembolsable(venta, venta.detalles[0]) == 0


def test_reembolso_combina_descuento_de_linea_y_global():
    venta = _venta(90, (100, 2, 20))
    assert precio_reembolsable(venta, venta.detalles[0]) == 45


def test_reembolso_es_el_precio_de_la_factura():
    """Mismo reparto que la factura: devolver todo da exacto el total cobrado,
    y la NC electrónica (que sale de `precios_facturados`) no difiere ni en 1 Gs."""
    venta = _venta(2000, (1001, 1, 0), (1001, 1, 0), (1001, 1, 0))
    facturados = precios_facturados(venta)
    devuelto = sum(monto_reembolsable(precio_reembolsable(venta, d), d.cantidad) for d in venta.detalles)
    assert devuelto == venta.total
    assert all(float(precio_reembolsable(venta, d)) == facturados[d.id_detalle_venta] for d in venta.detalles)


@pytest.mark.parametrize('contenido', [
    '', '<dIVA10>100</dIVA10>',
    '<dTotGralOpe>110</dTotGralOpe><dIVA10>error</dIVA10>',
    '<dTotGralOpe>NaN</dTotGralOpe>',
    '<dTotGralOpe>Infinity</dTotGralOpe>',
    '<dTotGralOpe/>',
])
def test_xml_incompleto_o_corrupto_activa_estimacion(contenido):
    assert totales_declarados(f'<rDE><DE><gTotSub>{contenido}</gTotSub></DE></rDE>') is None


def test_xml_valido_con_importes_cero_es_aceptado():
    totales = totales_declarados('<rDE><DE><gTotSub><dTotGralOpe>0</dTotGralOpe></gTotSub></DE></rDE>')
    assert totales['total'] == 0
