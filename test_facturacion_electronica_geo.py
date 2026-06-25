from facturacion_electronica.services import geo


def test_central_tiene_codigo_12():
    central = [d for d in geo.departamentos() if d['descripcion'] == 'CENTRAL']
    assert central and central[0]['codigo'] == 12


def test_nemby_codigos_oficiales():
    assert geo.descripcion_distrito('161') == 'ÑEMBY'
    assert geo.descripcion_ciudad(5975) == 'ÑEMBY'


def test_cascada_departamento_distrito_ciudad():
    distritos = geo.distritos_de('12')
    assert any(d['codigo'] == 161 for d in distritos)
    ciudades = geo.ciudades_de(161)
    assert any(c['codigo'] == 5975 for c in ciudades)


def test_codigos_invalidos_devuelven_vacio_o_none():
    assert geo.distritos_de('') == []
    assert geo.ciudades_de(None) == []
    assert geo.descripcion_departamento('99999') is None
