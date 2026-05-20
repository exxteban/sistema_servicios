"""
Script para crear la tabla de reparaciones
"""
import sqlite3
import os

# Ruta a la base de datos
db_path = os.path.join(os.path.dirname(__file__), 'inventario.db')

conn = None
try:
    # Conectar a la base de datos
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Activar Foreign Keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Crear tabla reparaciones
    sql_table = """
    CREATE TABLE IF NOT EXISTS reparaciones (
        id_reparacion INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        tipo_equipo VARCHAR(50) NOT NULL,
        marca_modelo VARCHAR(100) NOT NULL,
        imei_serie VARCHAR(100),
        password_patron VARCHAR(100),
        accesorios TEXT,
        falla_reportada TEXT NOT NULL,
        diagnostico_tecnico TEXT,
        solucion TEXT,
        estado VARCHAR(20) DEFAULT 'pendiente',
        prioridad VARCHAR(20) DEFAULT 'normal',
        costo_estimado NUMERIC(10, 2) DEFAULT 0,
        costo_final NUMERIC(10, 2) DEFAULT 0,
        abono NUMERIC(10, 2) DEFAULT 0,
        fecha_ingreso DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_estimada DATETIME,
        fecha_entrega DATETIME,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id_cliente)
    );
    """
    cursor.execute(sql_table)
    print("✓ Tabla reparaciones verificada/creada")

    # Crear índice para estado
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_reparaciones_estado ON reparaciones (estado)")
    print("✓ Índice de estado verificado/creado")
    
    conn.commit()
    print("\n✓ Migración completada exitosamente.")
    
except sqlite3.OperationalError as e:
    print(f"✗ Error SQLite: {e}")
    if conn:
        conn.rollback()
    raise
except Exception as e:
    print(f"✗ Error general: {e}")
    if conn:
        conn.rollback()
    raise
finally:
    if conn:
        conn.close()
