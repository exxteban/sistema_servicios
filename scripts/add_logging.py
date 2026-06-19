"""
Script para agregar logging detallado a las rutas de productos
Ejecutar este script para parchear temporalmente el archivo productos.py con logging
"""
import os
import sys

# Ruta al archivo productos.py
PRODUCTOS_FILE = r'c:\Users\Tars\Documents\proyectos\sistemas_tock_inventario_ventas2\app\routes\productos.py'

# Backup del archivo original
BACKUP_FILE = PRODUCTOS_FILE + '.backup'

def add_logging_to_crear_rapido():
    """Agrega logging detallado a la función crear_rapido"""
    
    # Hacer backup
    if not os.path.exists(BACKUP_FILE):
        with open(PRODUCTOS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Backup creado: {BACKUP_FILE}")
    
    # Leer el archivo
    with open(PRODUCTOS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Encontrar la función crear_rapido y agregar logging
    new_lines = []
    in_crear_rapido = False
    logger_imported = False
    indent = ''
    
    for i, line in enumerate(lines):
        # Detectar si ya tiene import logging
        if 'import logging' in line and not logger_imported:
            logger_imported = True
        
        # Detectar inicio de función crear_rapido
        if 'def crear_rapido():' in line:
            in_crear_rapido = True
            indent = line[:len(line) - len(line.lstrip())]
            new_lines.append(line)
            # Agregar import logging si no existe
            if not logger_imported:
                new_lines.append(f'{indent}    import logging\n')
                new_lines.append(f'{indent}    logger = logging.getLogger(__name__)\n')
                new_lines.append(f'{indent}    \n')
            continue
        
        # Agregar logging en puntos clave
        if in_crear_rapido:
            stripped = line.lstrip()
            
            # Al inicio del try
            if stripped.startswith('try:'):
                new_lines.append(line)
                new_lines.append(f'{indent}        logger.info("=== CREAR_RAPIDO INICIADO ===")\n')
                new_lines.append(f'{indent}        logger.info(f"Usuario: {{current_user.username}} (ID: {{current_user.id_usuario}})")\n')
                new_lines.append(f'{indent}        logger.info(f"Client IP: {{request.headers.get(\'X-Forwarded-For\', request.remote_addr)}}")\n')
                continue
            
            # Cuando recibe data
            if 'data = request.get_json()' in stripped:
                new_lines.append(line)
                new_lines.append(f'{indent}        logger.info(f"Datos recibidos: {{data}}")\n')
                continue
            
            # Antes de db.session.add
            if 'db.session.add(producto)' in stripped:
                new_lines.append(f'{indent}        logger.info(f"Agregando producto a sesión: codigo={{codigo}}, nombre={{nombre}}")\n')
                new_lines.append(line)
                continue
            
            # Antes de flush
            if 'db.session.flush()' in stripped:
                new_lines.append(f'{indent}        logger.info("Ejecutando db.session.flush()")\n')
                new_lines.append(line)
                new_lines.append(f'{indent}        logger.info(f"FLUSH EXITOSO - ID: {{producto.id_producto}}")\n')
                continue
            
            # Antes de commit
            if 'db.session.commit()' in stripped and 'commit=False' not in stripped:
                new_lines.append(f'{indent}        logger.info("Ejecutando db.session.commit()")\n')
                new_lines.append(line)
                new_lines.append(f'{indent}        logger.info("=== COMMIT EXITOSO - PRODUCTO GUARDADO ===")\n')
                continue
            
            # En el except
            if stripped.startswith('except Exception as e:'):
                new_lines.append(line)
                new_lines.append(f'{indent}        logger.error("=== ERROR EN CREAR_RAPIDO ===")\n')
                new_lines.append(f'{indent}        logger.error(f"Tipo: {{type(e).__name__}}, Mensaje: {{str(e)}}")\n')
                new_lines.append(f'{indent}        import traceback\n')
                new_lines.append(f'{indent}        logger.error(f"Traceback: {{traceback.format_exc()}}")\n')
                continue
            
            # Detectar fin de la función
            if stripped.startswith('def ') and 'crear_rapido' not in stripped:
                in_crear_rapido = False
        
        new_lines.append(line)
    
    # Escribir el archivo modificado
    with open(PRODUCTOS_FILE, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✓ Logging agregado a {PRODUCTOS_FILE}")
    print(f"  Para restaurar el original: copy {BACKUP_FILE} {PRODUCTOS_FILE}")

def restore_backup():
    """Restaura el archivo original desde el backup"""
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(PRODUCTOS_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Archivo restaurado desde backup")
    else:
        print(f"✗ No se encontró backup en {BACKUP_FILE}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'restore':
        restore_backup()
    else:
        add_logging_to_crear_rapido()
        print("\nPara ver los logs en tiempo real:")
        print("  tail -f logs/sistema.log")
        print("\nPara restaurar el archivo original:")
        print(f"  python {__file__} restore")
