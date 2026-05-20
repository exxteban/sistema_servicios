-- Script mejorado para configurar usuario con todos los permisos necesarios
-- Para XAMPP/MariaDB

-- Eliminar usuario si existe (para empezar limpio)
DROP USER IF EXISTS 'silvio_user'@'localhost';

-- Crear usuario con método de autenticación nativo
CREATE USER 'silvio_user'@'localhost' IDENTIFIED VIA mysql_native_password USING PASSWORD('tk--nj0102');

-- Otorgar todos los privilegios
GRANT ALL PRIVILEGES ON bd_silvio.* TO 'silvio_user'@'localhost' WITH GRANT OPTION;

-- Aplicar cambios
FLUSH PRIVILEGES;

-- Verificar que el usuario se creó correctamente
SELECT User, Host FROM mysql.user WHERE User = 'silvio_user';
