from datetime import datetime as _datetime

CLAVE_FACTURACION_ELECTRONICA_ACTIVO = 'facturacion_electronica_activo'
DESC_FACTURACION_ELECTRONICA_ACTIVO = (
    'Activa el modulo de facturacion electronica (SIFEN / e-Kuatia): datos del emisor, '
    'firma digital y posterior emision de documentos electronicos.'
)

AMBIENTE_TEST = 'test'
AMBIENTE_PRODUCCION = 'produccion'
AMBIENTES = (AMBIENTE_TEST, AMBIENTE_PRODUCCION)

# Cómo transmite el motor propio: de a uno y con respuesta en el momento
# (siRecepDE) o en un lote que SIFEN procesa aparte y se consulta después
# (siRecepLoteDE + siConsLoteDE), como hace la API externa. Vive en la tabla
# `configuracion` y no en una columna nueva de `facturacion_electronica_config`:
# `create_all()` no agrega columnas a una tabla que ya existe en los clientes.
CLAVE_MODO_ENVIO = 'facturacion_electronica_modo_envio'
MODO_ENVIO_SINCRONO = 'sincrono'
MODO_ENVIO_LOTE = 'lote'

TIPO_CONTRIBUYENTE_FISICA = '1'
TIPO_CONTRIBUYENTE_JURIDICA = '2'
TIPOS_CONTRIBUYENTE = (
    (TIPO_CONTRIBUYENTE_FISICA, 'Persona fisica'),
    (TIPO_CONTRIBUYENTE_JURIDICA, 'Persona juridica'),
)

# iTiDE: tipos de documento electrónico de SIFEN. El sistema emite factura y
# nota de crédito; los demás existen para leer lo que informe el proveedor.
TIPO_FACTURA = 1
TIPO_AUTOFACTURA = 4
TIPO_NOTA_CREDITO = 5
TIPO_NOTA_DEBITO = 6
TIPO_NOTA_REMISION = 7

# Los que el sistema sabe emitir. Cada uno lleva su propio correlativo dentro
# del timbrado: factura 001-001-0000001 y nota de crédito 001-001-0000001 son
# documentos distintos y cada rango cuenta por separado.
TIPOS_EMITIBLES = (TIPO_FACTURA, TIPO_NOTA_CREDITO)

# gCamNCDE: iMotEmi y su dDesMotEmi. El texto tiene que ser **exactamente** uno
# del catálogo TdDesMotEmi; SIFEN no acepta una descripción libre.
MOTIVOS_NOTA_CREDITO = (
    (1, 'Devolución y Ajuste de precios'),
    (2, 'Devolución'),
    (3, 'Descuento'),
    (4, 'Bonificación'),
    (5, 'Crédito incobrable'),
    (6, 'Recupero de costo'),
    (7, 'Recupero de gasto'),
    (8, 'Ajuste de precio'),
)
MOTIVO_NC_DEFECTO = 2

ESTADO_GENERADO = 'generado'
ESTADO_FIRMADO = 'firmado'
ESTADO_ENVIADO = 'enviado'
ESTADO_APROBADO = 'aprobado'
ESTADO_RECHAZADO = 'rechazado'
ESTADO_CANCELADO = 'cancelado'
# Sólo lo informa la API externa (rango de números inutilizado del lado del
# proveedor). No se fuerza a 'cancelado': son cosas distintas ante SIFEN.
ESTADO_INUTILIZADO = 'inutilizado'
ESTADO_ERROR = 'error'

# Estado **de la API externa** (no uno nuestro) que no tiene equivalente propio:
# la baja está pedida pero SIFEN todavía no la confirmó, y hasta que lo haga el
# DE sigue valiendo, así que de nuestro lado es 'aprobado'. Vive acá porque lo
# miran dos módulos que no pueden importarse entre sí (el proveedor API y el
# job de envío), y un literal suelto en cada uno se desincroniza.
ESTADO_API_CANCELACION_PENDIENTE = 'CANCELLATION_PENDING'

# Estados en los que el documento ya salió del sistema: SIFEN lo tiene (o lo
# tuvo). Son los que atan la instalación a su proveedor — los CDC y el
# protocolo son de quien los emitió. En el **motor propio**, generado/firmado/
# error nunca se transmitieron y no comprometen nada. En modo API, `firmado`
# es PENDING_BATCH: el DE ya existe del otro lado, con CDC, y su pipeline lo
# transmite en ~30s. Eso no entra acá (rompería el switch después de pruebas
# locales); se detecta por `api_documento_id` en `documento_en_proveedor`.
ESTADOS_TRANSMITIDOS = (ESTADO_ENVIADO, ESTADO_APROBADO, ESTADO_CANCELADO, ESTADO_INUTILIZADO)

# Estados desde los que ya no se debe regenerar el XML del documento.
ESTADOS_NO_REGENERABLES = (
    ESTADO_ENVIADO, ESTADO_APROBADO, ESTADO_CANCELADO, ESTADO_INUTILIZADO,
)

# CSC de maqueta: permite generar el QR del KuDE para demo sin el CSC real de
# la DNIT. El hash NO es válido contra SIFEN; sólo sirve para mostrar el KuDE.
CSC_DEMO_ID = '0001'
CSC_DEMO = 'ABCD0000000000000000000000000000'


# `reintentar_despues` tan lejos que el job de envío no lo va a tomar nunca
# más: la forma de decir "este fallo es definitivo" sin inventar un estado
# nuevo, que obligaría a revisar cada guarda y cada pantalla que hoy mira
# `estado`. Vive acá, igual que ESTADO_API_CANCELACION_PENDIENTE, porque lo
# miran dos módulos que no pueden importarse entre sí: el que decide que el
# fallo es definitivo (envio_service) y el que aplica el backoff común
# (envio_automatico), que si no lo pisaría con sus 10 minutos.
# Limpiarlo (ponerlo en NULL) alcanza para volver a habilitar el documento.
SIN_REINTENTO = _datetime(9999, 12, 31)
