import argparse
import os

from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'inventario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


def _resolve_target_client(slug: str | None, id_cliente: int | None):
    if slug:
        row = db.session.execute(
            text(
                """
                SELECT id_cliente, slug
                FROM tienda_config
                WHERE activa = 1 AND lower(slug) = lower(:slug)
                LIMIT 1
                """
            ),
            {'slug': slug},
        ).mappings().first()
        if not row:
            raise ValueError(f'No existe una tienda activa con slug "{slug}".')
        return int(row['id_cliente']), row['slug']

    if id_cliente:
        row = db.session.execute(
            text(
                """
                SELECT id_cliente, slug
                FROM tienda_config
                WHERE activa = 1 AND id_cliente = :id_cliente
                LIMIT 1
                """
            ),
            {'id_cliente': id_cliente},
        ).mappings().first()
        if not row:
            raise ValueError(f'No existe una tienda activa para el cliente {id_cliente}.')
        return int(row['id_cliente']), row['slug']

    stores = db.session.execute(
        text(
            """
            SELECT id_cliente, slug
            FROM tienda_config
            WHERE activa = 1
            ORDER BY id_config ASC
            """
        )
    ).mappings().all()

    if not stores:
        raise ValueError('No hay tiendas activas en tienda_config.')
    if len(stores) > 1:
        raise ValueError(
            'Hay múltiples tiendas activas. Ejecuta con --slug <slug> o --id-cliente <id>.'
        )
    store = stores[0]
    return int(store['id_cliente']), store['slug']


def _ensure_column_exists():
    dialect = db.engine.dialect.name
    if dialect == 'mysql':
        exists = db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'productos'
                  AND COLUMN_NAME = 'id_cliente'
                """
            )
        ).scalar()
        return bool(exists)

    cols_prod = [row[1] for row in db.session.execute(text("PRAGMA table_info(productos)")).fetchall()]
    return 'id_cliente' in cols_prod


def run_backfill(slug: str | None, id_cliente: int | None, dry_run: bool):
    with app.app_context():
        if not _ensure_column_exists():
            raise RuntimeError('La columna productos.id_cliente no existe. Ejecuta primero migrations/productos_cliente_scope.py')

        target_client_id, resolved_slug = _resolve_target_client(slug, id_cliente)
        rows = db.session.execute(
            text(
                """
                SELECT id_producto, nombre
                FROM productos
                WHERE publicado_tienda = 1
                  AND id_cliente IS NULL
                ORDER BY id_producto ASC
                """
            )
        ).mappings().all()

        if not rows:
            print('No hay productos publicados con id_cliente nulo.')
            return

        print(f'Tienda destino: cliente={target_client_id}, slug={resolved_slug}')
        print(f'Productos a actualizar: {len(rows)}')

        if dry_run:
            for row in rows[:20]:
                print(f"- {row['id_producto']}: {row['nombre']}")
            if len(rows) > 20:
                print(f'... y {len(rows) - 20} más')
            print('Dry-run finalizado. No se realizaron cambios.')
            return

        db.session.execute(
            text(
                """
                UPDATE productos
                SET id_cliente = :id_cliente
                WHERE publicado_tienda = 1
                  AND id_cliente IS NULL
                """
            ),
            {'id_cliente': target_client_id},
        )
        db.session.commit()
        print('Backfill completado.')


def parse_args():
    parser = argparse.ArgumentParser(description='Backfill seguro para productos.id_cliente de Tienda Online.')
    parser.add_argument('--slug', help='Slug de la tienda destino.')
    parser.add_argument('--id-cliente', type=int, help='ID del cliente destino.')
    parser.add_argument('--apply', action='store_true', help='Aplica cambios. Sin este flag corre en dry-run.')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    run_backfill(args.slug, args.id_cliente, dry_run=not args.apply)
