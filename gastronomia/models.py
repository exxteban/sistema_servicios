"""Modelos base del modulo Gastronomia."""
from datetime import datetime

from app import db
import json
import secrets


class GastronomiaClienteConfig(db.Model):
    __tablename__ = 'gastronomia_cliente_config'

    id_config = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    modo_operacion = db.Column(db.String(30), nullable=False, default='servicios')
    gastronomia_activo = db.Column(db.Boolean, nullable=False, default=False)
    menu_tv_publico_activo = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    menu_tv_slug = db.Column(db.String(100), nullable=True, unique=True, index=True)
    menu_tv_titulo = db.Column(db.String(160), nullable=True)
    menu_tv_subtitulo = db.Column(db.String(240), nullable=True)
    menu_tv_tema = db.Column(db.String(40), nullable=False, default='clasico', server_default='clasico')
    menu_tv_modo_rotacion = db.Column(db.String(20), nullable=False, default='auto', server_default='auto')
    menu_tv_mostrar_precios = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    menu_tv_mostrar_agotados = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    menu_tv_intervalo_refresco_seg = db.Column(db.Integer, nullable=False, default=60, server_default='60')
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True)

    cliente = db.relationship('Cliente', backref=db.backref('gastronomia_config', uselist=False))
    actualizado_por = db.relationship('Usuario', foreign_keys=[actualizado_por_id])

    def __repr__(self):
        return f'<GastronomiaClienteConfig cliente={self.cliente_id} modo={self.modo_operacion}>'


class GastronomiaCategoria(db.Model):
    __tablename__ = 'gastronomia_categorias'

    id_categoria = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text)
    orden = db.Column(db.Integer, nullable=False, default=0)
    visible = db.Column(db.Boolean, nullable=False, default=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = db.relationship('Cliente', backref=db.backref('gastronomia_categorias', lazy='dynamic'))
    productos = db.relationship('GastronomiaProducto', backref='categoria', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'nombre', name='uq_gastronomia_categoria_cliente_nombre'),
    )

    def to_dict(self):
        data = {
            'id_categoria': self.id_categoria,
            'cliente_id': self.cliente_id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'orden': int(self.orden or 0),
            'visible': bool(self.visible),
            'activo': bool(self.activo),
        }
        return data


class GastronomiaProducto(db.Model):
    __tablename__ = 'gastronomia_productos'

    id_producto = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('gastronomia_categorias.id_categoria'), nullable=False, index=True)
    nombre = db.Column(db.String(160), nullable=False)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    imagen_url = db.Column(db.String(500))
    disponible = db.Column(db.Boolean, nullable=False, default=True)
    visible = db.Column(db.Boolean, nullable=False, default=True)
    visible_en_tv = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    publicado_tienda = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    control_stock_venta = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    stock_disponible = db.Column(db.Integer, nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = db.relationship('Cliente', backref=db.backref('gastronomia_productos', lazy='dynamic'))
    grupos_opciones = db.relationship('GastronomiaGrupoOpciones', backref='producto', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'nombre', name='uq_gastronomia_producto_cliente_nombre'),
    )

    def to_dict(self):
        data = {
            'id_producto': self.id_producto,
            'cliente_id': self.cliente_id,
            'categoria_id': self.categoria_id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'precio': float(self.precio or 0),
            'imagen_url': self.imagen_url,
            'disponible': bool(self.disponible),
            'visible': bool(self.visible),
            'visible_en_tv': bool(self.visible_en_tv),
            'publicado_tienda': bool(self.publicado_tienda),
            'control_stock_venta': bool(self.control_stock_venta),
            'stock_disponible': self.stock_disponible,
            'activo': bool(self.activo),
            'orden': int(self.orden or 0),
        }
        from app.services.tienda_promociones import (
            attach_gastronomia_promotion_to_product_data,
            get_active_gastronomia_product_promotion,
        )
        promotion = get_active_gastronomia_product_promotion(self.cliente_id, self.id_producto)
        return attach_gastronomia_promotion_to_product_data(self, data, promotion)


class GastronomiaGrupoOpciones(db.Model):
    __tablename__ = 'gastronomia_grupos_opciones'

    id_grupo = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'), nullable=False, index=True)
    nombre = db.Column(db.String(140), nullable=False)
    tipo = db.Column(db.String(40), nullable=False, default='extra')
    obligatorio = db.Column(db.Boolean, nullable=False, default=False)
    min_selecciones = db.Column(db.Integer, nullable=False, default=0)
    max_selecciones = db.Column(db.Integer, nullable=False, default=1)
    orden = db.Column(db.Integer, nullable=False, default=0)
    visible = db.Column(db.Boolean, nullable=False, default=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = db.relationship('Cliente')
    opciones = db.relationship('GastronomiaOpcionProducto', backref='grupo', lazy='dynamic')

    def to_dict(self, incluir_opciones=True):
        data = {
            'id_grupo': self.id_grupo,
            'cliente_id': self.cliente_id,
            'producto_id': self.producto_id,
            'nombre': self.nombre,
            'tipo': self.tipo,
            'obligatorio': bool(self.obligatorio),
            'min_selecciones': int(self.min_selecciones or 0),
            'max_selecciones': int(self.max_selecciones or 0),
            'orden': int(self.orden or 0),
            'visible': bool(self.visible),
            'activo': bool(self.activo),
        }
        if incluir_opciones:
            data['opciones'] = [opcion.to_dict() for opcion in self.opciones_ordenadas()]
        return data

    def opciones_ordenadas(self):
        return (
            self.opciones
            .filter_by(activo=True)
            .order_by(GastronomiaOpcionProducto.orden.asc(), GastronomiaOpcionProducto.nombre.asc())
            .all()
        )


class GastronomiaOpcionProducto(db.Model):
    __tablename__ = 'gastronomia_opciones_producto'

    id_opcion = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('gastronomia_grupos_opciones.id_grupo', ondelete='CASCADE'), nullable=False, index=True)
    nombre = db.Column(db.String(140), nullable=False)
    precio_delta = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    imagen_url = db.Column(db.String(500))
    disponible = db.Column(db.Boolean, nullable=False, default=True)
    visible = db.Column(db.Boolean, nullable=False, default=True)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = db.relationship('Cliente')

    def to_dict(self):
        return {
            'id_opcion': self.id_opcion,
            'cliente_id': self.cliente_id,
            'grupo_id': self.grupo_id,
            'nombre': self.nombre,
            'precio_delta': float(self.precio_delta or 0),
            'imagen_url': self.imagen_url,
            'disponible': bool(self.disponible),
            'visible': bool(self.visible),
            'orden': int(self.orden or 0),
            'activo': bool(self.activo),
        }


class GastronomiaMesa(db.Model):
    __tablename__ = 'gastronomia_mesas'

    id_mesa = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    nombre = db.Column(db.String(40), nullable=False)
    capacidad = db.Column(db.Integer, nullable=False, default=4)
    ubicacion = db.Column(db.String(80))
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = db.relationship('Cliente')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'nombre', name='uq_gastronomia_mesa_cliente_nombre'),
    )

    def to_dict(self):
        return {
            'id_mesa': self.id_mesa,
            'cliente_id': self.cliente_id,
            'nombre': self.nombre,
            'capacidad': int(self.capacidad or 0),
            'ubicacion': self.ubicacion,
            'orden': int(self.orden or 0),
            'activo': bool(self.activo),
        }


class GastronomiaPedido(db.Model):
    __tablename__ = 'gastronomia_pedidos'

    id_pedido = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    tipo_pedido = db.Column(db.String(30), nullable=False, default='mostrador')
    codigo_publico = db.Column(db.String(32), unique=True, index=True)
    mesa = db.Column(db.String(40))
    referencia_entrega = db.Column(db.String(80))
    nombre_cliente = db.Column(db.String(120))
    celular_cliente = db.Column(db.String(40))
    direccion_entrega = db.Column(db.String(240))
    tiempo_estimado_minutos = db.Column(db.Integer)
    repartidor_id = db.Column(db.Integer, db.ForeignKey('gastronomia_repartidores.id_repartidor'), nullable=True, index=True)
    estado = db.Column(db.String(30), nullable=False, default='abierto', index=True)
    notas = db.Column(db.Text)
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    costo_envio = db.Column(db.Numeric(15, 2), nullable=False, default=0, server_default='0')
    total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    fecha_envio_cocina = db.Column(db.DateTime)
    fecha_inicio_preparacion = db.Column(db.DateTime)
    fecha_listo = db.Column(db.DateTime)
    fecha_asignacion_delivery = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)

    cliente = db.relationship('Cliente')
    usuario = db.relationship('Usuario')
    repartidor = db.relationship('GastronomiaRepartidor')
    items = db.relationship('GastronomiaPedidoItem', backref='pedido', lazy='dynamic', cascade='all, delete-orphan')
    pago = db.relationship(
        'GastronomiaPedidoPago',
        backref='pedido',
        uselist=False,
        cascade='all, delete-orphan',
    )

    def to_dict(self):
        from gastronomia.services.stock_service import alertas_stock_pedido

        return {
            'id_pedido': self.id_pedido,
            'codigo_entrega': self.codigo_entrega,
            'cliente_id': self.cliente_id,
            'usuario_id': self.usuario_id,
            'tipo_pedido': self.tipo_pedido,
            'codigo_publico': self.codigo_publico,
            'url_seguimiento': f'/gastronomia/pedido/{self.codigo_publico}' if self.codigo_publico else None,
            'mesa': self.mesa,
            'referencia_entrega': self.referencia_entrega,
            'nombre_cliente': self.nombre_cliente,
            'celular_cliente': self.celular_cliente,
            'direccion_entrega': self.direccion_entrega,
            'tiempo_estimado_minutos': self.tiempo_estimado_minutos,
            'repartidor_id': self.repartidor_id,
            'repartidor': self.repartidor.to_dict() if self.repartidor else None,
            'estado': self.estado,
            'notas': self.notas,
            'subtotal': float(self.subtotal or 0),
            'costo_envio': float(self.costo_envio or 0),
            'total': float(self.total or 0),
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'fecha_envio_cocina': self.fecha_envio_cocina.isoformat() if self.fecha_envio_cocina else None,
            'fecha_inicio_preparacion': self.fecha_inicio_preparacion.isoformat() if self.fecha_inicio_preparacion else None,
            'fecha_listo': self.fecha_listo.isoformat() if self.fecha_listo else None,
            'fecha_asignacion_delivery': self.fecha_asignacion_delivery.isoformat() if self.fecha_asignacion_delivery else None,
            'fecha_entrega': self.fecha_entrega.isoformat() if self.fecha_entrega else None,
            'pagado': bool(self.pago),
            'estado_pago': 'pagado' if self.pago else 'pendiente',
            'pago': self.pago.to_dict() if self.pago else None,
            'items': [item.to_dict() for item in self.items.order_by(GastronomiaPedidoItem.id_item.asc()).all()],
            'alertas_stock': alertas_stock_pedido(self.id_pedido),
        }

    @property
    def codigo_entrega(self):
        return _codigo_entrega(self.id_pedido)


def _codigo_entrega(pedido_id) -> str:
    return f'#{int(pedido_id or 0):03d}'


def generar_codigo_publico_pedido() -> str:
    return secrets.token_urlsafe(6).replace('-', '').replace('_', '')[:10].upper()


class GastronomiaRepartidor(db.Model):
    __tablename__ = 'gastronomia_repartidores'

    id_repartidor = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    celular = db.Column(db.String(40))
    documento = db.Column(db.String(40))
    vehiculo = db.Column(db.String(80))
    patente = db.Column(db.String(30))
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default='1', index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = db.relationship('Cliente')
    usuario = db.relationship('Usuario')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'usuario_id', name='uq_gastronomia_repartidor_cliente_usuario'),
    )

    def to_dict(self):
        return {
            'id_repartidor': self.id_repartidor,
            'cliente_id': self.cliente_id,
            'usuario_id': self.usuario_id,
            'usuario': self.usuario.username if self.usuario else None,
            'nombre': self.nombre,
            'celular': self.celular,
            'documento': self.documento,
            'vehiculo': self.vehiculo,
            'patente': self.patente,
            'activo': bool(self.activo),
        }


class GastronomiaPedidoItem(db.Model):
    __tablename__ = 'gastronomia_pedido_items'

    id_item = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('gastronomia_pedidos.id_pedido', ondelete='CASCADE'), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('gastronomia_productos.id_producto'), nullable=False, index=True)
    canal_precio = db.Column(db.String(30))
    nombre_producto = db.Column(db.String(160), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    precio_original = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    descuento_linea = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    id_promocion_aplicada = db.Column(
        db.Integer,
        db.ForeignKey('tienda_promociones.id_promocion'),
        nullable=True,
        index=True,
    )
    promocion_descripcion = db.Column(db.String(255))
    cantidad_bonificada = db.Column(db.Integer, nullable=False, default=0)
    notas = db.Column(db.Text)
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    producto = db.relationship('GastronomiaProducto')
    modificadores = db.relationship(
        'GastronomiaPedidoItemModificador',
        backref='item',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id_item': self.id_item,
            'producto_id': self.producto_id,
            'canal_precio': self.canal_precio,
            'nombre_producto': self.nombre_producto,
            'cantidad': int(self.cantidad or 0),
            'precio_unitario': float(self.precio_unitario or 0),
            'precio_original': float(self.precio_original or 0),
            'descuento_linea': float(self.descuento_linea or 0),
            'id_promocion_aplicada': self.id_promocion_aplicada,
            'promocion_descripcion': self.promocion_descripcion,
            'cantidad_bonificada': int(self.cantidad_bonificada or 0),
            'notas': self.notas,
            'subtotal': float(self.subtotal or 0),
            'modificadores': [
                item.to_dict()
                for item in self.modificadores.order_by(GastronomiaPedidoItemModificador.id_modificador.asc()).all()
            ],
        }


class GastronomiaPedidoItemModificador(db.Model):
    __tablename__ = 'gastronomia_pedido_item_modificadores'

    id_modificador = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('gastronomia_pedido_items.id_item', ondelete='CASCADE'), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('gastronomia_grupos_opciones.id_grupo'), nullable=False)
    opcion_id = db.Column(db.Integer, db.ForeignKey('gastronomia_opciones_producto.id_opcion'), nullable=False)
    nombre_grupo = db.Column(db.String(140), nullable=False)
    nombre_opcion = db.Column(db.String(140), nullable=False)
    tipo_grupo = db.Column(db.String(40), nullable=False)
    precio_delta = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    def to_dict(self):
        return {
            'id_modificador': self.id_modificador,
            'grupo_id': self.grupo_id,
            'opcion_id': self.opcion_id,
            'nombre_grupo': self.nombre_grupo,
            'nombre_opcion': self.nombre_opcion,
            'tipo_grupo': self.tipo_grupo,
            'precio_delta': float(self.precio_delta or 0),
        }


class GastronomiaPedidoEvento(db.Model):
    __tablename__ = 'gastronomia_pedido_eventos'

    id_evento = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('gastronomia_pedidos.id_pedido', ondelete='CASCADE'), nullable=False, index=True)
    tipo = db.Column(db.String(60), nullable=False, index=True)
    payload_json = db.Column(db.Text)
    fecha_evento = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def get_payload(self):
        try:
            return json.loads(self.payload_json or '{}')
        except Exception:
            return {}

    def set_payload(self, data):
        self.payload_json = json.dumps(data or {}, ensure_ascii=False)

    def to_dict(self):
        return {
            'id_evento': self.id_evento,
            'cliente_id': self.cliente_id,
            'pedido_id': self.pedido_id,
            'tipo': self.tipo,
            'payload': self.get_payload(),
            'fecha_evento': self.fecha_evento.isoformat() if self.fecha_evento else None,
        }


class GastronomiaPedidoPago(db.Model):
    __tablename__ = 'gastronomia_pedido_pagos'

    id_pago = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    pedido_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_pedidos.id_pedido', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=True, index=True)
    id_metodo_pago = db.Column(db.Integer, db.ForeignKey('metodos_pago.id_metodo_pago'), nullable=True, index=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=True, index=True)
    id_movimiento_caja = db.Column(db.Integer, db.ForeignKey('movimientos_caja.id_movimiento_caja'), nullable=True, index=True)
    metodo_pago = db.Column(db.String(40), nullable=False, default='efectivo')
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    descuento_monto = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_cobrado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    observacion = db.Column(db.String(255))
    fecha_pago = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    cliente = db.relationship('Cliente')
    usuario = db.relationship('Usuario')
    sesion_caja = db.relationship('SesionCaja', foreign_keys=[id_sesion_caja])
    metodo = db.relationship('MetodoPago', foreign_keys=[id_metodo_pago])
    venta = db.relationship('Venta', foreign_keys=[id_venta])
    movimiento_caja = db.relationship('MovimientoCaja', foreign_keys=[id_movimiento_caja])

    def to_dict(self):
        return {
            'id_pago': self.id_pago,
            'cliente_id': self.cliente_id,
            'pedido_id': self.pedido_id,
            'usuario_id': self.usuario_id,
            'id_sesion_caja': self.id_sesion_caja,
            'id_metodo_pago': self.id_metodo_pago,
            'id_venta': self.id_venta,
            'id_movimiento_caja': self.id_movimiento_caja,
            'metodo_pago': self.metodo_pago,
            'subtotal': float(self.subtotal or 0),
            'descuento_monto': float(self.descuento_monto or 0),
            'total_cobrado': float(self.total_cobrado or 0),
            'observacion': self.observacion,
            'fecha_pago': self.fecha_pago.isoformat() if self.fecha_pago else None,
        }
