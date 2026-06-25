from datetime import datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_TEST,
    ESTADO_GENERADO,
    TIPO_CONTRIBUYENTE_JURIDICA,
)


class FacturacionElectronicaConfig(db.Model):
    """Configuracion unica del emisor electronico (una instalacion = un negocio)."""

    __tablename__ = 'facturacion_electronica_config'

    id = db.Column(db.Integer, primary_key=True)

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
    id_venta = db.Column(
        db.Integer,
        db.ForeignKey('ventas.id_venta'),
        nullable=False,
        unique=True,
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

    respuesta_codigo = db.Column(db.String(10))
    respuesta_mensaje = db.Column(db.Text)
    protocolo_autorizacion = db.Column(db.String(20))

    fecha_generado = db.Column(db.DateTime)
    fecha_envio = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    venta = db.relationship('Venta')

    @property
    def cdc_formateado(self):
        if not self.cdc:
            return ''
        return ' '.join(self.cdc[i:i + 4] for i in range(0, len(self.cdc), 4))

    def __repr__(self):
        return f'<DocumentoElectronico venta={self.id_venta} estado={self.estado} cdc={self.cdc}>'


__all__ = ['FacturacionElectronicaConfig', 'DocumentoElectronico']
