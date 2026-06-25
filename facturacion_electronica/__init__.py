CLAVE_FACTURACION_ELECTRONICA_ACTIVO = 'facturacion_electronica_activo'
DESC_FACTURACION_ELECTRONICA_ACTIVO = (
    'Activa el modulo de facturacion electronica (SIFEN / e-Kuatia): datos del emisor, '
    'firma digital y posterior emision de documentos electronicos.'
)

AMBIENTE_TEST = 'test'
AMBIENTE_PRODUCCION = 'produccion'
AMBIENTES = (AMBIENTE_TEST, AMBIENTE_PRODUCCION)

TIPO_CONTRIBUYENTE_FISICA = '1'
TIPO_CONTRIBUYENTE_JURIDICA = '2'
TIPOS_CONTRIBUYENTE = (
    (TIPO_CONTRIBUYENTE_FISICA, 'Persona fisica'),
    (TIPO_CONTRIBUYENTE_JURIDICA, 'Persona juridica'),
)

ESTADO_GENERADO = 'generado'
ESTADO_FIRMADO = 'firmado'
ESTADO_ENVIADO = 'enviado'
ESTADO_APROBADO = 'aprobado'
ESTADO_RECHAZADO = 'rechazado'
ESTADO_CANCELADO = 'cancelado'
ESTADO_ERROR = 'error'

# Estados desde los que ya no se debe regenerar el XML del documento.
ESTADOS_NO_REGENERABLES = (ESTADO_ENVIADO, ESTADO_APROBADO, ESTADO_CANCELADO)
