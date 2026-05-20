"""
Construcción de contexto compartido para asistentes por canal.
"""
import json

from app.models.tienda import TiendaConfig
from app.models.whatsapp import WhatsAppConfiguracion
from app.services.bot_context import load_bot_context
from app.services.tienda_promociones import serialize_context_promotions


FAQ_DEFAULTS = {
    'horarios': 'Lunes a sábados de 8:00 a 18:00.',
    'ubicacion': 'Consultá por WhatsApp para confirmar la dirección exacta.',
    'garantia': 'Ofrecemos garantía según el tipo de producto o servicio.',
    'metodos_pago': 'Aceptamos efectivo, transferencia bancaria y pago con tarjeta.',
}


def _faq_value(key: str, fallback: str) -> str:
    record = WhatsAppConfiguracion.query.filter_by(clave=f'faq_{key}').first()
    value = (getattr(record, 'valor', '') or '').strip()
    return value or fallback


def build_store_assistant_context(config: TiendaConfig, metadata: dict | None = None) -> dict:
    public_config = config.to_public_dict()
    bot_context = load_bot_context()
    faq = {
        'horarios': public_config.get('texto_horarios') or bot_context.get('horarios_atencion') or _faq_value('horarios', FAQ_DEFAULTS['horarios']),
        'ubicacion': bot_context.get('direccion') or _faq_value('ubicacion', FAQ_DEFAULTS['ubicacion']),
        'garantia': public_config.get('texto_garantia') or _faq_value('garantia', FAQ_DEFAULTS['garantia']),
        'metodos_pago': bot_context.get('formas_de_pago') or _faq_value('metodos_pago', FAQ_DEFAULTS['metodos_pago']),
        'contacto': bot_context.get('telefonos_contacto') or '',
        'zonas_de_entrega': bot_context.get('zonas_de_entrega') or '',
        'politica_cambios': bot_context.get('politica_cambios') or '',
        'envios': public_config.get('texto_envios') or '',
        'retiro_local': public_config.get('texto_retiro_local') or '',
        'cobertura': public_config.get('texto_cobertura') or '',
    }
    faq = {key: value for key, value in faq.items() if value}

    return {
        'tienda': {
            'slug': config.slug,
            'nombre': bot_context.get('nombre_negocio') or config.nombre_tienda or 'Tienda Online',
            'telefono_whatsapp': config.telefono_whatsapp or '',
        },
        'contexto_bot': bot_context,
        'faq': faq,
        'senales_confianza': (public_config.get('senales_confianza') or [])[:4],
        'beneficios_producto': (public_config.get('beneficios_producto_items') or [])[:4],
        'promociones_activas': serialize_context_promotions(config, limit=3),
    }


def parse_session_metadata(raw_value: str | None) -> dict:
    try:
        data = json.loads(raw_value or '{}')
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
