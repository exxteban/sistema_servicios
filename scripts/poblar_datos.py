import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Script para poblar la base de datos con datos de prueba
"""
from app import create_app, db
from app.models import (
    Producto, Categoria, Proveedor, Cliente, Usuario
)

app = create_app()

with app.app_context():
    print("🔄 Poblando base de datos con datos de prueba...")
    
    # Obtener categorías existentes
    cat_termos = Categoria.query.filter_by(nombre='Termos').first()
    cat_guampas = Categoria.query.filter_by(nombre='Guampas').first()
    cat_mates = Categoria.query.filter_by(nombre='Mates').first()
    cat_bombillas = Categoria.query.filter_by(nombre='Bombillas').first()
    cat_yerbas = Categoria.query.filter_by(nombre='Yerbas').first()
    cat_accesorios = Categoria.query.filter_by(nombre='Accesorios').first()
    
    # Crear proveedores
    proveedores = [
        Proveedor(nombre='Stanley Argentina', ruc='80123456-7', telefono='021-555-0001', 
                  email='ventas@stanley.com.ar', dias_credito=30),
        Proveedor(nombre='Lumilagro S.A.', ruc='80234567-8', telefono='021-555-0002',
                  email='pedidos@lumilagro.com.py', dias_credito=15),
        Proveedor(nombre='Importadora Matear', ruc='80345678-9', telefono='021-555-0003',
                  email='info@matear.com.py', dias_credito=0),
    ]
    
    for prov in proveedores:
        if not Proveedor.query.filter_by(nombre=prov.nombre).first():
            db.session.add(prov)
    
    db.session.commit()
    print("✓ Proveedores creados")
    
    # Obtener proveedores
    prov_stanley = Proveedor.query.filter_by(nombre='Stanley Argentina').first()
    prov_lumilagro = Proveedor.query.filter_by(nombre='Lumilagro S.A.').first()
    prov_matear = Proveedor.query.filter_by(nombre='Importadora Matear').first()
    
    # Crear productos
    productos = [
        # Termos
        Producto(codigo='TERM001', nombre='Termo Stanley Classic 1L Verde', 
                 descripcion='Termo clásico Stanley de 1 litro, mantiene calor por 24hs',
                 id_categoria=cat_termos.id_categoria, id_proveedor_principal=prov_stanley.id_proveedor,
                 marca='Stanley', modelo='Classic', color='Verde', capacidad='1L',
                 precio_compra=85000, precio_venta=150000, precio_mayorista=130000,
                 porcentaje_iva=10, stock_actual=15, stock_minimo=5),
        
        Producto(codigo='TERM002', nombre='Termo Stanley Classic 1.4L Azul',
                 descripcion='Termo Stanley 1.4 litros, ideal para compartir',
                 id_categoria=cat_termos.id_categoria, id_proveedor_principal=prov_stanley.id_proveedor,
                 marca='Stanley', modelo='Classic', color='Azul', capacidad='1.4L',
                 precio_compra=95000, precio_venta=165000, precio_mayorista=145000,
                 porcentaje_iva=10, stock_actual=12, stock_minimo=5),
        
        Producto(codigo='TERM003', nombre='Termo Lumilagro 1L Negro',
                 descripcion='Termo económico de buena calidad',
                 id_categoria=cat_termos.id_categoria, id_proveedor_principal=prov_lumilagro.id_proveedor,
                 marca='Lumilagro', color='Negro', capacidad='1L',
                 precio_compra=45000, precio_venta=80000, precio_mayorista=70000,
                 porcentaje_iva=10, stock_actual=25, stock_minimo=10),
        
        # Guampas
        Producto(codigo='GUAM001', nombre='Guampa de Asta Natural Chica',
                 descripcion='Guampa artesanal de asta natural, 350ml',
                 id_categoria=cat_guampas.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Artesanal', capacidad='350ml',
                 precio_compra=25000, precio_venta=45000, precio_mayorista=40000,
                 porcentaje_iva=10, stock_actual=30, stock_minimo=10),
        
        Producto(codigo='GUAM002', nombre='Guampa de Asta Natural Grande',
                 descripcion='Guampa artesanal de asta natural, 500ml',
                 id_categoria=cat_guampas.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Artesanal', capacidad='500ml',
                 precio_compra=35000, precio_venta=60000, precio_mayorista=52000,
                 porcentaje_iva=10, stock_actual=20, stock_minimo=8),
        
        Producto(codigo='GUAM003', nombre='Guampa de Aluminio Grabada',
                 descripcion='Guampa de aluminio con grabados decorativos',
                 id_categoria=cat_guampas.id_categoria, id_proveedor_principal=prov_lumilagro.id_proveedor,
                 marca='Lumilagro', capacidad='400ml',
                 precio_compra=30000, precio_venta=55000, precio_mayorista=48000,
                 porcentaje_iva=10, stock_actual=18, stock_minimo=8),
        
        # Mates
        Producto(codigo='MATE001', nombre='Mate de Calabaza Natural',
                 descripcion='Mate tradicional de calabaza curada',
                 id_categoria=cat_mates.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Artesanal',
                 precio_compra=15000, precio_venta=28000, precio_mayorista=24000,
                 porcentaje_iva=10, stock_actual=40, stock_minimo=15),
        
        Producto(codigo='MATE002', nombre='Mate de Madera Tallado',
                 descripcion='Mate de madera con tallados artesanales',
                 id_categoria=cat_mates.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Artesanal',
                 precio_compra=20000, precio_venta=38000, precio_mayorista=32000,
                 porcentaje_iva=10, stock_actual=25, stock_minimo=10),
        
        # Bombillas
        Producto(codigo='BOMB001', nombre='Bombilla Alpaca Lisa',
                 descripcion='Bombilla de alpaca tradicional',
                 id_categoria=cat_bombillas.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Standard',
                 precio_compra=8000, precio_venta=15000, precio_mayorista=13000,
                 porcentaje_iva=10, stock_actual=50, stock_minimo=20),
        
        Producto(codigo='BOMB002', nombre='Bombilla Acero Inoxidable',
                 descripcion='Bombilla de acero inoxidable con filtro desmontable',
                 id_categoria=cat_bombillas.id_categoria, id_proveedor_principal=prov_lumilagro.id_proveedor,
                 marca='Lumilagro',
                 precio_compra=12000, precio_venta=22000, precio_mayorista=19000,
                 porcentaje_iva=10, stock_actual=35, stock_minimo=15),
        
        # Yerbas
        Producto(codigo='YERB001', nombre='Yerba Selecta 500g',
                 descripcion='Yerba mate tradicional paraguaya',
                 id_categoria=cat_yerbas.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Selecta', capacidad='500g',
                 precio_compra=8500, precio_venta=15000, precio_mayorista=13000,
                 porcentaje_iva=5, stock_actual=100, stock_minimo=30),
        
        Producto(codigo='YERB002', nombre='Yerba Pajarito 1kg',
                 descripcion='Yerba mate premium argentina',
                 id_categoria=cat_yerbas.id_categoria, id_proveedor_principal=prov_matear.id_proveedor,
                 marca='Pajarito', capacidad='1kg',
                 precio_compra=18000, precio_venta=32000, precio_mayorista=28000,
                 porcentaje_iva=5, stock_actual=80, stock_minimo=25),
        
        # Accesorios
        Producto(codigo='ACC001', nombre='Yerbera de Acero',
                 descripcion='Recipiente para guardar yerba mate',
                 id_categoria=cat_accesorios.id_categoria, id_proveedor_principal=prov_lumilagro.id_proveedor,
                 marca='Lumilagro',
                 precio_compra=15000, precio_venta=28000, precio_mayorista=24000,
                 porcentaje_iva=10, stock_actual=20, stock_minimo=8),
        
        Producto(codigo='ACC002', nombre='Azucarera con Cuchara',
                 descripcion='Azucarera de acero con cuchara incluida',
                 id_categoria=cat_accesorios.id_categoria, id_proveedor_principal=prov_lumilagro.id_proveedor,
                 marca='Lumilagro',
                 precio_compra=12000, precio_venta=22000, precio_mayorista=19000,
                 porcentaje_iva=10, stock_actual=25, stock_minimo=10),
        
        Producto(codigo='ACC003', nombre='Bolso Matero Térmico',
                 descripcion='Bolso térmico para termo y accesorios',
                 id_categoria=cat_accesorios.id_categoria, id_proveedor_principal=prov_stanley.id_proveedor,
                 marca='Stanley',
                 precio_compra=35000, precio_venta=65000, precio_mayorista=55000,
                 porcentaje_iva=10, stock_actual=15, stock_minimo=5),
    ]
    
    for prod in productos:
        if not Producto.query.filter_by(codigo=prod.codigo).first():
            db.session.add(prod)
    
    db.session.commit()
    print("✓ Productos creados")
    
    # Crear clientes adicionales
    clientes = [
        Cliente(nombre='María González', ruc_ci='3456789-0', telefono='0981-123456',
                tipo='minorista', email='maria.gonzalez@email.com'),
        Cliente(nombre='Comercial El Matero', ruc_ci='80456789-0', telefono='021-555-1001',
                tipo='mayorista', limite_credito=5000000, email='ventas@elmatero.com.py'),
        Cliente(nombre='Juan Pérez', ruc_ci='2345678-9', telefono='0982-234567',
                tipo='minorista'),
        Cliente(nombre='Distribuidora Sur', ruc_ci='80567890-1', telefono='021-555-2002',
                tipo='empresa', limite_credito=10000000, email='compras@distrisur.com.py'),
        Cliente(nombre='Ana Martínez', ruc_ci='4567890-1', telefono='0983-345678',
                tipo='minorista', email='ana.martinez@email.com'),
    ]
    
    for cliente in clientes:
        if not Cliente.query.filter_by(ruc_ci=cliente.ruc_ci).first():
            db.session.add(cliente)
    
    db.session.commit()
    print("✓ Clientes creados")
    
    # Crear usuario vendedor adicional
    vendedor = Usuario.query.filter_by(username='vendedor').first()
    if not vendedor:
        vendedor = Usuario(
            username='vendedor',
            nombre_completo='Vendedor de Prueba',
            id_rol=3
        )
        vendedor.set_password('vendedor123')
        db.session.add(vendedor)
        db.session.commit()
        print("✓ Usuario vendedor creado (usuario: vendedor, password: vendedor123)")
    
    print("\n✅ Base de datos poblada exitosamente!")
    print("\n📊 Resumen:")
    print(f"   - {Producto.query.count()} productos")
    print(f"   - {Proveedor.query.count()} proveedores")
    print(f"   - {Cliente.query.count()} clientes")
    print(f"   - {Usuario.query.count()} usuarios")
    print("\n🔐 Usuarios disponibles:")
    print("   - admin / admin123 (Administrador)")
    print("   - vendedor / vendedor123 (Vendedor)")
