-- Crear un usuario completamente nuevo para evitar conflictos con el backup
-- Usaremos usuario 'test_user' temporalmente para pruebas locales

-- Eliminar usuario de prueba si existe
DROP USER IF EXISTS 'test_user'@'localhost';

-- Crear nuevo usuario
CREATE USER 'test_user'@'localhost' IDENTIFIED BY 'test123';

-- Asegurarse de que bd_silvio existe
CREATE DATABASE IF NOT EXISTS bd_silvio CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Otorgar todos los privilegios
GRANT ALL PRIVILEGES ON bd_silvio.* TO 'test_user'@'localhost' WITH GRANT OPTION;
FLUSH PRIVILEGES;

-- Verificar
SHOW GRANTS FOR 'test_user'@'localhost';
SELECT 'Usuario test_user creado exitosamente!' AS Resultado;
