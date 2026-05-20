from app.utils.productos_errors import mensaje_error_producto, validar_longitudes_producto


def test_validar_longitudes_producto_avisa_campos_excedidos():
    mensaje = validar_longitudes_producto({
        'codigo': 'X' * 51,
        'nombre': 'N' * 201,
    })

    assert 'Codigo permite hasta 50 caracteres. Ingresaste 51.' in mensaje
    assert 'Nombre del producto permite hasta 200 caracteres. Ingresaste 201.' in mensaje


def test_validar_longitudes_producto_ignora_campos_validos_o_vacios():
    mensaje = validar_longitudes_producto({
        'codigo': 'X' * 50,
        'codigo_barras': None,
        'nombre': 'Producto valido',
    })

    assert mensaje is None


def test_mensaje_error_producto_traduce_data_too_long():
    class FakeDataError:
        orig = Exception('(1406, "Data too long for column \'codigo\' at row 1")')

    mensaje = mensaje_error_producto(FakeDataError())

    assert mensaje == 'El campo Codigo permite hasta 50 caracteres. Revisa el dato e intenta de nuevo.'
