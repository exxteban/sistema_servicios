"""La NC acredita lo que declaró la factura: su receptor y sus precios.

Las dos cosas salieron de la NC de anulación de la venta #123 (Janelipy,
2026-09-27): la factura se emitió a una cédula con 5% de descuento global, y la
NC salió a un RUC (la ficha había cambiado) y a precio lleno.
"""
from types import SimpleNamespace

from facturacion_electronica.services.receptor_facturado import (
    cliente_facturado_propio,
    cliente_propio,
    leer_receptor,
    receptor_api,
)

from test_facturacion_electronica_proveedor_base import xml_factura


def _cliente(ruc_ci, nombre='Esteban Lezcano'):
    return SimpleNamespace(
        id_cliente=7, ruc_ci=ruc_ci, nombre=nombre, email='', telefono='0981',
        direccion='',
    )


def test_lee_el_receptor_con_declaracion_de_encoding():
    campos = leer_receptor(xml_factura('4281292', 'Esteban Lezcano'))
    assert campos['iNatRec'] == '2'
    assert campos['dNumIDRec'] == '4281292'
    assert campos['dNomRec'] == 'Esteban Lezcano'


def test_xml_ilegible_o_sin_receptor_es_none():
    assert leer_receptor(None) is None
    assert leer_receptor('<no-cierra') is None
    assert leer_receptor('<rDE><DE/></rDE>') is None


def test_receptor_api_de_una_cedula():
    receptor = receptor_api(leer_receptor(xml_factura('4281292', 'Esteban Lezcano')))
    assert receptor['nature'] == 2
    assert receptor['operation_type'] == 2
    assert receptor['id_type'] == 1
    assert receptor['id_number'] == '4281292'
    assert 'ruc' not in receptor


def test_receptor_api_de_un_contribuyente():
    receptor = receptor_api(leer_receptor(xml_factura('4281292-5', 'Esteban Lezcano')))
    assert receptor['nature'] == 1
    assert receptor['ruc'] == '4281292'
    assert receptor['dv'] == 5
    assert 'id_number' not in receptor


def test_motor_propio_no_hereda_el_ruc_de_la_ficha():
    """La ficha tiene RUC; la factura, cédula. Gana la factura, y no queda
    ninguna clave de contribuyente colgando del `cliente` de xmlgen."""
    original = SimpleNamespace(xml_qr=None, xml_firmado=xml_factura('4281292'), xml=None)
    cliente = cliente_facturado_propio(original, _cliente('4281292-5'))
    assert cliente['contribuyente'] is False
    assert cliente['documentoNumero'] == '4281292'
    assert 'ruc' not in cliente
    assert 'tipoContribuyente' not in cliente
    assert cliente['codigo'] == '007'


def test_motor_propio_sin_xml_queda_la_ficha():
    original = SimpleNamespace(xml_qr=None, xml_firmado=None, xml=None)
    cliente = cliente_facturado_propio(original, _cliente('4281292-5'))
    assert cliente['contribuyente'] is True
    assert cliente['ruc'] == '4281292-5'


def test_cliente_propio_de_un_contribuyente_arma_el_ruc_con_dv():
    base = {'razonSocial': 'x', 'documentoTipo': 1, 'documentoNumero': '1', 'codigo': '001'}
    cliente = cliente_propio(leer_receptor(xml_factura('80012345-6', 'Ferretería SA')), base)
    assert cliente['ruc'] == '80012345-6'
    assert cliente['razonSocial'] == 'Ferretería SA'
    assert 'documentoNumero' not in cliente


def _detalle(id_detalle, precio, cantidad=1, descuento=0, iva=10):
    return SimpleNamespace(
        id_detalle_venta=id_detalle, id_producto=id_detalle, producto=None,
        cantidad=cantidad, precio_unitario=precio, descuento_linea=descuento,
        porcentaje_iva=iva, subtotal=precio * cantidad - descuento,
    )


def test_los_precios_de_la_nc_llevan_el_descuento_global():
    """Los mismos números de la #123: 344.343 + 301.000 con 5% global."""
    from facturacion_electronica.services.nota_credito import lineas_de_venta

    venta = SimpleNamespace(
        detalles=[_detalle(1, 344343), _detalle(2, 301000, iva=5)], total=613076,
    )
    lineas = lineas_de_venta(venta)
    acreditado = sum(l.cantidad * l.precio_unitario for l in lineas)
    assert round(acreditado) == 613076


def test_sin_descuento_global_el_precio_es_el_subtotal():
    from facturacion_electronica.services.nota_credito import precios_facturados

    venta = SimpleNamespace(detalles=[_detalle(1, 100000, cantidad=2, descuento=20000)],
                            total=180000)
    assert precios_facturados(venta) == {1: 90000}


def test_la_devolucion_tambien_acredita_con_el_descuento_global():
    """Mismo hueco en la NC por devolución: el precio salía del subtotal."""
    from facturacion_electronica.services.nota_credito import lineas_de_devolucion

    detalle = _detalle(1, 100000)
    venta = SimpleNamespace(detalles=[detalle], total=95000)
    devolucion = SimpleNamespace(venta=venta, detalles=[SimpleNamespace(
        detalle_venta_original=detalle, producto=None, id_producto=1, cantidad=1,
        precio_unitario=100000,
    )])
    assert lineas_de_devolucion(devolucion)[0].precio_unitario == 95000
