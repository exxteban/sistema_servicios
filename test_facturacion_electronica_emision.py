from facturacion_electronica.services.emision_service import extraer_cdc


def test_extraer_cdc_desde_xml():
    xml = (
        '<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
        '<DE Id="01042812925001001000000112026022419853987480">'
        '<dDVId>0</dDVId></DE></rDE>'
    )
    assert extraer_cdc(xml) == '01042812925001001000000112026022419853987480'


def test_extraer_cdc_sin_match():
    assert extraer_cdc('<rDE></rDE>') is None
    assert extraer_cdc('') is None
    assert extraer_cdc(None) is None
