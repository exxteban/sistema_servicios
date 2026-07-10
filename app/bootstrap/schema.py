from sqlalchemy import text


SCHEMA_COLUMN_MIGRATIONS = {
    'clientes': [
        (
            'nivel_estrellas',
            ("ALTER TABLE clientes ADD COLUMN nivel_estrellas INTEGER NOT NULL DEFAULT 3",),
            ("ALTER TABLE clientes ADD COLUMN nivel_estrellas INT NOT NULL DEFAULT 3",),
        ),
        (
            'fidelizacion_compras_acumuladas',
            ("ALTER TABLE clientes ADD COLUMN fidelizacion_compras_acumuladas INTEGER NOT NULL DEFAULT 0",),
            ("ALTER TABLE clientes ADD COLUMN fidelizacion_compras_acumuladas INT NOT NULL DEFAULT 0",),
        ),
        (
            'fidelizacion_consumos_disponibles',
            ("ALTER TABLE clientes ADD COLUMN fidelizacion_consumos_disponibles INTEGER NOT NULL DEFAULT 0",),
            ("ALTER TABLE clientes ADD COLUMN fidelizacion_consumos_disponibles INT NOT NULL DEFAULT 0",),
        ),
        (
            'fidelizacion_consumos_canjeados',
            ("ALTER TABLE clientes ADD COLUMN fidelizacion_consumos_canjeados INTEGER NOT NULL DEFAULT 0",),
            ("ALTER TABLE clientes ADD COLUMN fidelizacion_consumos_canjeados INT NOT NULL DEFAULT 0",),
        ),
    ],
    'usuarios': [
        (
            'id_cliente',
            (
                "ALTER TABLE usuarios ADD COLUMN id_cliente INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_usuarios_id_cliente ON usuarios(id_cliente)",
            ),
            (
                "ALTER TABLE usuarios ADD COLUMN id_cliente INT NULL",
                "CREATE INDEX ix_usuarios_id_cliente ON usuarios(id_cliente)",
            ),
        ),
    ],
    'agenda_actividades': [
        (
            'cliente_servicio_id',
            (
                "ALTER TABLE agenda_actividades ADD COLUMN cliente_servicio_id INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_agenda_actividades_cliente_servicio_id ON agenda_actividades(cliente_servicio_id)",
            ),
            (
                "ALTER TABLE agenda_actividades ADD COLUMN cliente_servicio_id INT NULL",
                "CREATE INDEX ix_agenda_actividades_cliente_servicio_id ON agenda_actividades(cliente_servicio_id)",
            ),
        ),
    ],
    'productos': [
        (
            'codigo_barras',
            (
                "ALTER TABLE productos ADD COLUMN codigo_barras VARCHAR(50)",
                "CREATE INDEX IF NOT EXISTS ix_productos_codigo_barras ON productos(codigo_barras)",
            ),
            ("ALTER TABLE productos ADD COLUMN codigo_barras VARCHAR(50) NULL",),
        ),
        (
            'publicado_tienda',
            ("ALTER TABLE productos ADD COLUMN publicado_tienda BOOLEAN NOT NULL DEFAULT 0",),
            ("ALTER TABLE productos ADD COLUMN publicado_tienda TINYINT(1) NOT NULL DEFAULT 0",),
        ),
        (
            'descripcion_tienda',
            ("ALTER TABLE productos ADD COLUMN descripcion_tienda TEXT",),
            ("ALTER TABLE productos ADD COLUMN descripcion_tienda TEXT NULL",),
        ),
        (
            'orden_tienda',
            ("ALTER TABLE productos ADD COLUMN orden_tienda INTEGER NOT NULL DEFAULT 0",),
            ("ALTER TABLE productos ADD COLUMN orden_tienda INT NOT NULL DEFAULT 0",),
        ),
        (
            'vistas_tienda',
            ("ALTER TABLE productos ADD COLUMN vistas_tienda INTEGER NOT NULL DEFAULT 0",),
            ("ALTER TABLE productos ADD COLUMN vistas_tienda INT NOT NULL DEFAULT 0",),
        ),
        (
            'es_destacado_tienda',
            ("ALTER TABLE productos ADD COLUMN es_destacado_tienda BOOLEAN NOT NULL DEFAULT 0",),
            ("ALTER TABLE productos ADD COLUMN es_destacado_tienda TINYINT(1) NOT NULL DEFAULT 0",),
        ),
        (
            'es_oferta_tienda',
            ("ALTER TABLE productos ADD COLUMN es_oferta_tienda BOOLEAN NOT NULL DEFAULT 0",),
            ("ALTER TABLE productos ADD COLUMN es_oferta_tienda TINYINT(1) NOT NULL DEFAULT 0",),
        ),
        (
            'precio_anterior_tienda',
            ("ALTER TABLE productos ADD COLUMN precio_anterior_tienda NUMERIC(10, 2)",),
            ("ALTER TABLE productos ADD COLUMN precio_anterior_tienda DECIMAL(10, 2) NULL",),
        ),
        (
            'id_cliente',
            (
                "ALTER TABLE productos ADD COLUMN id_cliente INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_productos_id_cliente ON productos(id_cliente)",
            ),
            ("ALTER TABLE productos ADD COLUMN id_cliente INT NULL",),
        ),
    ],
    'servicios': [
        (
            'turno_rapido_tipo',
            (
                "ALTER TABLE servicios ADD COLUMN turno_rapido_tipo VARCHAR(30)",
                "CREATE INDEX IF NOT EXISTS ix_servicios_turno_rapido_tipo ON servicios(turno_rapido_tipo)",
            ),
            (
                "ALTER TABLE servicios ADD COLUMN turno_rapido_tipo VARCHAR(30) NULL",
                "CREATE INDEX ix_servicios_turno_rapido_tipo ON servicios(turno_rapido_tipo)",
            ),
        ),
    ],
    'tienda_config': [
        ('mensaje_whatsapp', ("ALTER TABLE tienda_config ADD COLUMN mensaje_whatsapp VARCHAR(500)",), ("ALTER TABLE tienda_config ADD COLUMN mensaje_whatsapp VARCHAR(500) NULL",)),
        ('titulo_header_tienda', ("ALTER TABLE tienda_config ADD COLUMN titulo_header_tienda VARCHAR(200)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_header_tienda VARCHAR(200) NULL",)),
        ('mostrar_hero_tienda', ("ALTER TABLE tienda_config ADD COLUMN mostrar_hero_tienda BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_hero_tienda TINYINT(1) NOT NULL DEFAULT 1",)),
        ('mostrar_titulo_hero_tienda', ("ALTER TABLE tienda_config ADD COLUMN mostrar_titulo_hero_tienda BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_titulo_hero_tienda TINYINT(1) NOT NULL DEFAULT 1",)),
        ('titulo_hero_tienda', ("ALTER TABLE tienda_config ADD COLUMN titulo_hero_tienda VARCHAR(180)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_hero_tienda VARCHAR(180) NULL",)),
        ('mostrar_subtitulo_hero_tienda', ("ALTER TABLE tienda_config ADD COLUMN mostrar_subtitulo_hero_tienda BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_subtitulo_hero_tienda TINYINT(1) NOT NULL DEFAULT 1",)),
        ('subtitulo_hero_tienda', ("ALTER TABLE tienda_config ADD COLUMN subtitulo_hero_tienda TEXT",), ("ALTER TABLE tienda_config ADD COLUMN subtitulo_hero_tienda TEXT NULL",)),
        ('mostrar_boton_hero_tienda', ("ALTER TABLE tienda_config ADD COLUMN mostrar_boton_hero_tienda BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_boton_hero_tienda TINYINT(1) NOT NULL DEFAULT 1",)),
        ('texto_boton_hero', ("ALTER TABLE tienda_config ADD COLUMN texto_boton_hero VARCHAR(120) NOT NULL DEFAULT 'Explorar catálogo'",), ("ALTER TABLE tienda_config ADD COLUMN texto_boton_hero VARCHAR(120) NOT NULL DEFAULT 'Explorar catálogo'",)),
        ('hero_visual_tipo', ("ALTER TABLE tienda_config ADD COLUMN hero_visual_tipo VARCHAR(20) NOT NULL DEFAULT 'imagen'",), ("ALTER TABLE tienda_config ADD COLUMN hero_visual_tipo VARCHAR(20) NOT NULL DEFAULT 'imagen'",)),
        ('hero_carrusel_producto_ids', ("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_producto_ids TEXT",), ("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_producto_ids TEXT NULL",)),
        ('hero_carrusel_velocidad_segundos', ("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_velocidad_segundos INTEGER NOT NULL DEFAULT 5",), ("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_velocidad_segundos INT NOT NULL DEFAULT 5",)),
        ('hero_carrusel_animacion', ("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_animacion VARCHAR(20) NOT NULL DEFAULT 'fade'",), ("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_animacion VARCHAR(20) NOT NULL DEFAULT 'fade'",)),
        ('mostrar_bloque_beneficios_home', ("ALTER TABLE tienda_config ADD COLUMN mostrar_bloque_beneficios_home BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_bloque_beneficios_home TINYINT(1) NOT NULL DEFAULT 0",)),
        ('beneficio_home_1_texto', ("ALTER TABLE tienda_config ADD COLUMN beneficio_home_1_texto VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN beneficio_home_1_texto VARCHAR(255) NULL",)),
        ('beneficio_home_2_texto', ("ALTER TABLE tienda_config ADD COLUMN beneficio_home_2_texto VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN beneficio_home_2_texto VARCHAR(255) NULL",)),
        ('beneficio_home_3_texto', ("ALTER TABLE tienda_config ADD COLUMN beneficio_home_3_texto VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN beneficio_home_3_texto VARCHAR(255) NULL",)),
        ('texto_portada', ("ALTER TABLE tienda_config ADD COLUMN texto_portada TEXT",), ("ALTER TABLE tienda_config ADD COLUMN texto_portada TEXT NULL",)),
        ('estilo_tienda', ("ALTER TABLE tienda_config ADD COLUMN estilo_tienda VARCHAR(50) NOT NULL DEFAULT 'moderno'",), ("ALTER TABLE tienda_config ADD COLUMN estilo_tienda VARCHAR(50) NOT NULL DEFAULT 'moderno'",)),
        ('imagen_portada', ("ALTER TABLE tienda_config ADD COLUMN imagen_portada VARCHAR(500)",), ("ALTER TABLE tienda_config ADD COLUMN imagen_portada VARCHAR(500) NULL",)),
        ('mostrar_destacados', ("ALTER TABLE tienda_config ADD COLUMN mostrar_destacados BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_destacados TINYINT(1) NOT NULL DEFAULT 1",)),
        ('titulo_destacados', ("ALTER TABLE tienda_config ADD COLUMN titulo_destacados VARCHAR(150)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_destacados VARCHAR(150) NULL",)),
        ('mostrar_ofertas', ("ALTER TABLE tienda_config ADD COLUMN mostrar_ofertas BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_ofertas TINYINT(1) NOT NULL DEFAULT 1",)),
        ('titulo_ofertas', ("ALTER TABLE tienda_config ADD COLUMN titulo_ofertas VARCHAR(150)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_ofertas VARCHAR(150) NULL",)),
        ('titulo_footer', ("ALTER TABLE tienda_config ADD COLUMN titulo_footer VARCHAR(150)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_footer VARCHAR(150) NULL",)),
        ('mostrar_titulo_footer', ("ALTER TABLE tienda_config ADD COLUMN mostrar_titulo_footer BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_titulo_footer TINYINT(1) NOT NULL DEFAULT 1",)),
        ('mostrar_footer_enlaces', ("ALTER TABLE tienda_config ADD COLUMN mostrar_footer_enlaces BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_footer_enlaces TINYINT(1) NOT NULL DEFAULT 1",)),
        ('texto_footer_descripcion', ("ALTER TABLE tienda_config ADD COLUMN texto_footer_descripcion TEXT",), ("ALTER TABLE tienda_config ADD COLUMN texto_footer_descripcion TEXT NULL",)),
        ('mostrar_politicas_envio', ("ALTER TABLE tienda_config ADD COLUMN mostrar_politicas_envio BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_politicas_envio TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_politicas_envio', ("ALTER TABLE tienda_config ADD COLUMN texto_politicas_envio VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_politicas_envio VARCHAR(255) NULL",)),
        ('link_politicas_envio', ("ALTER TABLE tienda_config ADD COLUMN link_politicas_envio VARCHAR(500)",), ("ALTER TABLE tienda_config ADD COLUMN link_politicas_envio VARCHAR(500) NULL",)),
        ('mostrar_politicas_cambios', ("ALTER TABLE tienda_config ADD COLUMN mostrar_politicas_cambios BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_politicas_cambios TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_politicas_cambios', ("ALTER TABLE tienda_config ADD COLUMN texto_politicas_cambios VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_politicas_cambios VARCHAR(255) NULL",)),
        ('link_politicas_cambios', ("ALTER TABLE tienda_config ADD COLUMN link_politicas_cambios VARCHAR(500)",), ("ALTER TABLE tienda_config ADD COLUMN link_politicas_cambios VARCHAR(500) NULL",)),
        ('email_contacto', ("ALTER TABLE tienda_config ADD COLUMN email_contacto VARCHAR(200)",), ("ALTER TABLE tienda_config ADD COLUMN email_contacto VARCHAR(200) NULL",)),
        ('mostrar_email_contacto', ("ALTER TABLE tienda_config ADD COLUMN mostrar_email_contacto BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_email_contacto TINYINT(1) NOT NULL DEFAULT 0",)),
        ('sitio_web', ("ALTER TABLE tienda_config ADD COLUMN sitio_web VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN sitio_web VARCHAR(255) NULL",)),
        ('mostrar_sitio_web', ("ALTER TABLE tienda_config ADD COLUMN mostrar_sitio_web BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_sitio_web TINYINT(1) NOT NULL DEFAULT 0",)),
        ('instagram_url', ("ALTER TABLE tienda_config ADD COLUMN instagram_url VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN instagram_url VARCHAR(255) NULL",)),
        ('mostrar_instagram', ("ALTER TABLE tienda_config ADD COLUMN mostrar_instagram BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_instagram TINYINT(1) NOT NULL DEFAULT 0",)),
        ('facebook_url', ("ALTER TABLE tienda_config ADD COLUMN facebook_url VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN facebook_url VARCHAR(255) NULL",)),
        ('mostrar_facebook', ("ALTER TABLE tienda_config ADD COLUMN mostrar_facebook BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_facebook TINYINT(1) NOT NULL DEFAULT 0",)),
        ('meta_pixel_id', ("ALTER TABLE tienda_config ADD COLUMN meta_pixel_id VARCHAR(32)",), ("ALTER TABLE tienda_config ADD COLUMN meta_pixel_id VARCHAR(32) NULL",)),
        ('youtube_url', ("ALTER TABLE tienda_config ADD COLUMN youtube_url VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN youtube_url VARCHAR(255) NULL",)),
        ('mostrar_youtube', ("ALTER TABLE tienda_config ADD COLUMN mostrar_youtube BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_youtube TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_cta_catalogo', ("ALTER TABLE tienda_config ADD COLUMN texto_cta_catalogo VARCHAR(120) NOT NULL DEFAULT 'Consultar'",), ("ALTER TABLE tienda_config ADD COLUMN texto_cta_catalogo VARCHAR(120) NOT NULL DEFAULT 'Consultar'",)),
        ('texto_cta_producto', ("ALTER TABLE tienda_config ADD COLUMN texto_cta_producto VARCHAR(120) NOT NULL DEFAULT 'Comprar por WhatsApp'",), ("ALTER TABLE tienda_config ADD COLUMN texto_cta_producto VARCHAR(120) NOT NULL DEFAULT 'Comprar por WhatsApp'",)),
        ('mostrar_whatsapp_confianza', ("ALTER TABLE tienda_config ADD COLUMN mostrar_whatsapp_confianza BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_whatsapp_confianza TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_whatsapp_confianza', ("ALTER TABLE tienda_config ADD COLUMN texto_whatsapp_confianza VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_whatsapp_confianza VARCHAR(255) NULL",)),
        ('mostrar_envios', ("ALTER TABLE tienda_config ADD COLUMN mostrar_envios BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_envios TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_envios', ("ALTER TABLE tienda_config ADD COLUMN texto_envios VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_envios VARCHAR(255) NULL",)),
        ('mostrar_retiro_local', ("ALTER TABLE tienda_config ADD COLUMN mostrar_retiro_local BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_retiro_local TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_retiro_local', ("ALTER TABLE tienda_config ADD COLUMN texto_retiro_local VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_retiro_local VARCHAR(255) NULL",)),
        ('mostrar_garantia', ("ALTER TABLE tienda_config ADD COLUMN mostrar_garantia BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_garantia TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_garantia', ("ALTER TABLE tienda_config ADD COLUMN texto_garantia VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_garantia VARCHAR(255) NULL",)),
        ('mostrar_horarios', ("ALTER TABLE tienda_config ADD COLUMN mostrar_horarios BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_horarios TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_horarios', ("ALTER TABLE tienda_config ADD COLUMN texto_horarios VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_horarios VARCHAR(255) NULL",)),
        ('mostrar_cobertura', ("ALTER TABLE tienda_config ADD COLUMN mostrar_cobertura BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_cobertura TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_cobertura', ("ALTER TABLE tienda_config ADD COLUMN texto_cobertura VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_cobertura VARCHAR(255) NULL",)),
        ('mostrar_texto_apoyo_whatsapp', ("ALTER TABLE tienda_config ADD COLUMN mostrar_texto_apoyo_whatsapp BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_texto_apoyo_whatsapp TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_apoyo_whatsapp', ("ALTER TABLE tienda_config ADD COLUMN texto_apoyo_whatsapp VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_apoyo_whatsapp VARCHAR(255) NULL",)),
        ('mensaje_whatsapp_producto', ("ALTER TABLE tienda_config ADD COLUMN mensaje_whatsapp_producto TEXT",), ("ALTER TABLE tienda_config ADD COLUMN mensaje_whatsapp_producto TEXT NULL",)),
        ('mostrar_recordatorio_whatsapp', ("ALTER TABLE tienda_config ADD COLUMN mostrar_recordatorio_whatsapp BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_recordatorio_whatsapp TINYINT(1) NOT NULL DEFAULT 0",)),
        ('texto_recordatorio_whatsapp', ("ALTER TABLE tienda_config ADD COLUMN texto_recordatorio_whatsapp VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN texto_recordatorio_whatsapp VARCHAR(255) NULL",)),
        ('mostrar_beneficios_producto', ("ALTER TABLE tienda_config ADD COLUMN mostrar_beneficios_producto BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_beneficios_producto TINYINT(1) NOT NULL DEFAULT 0",)),
        ('beneficio_producto_1', ("ALTER TABLE tienda_config ADD COLUMN beneficio_producto_1 VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN beneficio_producto_1 VARCHAR(255) NULL",)),
        ('beneficio_producto_2', ("ALTER TABLE tienda_config ADD COLUMN beneficio_producto_2 VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN beneficio_producto_2 VARCHAR(255) NULL",)),
        ('beneficio_producto_3', ("ALTER TABLE tienda_config ADD COLUMN beneficio_producto_3 VARCHAR(255)",), ("ALTER TABLE tienda_config ADD COLUMN beneficio_producto_3 VARCHAR(255) NULL",)),
        ('mostrar_bloque_confianza_producto', ("ALTER TABLE tienda_config ADD COLUMN mostrar_bloque_confianza_producto BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_bloque_confianza_producto TINYINT(1) NOT NULL DEFAULT 0",)),
        ('mostrar_relacionados', ("ALTER TABLE tienda_config ADD COLUMN mostrar_relacionados BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_relacionados TINYINT(1) NOT NULL DEFAULT 1",)),
        ('titulo_relacionados', ("ALTER TABLE tienda_config ADD COLUMN titulo_relacionados VARCHAR(150) NOT NULL DEFAULT 'Productos relacionados'",), ("ALTER TABLE tienda_config ADD COLUMN titulo_relacionados VARCHAR(150) NOT NULL DEFAULT 'Productos relacionados'",)),
        ('mostrar_seccion_recomendados', ("ALTER TABLE tienda_config ADD COLUMN mostrar_seccion_recomendados BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_seccion_recomendados TINYINT(1) NOT NULL DEFAULT 0",)),
        ('titulo_recomendados', ("ALTER TABLE tienda_config ADD COLUMN titulo_recomendados VARCHAR(150)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_recomendados VARCHAR(150) NULL",)),
        ('mostrar_seccion_imperdibles', ("ALTER TABLE tienda_config ADD COLUMN mostrar_seccion_imperdibles BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_seccion_imperdibles TINYINT(1) NOT NULL DEFAULT 0",)),
        ('titulo_imperdibles', ("ALTER TABLE tienda_config ADD COLUMN titulo_imperdibles VARCHAR(150)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_imperdibles VARCHAR(150) NULL",)),
        ('titulo_panel_promociones_catalogo', ("ALTER TABLE tienda_config ADD COLUMN titulo_panel_promociones_catalogo VARCHAR(180)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_panel_promociones_catalogo VARCHAR(180) NULL",)),
        ('titulo_panel_confianza_catalogo', ("ALTER TABLE tienda_config ADD COLUMN titulo_panel_confianza_catalogo VARCHAR(180)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_panel_confianza_catalogo VARCHAR(180) NULL",)),
        ('kicker_panel_destacados_catalogo', ("ALTER TABLE tienda_config ADD COLUMN kicker_panel_destacados_catalogo VARCHAR(120)",), ("ALTER TABLE tienda_config ADD COLUMN kicker_panel_destacados_catalogo VARCHAR(120) NULL",)),
        ('titulo_panel_destacados_catalogo', ("ALTER TABLE tienda_config ADD COLUMN titulo_panel_destacados_catalogo VARCHAR(180)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_panel_destacados_catalogo VARCHAR(180) NULL",)),
        ('kicker_cta_whatsapp_catalogo', ("ALTER TABLE tienda_config ADD COLUMN kicker_cta_whatsapp_catalogo VARCHAR(120)",), ("ALTER TABLE tienda_config ADD COLUMN kicker_cta_whatsapp_catalogo VARCHAR(120) NULL",)),
        ('titulo_cta_whatsapp_catalogo', ("ALTER TABLE tienda_config ADD COLUMN titulo_cta_whatsapp_catalogo VARCHAR(180)",), ("ALTER TABLE tienda_config ADD COLUMN titulo_cta_whatsapp_catalogo VARCHAR(180) NULL",)),
        ('mostrar_descuento_porcentaje', ("ALTER TABLE tienda_config ADD COLUMN mostrar_descuento_porcentaje BOOLEAN NOT NULL DEFAULT 1",), ("ALTER TABLE tienda_config ADD COLUMN mostrar_descuento_porcentaje TINYINT(1) NOT NULL DEFAULT 1",)),
    ],
    'compras': [
        ('hora_compra', ("ALTER TABLE compras ADD COLUMN hora_compra TIME",), ("ALTER TABLE compras ADD COLUMN hora_compra TIME NULL",)),
        ('factura_imagen_url', ("ALTER TABLE compras ADD COLUMN factura_imagen_url VARCHAR(500)",), ("ALTER TABLE compras ADD COLUMN factura_imagen_url VARCHAR(500) NULL",)),
        ('es_resumida', ("ALTER TABLE compras ADD COLUMN es_resumida BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE compras ADD COLUMN es_resumida TINYINT(1) NOT NULL DEFAULT 0",)),
    ],
    'ventas': [
        (
            'client_request_id',
            (
                "ALTER TABLE ventas ADD COLUMN client_request_id VARCHAR(64)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_ventas_client_request_id ON ventas(client_request_id)",
            ),
            (
                "ALTER TABLE ventas ADD COLUMN client_request_id VARCHAR(64) NULL",
                "CREATE UNIQUE INDEX ix_ventas_client_request_id ON ventas(client_request_id)",
            ),
        ),
        (
            'id_reparacion',
            (
                "ALTER TABLE ventas ADD COLUMN id_reparacion INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_ventas_id_reparacion ON ventas(id_reparacion)",
            ),
            (
                "ALTER TABLE ventas ADD COLUMN id_reparacion INT NULL",
                "CREATE INDEX ix_ventas_id_reparacion ON ventas(id_reparacion)",
            ),
        ),
        (
            'id_usuario_vendedor',
            (
                "ALTER TABLE ventas ADD COLUMN id_usuario_vendedor INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_ventas_id_usuario_vendedor ON ventas(id_usuario_vendedor)",
            ),
            (
                "ALTER TABLE ventas ADD COLUMN id_usuario_vendedor INT NULL",
                "CREATE INDEX ix_ventas_id_usuario_vendedor ON ventas(id_usuario_vendedor)",
            ),
        ),
        (
            'descuento_manual_monto',
            ("ALTER TABLE ventas ADD COLUMN descuento_manual_monto NUMERIC(15, 2) NOT NULL DEFAULT 0",),
            ("ALTER TABLE ventas ADD COLUMN descuento_manual_monto DECIMAL(15, 2) NOT NULL DEFAULT 0",),
        ),
        (
            'descuento_fidelizacion_monto',
            ("ALTER TABLE ventas ADD COLUMN descuento_fidelizacion_monto NUMERIC(15, 2) NOT NULL DEFAULT 0",),
            ("ALTER TABLE ventas ADD COLUMN descuento_fidelizacion_monto DECIMAL(15, 2) NOT NULL DEFAULT 0",),
        ),
        (
            'beneficio_fidelizacion_tipo',
            (
                "ALTER TABLE ventas ADD COLUMN beneficio_fidelizacion_tipo VARCHAR(40)",
                "CREATE INDEX IF NOT EXISTS ix_ventas_beneficio_fidelizacion_tipo ON ventas(beneficio_fidelizacion_tipo)",
            ),
            (
                "ALTER TABLE ventas ADD COLUMN beneficio_fidelizacion_tipo VARCHAR(40) NULL",
                "CREATE INDEX ix_ventas_beneficio_fidelizacion_tipo ON ventas(beneficio_fidelizacion_tipo)",
            ),
        ),
        (
            'beneficio_fidelizacion_descripcion',
            ("ALTER TABLE ventas ADD COLUMN beneficio_fidelizacion_descripcion VARCHAR(255)",),
            ("ALTER TABLE ventas ADD COLUMN beneficio_fidelizacion_descripcion VARCHAR(255) NULL",),
        ),
    ],
    'pedidos_clientes_pagos': [
        (
            'id_sesion_caja',
            (
                "ALTER TABLE pedidos_clientes_pagos ADD COLUMN id_sesion_caja INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_pedidos_clientes_pagos_id_sesion_caja ON pedidos_clientes_pagos(id_sesion_caja)",
            ),
            (
                "ALTER TABLE pedidos_clientes_pagos ADD COLUMN id_sesion_caja INT NULL",
                "CREATE INDEX ix_pedidos_clientes_pagos_id_sesion_caja ON pedidos_clientes_pagos(id_sesion_caja)",
            ),
        ),
        (
            'id_movimiento_caja',
            (
                "ALTER TABLE pedidos_clientes_pagos ADD COLUMN id_movimiento_caja INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_pedidos_clientes_pagos_id_movimiento_caja ON pedidos_clientes_pagos(id_movimiento_caja)",
            ),
            (
                "ALTER TABLE pedidos_clientes_pagos ADD COLUMN id_movimiento_caja INT NULL",
                "CREATE INDEX ix_pedidos_clientes_pagos_id_movimiento_caja ON pedidos_clientes_pagos(id_movimiento_caja)",
            ),
        ),
    ],
    'detalle_reparaciones': [
        (
            'incluye_costo_final',
            (
                "ALTER TABLE detalle_reparaciones ADD COLUMN incluye_costo_final BOOLEAN NOT NULL DEFAULT 0",
                "CREATE INDEX IF NOT EXISTS ix_detalle_reparaciones_incluye_costo_final ON detalle_reparaciones(incluye_costo_final)",
            ),
            (
                "ALTER TABLE detalle_reparaciones ADD COLUMN incluye_costo_final BOOLEAN NOT NULL DEFAULT 0",
                "CREATE INDEX ix_detalle_reparaciones_incluye_costo_final ON detalle_reparaciones(incluye_costo_final)",
            ),
        ),
    ],
    'reparaciones': [
        ('password_patron_cifrado', ("ALTER TABLE reparaciones ADD COLUMN password_patron_cifrado VARCHAR(255)",), ("ALTER TABLE reparaciones ADD COLUMN password_patron_cifrado VARCHAR(255) NULL",)),
        ('patron_dibujo', ("ALTER TABLE reparaciones ADD COLUMN patron_dibujo TEXT",), ("ALTER TABLE reparaciones ADD COLUMN patron_dibujo TEXT NULL",)),
        ('nota_cliente', ("ALTER TABLE reparaciones ADD COLUMN nota_cliente TEXT",), ("ALTER TABLE reparaciones ADD COLUMN nota_cliente TEXT NULL",)),
        ('mostrar_costo', ("ALTER TABLE reparaciones ADD COLUMN mostrar_costo BOOLEAN NOT NULL DEFAULT 0",), ("ALTER TABLE reparaciones ADD COLUMN mostrar_costo BOOLEAN NOT NULL DEFAULT 0",)),
        ('fecha_estimada_hora', ("ALTER TABLE reparaciones ADD COLUMN fecha_estimada_hora TIME",), ("ALTER TABLE reparaciones ADD COLUMN fecha_estimada_hora TIME NULL",)),
        (
            'id_usuario_vendedor',
            (
                "ALTER TABLE reparaciones ADD COLUMN id_usuario_vendedor INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_reparaciones_id_usuario_vendedor ON reparaciones(id_usuario_vendedor)",
            ),
            (
                "ALTER TABLE reparaciones ADD COLUMN id_usuario_vendedor INT NULL",
                "CREATE INDEX ix_reparaciones_id_usuario_vendedor ON reparaciones(id_usuario_vendedor)",
            ),
        ),
        (
            'id_usuario_tecnico',
            (
                "ALTER TABLE reparaciones ADD COLUMN id_usuario_tecnico INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_reparaciones_id_usuario_tecnico ON reparaciones(id_usuario_tecnico)",
            ),
            (
                "ALTER TABLE reparaciones ADD COLUMN id_usuario_tecnico INT NULL",
                "CREATE INDEX ix_reparaciones_id_usuario_tecnico ON reparaciones(id_usuario_tecnico)",
            ),
        ),
        (
            'fecha_toma_tecnico',
            (
                "ALTER TABLE reparaciones ADD COLUMN fecha_toma_tecnico DATETIME",
                "CREATE INDEX IF NOT EXISTS ix_reparaciones_fecha_toma_tecnico ON reparaciones(fecha_toma_tecnico)",
            ),
            (
                "ALTER TABLE reparaciones ADD COLUMN fecha_toma_tecnico DATETIME NULL",
                "CREATE INDEX ix_reparaciones_fecha_toma_tecnico ON reparaciones(fecha_toma_tecnico)",
            ),
        ),
        ('fecha_listo_tecnico', ("ALTER TABLE reparaciones ADD COLUMN fecha_listo_tecnico DATETIME",), ("ALTER TABLE reparaciones ADD COLUMN fecha_listo_tecnico DATETIME NULL",)),
    ],
    'reparacion_seguimiento': [
        ('token_cifrado', ("ALTER TABLE reparacion_seguimiento ADD COLUMN token_cifrado VARCHAR(255)",), ("ALTER TABLE reparacion_seguimiento ADD COLUMN token_cifrado VARCHAR(255) NULL",)),
    ],
    'clientes_fidelizacion_movimientos': [
        (
            'beneficio_tipo',
            ("ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_tipo VARCHAR(40)",),
            ("ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_tipo VARCHAR(40) NULL",),
        ),
        (
            'beneficio_valor',
            ("ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_valor NUMERIC(15, 2)",),
            ("ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_valor DECIMAL(15, 2) NULL",),
        ),
        (
            'beneficio_descripcion',
            ("ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_descripcion VARCHAR(255)",),
            ("ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_descripcion VARCHAR(255) NULL",),
        ),
        (
            'beneficio_fecha_vencimiento',
            (
                "ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_fecha_vencimiento DATE",
                "CREATE INDEX IF NOT EXISTS ix_clientes_fidelizacion_movimientos_beneficio_fecha_vencimiento ON clientes_fidelizacion_movimientos(beneficio_fecha_vencimiento)",
            ),
            (
                "ALTER TABLE clientes_fidelizacion_movimientos ADD COLUMN beneficio_fecha_vencimiento DATE NULL",
                "CREATE INDEX ix_clientes_fidelizacion_movimientos_beneficio_fecha_vencimiento ON clientes_fidelizacion_movimientos(beneficio_fecha_vencimiento)",
            ),
        ),
    ],
    'whatsapp_asignacion_conversacion': [
        ('ultima_respuesta_asesor_at', ("ALTER TABLE whatsapp_asignacion_conversacion ADD COLUMN ultima_respuesta_asesor_at DATETIME",), ("ALTER TABLE whatsapp_asignacion_conversacion ADD COLUMN ultima_respuesta_asesor_at DATETIME NULL",)),
        ('motivo_devolucion', ("ALTER TABLE whatsapp_asignacion_conversacion ADD COLUMN motivo_devolucion VARCHAR(30)",), ("ALTER TABLE whatsapp_asignacion_conversacion ADD COLUMN motivo_devolucion VARCHAR(30) NULL",)),
    ],
    'whatsapp_estado_asesor': [
        ('ultima_asignacion', ("ALTER TABLE whatsapp_estado_asesor ADD COLUMN ultima_asignacion DATETIME",), ("ALTER TABLE whatsapp_estado_asesor ADD COLUMN ultima_asignacion DATETIME NULL",)),
    ],
    'agenda_actividades': [
        ('mostrar_agenda_en', ("ALTER TABLE agenda_actividades ADD COLUMN mostrar_agenda_en VARCHAR(30) NOT NULL DEFAULT 'solo_responsable'",), ("ALTER TABLE agenda_actividades ADD COLUMN mostrar_agenda_en VARCHAR(30) NOT NULL DEFAULT 'solo_responsable'",)),
        ('recordatorio_a', ("ALTER TABLE agenda_actividades ADD COLUMN recordatorio_a VARCHAR(30) NOT NULL DEFAULT 'solo_responsable'",), ("ALTER TABLE agenda_actividades ADD COLUMN recordatorio_a VARCHAR(30) NOT NULL DEFAULT 'solo_responsable'",)),
    ],
}


SQLITE_POST_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agenda_actividades_mostrar_agenda_en ON agenda_actividades(mostrar_agenda_en)",
    "CREATE INDEX IF NOT EXISTS ix_agenda_actividades_recordatorio_a ON agenda_actividades(recordatorio_a)",
    "CREATE INDEX IF NOT EXISTS ix_agenda_actividad_visible_usuarios_usuario_id ON agenda_actividad_visible_usuarios(usuario_id)",
    "CREATE INDEX IF NOT EXISTS ix_agenda_actividad_recordatorio_usuarios_usuario_id ON agenda_actividad_recordatorio_usuarios(usuario_id)",
)


MYSQL_INDEX_MIGRATIONS = (
    ('usuarios', 'ix_usuarios_id_cliente', "CREATE INDEX ix_usuarios_id_cliente ON usuarios(id_cliente)"),
    ('productos', 'ix_productos_id_cliente', "CREATE INDEX ix_productos_id_cliente ON productos(id_cliente)"),
    ('productos', 'ix_productos_codigo_barras', "CREATE INDEX ix_productos_codigo_barras ON productos(codigo_barras)"),
    ('cola_cobro', 'ix_cola_cobro_estado_fecha_envio', "CREATE INDEX ix_cola_cobro_estado_fecha_envio ON cola_cobro(estado, fecha_envio)"),
    ('agenda_actividades', 'ix_agenda_actividades_mostrar_agenda_en', "CREATE INDEX ix_agenda_actividades_mostrar_agenda_en ON agenda_actividades(mostrar_agenda_en)"),
    ('agenda_actividades', 'ix_agenda_actividades_recordatorio_a', "CREATE INDEX ix_agenda_actividades_recordatorio_a ON agenda_actividades(recordatorio_a)"),
    ('agenda_actividad_visible_usuarios', 'ix_agenda_actividad_visible_usuarios_usuario_id', "CREATE INDEX ix_agenda_actividad_visible_usuarios_usuario_id ON agenda_actividad_visible_usuarios(usuario_id)"),
    ('agenda_actividad_recordatorio_usuarios', 'ix_agenda_actividad_recordatorio_usuarios_usuario_id', "CREATE INDEX ix_agenda_actividad_recordatorio_usuarios_usuario_id ON agenda_actividad_recordatorio_usuarios(usuario_id)"),
)


def _execute_and_commit(db, statements):
    for statement in statements:
        db.session.execute(text(statement))
    db.session.commit()


def _sqlite_columns(db, table_name):
    return {row[1] for row in db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}


def _mysql_scalar(db, query):
    return db.session.execute(text(query)).scalar()


def _mysql_table_exists(db, table_name):
    query = f"""
    SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{table_name}'
    """
    return bool(_mysql_scalar(db, query))


def _mysql_column_exists(db, table_name, column_name):
    query = f"""
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{table_name}'
      AND COLUMN_NAME = '{column_name}'
    """
    return bool(_mysql_scalar(db, query))


def _mysql_index_exists(db, table_name, index_name):
    query = f"""
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{table_name}'
      AND INDEX_NAME = '{index_name}'
    """
    return bool(_mysql_scalar(db, query))


def _apply_sqlite_migrations(db):
    for table_name, specs in SCHEMA_COLUMN_MIGRATIONS.items():
        existing_columns = _sqlite_columns(db, table_name)
        for column_name, sqlite_statements, _mysql_statements in specs:
            if column_name in existing_columns:
                continue
            _execute_and_commit(db, sqlite_statements)
            existing_columns.add(column_name)

    from app.bootstrap.caja_unique_schema import ensure_sqlite_caja_unique_indexes
    ensure_sqlite_caja_unique_indexes(db)

    _execute_and_commit(db, SQLITE_POST_STATEMENTS)


def _apply_mysql_migrations(db):
    for table_name, specs in SCHEMA_COLUMN_MIGRATIONS.items():
        if table_name == 'tienda_config' and not _mysql_table_exists(db, table_name):
            continue
        for column_name, _sqlite_statements, mysql_statements in specs:
            if _mysql_column_exists(db, table_name, column_name):
                continue
            _execute_and_commit(db, mysql_statements)

    for table_name, index_name, ddl in MYSQL_INDEX_MIGRATIONS:
        if not _mysql_table_exists(db, table_name) or _mysql_index_exists(db, table_name, index_name):
            continue
        _execute_and_commit(db, (ddl,))

    from app.bootstrap.caja_unique_schema import ensure_mysql_caja_unique_indexes
    ensure_mysql_caja_unique_indexes(db, _mysql_table_exists, _mysql_column_exists, _mysql_index_exists)


def initialize_database(app, db, config_name='default'):
    with app.app_context():
        db.create_all()

        from cobranzas.schema import ensure_cobranzas_schema
        from control_de_empleados.schema import ensure_control_empleados_schema, ensure_asistencia_schema
        from flujo_caja.schema import ensure_flujo_caja_schema
        from gastos_corrientes.schema import ensure_gastos_corrientes_schema

        ensure_cobranzas_schema()
        ensure_control_empleados_schema()
        ensure_asistencia_schema()
        ensure_flujo_caja_schema()
        ensure_gastos_corrientes_schema()
        from gastronomia.schema import ensure_gastronomia_schema
        ensure_gastronomia_schema()
        from app.bootstrap.promociones_schema import ensure_promociones_schema
        ensure_promociones_schema()

        try:
            dialect = db.engine.dialect.name
            if dialect == 'sqlite':
                _apply_sqlite_migrations(db)
            elif dialect == 'mysql':
                _apply_mysql_migrations(db)
        except Exception:
            db.session.rollback()

        from app.utils.init_db import inicializar_datos_base

        inicializar_datos_base(config_name=config_name)
