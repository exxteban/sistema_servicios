"""Genera y persiste los documentos electrónicos: factura y nota de crédito.

Esta fase arma el XML (vía el microservicio TIPS) y lo guarda con su CDC y
estado. NO firma ni envía: eso requiere el certificado y se agrega después.
El código de seguridad se genera una sola vez y se reutiliza, para que el CDC
del documento sea estable entre regeneraciones.

La nota de crédito (`generar_nota_credito`) comparte todo lo de abajo —firma,
QR, envío, consulta— y se diferencia sólo en cómo se arma su `data` y en que
lleva su propio correlativo dentro del mismo timbrado.
"""
import json
import re
from datetime import datetime, timedelta
from types import SimpleNamespace

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    CSC_DEMO,
    CSC_DEMO_ID,
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_INUTILIZADO,
    ESTADO_RECHAZADO,
    ESTADOS_NO_REGENERABLES,
    ESTADOS_TRANSMITIDOS,
    SIN_REINTENTO,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.crypto import descifrar
from facturacion_electronica.services.data_builder import (
    construir_data_nota_credito,
    construir_data_venta,
    generar_codigo_seguridad,
)
from facturacion_electronica.services.nota_credito import (
    lineas_de_devolucion,
    lineas_de_venta,
    motivo_valido,
)
from facturacion_electronica.services.numeracion_service import reservar_numero
from facturacion_electronica.services.qr import extraer_qr_url
from facturacion_electronica.services.sifen_client import (
    cancelar_de,
    consultar_de,
    enviar_de,
    firmar_xml,
    generar_qr,
    generar_xml,
    inutilizar_de,
)
from facturacion_electronica.services.tips_payload import construir_params_emisor
from facturacion_electronica.services.guarda import (
    error_devolucion_no_acreditable,
    error_motivo_inutilizacion,
    error_numero_no_inutilizable,
    error_original_no_acreditable,
    error_timbrado_inutilizacion,
    error_venta_no_facturable,
)
from facturacion_electronica.services.validacion import validar_cliente, validar_monto_innominado

# Ventana de transmisión de SIFEN: el DE debe enviarse dentro de las ~72h de
# emitido. Se avisa al enviar, no antes.
HORAS_LIMITE_ENVIO = 72

# SIFEN admite el evento de cancelación hasta ~48h después de la emisión.
# Pasado ese plazo la única salida es la nota de crédito (`generar_nota_credito`).
HORAS_LIMITE_CANCELACION = 48

# siConsDE: "Documento No Existe en SIFEN o ha sido Rechazado". Es una
# respuesta definitiva —el DE no está del otro lado— y hay que tratarla como
# rechazo: la recepción de un DE es síncrona, así que si SIFEN lo hubiera
# aceptado, la consulta lo encontraría. Sin esto el documento se queda en
# 'enviado', que es de los estados que no se pueden regenerar, y la venta no
# se puede volver a facturar nunca más.
CODIGO_CONSULTA_NO_EXISTE = '0420'


_CDC_RE = re.compile(r'<DE\s+Id="(\d+)"')


def fecha_emision(documento):
    """Fecha de emisión (dFeEmiDE) del documento: la de la venta, no la de generación
    del XML. SIFEN cuenta las ventanas de envío/cancelación desde esa fecha.
    getattr defensivo: si la venta ya no está disponible, cae a las fechas
    guardadas en el propio documento.

    La nota de crédito es la excepción: se emite hoy para corregir una factura
    que puede ser de hace meses. Contra la fecha de la venta, la ventana de
    72h nacía vencida y la NC no se podía enviar nunca.
    """
    if documento is None:
        return None
    if getattr(documento, 'tipo_documento', None) == TIPO_NOTA_CREDITO:
        return (getattr(documento, 'fecha_generado', None)
                or getattr(documento, 'fecha_envio', None))
    venta = getattr(documento, 'venta', None)
    if venta is not None and getattr(venta, 'fecha_venta', None):
        return venta.fecha_venta
    return getattr(documento, 'fecha_generado', None) or getattr(documento, 'fecha_envio', None)


def extraer_cdc(xml):
    if not xml:
        return None
    match = _CDC_RE.search(xml)
    return match.group(1) if match else None


def obtener_documento(venta_id):
    """Devuelve la **factura** vigente de la venta: la más reciente (mayor id).

    Las notas de crédito cuelgan de la misma venta; si entraran acá, la última
    NC pasaría a ser "el documento" de la venta y el POS, el KuDE y la guarda
    de anulación empezarían a mirar el documento equivocado. El tipo nulo es de
    los documentos viejos, anteriores a las notas de crédito: son facturas.
    """
    return (
        DocumentoElectronico.query
        .filter(
            DocumentoElectronico.id_venta == venta_id,
            db.or_(
                DocumentoElectronico.tipo_documento.is_(None),
                DocumentoElectronico.tipo_documento == TIPO_FACTURA,
            ),
        )
        .order_by(DocumentoElectronico.id.desc())
        .first()
    )


def facturas_de_ventas(venta_ids):
    """{id_venta: factura vigente} para un listado. Una sola consulta.

    Existe para que la pantalla de Historial de Ventas pueda mostrar el número
    del DE sin pedir uno por fila: con 20 ventas por página, `obtener_documento`
    en el bucle son 20 consultas por carga.
    """
    if not venta_ids:
        return {}

    documentos = (
        DocumentoElectronico.query
        .filter(
            DocumentoElectronico.id_venta.in_(list(venta_ids)),
            db.or_(
                DocumentoElectronico.tipo_documento.is_(None),
                DocumentoElectronico.tipo_documento == TIPO_FACTURA,
            ),
        )
        .order_by(DocumentoElectronico.id.asc())
        .all()
    )
    # Ascendente y pisando: queda el de mayor id, que es el vigente — el mismo
    # criterio que `obtener_documento`, para que el listado y el detalle no
    # muestren documentos distintos de la misma venta.
    return {doc.id_venta: doc for doc in documentos}


def notas_credito(venta_id):
    """Notas de crédito de una venta, de la más nueva a la más vieja."""
    return (
        DocumentoElectronico.query
        .filter_by(id_venta=venta_id, tipo_documento=TIPO_NOTA_CREDITO)
        .order_by(DocumentoElectronico.id.desc())
        .all()
    )


def generar_documento(venta):
    """Arma el XML de la venta y lo guarda. Devuelve (documento, error)."""
    from app.services.caja_transacciones import bloquear_caja_de_venta

    bloquear_caja_de_venta(venta)
    error_venta = error_venta_no_facturable(venta)
    if error_venta:
        doc = obtener_documento(venta.id_venta)
        if doc is not None and doc.estado not in ESTADOS_NO_REGENERABLES:
            doc.estado = ESTADO_ERROR
            doc.respuesta_mensaje = error_venta
            db.session.commit()
        return doc, error_venta
    doc = obtener_documento(venta.id_venta)
    if doc is not None and doc.estado in ESTADOS_NO_REGENERABLES:
        if doc.estado not in (ESTADO_CANCELADO, ESTADO_INUTILIZADO):
            return doc, f'El documento ya está {doc.estado}; no se puede regenerar.'
        # Re-facturación: el DE vigente se canceló en SIFEN (estaba aprobado) o
        # su número se inutilizó (nunca llegó a transmitirse). En los dos casos
        # el documento viejo no se toca —es historial fiscal, y su número ya no
        # se puede reusar— y la venta arranca uno nuevo con su propio número.
        doc = None
    if doc is None:
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)

    # Datos del cliente que invalidarían la factura para el receptor (ej. RUC de
    # empresa sin DV). Se frena antes de reservar número: corregir la ficha del
    # cliente no consume correlativos y el reintento automático regenera el DE.
    error_cliente = validar_cliente(venta.cliente) or validar_monto_innominado(
        venta.cliente, venta.total,
    )
    if error_cliente:
        doc.estado = ESTADO_ERROR
        doc.respuesta_mensaje = error_cliente
        db.session.commit()
        return doc, error_cliente

    config = obtener_configuracion()

    establecimiento = (config.establecimiento or '001').strip() or '001'
    punto = (config.punto_expedicion or '001').strip() or '001'
    # El número se reserva una sola vez y se conserva entre regeneraciones, para
    # mantener la correlatividad y que el CDC sea estable (igual que el código de
    # seguridad). Un fallo posterior no consume un número nuevo en el reintento.
    if not doc.numero:
        numero, error_num = reservar_numero(establecimiento, punto)
        if error_num:
            doc.estado = ESTADO_ERROR
            db.session.commit()
            return doc, error_num
        doc.numero = numero
        doc.establecimiento = establecimiento
        doc.punto = punto

    params = construir_params_emisor(config)
    data = construir_data_venta(
        venta, config, codigo_seguridad=doc.codigo_seguridad, numero=doc.numero,
    )

    xml, error = generar_xml(params, data)
    if error:
        doc.estado = ESTADO_ERROR
        db.session.commit()
        return doc, error

    doc.tipo_documento = data['tipoDocumento']
    doc.establecimiento = data['establecimiento']
    doc.punto = data['punto']
    doc.numero = data['numero']
    doc.timbrado = config.timbrado_numero
    doc.ambiente = config.ambiente
    doc.cdc = extraer_cdc(xml)
    doc.xml = xml
    # Al regenerar se invalida cualquier firma/QR previo: corresponden al XML
    # anterior (otro CDC) y no deben reenviarse a SIFEN.
    doc.xml_firmado = None
    doc.xml_qr = None
    doc.qr_url = None
    # Limpia el resultado de un intento anterior (ej. el aviso de RUC sin DV):
    # ya no describe a este XML y confundiría en la UI.
    doc.respuesta_codigo = None
    doc.respuesta_mensaje = None
    doc.respuesta_raw = None
    doc.estado = ESTADO_GENERADO
    doc.fecha_generado = datetime.utcnow()
    db.session.commit()
    return doc, None


def nota_credito_de_devolucion(devolucion):
    """La NC más reciente de esa devolución, o None."""
    return (
        DocumentoElectronico.query
        .filter_by(
            id_devolucion=devolucion.id_devolucion, tipo_documento=TIPO_NOTA_CREDITO,
        )
        .order_by(DocumentoElectronico.id.desc())
        .first()
    )


def generar_nota_credito(devolucion, motivo=None):
    """Arma el XML de la NC de una devolución y lo guarda. Devuelve (doc, error).

    El correlativo, el código de seguridad y la fecha se reservan una sola vez
    y se conservan entre regeneraciones, igual que en la factura: el CDC tiene
    que ser estable, y un fallo al firmar no puede consumir otro número del
    rango de notas de crédito.
    """
    error_devolucion = error_devolucion_no_acreditable(devolucion)
    if error_devolucion:
        return None, error_devolucion

    original = obtener_documento(devolucion.id_venta)
    error_original = error_original_no_acreditable(original)
    if error_original:
        return None, error_original

    doc = nota_credito_de_devolucion(devolucion)
    if doc is not None and doc.estado in ESTADOS_NO_REGENERABLES:
        if doc.estado != ESTADO_CANCELADO:
            return doc, f'La nota de crédito ya figura como {doc.estado}; no se puede regenerar.'
        # La NC anterior fue dada de baja en SIFEN: la devolución vuelve a
        # quedar sin acreditar y corresponde emitir una nueva.
        doc = None

    codigo_motivo, descripcion_motivo = motivo_valido(motivo)
    if codigo_motivo is None and doc is not None:
        # Reintento sin motivo en el formulario: vale el que ya eligió la
        # persona la primera vez.
        codigo_motivo, descripcion_motivo = motivo_valido(doc.nc_motivo)
    if codigo_motivo is None:
        return doc, 'Elegí un motivo del catálogo de SIFEN para la nota de crédito.'

    lineas = lineas_de_devolucion(devolucion)
    if not lineas:
        return doc, 'La devolución no tiene ítems para acreditar.'

    if doc is None:
        doc = DocumentoElectronico(
            id_venta=devolucion.id_venta,
            tipo_documento=TIPO_NOTA_CREDITO,
            id_devolucion=devolucion.id_devolucion,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)
    return _completar_nota_credito(
        doc, original, codigo_motivo, descripcion_motivo, lineas, devolucion,
    )


def _completar_nota_credito(doc, original, codigo_motivo, descripcion_motivo,
                            lineas, origen):
    """Numeración, XML y persistencia de una NC ya identificada.

    Lo comparten la NC de una devolución y la que anula una factura mal
    emitida: sólo cambian de dónde salen las líneas y qué documento las
    respalda. `origen` es lo que aporta la descripción libre del DE (la
    devolución, o el texto que escribió quien anula).
    """
    doc.id_documento_asociado = original.id
    doc.nc_motivo = codigo_motivo
    doc.nc_motivo_desc = descripcion_motivo

    config = obtener_configuracion()
    establecimiento = (config.establecimiento or '001').strip() or '001'
    punto = (config.punto_expedicion or '001').strip() or '001'
    if not doc.numero:
        numero, error_num = reservar_numero(establecimiento, punto, TIPO_NOTA_CREDITO)
        if error_num:
            doc.estado = ESTADO_ERROR
            doc.respuesta_mensaje = error_num
            db.session.commit()
            return doc, error_num
        doc.numero = numero
        doc.establecimiento = establecimiento
        doc.punto = punto
    # La fecha del DE entra en el CDC: se fija en la primera generación para
    # que regenerar no cambie el CDC ni corra la ventana de envío.
    if not doc.fecha_generado:
        doc.fecha_generado = datetime.utcnow()

    params = construir_params_emisor(config)
    data = construir_data_nota_credito(
        origen, config, original, codigo_motivo,
        venta=original.venta, lineas=lineas,
        codigo_seguridad=doc.codigo_seguridad, numero=doc.numero,
        fecha=doc.fecha_generado,
    )

    xml, error = generar_xml(params, data)
    if error:
        doc.estado = ESTADO_ERROR
        doc.respuesta_mensaje = error
        db.session.commit()
        return doc, error

    doc.establecimiento = data['establecimiento']
    doc.punto = data['punto']
    doc.timbrado = config.timbrado_numero
    doc.ambiente = config.ambiente
    doc.cdc = extraer_cdc(xml)
    doc.xml = xml
    doc.xml_firmado = None
    doc.xml_qr = None
    doc.qr_url = None
    doc.respuesta_codigo = None
    doc.respuesta_mensaje = None
    doc.respuesta_raw = None
    doc.estado = ESTADO_GENERADO
    db.session.commit()
    return doc, None


def nota_credito_de_correccion(venta_id):
    """La NC de anulación de esa venta (la que no tiene devolución detrás)."""
    return (
        DocumentoElectronico.query
        .filter(
            DocumentoElectronico.id_venta == venta_id,
            DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO,
            DocumentoElectronico.id_devolucion.is_(None),
        )
        .order_by(DocumentoElectronico.id.desc())
        .first()
    )


def generar_nota_credito_correccion(venta, motivo=None, descripcion=None):
    """NC que anula una factura entera, sin devolución. Devuelve (doc, error).

    Es la salida cuando la factura está mal y ya pasaron las 48h en que SIFEN
    admite el evento de cancelación: acredita el total facturado y deja el
    saldo del cliente en cero ante SIFEN.

    **No mueve plata ni stock**, igual que la NC de una devolución: la NC
    respalda un movimiento, no lo hace. Quien quiera revertir el cobro anula la
    venta después, que es el camino que ya hace el contra-asiento de caja.
    """
    if venta is None:
        return None, 'La venta ya no existe.'

    original = obtener_documento(venta.id_venta)
    error_original = error_original_no_acreditable(original)
    if error_original:
        return None, error_original

    doc = nota_credito_de_correccion(venta.id_venta)
    if doc is not None and doc.estado in ESTADOS_NO_REGENERABLES:
        if doc.estado != ESTADO_CANCELADO:
            return doc, (
                f'La factura ya tiene una nota de crédito de anulación {doc.estado}; '
                'no se puede emitir otra.'
            )
        doc = None

    codigo_motivo, descripcion_motivo = motivo_valido(motivo)
    if codigo_motivo is None and doc is not None:
        codigo_motivo, descripcion_motivo = motivo_valido(doc.nc_motivo)
    if codigo_motivo is None:
        return doc, 'Elegí un motivo del catálogo de SIFEN para la nota de crédito.'

    lineas = lineas_de_venta(venta)
    if not lineas:
        return doc, 'La venta no tiene ítems para acreditar.'

    if doc is None:
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=TIPO_NOTA_CREDITO,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)

    origen = SimpleNamespace(motivo=(descripcion or '').strip() or None)
    return _completar_nota_credito(
        doc, original, codigo_motivo, descripcion_motivo, lineas, origen,
    )


def emitir_nota_credito_correccion(venta, motivo=None, descripcion=None):
    """Cadena completa de la NC de anulación: generar → firmar → QR."""
    doc, error = generar_nota_credito_correccion(venta, motivo, descripcion)
    if error:
        return doc, error
    doc, error = firmar_documento(doc)
    if error:
        return doc, error
    return generar_qr_documento(doc)


def emitir_nota_credito(devolucion, motivo=None):
    """Cadena completa de la NC: generar → firmar → QR. Devuelve (doc, error).

    No la envía a SIFEN: eso lo hace el job, igual que con la factura del POS.
    """
    doc, error = generar_nota_credito(devolucion, motivo)
    if error:
        return doc, error
    doc, error = firmar_documento(doc)
    if error:
        return doc, error
    return generar_qr_documento(doc)


def firmar_documento(documento):
    """Firma el XML guardado del documento con el certificado de la config."""
    if documento is None or not documento.xml:
        return documento, 'No hay XML generado para firmar. Generá el documento primero.'
    if documento.estado in ESTADOS_NO_REGENERABLES:
        return documento, f'El documento ya está {documento.estado}.'

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    firmado, error = firmar_xml(documento.xml, config.cert_path, descifrar(config.cert_password or ''))
    if error:
        return documento, error

    documento.xml_firmado = firmado
    documento.estado = ESTADO_FIRMADO
    db.session.commit()
    return documento, None


def generar_qr_documento(documento):
    """Agrega el QR (gCamFuFD/dCarQR) al XML firmado y persiste la URL.

    Usa el CSC de la config; si no está cargado, cae al CSC de maqueta para
    poder mostrar el KuDE en demo (el hash no es válido contra SIFEN).
    """
    if documento is None or not documento.xml_firmado:
        return documento, 'Primero firmá el documento; el QR se calcula sobre el XML firmado.'

    # El QR ya viajó dentro del XML que SIFEN aprobó. Recalcularlo con otro CSC
    # pisaría `qr_url` con un hash que no verifica contra e-Kuatia, y el KuDE
    # que se lleva el cliente dejaría de validar. Se permite sólo cuando falta:
    # ahí no hay nada que arruinar y es la única forma de recuperar el KuDE.
    if documento.estado in ESTADOS_NO_REGENERABLES and documento.qr_url:
        return documento, (
            f'El documento ya está {documento.estado} y tiene su QR. Regenerarlo con otro '
            'CSC dejaría un KuDE que no valida en e-Kuatia.'
        )

    config = obtener_configuracion()
    if config.ambiente == AMBIENTE_PRODUCCION and not (config.csc and config.csc_id):
        # El CSC de maqueta genera un QR que no verifica contra e-Kuatia; en
        # producción eso entregaría un KuDE fiscalmente inválido al cliente.
        return documento, 'Falta cargar el CSC real en la configuración para generar el QR en producción.'
    if config.ambiente == AMBIENTE_PRODUCCION and (config.csc or '').strip() == CSC_DEMO:
        # El CSC de pruebas de la DNIT es este mismo valor, así que "está
        # cargado" no alcanza: al pasar a producción hay que reemplazarlo.
        return documento, (
            'El CSC cargado es el de pruebas. Cargá el CSC real de la DNIT antes de '
            'emitir en producción, o el QR del KuDE no va a validar.'
        )
    id_csc = config.csc_id or CSC_DEMO_ID
    csc = config.csc or CSC_DEMO

    xml_con_qr, error = generar_qr(documento.xml_firmado, id_csc, csc, config.ambiente)
    if error:
        return documento, error

    documento.xml_qr = xml_con_qr
    documento.qr_url = extraer_qr_url(xml_con_qr)
    db.session.commit()
    return documento, None


def _ambiente_setapi(config):
    return 'prod' if config.ambiente == AMBIENTE_PRODUCCION else 'test'


def _fecha_firma_evento():
    """`dFecFirma` del evento, en hora de Paraguay y sin offset.

    La escribe el Node con la hora local **de su proceso**; en un servidor en
    UTC eso son tres horas en el futuro y SIFEN rechaza el evento con un error
    genérico. Se manda resuelta desde acá, igual que `dFeEmiDE` de la factura.
    """
    from app.utils.helpers import now_local

    return now_local().strftime('%Y-%m-%dT%H:%M:%S')


def _nombre_local(clave):
    """`ns2:dEstRes` → `dEstRes`.

    La respuesta real de SIFEN llega con el prefijo de namespace pegado a cada
    nombre. Comparando la clave entera, un rechazo (`ns2:dEstRes: Rechazado`)
    no se reconocía: el documento quedaba en 'enviado' para siempre, sin
    código ni motivo a la vista, aunque todo estuviera en `respuesta_raw`.
    """
    return clave.split(':')[-1] if isinstance(clave, str) else clave


def _buscar_clave(obj, claves):
    """Busca recursivamente la primera de `claves` en un dict/list anidado."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _nombre_local(k) in claves and v not in (None, ''):
                return v
        for v in obj.values():
            encontrado = _buscar_clave(v, claves)
            if encontrado is not None:
                return encontrado
    elif isinstance(obj, list):
        for item in obj:
            encontrado = _buscar_clave(item, claves)
            if encontrado is not None:
                return encontrado
    return None


def _serializar_respuesta(respuesta):
    """JSON completo de la respuesta de SIFEN, para diagnosticar rechazos sin
    depender de que _interpretar_respuesta haya encontrado los campos."""
    if respuesta is None:
        return None
    try:
        return json.dumps(respuesta, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(respuesta)


def _detalle_sifen(codigo, mensaje):
    """Texto del rechazo para la pantalla: código **y** mensaje.

    `dMsgRes` de los eventos suele ser genérico ("Error Inesperado"): sin el
    `dCodRes` al lado no hay nada que buscar en el manual de la DNIT.
    """
    codigo = str(codigo).strip() if codigo is not None else ''
    mensaje = str(mensaje).strip() if mensaje is not None else ''
    if codigo and mensaje:
        return f'{codigo} — {mensaje}'
    return codigo or mensaje or 'respuesta desconocida'


def _interpretar_respuesta(respuesta):
    """Extrae (estado, codigo, mensaje, protocolo) de la respuesta de SIFEN.

    Defensivo: la estructura exacta del SOAP recién se puede verificar contra el
    ambiente real, así que se busca por nombre de campo sin asumir el árbol.
    """
    codigo = _buscar_clave(respuesta, {'dCodRes', 'dCodResLot'})
    mensaje = _buscar_clave(respuesta, {'dMsgRes', 'dMsg'})
    protocolo = _buscar_clave(respuesta, {'dProtAut', 'dProtConsLote', 'dNumLote'})
    estado_txt = (_buscar_clave(respuesta, {'dEstRes'}) or '').lower()

    if 'aprob' in estado_txt:
        estado = ESTADO_APROBADO
    elif 'rechaz' in estado_txt:
        estado = ESTADO_RECHAZADO
    else:
        estado = ESTADO_ENVIADO
    return estado, codigo, mensaje, protocolo


def enviar_documento(documento, forzar_fecha=False):
    """Envía el DE firmado a SIFEN y guarda la respuesta. Devuelve (doc, error).

    NO está probado end-to-end: requiere un certificado real habilitado por la
    DNIT (TLS mutuo). El circuito interno (generar/firmar/QR) sí está probado.
    """
    if documento is None or not documento.xml_firmado:
        return documento, 'Primero generá y firmá el documento antes de enviarlo.'
    if not documento.xml_qr:
        # gCamFuFD/dCarQR es obligatorio en el rDE; sin QR, SIFEN rechaza el envío.
        return documento, 'Primero generá el QR del documento antes de enviarlo.'
    if documento.estado in ESTADOS_NO_REGENERABLES:
        return documento, f'El documento ya está {documento.estado}.'
    error_venta = error_venta_no_facturable(getattr(documento, 'venta', None))
    if error_venta:
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error_venta
        db.session.commit()
        return documento, error_venta

    emitido_el = fecha_emision(documento)
    if not forzar_fecha and emitido_el:
        antiguedad = datetime.utcnow() - emitido_el
        if antiguedad > timedelta(hours=HORAS_LIMITE_ENVIO):
            error = (
                f'El documento se emitió hace más de {HORAS_LIMITE_ENVIO}h; SIFEN '
                'va a rechazar el documento por fecha vencida. Regenerarlo no cambia '
                'la fecha de emisión, así que no se puede enviar.'
            )
            # Se persiste como error (no se deja en 'firmado') para que quede
            # visible en la UI con su motivo.
            documento.estado = ESTADO_ERROR
            documento.respuesta_mensaje = error
            # Y se marca como definitivo. El estado 'error' por sí solo no
            # frena al job: lo vuelve a tomar cada 10 minutos del backoff, para
            # siempre. Esto no es un fallo transitorio —la fecha de emisión ya
            # pasó y el tiempo no vuelve— así que reintentarlo es trabajo al
            # pedo, y peor: infla el contador de errores de cada pasada del
            # job, donde un error nuevo de verdad queda tapado en el número.
            documento.reintentar_despues = SIN_REINTENTO
            db.session.commit()
            return documento, error

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    xml = documento.xml_qr
    respuesta, error = enviar_de(
        xml, config.cert_path, descifrar(config.cert_password or ''),
        _ambiente_setapi(config), request_id=documento.id,
    )
    if error:
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error
        db.session.commit()
        return documento, error

    estado, codigo, mensaje, protocolo = _interpretar_respuesta(respuesta)
    documento.estado = estado
    documento.respuesta_codigo = str(codigo) if codigo is not None else None
    documento.respuesta_mensaje = str(mensaje) if mensaje is not None else None
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    documento.protocolo_autorizacion = str(protocolo) if protocolo is not None else None
    documento.fecha_envio = datetime.utcnow()
    db.session.commit()
    return documento, None


def consultar_documento(documento):
    """Consulta el estado actual del DE en SIFEN por CDC. Devuelve (respuesta, error)."""
    if documento is None or not documento.cdc:
        return None, 'No hay CDC para consultar.'
    config = obtener_configuracion()
    if not config.cert_path:
        return None, 'Falta cargar el certificado digital (.p12) en la configuración.'
    respuesta, error = consultar_de(
        documento.cdc, config.cert_path, descifrar(config.cert_password or ''),
        _ambiente_setapi(config), request_id=documento.id,
    )
    if error:
        return respuesta, error

    estado, codigo, mensaje, protocolo = _interpretar_respuesta(respuesta)
    if estado == ESTADO_ENVIADO and str(codigo or '').strip() == CODIGO_CONSULTA_NO_EXISTE:
        estado = ESTADO_RECHAZADO
    # La consulta refleja el estado real en SIFEN: sólo avanza a aprobado/rechazado,
    # nunca retrocede el documento a "enviado".
    if estado in (ESTADO_APROBADO, ESTADO_RECHAZADO):
        documento.estado = estado
        documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
        documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
        documento.respuesta_raw = _serializar_respuesta(respuesta)
        if protocolo is not None:
            documento.protocolo_autorizacion = str(protocolo)
        db.session.commit()
    return respuesta, None


def cancelar_documento(documento, motivo):
    """Cancela en SIFEN un DE aprobado (evento). Devuelve (documento, error).

    No revierte la venta ni habilita re-facturación por sí sola: sólo anula el
    DE en SIFEN. Tras cancelar, generar_documento crea un DE nuevo si se quiere
    volver a facturar la misma venta.
    """
    if documento is None:
        return documento, 'No hay documento para cancelar.'
    if documento.estado == ESTADO_CANCELADO:
        return documento, 'El documento ya está cancelado.'
    if documento.estado != ESTADO_APROBADO:
        return documento, 'Sólo se puede cancelar en SIFEN un documento aprobado.'

    motivo = (motivo or '').strip()
    if not 5 <= len(motivo) <= 500:
        return documento, 'El motivo de cancelación debe tener entre 5 y 500 caracteres.'

    referencia = fecha_emision(documento)
    if referencia and datetime.utcnow() - referencia > timedelta(hours=HORAS_LIMITE_CANCELACION):
        return documento, (
            f'Pasaron más de {HORAS_LIMITE_CANCELACION}h desde la emisión; SIFEN ya no '
            'permite cancelar. Corresponde emitir una nota de crédito.'
        )

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    params = construir_params_emisor(config)
    respuesta, xml_evento, error = cancelar_de(
        params, documento.cdc, motivo, config.cert_path,
        descifrar(config.cert_password or ''), _ambiente_setapi(config),
        request_id=documento.id, fecha_firma=_fecha_firma_evento(),
    )
    if error:
        return documento, error

    estado, codigo, mensaje, _protocolo = _interpretar_respuesta(respuesta)
    if estado != ESTADO_APROBADO:
        documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
        documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
        documento.respuesta_raw = _serializar_respuesta(respuesta)
        # El evento rechazado se guarda igual. Guardarlo sólo al aprobar dejaba
        # el rechazo sin nada que mirar: el mensaje de SIFEN es genérico y el
        # XML que se firmó —lo único que dice qué se mandó— se perdía.
        documento.xml_cancelacion = xml_evento
        db.session.commit()
        return documento, f'SIFEN no aprobó la cancelación: {_detalle_sifen(codigo, mensaje)}'

    documento.estado = ESTADO_CANCELADO
    documento.motivo_cancelacion = motivo
    documento.xml_cancelacion = xml_evento
    documento.fecha_cancelado = datetime.utcnow()
    documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
    documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    db.session.commit()
    return documento, None


def inutilizar_documento(documento, motivo):
    """Informa a SIFEN que el número de este documento no se va a usar.

    Es el caso del número **quemado**: se reservó el correlativo al generar el
    DE, y ese DE nunca llegó a SIFEN (se cortó la luz, falló la firma, se anuló
    la venta antes de transmitir). El número ya salió de la secuencia, y si
    nadie avisa, el timbrado queda con un hueco que ante SIFEN no tiene
    explicación.

    No es una cancelación y no se puede reemplazar por una: cancelar necesita
    un CDC aprobado del otro lado. Acá no hay nada que dar de baja, porque
    SIFEN nunca vio el documento.

    Se informa **un número por evento** (`desde` == `hasta`). Agrupar rangos
    sería más barato en llamadas, pero los huecos no son contiguos salvo por
    casualidad, y un rango que abarque un número emitido al medio lo estaría
    inutilizando sin que nadie lo pida.
    """
    error_numero = error_numero_no_inutilizable(documento)
    if error_numero:
        return documento, error_numero

    motivo = (motivo or '').strip()
    error_motivo = error_motivo_inutilizacion(motivo)
    if error_motivo:
        return documento, error_motivo

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    # xmlgen exige exactamente 8 caracteres y tira un Error genérico; se
    # valida antes para poder decir cuál es el problema.
    timbrado = (documento.timbrado or config.timbrado_numero or '').strip()
    error_timbrado = error_timbrado_inutilizacion(timbrado)
    if error_timbrado:
        return documento, error_timbrado

    numero = int(documento.numero)
    params = construir_params_emisor(config)
    data = {
        'timbrado': timbrado,
        'establecimiento': documento.establecimiento,
        'punto': documento.punto,
        'desde': numero,
        'hasta': numero,
        'tipoDocumento': documento.tipo_documento or TIPO_FACTURA,
        'motivo': motivo,
    }
    respuesta, xml_evento, error = inutilizar_de(
        params, data, config.cert_path,
        descifrar(config.cert_password or ''), _ambiente_setapi(config),
        request_id=documento.id, fecha_firma=_fecha_firma_evento(),
    )
    if error:
        return documento, error

    estado, codigo, mensaje, _protocolo = _interpretar_respuesta(respuesta)
    # `xml_cancelacion` y `motivo_cancelacion` guardan el evento, sea cual sea:
    # un DE tiene a lo sumo uno de los dos (o se transmitió y se cancela, o no
    # se transmitió y se inutiliza), y columnas nuevas obligan a un ALTER en
    # cada instalación a cambio de nada.
    documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
    documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    documento.xml_cancelacion = xml_evento
    if estado != ESTADO_APROBADO:
        db.session.commit()
        return documento, (
            f'SIFEN no aprobó la inutilización: {_detalle_sifen(codigo, mensaje)}'
        )

    documento.estado = ESTADO_INUTILIZADO
    documento.motivo_cancelacion = motivo
    documento.fecha_cancelado = datetime.utcnow()
    db.session.commit()
    return documento, None


def emitir_para_pos(venta):
    """Cadena completa para el POS: generar → firmar → QR. Devuelve (doc, error).

    Se llama DESPUÉS de que la venta ya está registrada; si algo falla, el error
    se devuelve para que el POS caiga al ticket normal sin romper la venta.
    """
    doc, error = generar_documento(venta)
    if error:
        return doc, error
    doc, error = firmar_documento(doc)
    if error:
        return doc, error
    return generar_qr_documento(doc)


__all__ = [
    'generar_documento',
    'firmar_documento',
    'generar_qr_documento',
    'enviar_documento',
    'consultar_documento',
    'cancelar_documento',
    'emitir_para_pos',
    'generar_nota_credito',
    'emitir_nota_credito',
    'nota_credito_de_devolucion',
    'obtener_documento',
    'notas_credito',
    'extraer_cdc',
    'fecha_emision',
]
