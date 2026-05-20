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


def _columnas_sqlite(tabla):
    rows = db.session.execute(text(f"PRAGMA table_info({tabla})")).fetchall()
    return {row[1] for row in rows}


def _crear_indice_si_no_existe(nombre, tabla, columna):
    db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} ({columna})"))


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name

        if dialect == 'sqlite':
            columnas = _columnas_sqlite('reparaciones')
            if 'id_usuario_tecnico' not in columnas:
                db.session.execute(text("ALTER TABLE reparaciones ADD COLUMN id_usuario_tecnico INTEGER"))
            if 'fecha_toma_tecnico' not in columnas:
                db.session.execute(text("ALTER TABLE reparaciones ADD COLUMN fecha_toma_tecnico DATETIME"))
            if 'fecha_listo_tecnico' not in columnas:
                db.session.execute(text("ALTER TABLE reparaciones ADD COLUMN fecha_listo_tecnico DATETIME"))

            _crear_indice_si_no_existe('ix_reparaciones_id_usuario_tecnico', 'reparaciones', 'id_usuario_tecnico')
            _crear_indice_si_no_existe('ix_reparaciones_fecha_toma_tecnico', 'reparaciones', 'fecha_toma_tecnico')
        else:
            for sql in [
                "ALTER TABLE reparaciones ADD COLUMN id_usuario_tecnico INTEGER NULL",
                "ALTER TABLE reparaciones ADD COLUMN fecha_toma_tecnico TIMESTAMP NULL",
                "ALTER TABLE reparaciones ADD COLUMN fecha_listo_tecnico TIMESTAMP NULL",
            ]:
                try:
                    db.session.execute(text(sql))
                except Exception as exc:
                    print(f"Columna existente o error controlado: {exc}")

            for sql in [
                "CREATE INDEX IF NOT EXISTS ix_reparaciones_id_usuario_tecnico ON reparaciones (id_usuario_tecnico)",
                "CREATE INDEX IF NOT EXISTS ix_reparaciones_fecha_toma_tecnico ON reparaciones (fecha_toma_tecnico)",
            ]:
                try:
                    db.session.execute(text(sql))
                except Exception as exc:
                    print(f"Índice existente o error controlado: {exc}")

        db.session.commit()
        print("Migración de reparaciones técnicas completada.")


if __name__ == "__main__":
    run_migration()
