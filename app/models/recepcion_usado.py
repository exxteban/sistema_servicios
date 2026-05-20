from datetime import date, datetime

from app import db


class VendedorUsado(db.Model):
    __tablename__ = 'vendedores_usados'

    id_vendedor_usado = db.Column(db.Integer, primary_key=True)
    nombres_apellidos = db.Column(db.String(200), nullable=False, index=True)
    fecha_nacimiento = db.Column(db.Date)
    nacionalidad = db.Column(db.String(80))
    tipo_documento = db.Column(db.String(50), nullable=False)
    numero_documento = db.Column(db.String(50), nullable=False)
    numero_documento_normalizado = db.Column(db.String(50), nullable=False)
    estado_civil = db.Column(db.String(50))
    domicilio = db.Column(db.Text)
    referencia_domicilio = db.Column(db.String(200))
    barrio = db.Column(db.String(100))
    ciudad = db.Column(db.String(100))
    departamento = db.Column(db.String(100))
    telefono = db.Column(db.String(50))
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recepciones = db.relationship('RecepcionCompraUsado', backref='vendedor', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('tipo_documento', 'numero_documento_normalizado', name='uq_vendedor_usado_documento'),
        db.Index('ix_vendedores_usados_documento', 'tipo_documento', 'numero_documento_normalizado'),
    )

    @property
    def total_ventas_usados(self):
        return self.recepciones.count()

    def __repr__(self):
        return f'<VendedorUsado {self.tipo_documento} {self.numero_documento}>'


class RecepcionCompraUsado(db.Model):
    __tablename__ = 'recepciones_compra_usados'

    id_recepcion_compra_usado = db.Column(db.Integer, primary_key=True)
    numero_formulario = db.Column(db.Integer, unique=True, index=True)
    fecha_formulario = db.Column(db.Date, nullable=False, default=date.today, index=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    id_vendedor_usado = db.Column(db.Integer, db.ForeignKey('vendedores_usados.id_vendedor_usado'), nullable=False, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), unique=True)
    id_compra = db.Column(db.Integer, db.ForeignKey('compras.id_compra'), unique=True)
    id_movimiento_caja = db.Column(db.Integer, db.ForeignKey('movimientos_caja.id_movimiento_caja'))

    descripcion_producto = db.Column(db.Text, nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    color = db.Column(db.String(50))
    capacidad = db.Column(db.String(50))
    imei_serie = db.Column(db.String(120))
    accesorios = db.Column(db.Text)
    estado_equipo = db.Column(db.Text)

    monto_compra = db.Column(db.Numeric(15, 2), nullable=False)
    metodo_pago = db.Column(db.String(80), nullable=False)
    referencia_pago = db.Column(db.String(120))
    observaciones = db.Column(db.Text)
    lugar_firma = db.Column(db.String(120))
    domicilio_especial_vendedor = db.Column(db.Text)

    vendedor_nombres_apellidos = db.Column(db.String(200), nullable=False)
    vendedor_fecha_nacimiento = db.Column(db.Date)
    vendedor_nacionalidad = db.Column(db.String(80))
    vendedor_tipo_documento = db.Column(db.String(50), nullable=False)
    vendedor_numero_documento = db.Column(db.String(50), nullable=False)
    vendedor_estado_civil = db.Column(db.String(50))
    vendedor_domicilio = db.Column(db.Text)
    vendedor_referencia_domicilio = db.Column(db.String(200))
    vendedor_barrio = db.Column(db.String(100))
    vendedor_ciudad = db.Column(db.String(100))
    vendedor_departamento = db.Column(db.String(100))
    vendedor_telefono = db.Column(db.String(50))

    cantidad_impresiones = db.Column(db.Integer, nullable=False, default=0)
    fecha_ultima_impresion = db.Column(db.DateTime)

    usuario = db.relationship('Usuario', backref='recepciones_compra_usados')
    producto = db.relationship('Producto', backref=db.backref('recepcion_compra_usado', uselist=False))
    compra = db.relationship('Compra', backref=db.backref('recepcion_compra_usado', uselist=False))
    movimiento_caja = db.relationship('MovimientoCaja', backref='recepciones_compra_usados')

    __table_args__ = (
        db.Index('ix_recepcion_usado_vendedor_fecha', 'id_vendedor_usado', 'fecha_formulario'),
        {'sqlite_autoincrement': True},
    )

    @property
    def numero_formulario_display(self):
        numero = int(self.numero_formulario or 0)
        return f'{numero:06d}'

    @property
    def resumen_producto(self):
        partes = [
            (self.descripcion_producto or '').strip(),
            (self.marca or '').strip(),
            (self.modelo or '').strip(),
            (self.color or '').strip(),
            (self.capacidad or '').strip(),
        ]
        return ' | '.join([p for p in partes if p])

    def __repr__(self):
        return f'<RecepcionCompraUsado {self.numero_formulario_display}>'
