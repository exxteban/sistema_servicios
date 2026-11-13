"""Schemas (formato OpenAI/DeepSeek) de las tools del asistente gastronomico."""


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': properties or {},
                'required': required or [],
            },
        },
    }


_STR = {'type': 'string'}
_NUM = {'type': 'number'}
_BOOL = {'type': 'boolean'}
_PLATO = {'type': 'string', 'description': 'Nombre o id del plato'}

TEMAS_GUIA = [
    'empezar', 'categorias', 'platos', 'menu_cargado', 'plantilla', 'extras', 'recetas', 'insumos',
    'precios_canales', 'promociones', 'pantalla_tv', 'mesas', 'vender', 'caja', 'cocina', 'delivery',
]

TOOLS = [
    _tool(
        'donde_esta', 'Devuelve el camino exacto en pantalla y el enlace real para llegar a una seccion del sistema. '
        'Usala SIEMPRE que pregunten donde/como se hace algo o por donde empezar. Con plato devuelve como encontrarlo en pantalla.',
        {'tema': {'type': 'string', 'enum': TEMAS_GUIA}, 'plato': {'type': 'string', 'description': 'Opcional: nombre o id de plato'}},
        ['tema'],
    ),
    _tool('estado_configuracion', 'Checklist del negocio: cuantas categorias, platos, insumos y mesas hay y que falta (sin precio, sin receta, insumos sin costo, ganancia negativa).'),
    _tool('ver_menu', 'Lista categorias y platos con id, precio y disponibilidad.'),
    _tool('ver_insumos', 'Lista insumos (ingredientes de stock) con unidad, stock y precio de compra.'),
    _tool('ver_plato', 'Detalle de un plato: receta, extras/opciones y costo estimado.', {'plato': _PLATO}, ['plato']),
    _tool(
        'crear_categorias', 'Crea categorias del menu (si ya existe la reutiliza).',
        {'categorias': {'type': 'array', 'items': {'type': 'object', 'properties': {'nombre': _STR, 'descripcion': _STR}, 'required': ['nombre']}}},
        ['categorias'],
    ),
    _tool(
        'guardar_platos', 'Crea o edita platos del menu. Si el nombre ya existe lo actualiza. Precio en moneda local sin separadores.',
        {'platos': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'id_producto': {'type': 'integer', 'description': 'Solo para editar uno existente'},
            'nombre': _STR, 'categoria': {'type': 'string', 'description': 'Nombre o id de categoria existente'},
            'precio': _NUM, 'descripcion': _STR, 'disponible': _BOOL,
        }, 'required': ['nombre']}}},
        ['platos'],
    ),
    _tool(
        'cambiar_estado_plato', 'Cambia precio, disponibilidad (agotado), visibilidad, publicacion en tienda o costo extra fijo (empaque, gas) de un plato.',
        {'plato': _PLATO, 'precio': _NUM, 'disponible': _BOOL, 'visible': _BOOL, 'publicado_tienda': _BOOL, 'costo_extra': _NUM},
        ['plato'],
    ),
    _tool(
        'guardar_insumos', 'Crea insumos de stock o actualiza unidad, stock minimo y precio de compra. Unidades: unidad, porcion, g, ml, mazo. precio_compra es por UNA unidad (ej. por gramo si unidad=g).',
        {'insumos': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'nombre': _STR, 'unidad': {'type': 'string', 'enum': ['unidad', 'porcion', 'g', 'ml', 'mazo']},
            'precio_compra': _NUM, 'stock_minimo': {'type': 'integer'}, 'stock_inicial': {'type': 'integer'},
        }, 'required': ['nombre']}}},
        ['insumos'],
    ),
    _tool(
        'guardar_receta_plato', 'Define la receta COMPLETA de un plato (reemplaza la anterior). Cantidades enteras en la unidad del insumo. Los insumos deben existir.',
        {'plato': _PLATO, 'ingredientes': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'insumo': {'type': 'string', 'description': 'Nombre o id del insumo'}, 'cantidad': _NUM,
        }, 'required': ['insumo', 'cantidad']}}},
        ['plato', 'ingredientes'],
    ),
    _tool(
        'configurar_extras_plato', 'Define adicionales con precio (ej. extra queso) y/o ingredientes que el cliente puede pedir sin (ej. sin cebolla). Cada lista reemplaza la anterior.',
        {'plato': _PLATO,
         'adicionales': {'type': 'array', 'items': {'type': 'object', 'properties': {'nombre': _STR, 'precio': _NUM}, 'required': ['nombre']}},
         'quitables': {'type': 'array', 'items': _STR}},
        ['plato'],
    ),
    _tool(
        'crear_mesas', 'Crea mesas del salon numeradas (ej. Mesa 1..10). Salta nombres ya existentes.',
        {'cantidad': {'type': 'integer'}, 'prefijo': _STR, 'capacidad': {'type': 'integer'},
         'desde_numero': {'type': 'integer'}, 'ubicacion': _STR},
        ['cantidad'],
    ),
]
