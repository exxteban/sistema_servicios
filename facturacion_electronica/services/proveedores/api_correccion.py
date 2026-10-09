"""Corregir y reenviar una factura que SIFEN rechazó (API 1.7.0).

`POST /sifen/electronic-documents/{id}/correct/` reencola el MISMO documento
—mismo id, CDC, número y código de seguridad— con los datos que mande el
body. Antes de esto un rechazo era terminal: el número quedaba perdido y la
única salida era inutilizarlo y emitir otro documento.

Reglas del contrato que deciden cómo se llama:

- El body es el mismo de la emisión. Los campos que forman el CDC (timbrado,
  establecimiento, punto, número y la FECHA de `issued_at`) tienen que ser los
  del original, y lo son: salen del documento y de la fecha de la venta, que
  no cambian. Lo que sí cambia es lo que se corrigió en la ficha del cliente.
- Pide una `Idempotency-Key` distinta de la de la emisión. Repetir la misma
  clave de corrección devuelve el resultado anterior sin reencolar nada.
- Sólo facturas (`document_type=1`) en `REJECTED`.
"""
import hashlib
import json

from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_documento import clave_idempotencia

# Largo máximo de la clave del lado de la API (`DocumentCorrectionAttempt`).
LARGO_MAXIMO_CLAVE = 100


def _ultimo_lote(documento):
    """Lote del último rechazo: distingue una corrección de la siguiente."""
    try:
        remoto = json.loads(documento.respuesta_raw or '{}')
    except (TypeError, ValueError):
        remoto = {}
    sifen_result = remoto.get('sifen_result') if isinstance(remoto, dict) else None
    if isinstance(sifen_result, dict) and sifen_result.get('batch_id'):
        return str(sifen_result['batch_id'])
    return documento.api_lote_id or ''


def clave_correccion(documento, cuerpo):
    """Clave de la corrección: estable al reintentar, nueva ante cada rechazo.

    Sale del cuerpo y del lote que lo rechazó. Reintentar la misma corrección
    (se cortó la red) repite la clave y la API no duplica nada. Si lo
    corregido vuelve a rechazarse, el lote es otro y la clave también: con la
    anterior, la API devolvería el resultado viejo en vez de reencolar.
    """
    huella = hashlib.sha256(
        (json.dumps(cuerpo, sort_keys=True, default=str) + _ultimo_lote(documento))
        .encode('utf-8')
    ).hexdigest()[:16]
    sufijo = f'-corr-{huella}'
    base = clave_idempotencia(documento)[:LARGO_MAXIMO_CLAVE - len(sufijo)]
    return base + sufijo


def corregir_rechazado(config, documento, cuerpo):
    """POST de la corrección. Devuelve (remoto, error) como `api_client.solicitar`."""
    return api_client.solicitar(
        config, 'POST',
        f'/sifen/electronic-documents/{documento.api_documento_id}/correct/',
        json=cuerpo,
        headers={'Idempotency-Key': clave_correccion(documento, cuerpo)},
        timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
    )


__all__ = ['clave_correccion', 'corregir_rechazado']
