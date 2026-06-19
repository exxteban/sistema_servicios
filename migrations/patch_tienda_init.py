"""
Script de parche seguro para app/__init__.py:
Agrega el import + registro + csrf.exempt del blueprint tienda_api_bp.
Y agrega la migración automática de campos de tienda en productos.

Ejecutar UNA SOLA VEZ desde sistema_silvio_cel/
"""
import re

INIT_PATH = 'app/__init__.py'

with open(INIT_PATH, 'r', encoding='utf-8') as f:
    contenido = f.read()

# ── 1. Import del blueprint ──
OLD_IMPORT = "    from app.routes.agenda import agenda_bp\n"
NEW_IMPORT = (
    "    from app.routes.agenda import agenda_bp\n"
    "    from app.routes.tienda_api import tienda_api_bp\n"
)
if 'tienda_api_bp' not in contenido:
    contenido = contenido.replace(OLD_IMPORT, NEW_IMPORT, 1)
    print("✓ Import tienda_api_bp agregado")
else:
    print("⊘ Import tienda_api_bp ya existe, saltando")

# ── 2. Registro del blueprint ──
OLD_REGISTER = "    app.register_blueprint(agenda_bp, url_prefix='/agenda')\n    if app.config.get('CRM_ENABLED', True):"
NEW_REGISTER = (
    "    app.register_blueprint(agenda_bp, url_prefix='/agenda')\n"
    "    app.register_blueprint(tienda_api_bp, url_prefix='/api/tienda')  # Tienda Online API\n"
    "    if app.config.get('CRM_ENABLED', True):"
)
if "tienda_api_bp, url_prefix='/api/tienda'" not in contenido:
    contenido = contenido.replace(OLD_REGISTER, NEW_REGISTER, 1)
    print("✓ registro tienda_api_bp agregado")
else:
    print("⊘ Registro tienda_api_bp ya existe, saltando")

# ── 3. csrf.exempt ──
OLD_CSRF = "    csrf.exempt(whatsapp_bp)\n    \n    # Crear tablas"
NEW_CSRF = (
    "    csrf.exempt(whatsapp_bp)\n"
    "    csrf.exempt(tienda_api_bp)  # SPA externo no envía token CSRF\n"
    "    \n"
    "    # Crear tablas"
)
if 'csrf.exempt(tienda_api_bp)' not in contenido:
    contenido = contenido.replace(OLD_CSRF, NEW_CSRF, 1)
    print("✓ csrf.exempt(tienda_api_bp) agregado")
else:
    print("⊘ csrf.exempt(tienda_api_bp) ya existe, saltando")

# ── 4. Migración de campos de tienda ──
# Buscar el último db.session.commit() dentro del bloque de migración de agenda
# (antes del except final) e insertar después.
MARKER_IN = "                    db.session.commit()\n        except Exception:\n            db.session.rollback()"
TIENDA_MIGRATION = '''
                # ── Tienda Online: nuevos campos en productos ──
                _tienda_cols = [
                    ('publicado_tienda', 'TINYINT(1) NOT NULL DEFAULT 0', 'BOOLEAN NOT NULL DEFAULT 0'),
                    ('descripcion_tienda', 'TEXT NULL', 'TEXT'),
                    ('orden_tienda', 'INT NOT NULL DEFAULT 0', 'INTEGER NOT NULL DEFAULT 0'),
                ]
                if dialect == 'mysql':
                    for _col, _mysql_def, _ in _tienda_cols:
                        _ex = db.session.execute(
                            text(
                                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                                "WHERE TABLE_SCHEMA = DATABASE() "
                                "AND TABLE_NAME = 'productos' "
                                f"AND COLUMN_NAME = '{_col}'"
                            )
                        ).scalar()
                        if not _ex:
                            db.session.execute(
                                text(f"ALTER TABLE productos ADD COLUMN {_col} {_mysql_def}")
                            )
                            db.session.commit()
                elif dialect == 'sqlite':
                    _prod_cols = [
                        r[1] for r in
                        db.session.execute(text("PRAGMA table_info(productos)")).fetchall()
                    ]
                    for _col, _, _sq_def in _tienda_cols:
                        if _col not in _prod_cols:
                            db.session.execute(
                                text(f"ALTER TABLE productos ADD COLUMN {_col} {_sq_def}")
                            )
                            db.session.commit()
'''

MARKER_OUT = TIENDA_MIGRATION + "        except Exception:\n            db.session.rollback()"

if 'Tienda Online: nuevos campos en productos' not in contenido:
    contenido = contenido.replace(MARKER_IN, MARKER_OUT, 1)
    print("✓ Migración tienda en productos agregada")
else:
    print("⊘ Migración tienda ya existe, saltando")

with open(INIT_PATH, 'w', encoding='utf-8') as f:
    f.write(contenido)

print("\n✅ app/__init__.py actualizado correctamente")
