-- Script para configurar la base de datos local de prueba
-- Este script crea el usuario y la base de datos necesarios para pruebas locales

-- Crear la base de datos si no existe
CREATE DATABASE IF NOT EXISTS bd_silvio CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Crear el usuario si no existe (MySQL 8.0+)
CREATE USER IF NOT EXISTS 'silvio_user'@'localhost' IDENTIFIED BY 'tk--nj0102';

-- Otorgar todos los privilegios al usuario sobre la base de datos
GRANT ALL PRIVILEGES ON bd_silvio.* TO 'silvio_user'@'localhost';

-- Aplicar los cambios
FLUSH PRIVILEGES;

-- Mostrar confirmación
SELECT 'Base de datos y usuario creados exitosamente!' AS Resultado;
