"""
Script para aplicar migración de dashboard_range_preference
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
    
    # Intentar agregar la columna
    cursor.execute("ALTER TABLE usuarios ADD COLUMN dashboard_range_preference VARCHAR(20) DEFAULT 'hoy'")
    conn.commit()
    print("✓ Columna dashboard_range_preference agregada exitosamente")
    
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("✓ La columna dashboard_range_preference ya existe")
    else:
        print(f"✗ Error: {e}")
        raise
        
finally:
    if conn:
        conn.close()

print("\n✓ Migración completada. Puedes reiniciar el servidor.")
