import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
from decimal import Decimal
from datetime import datetime
from app import create_app, db
from app.models.producto import Producto, Categoria
from app.models.proveedor import Proveedor
from app.models.usuario import Usuario
from sqlalchemy.exc import IntegrityError

import csv
from decimal import Decimal
from datetime import datetime
from app import create_app, db
from app.models.producto import Producto, Categoria
from app.models.proveedor import Proveedor
from app.models.usuario import Usuario
from sqlalchemy.exc import IntegrityError

# Configuración
CSV_FILE = 'Base de datos/PRODUCTO_202601141659.csv'
PROVEEDOR_DEFAULT = 'Proveedor General'

# Cache para no consultar la BD repetidamente
categorias_cache = {}

def get_categoria_by_name(nombre_categoria):
    """Busca o crea una categoría por nombre"""
    if not nombre_categoria or nombre_categoria.strip() == '':
        nombre_categoria = 'Sin Categoría'
    
    nombre_categoria = nombre_categoria.strip().upper()
    
    # Buscar en caché primero
    if nombre_categoria in categorias_cache:
        return categorias_cache[nombre_categoria]
    
    # Buscar en BD
    cat = Categoria.query.filter_by(nombre=nombre_categoria).first()
    
    if not cat:
        print(f"✨ Creando nueva categoría: {nombre_categoria}")
        cat = Categoria(
            nombre=nombre_categoria, 
            descripcion='Importada automáticamente',
            activo=True
        )
        db.session.add(cat)
        db.session.commit()
    
    # Guardar en caché
    categorias_cache[nombre_categoria] = cat
    return cat

def get_or_create_proveedor():
    prov = Proveedor.query.filter_by(nombre=PROVEEDOR_DEFAULT).first()
    if not prov:
        print(f"Creando proveedor: {PROVEEDOR_DEFAULT}")
        prov = Proveedor(
            nombre=PROVEEDOR_DEFAULT, 
            ruc='88888888-8', 
            telefono='0900000000'
        )
        db.session.add(prov)
        db.session.commit()
    return prov

def get_admin_user():
    user = Usuario.query.filter_by(username='admin').first()
    return user.id_usuario if user else None

def clean_decimal(value):
    if not value or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except:
        return Decimal('0')

def importar_productos(dry_run=False, limit=None):
    app = create_app()
    with app.app_context():
        print(f"Iniciando importación desde: {CSV_FILE}")
        
        if not os.path.exists(CSV_FILE):
            print(f"❌ Error: No se encuentra el archivo {CSV_FILE}")
            # Intentar buscar el archivo más reciente si el nombre exacto no existe
            import glob
            files = glob.glob('Base de datos/*.csv')
            if files:
                print(f"ℹ️  Archivos encontrados: {files}")
            return

        prov = get_or_create_proveedor()
        user_id = get_admin_user()
        
        count = 0
        errores = 0
        duplicados = 0
        actualizados = 0
        nuevos = 0
        
        try:
            with open(CSV_FILE, mode='r', encoding='utf-8') as csvfile:
                # Detectar formato automáticamente
                sample = csvfile.read(1024)
                csvfile.seek(0)
                dialect = csv.Sniffer().sniff(sample)
                
                reader = csv.DictReader(csvfile)
                
                # Verificar columnas
                if 'PRODUCTO' not in reader.fieldnames:
                    print(f"⚠️ Alerta: Columnas encontradas: {reader.fieldnames}")
                    # Mapeo de fallback por si acaso
                
                print("Columnas detectadas:", reader.fieldnames)

                for row in reader:
                    if limit and count >= limit:
                        break
                        
                    try:
                        # Datos del CSV
                        # "ID_PRODUCTO","BARRAS","PRODUCTO","COSTO_PROMEDIO","CATEGORIA","PRECIO_PUBLICO","PRECIO_MAYORISTA","STOCK_ACTUAL"
                        if 'PRODUCTO' in row:
                            nombre = row['PRODUCTO'].strip()
                        elif 'DESCRIPCION' in row:
                            nombre = row['DESCRIPCION'].strip()
                        else:
                            nombre = "Sin Nombre"

                        codigo_barras = row.get('BARRAS', '').strip()
                        if not codigo_barras or codigo_barras == '""':
                            codigo_barras = None
                            
                        nombre_categoria = row.get('CATEGORIA', 'General')
                        precio_publico = clean_decimal(row.get('PRECIO_PUBLICO', 0))
                        precio_mayorista = clean_decimal(row.get('PRECIO_MAYORISTA', 0))
                        precio_compra = clean_decimal(row.get('COSTO_PROMEDIO', 0))
                        stock_actual = clean_decimal(row.get('STOCK_ACTUAL', 0))
                        
                        id_externo = row.get('ID_PRODUCTO', str(count))
                        codigo_interno = f"IMP-{id_externo}"
                        
                        # Obtener categoría real
                        cat = get_categoria_by_name(nombre_categoria)
                        
                        # Validaciones básicas
                        if not nombre:
                            errores += 1
                            continue

                        # Buscar si ya existe por código de barras (si tiene) o por código interno
                        producto_existente = None
                        
                        # Primero intentar por código de barras si es válido
                        if codigo_barras and len(codigo_barras) > 2:
                            producto_existente = Producto.query.filter_by(codigo_barras=codigo_barras).first()
                        
                        # Si no, buscar por código interno (ID antiguo)
                        if not producto_existente:
                            producto_existente = Producto.query.filter_by(codigo=codigo_interno).first()

                        if producto_existente:
                            if not dry_run:
                                # Actualizar datos importantes
                                producto_existente.nombre = nombre
                                producto_existente.id_categoria = cat.id_categoria
                                producto_existente.precio_venta = precio_publico
                                producto_existente.precio_mayorista = precio_mayorista
                                producto_existente.precio_compra = precio_compra
                                producto_existente.stock_actual = stock_actual # Actualizamos stock también
                                if codigo_barras:
                                    producto_existente.codigo_barras = codigo_barras
                                
                                producto_existente.fecha_modificacion = datetime.utcnow()
                                db.session.commit()
                            actualizados += 1
                        else:
                            # Crear nuevo producto
                            nuevo_producto = Producto(
                                codigo=codigo_interno,
                                codigo_barras=codigo_barras,
                                nombre=nombre,
                                descripcion=f'Importado de categoría: {nombre_categoria}',
                                id_categoria=cat.id_categoria,
                                id_proveedor_principal=prov.id_proveedor,
                                precio_venta=precio_publico,
                                precio_mayorista=precio_mayorista,
                                precio_compra=precio_compra,
                                stock_actual=stock_actual,
                                stock_minimo=5,
                                porcentaje_iva=10,
                                activo=True,
                                id_usuario_modificacion=user_id
                            )
                            
                            if not dry_run:
                                db.session.add(nuevo_producto)
                                db.session.commit()
                            nuevos += 1
                        
                        count += 1
                            
                    except IntegrityError:
                        db.session.rollback()
                        print(f"⚠️ Error de integridad: {row.get('PRODUCTO', '?')}")
                        duplicados += 1
                    except Exception as e:
                        db.session.rollback()
                        print(f"❌ Error en fila {count}: {str(e)}")
                        errores += 1
                        
                    if count % 200 == 0 and count > 0:
                        db.session.commit() # Commit intermedio para liberar memoria
                        print(f"Procesados: {count}...")

        except Exception as e:
            print(f"❌ Error fatal: {str(e)}")
            return

        print("\n" + "="*40)
        print(f"REPORTE FINAL {'(DRY RUN)' if dry_run else ''}")
        print("="*40)
        print(f"✅ Nuevos creados:   {nuevos}")
        print(f"🔄 Actualizados:     {actualizados}")
        print(f"⚠️ Errores/Ign:      {errores + duplicados}")
        print(f"📊 Total procesados: {count}")
        print("="*40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Importar productos desde CSV')
    parser.add_argument('--dry-run', action='store_true', help='Simular sin guardar cambios')
    parser.add_argument('--limit', type=int, help='Limitar número de registros a procesar')
    args = parser.parse_args()
    
    importar_productos(dry_run=args.dry_run, limit=args.limit)
