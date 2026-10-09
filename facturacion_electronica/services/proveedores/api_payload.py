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
    _total_item,
    construir_condicion,
    construir_entregas_con_origen,
    construir_items,
    redondeo_sedeco,
)
from facturacion_electronica.services.validacion import email_valido

MONEDA_PYG = 'PYG'

# Redondeo SEDECO (Res. 347/2014) en las facturas de la API, desde su 1.20.0.
# El motor propio ya lo aplicaba siempre (xmlgen, PYG). Apagarlo acá vuelve a
# declarar el total crudo, como hasta el 2026-09-29.
API_REDONDEO_SEDECO = True
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
NOMBRE_INNOMINADO = 'Sin Nombre'
# tdNombre: de 4 a 255 caracteres.
NOMBRE_RECEPTOR_MIN = 4

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
    nombre = (getattr(cliente, 'nombre', '') or '').strip() or NOMBRE_INNOMINADO

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
    }
    email = (getattr(cliente, 'email', '') or '').strip()
    if email_valido(email):
        # Opcional: un email mal cargado en la ficha ("no tiene", "juan@") la
        # API lo rechaza con 400 y la venta queda sin factura. Mejor sin email.
        receptor['email'] = email

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
    if innominado and len(receptor['name']) < NOMBRE_RECEPTOR_MIN:
        # tdNombre exige 4 caracteres y la API lo valida desde su 1.3.0. Al
        # innominado no se lo identifica por el nombre, así que va el literal
        # de SIFEN (D211) en vez de frenar la venta de "Ana" sin cédula.
        receptor['name'] = NOMBRE_INNOMINADO
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
            # Sin `unit_name`: desde la 1.8.0 la API arma dDesUniMed desde su
            # catálogo DNCP por `unit_code` y lo ignora. Un código que no esté
            # en ese catálogo es 400 `invalid_line`; los de UNIDAD_MEDIDA_POR_VENTA
            # (77, 83, 87, 89, 109) están todos.
            'unit_code': item['unidadMedida'],
            'quantity': _decimal(item['cantidad']),
            'unit_price': _decimal(precio_neto),
            'tax': {
                'affectation': item['ivaTipo'],
                'rate': int(item.get('iva') or 0),
            },
        })
    return lineas


def error_total_descuadrado(venta):
    """Error si los ítems de la venta suman menos de lo que la venta cobró.

    El descuento global se reparte sobre las líneas, pero un cobro **de más**
    (un recargo que no está en ningún ítem) no tiene dónde ir: la API no tiene
    líneas libres ni recargos globales, y las entregas cuadran contra el total,
    así que el alta rebotaba con `400 invalid_payment` y el número ya estaba
    reservado. Inventar una línea sería declarar algo que nadie cargó: se
    frena antes y se dice cuánto falta. Se tolera 1 Gs por línea, que es lo que
    puede perder el redondeo de cada una.
    """
    detalles = list(venta.detalles)
    objetivo = int(round(float(venta.total or 0)))
    if not detalles or objetivo <= 0:
        return None
    items = construir_items(detalles, total_objetivo=venta.total)
    suma = sum(_total_item(item) for item in items)
    faltante = objetivo - int(round(suma))
    if faltante <= len(items):
        return None
    return (
        f'La venta cobra {objetivo:,} Gs pero sus ítems suman {int(round(suma)):,} Gs: '
        f'hay {faltante:,} Gs que no están en ningún ítem y la factura no puede declararlos. '
        'Revisá la venta (un recargo tiene que cargarse como ítem).'
    ).replace(',', '.')


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


def aplica_redondeo_sedeco(total):
    """True si el documento sale con `sedeco_rounding` (API 1.20.0).

    Igual que el motor propio, donde xmlgen lo aplica siempre en PYG: el total
    general baja al múltiplo de 50 inferior y la diferencia va en `dRedon`.
    No aplica cuando el redondeo dejaría el total en cero (una venta de 30 Gs).
    """
    if not API_REDONDEO_SEDECO:
        return False
    total_redondeado, _redondeo = redondeo_sedeco(total)
    return total_redondeado > 0


def construir_pago(venta, pagos):
    """Condición y entregas, reusando el cuadre contra el total del motor propio.

    Con redondeo SEDECO las entregas cuadran contra el total **redondeado**: la
    API rechaza (`400`) un pago por el total sin redondear.
    """
    condicion = construir_condicion(venta, pagos)
    if condicion['tipo'] == CONDICION_CREDITO:
        # Sin `entries`: el crédito con entrega inicial la API lo rechaza, y
        # por eso la emisión de esa venta se corta antes (ver api.py).
        return _pago_a_credito(condicion)
    total = venta.total
    if aplica_redondeo_sedeco(total):
        total, _redondeo = redondeo_sedeco(total)
    entries = [
        _entrada_de_pago(entrega, pago)
        for entrega, pago in construir_entregas_con_origen(pagos, total)
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

    La factura que reemplaza a una cancelada lleva sufijo (`141-2`). La API
    reserva la referencia para todo documento no rechazado, cancelados
    incluidos, asi que volver a facturar con `141` daba `409
    external_ref_conflict` y dejaba el numero nuevo colgado. Un rechazado no
    abre fila nueva (se corrige con `correct/`), asi que las filas anteriores
    de la venta son justamente las que ocupan una referencia; la primera
    factura sigue siendo `141`, como las ya emitidas.

    La NC de anulación tiene el mismo caso: si la anterior se canceló, la
    nueva fila de la misma venta pedía otra vez `anulacion-141` y la API
    respondía el mismo 409. Lleva el sufijo con el mismo criterio.
    """
    if documento.tipo_documento == TIPO_NOTA_CREDITO:
        if documento.id_devolucion is None:
            base = f'anulacion-{documento.id_venta}'
            anteriores = _anteriores_de_la_venta(documento, _filtro_nc_anulacion())
            return base if not anteriores else f'{base}-{anteriores + 1}'
        return f'devolucion-{documento.id_devolucion}'
    anteriores = _anteriores_de_la_venta(documento, _filtro_factura())
    return str(documento.id_venta) if not anteriores else f'{documento.id_venta}-{anteriores + 1}'


def _filtro_factura():
    from app import db
    from facturacion_electronica import TIPO_FACTURA
    from facturacion_electronica.models import DocumentoElectronico

    # El tipo nulo es de los documentos viejos: son facturas.
    return db.or_(
        DocumentoElectronico.tipo_documento.is_(None),
        DocumentoElectronico.tipo_documento == TIPO_FACTURA,
    )


def _filtro_nc_anulacion():
    from app import db
    from facturacion_electronica.models import DocumentoElectronico

    return db.and_(
        DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO,
        DocumentoElectronico.id_devolucion.is_(None),
    )


def _anteriores_de_la_venta(documento, filtro):
    """Documentos de la misma venta y la misma clase dados de alta antes (menor id)."""
    from facturacion_electronica.models import DocumentoElectronico

    if getattr(documento, 'id', None) is None:
        return 0
    return DocumentoElectronico.query.filter(
        DocumentoElectronico.id_venta == documento.id_venta,
        filtro,
        DocumentoElectronico.id < documento.id,
    ).count()


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
    if aplica_redondeo_sedeco(venta.total):
        cuerpo['sedeco_rounding'] = True
    if fecha_local:
        # Con offset explicito ('...T14:30:00-03:00'). Sin el, la fecha queda a
        # merced del TIME_ZONE del servidor de ellos: hoy es America/Asuncion y
        # coincide, pero un cambio de su lado correria el dFeEmiDE tres horas
        # sin que nada lo avise. `utc_naive_to_local` ya devuelve un aware.
        cuerpo['issued_at'] = fecha_local.isoformat(timespec='seconds')
    return cuerpo


def construir_nota_credito_api(documento, documento_original, venta, lineas, timbrado_id,
                               receptor=None, redondear=False):
    """Cuerpo de `POST /sifen/electronic-documents/` con document_type 5.

    `associated` es lo que ata la NC a la factura que corrige: sin el CDC
    original, SIFEN no sabe qué documento se está acreditando. `credit_debit`
    lleva el motivo del catálogo (ver services/nota_credito.py).

    `receptor` es el que declaró la factura (ver `api_nota_credito`); la ficha
    del cliente queda sólo como respaldo para quien llame sin él.
    """
    cuerpo = {
        'stamp': timbrado_id,
        'document_type': TIPO_NOTA_CREDITO,
        'document_number': documento.numero,
        'receiver': receptor or construir_receptor(venta.cliente),
        'operation': {'currency': MONEDA_PYG, 'tax_type': TIPO_IMPUESTO_IVA},
        'lines': construir_lineas(lineas),
        # Asociado electrónico: sólo el CDC. Timbrado, establecimiento, punto,
        # número y fecha (dNTimDI, dEstDocAso, dPExpDocAso, dNumDocAso,
        # dFecEmiDI) son del documento **impreso** (iTipDocAso=2): informarlos
        # con un electrónico es rechazo `2419 Número de timbrado no requerido
        # para el tipo de documento asociado` (NC de la venta #123, 2026-09-29).
        # La API los pasa al XML tal cual lleguen, así que no hay que mandarlos.
        'associated': {
            'doc_type': 1,
            'doc_type_desc': 'Electrónico',
            'cdc': documento_original.cdc,
        },
        'credit_debit': {
            'motive': documento.nc_motivo,
            'motive_desc': documento.nc_motivo_desc,
        },
        'external_ref': referencia_externa(documento),
    }
    if redondear:
        # Sólo si la factura salió redondeada (lo decide `api_nota_credito`
        # leyendo su dRedon): la NC acredita el mismo total que se declaró.
        cuerpo['sedeco_rounding'] = True
    return cuerpo


__all__ = [
    'referencia_externa',
    'construir_emision_api',
    'construir_nota_credito_api',
    'construir_receptor',
    'construir_lineas',
    'construir_pago',
    'error_total_descuadrado',
]
