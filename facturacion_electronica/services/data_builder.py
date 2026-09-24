"""Construye el objeto 'data' de TIPS xmlgen a partir de una Venta del sistema.

Referencia: https://github.com/TIPS-SA/facturacionelectronicapy-xmlgen
Capa de mapeo sin red: lee la venta y la config del emisor y devuelve el dict.
El envío y la persistencia del documento se resuelven en fases posteriores.
"""
import re
import secrets

from app.utils.helpers import utc_naive_to_local
from app.utils.unidades_venta import normalizar_unidad_venta

TIPO_DOCUMENTO_FACTURA = 1
TIPO_DOCUMENTO_NOTA_CREDITO = 5
# H002 del documento asociado: 1 = electrónico (se identifica por su CDC).
FORMATO_ASOCIADO_ELECTRONICO = 1
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
#
# Los tres campos son obligatorios juntos, y omitir dos de ellos costó dos
# rechazos reales (`0160 XML malformado`, DE 0000013 y 0000014 del 2026-09-22):
#
# - `tipo` 99 es "Otro" en el catálogo de marcas (iDenTarj). Elegir 99 **obliga**
#   a informar `tipoDescripcion` (dDesDenTarj): xmlgen sólo completa la marca
#   sola cuando el tipo es una del catálogo, y con 99 escribe el elemento vacío.
#   SIFEN lo rechaza por tipo de dato, no por campo faltante, así que el mensaje
#   no nombra la causa. Tiene que medir entre 4 y 20 caracteres.
# - `medioPago` (iForProPa) lo escribe xmlgen **siempre**, venga o no: sin él
#   sale `<iForProPa/>` vacío y es el tercer rechazo. 1=POS, 2=pago electrónico,
#   9=otro. Un local con terminal es POS.
INFO_TARJETA_GENERICA = {
    'tipo': 99,
    'tipoDescripcion': 'Marca no registrada',
    'medioPago': 1,
}

# Los otros dos medios que piden su propio bloque, con la misma forma que la
# tarjeta: elegirlos sin completarlos deja la venta sin poder facturarse.
MEDIO_CHEQUE = 2
MEDIO_OTRO = 99
CHEQUE_DIGITOS = 8
# `dDesTiPag`, obligatorio con el medio 99.
DESCRIPCION_MEDIO_MIN = 4
DESCRIPCION_MEDIO_MAX = 30
DESCRIPCION_MEDIO_POR_DEFECTO = 'Otro medio de pago'


def _descripcion_medio(nombre):
    """`dDesTiPag` del medio 99. Entre 4 y 30 caracteres, o xmlgen no genera.

    Se usa el nombre del método tal como lo cargó el cliente: es el único dato
    que hay sobre cómo se cobró. Un nombre de menos de 4 caracteres ("QR") no
    lo acepta la librería, así que cae a un genérico antes que frenar la venta.
    """
    texto = (nombre or '').strip()[:DESCRIPCION_MEDIO_MAX]
    return texto if len(texto) >= DESCRIPCION_MEDIO_MIN else DESCRIPCION_MEDIO_POR_DEFECTO


def _info_cheque(pago):
    """`gPagCheq`, o None si el pago no trae con qué llenarlo.

    El número sale de la referencia del pago (el método "Cheque" se carga con
    `requiere_referencia`) y el banco, del banco del pago. Los dos son
    obligatorios y no hay de dónde inventarlos; sin ellos la entrega se declara
    como "otro medio", que es preferible a no poder emitir. Mismo criterio que
    `api_payload._cheque`.
    """
    numero = _solo_digitos(getattr(pago, 'referencia', ''))[-CHEQUE_DIGITOS:]
    banco = (getattr(getattr(pago, 'banco', None), 'nombre', '') or '').strip()
    if not numero or len(banco) < DESCRIPCION_MEDIO_MIN:
        return None
    return {'numeroCheque': numero.zfill(CHEQUE_DIGITOS), 'banco': banco[:20]}


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


def fecha_firma_digital():
    """`dFecFirma`: hora de Paraguay, sin offset.

    Si no se la mandamos, `xmlgen` la arma con `new Date()` y la formatea con
    `getHours()`, o sea con la zona horaria **del proceso Node**, y la escribe
    sin offset. En un servidor en UTC eso son tres horas en el futuro dentro
    de un documento firmado. Va explícita por la misma razón que `dFeEmiDE`:
    la hora del DE la decide la aplicación, no el reloj de quien lo arma.
    """
    from app.utils.helpers import now_local

    return now_local().strftime('%Y-%m-%dT%H:%M:%S')


def _solo_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def _tipo_contribuyente_receptor(ruc):
    """iTiContRec del receptor: los RUC de personas jurídicas empiezan con 80;
    los de personas físicas son su número de cédula."""
    return 2 if _solo_digitos(ruc).startswith('80') else 1


# Redondeo SEDECO: en guaraníes el total del documento baja al múltiplo de 50
# más cercano hacia abajo, y la diferencia se declara aparte (dRedon). No es
# una opción nuestra: `xmlgen` lo aplica siempre en PYG (`redondeoSedeco: true`)
# y nos enteramos del resultado recién en el XML. Se replica acá para que las
# entregas de pago y el KuDE digan lo mismo que el documento: si el pago suma
# el total sin redondear, el DE se contradice a sí mismo.
UNIDAD_REDONDEO_SEDECO = 50


def redondeo_sedeco(total):
    """(total_redondeado, redondeo) en guaraníes. El redondeo nunca sube."""
    try:
        entero = int(round(float(total or 0)))
    except (TypeError, ValueError):
        return 0, 0
    redondeo = entero % UNIDAD_REDONDEO_SEDECO
    return entero - redondeo, redondeo


def _direccion_receptor(cliente):
    """Bloque de domicilio del receptor: completo o nada.

    Para SIFEN la dirección del receptor es opcional, pero **si se informa**
    pasan a ser obligatorios el número de casa y los códigos oficiales de
    departamento, distrito y ciudad (salvo en exportación, tipoOperacion 4).
    La ficha de cliente guarda una dirección de texto libre y ninguno de esos
    códigos, así que mandarla sola hacía fallar la generación del XML con
    cuatro errores de golpe y la venta se quedaba sin factura.

    Se lee con `getattr` a propósito: el día que la ficha de cliente guarde
    los códigos, el domicilio empieza a viajar sin tocar esta función.
    """
    direccion = (getattr(cliente, 'direccion', '') or '').strip()
    numero_casa = str(getattr(cliente, 'numero_casa', '') or '').strip()
    departamento = getattr(cliente, 'departamento_codigo', None)
    distrito = getattr(cliente, 'distrito_codigo', None)
    ciudad = getattr(cliente, 'ciudad_codigo', None)
    if not (direccion and numero_casa and departamento and distrito and ciudad):
        return {}

    from facturacion_electronica.services import geo

    return {
        'direccion': direccion,
        'numeroCasa': numero_casa,
        'departamento': int(departamento),
        'departamentoDescripcion': geo.descripcion_departamento(departamento),
        'distrito': int(distrito),
        'distritoDescripcion': geo.descripcion_distrito(distrito),
        'ciudad': int(ciudad),
        'ciudadDescripcion': geo.descripcion_ciudad(ciudad),
    }


def receptor_innominado(cliente):
    """True si el receptor va a viajar sin identificar (iTipIDRec 5, número 0).

    Vive acá y no dentro de `construir_cliente` porque hay una guarda fiscal
    que necesita la misma respuesta **antes** de emitir: SIFEN acepta facturar
    a un receptor innominado, pero rechaza acreditarle con una nota de crédito
    (`El adquiriente del comprobante de venta informado no se encuentra
    identificado`). Si la guarda decidiera por su cuenta, las dos respuestas se
    desincronizarían y volveríamos a emitir una NC condenada al rechazo.
    """
    if cliente is None:
        return True
    ruc_ci = (getattr(cliente, 'ruc_ci', '') or '').strip()
    if getattr(cliente, 'id_cliente', None) == 1 or not ruc_ci:
        return True
    if '-' in ruc_ci:
        return False
    documento = _solo_digitos(ruc_ci)
    return not documento or set(documento) == {'0'}


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
        'codigo': str(cliente.id_cliente).zfill(3),
    }
    base.update(_direccion_receptor(cliente))

    if not es_consumidor_final and '-' in ruc_ci:
        base.update({
            'contribuyente': True,
            'ruc': ruc_ci,
            'tipoOperacion': 1,
            'tipoContribuyente': _tipo_contribuyente_receptor(ruc_ci),
        })
    else:
        documento = _solo_digitos(ruc_ci)
        if receptor_innominado(cliente):
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
    return [entrega for entrega, _origen in construir_entregas_con_origen(pagos, total)]


def construir_entregas_con_origen(pagos, total):
    """Las entregas de contado, cada una junto al pago del que salió.

    El dialecto de xmlgen no lleva los datos de la tarjeta ni del cheque, pero
    la API sí los exige, y ésos están en el pago (su referencia y su banco), no
    en la entrega. Para no repartir el cuadre contra el total en dos lugares,
    el origen viaja al lado de la entrega y cada formato toma lo que necesita.
    La entrega de relleno (una venta sin pagos registrados) no tiene origen.
    """
    total = int(round(float(total or 0)))
    entregas = []
    for pago in pagos:
        metodo = getattr(pago, 'metodo', None)
        nombre = metodo.nombre if metodo else ''
        tipo, info = _tipo_pago(nombre)
        if tipo is None:
            continue
        entrega = {
            'tipo': tipo,
            'monto': str(int(round(float(pago.monto or 0)))),
            'moneda': MONEDA_PYG,
            'cambio': 0,
        }
        if info:
            # Copia: la constante es compartida por todas las entregas de todas
            # las ventas, y una mutación a través de una entrega las pisaría.
            entrega['infoTarjeta'] = dict(info)
        if entrega['tipo'] == MEDIO_CHEQUE:
            cheque = _info_cheque(pago)
            if cheque:
                entrega['infoCheque'] = cheque
            else:
                # Sin número ni banco, xmlgen no genera el documento. Cobrar en
                # cheque no puede dejar una venta sin poder facturarse.
                entrega['tipo'] = MEDIO_OTRO
        if entrega['tipo'] == MEDIO_OTRO:
            entrega['tipoDescripcion'] = _descripcion_medio(nombre)
        entregas.append((entrega, pago))
    if not entregas:
        return [({'tipo': 1, 'monto': str(total), 'moneda': MONEDA_PYG, 'cambio': 0}, None)]
    # SIFEN exige que la suma de las entregas iguale el total en condición
    # contado. Métodos omitidos (ej. crédito tienda) o redondeos a guaraní
    # pueden descuadrar; se ajusta la última entrega para cerrar el total.
    suma = sum(int(e['monto']) for e, _origen in entregas)
    diferencia = total - suma
    if diferencia:
        entregas[-1][0]['monto'] = str(int(entregas[-1][0]['monto']) + diferencia)
    return entregas


def _plazo_credito_dias(venta):
    """Días de plazo entre la venta y su vencimiento (venta.cuenta_por_cobrar).
    30 si no hay cuenta por cobrar o vencimiento cargado."""
    cuenta = getattr(venta, 'cuenta_por_cobrar', None)
    fecha_venc = getattr(cuenta, 'fecha_vencimiento', None) if cuenta else None
    fecha_venta = getattr(venta, 'fecha_venta', None)
    if not fecha_venc or not fecha_venta:
        return 30
    dias = (fecha_venc - fecha_venta.date()).days
    return dias if dias > 0 else 30


def construir_condicion(venta, pagos):
    es_credito = (venta.tipo_venta or '').strip().lower() == 'credito'
    if es_credito:
        return {
            'tipo': CONDICION_CREDITO,
            'credito': {
                'tipo': 1,
                'plazo': f'{_plazo_credito_dias(venta)} días',
            },
        }
    # Las entregas cuadran contra el total **redondeado**, que es el que el
    # documento declara en dTotGralOpe. Contra el total crudo, el DE dice que
    # se pagó una cifra distinta de su propio total.
    total_redondeado, _redondeo = redondeo_sedeco(venta.total)
    return {
        'tipo': CONDICION_CONTADO,
        'entregas': construir_entregas(pagos, total_redondeado),
    }


def _item_iva(porcentaje_iva):
    pct = int(porcentaje_iva or 0)
    if pct in (5, 10):
        return {'ivaTipo': IVA_TIPO_GRAVADO, 'iva': pct, 'ivaProporcion': 100}
    return {'ivaTipo': IVA_TIPO_EXENTO, 'iva': 0, 'ivaProporcion': 0}


def _unidad_medida(producto):
    if producto is None:
        return UNIDAD_MEDIDA_DEFAULT
    clave = normalizar_unidad_venta(getattr(producto, 'unidad_venta', None))
    return UNIDAD_MEDIDA_POR_VENTA.get(clave, UNIDAD_MEDIDA_DEFAULT)


def _codigo_y_descripcion(detalle, producto):
    """[servicios] Los platos de gastronomía y los servicios se venden como
    `Servicio`, sin producto: el ítem toma código y nombre de ahí."""
    if producto is not None:
        return (producto.codigo or '').strip(), (producto.nombre or '').strip()
    servicio = getattr(detalle, 'servicio', None)
    if servicio is not None:
        codigo = (servicio.codigo or '').strip() or f'SRV-{servicio.id_servicio}'
        return codigo, (servicio.nombre or '').strip()
    return str(detalle.id_producto), ''


def _descuento_unitario(detalle, cantidad):
    """[servicios] La línea declara lo que dice su `subtotal`.

    El POS y la caja gastronómica guardan `precio_unitario` ya con la promoción
    aplicada y además el descuento en `descuento_linea` (informativo, para
    reportes). Restarlo otra vez declaraba menos de lo cobrado. Sin `subtotal`
    (líneas livianas de la nota de crédito) se usa `descuento_linea`.
    """
    if not cantidad:
        return 0
    subtotal = getattr(detalle, 'subtotal', None)
    if subtotal is None:
        return float(detalle.descuento_linea or 0) / cantidad
    return max(float(detalle.precio_unitario or 0) - float(subtotal) / cantidad, 0)


def construir_item(detalle):
    producto = detalle.producto
    codigo, descripcion = _codigo_y_descripcion(detalle, producto)
    cantidad = float(detalle.cantidad or 0)
    descuento_unitario = _descuento_unitario(detalle, cantidad)

    item = {
        'codigo': codigo,
        'descripcion': descripcion,
        'unidadMedida': _unidad_medida(producto),
        'cantidad': cantidad,
        'precioUnitario': float(detalle.precio_unitario or 0),
        'cambio': 0,
        # 8 decimales para que (precio - descuento) * cantidad reconstruya el
        # subtotal sin desviarse del total de la venta al redondear a guaraníes.
        'descuento': round(descuento_unitario, 8),
        'anticipo': 0,
        'pais': PAIS_PY,
        'paisDescripcion': PAIS_PY_DESC,
    }
    item.update(_item_iva(detalle.porcentaje_iva))
    return item


def _total_item(item):
    return float(item['cantidad'] or 0) * (
        float(item['precioUnitario'] or 0) - float(item['descuento'] or 0)
    )


def _prorratear_descuento_global(items, total_objetivo):
    """Baja las líneas hasta que sumen exactamente lo que la venta cobró.

    El descuento global de la venta (`descuento_monto`: el manual más el de
    fidelización) no está en ninguna línea — los detalles guardan el precio sin
    él —, así que declarar las líneas tal cual emite un documento por más plata
    de la que se cobró y por un IVA que nadie pagó. Descuentos globales no hay
    dónde ponerlos: la API los rechaza y desde su versión 1.1.0 además exige
    que las entregas de pago sumen **exacto** el total del documento
    (`invalid_payment`). El único lugar donde el descuento entra es el precio
    de cada línea, repartido en proporción a lo que pesa.

    Cada línea queda en un importe entero de guaraníes y la suma da el total
    exacto: el guaraní suelto del reparto va a las líneas que más fracción
    perdieron al redondear.
    """
    objetivo = int(round(float(total_objetivo or 0)))
    brutos = [_total_item(item) for item in items]
    bruto = sum(brutos)
    if objetivo <= 0 or bruto <= 0 or int(round(bruto)) <= objetivo:
        return items

    factor = objetivo / bruto
    asignados = [int((bruto_item * factor) // 1) for bruto_item in brutos]
    sobrante = objetivo - sum(asignados)
    if sobrante > 0:
        orden = sorted(
            range(len(items)),
            key=lambda i: brutos[i] * factor - asignados[i],
            reverse=True,
        )
        for indice in orden[:sobrante]:
            asignados[indice] += 1

    for item, asignado in zip(items, asignados):
        cantidad = float(item['cantidad'] or 0)
        if cantidad <= 0:
            continue
        # 8 decimales, igual que el descuento de línea: es lo que permite que
        # cantidad × (precio - descuento) reconstruya el importe asignado.
        item['descuento'] = round(float(item['precioUnitario'] or 0) - asignado / cantidad, 8)
    return items


def construir_items(detalles, total_objetivo=None):
    """Los ítems del documento. Con `total_objetivo` se prorratea el descuento
    global de la venta sobre las líneas (ver `_prorratear_descuento_global`)."""
    items = [construir_item(detalle) for detalle in detalles]
    if total_objetivo is None:
        return items
    return _prorratear_descuento_global(items, total_objetivo)


def construir_data_venta(venta, config, detalles=None, pagos=None, codigo_seguridad=None, numero=None):
    detalles = detalles if detalles is not None else list(venta.detalles)
    pagos = pagos if pagos is not None else list(venta.pagos)
    # venta.fecha_venta se guarda en UTC; SIFEN exige la hora local de Paraguay
    # (dFeEmiDE) y rechaza fechas de emisión futuras, así que hay que convertir
    # antes de formatear.
    fecha_local = utc_naive_to_local(venta.fecha_venta) if venta.fecha_venta else None
    fecha = fecha_local.strftime('%Y-%m-%dT%H:%M:%S') if fecha_local else None

    return {
        'tipoDocumento': TIPO_DOCUMENTO_FACTURA,
        'fechaFirmaDigital': fecha_firma_digital(),
        'establecimiento': (config.establecimiento or '001').strip() or '001',
        'punto': (config.punto_expedicion or '001').strip() or '001',
        'numero': numero or '0000000',
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
        'items': construir_items(detalles, total_objetivo=venta.total),
    }


def construir_data_nota_credito(devolucion, config, original, motivo, venta=None,
                                lineas=None, codigo_seguridad=None, numero=None, fecha=None):
    """El `data` de una nota de crédito electrónica (iTiDE 5).

    Tres diferencias con la factura, y las tres son del estándar, no nuestras:

    - **No lleva condición de la operación.** La NC no cobra: acredita. xmlgen
      sólo valida `condicion` para los tipos 1 y 4, y mandarla igual sería
      declarar entregas de pago que no existieron.
    - **Lleva `gCamNCDE`** con el motivo, y el texto tiene que salir del
      catálogo TdDesMotEmi (lo resuelve `nota_credito.motivo_o_defecto`).
    - **Lleva `gCamDEAsoc`** con el CDC de la factura que corrige. Sin eso
      SIFEN no sabe qué documento se está acreditando y rechaza el DE.

    La fecha es la de **emisión de la NC**, no la de la venta: la factura pudo
    haberse emitido hace meses y SIFEN rechaza fechas futuras, no pasadas.
    """
    from facturacion_electronica.services.nota_credito import (
        lineas_de_devolucion,
        motivo_o_defecto,
    )

    venta = venta if venta is not None else original.venta
    lineas = lineas if lineas is not None else lineas_de_devolucion(devolucion)
    codigo_motivo, _descripcion = motivo_o_defecto(motivo)

    fecha_local = utc_naive_to_local(fecha) if fecha else None
    fecha_texto = fecha_local.strftime('%Y-%m-%dT%H:%M:%S') if fecha_local else None

    return {
        'tipoDocumento': TIPO_DOCUMENTO_NOTA_CREDITO,
        'fechaFirmaDigital': fecha_firma_digital(),
        'establecimiento': (config.establecimiento or '001').strip() or '001',
        'punto': (config.punto_expedicion or '001').strip() or '001',
        'numero': numero or '0000000',
        'codigoSeguridadAleatorio': codigo_seguridad or generar_codigo_seguridad(),
        'descripcion': (getattr(devolucion, 'motivo', '') or '').strip() or None,
        'fecha': fecha_texto,
        'tipoEmision': TIPO_EMISION_NORMAL,
        'tipoTransaccion': TIPO_TRANSACCION_VENTA,
        'tipoImpuesto': TIPO_IMPUESTO_IVA,
        'moneda': MONEDA_PYG,
        'cliente': construir_cliente(venta.cliente),
        'notaCreditoDebito': {'motivo': codigo_motivo},
        'documentoAsociado': {
            'formato': FORMATO_ASOCIADO_ELECTRONICO,
            'cdc': original.cdc,
        },
        # Sin `total_objetivo`: las líneas ya vienen con el precio que la
        # factura cobró (ver `nota_credito.lineas_de_devolucion`). Prorratear
        # de nuevo bajaría el crédito por un descuento que ya está adentro.
        'items': construir_items(lineas),
    }


__all__ = [
    'construir_data_venta',
    'fecha_firma_digital',
    'construir_data_nota_credito',
    'construir_cliente',
    'construir_condicion',
    'construir_entregas',
    'construir_entregas_con_origen',
    'construir_items',
    'construir_item',
    'generar_codigo_seguridad',
]
