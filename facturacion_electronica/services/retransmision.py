"""Reenvío seguro de un DE ya firmado que no llegó a SIFEN (motor propio).

Por defecto el motor propio transmite cada DE de forma **síncrona**
(`siRecepDE`). Si se configuró el envío por lote, el DE pendiente se consulta
por su lote y no pasa por acá mientras SIFEN lo procesa (ver envio_lote.py).
Lo que sí pasa en los dos modos es que
SIFEN o la red se caigan justo al enviar, y ahí aparecen dos problemas que
este módulo resuelve:

1. **El plazo.** Pasadas 72h desde `dFeEmiDE`, SIFEN NO rechaza: aprueba con
   observación (código 1005, transmisión extemporánea, MT v150 A004b). El
   rechazo duro es recién a las 720h (código 1150, MT v150 D002). Antes nos
   rendíamos a las 72h y el número quedaba para inutilizar, aunque el
   cliente ya tuviera su KuDE impreso con ese CDC.

2. **El reenvío a ciegas.** Si el envío anterior cortó por timeout, SIFEN
   pudo haberlo recibido igual. Antes de reenviar se consulta el CDC
   (`siConsDE`) y se actúa sólo con evidencia: si SIFEN lo tiene autorizado
   se adopta, si dice que no existe se reenvía, y si la respuesta no es
   clara no se hace nada y se espera a la próxima pasada. Es el mismo
   criterio de la API (`classify_cdc_evidence` en fe_django): un "ausente"
   de más es un doble envío fiscal; un "inconcluso" de más sólo demora.
"""
import re
from datetime import datetime, timedelta

from app import db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_RECHAZADO
from facturacion_electronica.services.respuesta_sifen import _buscar_clave, _serializar_respuesta

# Rechazo duro de SIFEN por fecha (código 1150): ya no hay reenvío posible.
HORAS_MAXIMO_TRANSMISION = 720

# siConsDE: "CDC encontrado". `0260` entra porque es el código de un DE
# aprobado y alguna versión de la librería lo devuelve así.
CODIGOS_CDC_ENCONTRADO = frozenset({'0422', '0260'})
# siConsDE: "Documento no existe en SIFEN o ha sido rechazado". Definitiva con
# la recepción síncrona: si SIFEN lo hubiera aceptado la consulta lo
# encontraría. Con un lote en proceso NO lo es, y por eso un DE de lote
# pendiente nunca se consulta por CDC (envio_service.consultar_documento). Sin tratarla, un DE quedaba en 'enviado' (no regenerable) y la
# venta no se podía volver a facturar nunca más.
CODIGOS_CDC_AUSENTE = frozenset({'0420'})

CONFIRMADO = 'confirmado'
AUSENTE = 'ausente'
INCONCLUSO = 'inconcluso'

# `dProtAut` viene dentro de `xContenDE`, que es el rDE como TEXTO (XML
# escapado), no como nodo: `_buscar_clave` no lo ve. Se busca en el texto en
# sus tres formas: clave JSON, etiqueta XML y etiqueta escapada.
_PROTOCOLO_RE = re.compile(r'dProtAut(?:"\s*:\s*"?|>|&gt;)\s*(\d+)')


def evaluar_plazo(emitido_el, ahora=None):
    """(error, aviso) del plazo de transmisión. A lo sumo uno tiene valor.

    `error`: pasaron más de 720h, SIFEN lo va a rechazar seguro.
    `aviso`: pasaron más de 72h; se envía igual y queda extemporáneo.
    """
    from facturacion_electronica.services.emision_service import HORAS_LIMITE_ENVIO

    if emitido_el is None:
        return None, None
    horas = ((ahora or datetime.utcnow()) - emitido_el) / timedelta(hours=1)
    if horas > HORAS_MAXIMO_TRANSMISION:
        return (
            f'El documento se emitió hace más de {HORAS_MAXIMO_TRANSMISION}h; SIFEN ya no '
            'lo acepta (rechazo 1150). Regenerarlo no cambia la fecha de emisión: '
            'corresponde inutilizar el número.'
        ), None
    if horas > HORAS_LIMITE_ENVIO:
        return None, (
            f'Transmitido fuera de las {HORAS_LIMITE_ENVIO}h: SIFEN lo aprueba con '
            'observación (1005, extemporáneo) y puede corresponder multa.'
        )
    return None, None


def evidencia_cdc(respuesta):
    """(evidencia, codigo, protocolo) de una respuesta de siConsDE."""
    codigo = str(_buscar_clave(respuesta, {'dCodRes'}) or '').strip()
    protocolo = _buscar_clave(respuesta, {'dProtAut'})
    if protocolo is None:
        encontrado = _PROTOCOLO_RE.search(_serializar_respuesta(respuesta) or '')
        protocolo = encontrado.group(1) if encontrado else None
    protocolo = str(protocolo).strip() if protocolo is not None else ''

    if codigo in CODIGOS_CDC_AUSENTE:
        # "No lo tengo" con un protocolo al lado se contradice: ante la duda,
        # nunca autorizar un reenvío.
        return (INCONCLUSO if protocolo else AUSENTE), codigo, protocolo
    if codigo in CODIGOS_CDC_ENCONTRADO and protocolo:
        return CONFIRMADO, codigo, protocolo
    return INCONCLUSO, codigo, protocolo


def aplicar_consulta(documento, respuesta):
    """Lleva el documento a lo que SIFEN dijo, sólo si hay evidencia. Devuelve la evidencia.

    Nunca retrocede un documento: aprueba con protocolo a la vista, marca
    rechazado si SIFEN dice que no lo tiene, y si no está claro no lo toca.
    """
    evidencia, codigo, protocolo = evidencia_cdc(respuesta)
    if evidencia == INCONCLUSO:
        return evidencia
    mensaje = _buscar_clave(respuesta, {'dMsgRes', 'dMsg'})
    documento.estado = ESTADO_APROBADO if evidencia == CONFIRMADO else ESTADO_RECHAZADO
    documento.respuesta_codigo = codigo or documento.respuesta_codigo
    documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    if protocolo:
        documento.protocolo_autorizacion = protocolo
    db.session.commit()
    return evidencia


def verificar_antes_de_reenviar(documento, consultar):
    """Consulta el CDC de un envío que falló. Devuelve (seguir, error).

    `consultar` es `consultar_de` ya atado a la configuración: recibe el CDC
    y devuelve (respuesta, error). `seguir` es True sólo si SIFEN confirmó
    que no tiene el documento.
    """
    respuesta, error = consultar(documento.cdc)
    if error:
        return False, (f'No se pudo confirmar en SIFEN si el envío anterior llegó: {error}. '
                       'No se reenvía a ciegas; se reintenta en la próxima pasada.')
    evidencia, _codigo, _protocolo = evidencia_cdc(respuesta)
    if evidencia == AUSENTE:
        # Ojo: no se usa `aplicar_consulta` acá, que lo marcaría rechazado. Lo
        # que SIFEN no tiene es justamente lo que se va a reenviar.
        return True, None
    if evidencia == CONFIRMADO:
        # El envío anterior sí llegó y SIFEN lo autorizó: se adopta tal cual.
        aplicar_consulta(documento, respuesta)
        documento.respuesta_mensaje = 'Aprobado (el envío anterior había llegado a SIFEN).'
        documento.fecha_envio = documento.fecha_envio or datetime.utcnow()
        db.session.commit()
        return False, None
    return False, ('SIFEN no confirmó si tiene el documento. No se reenvía a ciegas; '
                   'se vuelve a consultar en la próxima pasada.')


__all__ = [
    'AUSENTE', 'CONFIRMADO', 'HORAS_MAXIMO_TRANSMISION', 'INCONCLUSO',
    'aplicar_consulta', 'evaluar_plazo', 'evidencia_cdc', 'verificar_antes_de_reenviar',
]
