from decimal import Decimal, InvalidOperation


UNIDAD_VENTA_UNIDAD = 'unidad'
UNIDAD_VENTA_CANTIDAD = 'cantidad'
UNIDAD_VENTA_KG = 'kg'
UNIDAD_VENTA_METRO = 'metro'
UNIDAD_VENTA_METRO2 = 'metro cuadrado'
UNIDAD_VENTA_LITRO = 'litro'
UNIDAD_VENTA_BOLSA = 'bolsa'
UNIDAD_VENTA_CAJA = 'caja'
UNIDAD_VENTA_ROLLO = 'rollo'


_DEFINICIONES = {
    UNIDAD_VENTA_UNIDAD: ('Unidad', 'und', False),
    UNIDAD_VENTA_CANTIDAD: ('Cantidad', 'cant', False),
    UNIDAD_VENTA_KG: ('Kilogramo', 'kg', True),
    UNIDAD_VENTA_METRO: ('Metro', 'm', True),
    UNIDAD_VENTA_METRO2: ('Metro cuadrado', 'm2', True),
    UNIDAD_VENTA_LITRO: ('Litro', 'lt', True),
    UNIDAD_VENTA_BOLSA: ('Bolsa', 'bol', False),
    UNIDAD_VENTA_CAJA: ('Caja', 'caj', False),
    UNIDAD_VENTA_ROLLO: ('Rollo', 'rol', False),
}

UNIDADES_VENTA = tuple(_DEFINICIONES)

_SINONIMOS = {
    'cantidad': UNIDAD_VENTA_CANTIDAD, 'cantidades': UNIDAD_VENTA_CANTIDAD,
    'cant': UNIDAD_VENTA_CANTIDAD, 'por cantidad': UNIDAD_VENTA_CANTIDAD,
    'kg': UNIDAD_VENTA_KG, 'kilo': UNIDAD_VENTA_KG, 'kilos': UNIDAD_VENTA_KG,
    'kilogramo': UNIDAD_VENTA_KG, 'kilogramos': UNIDAD_VENTA_KG,
    'metro': UNIDAD_VENTA_METRO, 'metros': UNIDAD_VENTA_METRO,
    'm': UNIDAD_VENTA_METRO, 'mt': UNIDAD_VENTA_METRO, 'mts': UNIDAD_VENTA_METRO,
    'metro cuadrado': UNIDAD_VENTA_METRO2, 'metros cuadrados': UNIDAD_VENTA_METRO2,
    'm2': UNIDAD_VENTA_METRO2, 'm²': UNIDAD_VENTA_METRO2,
    'litro': UNIDAD_VENTA_LITRO, 'litros': UNIDAD_VENTA_LITRO,
    'l': UNIDAD_VENTA_LITRO, 'lt': UNIDAD_VENTA_LITRO, 'lts': UNIDAD_VENTA_LITRO,
    'bolsa': UNIDAD_VENTA_BOLSA, 'bolsas': UNIDAD_VENTA_BOLSA,
    'caja': UNIDAD_VENTA_CAJA, 'cajas': UNIDAD_VENTA_CAJA,
    'rollo': UNIDAD_VENTA_ROLLO, 'rollos': UNIDAD_VENTA_ROLLO,
}


def normalizar_unidad_venta(valor):
    valor = (valor or '').strip().lower()
    return _SINONIMOS.get(valor, UNIDAD_VENTA_UNIDAD)


def unidad_venta_label(unidad):
    return _DEFINICIONES[normalizar_unidad_venta(unidad)][0]


def unidad_venta_abreviatura(unidad):
    return _DEFINICIONES[normalizar_unidad_venta(unidad)][1]


def permite_cantidad_decimal(unidad):
    return _DEFINICIONES[normalizar_unidad_venta(unidad)][2]


def unidades_venta_meta():
    return {
        clave: {'label': label, 'abreviatura': abrev, 'decimal': decimal}
        for clave, (label, abrev, decimal) in _DEFINICIONES.items()
    }


def decimal_desde_valor(valor, default='0'):
    if valor in (None, ''):
        valor = default
    if isinstance(valor, Decimal):
        return valor
    texto = str(valor).strip().replace(',', '.')
    if not texto:
        texto = str(default)
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        raise ValueError('Cantidad inválida')


def cantidad_para_unidad(valor, unidad, *, campo='Cantidad', default='0'):
    cantidad = decimal_desde_valor(valor, default=default)
    unidad = normalizar_unidad_venta(unidad)
    if cantidad < 0:
        raise ValueError(f'{campo} no puede ser negativa')
    if not permite_cantidad_decimal(unidad) and cantidad != cantidad.to_integral_value():
        raise ValueError(f'{campo} debe ser entera para productos por unidad o cantidad')
    return cantidad


def cantidad_positiva_para_unidad(valor, unidad, *, campo='Cantidad'):
    cantidad = cantidad_para_unidad(valor, unidad, campo=campo, default='0')
    if cantidad <= 0:
        raise ValueError(f'{campo} debe ser mayor a cero')
    return cantidad


def format_cantidad(valor):
    try:
        cantidad = Decimal(str(valor or 0))
    except (InvalidOperation, ValueError):
        return str(valor or 0)
    texto = format(cantidad, 'f')
    if '.' in texto:
        texto = texto.rstrip('0').rstrip('.')
    return texto or '0'


def cantidad_json(valor):
    try:
        cantidad = Decimal(str(valor or 0))
    except (InvalidOperation, ValueError):
        return 0
    if cantidad == cantidad.to_integral_value():
        return int(cantidad)
    return float(cantidad)
