"""Redondeo SEDECO en el modo API (`sedeco_rounding`, API 1.20.0).

- La factura sale redondeada, igual que en el motor propio, y el pago tiene que
  sumar el total **redondeado**: la API rechaza con 400 el total crudo.
- La NC acredita el mismo total general que la factura: redondea sólo si la
  factura salió redondeada (se lee su dRedon). Las facturas anteriores a esto
  salieron crudas, y la NC de una de ellas tampoco redondea.
- El KuDE imprime el redondeo que la API informó, no uno calculado acá (esa
  prueba está en `test_facturacion_electronica_proveedor_ciclo.py`).
"""
from types import SimpleNamespace

from facturacion_electronica.services.receptor_facturado import redondeo_declarado

from test_facturacion_electronica_proveedor_base import xml_factura


def _pago(monto, nombre='Efectivo'):
    return SimpleNamespace(monto=monto, referencia=None, metodo=SimpleNamespace(nombre=nombre),
                           banco=None)


def _venta(total, tipo='contado'):
    return SimpleNamespace(tipo_venta=tipo, total=total)


def test_el_pago_suma_el_total_redondeado():
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(_venta(107437), [_pago(107437)])

    assert sum(int(e['amount']) for e in pago['entries']) == 107400


def test_el_pago_en_dos_medios_cierra_contra_el_redondeado():
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(_venta(107437), [_pago(50000), _pago(57437, 'Transferencia')])

    assert sum(int(e['amount']) for e in pago['entries']) == 107400


def test_apagado_el_pago_es_el_total_crudo(monkeypatch):
    from facturacion_electronica.services.proveedores import api_payload

    monkeypatch.setattr(api_payload, 'API_REDONDEO_SEDECO', False)
    pago = api_payload.construir_pago(_venta(107437), [_pago(107437)])

    assert sum(int(e['amount']) for e in pago['entries']) == 107437


def test_no_se_redondea_un_total_que_quedaria_en_cero():
    from facturacion_electronica.services.proveedores.api_payload import aplica_redondeo_sedeco

    assert aplica_redondeo_sedeco(30) is False
    assert aplica_redondeo_sedeco(107437) is True


def _xml_con_redondeo(redondeo):
    return xml_factura().replace(
        '</DE>', f'<gTotSub><dRedon>{redondeo}</dRedon></gTotSub></DE>',
    )


def test_lee_el_redondeo_de_la_factura():
    assert redondeo_declarado(_xml_con_redondeo(37)) == 37
    assert redondeo_declarado(_xml_con_redondeo(0)) == 0
    assert redondeo_declarado(xml_factura()) == 0  # factura sin gTotSub
    assert redondeo_declarado(None) == 0


def _nc_con_xml(xml):
    from unittest.mock import patch

    from facturacion_electronica import TIPO_NOTA_CREDITO
    from facturacion_electronica.services.proveedores.api_nota_credito import armar_cuerpo_nc

    documento = SimpleNamespace(numero='0000001', nc_motivo=1, nc_motivo_desc='x',
                                tipo_documento=TIPO_NOTA_CREDITO, id_devolucion=None, id_venta=9)
    original = SimpleNamespace(cdc='0' * 44)
    with patch('facturacion_electronica.services.proveedores.api_nota_credito.descargar_xml',
               return_value=(xml, None)):
        cuerpo, error = armar_cuerpo_nc(None, documento, original, SimpleNamespace(), [], 'uuid')
    assert error is None
    return cuerpo


def test_la_nc_de_una_factura_redondeada_tambien_redondea():
    assert _nc_con_xml(_xml_con_redondeo(37)).get('sedeco_rounding') is True


def test_la_nc_de_una_factura_cruda_no_redondea():
    """La #123 de Janelipy salió por 613.076 sin redondeo: su NC tiene que
    acreditar 613.076, no 613.050."""
    assert 'sedeco_rounding' not in _nc_con_xml(_xml_con_redondeo(0))
