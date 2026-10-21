"""Carga un menu de cafeteria para demos: bebidas con imagen, tamanos, tipo de leche y extras.

Uso (desde la raiz del repo, con el mismo env que el servicio):
    python scripts/demo_cafeteria.py                 # usa el unico cliente con gastronomia activa
    python scripts/demo_cafeteria.py --cliente-id 3
    python scripts/demo_cafeteria.py --sin-imagenes

Se puede correr varias veces: actualiza por nombre y no borra nada. Si un producto con el
mismo nombre ya existia, conserva su precio (solo suma imagen, opciones y categoria).
"""
from demo_cafeteria_imagenes import dibujar_taza, dibujar_vaso
from demo_menu_utils import asegurar_categoria, ejecutar, guardar_grupo_demo, guardar_producto_demo

CATEGORIA = 'Cafes'
EXTRAS = 'Shot extra de café | 4000\nCrema batida | 3000\nJarabe de vainilla | 3000\nJarabe de caramelo | 3000\nCanela | 0'
TAMANOS = [('Chico', 0, 0.78), ('Mediano', 3000, 0.92), ('Grande', 5000, 1.06)]
# Los adicionales usan orden -90: tamano y leche van antes en el POS.
ORDEN_TAMANO = -120
LECHES = [('Entera', 0), ('Descremada', 0), ('Deslactosada', 0), ('De almendras', 4000)]

CAFE = '#3B2314'
CREMA = '#C88A4A'
LECHE = '#F6EFE4'
ESPUMA = '#FBF4EA'
CHOCOLATE = '#5A3420'

# tamanos / leche: si la bebida ofrece esos grupos. El resto describe el dibujo.
BEBIDAS = [
    {'nombre': 'Espresso', 'precio': 9000, 'forma': 'taza', 'escala': 0.8, 'liquido': CAFE, 'superficie': CREMA},
    {'nombre': 'Espresso doble', 'precio': 12000, 'forma': 'taza', 'escala': 0.9, 'liquido': CAFE, 'superficie': CREMA},
    {'nombre': 'Americano', 'precio': 11000, 'forma': 'taza', 'tamanos': True, 'liquido': '#2A170C', 'superficie': '#6B4428'},
    {'nombre': 'Cortado', 'precio': 12000, 'forma': 'vaso', 'leche': True,
     'capas': [(CAFE, 6), ('#C9A27E', 2)], 'tope': 'espuma'},
    {'nombre': 'Café con leche', 'precio': 13000, 'forma': 'taza', 'tamanos': True, 'leche': True,
     'liquido': '#B98C5E', 'superficie': '#C9A27E'},
    {'nombre': 'Capuccino', 'precio': 15000, 'forma': 'taza', 'tamanos': True, 'leche': True,
     'liquido': '#A87850', 'superficie': ESPUMA, 'arte': 'cacao'},
    {'nombre': 'Latte', 'precio': 16000, 'forma': 'taza', 'tamanos': True, 'leche': True,
     'liquido': '#B8875A', 'superficie': '#C99C70', 'arte': 'corazon'},
    {'nombre': 'Flat white', 'precio': 16000, 'forma': 'taza', 'leche': True,
     'liquido': '#8E5F38', 'superficie': '#A8764C', 'arte': 'corazon'},
    {'nombre': 'Latte macchiato', 'precio': 16000, 'forma': 'vaso', 'tamanos': True, 'leche': True,
     'capas': [(LECHE, 5), ('#A87850', 2), (CAFE, 1)], 'tope': 'espuma'},
    {'nombre': 'Mocaccino', 'precio': 17000, 'forma': 'vaso', 'tamanos': True, 'leche': True,
     'capas': [(CHOCOLATE, 3), (CAFE, 3), ('#B98C5E', 2)], 'tope': 'crema', 'drizzle': CHOCOLATE},
    {'nombre': 'Lágrima', 'precio': 11000, 'forma': 'vaso', 'leche': True,
     'capas': [(LECHE, 8), ('#C9A27E', 1)], 'tope': 'espuma'},
    {'nombre': 'Submarino', 'precio': 15000, 'forma': 'vaso', 'leche': True,
     'capas': [(CHOCOLATE, 2), ('#E8D8C3', 7)], 'tope': 'espuma'},
    {'nombre': 'Chocolate caliente', 'precio': 15000, 'forma': 'taza', 'tamanos': True, 'leche': True,
     'liquido': CHOCOLATE, 'superficie': '#6E4128'},
    {'nombre': 'Cocido con leche', 'precio': 9000, 'forma': 'taza', 'tamanos': True, 'leche': True,
     'liquido': '#B07A4A', 'superficie': '#C09062'},
    {'nombre': 'Té', 'precio': 8000, 'forma': 'taza', 'liquido': '#B5651D', 'superficie': '#C8782E'},
    {'nombre': 'Café helado', 'precio': 15000, 'forma': 'vaso', 'tamanos': True, 'leche': True,
     'capas': [('#D9BFA0', 4), ('#8E5F38', 4)], 'hielo': True},
    {'nombre': 'Frappé de café', 'precio': 19000, 'forma': 'vaso', 'tamanos': True, 'leche': True,
     'capas': [('#C9A27E', 7)], 'tope': 'crema', 'drizzle': '#C47A2C'},
    {'nombre': 'Frappé de chocolate', 'precio': 19000, 'forma': 'vaso', 'tamanos': True, 'leche': True,
     'capas': [('#8A5A3C', 7)], 'tope': 'crema', 'drizzle': CHOCOLATE},
    {'nombre': 'Affogato', 'precio': 17000, 'forma': 'vaso', 'capas': [(CAFE, 3), ('#E9D9A8', 4)], 'tope': 'bocha', 'drizzle': CAFE},
]


def _cargar(cliente_id, imagen):
    from gastronomia.services.modificadores_service import sincronizar_adicionales_precio

    taza_modelo = next(b for b in BEBIDAS if b['nombre'] == 'Café con leche')
    tamanos = [
        {'nombre': nombre, 'precio_delta': delta,
         'imagen_url': imagen('cafe_tamano', nombre, lambda ruta, e=escala: dibujar_taza(taza_modelo, ruta, e))}
        for nombre, delta, escala in TAMANOS
    ]
    leches = [{'nombre': nombre, 'precio_delta': delta} for nombre, delta in LECHES]
    categoria = asegurar_categoria(cliente_id, CATEGORIA, 20)
    for orden, bebida in enumerate(BEBIDAS):
        dibujar = dibujar_vaso if bebida['forma'] == 'vaso' else (
            lambda b, ruta: dibujar_taza(b, ruta, b.get('escala', 1.0)))
        imagen_url = imagen('cafe', bebida['nombre'], lambda ruta, b=bebida, d=dibujar: d(b, ruta))
        producto = guardar_producto_demo(cliente_id, categoria, {
            'nombre': bebida['nombre'],
            'precio': bebida['precio'],
            'imagen_url': imagen_url,
            'orden': orden * 10,
        }, conservar_precio=True)
        if bebida.get('tamanos'):
            guardar_grupo_demo(cliente_id, producto, {
                'nombre': 'Tamaño', 'tipo': 'variante', 'obligatorio': True,
                'min_selecciones': 1, 'max_selecciones': 1, 'orden': ORDEN_TAMANO,
            }, tamanos)
        if bebida.get('leche'):
            guardar_grupo_demo(cliente_id, producto, {
                'nombre': 'Leche', 'tipo': 'variante', 'obligatorio': False,
                'min_selecciones': 0, 'max_selecciones': 1, 'orden': ORDEN_TAMANO + 1,
            }, leches)
        sincronizar_adicionales_precio(cliente_id, producto.id_producto, EXTRAS)
        print(f'  {producto.nombre}: Gs. {int(producto.precio):,}'.replace(',', '.'))
    print(f'Listo: cliente {cliente_id}, categoria "{CATEGORIA}", {len(BEBIDAS)} bebidas.')


if __name__ == '__main__':
    ejecutar(__doc__.splitlines()[0], _cargar)
