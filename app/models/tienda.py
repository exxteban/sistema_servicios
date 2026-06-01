"""
Modelos para el módulo Tienda Online
Multi-tenant: todos los datos van atados a id_cliente (nunca cross-tenant).
"""
from datetime import datetime
from app import db


class TiendaConfig(db.Model):
    """Configuración pública de la tienda de un cliente (1 por cliente)."""
    __tablename__ = 'tienda_config'

    id_config = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True
    )
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    nombre_tienda = db.Column(db.String(200), nullable=True)
    titulo_header_tienda = db.Column(db.String(200), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    color_primario = db.Column(db.String(20), nullable=False, default='#6366f1')
    telefono_whatsapp = db.Column(db.String(30), nullable=True)
    mensaje_whatsapp = db.Column(db.String(500), nullable=True)
    mostrar_hero_tienda = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    mostrar_titulo_hero_tienda = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    titulo_hero_tienda = db.Column(db.String(180), nullable=True)
    mostrar_subtitulo_hero_tienda = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    subtitulo_hero_tienda = db.Column(db.Text, nullable=True)
    mostrar_boton_hero_tienda = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    texto_boton_hero = db.Column(db.String(120), nullable=False, default='Explorar catálogo', server_default='Explorar catálogo')
    hero_visual_tipo = db.Column(db.String(20), nullable=False, default='imagen', server_default='imagen')
    hero_carrusel_producto_ids = db.Column(db.Text, nullable=True)
    hero_carrusel_velocidad_segundos = db.Column(db.Integer, nullable=False, default=5, server_default='5')
    hero_carrusel_animacion = db.Column(db.String(20), nullable=False, default='fade', server_default='fade')
    mostrar_bloque_beneficios_home = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    beneficio_home_1_texto = db.Column(db.String(255), nullable=True)
    beneficio_home_2_texto = db.Column(db.String(255), nullable=True)
    beneficio_home_3_texto = db.Column(db.String(255), nullable=True)
    texto_portada = db.Column(db.Text, nullable=True)
    imagen_portada = db.Column(db.String(500), nullable=True)
    mostrar_destacados = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    titulo_destacados = db.Column(db.String(150), nullable=True)
    mostrar_ofertas = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    titulo_ofertas = db.Column(db.String(150), nullable=True)
    mostrar_seccion_recomendados = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    titulo_recomendados = db.Column(db.String(150), nullable=True)
    mostrar_seccion_imperdibles = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    titulo_imperdibles = db.Column(db.String(150), nullable=True)
    titulo_footer = db.Column(db.String(150), nullable=True)
    mostrar_titulo_footer = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    mostrar_footer_enlaces = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    texto_footer_descripcion = db.Column(db.Text, nullable=True)
    mostrar_politicas_envio = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_politicas_envio = db.Column(db.String(255), nullable=True)
    link_politicas_envio = db.Column(db.String(500), nullable=True)
    mostrar_politicas_cambios = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_politicas_cambios = db.Column(db.String(255), nullable=True)
    link_politicas_cambios = db.Column(db.String(500), nullable=True)
    email_contacto = db.Column(db.String(200), nullable=True)
    mostrar_email_contacto = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    sitio_web = db.Column(db.String(255), nullable=True)
    mostrar_sitio_web = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    instagram_url = db.Column(db.String(255), nullable=True)
    mostrar_instagram = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    facebook_url = db.Column(db.String(255), nullable=True)
    mostrar_facebook = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    meta_pixel_id = db.Column(db.String(32), nullable=True)
    youtube_url = db.Column(db.String(255), nullable=True)
    mostrar_youtube = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_cta_catalogo = db.Column(db.String(120), nullable=False, default='Consultar', server_default='Consultar')
    texto_cta_producto = db.Column(db.String(120), nullable=False, default='Comprar por WhatsApp', server_default='Comprar por WhatsApp')
    mostrar_whatsapp_confianza = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_whatsapp_confianza = db.Column(db.String(255), nullable=True)
    mostrar_envios = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_envios = db.Column(db.String(255), nullable=True)
    mostrar_retiro_local = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_retiro_local = db.Column(db.String(255), nullable=True)
    mostrar_garantia = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_garantia = db.Column(db.String(255), nullable=True)
    mostrar_horarios = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_horarios = db.Column(db.String(255), nullable=True)
    mostrar_cobertura = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_cobertura = db.Column(db.String(255), nullable=True)
    mostrar_texto_apoyo_whatsapp = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_apoyo_whatsapp = db.Column(db.String(255), nullable=True)
    mensaje_whatsapp_producto = db.Column(db.Text, nullable=True)
    mostrar_recordatorio_whatsapp = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    texto_recordatorio_whatsapp = db.Column(db.String(255), nullable=True)
    mostrar_beneficios_producto = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    beneficio_producto_1 = db.Column(db.String(255), nullable=True)
    beneficio_producto_2 = db.Column(db.String(255), nullable=True)
    beneficio_producto_3 = db.Column(db.String(255), nullable=True)
    mostrar_bloque_confianza_producto = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    mostrar_relacionados = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    titulo_relacionados = db.Column(db.String(150), nullable=False, default='Productos relacionados', server_default='Productos relacionados')
    mostrar_descuento_porcentaje = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    estilo_tienda = db.Column(db.String(50), nullable=False, default='moderno')
    activa = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relación al cliente (lectura)
    cliente = db.relationship('Cliente', backref='tienda_config', uselist=False)

    def _trust_signals(self):
        señales = []
        bloques = (
            ('whatsapp', self.mostrar_whatsapp_confianza, self.texto_whatsapp_confianza),
            ('envios', self.mostrar_envios, self.texto_envios),
            ('retiro', self.mostrar_retiro_local, self.texto_retiro_local),
            ('garantia', self.mostrar_garantia, self.texto_garantia),
            ('horarios', self.mostrar_horarios, self.texto_horarios),
            ('cobertura', self.mostrar_cobertura, self.texto_cobertura),
        )
        for clave, mostrar, texto in bloques:
            if mostrar and texto:
                señales.append({'key': clave, 'text': texto})
        return señales

    def _product_benefits(self):
        if not self.mostrar_beneficios_producto:
            return []
        return [
            texto for texto in (
                self.beneficio_producto_1,
                self.beneficio_producto_2,
                self.beneficio_producto_3,
            )
            if texto
        ]

    def _home_benefits(self):
        if not self.mostrar_bloque_beneficios_home:
            return []
        return [
            texto for texto in (
                self.beneficio_home_1_texto,
                self.beneficio_home_2_texto,
                self.beneficio_home_3_texto,
            )
            if texto
        ]

    def _hero_carousel_product_ids(self):
        ids = []
        seen = set()
        for raw_item in str(self.hero_carrusel_producto_ids or '').replace(';', ',').split(','):
            try:
                product_id = int(raw_item.strip())
            except (TypeError, ValueError):
                continue
            if product_id <= 0 or product_id in seen:
                continue
            ids.append(product_id)
            seen.add(product_id)
        return ids

    def to_public_dict(self):
        """Serialización segura para la API pública."""
        return {
            'slug': self.slug,
            'nombre_tienda': self.nombre_tienda,
            'titulo_header_tienda': self.titulo_header_tienda,
            'logo_url': self.logo_url,
            'color_primario': self.color_primario,
            'telefono_whatsapp': self.telefono_whatsapp,
            'mensaje_whatsapp': self.mensaje_whatsapp,
            'mensaje_whatsapp_general': self.mensaje_whatsapp,
            'mostrar_hero_tienda': self.mostrar_hero_tienda,
            'mostrar_titulo_hero_tienda': self.mostrar_titulo_hero_tienda,
            'titulo_hero_tienda': self.titulo_hero_tienda,
            'mostrar_subtitulo_hero_tienda': self.mostrar_subtitulo_hero_tienda,
            'subtitulo_hero_tienda': self.subtitulo_hero_tienda,
            'mostrar_boton_hero_tienda': self.mostrar_boton_hero_tienda,
            'texto_boton_hero': self.texto_boton_hero or 'Explorar catálogo',
            'hero_visual_tipo': self.hero_visual_tipo or 'imagen',
            'hero_carrusel_producto_ids': self.hero_carrusel_producto_ids,
            'hero_carrusel_producto_ids_items': self._hero_carousel_product_ids(),
            'hero_carrusel_velocidad_segundos': int(self.hero_carrusel_velocidad_segundos or 5),
            'hero_carrusel_animacion': self.hero_carrusel_animacion or 'fade',
            'mostrar_bloque_beneficios_home': self.mostrar_bloque_beneficios_home,
            'beneficio_home_1_texto': self.beneficio_home_1_texto,
            'beneficio_home_2_texto': self.beneficio_home_2_texto,
            'beneficio_home_3_texto': self.beneficio_home_3_texto,
            'beneficios_home_items': self._home_benefits(),
            'mensaje_whatsapp_producto': self.mensaje_whatsapp_producto,
            'texto_portada': self.texto_portada,
            'imagen_portada': self.imagen_portada,
            'mostrar_destacados': self.mostrar_destacados,
            'titulo_destacados': self.titulo_destacados,
            'mostrar_ofertas': self.mostrar_ofertas,
            'titulo_ofertas': self.titulo_ofertas,
            'mostrar_seccion_recomendados': self.mostrar_seccion_recomendados,
            'titulo_recomendados': self.titulo_recomendados,
            'mostrar_seccion_imperdibles': self.mostrar_seccion_imperdibles,
            'titulo_imperdibles': self.titulo_imperdibles,
            'titulo_footer': self.titulo_footer,
            'mostrar_titulo_footer': self.mostrar_titulo_footer,
            'mostrar_footer_enlaces': self.mostrar_footer_enlaces,
            'texto_footer_descripcion': self.texto_footer_descripcion,
            'mostrar_politicas_envio': self.mostrar_politicas_envio,
            'texto_politicas_envio': self.texto_politicas_envio,
            'link_politicas_envio': self.link_politicas_envio,
            'mostrar_politicas_cambios': self.mostrar_politicas_cambios,
            'texto_politicas_cambios': self.texto_politicas_cambios,
            'link_politicas_cambios': self.link_politicas_cambios,
            'email_contacto': self.email_contacto,
            'mostrar_email_contacto': self.mostrar_email_contacto,
            'sitio_web': self.sitio_web,
            'mostrar_sitio_web': self.mostrar_sitio_web,
            'instagram_url': self.instagram_url,
            'mostrar_instagram': self.mostrar_instagram,
            'facebook_url': self.facebook_url,
            'mostrar_facebook': self.mostrar_facebook,
            'meta_pixel_id': self.meta_pixel_id,
            'youtube_url': self.youtube_url,
            'mostrar_youtube': self.mostrar_youtube,
            'texto_cta_catalogo': self.texto_cta_catalogo or 'Consultar',
            'texto_cta_producto': self.texto_cta_producto or 'Comprar por WhatsApp',
            'mostrar_whatsapp_confianza': self.mostrar_whatsapp_confianza,
            'texto_whatsapp_confianza': self.texto_whatsapp_confianza,
            'mostrar_envios': self.mostrar_envios,
            'texto_envios': self.texto_envios,
            'mostrar_retiro_local': self.mostrar_retiro_local,
            'texto_retiro_local': self.texto_retiro_local,
            'mostrar_garantia': self.mostrar_garantia,
            'texto_garantia': self.texto_garantia,
            'mostrar_horarios': self.mostrar_horarios,
            'texto_horarios': self.texto_horarios,
            'mostrar_cobertura': self.mostrar_cobertura,
            'texto_cobertura': self.texto_cobertura,
            'mostrar_texto_apoyo_whatsapp': self.mostrar_texto_apoyo_whatsapp,
            'texto_apoyo_whatsapp': self.texto_apoyo_whatsapp,
            'mostrar_recordatorio_whatsapp': self.mostrar_recordatorio_whatsapp,
            'texto_recordatorio_whatsapp': self.texto_recordatorio_whatsapp,
            'mostrar_beneficios_producto': self.mostrar_beneficios_producto,
            'beneficio_producto_1': self.beneficio_producto_1,
            'beneficio_producto_2': self.beneficio_producto_2,
            'beneficio_producto_3': self.beneficio_producto_3,
            'mostrar_bloque_confianza_producto': self.mostrar_bloque_confianza_producto,
            'mostrar_relacionados': self.mostrar_relacionados,
            'titulo_relacionados': self.titulo_relacionados or 'Productos relacionados',
            'mostrar_descuento_porcentaje': self.mostrar_descuento_porcentaje,
            'senales_confianza': self._trust_signals(),
            'beneficios_producto_items': self._product_benefits(),
            'estilo_tienda': self.estilo_tienda,
        }

    def __repr__(self):
        return f'<TiendaConfig slug={self.slug} cliente={self.id_cliente}>'


class ProductoImagen(db.Model):
    """Imágenes adicionales de un producto para la tienda."""
    __tablename__ = 'producto_imagenes'

    id_imagen = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(
        db.Integer,
        db.ForeignKey('productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    url = db.Column(db.String(500), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    activa = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_producto_imagenes_producto_activa', 'id_producto', 'activa'),
    )

    def to_dict(self):
        return {
            'id_imagen': self.id_imagen,
            'url': self.url,
            'orden': self.orden,
        }

    def __repr__(self):
        return f'<ProductoImagen id={self.id_imagen} producto={self.id_producto}>'


class TiendaLead(db.Model):
    """Registro de intenciones de compra recibidas por formulario."""
    __tablename__ = 'tienda_leads'

    id_lead = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    id_producto = db.Column(
        db.Integer,
        db.ForeignKey('productos.id_producto', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    nombre_contacto = db.Column(db.String(200), nullable=False)
    telefono_contacto = db.Column(db.String(50), nullable=True)
    email_contacto = db.Column(db.String(120), nullable=True)
    mensaje = db.Column(db.Text, nullable=True)
    leido = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relaciones de lectura
    producto = db.relationship('Producto', backref='leads_tienda', lazy='select')

    __table_args__ = (
        db.Index('ix_tienda_leads_cliente_leido', 'id_cliente', 'leido'),
    )

    def __repr__(self):
        return f'<TiendaLead id={self.id_lead} cliente={self.id_cliente}>'


class TiendaVisitaEvento(db.Model):
    __tablename__ = 'tienda_visitas_eventos'

    id_visita = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    id_producto = db.Column(
        db.Integer,
        db.ForeignKey('productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    id_usuario = db.Column(
        db.Integer,
        db.ForeignKey('usuarios.id_usuario', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    visitante_hash = db.Column(db.String(64), nullable=False, index=True)
    referer_url = db.Column(db.String(500), nullable=True)
    fecha_evento = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    producto = db.relationship('Producto', backref='visitas_tienda_eventos', lazy='select')
    usuario = db.relationship('Usuario', backref='visitas_tienda_eventos', lazy='select')

    __table_args__ = (
        db.Index('ix_tienda_visitas_cliente_producto_fecha', 'id_cliente', 'id_producto', 'fecha_evento'),
        db.Index('ix_tienda_visitas_producto_visitante', 'id_producto', 'visitante_hash'),
    )

    def __repr__(self):
        return f'<TiendaVisitaEvento id={self.id_visita} cliente={self.id_cliente} producto={self.id_producto}>'
