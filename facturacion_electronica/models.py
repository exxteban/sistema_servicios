from datetime import datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_TEST,
    ESTADO_GENERADO,
    TIPO_CONTRIBUYENTE_JURIDICA,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)


class FacturacionElectronicaConfig(db.Model):
    """Configuracion unica del emisor electronico (una instalacion = un negocio)."""

    __tablename__ = 'facturacion_electronica_config'

    id = db.Column(db.Integer, primary_key=True)
    proveedor = db.Column(db.String(20), nullable=False, default='propio', server_default='propio')
    api_url = db.Column(db.String(500))
    api_client_id = db.Column(db.String(128))
    # client_secret cifrado con el mismo crypto.cifrar que la clave del .p12.
    api_credenciales = db.Column(db.Text)

    ambiente = db.Column(db.String(12), nullable=False, default=AMBIENTE_TEST)

    razon_social = db.Column(db.String(255))
    nombre_fantasia = db.Column(db.String(255))
    ruc = db.Column(db.String(15))
    dv_ruc = db.Column(db.String(2))
    tipo_contribuyente = db.Column(db.String(2), nullable=False, default=TIPO_CONTRIBUYENTE_JURIDICA)
    tipo_regimen = db.Column(db.String(2))

    timbrado_numero = db.Column(db.String(20))
    timbrado_fecha_inicio = db.Column(db.Date)
    establecimiento = db.Column(db.String(3), nullable=False, default='001')
    punto_expedicion = db.Column(db.String(3), nullable=False, default='001')

    actividad_economica_codigo = db.Column(db.String(20))
    actividad_economica_desc = db.Column(db.String(255))

    departamento_codigo = db.Column(db.String(5))
    departamento_desc = db.Column(db.String(120))
    distrito_codigo = db.Column(db.String(6))
    distrito_desc = db.Column(db.String(120))
    ciudad_codigo = db.Column(db.String(8))
    ciudad_desc = db.Column(db.String(120))
    direccion = db.Column(db.String(255))
    numero_casa = db.Column(db.String(20))
    telefono = db.Column(db.String(40))
    email = db.Column(db.String(120))

    cert_path = db.Column(db.String(500))
    cert_nombre_original = db.Column(db.String(255))
    cert_password = db.Column(db.String(255))

    csc = db.Column(db.String(64))
    csc_id = db.Column(db.String(8))

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    @classmethod
    def obtener(cls):
        config = db.session.get(cls, 1)
        if config is None:
            config = cls(id=1)
            db.session.add(config)
            db.session.commit()
        return config

    @property
    def certificado_cargado(self):
        return bool(self.cert_path)

    def __repr__(self):
        return f'<FacturacionElectronicaConfig ruc={self.ruc} ambiente={self.ambiente}>'


class DocumentoElectronico(db.Model):
    """Documento electrónico generado a partir de una venta (un DE por venta)."""

    __tablename__ = 'facturacion_electronica_documentos'

    id = db.Column(db.Integer, primary_key=True)
    # Sin unique: una venta puede tener varios DE a lo largo del tiempo (una
    # factura cancelada + su re-emisión). El vigente es el de mayor id.
    id_venta = db.Column(
        db.Integer,
        db.ForeignKey('ventas.id_venta'),
        nullable=False,
        index=True,
    )

    tipo_documento = db.Column(db.Integer)
    cdc = db.Column(db.String(44), index=True)
    establecimiento = db.Column(db.String(3))
    punto = db.Column(db.String(3))
    numero = db.Column(db.String(7))
    timbrado = db.Column(db.String(20))
    codigo_seguridad = db.Column(db.String(9))
    ambiente = db.Column(db.String(12))

    estado = db.Column(db.String(20), nullable=False, default=ESTADO_GENERADO, index=True)

    xml = db.Column(db.Text)
    xml_firmado = db.Column(db.Text)
    xml_qr = db.Column(db.Text)
    qr_url = db.Column(db.Text)

    # Cabe el codigo numerico de SIFEN (4 digitos) y tambien el estado de la
    # API externa, que es una palabra: 'CANCELLATION_PENDING' son 20 caracteres
    # y en MySQL estricto un VARCHAR(10) no trunca, revienta el INSERT.
    respuesta_codigo = db.Column(db.String(40))
    respuesta_mensaje = db.Column(db.Text)
    # JSON completo de la última respuesta de SIFEN (envío/consulta/cancelación),
    # para diagnosticar rechazos aunque el parseo de campos conocidos falle.
    respuesta_raw = db.Column(db.Text)
    protocolo_autorizacion = db.Column(db.String(20))

    # Identificadores del lado de la API externa (vacíos con el motor propio).
    api_documento_id = db.Column(db.String(36), index=True)
    # Sin uso desde que el loteo lo hace el pipeline del proveedor solo. Se
    # deja la columna: quitarla obliga a un ALTER en cada cliente y no gana nada.
    api_lote_id = db.Column(db.String(36))
    # Clave de idempotencia del alta: estable entre reintentos, para que un
    # corte de red no emita dos veces el mismo número.
    api_idempotency_key = db.Column(db.String(120))

    # Nota de crédito: a qué documento corrige y de qué devolución salió.
    # `id_devolucion` no lleva FK a propósito: el módulo de FE no depende del
    # de devoluciones, y una instalación vieja puede no tener esa tabla.
    id_documento_asociado = db.Column(
        db.Integer, db.ForeignKey('facturacion_electronica_documentos.id'), index=True,
    )
    id_devolucion = db.Column(db.Integer, index=True)
    nc_motivo = db.Column(db.Integer)
    nc_motivo_desc = db.Column(db.String(60))

    motivo_cancelacion = db.Column(db.Text)
    xml_cancelacion = db.Column(db.Text)

    # Momento a partir del cual el job puede volver a tocar este documento.
    # Es el backoff de los fallos de **transporte**, que no cambian el estado
    # fiscal: firmar con el Node caído deja el DE en 'generado', y sin esta
    # marca el job lo reintenta en cada pasada para siempre (el backoff por
    # `updated_at` sólo alcanza a los que quedaron en 'error').
    reintentar_despues = db.Column(db.DateTime)

    fecha_generado = db.Column(db.DateTime)
    fecha_envio = db.Column(db.DateTime)
    fecha_cancelado = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    venta = db.relationship('Venta')
    documento_asociado = db.relationship('DocumentoElectronico', remote_side=[id])

    @property
    def es_nota_credito(self):
        return self.tipo_documento == TIPO_NOTA_CREDITO

    @property
    def numero_formateado(self):
        if not (self.establecimiento and self.punto and self.numero):
            return ''
        return f'{self.establecimiento}-{self.punto}-{self.numero}'

    @property
    def cdc_formateado(self):
        if not self.cdc:
            return ''
        return ' '.join(self.cdc[i:i + 4] for i in range(0, len(self.cdc), 4))

    def __repr__(self):
        return f'<DocumentoElectronico venta={self.id_venta} estado={self.estado} cdc={self.cdc}>'


class SecuenciaNumeracionDE(db.Model):
    """Correlativo de numeración del DE por establecimiento + punto de expedición.

    SIFEN exige numeración correlativa por establecimiento y punto dentro del
    rango del timbrado; la lleva el contribuyente, no SIFEN. La granularidad
    (establecimiento, punto) es la que pide el estándar: hoy hay una sola fila,
    pero si se habilita otro punto se agrega una fila sin tocar el código.
    """

    __tablename__ = 'facturacion_electronica_secuencia'
    __table_args__ = (
        db.UniqueConstraint(
            'tipo_documento', 'establecimiento', 'punto',
            name='uq_fe_secuencia_tipo_estab_punto',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    # iTiDE: cada tipo de documento tiene su propio rango dentro del timbrado.
    tipo_documento = db.Column(
        db.Integer, nullable=False, default=TIPO_FACTURA, server_default='1',
    )
    establecimiento = db.Column(db.String(3), nullable=False)
    punto = db.Column(db.String(3), nullable=False)
    ultimo_numero = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return (f'<SecuenciaNumeracionDE tipo={self.tipo_documento} '
                f'{self.establecimiento}-{self.punto}={self.ultimo_numero}>')


__all__ = ['FacturacionElectronicaConfig', 'DocumentoElectronico', 'SecuenciaNumeracionDE']
