"""Plantillas de arranque del menu por rubro.

Solo traen nombres sugeridos: el precio siempre lo carga el usuario.
`promo` es opcional: una promo por cantidad (lleva/paga) que se crea pausada.
`removibles` y `adicionales` usan el mismo formato de texto que el formulario
de producto ("nombre" o "nombre | precio", uno por linea).
"""

BEBIDAS = {
    'nombre': 'Bebidas',
    'productos': [
        {'nombre': 'Gaseosa 500 ml'},
        {'nombre': 'Gaseosa 1,5 L'},
        {'nombre': 'Agua mineral sin gas'},
        {'nombre': 'Agua mineral con gas'},
        {'nombre': 'Jugo natural'},
        {'nombre': 'Cerveza lata'},
    ],
}

PLANTILLAS = {
    'hamburgueseria': {
        'nombre': 'Hamburgueseria',
        'icono': 'fa-hamburger',
        'promo': {'producto': 'Hamburguesa clasica', 'lleva': 2, 'paga': 1},
        'categorias': [
            {
                'nombre': 'Hamburguesas',
                'productos': [
                    {
                        'nombre': 'Hamburguesa clasica',
                        'removibles': 'lechuga\ntomate\ncebolla',
                        'adicionales': 'carne extra | 8000\nqueso extra | 3000\nhuevo | 3000',
                    },
                    {
                        'nombre': 'Hamburguesa doble',
                        'removibles': 'lechuga\ntomate\ncebolla',
                        'adicionales': 'queso extra | 3000\nhuevo | 3000',
                    },
                    {'nombre': 'Hamburguesa con panceta', 'removibles': 'lechuga\ntomate'},
                    {'nombre': 'Hamburguesa de pollo', 'removibles': 'lechuga\ntomate'},
                ],
            },
            {
                'nombre': 'Acompanamientos',
                'productos': [
                    {'nombre': 'Papas fritas'},
                    {'nombre': 'Papas con cheddar'},
                    {'nombre': 'Aros de cebolla'},
                ],
            },
            BEBIDAS,
        ],
    },
    'pizzeria': {
        'nombre': 'Pizzeria',
        'icono': 'fa-pizza-slice',
        'promo': {'producto': 'Pizza muzzarella', 'lleva': 2, 'paga': 1},
        'categorias': [
            {
                'nombre': 'Pizzas',
                'productos': [
                    {'nombre': 'Pizza muzzarella', 'adicionales': 'borde relleno | 10000\nqueso extra | 5000'},
                    {'nombre': 'Pizza napolitana', 'adicionales': 'queso extra | 5000'},
                    {'nombre': 'Pizza de pepperoni', 'adicionales': 'queso extra | 5000'},
                    {'nombre': 'Pizza cuatro quesos'},
                    {'nombre': 'Pizza de jamon y morron', 'removibles': 'morron'},
                ],
            },
            {
                'nombre': 'Empanadas',
                'productos': [
                    {'nombre': 'Empanada de carne'},
                    {'nombre': 'Empanada de pollo'},
                    {'nombre': 'Empanada de jamon y queso'},
                ],
            },
            BEBIDAS,
        ],
    },
    'lomiteria': {
        'nombre': 'Lomiteria',
        'icono': 'fa-bread-slice',
        'categorias': [
            {
                'nombre': 'Lomitos',
                'productos': [
                    {
                        'nombre': 'Lomito arabe de carne',
                        'removibles': 'cebolla\ntomate\nlechuga',
                        'adicionales': 'queso | 3000\nhuevo | 3000',
                    },
                    {'nombre': 'Lomito arabe de pollo', 'removibles': 'cebolla\ntomate\nlechuga'},
                    {
                        'nombre': 'Lomito completo',
                        'removibles': 'huevo\njamon\nqueso\nlechuga\ntomate',
                        'adicionales': 'carne extra | 8000',
                    },
                ],
            },
            {
                'nombre': 'Minutas',
                'productos': [
                    {'nombre': 'Milanesa con papas'},
                    {'nombre': 'Milanesa napolitana'},
                    {'nombre': 'Papas fritas'},
                ],
            },
            BEBIDAS,
        ],
    },
    'cafeteria': {
        'nombre': 'Cafeteria',
        'icono': 'fa-mug-hot',
        'categorias': [
            {
                'nombre': 'Cafes',
                'productos': [
                    {'nombre': 'Cafe', 'adicionales': 'leche vegetal | 3000\nshot extra | 4000'},
                    {'nombre': 'Cafe con leche', 'adicionales': 'leche vegetal | 3000'},
                    {'nombre': 'Capuchino', 'adicionales': 'leche vegetal | 3000'},
                    {'nombre': 'Cocido'},
                ],
            },
            {
                'nombre': 'Para acompanar',
                'productos': [
                    {'nombre': 'Chipa'},
                    {'nombre': 'Medialuna'},
                    {'nombre': 'Tostado de jamon y queso'},
                    {'nombre': 'Porcion de torta'},
                ],
            },
            BEBIDAS,
        ],
    },
    'restaurante': {
        'nombre': 'Restaurante',
        'icono': 'fa-utensils',
        'categorias': [
            {
                'nombre': 'Entradas',
                'productos': [
                    {'nombre': 'Empanadas surtidas'},
                    {'nombre': 'Provoleta'},
                ],
            },
            {
                'nombre': 'Platos principales',
                'productos': [
                    {'nombre': 'Milanesa con guarnicion'},
                    {'nombre': 'Pollo a la plancha'},
                    {'nombre': 'Bife con guarnicion'},
                    {'nombre': 'Pasta del dia'},
                ],
            },
            {
                'nombre': 'Postres',
                'productos': [
                    {'nombre': 'Flan casero'},
                    {'nombre': 'Helado'},
                ],
            },
            BEBIDAS,
        ],
    },
    'bar': {
        'nombre': 'Bar',
        'icono': 'fa-glass-martini-alt',
        'categorias': [
            {
                'nombre': 'Cervezas',
                'productos': [
                    {'nombre': 'Cerveza 1 L'},
                    {'nombre': 'Cerveza lata'},
                    {'nombre': 'Balde de cervezas'},
                ],
            },
            {
                'nombre': 'Tragos',
                'productos': [
                    {'nombre': 'Caipirinha'},
                    {'nombre': 'Fernet con cola'},
                    {'nombre': 'Gin tonic'},
                ],
            },
            {
                'nombre': 'Picadas',
                'productos': [
                    {'nombre': 'Picada para 2'},
                    {'nombre': 'Papas fritas'},
                ],
            },
        ],
    },
}
