"""Guardas compartidas de emisión y anulación de documentos electrónicos.

Viven acá y no en cada proveedor para que el motor propio, la API y las rutas
de venta no se desincronicen: un literal distinto en cada uno es exactamente
cómo se emitió la factura de una venta anulada y cómo se dejó anular una
venta con el DE ya vivo del otro lado.
"""
from facturacion_electronica import (
    AMBIENTE_TEST,
    ESTADO_API_CANCELACION_PENDIENTE,
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ENVIADO,
    ESTADO_INUTILIZADO,
    ESTADO_RECHAZADO,
    ESTADOS_TRANSMITIDOS,
)

MENSAJE_VENTA_ANULADA = (
    'No se puede emitir la factura electrónica de una venta anulada.'
)

MENSAJE_DEVOLUCION_ANULADA = (
    'La devolución fue anulada; no corresponde emitir una nota de crédito por ella.'
)


def venta_anulada(venta):
    return (getattr(venta, 'estado', None) or '').strip().lower() == 'anulada'


def error_venta_no_facturable(venta):
    """Error si esta venta no puede generar/enviar un DE. None si sigue."""
    if venta is None:
        return None
    if venta_anulada(venta):
        return MENSAJE_VENTA_ANULADA
    return None


def devolucion_anulada(devolucion):
    return (getattr(devolucion, 'estado', None) or '').strip().lower() == 'anulada'


def error_devolucion_no_acreditable(devolucion):
    """Error si esta devolución no puede generar una NC. None si sigue."""
    if devolucion is None:
        return 'La devolución de esta nota de crédito ya no existe.'
    if devolucion_anulada(devolucion):
        return MENSAJE_DEVOLUCION_ANULADA
    return None


def error_original_no_acreditable(original):
    """Error si la factura que se quiere corregir no admite una NC ahora.

    Lo mira tanto la emisión manual como el reintento del job: el original
    puede haber cambiado de estado entre el primer intento y el segundo, y
    acreditar una factura que se está cancelando emite dos veces la misma
    plata (la baja y la NC).
    """
    if original is None or not original.cdc:
        return ('La venta no tiene factura electrónica emitida; no hay nada '
                'que acreditar.')
    if original.estado != ESTADO_APROBADO:
        return (f'La factura está {original.estado}. Sólo se puede emitir una nota '
                'de crédito contra una factura aprobada por SIFEN.')
    if (original.respuesta_codigo or '').upper() == ESTADO_API_CANCELACION_PENDIENTE:
        return ('La factura tiene una cancelación pedida y SIFEN todavía no la '
                'confirmó. Esperá a que la anulación quede firme: si se concreta, '
                'la nota de crédito sobra, y si SIFEN la rechaza, recién ahí '
                'corresponde emitirla.')

    # SIFEN deja facturar a un consumidor sin identificar, pero no deja
    # acreditarle: la NC de una factura innominada vuelve rechazada con
    # "El adquiriente del comprobante de venta informado no se encuentra
    # identificado" (visto el 2026-09-22 en la NC 0000004). Se frena acá antes
    # de reservar número, igual que `validar_cliente` en la factura: corregir
    # la ficha del cliente no debe costar un correlativo.
    from facturacion_electronica.services.data_builder import receptor_innominado

    cliente = getattr(getattr(original, 'venta', None), 'cliente', None)
    if receptor_innominado(cliente):
        return ('La factura se emitió a un cliente sin identificar, y SIFEN no acepta '
                'notas de crédito a un receptor innominado. Cargale el RUC o la cédula '
                'al cliente en su ficha y volvé a intentar. Si la factura tiene menos '
                'de 48h, el camino que sí funciona es cancelarla.')
    return None


def error_numero_no_inutilizable(documento):
    """Error si el número de este documento no se puede informar como quemado.

    Vive acá porque la regla es la misma con los dos proveedores y sólo cambia
    el transporte: el motor propio arma el evento y lo firma, la API lo pide
    por `POST /sifen/inutilizations/`. Cuando estaba escrita sólo dentro del
    motor propio, el día que la API implementó su inutilización hubo que
    elegir entre copiarla o quedarse sin ella.
    """
    if documento is None:
        return 'No hay documento para inutilizar.'
    if documento.estado == ESTADO_INUTILIZADO:
        return 'Ese número ya está inutilizado.'
    if documento.estado in ESTADOS_TRANSMITIDOS:
        return (
            'Ese documento ya salió hacia SIFEN, así que su número está usado. '
            'Si hay que darlo de baja, corresponde cancelarlo o emitir una nota '
            'de crédito, no inutilizar el número.'
        )
    if not documento.numero:
        return 'Ese documento no llegó a reservar un número; no hay nada que inutilizar.'
    return None


def error_motivo_inutilizacion(motivo):
    """Error si el motivo no entra en lo que acepta SIFEN (`mMotInu`). None si sigue."""
    if not 5 <= len((motivo or '').strip()) <= 500:
        return 'El motivo de la inutilización debe tener entre 5 y 500 caracteres.'
    return None


def error_timbrado_inutilizacion(timbrado):
    """Error si el timbrado del evento no sirve. None si sigue.

    El timbrado va al evento, no al documento: se usa el que tenía el DE
    cuando se generó, porque un timbrado nuevo no puede inutilizar números del
    anterior. SIFEN exige 8 dígitos exactos.
    """
    timbrado = (timbrado or '').strip()
    if len(timbrado) != 8:
        return (
            f'El timbrado del documento ({timbrado or "vacío"}) no tiene 8 dígitos; '
            'SIFEN no acepta el evento de inutilización sin un timbrado válido.'
        )
    return None


def documento_en_proveedor(documento):
    """El DE ya existe fuera de esta instalación (SIFEN o API remota)."""
    if documento is None:
        return False
    if getattr(documento, 'api_documento_id', None):
        return True
    return documento.estado in ESTADOS_TRANSMITIDOS


def anulada_por_nota_credito(documento):
    """True si una NC de anulación aprobada ya dejó sin efecto esta factura.

    Es la salida cuando pasaron las 48h y SIFEN ya no admite el evento de
    cancelación: la factura sigue `aprobado` para siempre —una NC no cambia el
    estado del DE que corrige— pero fiscalmente no queda nada en pie, así que
    la venta se tiene que poder anular.

    Sólo cuenta la NC **sin devolución detrás**: la de una devolución acredita
    los ítems que volvieron, que puede ser una parte, y con una devolución
    parcial la factura sigue viva por el resto.
    """
    if documento is None or getattr(documento, 'id', None) is None:
        return False

    from facturacion_electronica import TIPO_NOTA_CREDITO
    from facturacion_electronica.models import DocumentoElectronico

    return DocumentoElectronico.query.filter(
        DocumentoElectronico.id_documento_asociado == documento.id,
        DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO,
        DocumentoElectronico.id_devolucion.is_(None),
        DocumentoElectronico.estado == ESTADO_APROBADO,
    ).first() is not None


def documento_impide_anular_venta(documento):
    """True si anular la venta dejaría un DE vivo en SIFEN o en la API.

    Motor propio: bloquea enviado y aprobado (firmado todavía no salió).
    API: firmado = PENDING_BATCH, el documento ya está del otro lado con CDC
    y su pipeline lo transmite en ~30s; se detecta por `api_documento_id`.
    """
    if documento is None:
        return False
    estado = documento.estado
    if anulada_por_nota_credito(documento):
        return False
    if estado in (ESTADO_ENVIADO, ESTADO_APROBADO):
        return True
    if documento_en_proveedor(documento) and estado not in (
        ESTADO_CANCELADO, ESTADO_INUTILIZADO, ESTADO_RECHAZADO,
    ):
        return True
    return False


def filtro_documentos_en_proveedor():
    """Filtro ORM: hay al menos un DE que ata la instalación a su proveedor.

    Lo emitido en ambiente de prueba no ata: no tiene validez fiscal y nadie
    va a tener que anularlo ni hacerle una nota de crédito. Un documento sin
    ambiente se toma como de producción, por las dudas.
    """
    from app import db
    from facturacion_electronica.models import DocumentoElectronico

    return db.and_(
        db.or_(
            DocumentoElectronico.estado.in_(ESTADOS_TRANSMITIDOS),
            DocumentoElectronico.api_documento_id.isnot(None),
        ),
        db.or_(
            DocumentoElectronico.ambiente.is_(None),
            DocumentoElectronico.ambiente != AMBIENTE_TEST,
        ),
    )
