"""Construye el objeto 'data' de TIPS xmlgen a partir de una Venta del sistema.

Referencia: https://github.com/TIPS-SA/facturacionelectronicapy-xmlgen
Capa de mapeo sin red: lee la venta y la config del emisor y devuelve el dict.
El envío y la persistencia del documento se resuelven en fases posteriores.
"""
import re
import secrets

TIPO_DOCUMENTO_FACTURA = 1
TIPO_EMISION_NORMAL = 1
TIPO_TRANSACCION_VENTA = 1
TIPO_IMPUESTO_IVA = 1
MONEDA_PYG = 'PYG'
PAIS_PY = 'PRY'
PAIS_PY_DESC = 'Paraguay'

CONDICION_CONTADO = 1
CONDICION_CREDITO = 2

# Códigos de unidad de medida de SIFEN. Los que el sistema maneja pero SIFEN no
# tipifica (bolsa/caja/rollo) caen a Unidad (77).
UNIDAD_MEDIDA_DEFAULT = 77
UNIDAD_MEDIDA_POR_VENTA = {
    'unidad': 77,
    'cantidad': 77,
    'kg': 83,
    'metro': 87,
    'metro cuadrado': 109,
    'litro': 89,
    'bolsa': 77,
    'caja': 77,
    'rollo': 77,
}

IVA_TIPO_GRAVADO = 1
IVA_TIPO_EXENTO = 3

DOCUMENTO_TIPO_CEDULA = 1
DOCUMENTO_TIPO_INNOMINADO = 5

# Formas de pago SIFEN (iTiPago) y la tarjeta genérica (sin marca) que pide
# para pagos con tarjeta, ya que el POS no guarda la marca.
INFO_TARJETA_GENERICA = {'tipo': 99}

_SINONIMOS_UNIDAD = {
    'cantidad': 'cantidad',
    'cantidades': 'cantidad',
    'cant': 'cantidad',
    'kg': 'kg',
    'kilo': 'kg',
    'kilos': 'kg',
    'kilogramo': 'kg',
    'kilogramos': 'kg',
    'metro': 'metro',
    'metros': 'metro',
    'm': 'metro',
    'mt': 'metro',
    'mts': 'metro',
    'metro cuadrado': 'metro cuadrado',
    'metros cuadrados': 'metro cuadrado',
    'm2': 'metro cuadrado',
    'litro': 'litro',
    'litros': 'litro',
    'l': 'litro',
    'lt': 'litro',
    'lts': 'litro',
    'bolsa': 'bolsa',
    'bolsas': 'bolsa',
    'caja': 'caja',
    'cajas': 'caja',
    'rollo': 'rollo',
    'rollos': 'rollo',
    'unidad': 'unidad',
    'unidades': 'unidad',
    'und': 'unidad',
}


def _tipo_pago(nombre):
    """Mapea el nombre del método de pago al código SIFEN. Devuelve
    (tipo, infoTarjeta). tipo None significa que no es una entrega de contado."""
    n = (nombre or '').strip().lower()
    if 'efectivo' in n:
        return 1, None
    if 'debito' in n or 'débito' in n:
        return 4, INFO_TARJETA_GENERICA
    if 'credito tienda' in n or 'crédito tienda' in n:
        return None, None
    if 'tarjeta' in n or 'credito' in n or 'crédito' in n:
        return 3, INFO_TARJETA_GENERICA
    if 'transfer' in n:
        return 5, None
    if 'qr' in n or 'billetera' in n:
        return 7, None
    if 'cheque' in n:
        return 2, None
    return 99, None


def generar_codigo_seguridad():
    return str(secrets.randbelow(999_999_999) + 1).zfill(9)


def _solo_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def _normalizar_unidad(valor):
    valor = (valor or '').strip().lower()
    return _SINONIMOS_UNIDAD.get(valor, 'unidad')


def numero_documento(venta):
    """Extrae el numero de 7 digitos del documento desde la venta."""
    crudo = (
        getattr(venta, 'numero_factura', None)
        or getattr(venta, 'numero_comprobante', None)
        or ''
    ).strip()
    if '-' in crudo:
        crudo = crudo.split('-')[-1]
    digitos = _solo_digitos(crudo)
    if not digitos:
        digitos = str(venta.id_venta or 0)
    return digitos[-7:].zfill(7)


def construir_cliente(cliente):
    ruc_ci = (cliente.ruc_ci or '').strip()
    es_consumidor_final = cliente.id_cliente == 1 or not ruc_ci
    nombre = (cliente.nombre or '').strip() or 'Sin Nombre'

    base = {
        'razonSocial': nombre,
        'pais': PAIS_PY,
        'paisDescripcion': PAIS_PY_DESC,
        'email': (cliente.email or '').strip() or None,
        'telefono': (cliente.telefono or '').strip() or None,
        'direccion': (cliente.direccion or '').strip() or None,
        'codigo': str(cliente.id_cliente).zfill(3),
    }

    if not es_consumidor_final and '-' in ruc_ci:
        base.update({
            'contribuyente': True,
            'ruc': ruc_ci,
            'tipoOperacion': 1,
            'tipoContribuyente': 1,
        })
    else:
        documento = _solo_digitos(ruc_ci)
        innominado = es_consumidor_final or not documento or set(documento) == {'0'}
        if innominado:
            base.update({
                'contribuyente': False,
                'tipoOperacion': 2,
                'documentoTipo': DOCUMENTO_TIPO_INNOMINADO,
                'documentoNumero': '0',
            })
        else:
            base.update({
                'contribuyente': False,
                'tipoOperacion': 2,
                'documentoTipo': DOCUMENTO_TIPO_CEDULA,
                'documentoNumero': documento,
            })
    return base


def construir_entregas(pagos, total):
    entregas = []
    for pago in pagos:
        metodo = getattr(pago, 'metodo', None)
        tipo, info = _tipo_pago(metodo.nombre if metodo else '')
        if tipo is None:
            continue
        entrega = {
            'tipo': tipo,
            'monto': str(float(pago.monto or 0)),
            'moneda': MONEDA_PYG,
            'cambio': 0,
        }
        if info:
            entrega['infoTarjeta'] = info
        entregas.append(entrega)
    if not entregas:
        entregas = [
            {'tipo': 1, 'monto': str(float(total or 0)), 'moneda': MONEDA_PYG, 'cambio': 0}
        ]
    return entregas


def construir_condicion(venta, pagos):
    es_credito = (venta.tipo_venta or '').strip().lower() == 'credito'
    if es_credito:
        return {
            'tipo': CONDICION_CREDITO,
            'credito': {
                'tipo': 1,
                'plazo': '30 días',
            },
        }
    return {
        'tipo': CONDICION_CONTADO,
        'entregas': construir_entregas(pagos, venta.total),
    }


def _item_iva(porcentaje_iva):
    pct = int(porcentaje_iva or 0)
    if pct in (5, 10):
        return {'ivaTipo': IVA_TIPO_GRAVADO, 'iva': pct, 'ivaProporcion': 100}
    return {'ivaTipo': IVA_TIPO_EXENTO, 'iva': 0, 'ivaProporcion': 0}


def _unidad_medida(item):
    if item is None:
        return UNIDAD_MEDIDA_DEFAULT
    clave = _normalizar_unidad(
        getattr(item, 'unidad_venta', None)
        or getattr(item, 'unidad_stock', None)
    )
    return UNIDAD_MEDIDA_POR_VENTA.get(clave, UNIDAD_MEDIDA_DEFAULT)


def _item_facturable(detalle):
    return getattr(detalle, 'producto', None) or getattr(detalle, 'servicio', None)


def construir_item(detalle):
    item_facturable = _item_facturable(detalle)
    cantidad = float(detalle.cantidad or 0)
    descuento_total = float(detalle.descuento_linea or 0)
    descuento_unitario = (descuento_total / cantidad) if cantidad else 0

    item = {
        'codigo': (
            (getattr(item_facturable, 'codigo', None) or '').strip()
            if item_facturable else str(
                getattr(detalle, 'id_producto', None) or getattr(detalle, 'id_servicio', '') or ''
            )
        ),
        'descripcion': (getattr(item_facturable, 'nombre', '') or '').strip() if item_facturable else '',
        'unidadMedida': _unidad_medida(item_facturable),
        'cantidad': cantidad,
        'precioUnitario': float(detalle.precio_unitario or 0),
        'cambio': 0,
        'descuento': round(descuento_unitario, 4),
        'anticipo': 0,
        'pais': PAIS_PY,
        'paisDescripcion': PAIS_PY_DESC,
    }
    item.update(_item_iva(detalle.porcentaje_iva))
    return item


def construir_items(detalles):
    return [construir_item(detalle) for detalle in detalles]


def construir_data_venta(venta, config, detalles=None, pagos=None, codigo_seguridad=None):
    detalles = detalles if detalles is not None else list(venta.detalles)
    pagos = pagos if pagos is not None else list(venta.pagos)
    fecha = venta.fecha_venta.strftime('%Y-%m-%dT%H:%M:%S') if venta.fecha_venta else None

    return {
        'tipoDocumento': TIPO_DOCUMENTO_FACTURA,
        'establecimiento': (config.establecimiento or '001').strip() or '001',
        'punto': (config.punto_expedicion or '001').strip() or '001',
        'numero': numero_documento(venta),
        'codigoSeguridadAleatorio': codigo_seguridad or generar_codigo_seguridad(),
        'descripcion': (venta.observaciones or '').strip() or None,
        'fecha': fecha,
        'tipoEmision': TIPO_EMISION_NORMAL,
        'tipoTransaccion': TIPO_TRANSACCION_VENTA,
        'tipoImpuesto': TIPO_IMPUESTO_IVA,
        'moneda': MONEDA_PYG,
        'factura': {'presencia': 1},
        'cliente': construir_cliente(venta.cliente),
        'condicion': construir_condicion(venta, pagos),
        'items': construir_items(detalles),
    }


__all__ = [
    'construir_data_venta',
    'construir_cliente',
    'construir_condicion',
    'construir_entregas',
    'construir_items',
    'construir_item',
    'numero_documento',
    'generar_codigo_seguridad',
]
