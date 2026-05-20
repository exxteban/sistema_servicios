"""
Configuracion compartida de contexto de negocio para bots de WhatsApp y web.
"""
import json

from app.models.whatsapp import WhatsAppConfiguracion


BOT_CONTEXT_CONFIG_KEY = 'bot_contexto_negocio'

BOT_CONTEXT_FIELDS = (
    {
        'key': 'nombre_negocio',
        'label': 'Nombre del negocio',
        'placeholder': 'Ej: Silvio Cell',
        'help': 'Nombre comercial que el bot debe usar al responder.',
        'multiline': False,
    },
    {
        'key': 'descripcion_negocio',
        'label': 'Descripcion del negocio',
        'placeholder': 'Ej: Reparacion de celulares, venta de accesorios y equipos.',
        'help': 'Resumen corto para que el bot entienda a que se dedica el local.',
        'multiline': True,
    },
    {
        'key': 'direccion',
        'label': 'Direccion',
        'placeholder': 'Ej: Av. España 1234, Asuncion',
        'help': 'Ubicacion o referencia que el bot puede compartir.',
        'multiline': True,
    },
    {
        'key': 'telefonos_contacto',
        'label': 'Telefonos de contacto',
        'placeholder': 'Ej: 0981 111111 / 021 222222',
        'help': 'Telefonos que el bot puede pasar cuando pidan contacto.',
        'multiline': True,
    },
    {
        'key': 'horarios_atencion',
        'label': 'Horarios de atencion',
        'placeholder': 'Ej: Lunes a sabados de 8:00 a 18:00',
        'help': 'Horario comercial para WhatsApp y web.',
        'multiline': True,
    },
    {
        'key': 'formas_de_pago',
        'label': 'Formas de pago',
        'placeholder': 'Ej: Efectivo, transferencia, tarjeta y QR',
        'help': 'Metodos de pago que el bot puede informar.',
        'multiline': True,
    },
    {
        'key': 'zonas_de_entrega',
        'label': 'Zonas de entrega',
        'placeholder': 'Ej: Asuncion, San Lorenzo y Fernando de la Mora',
        'help': 'Cobertura o zonas donde entregan/envian.',
        'multiline': True,
    },
    {
        'key': 'politica_cambios',
        'label': 'Politica de cambios',
        'placeholder': 'Ej: Cambios dentro de 48 hs con ticket y producto en buen estado.',
        'help': 'Condiciones de cambios, devoluciones o reclamos comerciales.',
        'multiline': True,
    },
    {
        'key': 'cuando_derivar_a_humano',
        'label': 'Cuando derivar a humano',
        'placeholder': 'Ej: Reclamos, pagos no registrados, pedidos especiales o clientes molestos.',
        'help': 'Regla operativa para que el bot sepa cuando pasar a una persona.',
        'multiline': True,
    },
    {
        'key': 'tono_respuesta',
        'label': 'Tono de respuesta',
        'placeholder': 'Ej: Cercano, amable, breve y profesional.',
        'help': 'Indica el estilo que el bot debe mantener.',
        'multiline': True,
    },
    {
        'key': 'contexto_extra',
        'label': 'Contexto extra',
        'placeholder': 'Ej: No prometer entregas en el dia sin confirmacion humana.',
        'help': 'Reglas, excepciones o detalles adicionales importantes para ambos bots.',
        'multiline': True,
    },
)

BOT_CONTEXT_DEFAULTS = {field['key']: '' for field in BOT_CONTEXT_FIELDS}

BOT_CONTEXT_FAQ_TOPICS = {
    'horarios': 'horarios_atencion',
    'ubicacion': 'direccion',
    'metodos_pago': 'formas_de_pago',
    'contacto': 'telefonos_contacto',
    'zonas_de_entrega': 'zonas_de_entrega',
    'politica_cambios': 'politica_cambios',
}


def normalize_bot_context(payload: dict | None) -> dict:
    data = payload if isinstance(payload, dict) else {}
    normalizado = {}
    for field in BOT_CONTEXT_FIELDS:
        value = data.get(field['key'], '')
        if isinstance(value, list):
            value = '\n'.join(str(item).strip() for item in value if str(item).strip())
        normalizado[field['key']] = str(value or '').strip()
    return normalizado


def load_bot_context() -> dict:
    record = WhatsAppConfiguracion.query.filter_by(clave=BOT_CONTEXT_CONFIG_KEY).first()
    if not record or not record.valor:
        return dict(BOT_CONTEXT_DEFAULTS)
    try:
        payload = json.loads(record.valor)
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(BOT_CONTEXT_DEFAULTS)
    return normalize_bot_context(payload)


def build_bot_context_faq(extra_defaults: dict | None = None) -> dict:
    context = load_bot_context()
    faq = {}
    for topic, field_key in BOT_CONTEXT_FAQ_TOPICS.items():
        value = context.get(field_key, '')
        if value:
            faq[topic] = value
    for key, value in (extra_defaults or {}).items():
        if value and not faq.get(key):
            faq[key] = value
    return faq
