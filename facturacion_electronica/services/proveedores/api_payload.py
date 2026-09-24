"""Traduce una Venta al cuerpo `EmitDocumentRequest` de la API externa.

Se apoya en `data_builder` para el mapeo fiscal (cliente, IVA, formas de pago,
cuadre de las entregas contra el total) y sólo cambia la **forma**: el motor
propio habla el dialecto de TIPS xmlgen y la API habla el suyo. Las reglas
fiscales viven en un solo lugar; acá no se decide nada nuevo.

Lo que NO va en el cuerpo: los datos del emisor, el timbrado y el certificado.
La API los deriva del token (`GET /sifen/me/`). Lo que SÍ sigue siendo nuestro:
el **número** del documento (`document_number`), porque la API lo exige en el
alta — ver `plan_switch_FE.md`.
"""
import re

from app.utils.helpers import utc_naive_to_local
from facturacion_electronica import TIPO_NOTA_CREDITO
from facturacion_electronica.services.data_builder import (
    CONDICION_CREDITO,
    TIPO_DOCUMENTO_FACTURA,
    _descripcion_medio,
    construir_condicion,
    construir_entregas_con_origen,
    construir_items,
)
from facturacion_electronica.services.emision_service import fecha_emision

MONEDA_PYG = 'PYG'
PAIS_PY = 'PRY'
PAIS_PY_DESC = 'Paraguay'

# iTImp: 1 = IVA.
TIPO_IMPUESTO_IVA = 1

# iNatRec del receptor.
NATURALEZA_CONTRIBUYENTE = 1
NATURALEZA_NO_CONTRIBUYENTE = 2

# iTiOpe: 1 = B2B, 2 = B2C.
OPERACION_B2B = 1
OPERACION_B2C = 2

DOCUMENTO_TIPO_CEDULA = 1
DOCUMENTO_TIPO_INNOMINADO = 5

# Medios de pago (iTiPago) que la API valida distinto a partir de su 1.1.0:
# el cheque y la tarjeta traen su propio bloque obligatorio, y el 99 ("otro")
# exige la descripción del medio. Ver el changelog de la API, versión 1.1.0.
MEDIO_CHEQUE = 2
MEDIOS_TARJETA = (3, 4)
MEDIO_OTRO = 99

# El POS no guarda la marca de la tarjeta (el voucher queda en el comercio),
# así que va la genérica del catálogo con su descripción, igual que el motor
# propio (data_builder.INFO_TARJETA_GENERICA). Procesamiento: 1 = POS.
TARJETA_MARCA_OTRA = 99
TARJETA_PROCESAMIENTO_POS = 1
# dDesDenTarj libre (marca 99): el XSD oficial (tdDesDenTarj) exige de 4 a 20
# caracteres. La API acepta hasta 100 en el borde, pero valida el XML contra el
# XSD antes de transmitir: un nombre de método largo ("Tarjeta de Crédito
# Bancard") pasa el serializer y revienta después, con la venta sin facturar.
TARJETA_DESC_MIN = 4
TARJETA_DESC_MAX = 20
TARJETA_DESC_POR_DEFECTO = 'Marca no registrada'

# dNumCheq: exactamente 8 dígitos, y la API no rellena por nosotros.
CHEQUE_DIGITOS = 8
# El banco del cheque es un string de 4 a 20 caracteres.
CHEQUE_BANCO_MIN = 4
CHEQUE_BANCO_MAX = 20

# dPlazoCre: texto libre de 2 a 15 caracteres.
PLAZO_MAX = 15
PLAZO_DEFAULT = '30 dias'

# Nombre corto de la unidad (dDesUniMed, máximo 4 caracteres) por código DNCP.
NOMBRE_UNIDAD = {77: 'UNI', 83: 'kg', 87: 'm', 89: 'l', 109: 'm2'}
NOMBRE_UNIDAD_DEFAULT = 'UNI'


def _solo_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def _decimal(valor, decimales=8):
    """Número como texto, sin notación científica ni ceros de relleno.

    Los campos decimales de la API son strings con un patrón acotado; mandar
    un float de Python arriesga un `1e-05` que no matchea el patrón.
    """
    texto = f'{float(valor or 0):.{decimales}f}'
    if '.' in texto:
        texto = texto.rstrip('0').rstrip('.')
    return texto or '0'


def _entero(valor):
    return str(int(round(float(valor or 0))))


def construir_receptor(cliente):
    """gDatRec: mismo criterio que el motor propio (ver data_builder.construir_cliente)."""
    ruc_ci = (getattr(cliente, 'ruc_ci', '') or '').strip()
    es_consumidor_final = getattr(cliente, 'id_cliente', None) == 1 or not ruc_ci
    nombre = (getattr(cliente, 'nombre', '') or '').strip() or 'Sin Nombre'

    # Sin `address` a propósito: SIFEN exige, junto con la dirección del
    # receptor, el número de casa y los códigos de departamento, distrito y
    # ciudad (salvo exportación). La ficha de cliente sólo tiene una dirección
    # de texto libre, y mandarla sola es lo que hace fallar la validación del
    # XML — ver `data_builder._direccion_receptor`. Cuando la ficha guarde esos
    # códigos hay que mapear el bloque completo contra el OpenAPI del
    # proveedor, sin inventar nombres de campo.
    receptor = {
        'name': nombre[:255],
        'country_code': PAIS_PY,
        'country_name': PAIS_PY_DESC,
        'email': (getattr(cliente, 'email', '') or '').strip() or None,
    }

    if not es_consumidor_final and '-' in ruc_ci:
        raiz, _sep, dv = ruc_ci.partition('-')
        raiz = _solo_digitos(raiz)
        try:
            dv_numero = int(_solo_digitos(dv) or 0)
        except ValueError:
            dv_numero = 0
        receptor.update({
            'nature': NATURALEZA_CONTRIBUYENTE,
            'operation_type': OPERACION_B2B,
            # iTiContRec: los RUC de personas jurídicas empiezan con 80.
            'contributor_type': 2 if raiz.startswith('80') else 1,
            'ruc': raiz[:8],
            'dv': dv_numero,
        })
        return receptor

    documento = _solo_digitos(ruc_ci)
    innominado = es_consumidor_final or not documento or set(documento) == {'0'}
    receptor.update({
        'nature': NATURALEZA_NO_CONTRIBUYENTE,
        'operation_type': OPERACION_B2C,
        'id_type': DOCUMENTO_TIPO_INNOMINADO if innominado else DOCUMENTO_TIPO_CEDULA,
        'id_number': '0' if innominado else documento[:20],
    })
    return receptor


def construir_lineas(detalles, total_objetivo=None):
    """Ítems en el formato de la API.

    La API no tiene descuentos, ni por línea ni globales: todo descuento se
    descuenta del precio (con los 8 decimales que ya usa el motor propio) para
    que cantidad × precio reconstruya lo que la venta cobró. `total_objetivo`
    es el total de la venta, y con él `construir_items` reparte además el
    descuento global sobre las líneas — sin eso el documento sale por más plata
    de la que se cobró y las entregas de pago no cuadran contra el total, que
    es justo lo que la API rechaza desde su 1.1.0 (`invalid_payment`).
    """
    lineas = []
    for indice, item in enumerate(construir_items(detalles, total_objetivo), start=1):
        precio_neto = float(item['precioUnitario'] or 0) - float(item.get('descuento') or 0)
        codigo = (item.get('codigo') or '').strip() or f'ITEM{indice}'
        lineas.append({
            'internal_code': codigo[:50],
            'description': ((item.get('descripcion') or '').strip() or codigo)[:500],
            'unit_code': item['unidadMedida'],
            'unit_name': NOMBRE_UNIDAD.get(item['unidadMedida'], NOMBRE_UNIDAD_DEFAULT),
            'quantity': _decimal(item['cantidad']),
            'unit_price': _decimal(precio_neto),
            'tax': {
                'affectation': item['ivaTipo'],
                'rate': int(item.get('iva') or 0),
            },
        })
    return lineas


def _nombre_metodo(pago):
    metodo = getattr(pago, 'metodo', None)
    return (getattr(metodo, 'nombre', '') or '').strip()


def _descripcion_tarjeta(nombre_metodo):
    """`brand_description` dentro del rango del XSD (4 a 20 caracteres)."""
    texto = (nombre_metodo or '').strip()[:TARJETA_DESC_MAX]
    return texto if len(texto) >= TARJETA_DESC_MIN else TARJETA_DESC_POR_DEFECTO


def _tarjeta(nombre_metodo):
    """gPagTarCD. Obligatorio cuando el medio es 3 (crédito) o 4 (débito).

    De la tarjeta el sistema sabe lo que el POS le dejó: qué método de pago
    eligió el cajero. La marca no se pregunta, así que va la genérica (99) con
    el nombre del método como descripción — inventar "Visa" sería declarar un
    dato que nadie cargó.
    """
    return {
        'brand': TARJETA_MARCA_OTRA,
        'brand_description': _descripcion_tarjeta(nombre_metodo),
        'processing': TARJETA_PROCESAMIENTO_POS,
    }


def _cheque(pago):
    """gPagCheq, o None si el pago no trae con qué llenarlo.

    El número sale de la referencia del pago (el método "Cheque" se carga con
    `requiere_referencia`) y el banco del banco del pago. Los dos campos son
    obligatorios del lado de la API y no hay de dónde inventarlos: sin ellos la
    entrega se declara como "otro medio", que es preferible a no emitir.
    """
    numero = _solo_digitos(getattr(pago, 'referencia', ''))[-CHEQUE_DIGITOS:]
    banco = (getattr(getattr(pago, 'banco', None), 'nombre', '') or '').strip()
    if not numero or len(banco) < CHEQUE_BANCO_MIN:
        return None
    return {'number': numero.zfill(CHEQUE_DIGITOS), 'bank': banco[:CHEQUE_BANCO_MAX]}


def _entrada_de_pago(entrega, pago):
    """Una entrega de contado en el formato de la API, con su bloque obligatorio."""
    entrada = {
        'means': entrega['tipo'],
        'amount': _entero(entrega['monto']),
        'currency': entrega.get('moneda') or MONEDA_PYG,
    }
    nombre = _nombre_metodo(pago)

    if entrada['means'] in MEDIOS_TARJETA:
        entrada['card'] = _tarjeta(nombre)
    elif entrada['means'] == MEDIO_CHEQUE:
        cheque = _cheque(pago)
        if cheque:
            entrada['cheque'] = cheque
        else:
            entrada['means'] = MEDIO_OTRO
            entrada['means_description'] = _descripcion_medio(nombre or 'Cheque')

    if entrada['means'] == MEDIO_OTRO and not entrada.get('means_description'):
        # dDesTiPag es obligatorio con medio 99 y prohibido en cualquier otro.
        entrada['means_description'] = _descripcion_medio(nombre)
    return entrada


def _pago_a_credito(condicion):
    """gPagCred a plazo simple.

    En cuotas no se manda aunque el sistema tenga plan de cobranzas: la API
    exige que las cuotas sumen exacto el total del documento y el plan se arma
    después de la venta, con intereses que no están en la factura.
    """
    plazo = ((condicion.get('credito') or {}).get('plazo') or '').strip()[:PLAZO_MAX]
    return {
        'condition': 'credito',
        'credit_type': 'plazo',
        'term': plazo if len(plazo) >= 2 else PLAZO_DEFAULT,
    }


def construir_pago(venta, pagos):
    """Condición y entregas, reusando el cuadre contra el total del motor propio."""
    condicion = construir_condicion(venta, pagos)
    if condicion['tipo'] == CONDICION_CREDITO:
        # Sin `entries`: el crédito con entrega inicial la API lo rechaza, y
        # por eso la emisión de esa venta se corta antes (ver api.py).
        return _pago_a_credito(condicion)
    entries = [
        _entrada_de_pago(entrega, pago)
        for entrega, pago in construir_entregas_con_origen(pagos, venta.total)
    ]
    return {'condition': 'contado', 'entries': entries}


def referencia_externa(documento):
    """`external_ref` del documento en la API: el unico lugar donde se decide.

    La factura se referencia por su venta y la nota de credito por su
    devolucion. Tiene que salir de aca tambien cuando se lo **busca** del otro
    lado (recuperacion de un alta cuya respuesta se perdio): si el alta manda
    una referencia y la busqueda filtra por otra, el documento existe en la API
    y nosotros lo damos por no emitido.

    La NC de anulacion no tiene devolucion detras, asi que lleva su propio
    prefijo: sin esto se referenciaba `devolucion-None`, y todas las NC de
    anulacion de todos los clientes compartian la misma referencia.
    """
    if documento.tipo_documento == TIPO_NOTA_CREDITO:
        if documento.id_devolucion is None:
            return f'anulacion-{documento.id_venta}'
        return f'devolucion-{documento.id_devolucion}'
    return str(documento.id_venta)


def construir_emision_api(venta, documento, timbrado_id, detalles=None, pagos=None):
    """Cuerpo de `POST /sifen/electronic-documents/`."""
    detalles = detalles if detalles is not None else list(venta.detalles)
    pagos = pagos if pagos is not None else list(venta.pagos)

    # La venta se guarda en UTC y SIFEN cuenta en hora local de Paraguay; el
    # mismo cuidado que en data_builder (un DE con fecha futura se rechaza).
    fecha_local = utc_naive_to_local(venta.fecha_venta) if venta.fecha_venta else None

    cuerpo = {
        'stamp': timbrado_id,
        'document_type': TIPO_DOCUMENTO_FACTURA,
        'document_number': documento.numero,
        'receiver': construir_receptor(venta.cliente),
        'operation': {'currency': MONEDA_PYG, 'tax_type': TIPO_IMPUESTO_IVA},
        'lines': construir_lineas(detalles, total_objetivo=venta.total),
        'payment': construir_pago(venta, pagos),
        'external_ref': referencia_externa(documento),
    }
    if fecha_local:
        # Con offset explicito ('...T14:30:00-03:00'). Sin el, la fecha queda a
        # merced del TIME_ZONE del servidor de ellos: hoy es America/Asuncion y
        # coincide, pero un cambio de su lado correria el dFeEmiDE tres horas
        # sin que nada lo avise. `utc_naive_to_local` ya devuelve un aware.
        cuerpo['issued_at'] = fecha_local.isoformat(timespec='seconds')
    return cuerpo


def construir_nota_credito_api(documento, documento_original, venta, lineas, timbrado_id):
    """Cuerpo de `POST /sifen/electronic-documents/` con document_type 5.

    `associated` es lo que ata la NC a la factura que corrige: sin el CDC
    original, SIFEN no sabe qué documento se está acreditando. `credit_debit`
    lleva el motivo del catálogo (ver services/nota_credito.py).
    """
    cuerpo = {
        'stamp': timbrado_id,
        'document_type': TIPO_NOTA_CREDITO,
        'document_number': documento.numero,
        'receiver': construir_receptor(venta.cliente),
        'operation': {'currency': MONEDA_PYG, 'tax_type': TIPO_IMPUESTO_IVA},
        'lines': construir_lineas(lineas),
        'associated': {
            'doc_type': 1,
            'doc_type_desc': 'Electrónico',
            'cdc': documento_original.cdc,
            'stamp_number': documento_original.timbrado or None,
            'establishment': documento_original.establecimiento or None,
            'expedition_point': documento_original.punto or None,
            'document_number': documento_original.numero or None,
        },
        'credit_debit': {
            'motive': documento.nc_motivo,
            'motive_desc': documento.nc_motivo_desc,
        },
        'external_ref': referencia_externa(documento),
    }
    # `dFeEmiDoAso` tiene que ser **el mismo dFeEmiDE que se declaró en la
    # factura**, y ése salió de la fecha de la venta (`fecha_emision`), no de
    # cuándo se armó el documento: una venta de las 23:50 cuya emisión la
    # reintentó el job a las 00:05 tiene `fecha_generado` de otro día, y la NC
    # declararía del documento original una fecha que SIFEN no tiene.
    #
    # Misma conversión que `issued_at`: la fecha se guarda en UTC y SIFEN
    # cuenta en hora local de Paraguay.
    fecha_original = fecha_emision(documento_original)
    if fecha_original:
        cuerpo['associated']['issue_date'] = (
            utc_naive_to_local(fecha_original).strftime('%Y-%m-%d')
        )
    return cuerpo


__all__ = [
    'referencia_externa',
    'construir_emision_api',
    'construir_nota_credito_api',
    'construir_receptor',
    'construir_lineas',
    'construir_pago',
]
