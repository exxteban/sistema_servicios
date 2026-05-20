from sqlalchemy import text

from app import db


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


def _pg_index_exists(index_name: str) -> bool:
    return bool(db.session.execute(
        text(
            "SELECT COUNT(*) FROM pg_indexes WHERE indexname = :index_name"
        ),
        {'index_name': index_name},
    ).scalar())


def _pg_constraint_exists(constraint_name: str) -> bool:
    return bool(db.session.execute(
        text(
            "SELECT COUNT(*) FROM pg_constraint WHERE conname = :constraint_name"
        ),
        {'constraint_name': constraint_name},
    ).scalar())


def ensure_flujo_caja_schema() -> None:
    dialect = db.engine.dialect.name
    statements = []

    if dialect == 'sqlite':
        statements = [
            "CREATE INDEX IF NOT EXISTS ix_flujo_semana_cliente_fecha ON flujo_caja_semanas(cliente_id, fecha_inicio)",
            "CREATE INDEX IF NOT EXISTS ix_flujo_mov_cliente_semana_estado ON flujo_caja_movimientos(cliente_id, id_flujo_semana, estado)",
            "CREATE INDEX IF NOT EXISTS ix_flujo_plantilla_cliente_activa ON flujo_caja_plantillas(cliente_id, activa)",
            # La UNIQUE constraint la crea SQLAlchemy via db.create_all(); aqui solo los indices extra.
        ]
    elif dialect == 'mysql':
        specs = [
            (
                'flujo_caja_semanas',
                'ix_flujo_semana_cliente_fecha',
                "CREATE INDEX ix_flujo_semana_cliente_fecha ON flujo_caja_semanas(cliente_id, fecha_inicio)",
            ),
            (
                'flujo_caja_movimientos',
                'ix_flujo_mov_cliente_semana_estado',
                "CREATE INDEX ix_flujo_mov_cliente_semana_estado ON flujo_caja_movimientos(cliente_id, id_flujo_semana, estado)",
            ),
            (
                'flujo_caja_plantillas',
                'ix_flujo_plantilla_cliente_activa',
                "CREATE INDEX ix_flujo_plantilla_cliente_activa ON flujo_caja_plantillas(cliente_id, activa)",
            ),
        ]
        for table_name, index_name, ddl in specs:
            if not _mysql_index_exists(table_name, index_name):
                statements.append(ddl)
    elif dialect == 'postgresql':
        # FIX #7: CREATE INDEX CONCURRENTLY no puede ejecutarse dentro de una
        # transacción activa en PostgreSQL. Usamos CREATE INDEX sin CONCURRENTLY
        # para la creación inicial (que ocurre una sola vez en el arranque).
        # IF NOT EXISTS evita errores si el índice ya existe.
        pg_indexes = [
            (
                'ix_flujo_semana_cliente_fecha',
                "CREATE INDEX IF NOT EXISTS ix_flujo_semana_cliente_fecha ON flujo_caja_semanas(cliente_id, fecha_inicio)",
            ),
            (
                'ix_flujo_mov_cliente_semana_estado',
                "CREATE INDEX IF NOT EXISTS ix_flujo_mov_cliente_semana_estado ON flujo_caja_movimientos(cliente_id, id_flujo_semana, estado)",
            ),
            (
                'ix_flujo_plantilla_cliente_activa',
                "CREATE INDEX IF NOT EXISTS ix_flujo_plantilla_cliente_activa ON flujo_caja_plantillas(cliente_id, activa)",
            ),
        ]
        for index_name, ddl in pg_indexes:
            if not _pg_index_exists(index_name):
                statements.append(ddl)

    if statements:
        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()
