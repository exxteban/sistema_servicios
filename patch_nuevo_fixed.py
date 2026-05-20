#!/usr/bin/env python3
"""
Parche CORREGIDO para agregar logging a /productos/nuevo
Este parche es más conservador y solo agrega logs sin modificar la estructura
"""

PRODUCTOS_FILE = 'app/routes/productos.py'

print("Leyendo archivo...")
with open(PRODUCTOS_FILE, 'r') as f:
    content = f.read()

# Backup
with open(PRODUCTOS_FILE + '.backup', 'w') as f:
    f.write(content)
print("Backup creado: app/routes/productos.py.backup")

# Buscar la función nuevo() y agregar logging SIN modificar la estructura
lines = content.split('\n')
new_lines = []
in_nuevo_function = False
post_method_found = False
added_logger_import = False

for i, line in enumerate(lines):
    # Detectar función nuevo()
    if 'def nuevo():' in line:
        in_nuevo_function = True
        new_lines.append(line)
        # Agregar import logging después de la docstring
        if i + 1 < len(lines) and '"""' in lines[i+1]:
            new_lines.append(lines[i+1])  # docstring
            if not added_logger_import:
                new_lines.append('    import logging')
                new_lines.append('    logger = logging.getLogger(__name__)')
                added_logger_import = True
            continue
        continue
    
    # Si estamos en la función nuevo y encontramos el POST
    if in_nuevo_function and "if request.method == 'POST':" in line and not post_method_found:
        new_lines.append(line)
        # Agregar log justo después del if POST
        indent = '        '
        new_lines.append(f"{indent}logger.info(f'=== NUEVO PRODUCTO POST === Usuario: {{current_user.username}}')")
        new_lines.append(f"{indent}logger.info(f'Client IP: {{request.headers.get(\"X-Forwarded-For\", request.remote_addr)}}')")
        post_method_found = True
        continue
    
    # Agregar log antes de db.session.add(producto)
    if in_nuevo_function and 'db.session.add(producto)' in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(f"{indent}logger.info(f'Agregando producto: codigo={{codigo}}, nombre={{nombre}}')")
        new_lines.append(line)
        continue
    
    # Agregar log antes y después de db.session.commit()
    if in_nuevo_function and 'db.session.commit()' in line and 'commit=False' not in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(f"{indent}logger.info('Ejecutando db.session.commit()')")
        new_lines.append(line)
        new_lines.append(f"{indent}logger.info(f'=== PRODUCTO GUARDADO === ID: {{producto.id_producto}}')")
        continue
    
    # Detectar fin de función
    if in_nuevo_function and line and not line[0].isspace() and 'def ' in line:
        in_nuevo_function = False
    
    new_lines.append(line)

# Escribir el archivo
new_content = '\n'.join(new_lines)
with open(PRODUCTOS_FILE, 'w') as f:
    f.write(new_content)

print("\n✓ Parche aplicado exitosamente!")
print("\nPara restaurar si hay problemas:")
print("  cp app/routes/productos.py.backup app/routes/productos.py")
print("\nAhora ejecuta:")
print("  sudo systemctl restart inventario-ventas")
print("  sudo journalctl -u inventario-ventas -f | grep -E 'NUEVO PRODUCTO|GUARDADO|ERROR'")
