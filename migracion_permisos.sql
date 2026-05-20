-- ============================================
-- SCRIPT DE MIGRACIÓN: Sistema de Permisos
-- ============================================
-- Este script actualiza la base de datos existente
-- para agregar el sistema de permisos y autorizaciones
-- ============================================

-- PASO 1: Crear tablas de roles y permisos
-- ============================================

CREATE TABLE IF NOT EXISTS roles (
    id_rol INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre VARCHAR(50) UNIQUE NOT NULL,
    descripcion TEXT,
    nivel_jerarquia INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN DEFAULT 1,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permisos (
    id_permiso INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    modulo VARCHAR(50) NOT NULL,
    requiere_autorizacion BOOLEAN DEFAULT 0,
    activo BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rol_permisos (
    id_rol_permiso INTEGER PRIMARY KEY AUTOINCREMENT,
    id_rol INTEGER NOT NULL,
    id_permiso INTEGER NOT NULL,
    FOREIGN KEY (id_rol) REFERENCES roles(id_rol) ON DELETE CASCADE,
    FOREIGN KEY (id_permiso) REFERENCES permisos(id_permiso) ON DELETE CASCADE,
    UNIQUE(id_rol, id_permiso)
);

CREATE TABLE IF NOT EXISTS usuario_permisos_adicionales (
    id_usuario_permiso INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    id_permiso INTEGER NOT NULL,
    concedido_por INTEGER NOT NULL,
    fecha_concesion DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_expiracion DATETIME,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    FOREIGN KEY (id_permiso) REFERENCES permisos(id_permiso) ON DELETE CASCADE,
    FOREIGN KEY (concedido_por) REFERENCES usuarios(id_usuario),
    UNIQUE(id_usuario, id_permiso)
);

CREATE TABLE IF NOT EXISTS autorizaciones (
    id_autorizacion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario_solicitante INTEGER NOT NULL,
    id_usuario_autorizador INTEGER NOT NULL,
    id_permiso INTEGER NOT NULL,
    accion VARCHAR(100) NOT NULL,
    referencia_tipo VARCHAR(30),
    referencia_id INTEGER,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobada', 'rechazada', 'expirada')),
    fecha_solicitud DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_respuesta DATETIME,
    observaciones TEXT,
    ip_address VARCHAR(45),
    FOREIGN KEY (id_usuario_solicitante) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_usuario_autorizador) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_permiso) REFERENCES permisos(id_permiso)
);

CREATE TABLE IF NOT EXISTS preferencias_usuario (
    id_preferencia INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    clave VARCHAR(50) NOT NULL,
    valor TEXT NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    UNIQUE(id_usuario, clave)
);

-- PASO 2: Crear tablas de gestión financiera
-- ============================================

CREATE TABLE IF NOT EXISTS pagos_compras (
    id_pago_compra INTEGER PRIMARY KEY AUTOINCREMENT,
    id_compra INTEGER NOT NULL,
    id_metodo_pago INTEGER NOT NULL,
    id_sesion_caja INTEGER,
    id_usuario INTEGER NOT NULL,
    monto DECIMAL(15,2) NOT NULL CHECK (monto > 0),
    referencia VARCHAR(100),
    fecha_pago DATETIME DEFAULT CURRENT_TIMESTAMP,
    observaciones TEXT,
    FOREIGN KEY (id_compra) REFERENCES compras(id_compra) ON DELETE CASCADE,
    FOREIGN KEY (id_metodo_pago) REFERENCES metodos_pago(id_metodo_pago),
    FOREIGN KEY (id_sesion_caja) REFERENCES sesiones_caja(id_sesion),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS cuentas_por_pagar (
    id_cuenta_pagar INTEGER PRIMARY KEY AUTOINCREMENT,
    id_compra INTEGER NOT NULL,
    id_proveedor INTEGER NOT NULL,
    monto_total DECIMAL(15,2) NOT NULL,
    monto_pagado DECIMAL(15,2) NOT NULL DEFAULT 0,
    saldo_pendiente DECIMAL(15,2) NOT NULL,
    fecha_vencimiento DATE,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'pagada', 'vencida', 'cancelada')),
    dias_vencido INTEGER DEFAULT 0,
    FOREIGN KEY (id_compra) REFERENCES compras(id_compra),
    FOREIGN KEY (id_proveedor) REFERENCES proveedores(id_proveedor)
);

CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
    id_cuenta_cobrar INTEGER PRIMARY KEY AUTOINCREMENT,
    id_venta INTEGER NOT NULL,
    id_cliente INTEGER NOT NULL,
    monto_total DECIMAL(15,2) NOT NULL,
    monto_cobrado DECIMAL(15,2) NOT NULL DEFAULT 0,
    saldo_pendiente DECIMAL(15,2) NOT NULL,
    fecha_vencimiento DATE,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'cobrada', 'vencida', 'cancelada')),
    dias_vencido INTEGER DEFAULT 0,
    FOREIGN KEY (id_venta) REFERENCES ventas(id_venta),
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
);

CREATE TABLE IF NOT EXISTS pagos_cuentas_cobrar (
    id_pago_cuenta INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cuenta_cobrar INTEGER NOT NULL,
    id_sesion_caja INTEGER NOT NULL,
    id_usuario INTEGER NOT NULL,
    monto DECIMAL(15,2) NOT NULL CHECK (monto > 0),
    id_metodo_pago INTEGER NOT NULL,
    referencia VARCHAR(100),
    fecha_pago DATETIME DEFAULT CURRENT_TIMESTAMP,
    observaciones TEXT,
    FOREIGN KEY (id_cuenta_cobrar) REFERENCES cuentas_por_cobrar(id_cuenta_cobrar),
    FOREIGN KEY (id_sesion_caja) REFERENCES sesiones_caja(id_sesion),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_metodo_pago) REFERENCES metodos_pago(id_metodo_pago)
);

-- PASO 3: Crear tabla de auditoría
-- ============================================

CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    accion VARCHAR(50) NOT NULL,
    modulo VARCHAR(50) NOT NULL,
    descripcion TEXT NOT NULL,
    referencia_tipo VARCHAR(30),
    referencia_id INTEGER,
    datos_anteriores TEXT,
    datos_nuevos TEXT,
    id_autorizacion INTEGER,
    ip_address VARCHAR(45),
    user_agent TEXT,
    fecha_accion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_autorizacion) REFERENCES autorizaciones(id_autorizacion)
);

-- PASO 4: Migrar usuarios existentes
-- ============================================

-- Agregar columna id_rol a usuarios (si no existe)
-- Nota: SQLite no soporta ALTER TABLE ADD COLUMN con FOREIGN KEY directamente
-- Por lo tanto, debemos recrear la tabla

-- Crear tabla temporal con nueva estructura
CREATE TABLE IF NOT EXISTS usuarios_new (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(100) NOT NULL,
    id_rol INTEGER NOT NULL DEFAULT 3,
    activo BOOLEAN DEFAULT 1,
    ultimo_acceso DATETIME,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_rol) REFERENCES roles(id_rol)
);

-- Copiar datos existentes (si la tabla usuarios existe)
-- Mapear roles antiguos a nuevos IDs
INSERT INTO usuarios_new (id_usuario, username, password_hash, nombre_completo, id_rol, activo, ultimo_acceso, fecha_creacion, fecha_modificacion)
SELECT 
    id_usuario, 
    username, 
    password_hash, 
    nombre_completo,
    CASE 
        WHEN rol = 'admin' THEN 1
        WHEN rol = 'supervisor' THEN 2
        ELSE 3
    END as id_rol,
    activo,
    ultimo_acceso,
    fecha_creacion,
    fecha_modificacion
FROM usuarios
WHERE EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios');

-- Eliminar tabla antigua y renombrar
DROP TABLE IF EXISTS usuarios;
ALTER TABLE usuarios_new RENAME TO usuarios;

-- PASO 5: Insertar datos iniciales
-- ============================================

-- Roles
INSERT OR IGNORE INTO roles (id_rol, nombre, descripcion, nivel_jerarquia) VALUES
(1, 'Administrador', 'Acceso total al sistema', 100),
(2, 'Supervisor', 'Puede supervisar operaciones y generar reportes', 50),
(3, 'Cajero', 'Operaciones básicas de venta y caja', 10);

-- Permisos (ver archivo inicial_sql para la lista completa)
-- Módulo: Ventas
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('crear_venta', 'Crear Venta', 'Permite realizar ventas', 'ventas', 0),
('ver_ventas', 'Ver Ventas', 'Permite ver listado de ventas', 'ventas', 0),
('ver_detalle_venta', 'Ver Detalle de Venta', 'Permite ver detalles de una venta', 'ventas', 0),
('anular_venta', 'Anular Venta', 'Permite anular ventas completadas', 'ventas', 1),
('editar_venta', 'Editar Venta', 'Permite modificar ventas', 'ventas', 1),
('aplicar_descuento', 'Aplicar Descuento', 'Permite aplicar descuentos en ventas', 'ventas', 0),
('aplicar_descuento_mayor', 'Aplicar Descuento Mayor al 10%', 'Permite descuentos superiores al 10%', 'ventas', 1),
('venta_credito', 'Venta a Crédito', 'Permite realizar ventas a crédito', 'ventas', 0),
('vender_sin_stock', 'Vender sin Stock', 'Permite completar venta con stock insuficiente (requiere autorización)', 'ventas', 1);

-- Módulo: Inventario
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('ver_inventario', 'Ver Inventario', 'Permite ver el inventario', 'inventario', 0),
('crear_producto', 'Crear Producto', 'Permite crear nuevos productos', 'inventario', 0),
('editar_producto', 'Editar Producto', 'Permite modificar productos', 'inventario', 0),
('eliminar_producto', 'Eliminar Producto', 'Permite eliminar productos', 'inventario', 1),
('editar_stock', 'Editar Stock', 'Permite ajustar stock manualmente', 'inventario', 1),
('editar_precios', 'Editar Precios', 'Permite modificar precios de productos', 'inventario', 1),
('ver_costo_compra', 'Ver Costo de Compra', 'Permite ver precios de compra', 'inventario', 0);

-- Módulo: Compras
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('crear_compra', 'Crear Compra', 'Permite registrar compras', 'compras', 0),
('ver_compras', 'Ver Compras', 'Permite ver listado de compras', 'compras', 0),
('anular_compra', 'Anular Compra', 'Permite anular compras', 'compras', 1),
('pagar_compra', 'Pagar Compra', 'Permite registrar pagos a proveedores', 'compras', 0);

-- Módulo: Caja
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('abrir_caja', 'Abrir Caja', 'Permite abrir sesión de caja', 'caja', 0),
('cerrar_caja', 'Cerrar Caja', 'Permite cerrar sesión de caja', 'caja', 0),
('ver_caja', 'Ver Caja', 'Permite ver estado de caja', 'caja', 0),
('movimiento_caja', 'Movimiento de Caja', 'Permite ingresos/egresos de caja', 'caja', 0),
('editar_cierre_caja', 'Editar Cierre de Caja', 'Permite modificar cierres de caja', 'caja', 1),
('ver_otras_cajas', 'Ver Otras Cajas', 'Permite ver cajas de otros usuarios', 'caja', 0);

-- Módulo: Clientes
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('crear_cliente', 'Crear Cliente', 'Permite crear nuevos clientes', 'clientes', 0),
('editar_cliente', 'Editar Cliente', 'Permite modificar clientes', 'clientes', 0),
('eliminar_cliente', 'Eliminar Cliente', 'Permite eliminar clientes', 'clientes', 1),
('ver_clientes', 'Ver Clientes', 'Permite ver listado de clientes', 'clientes', 0);

-- Módulo: Proveedores
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('crear_proveedor', 'Crear Proveedor', 'Permite crear proveedores', 'proveedores', 0),
('editar_proveedor', 'Editar Proveedor', 'Permite modificar proveedores', 'proveedores', 0),
('eliminar_proveedor', 'Eliminar Proveedor', 'Permite eliminar proveedores', 'proveedores', 1),
('ver_proveedores', 'Ver Proveedores', 'Permite ver listado de proveedores', 'proveedores', 0);

-- Módulo: Reportes
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('ver_reportes', 'Ver Reportes', 'Permite acceder a reportes', 'reportes', 0),
('ver_reporte_ventas', 'Ver Reporte de Ventas', 'Permite ver reportes de ventas', 'reportes', 0),
('ver_reporte_inventario', 'Ver Reporte de Inventario', 'Permite ver reportes de inventario', 'reportes', 0),
('ver_reporte_financiero', 'Ver Reporte Financiero', 'Permite ver reportes financieros', 'reportes', 0),
('exportar_reportes', 'Exportar Reportes', 'Permite exportar reportes a Excel/PDF', 'reportes', 0);

-- Módulo: Configuración
INSERT OR IGNORE INTO permisos (codigo, nombre, descripcion, modulo, requiere_autorizacion) VALUES
('ver_configuracion', 'Ver Configuración', 'Permite ver configuración del sistema', 'configuracion', 0),
('editar_configuracion', 'Editar Configuración', 'Permite modificar configuración', 'configuracion', 1),
('gestionar_usuarios', 'Gestionar Usuarios', 'Permite crear/editar usuarios', 'configuracion', 1),
('gestionar_roles', 'Gestionar Roles', 'Permite administrar roles y permisos', 'configuracion', 1),
('gestionar_cajas', 'Gestionar Cajas', 'Permite crear/editar cajas', 'caja', 1),
('ver_auditoria', 'Ver Auditoría', 'Permite ver logs de auditoría', 'configuracion', 0),
('crm_operar_como_asesor', 'CRM Operar como Asesor', 'Permite tomar y responder chats en el panel asesor CRM', 'crm', 0);

-- Asignar permisos a roles
-- ADMINISTRADOR: Todos los permisos
INSERT OR IGNORE INTO rol_permisos (id_rol, id_permiso)
SELECT 1, id_permiso FROM permisos WHERE activo = 1;

-- SUPERVISOR: Permisos de lectura y operaciones normales
INSERT OR IGNORE INTO rol_permisos (id_rol, id_permiso)
SELECT 2, id_permiso FROM permisos WHERE codigo IN (
    'crear_venta', 'ver_ventas', 'ver_detalle_venta', 'aplicar_descuento', 'venta_credito', 'vender_sin_stock',
    'ver_inventario', 'crear_producto', 'editar_producto', 'ver_costo_compra',
    'crear_compra', 'ver_compras', 'pagar_compra',
    'abrir_caja', 'cerrar_caja', 'ver_caja', 'movimiento_caja', 'ver_otras_cajas',
    'crear_cliente', 'editar_cliente', 'ver_clientes',
    'crear_proveedor', 'editar_proveedor', 'ver_proveedores',
    'ver_reportes', 'ver_reporte_ventas', 'ver_reporte_inventario', 'ver_reporte_financiero', 'exportar_reportes',
    'ver_configuracion', 'ver_auditoria', 'crm_operar_como_asesor'
);

-- CAJERO: Solo operaciones básicas
INSERT OR IGNORE INTO rol_permisos (id_rol, id_permiso)
SELECT 3, id_permiso FROM permisos WHERE codigo IN (
    'crear_venta', 'ver_ventas', 'ver_detalle_venta', 'aplicar_descuento', 'vender_sin_stock',
    'ver_inventario',
    'abrir_caja', 'cerrar_caja', 'ver_caja', 'movimiento_caja',
    'crear_cliente', 'ver_clientes',
    'ver_proveedores'
);

-- PASO 6: Crear índices
-- ============================================

CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);
CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios(id_rol);
CREATE INDEX IF NOT EXISTS idx_usuarios_activo ON usuarios(activo);

CREATE INDEX IF NOT EXISTS idx_rol_permisos_rol ON rol_permisos(id_rol);
CREATE INDEX IF NOT EXISTS idx_rol_permisos_permiso ON rol_permisos(id_permiso);

CREATE INDEX IF NOT EXISTS idx_autorizaciones_solicitante ON autorizaciones(id_usuario_solicitante);
CREATE INDEX IF NOT EXISTS idx_autorizaciones_autorizador ON autorizaciones(id_usuario_autorizador);
CREATE INDEX IF NOT EXISTS idx_autorizaciones_estado ON autorizaciones(estado);
CREATE INDEX IF NOT EXISTS idx_autorizaciones_fecha ON autorizaciones(fecha_solicitud);

CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria(id_usuario);
CREATE INDEX IF NOT EXISTS idx_auditoria_accion ON auditoria(accion);
CREATE INDEX IF NOT EXISTS idx_auditoria_modulo ON auditoria(modulo);
CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(fecha_accion);
CREATE INDEX IF NOT EXISTS idx_auditoria_referencia ON auditoria(referencia_tipo, referencia_id);

CREATE INDEX IF NOT EXISTS idx_cuentas_cobrar_cliente ON cuentas_por_cobrar(id_cliente);
CREATE INDEX IF NOT EXISTS idx_cuentas_cobrar_estado ON cuentas_por_cobrar(estado);
CREATE INDEX IF NOT EXISTS idx_cuentas_cobrar_vencimiento ON cuentas_por_cobrar(fecha_vencimiento);

CREATE INDEX IF NOT EXISTS idx_cuentas_pagar_proveedor ON cuentas_por_pagar(id_proveedor);
CREATE INDEX IF NOT EXISTS idx_cuentas_pagar_estado ON cuentas_por_pagar(estado);
CREATE INDEX IF NOT EXISTS idx_cuentas_pagar_vencimiento ON cuentas_por_pagar(fecha_vencimiento);

CREATE INDEX IF NOT EXISTS idx_pagos_compras_compra ON pagos_compras(id_compra);
CREATE INDEX IF NOT EXISTS idx_pagos_compras_fecha ON pagos_compras(fecha_pago);

CREATE INDEX IF NOT EXISTS idx_preferencias_usuario ON preferencias_usuario(id_usuario);

-- ============================================
-- MIGRACIÓN COMPLETADA
-- ============================================
