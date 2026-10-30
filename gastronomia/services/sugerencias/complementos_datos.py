"""Base inicial gastronómica, sin ventas: relaciones prudentes, nunca sustitutos.

Solo se reconocen nombres/categorías explícitos. Los nombres comerciales de
hamburguesas se reconocen por su categoría. No se adivinan ingredientes,
compatibilidades dietarias ni bebidas alcohólicas. El dueño siempre puede prohibir.
"""

ALIAS = {
    'hamburguesa': ('hamburguesa', 'hamburguesas', 'burger', 'burgers', 'cheeseburger'),
    'sandwich': ('sandwich', 'sandwiches', 'sandiwich', 'lomito', 'lomitos', 'pancho', 'panchos', 'hot dog'),
    'pizza': ('pizza', 'pizzas', 'pizzeta', 'pizzetas'),
    'empanada': ('empanada', 'empanadas'),
    'milanesa': ('milanesa', 'milanesas'),
    'papas': ('papas fritas', 'papa frita', 'papas rusticas', 'papas bravas', 'papas con cheddar',
              'papas', 'french fries', 'fries', 'batatas fritas', 'mandioca frita'),
    'gaseosa': ('gaseosa', 'gaseosas', 'refresco', 'refrescos', 'coca cola', 'cocacola', 'coca',
                'pepsi', 'sprite', 'fanta', '7up', 'seven up', 'mirinda', 'soda', 'agua tonica'),
    'agua': ('agua', 'aguas'),
    'jugo': ('jugo', 'jugos', 'zumo', 'zumos', 'limonada'),
    'cafe': ('cafe', 'cafes', 'espresso', 'expreso', 'americano', 'capuccino', 'capuchino',
             'cappuccino', 'cortado', 'latte', 'flat white', 'mocaccino', 'mocachino',
             'lagrima', 'frappe de cafe', 'affogato'),
    'infusion': ('te', 'cocido', 'mate cocido', 'chocolate caliente', 'submarino'),
    'panificado': ('medialuna', 'medialunas', 'croissant', 'croissants', 'chipa', 'chipas',
                   'tostado', 'tostados', 'alfajor', 'alfajores'),
    'torta': ('torta', 'tortas', 'porcion de torta', 'porciones de torta', 'budin', 'brownie'),
    'helado': ('helado', 'helados', 'cucurucho', 'vasito', 'pote'),
}

# Primero guarnición, después alternativas de bebida. Se conserva una por tipo.
ACOMPANAN = {
    'hamburguesa': ('papas', 'gaseosa', 'agua', 'jugo'),
    'sandwich': ('papas', 'gaseosa', 'agua', 'jugo'),
    'pizza': ('gaseosa', 'agua', 'jugo'),
    'empanada': ('gaseosa', 'agua', 'jugo'),
    'milanesa': ('papas', 'gaseosa', 'agua', 'jugo'),
    'cafe': ('panificado', 'torta'),
    'infusion': ('panificado', 'torta'),
    'panificado': ('cafe', 'infusion'),
    'torta': ('cafe', 'infusion'),
}

GRUPOS = {
    **{t: 'bebida' for t in ('gaseosa', 'agua', 'jugo', 'cafe', 'infusion')},
    'panificado': 'panificado', 'torta': 'panificado', 'papas': 'guarnicion',
}
ETIQUETAS = {
    'hamburguesa': 'hamburguesas', 'sandwich': 'sándwiches', 'pizza': 'pizzas',
    'empanada': 'empanadas', 'milanesa': 'milanesas', 'cafe': 'café',
    'infusion': 'infusiones', 'panificado': 'panificados', 'torta': 'tortas',
}
ALCOHOL = frozenset(('cerveza', 'cervezas', 'vino', 'vinos', 'vodka', 'ron', 'whisky',
                     'fernet', 'licor', 'alcohol', 'coctel', 'cocktail'))
COMBOS = frozenset(('combo', 'combos', 'promo', 'promocion', 'promociones'))
