import json
from datetime import date, datetime, timedelta

from app import db


class PresupuestoEmpresarial(db.Model):
    __tablename__ = 'presupuestos_empresariales'

    id_presupuesto_empresarial = db.Column(db.Integer, primary_key=True)
    numero_presupuesto = db.Column(db.Integer, unique=True, nullable=False, index=True)
    fecha_emision = db.Column(db.Date, nullable=False, default=date.today, index=True)
    validez_dias = db.Column(db.Integer, nullable=False, default=7)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), index=True)

    destinatario_nombre = db.Column(db.String(200), nullable=False, index=True)
    destinatario_ruc = db.Column(db.String(50), index=True)
    destinatario_contacto = db.Column(db.String(120))
    destinatario_telefono = db.Column(db.String(50))
    destinatario_email = db.Column(db.String(120))
    destinatario_direccion = db.Column(db.Text)

    asunto = db.Column(db.String(200), nullable=False)
    moneda = db.Column(db.String(10), nullable=False, default='PYG')
    items_json = db.Column(db.Text, nullable=False, default='[]')
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    descuento = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    observaciones = db.Column(db.Text)
    condiciones = db.Column(db.Text)

    cantidad_impresiones = db.Column(db.Integer, nullable=False, default=0)
    fecha_ultima_impresion = db.Column(db.DateTime)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = db.relationship('Usuario', backref='presupuestos_empresariales')
    cliente = db.relationship('Cliente', backref='presupuestos_empresariales')

    __table_args__ = (
        db.Index('ix_presupuesto_empresarial_cliente_fecha', 'id_cliente', 'fecha_emision'),
        {'sqlite_autoincrement': True},
    )

    @property
    def numero_presupuesto_display(self):
        numero = int(self.numero_presupuesto or 0)
        return f'{numero:06d}'

    @property
    def items(self):
        try:
            items = json.loads(self.items_json or '[]')
        except (TypeError, ValueError):
            items = []
        return items if isinstance(items, list) else []

    @property
    def valido_hasta(self):
        base = self.fecha_emision or date.today()
        dias = max(int(self.validez_dias or 0), 0)
        return base + timedelta(days=dias)

    def set_items(self, items):
        self.items_json = json.dumps(items or [], ensure_ascii=False)

    def __repr__(self):
        return f'<PresupuestoEmpresarial {self.numero_presupuesto_display}>'
