from sqlalchemy import inspect, text

from app import db


def ensure_cobranzas_schema() -> None:
    inspector = inspect(db.engine)
    columnas = {col['name'] for col in inspector.get_columns('pagos_cuentas_cobrar')}
    columnas_planes = {col['name'] for col in inspector.get_columns('planes_credito_venta')}
    columnas_cuotas = {col['name'] for col in inspector.get_columns('cuotas_credito_venta')}
    dialect = db.engine.dialect.name

    statements = []

    if 'estado' not in columnas:
        if dialect == 'mysql':
            statements.append("ALTER TABLE pagos_cuentas_cobrar ADD COLUMN estado VARCHAR(20) NOT NULL DEFAULT 'activo'")
        else:
            statements.append("ALTER TABLE pagos_cuentas_cobrar ADD COLUMN estado VARCHAR(20) NOT NULL DEFAULT 'activo'")
    if 'fecha_anulacion' not in columnas:
        statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN fecha_anulacion DATETIME')
    if 'id_usuario_anulacion' not in columnas:
        if dialect == 'mysql':
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN id_usuario_anulacion INTEGER')
        else:
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN id_usuario_anulacion INTEGER')
    if 'motivo_anulacion' not in columnas:
        statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN motivo_anulacion TEXT')
    if 'id_movimiento_reversa' not in columnas:
        if dialect == 'mysql':
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN id_movimiento_reversa INTEGER')
        else:
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN id_movimiento_reversa INTEGER')
    if 'cliente_nombre_snapshot' not in columnas:
        if dialect == 'mysql':
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN cliente_nombre_snapshot VARCHAR(150)')
        else:
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN cliente_nombre_snapshot VARCHAR(150)')
    if 'id_cuota_credito_principal' not in columnas:
        if dialect == 'mysql':
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN id_cuota_credito_principal INTEGER')
        else:
            statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN id_cuota_credito_principal INTEGER')
    if 'numero_cuota_principal' not in columnas:
        statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN numero_cuota_principal INTEGER')
    if 'detalle_aplicacion_json' not in columnas:
        statements.append('ALTER TABLE pagos_cuentas_cobrar ADD COLUMN detalle_aplicacion_json TEXT')

    if 'tasa_periodica_pct' not in columnas_planes:
        if dialect == 'mysql':
            statements.append("ALTER TABLE planes_credito_venta ADD COLUMN tasa_periodica_pct DECIMAL(8, 4) NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE planes_credito_venta ADD COLUMN tasa_periodica_pct NUMERIC(8, 4) NOT NULL DEFAULT 0")
    if 'sistema_amortizacion' not in columnas_planes:
        statements.append("ALTER TABLE planes_credito_venta ADD COLUMN sistema_amortizacion VARCHAR(20) NOT NULL DEFAULT 'frances'")
    if 'monto_total_interes' not in columnas_planes:
        if dialect == 'mysql':
            statements.append("ALTER TABLE planes_credito_venta ADD COLUMN monto_total_interes DECIMAL(15, 2) NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE planes_credito_venta ADD COLUMN monto_total_interes NUMERIC(15, 2) NOT NULL DEFAULT 0")
    if 'monto_total_con_interes' not in columnas_planes:
        if dialect == 'mysql':
            statements.append("ALTER TABLE planes_credito_venta ADD COLUMN monto_total_con_interes DECIMAL(15, 2) NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE planes_credito_venta ADD COLUMN monto_total_con_interes NUMERIC(15, 2) NOT NULL DEFAULT 0")

    if 'capital_programado' not in columnas_cuotas:
        if dialect == 'mysql':
            statements.append("ALTER TABLE cuotas_credito_venta ADD COLUMN capital_programado DECIMAL(15, 2) NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE cuotas_credito_venta ADD COLUMN capital_programado NUMERIC(15, 2) NOT NULL DEFAULT 0")
    if 'interes_programado' not in columnas_cuotas:
        if dialect == 'mysql':
            statements.append("ALTER TABLE cuotas_credito_venta ADD COLUMN interes_programado DECIMAL(15, 2) NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE cuotas_credito_venta ADD COLUMN interes_programado NUMERIC(15, 2) NOT NULL DEFAULT 0")
    if 'saldo_capital' not in columnas_cuotas:
        if dialect == 'mysql':
            statements.append("ALTER TABLE cuotas_credito_venta ADD COLUMN saldo_capital DECIMAL(15, 2) NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE cuotas_credito_venta ADD COLUMN saldo_capital NUMERIC(15, 2) NOT NULL DEFAULT 0")

    for statement in statements:
        db.session.execute(text(statement))

    if 'estado' not in columnas:
        try:
            db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_pagos_cuentas_cobrar_estado ON pagos_cuentas_cobrar(estado)'))
        except Exception:
            pass

    db.session.flush()
