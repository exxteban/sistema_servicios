from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'inventario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    return bool(db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
            """
        ),
        {'table_name': table_name, 'column_name': column_name},
    ).scalar())


def _mysql_index_exists(table_name: str, index_name: str) -> bool:
    return bool(db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND INDEX_NAME = :index_name
            """
        ),
        {'table_name': table_name, 'index_name': index_name},
    ).scalar())


def _mysql_fk_exists(table_name: str, fk_name: str) -> bool:
    return bool(db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND CONSTRAINT_NAME = :fk_name
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            """
        ),
        {'table_name': table_name, 'fk_name': fk_name},
    ).scalar())


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name

        if dialect == 'mysql':
            if not _mysql_column_exists('productos', 'id_cliente'):
                db.session.execute(text(
                    "ALTER TABLE productos ADD COLUMN id_cliente INT NULL"
                ))
                print('MySQL: columna productos.id_cliente agregada.')
            else:
                print('MySQL: columna productos.id_cliente ya existe.')

            if not _mysql_index_exists('productos', 'ix_productos_id_cliente'):
                db.session.execute(text(
                    "CREATE INDEX ix_productos_id_cliente ON productos(id_cliente)"
                ))
                print('MySQL: índice ix_productos_id_cliente creado.')
            else:
                print('MySQL: índice ix_productos_id_cliente ya existe.')

            if not _mysql_fk_exists('productos', 'fk_productos_cliente'):
                db.session.execute(text(
                    """
                    ALTER TABLE productos
                    ADD CONSTRAINT fk_productos_cliente
                    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
                    ON DELETE SET NULL
                    """
                ))
                print('MySQL: foreign key fk_productos_cliente creada.')
            else:
                print('MySQL: foreign key fk_productos_cliente ya existe.')

            db.session.commit()
            return

        if dialect == 'sqlite':
            cols_prod = [row[1] for row in db.session.execute(text("PRAGMA table_info(productos)")).fetchall()]
            if 'id_cliente' not in cols_prod:
                db.session.execute(text("ALTER TABLE productos ADD COLUMN id_cliente INTEGER"))
                print('SQLite: columna productos.id_cliente agregada.')
            else:
                print('SQLite: columna productos.id_cliente ya existe.')

            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_productos_id_cliente ON productos(id_cliente)"
            ))
            print('SQLite: índice ix_productos_id_cliente verificado.')
            db.session.commit()
            return

        raise RuntimeError(f'Dialecto no soportado para esta migración: {dialect}')


if __name__ == '__main__':
    run_migration()
