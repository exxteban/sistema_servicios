"""Indices unicos condicionales para caja y cola de cobro."""
from sqlalchemy import text


def ensure_sqlite_caja_unique_indexes(db):
    if _sqlite_table_exists(db, 'cola_cobro'):
        _execute_and_commit(db, ("CREATE INDEX IF NOT EXISTS ix_cola_cobro_estado_fecha_envio ON cola_cobro(estado, fecha_envio)",))
        if _duplicados_cola_activa(db) == 0:
            _execute_and_commit(db, (
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_cola_cobro_origen_activo
                ON cola_cobro(tipo_origen, id_origen)
                WHERE estado IN ('pendiente', 'en_proceso')
                """,
            ))
    if _sqlite_table_exists(db, 'sesiones_caja') and _duplicados_sesiones_abiertas(db) == 0:
        _execute_and_commit(db, (
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sesiones_caja_caja_abierta
            ON sesiones_caja(id_caja)
            WHERE estado = 'abierta'
            """,
        ))


def ensure_mysql_caja_unique_indexes(db, table_exists, column_exists, index_exists):
    if table_exists(db, 'cola_cobro'):
        if not column_exists(db, 'cola_cobro', 'activo_para_unico'):
            _execute_and_commit(db, (
                """
                ALTER TABLE cola_cobro
                ADD COLUMN activo_para_unico TINYINT
                GENERATED ALWAYS AS (
                    CASE WHEN estado IN ('pendiente', 'en_proceso') THEN 1 ELSE NULL END
                ) STORED
                """,
            ))
        if not index_exists(db, 'cola_cobro', 'uq_cola_cobro_origen_activo') and _duplicados_cola_activa(db) == 0:
            _execute_and_commit(db, (
                """
                CREATE UNIQUE INDEX uq_cola_cobro_origen_activo
                ON cola_cobro(tipo_origen, id_origen, activo_para_unico)
                """,
            ))
    if table_exists(db, 'sesiones_caja'):
        if not column_exists(db, 'sesiones_caja', 'activo_para_unico'):
            _execute_and_commit(db, (
                """
                ALTER TABLE sesiones_caja
                ADD COLUMN activo_para_unico TINYINT
                GENERATED ALWAYS AS (
                    CASE WHEN estado = 'abierta' THEN 1 ELSE NULL END
                ) STORED
                """,
            ))
        if not index_exists(db, 'sesiones_caja', 'uq_sesiones_caja_caja_abierta') and _duplicados_sesiones_abiertas(db) == 0:
            _execute_and_commit(db, (
                """
                CREATE UNIQUE INDEX uq_sesiones_caja_caja_abierta
                ON sesiones_caja(id_caja, activo_para_unico)
                """,
            ))


def _sqlite_table_exists(db, table_name: str) -> bool:
    return db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
        {'table_name': table_name},
    ).scalar() is not None


def _duplicados_cola_activa(db) -> int:
    return int(db.session.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT tipo_origen, id_origen, COUNT(*) AS total
            FROM cola_cobro
            WHERE estado IN ('pendiente', 'en_proceso')
            GROUP BY tipo_origen, id_origen
            HAVING COUNT(*) > 1
        ) dup
    """)).scalar() or 0)


def _duplicados_sesiones_abiertas(db) -> int:
    return int(db.session.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT id_caja, COUNT(*) AS total
            FROM sesiones_caja
            WHERE estado = 'abierta'
            GROUP BY id_caja
            HAVING COUNT(*) > 1
        ) dup
    """)).scalar() or 0)


def _execute_and_commit(db, statements):
    for statement in statements:
        db.session.execute(text(statement))
    db.session.commit()
