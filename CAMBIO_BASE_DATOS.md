# Guía para Cambiar de Base de Datos

Este documento explica cómo cambiar el sistema para que use una nueva base de datos MySQL en lugar de la base de datos actual.

## 🎯 Objetivo

Configurar el sistema para usar una nueva base de datos llamada `bd_silvio` para el nuevo cliente, manteniendo separada la base de datos del cliente anterior.

## 📋 Pasos a Seguir

### 1. Crear la Base de Datos en MySQL

Abre MySQL y ejecuta los siguientes comandos:

```sql
-- Crear la base de datos
CREATE DATABASE bd_silvio CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Crear un usuario específico (recomendado)
CREATE USER 'silvio_user'@'localhost' IDENTIFIED BY 'tu_password_seguro';

-- Dar permisos al usuario
GRANT ALL PRIVILEGES ON bd_silvio.* TO 'silvio_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Configurar el Archivo .env

1. **Copia el archivo de ejemplo:**
   ```bash
   copy .env.example .env
   ```

2. **Edita el archivo `.env`** y configura la conexión a MySQL:
   ```env
   DATABASE_URL=mysql+pymysql://silvio_user:tu_password_seguro@localhost:3306/bd_silvio?charset=utf8mb4
   ```

   **Formato de la URL:**
   ```
   mysql+pymysql://USUARIO:PASSWORD@HOST:PUERTO/NOMBRE_BD?charset=utf8mb4
   ```

   **Ejemplo con valores reales:**
   ```
   mysql+pymysql://silvio_user:MiPassword123@localhost:3306/bd_silvio?charset=utf8mb4
   ```

### 3. Migrar los Datos (Opcional)

Si quieres copiar los datos del sistema anterior a la nueva base de datos:

```bash
# Activar el entorno virtual
.\venv\Scripts\activate  # En Windows
# source venv/bin/activate  # En Linux/Mac

# Ejecutar la migración
python migrations/migrar_sqlite_a_mysql.py
```

### 4. Inicializar la Nueva Base de Datos

Si prefieres empezar con una base de datos vacía:

```bash
# Activar el entorno virtual
.\venv\Scripts\activate

# Ejecutar la aplicación (creará las tablas automáticamente)
python run.py
```

La primera vez que ejecutes el sistema, se crearán automáticamente:
- Todas las tablas necesarias
- Un usuario administrador por defecto: `admin` / `admin`

### 5. Verificar la Conexión

1. Inicia la aplicación:
   ```bash
   python run.py
   ```

2. Abre el navegador en `http://localhost:5000`

3. Inicia sesión con `admin` / `admin`

4. Verifica que todo funcione correctamente

## 🔄 Volver a la Base de Datos Anterior

Si necesitas volver a usar el sistema anterior:

1. **Opción 1 - Comentar la variable:**
   Edita `.env` y comenta la línea de DATABASE_URL:
   ```env
   # DATABASE_URL=mysql+pymysql://silvio_user:password@localhost:3306/bd_silvio?charset=utf8mb4
   ```

2. **Opción 2 - Cambiar a SQLite:**
   ```env
   DATABASE_URL=sqlite:///inventario.db
   ```

3. **Opción 3 - Apuntar a la BD anterior:**
   ```env
   DATABASE_URL=mysql+pymysql://usuario_anterior:password@localhost:3306/inventario?charset=utf8mb4
   ```

## 📝 Notas Importantes

- **Seguridad:** Nunca subas el archivo `.env` a Git (ya está en `.gitignore`)
- **Backup:** Haz backup de la base de datos anterior antes de hacer cambios
- **Passwords:** Usa contraseñas seguras para los usuarios de MySQL
- **Permisos:** Asegúrate de que el usuario de MySQL tenga todos los permisos necesarios

## 🔍 Solución de Problemas

### Error: "Access denied for user"
- Verifica el usuario y contraseña en el archivo `.env`
- Asegúrate de que el usuario tenga permisos en la base de datos

### Error: "Unknown database"
- Verifica que la base de datos exista: `SHOW DATABASES;`
- Crea la base de datos si no existe

### Error: "Can't connect to MySQL server"
- Verifica que MySQL esté corriendo
- Verifica el host y puerto en la URL de conexión

### Las tablas no se crean
- Ejecuta `python run.py` para que se creen automáticamente
- O usa el script de migración si vienes de SQLite

## 📞 Resumen Rápido

```bash
# 1. Crear BD en MySQL
mysql -u root -p
CREATE DATABASE bd_silvio CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 2. Configurar .env
copy .env.example .env
# Editar .env con la conexión a MySQL

# 3. Ejecutar
python run.py
```

¡Listo! El sistema ahora usará la nueva base de datos `bd_silvio`.
