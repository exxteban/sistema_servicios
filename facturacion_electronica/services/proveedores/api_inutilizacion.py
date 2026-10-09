"""Inutilización de un número quemado contra la API externa.

El caso es el mismo que en el motor propio: el correlativo se reservó al
generar el DE y ese DE nunca llegó a SIFEN. El número ya salió de la
secuencia, y si nadie avisa el timbrado queda con un hueco que ante la DNIT
no tiene explicación.

Lo que cambia es el transporte. Acá no armamos ni firmamos el evento: se pide
`POST /sifen/inutilizations/` (scope `events`), que recibe un **rango** de
números y devuelve un `SifenEventRead`. Se informa **un número por evento**
(`range_from` == `range_to`): los huecos no son contiguos salvo por
casualidad, y un rango que abarque un número emitido al medio lo estaría
inutilizando sin que nadie lo pida.

Dos cosas que el motor propio no tiene que mirar y acá deciden todo:

- **El DE puede existir del otro lado.** Su pipeline lotea y transmite solo
  cada 30 segundos. Un documento que todavía vive allá puede salir en la
  próxima pasada, así que inutilizar su número sería quemar un número que iba
  a ser válido. Se relee el estado remoto antes de decidir y se niega si sigue
  vivo.
- **Sandbox no transmite.** En ese modo su API construye, firma y valida el
  evento contra el XSD, pero no lo manda: el hueco seguiría sin justificar y
  la pantalla estaría diciendo que se informó algo que SIFEN nunca vio.
"""
from datetime import datetime

from app import db
from facturacion_electronica import ESTADO_INUTILIZADO, TIPO_FACTURA
from facturacion_electronica.services.guarda import (
    error_motivo_inutilizacion,
    error_numero_no_inutilizable,
    error_timbrado_inutilizacion,
)
from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_documento import serializar
from facturacion_electronica.services.proveedores.api_perfil import (
    normalizar_codigo,
    obtener_perfil,
)
from facturacion_electronica.services.proveedores.api_rechazo import texto_resultado

# Estados de la API en los que el documento remoto todavía puede terminar en
# SIFEN. `REJECTED` y `VOIDED` no están: ahí el número ya no va a salir.
ESTADOS_REMOTOS_VIVOS = (
    'DRAFT', 'PREPARING', 'PENDING_BATCH', 'BATCHED', 'SUBMITTED',
    'APPROVED', 'CANCELLATION_PENDING', 'RETRYABLE_ERROR',
)

# El `result` del evento es un objeto libre en su OpenAPI (igual que el de los
# lotes), así que el veredicto se lee por el texto. Ante la duda se toma el
# 201 como bueno: su endpoint es síncrono —registra el evento y responde—, no
# queda nada pendiente que consultar después.
_PALABRAS_DE_RECHAZO = ('rechaz', 'no autoriz', 'inválid', 'invalid', 'denegad')

MENSAJE_REMOTO_VIVO = (
    'Ese número ya está dado de alta en la API y su pipeline lo transmite solo. '
    'No se puede inutilizar un número que todavía puede salir: esperá a que el '
    'documento quede aprobado —y entonces cancelalo o emití una nota de crédito— '
    'o a que SIFEN lo rechace.'
)

MENSAJE_SANDBOX = (
    'La empresa está en modo sandbox en la API: el evento de inutilización se firma '
    'y se valida, pero no se transmite a SIFEN, así que el hueco del timbrado '
    'seguiría sin justificar. Pedile al proveedor que pase la empresa a test o '
    'producción y volvé a intentarlo.'
)


def _rechazado(mensaje):
    texto = (mensaje or '').lower()
    return any(palabra in texto for palabra in _PALABRAS_DE_RECHAZO)


def _estado_remoto_vivo(config, documento, refrescar):
    """Error si el DE sigue vigente del otro lado. None si se puede seguir."""
    if not documento.api_documento_id:
        return None

    _documento, error = refrescar(documento)
    if error:
        # Sin confirmación no se decide: quemar el número a ciegas no se
        # deshace, y un timeout de su lado no dice nada sobre el documento.
        return (f'No se pudo confirmar en la API el estado del documento antes de '
                f'inutilizar su número: {error}')

    # El refresco pudo traer un estado que ya no admite la inutilización
    # (aprobado, cancelado, o inutilizado por alguien más).
    error_numero = error_numero_no_inutilizable(documento)
    if error_numero:
        return error_numero

    if (documento.respuesta_codigo or '').upper() in ESTADOS_REMOTOS_VIVOS:
        return MENSAJE_REMOTO_VIVO
    return None


def inutilizar_numero(config, documento, motivo, refrescar):
    """Informa a SIFEN, vía la API, que este número no se va a usar.

    `refrescar(documento)` es el relectura del documento remoto del proveedor
    —se recibe en vez de importarse para no atar este módulo a `api.py`, que
    ya lo importa a él—. Devuelve (documento, error) como todo el módulo.
    """
    error_numero = error_numero_no_inutilizable(documento)
    if error_numero:
        return documento, error_numero

    motivo = (motivo or '').strip()
    error_motivo = error_motivo_inutilizacion(motivo)
    if error_motivo:
        return documento, error_motivo

    error_vivo = _estado_remoto_vivo(config, documento, refrescar)
    if error_vivo:
        return documento, error_vivo

    perfil, error = obtener_perfil(config)
    if error:
        return documento, error
    if (perfil.get('sifen_mode') or '').strip().lower() == 'sandbox':
        return documento, MENSAJE_SANDBOX

    timbrado = (documento.timbrado or config.timbrado_numero or '').strip()
    error_timbrado = error_timbrado_inutilizacion(timbrado)
    if error_timbrado:
        return documento, error_timbrado

    numero = int(documento.numero)
    cuerpo = {
        'stamp_number': timbrado,
        'establishment': normalizar_codigo(documento.establecimiento or config.establecimiento),
        'expedition_point': normalizar_codigo(documento.punto or config.punto_expedicion),
        'document_type': documento.tipo_documento or TIPO_FACTURA,
        'range_from': numero,
        'range_to': numero,
        'motive': motivo,
    }
    evento, error = api_client.solicitar(
        config, 'POST', '/sifen/inutilizations/', json=cuerpo,
        timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
    )
    if error:
        return documento, error

    evento = evento if isinstance(evento, dict) else {}
    codigo, mensaje = texto_resultado(evento.get('result'))
    detalle = ' - '.join(parte for parte in (codigo, mensaje) if parte)

    documento.respuesta_raw = serializar(evento)
    if _rechazado(mensaje):
        documento.respuesta_mensaje = (
            f'SIFEN no aprobó la inutilización: {detalle}'
        )[:2000]
        db.session.commit()
        return documento, documento.respuesta_mensaje

    # `motivo_cancelacion` y `fecha_cancelado` guardan el evento sea cual sea,
    # igual que en el motor propio: un DE tiene a lo sumo uno de los dos (o se
    # transmitió y se cancela, o no se transmitió y se inutiliza).
    documento.estado = ESTADO_INUTILIZADO
    documento.respuesta_codigo = 'VOIDED'
    documento.respuesta_mensaje = (detalle or 'Inutilización informada a SIFEN.')[:2000]
    documento.motivo_cancelacion = motivo
    documento.fecha_cancelado = datetime.utcnow()
    db.session.commit()
    return documento, None


__all__ = ['inutilizar_numero', 'ESTADOS_REMOTOS_VIVOS', 'MENSAJE_REMOTO_VIVO', 'MENSAJE_SANDBOX']
