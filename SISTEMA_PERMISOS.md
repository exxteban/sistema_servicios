# Sistema de Permisos y Autorizaciones

## Resumen de Cambios en la Base de Datos

Se ha actualizado el esquema SQL con las siguientes mejoras:

### 1. Sistema de Roles y Permisos ✅

#### Nuevas Tablas:
- **`roles`**: Define los roles del sistema (Administrador, Supervisor, Cajero)
- **`permisos`**: Catálogo de permisos granulares por módulo
- **`rol_permisos`**: Relación muchos a muchos entre roles y permisos
- **`usuario_permisos_adicionales`**: Permisos excepcionales por usuario

#### Roles Predefinidos:
1. **Administrador** (nivel 100): Acceso total al sistema
2. **Supervisor** (nivel 50): Operaciones normales + reportes, sin eliminaciones críticas
3. **Cajero** (nivel 10): Solo operaciones básicas de venta y caja

### 2. Sistema de Autorizaciones ✅

#### Nueva Tabla: `autorizaciones`
Registra cuando un usuario solicita autorización del administrador para realizar una acción crítica.

**Flujo de Autorización:**
1. Cajero intenta realizar acción crítica (ej: anular venta)
2. Sistema detecta que requiere autorización (`requiere_autorizacion = 1`)
3. Se muestra modal solicitando código de administrador
4. Administrador ingresa su usuario/contraseña
5. Se registra la autorización en la tabla
6. Se permite la acción
7. Se registra en auditoría

**Acciones que Requieren Autorización:**
- Anular venta
- Editar venta
- Aplicar descuento mayor al 10%
- Editar stock manualmente
- Editar precios
- Eliminar productos/clientes/proveedores
- Anular compras
- Editar cierre de caja
- Modificar configuración del sistema
- Gestionar usuarios y roles

### 3. Pagos de Compras ✅

#### Nueva Tabla: `pagos_compras`
Similar a `pagos_ventas`, permite registrar pagos a proveedores con múltiples métodos de pago.

### 4. Gestión de Cuentas ✅

#### Nuevas Tablas:
- **`cuentas_por_pagar`**: Deudas con proveedores
- **`cuentas_por_cobrar`**: Créditos a clientes
- **`pagos_cuentas_cobrar`**: Pagos parciales de clientes

### 5. Auditoría Completa ✅

#### Nueva Tabla: `auditoria`
Registra todas las acciones críticas del sistema:
- Quién realizó la acción
- Qué módulo y acción
- Datos antes y después del cambio (JSON)
- Referencia a autorización si aplica
- IP y user agent

### 6. Preferencias de Usuario ✅

#### Nueva Tabla: `preferencias_usuario`
Almacena configuraciones personalizadas por usuario:
- Tema (claro/oscuro)
- Idioma
- Rango de fecha del dashboard
- Otras preferencias de UI

## Permisos por Módulo

### Ventas
- `crear_venta`: Realizar ventas
- `ver_ventas`: Ver listado de ventas
- `ver_detalle_venta`: Ver detalles de una venta
- `anular_venta`: ⚠️ Anular ventas (requiere autorización)
- `editar_venta`: ⚠️ Modificar ventas (requiere autorización)
- `aplicar_descuento`: Aplicar descuentos normales
- `aplicar_descuento_mayor`: ⚠️ Descuentos >10% (requiere autorización)
- `venta_credito`: Realizar ventas a crédito

### Inventario
- `ver_inventario`: Ver el inventario
- `crear_producto`: Crear nuevos productos
- `editar_producto`: Modificar productos
- `eliminar_producto`: ⚠️ Eliminar productos (requiere autorización)
- `editar_stock`: ⚠️ Ajustar stock manualmente (requiere autorización)
- `editar_precios`: ⚠️ Modificar precios (requiere autorización)
- `ver_costo_compra`: Ver precios de compra

### Compras
- `crear_compra`: Registrar compras
- `ver_compras`: Ver listado de compras
- `anular_compra`: ⚠️ Anular compras (requiere autorización)
- `pagar_compra`: Registrar pagos a proveedores

### Caja
- `abrir_caja`: Abrir sesión de caja
- `cerrar_caja`: Cerrar sesión de caja
- `ver_caja`: Ver estado de caja
- `movimiento_caja`: Ingresos/egresos de caja
- `editar_cierre_caja`: ⚠️ Modificar cierres (requiere autorización)
- `ver_otras_cajas`: Ver cajas de otros usuarios

### Clientes
- `crear_cliente`: Crear nuevos clientes
- `editar_cliente`: Modificar clientes
- `eliminar_cliente`: ⚠️ Eliminar clientes (requiere autorización)
- `ver_clientes`: Ver listado de clientes

### Proveedores
- `crear_proveedor`: Crear proveedores
- `editar_proveedor`: Modificar proveedores
- `eliminar_proveedor`: ⚠️ Eliminar proveedores (requiere autorización)
- `ver_proveedores`: Ver listado de proveedores

### Reportes
- `ver_reportes`: Acceder a reportes
- `ver_reporte_ventas`: Ver reportes de ventas
- `ver_reporte_inventario`: Ver reportes de inventario
- `ver_reporte_financiero`: Ver reportes financieros
- `exportar_reportes`: Exportar reportes a Excel/PDF

### Configuración
- `ver_configuracion`: Ver configuración del sistema
- `editar_configuracion`: ⚠️ Modificar configuración (requiere autorización)
- `gestionar_usuarios`: ⚠️ Crear/editar usuarios (requiere autorización)
- `gestionar_roles`: ⚠️ Administrar roles y permisos (requiere autorización)
- `ver_auditoria`: Ver logs de auditoría

## Implementación en el Backend

### 1. Verificar Permisos

```python
from functools import wraps
from flask import session, jsonify
from app.models.usuario import Usuario

def requiere_permiso(codigo_permiso):
    """Decorator para verificar permisos"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'No autenticado'}), 401
            
            usuario = Usuario.query.get(session['user_id'])
            if not usuario.tiene_permiso(codigo_permiso):
                return jsonify({'error': 'Sin permisos'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Uso:
@app.route('/api/ventas/anular/<int:id>', methods=['POST'])
@requiere_permiso('anular_venta')
def anular_venta(id):
    # Lógica para anular venta
    pass
```

### 2. Solicitar Autorización

```python
@app.route('/api/autorizacion/solicitar', methods=['POST'])
def solicitar_autorizacion():
    """
    Solicita autorización del administrador
    Body: {
        "codigo_permiso": "anular_venta",
        "accion": "Anular venta #123",
        "referencia_tipo": "venta",
        "referencia_id": 123,
        "username_admin": "admin",
        "password_admin": "***"
    }
    """
    data = request.json
    
    # Verificar credenciales del admin
    admin = Usuario.verificar_credenciales(
        data['username_admin'], 
        data['password_admin']
    )
    
    if not admin or not admin.tiene_permiso(data['codigo_permiso']):
        return jsonify({'error': 'Credenciales inválidas'}), 401
    
    # Crear registro de autorización
    autorizacion = Autorizacion(
        id_usuario_solicitante=session['user_id'],
        id_usuario_autorizador=admin.id_usuario,
        id_permiso=Permiso.query.filter_by(codigo=data['codigo_permiso']).first().id_permiso,
        accion=data['accion'],
        referencia_tipo=data['referencia_tipo'],
        referencia_id=data['referencia_id'],
        estado='aprobada',
        fecha_respuesta=datetime.now()
    )
    db.session.add(autorizacion)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'id_autorizacion': autorizacion.id_autorizacion
    })
```

### 3. Registrar en Auditoría

```python
def registrar_auditoria(usuario_id, accion, modulo, descripcion, 
                       referencia_tipo=None, referencia_id=None,
                       datos_anteriores=None, datos_nuevos=None,
                       id_autorizacion=None):
    """Registra una acción en la auditoría"""
    import json
    from flask import request
    
    auditoria = Auditoria(
        id_usuario=usuario_id,
        accion=accion,
        modulo=modulo,
        descripcion=descripcion,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        datos_anteriores=json.dumps(datos_anteriores) if datos_anteriores else None,
        datos_nuevos=json.dumps(datos_nuevos) if datos_nuevos else None,
        id_autorizacion=id_autorizacion,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    db.session.add(auditoria)
    db.session.commit()
```

## Ejemplo de Flujo Completo: Anular Venta

1. **Frontend**: Usuario cajero intenta anular venta
2. **Backend**: Detecta que requiere permiso `anular_venta`
3. **Backend**: Verifica que el permiso tiene `requiere_autorizacion = 1`
4. **Frontend**: Muestra modal pidiendo credenciales de administrador
5. **Usuario**: Administrador ingresa su usuario y contraseña
6. **Backend**: Valida credenciales y crea registro en `autorizaciones`
7. **Backend**: Procede a anular la venta
8. **Backend**: Registra la acción en `auditoria` con referencia a la autorización
9. **Frontend**: Muestra confirmación

## Migración de Datos Existentes

Ver archivo `migracion_permisos.sql` para actualizar la base de datos existente.

## Próximos Pasos

1. ✅ Actualizar modelos de SQLAlchemy
2. ✅ Implementar decoradores de permisos
3. ✅ Crear endpoints de autorización
4. ✅ Implementar UI para solicitar autorizaciones
5. ✅ Agregar gestión de roles y permisos en panel de admin
6. ✅ Implementar sistema de auditoría
