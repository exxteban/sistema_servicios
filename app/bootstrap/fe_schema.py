"""Esquema de facturacion electronica (portado del sistema padre).

Vive aparte de `schema.py` por tamano. Las instalaciones de servicios que ya
corrieron el porte viejo del modulo tienen las tablas de FE creadas sin las
columnas nuevas, y `create_all` no agrega columnas a tablas existentes: todo lo
de aca es aditivo e idempotente.
"""
from sqlalchemy import inspect, text


_FE_COLUMNAS = {
    'facturacion_electronica_config': (
        ('proveedor', "VARCHAR(20) NOT NULL DEFAULT 'propio'"),
        ('api_url', 'VARCHAR(500)'),
        ('api_client_id', 'VARCHAR(128)'),
        ('api_credenciales', 'TEXT'),
    ),
    'facturacion_electronica_documentos': (
        ('xml_qr', 'TEXT'),
        ('qr_url', 'TEXT'),
        ('respuesta_raw', 'TEXT'),
        ('api_documento_id', 'VARCHAR(36)'),
        ('api_lote_id', 'VARCHAR(36)'),
        ('api_idempotency_key', 'VARCHAR(120)'),
        ('id_documento_asociado', 'INTEGER'),
        ('id_devolucion', 'INTEGER'),
        ('nc_motivo', 'INTEGER'),
        ('nc_motivo_desc', 'VARCHAR(60)'),
        ('motivo_cancelacion', 'TEXT'),
        ('xml_cancelacion', 'TEXT'),
        ('reintentar_despues', 'DATETIME'),
        ('fecha_cancelado', 'DATETIME'),
    ),
    'facturacion_electronica_secuencia': (
        ('tipo_documento', 'INTEGER NOT NULL DEFAULT 1'),
    ),
}

FE_DOCUMENTOS_TABLA = 'facturacion_electronica_documentos'
FE_IDX_ID_VENTA = 'ix_facturacion_electronica_documentos_id_venta'
FE_IDX_ID_VENTA_TMP = 'ix_fe_documentos_id_venta_tmp'


def _ensure_fe_columnas(db):
    inspector = inspect(db.engine)
    tablas = set(inspector.get_table_names())
    for tabla, pendientes in _FE_COLUMNAS.items():
        if tabla not in tablas:
            continue
        existentes = {columna['name'] for columna in inspector.get_columns(tabla)}
        for columna, tipo in pendientes:
            if columna in existentes:
                continue
            with db.engine.begin() as conexion:
                conexion.execute(text(f'ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}'))
            existentes.add(columna)


def _ensure_fe_secuencia_por_tipo(db):
    """UNIQUE(establecimiento, punto) -> UNIQUE(tipo_documento, establecimiento, punto).

    Factura y nota de credito llevan cada una su correlativo dentro del
    timbrado. En SQLite rehacer la restriccion es rehacer la tabla.
    """
    tabla = 'facturacion_electronica_secuencia'
    inspector = inspect(db.engine)
    if tabla not in set(inspector.get_table_names()):
        return
    columnas = {columna['name'] for columna in inspector.get_columns(tabla)}
    if 'tipo_documento' not in columnas:
        return
    unicas = inspector.get_unique_constraints(tabla)
    if any('tipo_documento' in (uc.get('column_names') or []) for uc in unicas):
        return

    dialecto = db.engine.dialect.name
    if dialecto == 'sqlite':
        with db.engine.begin() as conexion:
            conexion.execute(text(f'ALTER TABLE {tabla} RENAME TO {tabla}_old'))
            conexion.execute(text(f'''
                CREATE TABLE {tabla} (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tipo_documento INTEGER NOT NULL DEFAULT 1,
                    establecimiento VARCHAR(3) NOT NULL,
                    punto VARCHAR(3) NOT NULL,
                    ultimo_numero INTEGER NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT uq_fe_secuencia_tipo_estab_punto
                        UNIQUE (tipo_documento, establecimiento, punto)
                )
            '''))
            conexion.execute(text(f'''
                INSERT INTO {tabla}
                    (id, tipo_documento, establecimiento, punto, ultimo_numero, updated_at)
                SELECT id, COALESCE(tipo_documento, 1), establecimiento, punto,
                       ultimo_numero, updated_at
                FROM {tabla}_old
            '''))
            conexion.execute(text(f'DROP TABLE {tabla}_old'))
        return

    if dialecto == 'mysql':
        with db.engine.begin() as conexion:
            for vieja in ('uq_fe_secuencia_estab_punto', 'establecimiento'):
                try:
                    conexion.execute(text(f'ALTER TABLE {tabla} DROP INDEX {vieja}'))
                except Exception:
                    continue
                break
            conexion.execute(text(
                f'ALTER TABLE {tabla} ADD CONSTRAINT uq_fe_secuencia_tipo_estab_punto '
                'UNIQUE (tipo_documento, establecimiento, punto)'
            ))


def _ensure_fe_respuesta_codigo_ancho(db):
    """En MySQL estricto el estado de la API ('CANCELLATION_PENDING') no entra en VARCHAR(10)."""
    if db.engine.dialect.name != 'mysql':
        return
    inspector = inspect(db.engine)
    if FE_DOCUMENTOS_TABLA not in set(inspector.get_table_names()):
        return
    for columna in inspector.get_columns(FE_DOCUMENTOS_TABLA):
        if columna['name'] != 'respuesta_codigo':
            continue
        if (getattr(columna['type'], 'length', 0) or 0) >= 40:
            return
        with db.engine.begin() as conexion:
            conexion.execute(text(
                f'ALTER TABLE {FE_DOCUMENTOS_TABLA} MODIFY COLUMN respuesta_codigo VARCHAR(40) NULL'
            ))
        return


def _sentencias_id_venta_no_unico(dialecto):
    """En InnoDB la FK de id_venta exige un indice que la sostenga: el temporal
    toma la posta antes del DROP."""
    tabla, indice, temporal = FE_DOCUMENTOS_TABLA, FE_IDX_ID_VENTA, FE_IDX_ID_VENTA_TMP
    if dialecto == 'mysql':
        return (
            f'CREATE INDEX {temporal} ON {tabla} (id_venta)',
            f'DROP INDEX {indice} ON {tabla}',
            f'CREATE INDEX {indice} ON {tabla} (id_venta)',
            f'DROP INDEX {temporal} ON {tabla}',
        )
    return (
        f'DROP INDEX IF EXISTS {indice}',
        f'CREATE INDEX {indice} ON {tabla} (id_venta)',
    )


def _ensure_fe_documentos_id_venta_no_unico(db, logger=None):
    """`id_venta` nacio UNIQUE; con notas de credito y re-facturacion una venta
    tiene varios DE. Nunca propaga: corre en el arranque."""
    try:
        inspector = inspect(db.engine)
        if FE_DOCUMENTOS_TABLA not in set(inspector.get_table_names()):
            return
        actual = next(
            (d for d in inspector.get_indexes(FE_DOCUMENTOS_TABLA) if d.get('name') == FE_IDX_ID_VENTA),
            None,
        )
        if actual is None or not actual.get('unique'):
            return
        for sentencia in _sentencias_id_venta_no_unico(db.engine.dialect.name):
            with db.engine.begin() as conexion:
                conexion.execute(text(sentencia))
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        if logger is not None:
            logger.exception(
                'No se pudo convertir %s en indice comun: la nota de credito y la '
                're-facturacion van a fallar con "Duplicate entry" hasta arreglarlo',
                FE_IDX_ID_VENTA,
            )


def ensure_facturacion_electronica_schema(db, logger=None):
    _ensure_fe_columnas(db)
    _ensure_fe_secuencia_por_tipo(db)
    _ensure_fe_respuesta_codigo_ancho(db)
    _ensure_fe_documentos_id_venta_no_unico(db, logger)
