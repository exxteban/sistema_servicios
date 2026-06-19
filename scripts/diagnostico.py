"""
Script de diagnóstico para depurar problemas de guardado en el servidor
"""
import os
import sys
import sqlite3
from datetime import datetime

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{text:^60}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")

def check_permissions():
    """Verifica permisos de archivos y directorios"""
    print_header("VERIFICACIÓN DE PERMISOS")
    
    paths_to_check = [
        'logs',
        'logs/sistema.log',
        'instance',
        'instance/inventario.db'
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            is_writable = os.access(path, os.W_OK)
            is_readable = os.access(path, os.R_OK)
            status = f"{Colors.GREEN}✓{Colors.END}" if (is_writable and is_readable) else f"{Colors.RED}✗{Colors.END}"
            print(f"{status} {path}")
            print(f"   Lectura: {'Sí' if is_readable else 'NO'}, Escritura: {'Sí' if is_writable else 'NO'}")
            
            # Mostrar propietario y permisos en Windows
            try:
                stat_info = os.stat(path)
                print(f"   Tamaño: {stat_info.st_size} bytes")
                print(f"   Última modificación: {datetime.fromtimestamp(stat_info.st_mtime)}")
            except Exception as e:
                print(f"   {Colors.YELLOW}No se pudo obtener info: {e}{Colors.END}")
        else:
            print(f"{Colors.RED}✗{Colors.END} {path} - NO EXISTE")

def check_database():
    """Verifica estado de la base de datos"""
    print_header("VERIFICACIÓN DE BASE DE DATOS")
    
    db_path = 'instance/inventario.db'
    if not os.path.exists(db_path):
        print(f"{Colors.RED}✗ Base de datos no encontrada: {db_path}{Colors.END}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar tablas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"{Colors.GREEN}✓{Colors.END} Tablas encontradas: {len(tables)}")
        
        # Verificar tabla productos
        if ('productos',) in tables:
            cursor.execute("SELECT COUNT(*) FROM productos")
            count = cursor.fetchone()[0]
            print(f"{Colors.GREEN}✓{Colors.END} Productos en DB: {count}")
            
            # Último producto creado
            cursor.execute("""
                SELECT id_producto, codigo, nombre, fecha_creacion 
                FROM productos 
                ORDER BY id_producto DESC 
                LIMIT 1
            """)
            last = cursor.fetchone()
            if last:
                print(f"  Último producto: ID={last[0]}, Código={last[1]}, Nombre={last[2]}")
                print(f"  Fecha creación: {last[3]}")
        
        # Verificar PRAGMA foreign_keys
        cursor.execute("PRAGMA foreign_keys")
        fk_status = cursor.fetchone()[0]
        print(f"{Colors.GREEN if fk_status else Colors.YELLOW}{'✓' if fk_status else '!'}{Colors.END} Foreign keys: {'ACTIVADAS' if fk_status else 'DESACTIVADAS'}")
        
        # Verificar integridad
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        if integrity == 'ok':
            print(f"{Colors.GREEN}✓{Colors.END} Integridad de DB: OK")
        else:
            print(f"{Colors.RED}✗{Colors.END} Integridad de DB: {integrity}")
        
        conn.close()
        
    except Exception as e:
        print(f"{Colors.RED}✗ Error al verificar DB: {e}{Colors.END}")

def check_logs():
    """Verifica y muestra últimas líneas de logs"""
    print_header("ÚLTIMAS LÍNEAS DE LOG")
    
    log_file = 'logs/sistema.log'
    if not os.path.exists(log_file):
        print(f"{Colors.YELLOW}! Log file no existe aún: {log_file}{Colors.END}")
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-20:] if len(lines) > 20 else lines
            
            print(f"Mostrando últimas {len(last_lines)} líneas:\n")
            for line in last_lines:
                if 'ERROR' in line:
                    print(f"{Colors.RED}{line.rstrip()}{Colors.END}")
                elif 'WARNING' in line:
                    print(f"{Colors.YELLOW}{line.rstrip()}{Colors.END}")
                else:
                    print(line.rstrip())
    except Exception as e:
        print(f"{Colors.RED}✗ Error al leer log: {e}{Colors.END}")

def check_config():
    """Verifica configuración de la aplicación"""
    print_header("VERIFICACIÓN DE CONFIGURACIÓN")
    
    # Verificar archivo config.py
    if os.path.exists('config.py'):
        print(f"{Colors.GREEN}✓{Colors.END} config.py encontrado")
    else:
        print(f"{Colors.RED}✗{Colors.END} config.py NO encontrado")
    
    # Verificar variables de entorno importantes
    env_vars = ['FLASK_ENV', 'FLASK_APP', 'SECRET_KEY', 'DATABASE_URL']
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            # Ocultar valores sensibles
            display_value = value if var not in ['SECRET_KEY', 'DATABASE_URL'] else '***'
            print(f"{Colors.GREEN}✓{Colors.END} {var} = {display_value}")
        else:
            print(f"{Colors.YELLOW}!{Colors.END} {var} no definida")

def monitor_log_realtime():
    """Monitorea el log en tiempo real"""
    print_header("MONITOR DE LOG EN TIEMPO REAL")
    print("Presiona Ctrl+C para detener\n")
    
    log_file = 'logs/sistema.log'
    
    try:
        # Crear el archivo si no existe
        if not os.path.exists('logs'):
            os.makedirs('logs')
        if not os.path.exists(log_file):
            open(log_file, 'a').close()
        
        with open(log_file, 'r', encoding='utf-8') as f:
            # Ir al final del archivo
            f.seek(0, 2)
            
            print(f"Monitoreando {log_file}...\n")
            while True:
                line = f.readline()
                if line:
                    if 'ERROR' in line:
                        print(f"{Colors.RED}{line.rstrip()}{Colors.END}")
                    elif 'WARNING' in line:
                        print(f"{Colors.YELLOW}{line.rstrip()}{Colors.END}")
                    elif 'CREAR_RAPIDO' in line or 'COMMIT' in line:
                        print(f"{Colors.GREEN}{line.rstrip()}{Colors.END}")
                    else:
                        print(line.rstrip())
                else:
                    import time
                    time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"\n{Colors.BLUE}Monitor detenido{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.END}")

def main():
    """Función principal"""
    if len(sys.argv) > 1 and sys.argv[1] == 'monitor':
        monitor_log_realtime()
        return
    
    print(f"\n{Colors.BLUE}{'='*60}")
    print(f"  DIAGNÓSTICO DEL SISTEMA - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}{Colors.END}\n")
    
    check_permissions()
    check_database()
    check_config()
    check_logs()
    
    print(f"\n{Colors.BLUE}{'='*60}")
    print("  DIAGNÓSTICO COMPLETADO")
    print(f"{'='*60}{Colors.END}\n")
    
    print("Para monitorear logs en tiempo real:")
    print(f"  python {__file__} monitor\n")

if __name__ == '__main__':
    main()
