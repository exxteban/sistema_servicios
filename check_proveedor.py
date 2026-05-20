from app import create_app, db
from app.models import Proveedor

app = create_app()
with app.app_context():
    prov = Proveedor.query.get(1)
    if prov:
        print(f'✓ Proveedor ID 1 existe: {prov.nombre}')
    else:
        print('✗ Proveedor ID 1 no existe - ejecutar init_db')
        print('Ejecutando inicialización...')
        from app.utils.init_db import inicializar_datos_base
        inicializar_datos_base()
        prov = Proveedor.query.get(1)
        if prov:
            print(f'✓ Proveedor genérico creado: {prov.nombre}')
