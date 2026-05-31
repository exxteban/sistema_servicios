"""
Tools y handlers para el asistente web de tienda.
"""
from decimal import Decimal
import re
import unicodedata

from app import db
from app.models.producto import Categoria, Producto
from app.services.asistente.store_truth_tools import (
    obtener_calendario_relativo,
    obtener_contexto_temporal_local,
    obtener_envio_estimado,
    obtener_estado_tienda_actual,
    obtener_fecha_hora_actual,
    obtener_info_contacto_actual,
    obtener_metodos_pago_vigentes,
    obtener_politicas_publicas,
    obtener_precio_preciso_producto,
    obtener_stock_preciso_producto,
)
from app.services.tienda_promociones import (
    attach_promotion_to_product_data,
    get_active_product_promotion_map,
    get_active_promotions_for_store,
    serialize_public_promotion,
)
from app.services.tienda_promociones_public import store_promotion_catalog_type
from app.services.tienda_scope import public_product_query
from app.utils.tienda_urls import build_product_public_path


WEB_BOT_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'obtener_fecha_hora_actual',
            'description': 'Devuelve la fecha y hora actual exacta de la tienda según la zona horaria configurada.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_calendario_relativo',
            'description': 'Resuelve fechas relativas como hoy, mañana, pasado mañana o este fin de semana.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'referencia': {
                        'type': 'string',
                        'enum': ['hoy', 'mañana', 'pasado_mañana', 'ayer', 'este_fin_de_semana'],
                    },
                },
                'required': ['referencia'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_estado_tienda_actual',
            'description': 'Indica si la tienda está abierta o cerrada y cuál es el horario aplicable hoy u otra fecha cercana.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'referencia': {
                        'type': 'string',
                        'enum': ['ahora', 'hoy', 'mañana', 'pasado_mañana'],
                    },
                    'fecha': {'type': 'string', 'description': 'Fecha opcional en formato YYYY-MM-DD.'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_info_contacto_actual',
            'description': 'Devuelve medios de contacto públicos vigentes como WhatsApp, teléfono, email, dirección, web o redes.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'canal': {
                        'type': 'string',
                        'enum': ['todos', 'whatsapp', 'telefono', 'email', 'direccion', 'sitio_web', 'redes'],
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_stock_preciso_producto',
            'description': 'Consulta stock real y disponibilidad de uno o varios productos publicados de la tienda.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'busqueda': {'type': 'string', 'description': 'Nombre, modelo o marca del producto.'},
                },
                'required': ['busqueda'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_precio_preciso_producto',
            'description': 'Consulta precio exacto, promociones vigentes y precio anterior de productos publicados.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'busqueda': {'type': 'string', 'description': 'Nombre, modelo o marca del producto.'},
                },
                'required': ['busqueda'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_metodos_pago_vigentes',
            'description': 'Devuelve los métodos de pago vigentes informados por la tienda.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_envio_estimado',
            'description': 'Devuelve información vigente de envíos, cobertura y zonas de entrega; admite filtrar por zona.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'zona': {'type': 'string', 'description': 'Zona o ciudad consultada por la persona.'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_contexto_temporal_local',
            'description': 'Resume contexto temporal local: fecha, día, fin de semana y horario de tienda para una referencia cercana.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'referencia': {
                        'type': 'string',
                        'enum': ['hoy', 'mañana', 'pasado_mañana'],
                    },
                    'fecha': {'type': 'string', 'description': 'Fecha opcional en formato YYYY-MM-DD.'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_politicas_publicas',
            'description': 'Devuelve políticas públicas vigentes de garantía, cambios, retiro, envíos o cobertura.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'tema': {
                        'type': 'string',
                        'enum': ['garantia', 'politica_cambios', 'retiro_local', 'envios', 'cobertura', 'todos'],
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'buscar_productos_tienda',
            'description': (
                'Busca productos publicados en la tienda pública actual. '
                'Sirve para precios, disponibilidad, sugerencias y alternativas.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'busqueda': {'type': 'string', 'description': 'Nombre, marca, modelo o tipo de producto.'},
                    'categoria': {'type': 'string', 'description': 'Categoría opcional como celulares, accesorios o repuestos.'},
                    'orden': {
                        'type': 'string',
                        'enum': ['relevancia', 'precio_menor', 'precio_mayor'],
                        'description': 'Orden sugerido según la consulta.',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'obtener_info_tienda',
            'description': 'Devuelve información comercial de la tienda como horarios, pagos, garantía, envíos o ubicación.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'tema': {
                        'type': 'string',
                        'enum': ['horarios', 'ubicacion', 'garantia', 'metodos_pago', 'contacto', 'zonas_de_entrega', 'politica_cambios', 'envios', 'retiro_local', 'cobertura', 'todos'],
                        'description': 'Tema puntual solicitado por la persona.',
                    },
                },
                'required': ['tema'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'listar_promociones_activas',
            'description': 'Devuelve promociones activas, descuentos vigentes y productos alcanzados.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'busqueda': {
                        'type': 'string',
                        'description': 'Filtro opcional por nombre de promoción o nombre de producto.',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'solicitar_handoff_whatsapp',
            'description': 'Marca que conviene continuar la conversación por WhatsApp.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'motivo': {'type': 'string', 'description': 'Motivo breve del handoff.'},
                },
                'required': ['motivo'],
            },
        },
    },
]


SEARCH_STOPWORDS = {
    'a', 'al', 'con', 'cual', 'cuales', 'cuanto', 'cuantos', 'cuesta', 'cuestan',
    'de', 'del', 'el', 'en', 'hay', 'la', 'las', 'lo', 'los', 'me', 'mostrar',
    'mostrame', 'necesito', 'para', 'que', 'queria', 'quiero', 'tienen', 'tenes',
    'tiene', 'un', 'una', 'uno', 'unas', 'unos', 'ver',
}


def _decimal_to_price(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if value in (None, ''):
        return 0.0
    return float(value)


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    without_marks = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_marks.lower().strip()


def _extract_search_terms(value: str) -> list[str]:
    tokens = re.findall(r'[a-z0-9]+', _normalize_search_text(value))
    terms = []
    seen = set()
    for token in tokens:
        if len(token) < 2 or token in SEARCH_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _serialize_product(producto: Producto, slug: str) -> dict:
    return {
        'id': producto.id_producto,
        'nombre': producto.nombre,
        'precio': _decimal_to_price(producto.precio_venta),
        'disponible': bool((producto.stock_actual or 0) > 0),
        'marca': producto.marca or '',
        'modelo': producto.modelo or '',
        'categoria': producto.categoria.nombre if producto.categoria else '',
        'url': build_product_public_path(slug, producto.id_producto, producto.nombre),
        'promocion_activa': None,
    }


def _build_query(config, busqueda: str, categoria: str):
    query = public_product_query(config).outerjoin(Categoria)
    categoria_norm = _normalize_search_text(categoria)
    if categoria_norm:
        query = query.filter(Categoria.nombre.ilike(f'%{categoria_norm}%'))

    terms = _extract_search_terms(busqueda)
    if terms:
        conditions = []
        for term in terms:
            pattern = f'%{term}%'
            conditions.extend([
                Producto.nombre.ilike(pattern),
                Producto.marca.ilike(pattern),
                Producto.modelo.ilike(pattern),
                Producto.descripcion_tienda.ilike(pattern),
                Producto.descripcion.ilike(pattern),
                Categoria.nombre.ilike(pattern),
            ])
        query = query.filter(db.or_(*conditions))
    elif (busqueda or '').strip():
        pattern = f"%{_normalize_search_text(busqueda.strip())}%"
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(pattern),
                Producto.marca.ilike(pattern),
                Producto.modelo.ilike(pattern),
                Producto.descripcion_tienda.ilike(pattern),
                Producto.descripcion.ilike(pattern),
                Categoria.nombre.ilike(pattern),
            )
        )
    return query.distinct()


def _handle_buscar_productos_tienda(args: dict, contexto: dict) -> dict:
    config = contexto['config']
    slug = contexto['slug']
    busqueda = (args.get('busqueda') or '').strip()
    categoria = (args.get('categoria') or '').strip()
    orden = (args.get('orden') or 'relevancia').strip().lower()

    query = _build_query(config, busqueda, categoria)
    if orden == 'precio_menor':
        query = query.order_by(Producto.precio_venta.asc(), Producto.nombre.asc())
    elif orden == 'precio_mayor':
        query = query.order_by(Producto.precio_venta.desc(), Producto.nombre.asc())
    else:
        query = query.order_by(Producto.es_destacado_tienda.desc(), Producto.vistas_tienda.desc(), Producto.nombre.asc())

    productos = query.limit(6).all()
    fallback_terms = _extract_search_terms(busqueda)
    if not productos and fallback_terms:
        fallback_conditions = []
        for term in fallback_terms:
            pattern = f'%{term}%'
            fallback_conditions.extend([
                Producto.nombre.ilike(pattern),
                Producto.marca.ilike(pattern),
                Producto.modelo.ilike(pattern),
                Categoria.nombre.ilike(pattern),
            ])
        query = (
            public_product_query(config)
            .outerjoin(Categoria)
            .filter(db.or_(*fallback_conditions))
            .distinct()
            .order_by(Producto.vistas_tienda.desc(), Producto.nombre.asc())
        )
        productos = query.limit(6).all()

    promotion_map = get_active_product_promotion_map(
        int(config.id_cliente),
        [item.id_producto for item in productos],
    )

    return {
        'total': len(productos),
        'productos': [
            attach_promotion_to_product_data(
                item,
                _serialize_product(item, slug),
                promotion_map.get(item.id_producto),
                allow_discount_percentage=True,
            )
            for item in productos
        ],
        'busqueda': busqueda,
        'categoria': categoria,
    }


def _handle_obtener_info_tienda(args: dict, contexto: dict) -> dict:
    assistant_context = contexto['assistant_context']
    faq = assistant_context.get('faq') or {}
    tema = (args.get('tema') or 'todos').strip().lower()
    if tema == 'todos':
        return {'faq': faq}
    return {
        'tema': tema,
        'valor': faq.get(tema) or 'No tenemos ese dato cargado en este momento.',
    }


def _handle_listar_promociones_activas(args: dict, contexto: dict) -> dict:
    config = contexto['config']
    busqueda = _normalize_search_text((args.get('busqueda') or '').strip())
    promociones = get_active_promotions_for_store(config)
    catalog_type = store_promotion_catalog_type(config)
    resultados = []
    for promotion in promociones:
        serialized = serialize_public_promotion(promotion, include_products=True, catalog_type=catalog_type)
        hay_match = not busqueda
        if busqueda:
            candidate_texts = [
                promotion.nombre,
                promotion.descripcion_corta,
                ' '.join(product.get('nombre', '') for product in serialized['productos']),
            ]
            hay_match = any(busqueda in _normalize_search_text(text) for text in candidate_texts if text)
        if hay_match:
            resultados.append(serialized)

    return {
        'total': len(resultados),
        'promociones': resultados[:8],
    }


def _handle_solicitar_handoff_whatsapp(args: dict, contexto: dict) -> dict:
    motivo = (args.get('motivo') or 'Solicitud del visitante').strip()
    return {
        'solicitar_handoff': True,
        'canal_destino': 'whatsapp',
        'motivo': motivo,
        'telefono_disponible': bool((contexto['config'].telefono_whatsapp or '').strip()),
    }


_HANDLERS = {
    'obtener_fecha_hora_actual': obtener_fecha_hora_actual,
    'obtener_calendario_relativo': obtener_calendario_relativo,
    'obtener_estado_tienda_actual': obtener_estado_tienda_actual,
    'obtener_info_contacto_actual': obtener_info_contacto_actual,
    'obtener_stock_preciso_producto': obtener_stock_preciso_producto,
    'obtener_precio_preciso_producto': obtener_precio_preciso_producto,
    'obtener_metodos_pago_vigentes': obtener_metodos_pago_vigentes,
    'obtener_envio_estimado': obtener_envio_estimado,
    'obtener_contexto_temporal_local': obtener_contexto_temporal_local,
    'obtener_politicas_publicas': obtener_politicas_publicas,
    'buscar_productos_tienda': _handle_buscar_productos_tienda,
    'obtener_info_tienda': _handle_obtener_info_tienda,
    'listar_promociones_activas': _handle_listar_promociones_activas,
    'solicitar_handoff_whatsapp': _handle_solicitar_handoff_whatsapp,
}


def execute_web_tool(nombre: str, argumentos: dict, contexto: dict) -> dict:
    handler = _HANDLERS.get(nombre)
    if not handler:
        return {'error': f'Tool desconocido: {nombre}'}
    try:
        return handler(argumentos or {}, contexto)
    except Exception as exc:
        return {'error': 'tool_error', 'detalle': str(exc)}
