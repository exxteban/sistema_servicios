from types import SimpleNamespace

from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_RECHAZADO,
)
from facturacion_electronica.services.guarda import (
    documento_en_proveedor,
    documento_impide_anular_venta,
    error_original_no_acreditable,
    error_venta_no_facturable,
)


def test_venta_anulada_no_se_factura():
    error = error_venta_no_facturable(SimpleNamespace(estado='anulada'))
    assert error is not None
    assert 'anulada' in error.lower()
    assert error_venta_no_facturable(SimpleNamespace(estado='completada')) is None
    assert error_venta_no_facturable(None) is None


def test_firmado_propio_no_impide_anular_la_venta():
    doc = SimpleNamespace(estado=ESTADO_FIRMADO, api_documento_id=None)
    assert not documento_impide_anular_venta(doc)
    assert not documento_en_proveedor(doc)


def test_firmado_de_la_api_impide_anular_la_venta():
    """PENDING_BATCH ya tiene CDC del otro lado y se transmite solo en ~30s."""
    doc = SimpleNamespace(estado=ESTADO_FIRMADO, api_documento_id='abc-123')
    assert documento_impide_anular_venta(doc)
    assert documento_en_proveedor(doc)


def test_enviado_y_aprobado_impiden_anular():
    assert documento_impide_anular_venta(
        SimpleNamespace(estado=ESTADO_ENVIADO, api_documento_id=None)
    )
    assert documento_impide_anular_venta(
        SimpleNamespace(estado=ESTADO_APROBADO, api_documento_id=None)
    )


def test_cancelado_o_rechazado_ya_no_impiden_anular():
    assert not documento_impide_anular_venta(
        SimpleNamespace(estado=ESTADO_CANCELADO, api_documento_id='abc-123')
    )
    assert not documento_impide_anular_venta(
        SimpleNamespace(estado=ESTADO_RECHAZADO, api_documento_id='abc-123')
    )


def test_generado_local_no_impide_anular():
    assert not documento_impide_anular_venta(
        SimpleNamespace(estado=ESTADO_GENERADO, api_documento_id=None)
    )
    assert not documento_impide_anular_venta(
        SimpleNamespace(estado=ESTADO_ERROR, api_documento_id=None)
    )


def _factura_aprobada(cliente):
    """Factura viva, con su venta y su cliente, como la mira la guarda."""
    return SimpleNamespace(
        estado=ESTADO_APROBADO,
        cdc='0' * 44,
        respuesta_codigo=None,
        venta=SimpleNamespace(cliente=cliente),
    )


def test_no_se_acredita_una_factura_con_receptor_innominado():
    """SIFEN deja facturar a un consumidor sin identificar pero no deja
    acreditarle: la NC vuelve rechazada con "El adquiriente ... no se encuentra
    identificado". Se frena antes de reservar número, porque corregir la ficha
    del cliente no tiene que costar un correlativo."""
    consumidor_final = SimpleNamespace(id_cliente=1, ruc_ci=None)
    error = error_original_no_acreditable(_factura_aprobada(consumidor_final))
    assert error and 'sin identificar' in error
    # El mensaje tiene que decir la salida, no sólo el problema.
    assert 'cancelarla' in error

    sin_documento = SimpleNamespace(id_cliente=7, ruc_ci='   ')
    assert error_original_no_acreditable(_factura_aprobada(sin_documento))

    todo_ceros = SimpleNamespace(id_cliente=7, ruc_ci='0000000')
    assert error_original_no_acreditable(_factura_aprobada(todo_ceros))


_XML_INNOMINADO = (
    '<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><DE><gDatRec>'
    '<iNatRec>2</iNatRec><iTipIDRec>5</iTipIDRec><dNumIDRec>0</dNumIDRec>'
    '<dNomRec>Sin Nombre</dNomRec></gDatRec></DE></rDE>'
)
_XML_CON_CEDULA = _XML_INNOMINADO.replace(
    '<iTipIDRec>5</iTipIDRec><dNumIDRec>0</dNumIDRec>',
    '<iTipIDRec>1</iTipIDRec><dNumIDRec>4281292</dNumIDRec>',
)


def test_decide_el_receptor_que_declaro_la_factura_no_la_ficha():
    """La NC lleva el receptor del XML de la factura. Con la ficha completada
    después, mirar la ficha dejaba pasar una NC condenada al rechazo."""
    con_cedula_hoy = SimpleNamespace(id_cliente=7, ruc_ci='4281292')
    factura = _factura_aprobada(con_cedula_hoy)

    error = error_original_no_acreditable(factura, xml_factura=_XML_INNOMINADO)
    assert error and 'sin identificar' in error
    assert 'cancelarla' in error

    # Motor propio: el XML guardado en el documento alcanza, sin pasarlo.
    factura.xml_firmado = _XML_INNOMINADO
    assert error_original_no_acreditable(factura)


def test_factura_identificada_se_acredita_aunque_la_ficha_ya_no_lo_este():
    consumidor_final = SimpleNamespace(id_cliente=1, ruc_ci=None)
    factura = _factura_aprobada(consumidor_final)
    assert error_original_no_acreditable(factura, xml_factura=_XML_CON_CEDULA) is None


def test_un_cliente_identificado_si_se_puede_acreditar():
    con_cedula = SimpleNamespace(id_cliente=7, ruc_ci='4281292')
    assert error_original_no_acreditable(_factura_aprobada(con_cedula)) is None

    con_ruc = SimpleNamespace(id_cliente=8, ruc_ci='80012345-6')
    assert error_original_no_acreditable(_factura_aprobada(con_ruc)) is None
