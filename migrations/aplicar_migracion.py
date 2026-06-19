"""
Script para aplicar migración del sistema de permisos
"""
import sqlite3
import os
import sys

def aplicar_migracion(sql_file='migracion_permisos.sql'):
    """Aplica un archivo SQL de migración a la base de datos"""
    
    # Ruta a la base de datos
    db_path = os.path.join(os.path.dirname(__file__), 'inventario.db')
    
    # Verificar que existe la base de datos
    if not os.path.exists(db_path):
        print(f"✗ Error: No se encontró la base de datos en {db_path}")
        return False
    
    # Verificar que existe el archivo SQL
    sql_path = os.path.join(os.path.dirname(__file__), sql_file)
    if not os.path.exists(sql_path):
        print(f"✗ Error: No se encontró el archivo {sql_file}")
        return False
    
    # Leer el archivo SQL
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    conn = None
    try:
        print(f"Conectando a la base de datos: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"Aplicando migración desde: {sql_file}")
        print("-" * 60)
        
        # Ejecutar el script SQL completo
        cursor.executescript(sql_script)
        conn.commit()
        
        print("-" * 60)
        print("✓ Migración aplicada exitosamente")
        
        # Verificar que las tablas se crearon
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tablas = cursor.fetchall()
        
        print(f"\n✓ Tablas en la base de datos ({len(tablas)}):")
        for tabla in tablas:
            print(f"  - {tabla[0]}")
        
        # Verificar datos iniciales
        cursor.execute("SELECT COUNT(*) FROM roles")
        num_roles = cursor.fetchone()[0]
        print(f"\n✓ Roles creados: {num_roles}")
        
        cursor.execute("SELECT COUNT(*) FROM permisos")
        num_permisos = cursor.fetchone()[0]
        print(f"✓ Permisos creados: {num_permisos}")
        
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        num_usuarios = cursor.fetchone()[0]
        print(f"✓ Usuarios migrados: {num_usuarios}")
        
        return True
        
    except sqlite3.Error as e:
        print(f"✗ Error durante la migración: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # Permitir especificar archivo SQL como argumento
    sql_file = sys.argv[1] if len(sys.argv) > 1 else 'migracion_permisos.sql'
    
    print("=" * 60)
    print("MIGRACIÓN DEL SISTEMA DE PERMISOS")
    print("=" * 60)
    print()
    
    exito = aplicar_migracion(sql_file)
    
    if exito:
        print("\n✓ Migración completada exitosamente.")
        print("  Puedes reiniciar el servidor ahora.")
    else:
        print("\n✗ La migración falló.")
        print("  Revisa los errores anteriores.")
        sys.exit(1)
