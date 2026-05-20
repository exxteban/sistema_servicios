from sqlalchemy import text

from app import db


def _sqlite_columns(table_name: str) -> set[str]:
    return {row[1] for row in db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}


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


def ensure_gastos_corrientes_schema() -> None:
    dialect = db.engine.dialect.name
    statements = []
    column_specs = (
        (
            'gastos_corrientes',
            'requiere_caja_por_defecto',
            "ALTER TABLE gastos_corrientes ADD COLUMN requiere_caja_por_defecto BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE gastos_corrientes ADD COLUMN requiere_caja_por_defecto BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            'gastos_corrientes',
            'alerta_activa',
            "ALTER TABLE gastos_corrientes ADD COLUMN alerta_activa BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE gastos_corrientes ADD COLUMN alerta_activa BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            'gastos_corrientes',
            'dias_anticipacion_alerta',
            "ALTER TABLE gastos_corrientes ADD COLUMN dias_anticipacion_alerta INTEGER NOT NULL DEFAULT 3",
            "ALTER TABLE gastos_corrientes ADD COLUMN dias_anticipacion_alerta INTEGER NOT NULL DEFAULT 3",
        ),
        (
            'pagos_gastos_corrientes',
            'id_sesion_caja',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_sesion_caja INTEGER",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_sesion_caja INTEGER NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'id_movimiento_caja',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_movimiento_caja INTEGER",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_movimiento_caja INTEGER NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'id_movimiento_reversa',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_movimiento_reversa INTEGER",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_movimiento_reversa INTEGER NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'id_usuario',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_usuario INTEGER",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_usuario INTEGER NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'id_usuario_anulacion',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_usuario_anulacion INTEGER",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN id_usuario_anulacion INTEGER NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'numero_comprobante',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN numero_comprobante VARCHAR(120)",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN numero_comprobante VARCHAR(120) NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'comprobante_adjunto_path',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN comprobante_adjunto_path VARCHAR(255)",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN comprobante_adjunto_path VARCHAR(255) NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'comprobante_adjunto_nombre',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN comprobante_adjunto_nombre VARCHAR(255)",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN comprobante_adjunto_nombre VARCHAR(255) NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'comprobante_adjunto_mime',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN comprobante_adjunto_mime VARCHAR(120)",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN comprobante_adjunto_mime VARCHAR(120) NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'motivo_anulacion',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN motivo_anulacion TEXT",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN motivo_anulacion TEXT NULL",
        ),
        (
            'pagos_gastos_corrientes',
            'fecha_anulacion',
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN fecha_anulacion DATE",
            "ALTER TABLE pagos_gastos_corrientes ADD COLUMN fecha_anulacion DATE NULL",
        ),
    )

    if dialect == 'sqlite':
        for table_name, column_name, sqlite_statement, _mysql_statement in column_specs:
            existing_columns = _sqlite_columns(table_name)
            if column_name not in existing_columns:
                statements.append(sqlite_statement)
        statements = [
            *statements,
            "CREATE INDEX IF NOT EXISTS ix_gastos_corrientes_cliente_activo ON gastos_corrientes(cliente_id, activo)",
            "CREATE INDEX IF NOT EXISTS ix_pago_gasto_periodo_gasto_estado ON pagos_gastos_corrientes(id_gasto_corriente, periodo_anio, periodo_mes, estado)",
        ]
    elif dialect == 'mysql':
        for table_name, column_name, _sqlite_statement, mysql_statement in column_specs:
            if not _mysql_column_exists(table_name, column_name):
                statements.append(mysql_statement)
        specs = [
            (
                'gastos_corrientes',
                'ix_gastos_corrientes_cliente_activo',
                "CREATE INDEX ix_gastos_corrientes_cliente_activo ON gastos_corrientes(cliente_id, activo)",
            ),
            (
                'pagos_gastos_corrientes',
                'ix_pago_gasto_periodo_gasto_estado',
                "CREATE INDEX ix_pago_gasto_periodo_gasto_estado ON pagos_gastos_corrientes(id_gasto_corriente, periodo_anio, periodo_mes, estado)",
            ),
        ]
        for table_name, index_name, ddl in specs:
            if not _mysql_index_exists(table_name, index_name):
                statements.append(ddl)

    if statements:
        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()
