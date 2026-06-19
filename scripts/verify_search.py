import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Producto, Categoria

# Disable flask logging
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = create_app()
with app.app_context():
    # Ensure we have a product and category for testing
    cat_name = "CategoriaTestSearch"
    cat = Categoria.query.filter_by(nombre=cat_name).first()
    if not cat:
        cat = Categoria(nombre=cat_name)
        db.session.add(cat)
        db.session.commit()
    
    prod_name = "ProductoTestSearch"
    prod = Producto.query.filter_by(codigo="TESTSEARCH").first()
    if not prod:
        prod = Producto(codigo="TESTSEARCH", nombre=prod_name, id_categoria=cat.id_categoria, precio_venta=100)
        db.session.add(prod)
        db.session.commit()
        
    print("--- START TESTS ---")
    
    # Test API Logic
    q = cat_name
    productos = Producto.query.join(Categoria, Producto.id_categoria == Categoria.id_categoria).filter(
        Producto.activo == True,
        db.or_(
            Producto.nombre.ilike(f'%{q}%'),
            Producto.codigo.ilike(f'%{q}%'),
            Categoria.nombre.ilike(f'%{q}%')
        )
    ).all()
    
    found = any(p.codigo == "TESTSEARCH" for p in productos)
    print(f"API_SEARCH: {'PASS' if found else 'FAIL'}")
    
    # Test Listar Logic
    query = Producto.query.filter_by(activo=True)
    buscar = cat_name
    
    query = query.join(Categoria, Producto.id_categoria == Categoria.id_categoria)
    query = query.filter(
        db.or_(
            Producto.nombre.ilike(f'%{buscar}%'),
            Producto.codigo.ilike(f'%{buscar}%'),
            Categoria.nombre.ilike(f'%{buscar}%')
        )
    )
    results = query.all()
    found_listar = any(p.codigo == "TESTSEARCH" for p in results)
    
    print(f"LISTAR_SEARCH: {'PASS' if found_listar else 'FAIL'}")

    # Clean up
    prod = Producto.query.filter_by(codigo="TESTSEARCH").first()
    cat = Categoria.query.filter_by(nombre=cat_name).first()
    
    if prod:
        db.session.delete(prod)
    if cat:
        remaining = Producto.query.filter_by(id_categoria=cat.id_categoria).count()
        if remaining == 0:
            db.session.delete(cat)
            
    db.session.commit()
    print("--- END TESTS ---")
