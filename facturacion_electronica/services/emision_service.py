"""Fachada de la emisión con el motor propio: factura y nota de crédito.

El código vive repartido por responsabilidad; este módulo sólo re-exporta los
nombres para que los imports existentes sigan funcionando:

- `documento_consulta`: qué documento es el vigente, CDC y fecha de emisión.
- `generacion_service`: XML de la factura, firma y QR.
- `nota_credito_service`: XML de la nota de crédito (devolución y anulación).
- `envio_service`: transmisión a SIFEN y consulta por CDC.
- `eventos_service`: cancelación e inutilización.
- `respuesta_sifen`: lectura de las respuestas de SIFEN.

Para simular el microservicio o la config en una prueba, el `patch` va sobre
el módulo que hace la llamada, no sobre esta fachada.
"""
from facturacion_electronica import SIN_REINTENTO
from facturacion_electronica.services.documento_consulta import (
    _CDC_RE,
    extraer_cdc,
    facturas_de_ventas,
    fecha_emision,
    nota_credito_de_correccion,
    nota_credito_de_devolucion,
    notas_credito,
    obtener_documento,
)
from facturacion_electronica.services.envio_service import (
    HORAS_LIMITE_ENVIO,
    _ambiente_setapi,
    consultar_documento,
    enviar_documento,
)
from facturacion_electronica.services.eventos_service import (
    HORAS_LIMITE_CANCELACION,
    _fecha_firma_evento,
    cancelar_documento,
    inutilizar_documento,
)
from facturacion_electronica.services.generacion_service import (
    emitir_para_pos,
    firmar_documento,
    generar_documento,
    generar_qr_documento,
)
from facturacion_electronica.services.nota_credito_service import (
    _completar_nota_credito,
    emitir_nota_credito,
    emitir_nota_credito_correccion,
    generar_nota_credito,
    generar_nota_credito_correccion,
)
from facturacion_electronica.services.respuesta_sifen import (
    _buscar_clave,
    _detalle_sifen,
    _interpretar_respuesta,
    _nombre_local,
    _serializar_respuesta,
)


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
