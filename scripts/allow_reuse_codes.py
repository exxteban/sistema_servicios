#!/usr/bin/env python3
"""
Parche para permitir reutilizar códigos de productos desactivados
Modifica la validación para solo verificar productos ACTIVOS
"""

PRODUCTOS_FILE = 'app/routes/productos.py'

print("Leyendo productos.py...")
with open(PRODUCTOS_FILE, 'r') as f:
    content = f.read()

# Backup
with open(PRODUCTOS_FILE + '.backup2', 'w') as f:
    f.write(content)
print(f"Backup creado: {PRODUCTOS_FILE}.backup2")

# Reemplazar la validación de código único en la función nuevo()
old_validation = "if Producto.query.filter_by(codigo=codigo).first():"
new_validation = "if Producto.query.filter_by(codigo=codigo, activo=True).first():"

if old_validation in content:
    # Contar cuántas veces aparece
    count = content.count(old_validation)
    content = content.replace(old_validation, new_validation)
    print(f"✓ Validación actualizada ({count} ocurrencias)")
    print("  Ahora solo verifica productos ACTIVOS")
else:
    print("⚠ No se encontró la validación exacta")

# También actualizar en crear_rapido si existe
old_validation_rapido = 'if Producto.query.filter_by(codigo=codigo).first():'
if old_validation_rapido in content and old_validation_rapido != old_validation:
    content = content.replace(old_validation_rapido, 
                            'if Producto.query.filter_by(codigo=codigo, activo=True).first():')
    print("✓ También actualizado en crear_rapido")

# Escribir el archivo
with open(PRODUCTOS_FILE, 'w') as f:
    f.write(content)

print("\n✓ Parche aplicado!")
print("\nAhora puedes:")
print("  1. Reutilizar códigos de productos desactivados")
print("  2. El sistema solo verifica duplicados en productos ACTIVOS")
print("\nPara restaurar: cp app/routes/productos.py.backup2 app/routes/productos.py")
print("\nReinicia el servidor:")
print("  sudo systemctl restart inventario-ventas")
