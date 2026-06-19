"""
Parche para agregar logging detallado a la ruta /productos/nuevo
Ejecutar en el servidor después de hacer git pull
"""

import sys
import os

PRODUCTOS_FILE = 'app/routes/productos.py'

# Leer el archivo
with open(PRODUCTOS_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Buscar la función nuevo() y agregar logging
nuevo_function_start = content.find('def nuevo():')

if nuevo_function_start == -1:
    print("ERROR: No se encontró la función nuevo()")
    sys.exit(1)

# Encontrar donde dice "if request.method == 'POST':"
post_check = content.find("if request.method == 'POST':", nuevo_function_start)

if post_check == -1:
    print("ERROR: No se encontró el check de POST")
    sys.exit(1)

# Agregar import logging al inicio si no existe
if 'import logging' not in content[:nuevo_function_start]:
    # Buscar los imports al inicio del archivo
    first_import = content.find('from flask import')
    if first_import != -1:
        # Agregar después de los imports de Flask
        end_of_line = content.find('\n', first_import)
        content = content[:end_of_line+1] + 'import logging\n' + content[end_of_line+1:]

# Agregar logger al inicio de la función nuevo
docstring_end = content.find('"""', nuevo_function_start + 20)
next_line = content.find('\n', docstring_end) + 1

logger_init = "    logger = logging.getLogger(__name__)\n    "
if 'logger = logging.getLogger' not in content[nuevo_function_start:nuevo_function_start+500]:
    content = content[:next_line] + logger_init + content[next_line:]

# Ahora agregar logs en puntos clave
# Después de "if request.method == 'POST':"
post_check = content.find("if request.method == 'POST':", nuevo_function_start)
next_line = content.find('\n', post_check) + 1
log_line = "        logger.info(f'=== NUEVO PRODUCTO POST === Usuario: {current_user.username}')\n        "
if '=== NUEVO PRODUCTO POST ===' not in content[post_check:post_check+200]:
    content = content[:next_line] + log_line + content[next_line:]

# Antes de db.session.add
add_pos = content.find('db.session.add(producto)', nuevo_function_start)
if add_pos != -1:
    # Encontrar el inicio de la línea
    line_start = content.rfind('\n', nuevo_function_start, add_pos) + 1
    indent = content[line_start:add_pos]
    log_line = f"{indent}logger.info(f'Agregando producto: codigo={{codigo}}, nombre={{nombre}}')\n"
    if 'Agregando producto:' not in content[add_pos-200:add_pos]:
        content = content[:line_start] + log_line + content[line_start:]

# Antes de db.session.commit
commit_pos = content.find('db.session.commit()', add_pos)
if commit_pos != -1:
    line_start = content.rfind('\n', add_pos, commit_pos) + 1
    indent = content[line_start:commit_pos]
    log_line = f"{indent}logger.info('Ejecutando commit...')\n"
    if 'Ejecutando commit' not in content[commit_pos-200:commit_pos]:
        content = content[:line_start] + log_line + content[line_start:]

# Después de commit
commit_end = content.find('\n', commit_pos)
log_line = f"{indent}logger.info(f'PRODUCTO GUARDADO EXITOSAMENTE - ID: {{producto.id_producto}}')\n"
if 'PRODUCTO GUARDADO EXITOSAMENTE' not in content[commit_pos:commit_pos+200]:
    content = content[:commit_end+1] + log_line + content[commit_end+1:]

# Escribir el archivo modificado
with open(PRODUCTOS_FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Logging agregado a la función nuevo()")
print("\nAhora ejecuta:")
print("  sudo systemctl restart inventario-ventas")
print("  sudo journalctl -u inventario-ventas -f | grep -E 'NUEVO PRODUCTO|GUARDADO|ERROR'")
