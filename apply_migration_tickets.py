"""
Script para aplicar migración de tabla tickets
"""
import sqlite3
import os

# Ruta a la base de datos
db_path = os.path.join(os.path.dirname(__file__), 'inventario.db')
migration_path = os.path.join(os.path.dirname(__file__), 'migrations', '002_create_tickets_table.sql')

# Leer el script SQL
with open(migration_path, 'r', encoding='utf-8') as f:
    sql_script = f.read()

# Conectar a la base de datos y ejecutar
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.executescript(sql_script)
    conn.commit()
    print("✓ Migración aplicada exitosamente")
    print("✓ Tabla 'tickets' creada")
    
    # Verificar que la tabla existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'")
    if cursor.fetchone():
        print("✓ Tabla verificada en la base de datos")
        
        # Mostrar estructura de la tabla
        cursor.execute("PRAGMA table_info(tickets)")
        columns = cursor.fetchall()
        print("\nEstructura de la tabla 'tickets':")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
except Exception as e:
    print(f"✗ Error al aplicar migración: {e}")
    conn.rollback()
finally:
    conn.close()
