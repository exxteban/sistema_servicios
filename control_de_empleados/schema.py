from sqlalchemy import text

from app import db


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


def _mysql_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            """
        ),
        {'table_name': table_name},
    ).scalar())


def _sqlite_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(
        text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:table_name"
        ),
        {'table_name': table_name},
    ).scalar())


def ensure_control_empleados_schema() -> None:
    dialect = db.engine.dialect.name
    cambios = False

    if dialect == 'sqlite':
        columnas = [
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(control_empleados)")).fetchall()
        ]
        if 'salario_incluye_ips' not in columnas:
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados "
                    "ADD COLUMN salario_incluye_ips BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            cambios = True
        if 'dias_vacaciones_anuales' not in columnas:
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados "
                    "ADD COLUMN dias_vacaciones_anuales INTEGER NOT NULL DEFAULT 12"
                )
            )
            cambios = True
        if 'fecha_egreso' not in columnas:
            db.session.execute(text("ALTER TABLE control_empleados ADD COLUMN fecha_egreso DATE"))
            cambios = True
        columnas_movimientos = [
            row[1]
            for row in db.session.execute(
                text("PRAGMA table_info(control_empleados_movimientos)")
            ).fetchall()
        ]
        if 'incide_aguinaldo' not in columnas_movimientos:
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados_movimientos "
                    "ADD COLUMN incide_aguinaldo BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            cambios = True
        if 'cantidad_calculo' not in columnas_movimientos:
            db.session.execute(
                text("ALTER TABLE control_empleados_movimientos ADD COLUMN cantidad_calculo NUMERIC(12, 3)")
            )
            cambios = True
        if 'unidad_calculo' not in columnas_movimientos:
            db.session.execute(
                text("ALTER TABLE control_empleados_movimientos ADD COLUMN unidad_calculo VARCHAR(30)")
            )
            cambios = True
        if 'valor_unitario_calculo' not in columnas_movimientos:
            db.session.execute(
                text("ALTER TABLE control_empleados_movimientos ADD COLUMN valor_unitario_calculo NUMERIC(12, 2)")
            )
            cambios = True
    elif dialect == 'mysql':
        if not _mysql_column_exists('control_empleados', 'salario_incluye_ips'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados "
                    "ADD COLUMN salario_incluye_ips TINYINT(1) NOT NULL DEFAULT 0"
                )
            )
            cambios = True
        if not _mysql_column_exists('control_empleados', 'dias_vacaciones_anuales'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados "
                    "ADD COLUMN dias_vacaciones_anuales INT NOT NULL DEFAULT 12"
                )
            )
            cambios = True
        if not _mysql_column_exists('control_empleados', 'fecha_egreso'):
            db.session.execute(
                text("ALTER TABLE control_empleados ADD COLUMN fecha_egreso DATE NULL")
            )
            cambios = True
        if not _mysql_column_exists('control_empleados_movimientos', 'incide_aguinaldo'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados_movimientos "
                    "ADD COLUMN incide_aguinaldo TINYINT(1) NOT NULL DEFAULT 0"
                )
            )
            cambios = True
        if not _mysql_column_exists('control_empleados_movimientos', 'cantidad_calculo'):
            db.session.execute(
                text("ALTER TABLE control_empleados_movimientos ADD COLUMN cantidad_calculo DECIMAL(12, 3) NULL")
            )
            cambios = True
        if not _mysql_column_exists('control_empleados_movimientos', 'unidad_calculo'):
            db.session.execute(
                text("ALTER TABLE control_empleados_movimientos ADD COLUMN unidad_calculo VARCHAR(30) NULL")
            )
            cambios = True
        if not _mysql_column_exists('control_empleados_movimientos', 'valor_unitario_calculo'):
            db.session.execute(
                text("ALTER TABLE control_empleados_movimientos ADD COLUMN valor_unitario_calculo DECIMAL(12, 2) NULL")
            )
            cambios = True
    elif dialect == 'postgresql':
        # PostgreSQL: usa information_schema igual que MySQL pero con sintaxis propia.
        def _pg_column_exists(table: str, column: str) -> bool:
            return bool(db.session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {'table_name': table, 'column_name': column},
            ).scalar())

        if not _pg_column_exists('control_empleados', 'salario_incluye_ips'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados "
                    "ADD COLUMN salario_incluye_ips BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            cambios = True
        if not _pg_column_exists('control_empleados', 'dias_vacaciones_anuales'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados "
                    "ADD COLUMN dias_vacaciones_anuales INTEGER NOT NULL DEFAULT 12"
                )
            )
            cambios = True
        if not _pg_column_exists('control_empleados', 'fecha_egreso'):
            db.session.execute(
                text("ALTER TABLE control_empleados ADD COLUMN fecha_egreso DATE NULL")
            )
            cambios = True
        if not _pg_column_exists('control_empleados_movimientos', 'incide_aguinaldo'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados_movimientos "
                    "ADD COLUMN incide_aguinaldo BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            cambios = True
        if not _pg_column_exists('control_empleados_movimientos', 'cantidad_calculo'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados_movimientos "
                    "ADD COLUMN cantidad_calculo NUMERIC(12, 3) NULL"
                )
            )
            cambios = True
        if not _pg_column_exists('control_empleados_movimientos', 'unidad_calculo'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados_movimientos "
                    "ADD COLUMN unidad_calculo VARCHAR(30) NULL"
                )
            )
            cambios = True
        if not _pg_column_exists('control_empleados_movimientos', 'valor_unitario_calculo'):
            db.session.execute(
                text(
                    "ALTER TABLE control_empleados_movimientos "
                    "ADD COLUMN valor_unitario_calculo NUMERIC(12, 2) NULL"
                )
            )
            cambios = True
    else:
        raise RuntimeError(f'Dialecto no soportado para control_empleados: {dialect}')

    if cambios:
        db.session.commit()


def ensure_asistencia_schema() -> None:
    """Crea la tabla de asistencia diaria si no existe."""
    dialect = db.engine.dialect.name

    if dialect == 'sqlite':
        if not _sqlite_table_exists('control_empleados_asistencia'):
            db.session.execute(text("""
                CREATE TABLE control_empleados_asistencia (
                    id_asistencia INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER,
                    id_empleado INTEGER NOT NULL REFERENCES control_empleados(id_empleado) ON DELETE CASCADE,
                    periodo VARCHAR(7) NOT NULL,
                    fecha DATE NOT NULL,
                    estado VARCHAR(20) NOT NULL DEFAULT 'presente',
                    observaciones VARCHAR(160),
                    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    fecha_modificacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (id_empleado, fecha)
                )
            """))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ce_asistencia_empleado_periodo "
                "ON control_empleados_asistencia (id_empleado, periodo)"
            ))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ce_asistencia_cliente_id "
                "ON control_empleados_asistencia (cliente_id)"
            ))
            db.session.commit()

    elif dialect == 'mysql':
        if not _mysql_table_exists('control_empleados_asistencia'):
            db.session.execute(text("""
                CREATE TABLE control_empleados_asistencia (
                    id_asistencia INT AUTO_INCREMENT PRIMARY KEY,
                    cliente_id INT NULL,
                    id_empleado INT NOT NULL,
                    periodo VARCHAR(7) NOT NULL,
                    fecha DATE NOT NULL,
                    estado VARCHAR(20) NOT NULL DEFAULT 'presente',
                    observaciones VARCHAR(160) NULL,
                    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    fecha_modificacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_ce_asistencia_empleado_fecha (id_empleado, fecha),
                    KEY ix_ce_asistencia_empleado_periodo (id_empleado, periodo),
                    KEY ix_ce_asistencia_cliente_id (cliente_id),
                    CONSTRAINT fk_ce_asistencia_empleado
                        FOREIGN KEY (id_empleado)
                        REFERENCES control_empleados(id_empleado)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            db.session.commit()

    elif dialect == 'postgresql':
        def _pg_table_exists(table: str) -> bool:
            return bool(db.session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = :table_name"
                ),
                {'table_name': table},
            ).scalar())

        if not _pg_table_exists('control_empleados_asistencia'):
            db.session.execute(text("""
                CREATE TABLE control_empleados_asistencia (
                    id_asistencia SERIAL PRIMARY KEY,
                    cliente_id INTEGER NULL,
                    id_empleado INTEGER NOT NULL
                        REFERENCES control_empleados(id_empleado) ON DELETE CASCADE,
                    periodo VARCHAR(7) NOT NULL,
                    fecha DATE NOT NULL,
                    estado VARCHAR(20) NOT NULL DEFAULT 'presente',
                    observaciones VARCHAR(160) NULL,
                    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
                    fecha_modificacion TIMESTAMP NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_ce_asistencia_empleado_fecha UNIQUE (id_empleado, fecha)
                )
            """))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ce_asistencia_empleado_periodo "
                "ON control_empleados_asistencia (id_empleado, periodo)"
            ))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ce_asistencia_cliente_id "
                "ON control_empleados_asistencia (cliente_id)"
            ))
            db.session.commit()
    else:
        raise RuntimeError(f'Dialecto no soportado para asistencia: {dialect}')
