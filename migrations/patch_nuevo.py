#!/usr/bin/env python3
"""
Parche urgente para agregar logging a /productos/nuevo
Ejecutar en el servidor: python3 patch_nuevo.py
"""

import re

PRODUCTOS_FILE = 'app/routes/productos.py'

print("Leyendo archivo...")
with open(PRODUCTOS_FILE, 'r') as f:
    lines = f.readlines()

print(f"Total líneas: {len(lines)}")

# Encontrar la función nuevo()
nuevo_start = None
for i, line in enumerate(lines):
    if 'def nuevo():' in line:
        nuevo_start = i
        print(f"Función nuevo() encontrada en línea {i+1}")
        break

if nuevo_start is None:
    print("ERROR: No se encontró la función nuevo()")
    exit(1)

# Agregar import logging después de la docstring
for i in range(nuevo_start, min(nuevo_start + 10, len(lines))):
    if '"""' in lines[i] and i > nuevo_start:
        # Insertar después de la docstring
        if 'logger = logging.getLogger' not in ''.join(lines[nuevo_start:nuevo_start+15]):
            lines.insert(i+1, "    import logging\n")
            lines.insert(i+2, "    logger = logging.getLogger(__name__)\n")
            lines.insert(i+3, "    \n")
            print(f"Logger agregado en línea {i+2}")
        break

# Encontrar "if request.method == 'POST':"
for i in range(nuevo_start, min(nuevo_start + 30, len(lines))):
    if "if request.method == 'POST':" in lines[i]:
        # Agregar log después
        if '=== NUEVO PRODUCTO POST ===' not in ''.join(lines[i:i+5]):
            indent = '        '
            lines.insert(i+1, f"{indent}try:\n")
            lines.insert(i+2, f"{indent}    logger.info(f'=== NUEVO PRODUCTO POST === Usuario: {{current_user.username}}')\n")
            lines.insert(i+3, f"{indent}    logger.info(f'Client IP: {{request.headers.get(\"X-Forwarded-For\", request.remote_addr)}}')\n")
            lines.insert(i+4, f"{indent}    \n")
            print(f"Log POST agregado en línea {i+2}")
        break

# Encontrar db.session.add(producto)
for i in range(nuevo_start, len(lines)):
    if 'db.session.add(producto)' in lines[i] and i > nuevo_start + 20:
        if 'Agregando producto' not in ''.join(lines[max(0,i-2):i]):
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            lines.insert(i, f"{indent}logger.info(f'Agregando producto: codigo={{codigo}}, nombre={{nombre}}')\n")
            print(f"Log add agregado en línea {i+1}")
        break

# Encontrar db.session.commit()
for i in range(nuevo_start, len(lines)):
    if 'db.session.commit()' in lines[i] and i > nuevo_start + 20:
        if 'Ejecutando commit' not in ''.join(lines[max(0,i-2):i]):
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            lines.insert(i, f"{indent}logger.info('Ejecutando db.session.commit()')\n")
            lines.insert(i+2, f"{indent}logger.info(f'=== PRODUCTO GUARDADO === ID: {{producto.id_producto}}')\n")
            print(f"Log commit agregado en línea {i+1}")
        break

# Encontrar el return redirect después del commit y agregar except antes
for i in range(nuevo_start, len(lines)):
    if 'return redirect(url_for' in lines[i] and 'productos.listar' in lines[i] and i > nuevo_start + 40:
        # Buscar hacia atrás para encontrar dónde termina el bloque try
        if 'except Exception as e:' not in ''.join(lines[i:min(i+20, len(lines))]):
            indent = '        '
            lines.insert(i+2, f"{indent}\n")
            lines.insert(i+3, f"{indent}except Exception as e:\n")
            lines.insert(i+4, f"{indent}    logger.error(f'=== ERROR AL CREAR PRODUCTO ===')\n")
            lines.insert(i+5, f"{indent}    logger.error(f'Tipo: {{type(e).__name__}}, Mensaje: {{str(e)}}')\n")
            lines.insert(i+6, f"{indent}    import traceback\n")
            lines.insert(i+7, f"{indent}    logger.error(f'Traceback: {{traceback.format_exc()}}')\n")
            lines.insert(i+8, f"{indent}    db.session.rollback()\n")
            lines.insert(i+9, f"{indent}    flash(f'Error al crear producto: {{str(e)}}', 'danger')\n")
            lines.insert(i+10, f"{indent}    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()\n")
            lines.insert(i+11, f"{indent}    return render_template('productos/form.html', categorias=categorias, producto=None)\n")
            print(f"Bloque except agregado en línea {i+4}")
        break

# Escribir el archivo
print("Escribiendo archivo modificado...")
with open(PRODUCTOS_FILE, 'w') as f:
    f.writelines(lines)

print("\n✓ Parche aplicado exitosamente!")
print("\nAhora ejecuta:")
print("  sudo systemctl restart inventario-ventas")
print("  sudo journalctl -u inventario-ventas -f | grep -E 'NUEVO PRODUCTO|GUARDADO|ERROR'")
