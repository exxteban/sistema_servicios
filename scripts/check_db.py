"""Script para diagnosticar problemas en la base de datos"""
import sqlite3

db_path = 'inventario.db'
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys=ON")
cursor = conn.cursor()

# Check usuarios table schema
print("=" * 60)
print("TABLA USUARIOS - SCHEMA")
print("=" * 60)
cursor.execute("PRAGMA table_info(usuarios)")
columns = cursor.fetchall()
for col in columns:
    print(f"{col[1]}: {col[2]}")

# Check if there's a user management route missing
print("\n" + "=" * 60)
print("ROLES EN LA BASE DE DATOS")
print("=" * 60)
cursor.execute("SELECT * FROM roles")
roles = cursor.fetchall()
for role in roles:
    print(role)

print("\n" + "=" * 60)
print("PERMISOS ROL TECNICO (REPARACIONES)")
print("=" * 60)
cursor.execute(
    """
    SELECT p.codigo, p.nombre
    FROM permisos p
    JOIN rol_permisos rp ON rp.id_permiso = p.id_permiso
    JOIN roles r ON r.id_rol = rp.id_rol
    WHERE r.nombre = ?
      AND p.activo = 1
      AND p.modulo = 'reparaciones'
    ORDER BY p.codigo
    """,
    ("Tecnico",),
)
tecnico_reparaciones = cursor.fetchall()
print(f"Total permisos reparaciones: {len(tecnico_reparaciones)}")
for row in tecnico_reparaciones:
    print(row)
codigos = {row[0] for row in tecnico_reparaciones}
print(f"Tiene cambiar_estado_reparacion: {'cambiar_estado_reparacion' in codigos}")

# Check permisos
print("\n" + "=" * 60)
print("PERMISOS TOTALES")
print("=" * 60)
cursor.execute("SELECT COUNT(*) FROM permisos")
count = cursor.fetchone()
print(f"Total permisos: {count[0]}")

# Check compras
print("\n" + "=" * 60)
print("COMPRAS")
print("=" * 60)
cursor.execute("SELECT COUNT(*) FROM compras")
count = cursor.fetchone()
print(f"Total compras: {count[0]}")

# Check if proveedores exist
print("\n" + "=" * 60)
print("PROVEEDORES")
print("=" * 60)
cursor.execute("SELECT id_proveedor, nombre, activo FROM proveedores")
proveedores = cursor.fetchall()
print(f"Total proveedores: {len(proveedores)}")
for prov in proveedores[:5]:
    print(f"  - {prov}")

# Check if productos exist
print("\n" + "=" * 60)
print("PRODUCTOS")
print("=" * 60)
cursor.execute("SELECT COUNT(*) FROM productos WHERE activo = 1")
count = cursor.fetchone()
print(f"Total productos activos: {count[0]}")

print("\n" + "=" * 60)
print("INTEGRIDAD (FK)")
print("=" * 60)
cursor.execute("PRAGMA foreign_key_check")
fk_rows = cursor.fetchall()
print(f"foreign_key_check rows: {len(fk_rows)}")
for row in fk_rows[:20]:
    print(row)

print("\n" + "=" * 60)
print("STOCK NEGATIVO")
print("=" * 60)
cursor.execute("SELECT id_producto, codigo, nombre, stock_actual FROM productos WHERE stock_actual < 0 ORDER BY stock_actual ASC")
negativos = cursor.fetchall()
print(f"Productos con stock negativo: {len(negativos)}")
for p in negativos[:20]:
    print(f"  - {p}")

conn.close()
print("\n✅ Verificación completada")
