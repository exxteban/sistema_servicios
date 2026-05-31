"""Migraciones ligeras del modulo Gastronomia."""
import re
import unicodedata

from sqlalchemy import text

from app import db


ORDER_COLUMN_MIGRATIONS = (
    ('codigo_publico', 'VARCHAR(32)'),
    ('referencia_entrega', 'VARCHAR(80)'),
    ('nombre_cliente', 'VARCHAR(120)'),
    ('celular_cliente', 'VARCHAR(40)'),
    ('direccion_entrega', 'VARCHAR(240)'),
    ('tiempo_estimado_minutos', 'INTEGER'),
    ('repartidor_id', 'INTEGER'),
    ('costo_envio', 'NUMERIC(15, 2) NOT NULL DEFAULT 0'),
    ('fecha_inicio_preparacion', 'DATETIME'),
    ('fecha_listo', 'DATETIME'),
    ('fecha_asignacion_delivery', 'DATETIME'),
    ('fecha_entrega', 'DATETIME'),
)

PAYMENT_COLUMN_MIGRATIONS = (
    ('id_sesion_caja', 'INTEGER'),
    ('id_metodo_pago', 'INTEGER'),
    ('id_venta', 'INTEGER'),
    ('id_movimiento_caja', 'INTEGER'),
)

ORDER_ITEM_COLUMN_MIGRATIONS = (
    ('canal_precio', 'VARCHAR(30)'),
)

CONFIG_COLUMN_MIGRATIONS = (
    ('menu_tv_publico_activo', 'BOOLEAN NOT NULL DEFAULT 1'),
    ('menu_tv_slug', 'VARCHAR(100)'),
    ('menu_tv_titulo', 'VARCHAR(160)'),
    ('menu_tv_subtitulo', 'VARCHAR(240)'),
    ('menu_tv_tema', "VARCHAR(40) NOT NULL DEFAULT 'clasico'"),
    ('menu_tv_modo_rotacion', "VARCHAR(20) NOT NULL DEFAULT 'auto'"),
    ('menu_tv_mostrar_precios', 'BOOLEAN NOT NULL DEFAULT 1'),
    ('menu_tv_mostrar_agotados', 'BOOLEAN NOT NULL DEFAULT 0'),
    ('menu_tv_intervalo_refresco_seg', 'INTEGER NOT NULL DEFAULT 60'),
)

PRODUCT_COLUMN_MIGRATIONS = (
    ('visible_en_tv', 'BOOLEAN NOT NULL DEFAULT 1'),
    ('publicado_tienda', 'BOOLEAN NOT NULL DEFAULT 1'),
    ('control_stock_venta', 'BOOLEAN NOT NULL DEFAULT 0'),
    ('stock_disponible', 'INTEGER'),
)

OPTION_COLUMN_MIGRATIONS = (
    ('imagen_url', 'VARCHAR(500)'),
)

CENTRAL_PRODUCT_COLUMN_MIGRATIONS = (
    ('unidad_stock', "VARCHAR(20) NOT NULL DEFAULT 'unidad'"),
)


def ensure_gastronomia_schema():
    from gastronomia.channel_models import GastronomiaProductoPrecioCanal
    from gastronomia.models import GastronomiaProducto
    from gastronomia.services.channel_price_service import asegurar_precios_productos

    GastronomiaProductoPrecioCanal.__table__.create(bind=db.engine, checkfirst=True)
    dialect = db.engine.dialect.name
    if dialect == 'sqlite':
        _ensure_sqlite_columns()
    elif dialect == 'mysql':
        _ensure_mysql_columns()
    asegurar_precios_productos(GastronomiaProducto.query.filter_by(activo=True).all())


def _ensure_sqlite_columns():
    _ensure_sqlite_central_product_columns()
    _ensure_sqlite_config_columns()
    _ensure_sqlite_product_columns()
    _ensure_sqlite_option_columns()
    if not _sqlite_table_exists('gastronomia_pedidos'):
        db.session.commit()
        return
    order_columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(gastronomia_pedidos)')).fetchall()
    }
    for column, column_type in ORDER_COLUMN_MIGRATIONS:
        if column not in order_columns:
            db.session.execute(text(f'ALTER TABLE gastronomia_pedidos ADD COLUMN {column} {column_type}'))
    if _sqlite_table_exists('gastronomia_pedido_pagos'):
        payment_columns = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(gastronomia_pedido_pagos)')).fetchall()
        }
        for column, column_type in PAYMENT_COLUMN_MIGRATIONS:
            if column not in payment_columns:
                db.session.execute(text(f'ALTER TABLE gastronomia_pedido_pagos ADD COLUMN {column} {column_type}'))
    if _sqlite_table_exists('gastronomia_pedido_items'):
        item_columns = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(gastronomia_pedido_items)')).fetchall()
        }
        for column, column_type in ORDER_ITEM_COLUMN_MIGRATIONS:
            if column not in item_columns:
                db.session.execute(text(f'ALTER TABLE gastronomia_pedido_items ADD COLUMN {column} {column_type}'))
    db.session.commit()


def _ensure_mysql_columns():
    _ensure_mysql_central_product_columns()
    _ensure_mysql_config_columns()
    _ensure_mysql_product_columns()
    _ensure_mysql_option_columns()
    if not _mysql_table_exists('gastronomia_pedidos'):
        db.session.commit()
        return
    for column, column_type in ORDER_COLUMN_MIGRATIONS:
        if not _mysql_column_exists('gastronomia_pedidos', column):
            add_type = column_type if _declares_nullability_or_default(column_type) else f'{column_type} NULL'
            db.session.execute(text(f'ALTER TABLE gastronomia_pedidos ADD COLUMN {column} {add_type}'))
    if _mysql_table_exists('gastronomia_pedido_pagos'):
        for column, column_type in PAYMENT_COLUMN_MIGRATIONS:
            if not _mysql_column_exists('gastronomia_pedido_pagos', column):
                db.session.execute(text(f'ALTER TABLE gastronomia_pedido_pagos ADD COLUMN {column} {column_type} NULL'))
    if _mysql_table_exists('gastronomia_pedido_items'):
        for column, column_type in ORDER_ITEM_COLUMN_MIGRATIONS:
            if not _mysql_column_exists('gastronomia_pedido_items', column):
                db.session.execute(text(f'ALTER TABLE gastronomia_pedido_items ADD COLUMN {column} {column_type} NULL'))
    db.session.commit()


def _ensure_sqlite_config_columns():
    if not _sqlite_table_exists('gastronomia_cliente_config'):
        return
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(gastronomia_cliente_config)')).fetchall()
    }
    for column, column_type in CONFIG_COLUMN_MIGRATIONS:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE gastronomia_cliente_config ADD COLUMN {column} {column_type}'))
    _backfill_menu_tv_slugs()
    db.session.execute(text(
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_gastronomia_cliente_config_menu_tv_slug '
        'ON gastronomia_cliente_config(menu_tv_slug)'
    ))


def _ensure_sqlite_product_columns():
    if not _sqlite_table_exists('gastronomia_productos'):
        return
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(gastronomia_productos)')).fetchall()
    }
    for column, column_type in PRODUCT_COLUMN_MIGRATIONS:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE gastronomia_productos ADD COLUMN {column} {column_type}'))


def _ensure_sqlite_option_columns():
    if not _sqlite_table_exists('gastronomia_opciones_producto'):
        return
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(gastronomia_opciones_producto)')).fetchall()
    }
    for column, column_type in OPTION_COLUMN_MIGRATIONS:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE gastronomia_opciones_producto ADD COLUMN {column} {column_type}'))


def _ensure_sqlite_central_product_columns():
    if not _sqlite_table_exists('productos'):
        return
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(productos)')).fetchall()
    }
    for column, column_type in CENTRAL_PRODUCT_COLUMN_MIGRATIONS:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE productos ADD COLUMN {column} {column_type}'))


def _ensure_mysql_config_columns():
    if not _mysql_table_exists('gastronomia_cliente_config'):
        return
    for column, column_type in CONFIG_COLUMN_MIGRATIONS:
        if not _mysql_column_exists('gastronomia_cliente_config', column):
            db.session.execute(text(f'ALTER TABLE gastronomia_cliente_config ADD COLUMN {column} {column_type}'))
    _backfill_menu_tv_slugs()
    if not _mysql_index_exists('gastronomia_cliente_config', 'ix_gastronomia_cliente_config_menu_tv_slug'):
        db.session.execute(text(
            'CREATE UNIQUE INDEX ix_gastronomia_cliente_config_menu_tv_slug '
            'ON gastronomia_cliente_config(menu_tv_slug)'
        ))


def _ensure_mysql_product_columns():
    if not _mysql_table_exists('gastronomia_productos'):
        return
    for column, column_type in PRODUCT_COLUMN_MIGRATIONS:
        if not _mysql_column_exists('gastronomia_productos', column):
            db.session.execute(text(f'ALTER TABLE gastronomia_productos ADD COLUMN {column} {column_type}'))


def _ensure_mysql_option_columns():
    if not _mysql_table_exists('gastronomia_opciones_producto'):
        return
    for column, column_type in OPTION_COLUMN_MIGRATIONS:
        if not _mysql_column_exists('gastronomia_opciones_producto', column):
            db.session.execute(text(f'ALTER TABLE gastronomia_opciones_producto ADD COLUMN {column} {column_type} NULL'))


def _ensure_mysql_central_product_columns():
    if not _mysql_table_exists('productos'):
        return
    for column, column_type in CENTRAL_PRODUCT_COLUMN_MIGRATIONS:
        if not _mysql_column_exists('productos', column):
            db.session.execute(text(f'ALTER TABLE productos ADD COLUMN {column} {column_type}'))


def _declares_nullability_or_default(column_type: str) -> bool:
    normalized = (column_type or '').upper()
    return ' NOT NULL' in normalized or ' DEFAULT ' in normalized


def _backfill_menu_tv_slugs():
    rows = db.session.execute(text(
        """
        SELECT cfg.id_config, cfg.cliente_id, cfg.menu_tv_slug, c.nombre
        FROM gastronomia_cliente_config cfg
        LEFT JOIN clientes c ON c.id_cliente = cfg.cliente_id
        WHERE cfg.menu_tv_slug IS NULL OR cfg.menu_tv_slug = ''
        """
    )).fetchall()
    if not rows:
        return
    existentes = {
        (row[0] or '').lower()
        for row in db.session.execute(text(
            """
            SELECT menu_tv_slug FROM gastronomia_cliente_config
            WHERE menu_tv_slug IS NOT NULL AND menu_tv_slug != ''
            """
        )).fetchall()
    }
    for row in rows:
        slug = _unique_menu_tv_slug(row.nombre or f'menu-tv-{row.cliente_id}', existentes)
        existentes.add(slug)
        db.session.execute(
            text('UPDATE gastronomia_cliente_config SET menu_tv_slug = :slug WHERE id_config = :id_config'),
            {'slug': slug, 'id_config': row.id_config},
        )


def _unique_menu_tv_slug(base: str, existentes: set[str]) -> str:
    root = _slugify(base)[:80] or 'menu-tv'
    slug = root
    counter = 2
    while slug in existentes:
        suffix = f'-{counter}'
        slug = f'{root[:100 - len(suffix)]}{suffix}'
        counter += 1
    return slug


def _slugify(value: str) -> str:
    text_value = unicodedata.normalize('NFKD', str(value or ''))
    text_value = ''.join(ch for ch in text_value if not unicodedata.combining(ch)).lower()
    text_value = re.sub(r'[^a-z0-9]+', '-', text_value).strip('-')
    return re.sub(r'-{2,}', '-', text_value)


def _sqlite_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
        {'table_name': table_name},
    ).scalar())


def _mysql_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name
        """
    ), {'table_name': table_name}).scalar())


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    return bool(db.session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name AND COLUMN_NAME = :column_name
        """
    ), {'table_name': table_name, 'column_name': column_name}).scalar())


def _mysql_index_exists(table_name: str, index_name: str) -> bool:
    return bool(db.session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name AND INDEX_NAME = :index_name
        """
    ), {'table_name': table_name, 'index_name': index_name}).scalar())
