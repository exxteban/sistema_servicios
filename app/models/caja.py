"""
Modelos de Caja, Sesiones y Movimientos
"""
from datetime import datetime
import json
from app import db
from sqlalchemy import and_, func


class Caja(db.Model):
    __tablename__ = 'cajas'
    
    id_caja = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    ubicacion = db.Column(db.String(100))
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    sesiones = db.relationship('SesionCaja', backref='caja', lazy='dynamic')
    
    def sesion_activa(self):
        """Retorna la sesión abierta de esta caja, o None"""
        return SesionCaja.query.filter_by(
            id_caja=self.id_caja, 
            estado='abierta'
        ).first()
    
    def __repr__(self):
        return f'<Caja {self.nombre}>'


class SesionCaja(db.Model):
    __tablename__ = 'sesiones_caja'
    
    id_sesion = db.Column(db.Integer, primary_key=True)
    id_caja = db.Column(db.Integer, db.ForeignKey('cajas.id_caja'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_apertura = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_cierre = db.Column(db.DateTime)
    monto_inicial = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    monto_final_declarado = db.Column(db.Numeric(15, 2))
    monto_final_sistema = db.Column(db.Numeric(15, 2))
    diferencia = db.Column(db.Numeric(15, 2))
    estado = db.Column(db.String(20), nullable=False, default='abierta')
    observaciones = db.Column(db.Text)
    id_usuario_cierre = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    
    # Relaciones
    ventas = db.relationship('Venta', backref='sesion_caja', lazy='dynamic')
    movimientos = db.relationship('MovimientoCaja', backref='sesion_caja', lazy='dynamic')
    usuario_cierre = db.relationship('Usuario', foreign_keys=[id_usuario_cierre])
    
    @property
    def esta_abierta(self):
        return self.estado == 'abierta'
    
    def calcular_total_efectivo(self):
        """Calcula el total en efectivo que debería haber en caja"""
        total = float(self.monto_inicial or 0)

        total_ingresos = (
            db.session.query(func.sum(MovimientoCaja.monto))
            .filter(MovimientoCaja.id_sesion_caja == self.id_sesion, MovimientoCaja.tipo == 'ingreso')
            .scalar()
        )
        total_egresos = (
            db.session.query(func.sum(MovimientoCaja.monto))
            .filter(MovimientoCaja.id_sesion_caja == self.id_sesion, MovimientoCaja.tipo == 'egreso')
            .scalar()
        )
        total += float(total_ingresos or 0) - float(total_egresos or 0)

        from app.models.venta import PagoVenta
        from app.services.caja_metodos import obtener_metodo_efectivo_id

        efectivo_id = obtener_metodo_efectivo_id(solo_activos=False)

        # Si no se pudo resolver el metodo efectivo, el cuadre fino de ventas
        # en efectivo y anulaciones no puede calcularse. Devolvemos el total
        # basado solo en movimientos de caja para no dar un numero incorrecto.
        if efectivo_id is None:
            return total

        pagos_efectivo = (
            db.session.query(func.sum(PagoVenta.monto))
            .join(Venta, PagoVenta.id_venta == Venta.id_venta)
            .filter(
                Venta.id_sesion_caja == self.id_sesion,
                Venta.estado == 'completada',
                PagoVenta.id_metodo_pago == efectivo_id,
            )
            .scalar()
        )
        ingresos_mov_venta = (
            db.session.query(func.sum(MovimientoCaja.monto))
            .join(
                Venta,
                and_(
                    Venta.id_venta == MovimientoCaja.referencia_id,
                    MovimientoCaja.referencia_tipo == 'venta',
                ),
            )
            .filter(
                MovimientoCaja.id_sesion_caja == self.id_sesion,
                MovimientoCaja.tipo == 'ingreso',
                MovimientoCaja.referencia_tipo == 'venta',
                Venta.estado == 'completada',
            )
            .scalar()
        )

        diferencia = float(pagos_efectivo or 0) - float(ingresos_mov_venta or 0)
        total += diferencia

        from app.services.caja_cuadre import obtener_resumen_anulaciones_ventas_sesion

        anulaciones_ctx = obtener_resumen_anulaciones_ventas_sesion(self, efectivo_id=efectivo_id)
        faltante_anulaciones = float(anulaciones_ctx['efectivo_faltante'] or 0.0)
        if faltante_anulaciones > 0:
            total -= faltante_anulaciones

        return total
    
    def __repr__(self):
        return f'<SesionCaja {self.id_sesion} - {self.estado}>'


# Importación tardía para evitar circular
from app.models.venta import Venta


class MovimientoCaja(db.Model):
    __tablename__ = 'movimientos_caja'
    
    id_movimiento_caja = db.Column(db.Integer, primary_key=True)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # ingreso, egreso
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    motivo = db.Column(db.String(200), nullable=False)
    referencia_tipo = db.Column(db.String(50))
    referencia_id = db.Column(db.Integer)
    fecha_movimiento = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    usuario = db.relationship('Usuario', backref='movimientos_caja')
    
    def __repr__(self):
        return f'<MovimientoCaja {self.tipo} {self.monto}>'


class ColaCobro(db.Model):
    __tablename__ = 'cola_cobro'

    id = db.Column(db.Integer, primary_key=True)
    tipo_origen = db.Column(db.String(20), nullable=False, index=True)
    id_origen = db.Column(db.Integer, index=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=True, index=True)
    monto_total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    id_usuario_origen = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    id_usuario_destino = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    fecha_envio = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    fecha_toma = db.Column(db.DateTime)
    fecha_cobro = db.Column(db.DateTime)
    metadata_json = db.Column(db.Text)

    cliente = db.relationship('Cliente', foreign_keys=[id_cliente])
    usuario_origen = db.relationship('Usuario', foreign_keys=[id_usuario_origen], backref='cola_cobro_enviadas')
    usuario_destino = db.relationship('Usuario', foreign_keys=[id_usuario_destino], backref='cola_cobro_recibidas')

    def get_metadata(self):
        try:
            if not self.metadata_json:
                return {}
            return json.loads(self.metadata_json)
        except Exception:
            return {}

    def set_metadata(self, data):
        try:
            self.metadata_json = json.dumps(data or {}, ensure_ascii=False)
        except Exception:
            self.metadata_json = '{}'

    def __repr__(self):
        return f'<ColaCobro #{self.id} {self.tipo_origen}:{self.estado}>'
