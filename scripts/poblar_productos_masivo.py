import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from app import create_app, db
from app.models.producto import Producto, Categoria
from app.models.proveedor import Proveedor
from decimal import Decimal

def poblar_masivo(cantidad=100):
    app = create_app()
    with app.app_context():
        db_url = app.config.get('SQLALCHEMY_DATABASE_URI', 'Desconocida')
        print(f"🔌 Conectando a: {db_url}")
        if 'sqlite' in db_url:
            print("⚠️  ADVERTENCIA: Estás usando SQLite. Si deberías usar MySQL, configura DATABASE_URL.")
            
        print(f"🚀 Iniciando población masiva de {cantidad} productos...")

        # 1. Asegurar Categorías
        categorias_data = ['Celulares', 'Accesorios', 'Repuestos', 'Servicio Técnico', 'Gadgets']
        categorias_db = {}
        
        for cat_nombre in categorias_data:
            cat = Categoria.query.filter_by(nombre=cat_nombre).first()
            if not cat:
                cat = Categoria(nombre=cat_nombre, descripcion=f'Categoría de {cat_nombre}')
                db.session.add(cat)
                print(f"   + Categoría creada: {cat_nombre}")
            categorias_db[cat_nombre] = cat
        
        # 2. Asegurar Proveedor Genérico
        proveedor = Proveedor.query.filter_by(nombre='Proveedor General').first()
        if not proveedor:
            proveedor = Proveedor(
                nombre='Proveedor General',
                ruc='88888888-8',
                telefono='0981000000',
                email='proveedor@ejemplo.com',
                dias_credito=30
            )
            db.session.add(proveedor)
            print("   + Proveedor 'Proveedor General' creado")
        
        db.session.commit()

        # Recargar objetos para tener sus IDs
        for cat_nombre in categorias_data:
            categorias_db[cat_nombre] = Categoria.query.filter_by(nombre=cat_nombre).first()
        proveedor = Proveedor.query.filter_by(nombre='Proveedor General').first()

        # 3. Generar Productos
        marcas = ['Samsung', 'Apple', 'Xiaomi', 'Motorola', 'Huawei', 'Nokia']
        modelos_base = ['Galaxy S', 'iPhone', 'Redmi Note', 'Moto G', 'P', '1100']
        colores = ['Negro', 'Blanco', 'Azul', 'Dorado', 'Plata', 'Rojo']
        capacidades = ['64GB', '128GB', '256GB', '512GB']
        
        tipos_producto = [
            {'nombre': 'Celular', 'cat': 'Celulares', 'min_price': 800000, 'max_price': 8000000},
            {'nombre': 'Funda', 'cat': 'Accesorios', 'min_price': 20000, 'max_price': 150000},
            {'nombre': 'Cargador', 'cat': 'Accesorios', 'min_price': 50000, 'max_price': 250000},
            {'nombre': 'Pantalla', 'cat': 'Repuestos', 'min_price': 150000, 'max_price': 1500000},
            {'nombre': 'Auriculares', 'cat': 'Gadgets', 'min_price': 80000, 'max_price': 1200000},
        ]

        productos_creados = 0
        existing_codes = set(p.codigo for p in db.session.query(Producto.codigo).all())

        for i in range(cantidad):
            tipo = random.choice(tipos_producto)
            marca = random.choice(marcas)
            modelo_num = random.randint(10, 99)
            modelo_base = random.choice(modelos_base)
            
            # Construir nombre realista
            if tipo['nombre'] == 'Celular':
                nombre_prod = f"{marca} {modelo_base}{modelo_num}"
                detalle = f"{random.choice(capacidades)} {random.choice(colores)}"
            else:
                nombre_prod = f"{tipo['nombre']} para {marca} {modelo_base}{modelo_num}"
                detalle = random.choice(colores)
            
            nombre_completo = f"{nombre_prod} - {detalle}"
            
            # Generar código único
            codigo_base = f"{tipo['nombre'][:3].upper()}-{marca[:3].upper()}-{random.randint(1000, 9999)}"
            codigo = codigo_base
            suffix = 1
            while codigo in existing_codes:
                codigo = f"{codigo_base}-{suffix}"
                suffix += 1
            existing_codes.add(codigo)

            # Precios
            costo = random.randint(tipo['min_price'], tipo['max_price'])
            # Redondear a miles
            costo = (costo // 1000) * 1000
            margen = random.uniform(1.3, 1.8) # 30% a 80% de margen
            precio_venta = int(costo * margen)
            precio_venta = (precio_venta // 1000) * 1000 # Redondear

            nuevo_prod = Producto(
                codigo=codigo,
                codigo_barras=f"784{random.randint(100000000, 999999999)}",
                nombre=nombre_completo,
                descripcion=f"Producto generado automáticamente: {nombre_completo}",
                id_categoria=categorias_db[tipo['cat']].id_categoria,
                id_proveedor_principal=proveedor.id_proveedor,
                marca=marca,
                modelo=f"{modelo_base}{modelo_num}",
                color=detalle if tipo['nombre'] != 'Celular' else detalle.split()[-1],
                capacidad=detalle.split()[0] if tipo['nombre'] == 'Celular' else None,
                precio_compra=costo,
                precio_venta=precio_venta,
                precio_mayorista=int(precio_venta * 0.9),
                stock_actual=random.randint(0, 50),
                stock_minimo=5,
                porcentaje_iva=10
            )

            db.session.add(nuevo_prod)
            productos_creados += 1

            if productos_creados % 50 == 0:
                db.session.commit()
                print(f"   ... {productos_creados} productos procesados")

        db.session.commit()
        print(f"✅ Finalizado! Se agregaron {productos_creados} productos nuevos.")

if __name__ == '__main__':
    qty = 500
    if len(sys.argv) > 1:
        try:
            qty = int(sys.argv[1])
        except ValueError:
            pass
    poblar_masivo(qty)
