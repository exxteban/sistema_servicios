-- Reparar permisos después de restaurar backup de MySQL
-- Este script reestablece todos los permisos necesarios

-- Paso 1: Asegurarse de que la base de datos existe
CREATE DATABASE IF NOT EXISTS bd_silvio CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Paso 2: Eliminar privilegios antiguos del usuario (limpiar)
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'silvio_user'@'localhost';

-- Paso 3: Otorgar TODOS los privilegios sobre la base de datos bd_silvio
GRANT ALL PRIVILEGES ON bd_silvio.* TO 'silvio_user'@'localhost';

-- Paso 4: Aplicar cambios inmediatamente
FLUSH PRIVILEGES;

-- Paso 5: Verificar los permisos otorgados
SHOW GRANTS FOR 'silvio_user'@'localhost';
