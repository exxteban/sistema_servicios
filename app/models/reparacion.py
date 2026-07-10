from datetime import datetime
from decimal import Decimal
from app import db


ESTADO_LABELS = {
    'pendiente': 'Pendiente',
    'diagnostico': 'En Diagnóstico',
    'espera_presupuesto': 'A confirmar presupuesto',
    'espera_repuesto': 'Espera repuesto',
    'espera_cliente': 'Espera cliente',
    'en_proceso': 'En proceso',
    'listo': 'Listo para entrega',
    'no_se_pudo': 'No se pudo',
    'entregado': 'Entregado',
    'cancelado': 'Cancelado',
    'antiguos': 'Antiguos',
}

class Reparacion(db.Model):
    __tablename__ = 'reparaciones'
    __table_args__ = (
        db.Index('ix_reparaciones_estado_fecha_ingreso', 'estado', 'fecha_ingreso'),
        db.Index('ix_reparaciones_cliente_fecha_ingreso', 'cliente_id', 'fecha_ingreso'),
    )

    id_reparacion = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False)
    id_usuario_vendedor = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), index=True)
    id_usuario_tecnico = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), index=True)
    
    # Datos del Equipo
    tipo_equipo = db.Column(db.String(50), nullable=False) # Celular, Tablet, Laptop, etc.
    marca_modelo = db.Column(db.String(100), nullable=False)
    imei_serie = db.Column(db.String(100)) # Opcional pero recomendado
    password_patron = db.Column(db.String(100)) # Texto descriptivo o código
    password_patron_cifrado = db.Column(db.String(255))
    patron_dibujo = db.Column(db.Text)
    accesorios = db.Column(db.Text) # JSON o texto separado por comas
    
    # Diagnóstico
    falla_reportada = db.Column(db.Text, nullable=False)
    diagnostico_tecnico = db.Column(db.Text)
    solucion = db.Column(db.Text) # Qué se le hizo
    
    # Estado y Costos
    # Estados: pendiente, diagnostico, espera_presupuesto, espera_repuesto, espera_cliente,
    # en_proceso, listo, no_se_pudo, entregado, cancelado, antiguos
    estado = db.Column(db.String(20), default='pendiente', index=True) 
    prioridad = db.Column(db.String(20), default='normal') # normal, urgente
    
    costo_estimado = db.Column(db.Numeric(10, 2), default=0)
    costo_final = db.Column(db.Numeric(10, 2), default=0)
    abono = db.Column(db.Numeric(10, 2), default=0) 
    
    # Fechas
    fecha_ingreso = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_toma_tecnico = db.Column(db.DateTime)
    fecha_estimada = db.Column(db.DateTime)
    fecha_estimada_hora = db.Column(db.Time)  # Hora estimada para entrega (complementa fecha_estimada)
    fecha_listo_tecnico = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)
    
    # Seguimiento público
    nota_cliente = db.Column(db.Text)  # Nota visible al cliente en seguimiento público
    mostrar_costo = db.Column(db.Boolean, default=False)  # Toggle para mostrar costo en seguimiento
    
    # Relaciones
    cliente = db.relationship('Cliente', backref=db.backref('reparaciones', lazy=True))
    vendedor = db.relationship('Usuario', foreign_keys=[id_usuario_vendedor])
    tecnico = db.relationship('Usuario', foreign_keys=[id_usuario_tecnico])
    detalles = db.relationship('DetalleReparacion', backref='reparacion', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Reparacion {self.id_reparacion} - {self.marca_modelo}>'

    @property
    def total_reparacion(self):
        """Calcula el total basado en los detalles (repuestos + mano de obra)"""
        return sum(d.subtotal for d in self.detalles)

    @property
    def costo_final_calculado(self):
        base = self.costo_final or Decimal('0')
        extras = Decimal('0')
        try:
            for det in self.detalles.filter_by(incluye_costo_final=True).all():
                extras += det.subtotal or Decimal('0')
        except Exception:
            pass
        return base + extras

    @property
    def saldo_pendiente(self):
        costo = float(self.costo_final_calculado or 0)
        if costo == 0:
            costo = float(self.costo_estimado or 0)
        return costo - float(self.abono or 0)

    @property
    def total_generado(self):
        return float(self.costo_final_calculado or 0)

    @property
    def mano_obra_generada(self):
        total = Decimal(self.costo_final or 0)
        try:
            for det in self.detalles.filter_by(incluye_costo_final=True).all():
                if det.es_servicio:
                    total += det.subtotal or Decimal('0')
        except Exception:
            pass
        return float(total or 0)

    @property
    def repuestos_generados(self):
        total = Decimal('0')
        try:
            for det in self.detalles.filter_by(incluye_costo_final=True).all():
                if not det.es_servicio:
                    total += det.subtotal or Decimal('0')
        except Exception:
            pass
        return float(total or 0)

    @property
    def estado_badge_color(self):
        colors = {
            'pendiente': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-100',
            'diagnostico': 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
            'espera_presupuesto': 'bg-orange-100 text-orange-800 dark:bg-orange-900/35 dark:text-orange-200',
            'espera_repuesto': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/35 dark:text-yellow-200',
            'espera_cliente': 'bg-teal-100 text-teal-800 dark:bg-teal-900/35 dark:text-teal-200',
            'en_proceso': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/35 dark:text-indigo-200',
            'listo': 'bg-green-100 text-green-800 dark:bg-green-900/35 dark:text-green-200',
            'no_se_pudo': 'bg-rose-100 text-rose-800 dark:bg-rose-900/35 dark:text-rose-200',
            'entregado': 'bg-purple-100 text-purple-800 dark:bg-purple-900/35 dark:text-purple-200',
            'cancelado': 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-200',
            'antiguos': 'bg-slate-100 text-slate-800 dark:bg-slate-800/70 dark:text-slate-200',
        }
        return colors.get(self.estado, 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-100')

    @property
    def estado_display(self):
        return ESTADO_LABELS.get(self.estado, (self.estado or '').replace('_', ' ').title())


class DetalleReparacion(db.Model):
    __tablename__ = 'detalle_reparaciones'

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_reparacion = db.Column(db.Integer, db.ForeignKey('reparaciones.id_reparacion'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    incluye_costo_final = db.Column(db.Boolean, default=False, nullable=False)
    
    # Snapshot del producto (por si cambia el nombre después)
    nombre_producto = db.Column(db.String(200))
    es_servicio = db.Column(db.Boolean, default=False)
    
    # Relación con Producto para acceder a datos vivos
    producto = db.relationship('Producto')
