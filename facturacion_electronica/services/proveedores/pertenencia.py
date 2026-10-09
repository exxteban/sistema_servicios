"""De qué proveedor es cada documento, para que el otro no lo toque.

Cambiar de proveedor está permitido mientras todo sea de prueba, y ahí
conviven documentos de los dos. Cada uno sólo se puede seguir con el
proveedor que lo transmitió. Pasó el 2026-10-03, al pasar Janelipy de la API
al motor propio:

- **El motor propio consultó por CDC una factura de la API** con su lote
  todavía en proceso. SIFEN contestó `0420` "no existe", que para el motor
  propio es definitivo, y la factura quedó marcada rechazada sin serlo.
- **Al revés es peor:** la API toma todo documento sin `api_documento_id`
  como "todavía no dado de alta" y lo emite. Una factura que el motor propio
  ya mandó a SIFEN se habría emitido dos veces.

Cómo se reconoce cada uno:

- **De la API:** tiene `api_documento_id`.
- **Del motor propio:** sin `api_documento_id`, con XML firmado local (la API
  nunca lo guarda) y con señales de que salió: estado transmitido o
  rechazado, fecha de envío o número de lote. Uno que sólo se generó y nunca
  salió no ata a nadie: la API lo puede emitir.
"""
from facturacion_electronica import ESTADO_RECHAZADO, ESTADOS_TRANSMITIDOS
from facturacion_electronica.services.proveedores import PROVEEDOR_API

ESTADOS_QUE_ATAN_AL_MOTOR_PROPIO = tuple(ESTADOS_TRANSMITIDOS) + (ESTADO_RECHAZADO,)


def emitido_por_api(documento):
    return bool(getattr(documento, 'api_documento_id', None))


def emitido_por_motor_propio(documento):
    if documento is None or emitido_por_api(documento) or not getattr(documento, 'xml_firmado', None):
        return False
    return bool(
        documento.estado in ESTADOS_QUE_ATAN_AL_MOTOR_PROPIO
        or getattr(documento, 'fecha_envio', None)
        or getattr(documento, 'api_lote_id', None)
    )


def error_de_otro_proveedor(documento, proveedor):
    """Mensaje si el documento es del proveedor que NO está activo; si no, None."""
    if documento is None:
        return None
    if proveedor == PROVEEDOR_API and emitido_por_motor_propio(documento):
        return ('Esta factura la transmitió el motor propio. Para consultarla o reenviarla, '
                'volvé a elegir "Motor propio" como proveedor.')
    if proveedor != PROVEEDOR_API and emitido_por_api(documento):
        return ('Esta factura la emitió la API externa. Para consultarla o reenviarla, '
                'volvé a elegir "API externa" como proveedor.')
    return None


def filtro_documentos_del_proveedor(proveedor):
    """Filtro ORM con los documentos que el proveedor activo puede tocar."""
    from app import db
    from facturacion_electronica.models import DocumentoElectronico as DE

    if proveedor != PROVEEDOR_API:
        return DE.api_documento_id.is_(None)
    return db.not_(db.and_(
        DE.api_documento_id.is_(None),
        DE.xml_firmado.isnot(None),
        db.or_(
            DE.estado.in_(ESTADOS_QUE_ATAN_AL_MOTOR_PROPIO),
            DE.fecha_envio.isnot(None),
            DE.api_lote_id.isnot(None),
        ),
    ))


__all__ = [
    'emitido_por_api', 'emitido_por_motor_propio', 'error_de_otro_proveedor',
    'filtro_documentos_del_proveedor',
]
