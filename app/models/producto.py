"""
Modelos de Producto, Categoría, Kits y Repuestos
"""
from datetime import datetime
from app import db


class Categoria(db.Model):
    __tablename__ = 'categorias'
    
    id_categoria = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    categoria_padre = db.Column(db.Integer, db.ForeignKey('categorias.id_categoria'))
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    productos = db.relationship('Producto', backref='categoria', lazy='dynamic')
    subcategorias = db.relationship('Categoria', backref=db.backref('padre', remote_side=[id_categoria]))
    
    def __repr__(self):
        return f'<Categoria {self.nombre}>'


class Producto(db.Model):
    __tablename__ = 'productos'
    __table_args__ = (
        db.Index('ix_productos_activo_publicado_orden', 'activo', 'publicado_tienda', 'orden_tienda'),
    )
    
    id_producto = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False, index=True)
    codigo_proveedor = db.Column(db.String(50))
    codigo_barras = db.Column(db.String(50), index=True)  # Nuevo campo
    nombre = db.Column(db.String(200), nullable=False, index=True)
    descripcion = db.Column(db.Text)
    id_categoria = db.Column(db.Integer, db.ForeignKey('categorias.id_categoria'), nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=True, index=True)
    id_proveedor_principal = db.Column(db.Integer, db.ForeignKey('proveedores.id_proveedor'))
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    color = db.Column(db.String(50))
    capacidad = db.Column(db.String(50))
    
    # Precios
    precio_compra = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    precio_venta = db.Column(db.Numeric(10, 2), nullable=False)
    precio_mayorista = db.Column(db.Numeric(10, 2))
    
    # Impuestos
    porcentaje_iva = db.Column(db.Integer, nullable=False, default=10)
    
    # Stock
    stock_actual = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=5)
    stock_maximo = db.Column(db.Integer)
    
    # Tipo
    es_kit = db.Column(db.Boolean, default=False)
    kit_stock_propio = db.Column(db.Boolean, default=False)
    es_servicio = db.Column(db.Boolean, default=False)
    
    # Control
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    id_usuario_modificacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))

    # Tienda Online
    publicado_tienda = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    descripcion_tienda = db.Column(db.Text, nullable=True)
    orden_tienda = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    vistas_tienda = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    es_destacado_tienda = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    es_oferta_tienda = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    precio_anterior_tienda = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Relaciones
    componentes = db.relationship('ProductoCompuesto', 
                                   foreign_keys='ProductoCompuesto.id_producto_kit',
                                   backref='kit', lazy='dynamic')
    repuestos = db.relationship('ProductoRepuesto',
                                 foreign_keys='ProductoRepuesto.id_producto_principal',
                                 backref='producto_principal', lazy='dynamic')
    movimientos_stock = db.relationship('MovimientoStock', backref='producto', lazy='dynamic')
    cliente = db.relationship('Cliente', backref='productos', lazy='select')
    precios_opciones = db.relationship(
        'ProductoPrecioOpcion',
        backref='producto',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    imagenes_tienda = db.relationship(
        'ProductoImagen',
        backref='producto',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ProductoImagen.orden'
    )
    
    @property
    def stock_bajo(self):
        """Retorna True si el stock está por debajo del mínimo"""
        return self.stock_actual <= self.stock_minimo
    
    @property
    def precio_venta_con_iva(self):
        """Precio de venta (asumiendo IVA incluido)"""
        return self.precio_venta
    
    @property
    def iva_unitario(self):
        """Calcula el IVA unitario (IVA incluido en precio)"""
        if self.porcentaje_iva == 10:
            return float(self.precio_venta) / 11
        elif self.porcentaje_iva == 5:
            return float(self.precio_venta) / 21
        return 0
    
    def __repr__(self):
        return f'<Producto {self.codigo} - {self.nombre}>'


class ProductoPrecioOpcion(db.Model):
    __tablename__ = 'producto_precios_opciones'

    id_opcion_precio = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto', ondelete='CASCADE'), nullable=False, index=True)
    etiqueta = db.Column(db.String(100))
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_producto_precios_opciones_producto_activo', 'id_producto', 'activo'),
    )

    def __repr__(self):
        return f'<ProductoPrecioOpcion {self.id_producto} {self.etiqueta or ""} {self.precio}>'


class ProductoCompuesto(db.Model):
    """Componentes de un Kit/Combo"""
    __tablename__ = 'productos_compuestos'
    
    id_composicion = db.Column(db.Integer, primary_key=True)
    id_producto_kit = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    id_producto_componente = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    
    # Relación al componente
    componente = db.relationship('Producto', foreign_keys=[id_producto_componente])
    
    __table_args__ = (
        db.UniqueConstraint('id_producto_kit', 'id_producto_componente', name='uq_kit_componente'),
        db.CheckConstraint('id_producto_kit != id_producto_componente', name='ck_no_autoref'),
    )
    
    def __repr__(self):
        return f'<KitComponente {self.id_producto_kit} -> {self.id_producto_componente} x{self.cantidad}>'


class ProductoRepuesto(db.Model):
    """Relación Producto-Repuesto"""
    __tablename__ = 'producto_repuestos'
    
    id_relacion = db.Column(db.Integer, primary_key=True)
    id_producto_principal = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    id_producto_repuesto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    
    # Relación al repuesto
    repuesto = db.relationship('Producto', foreign_keys=[id_producto_repuesto])
    
    __table_args__ = (
        db.UniqueConstraint('id_producto_principal', 'id_producto_repuesto', name='uq_producto_repuesto'),
        db.CheckConstraint('id_producto_principal != id_producto_repuesto', name='ck_no_autoref_repuesto'),
    )
    
    def __repr__(self):
        return f'<Repuesto {self.id_producto_principal} -> {self.id_producto_repuesto}>'
