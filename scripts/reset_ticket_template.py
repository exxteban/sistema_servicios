"""
Script para resetear la configuración del template de ticket.
Esto limpia cualquier template personalizado guardado y fuerza el uso del template por defecto.
"""
import sqlite3
import os

def reset_ticket_template():
    db_path = os.path.join(os.path.dirname(__file__), 'inventario.db')
    
    print("=" * 50)
    print("RESET DE TEMPLATE DE TICKET")
    print("=" * 50)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Verificar configuración actual
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave = 'ticket_template_html'")
    row = cursor.fetchone()
    
    if row and row[1]:
        print(f"\nTemplate personalizado encontrado ({len(row[1])} caracteres)")
        
        # Limpiar el template personalizado (establecer a vacío)
        cursor.execute(
            "UPDATE configuracion SET valor = '' WHERE clave = 'ticket_template_html'"
        )
        conn.commit()
        print("✓ Template personalizado eliminado")
        print("  El sistema ahora usará el template por defecto (ticket.html)")
    else:
        print("\nNo hay template personalizado guardado")
        print("  El sistema ya usa el template por defecto")
    
    # Verificar otras configuraciones de ticket
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave LIKE '%ticket%'")
    rows = cursor.fetchall()
    
    print("\n" + "-" * 50)
    print("CONFIGURACIONES ACTUALES DE TICKET:")
    print("-" * 50)
    for key, val in rows:
        display_val = val if val and len(val) < 50 else ('(vacío)' if not val else f'({len(val)} chars)')
        print(f"  {key}: {display_val}")
    
    conn.close()
    print("\n✓ Proceso completado")

if __name__ == '__main__':
    reset_ticket_template()
