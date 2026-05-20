-- Solución directa: insertar permisos en la tabla mysql.db
-- Esto evita problemas con GRANT después de restaurar backups

-- Primero, eliminar cualquier entrada antigua
DELETE FROM mysql.db WHERE User = 'silvio_user' AND Db = 'bd_silvio';

-- Insertar permisos directamente en la tabla mysql.db
INSERT INTO mysql.db 
(Host, Db, User, Select_priv, Insert_priv, Update_priv, Delete_priv, 
 Create_priv, Drop_priv, Grant_priv, References_priv, Index_priv, 
 Alter_priv, Create_tmp_table_priv, Lock_tables_priv, Create_view_priv, 
 Show_view_priv, Create_routine_priv, Alter_routine_priv, Execute_priv, 
 Event_priv, Trigger_priv)
VALUES 
('localhost', 'bd_silvio', 'silvio_user', 'Y', 'Y', 'Y', 'Y', 
 'Y', 'Y', 'Y', 'Y', 'Y', 
 'Y', 'Y', 'Y', 'Y', 
 'Y', 'Y', 'Y', 'Y', 
 'Y', 'Y');

-- Aplicar cambios
FLUSH PRIVILEGES;

-- Verificar
SELECT Host, Db, User, Select_priv, Insert_priv, Create_priv, Drop_priv 
FROM mysql.db 
WHERE User = 'silvio_user' AND Db = 'bd_silvio';
