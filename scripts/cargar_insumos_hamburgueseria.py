"""Carga los insumos de una hamburgueseria en el inventario central (Productos) con su presentacion de compra.

Uso (desde la raiz del repo, con el mismo env que el servicio):
    python scripts/cargar_insumos_hamburgueseria.py --dry-run          # muestra que haria
    python scripts/cargar_insumos_hamburgueseria.py                    # usa el unico cliente con gastronomia activa
    python scripts/cargar_insumos_hamburgueseria.py --cliente-id 3

El stock se guarda en enteros de la unidad base (g, ml, unidad, mazo); la presentacion permite
cargar compras como "5 Kilo" = 5000 g. Se puede correr varias veces: busca por nombre, no borra
nada, no toca el stock ni la unidad de un insumo existente y solo suma presentaciones faltantes.
"""
import argparse

from demo_menu_utils import _resolver_cliente_id, slug

CATEGORIA = 'Insumos cocina'
KILO = ('Kilo', 1000)
LITRO = ('Litro', 1000)

# (nombre, unidad base, presentaciones de compra)
INSUMOS = [
    ('Tapa de costilla', 'g', [KILO]),
    ('Panceta', 'g', [KILO]),
    ('Pan de hamburguesa', 'unidad', []),
    ('Queso cheddar (feta)', 'unidad', []),
    ('Lechuga repollada', 'g', [KILO]),
    ('Tomate', 'g', [KILO]),
    ('Cebolla', 'g', [KILO]),
    ('Pepinillos', 'g', [KILO]),
    ('Jalapeños', 'g', [KILO]),
    ('Ajo', 'g', [KILO]),
    ('Albahaca', 'mazo', []),
    ('Aceite de girasol', 'ml', [LITRO]),
    ('Huevos', 'unidad', [('Maple', 30)]),
    ('Vinagre de alcohol', 'ml', [LITRO]),
    ('Sal', 'g', [KILO]),
    # Preparaciones propias: se les suma stock al hacer cada tanda.
    ('Cebolla caramelizada', 'g', [KILO]),
    ('Salsa de ajo', 'ml', [LITRO]),
    ('Salsa de albahaca', 'ml', [LITRO]),
    ('Mayonesa', 'g', [KILO]),
    ('Kétchup', 'g', [KILO]),
    ('Mostaza', 'g', [KILO]),
    # Descartables que conviene contar.
    ('Caja para hamburguesa', 'unidad', []),
    ('Papel envoltorio', 'unidad', []),
    ('Bolsa para delivery', 'unidad', []),
]


def _categoria():
    from app import db
    from app.models.producto import Categoria

    categoria = Categoria.query.filter(db.func.lower(Categoria.nombre) == CATEGORIA.lower()).first()
    if categoria is None:
        categoria = Categoria(nombre=CATEGORIA, descripcion='Materias primas para recetas de gastronomia', activo=True)
        db.session.add(categoria)
        db.session.flush()
    return categoria


def _buscar_insumo(cliente_id, nombre):
    from app import db
    from app.models.producto import Producto

    return Producto.query.filter(
        Producto.id_cliente == cliente_id,
        Producto.activo.is_(True),
        db.func.lower(Producto.nombre) == nombre.lower(),
    ).first()


def cargar(cliente_id, dry_run=False):
    from app import db
    from app.models.producto import Producto
    from app.models.producto_presentacion import ProductoPresentacionStock

    categoria = _categoria()
    creados = existentes = presentaciones = 0
    for nombre, unidad, compras in INSUMOS:
        insumo = _buscar_insumo(cliente_id, nombre)
        if insumo is None:
            insumo = Producto(
                codigo=f'INS-{cliente_id}-{slug(nombre)}'.upper()[:50],
                nombre=nombre,
                id_categoria=categoria.id_categoria,
                id_cliente=cliente_id,
                precio_compra=0,
                precio_venta=0,
                stock_actual=0,
                stock_minimo=0,
                unidad_stock=unidad,
                es_servicio=False,
                activo=True,
            )
            db.session.add(insumo)
            db.session.flush()
            creados += 1
            print(f'+ {nombre} ({unidad})')
        else:
            existentes += 1
            aviso = '' if insumo.unidad_stock == unidad else f'  [se deja en {insumo.unidad_stock}, el script sugiere {unidad}]'
            print(f'= {nombre} ya existe{aviso}')
        actuales = {p.nombre.lower() for p in insumo.presentaciones_stock.filter_by(activo=True).all()}
        for compra, factor in compras:
            if compra.lower() in actuales or insumo.unidad_stock != unidad:
                continue
            db.session.add(ProductoPresentacionStock(id_producto=insumo.id_producto, nombre=compra, factor_unidad_base=factor))
            presentaciones += 1
            print(f'    presentacion {compra} = {factor} {unidad}')

    if dry_run:
        db.session.rollback()
        print('\n(dry-run: no se guardo nada)')
    else:
        db.session.commit()
    print(f'\nInsumos creados: {creados} | ya existian: {existentes} | presentaciones nuevas: {presentaciones}')


def main():
    parser = argparse.ArgumentParser(description='Carga insumos de hamburgueseria en el inventario central.')
    parser.add_argument('--cliente-id', type=int)
    parser.add_argument('--dry-run', action='store_true', help='Muestra lo que haria sin guardar.')
    parser.add_argument('--si', action='store_true', help='No pide confirmacion antes de guardar.')
    args = parser.parse_args()

    from app import create_app, db
    from app.models.cliente import Cliente

    app = create_app()
    with app.app_context():
        # En un servidor con varias instancias la base sale de ENV_FILE_PATH: mostrarla antes de escribir.
        cliente_id = _resolver_cliente_id(args.cliente_id)
        cliente = db.session.get(Cliente, cliente_id)
        print(f'Base de datos: {db.engine.url.render_as_string(hide_password=True)}')
        print(f'Cliente {cliente_id}: {cliente.nombre if cliente else "(no existe)"}\n')
        if cliente is None:
            raise SystemExit('Ese cliente no existe en esta base.')
        if not args.dry_run and not args.si and input('Cargar los insumos aca? [s/N] ').strip().lower() != 's':
            raise SystemExit('Cancelado.')
        cargar(cliente_id, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
