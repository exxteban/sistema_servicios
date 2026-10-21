"""Carga un menu de heladeria para demos: presentaciones, sabores con imagen y adicionales.

Uso (desde la raiz del repo, con el mismo env que el servicio):
    python scripts/demo_heladeria.py                 # usa el unico cliente con gastronomia activa
    python scripts/demo_heladeria.py --cliente-id 3
    python scripts/demo_heladeria.py --sin-imagenes

Se puede correr varias veces: actualiza por nombre lo que ya existe y no borra nada.
"""
from demo_heladeria_imagenes import dibujar_presentacion, dibujar_sabor
from demo_menu_utils import asegurar_categoria, ejecutar, guardar_grupo_demo, guardar_producto_demo

CATEGORIA = 'Helados'
GRUPO_SABORES = 'Sabores'
ADICIONALES = 'Baño de chocolate | 3000\nSalsa de dulce de leche | 2000\nConfites de colores | 3000\nCucurucho bañado | 2000'

# topping: chips (trozos), frutas (pedacitos), copos (coco/almendra), remolino (veteado).
SABORES = [
    {'nombre': 'Dulce de leche', 'color': '#C68A4E'},
    {'nombre': 'Dulce de leche granizado', 'color': '#C68A4E', 'topping': 'chips', 'topping_color': '#3B2314'},
    {'nombre': 'Super dulce de leche', 'color': '#A86B32', 'topping': 'remolino', 'topping_color': '#6B3E1D'},
    {'nombre': 'Dulce de leche con nuez', 'color': '#C68A4E', 'topping': 'chips', 'topping_color': '#7A5230'},
    {'nombre': 'Chocolate', 'color': '#5A3825'},
    {'nombre': 'Chocolate amargo', 'color': '#3B2316'},
    {'nombre': 'Chocolate con almendras', 'color': '#5A3825', 'topping': 'copos', 'topping_color': '#E8D3A9'},
    {'nombre': 'Chocolate blanco', 'color': '#F3E9D2'},
    {'nombre': 'Vainilla', 'color': '#F3E5AB'},
    {'nombre': 'Americana', 'color': '#FFF5DD'},
    {'nombre': 'Crema del cielo', 'color': '#9FD8F0'},
    {'nombre': 'Granizado', 'color': '#FFF5DD', 'topping': 'chips', 'topping_color': '#2B1A10'},
    {'nombre': 'Tramontana', 'color': '#F6EAD0', 'topping': 'chips', 'topping_color': '#3B2314'},
    {'nombre': 'Sambayón', 'color': '#F2D16B'},
    {'nombre': 'Tiramisú', 'color': '#D9B99B', 'topping': 'chips', 'topping_color': '#4A2C1A'},
    {'nombre': 'Café', 'color': '#8B5E3C'},
    {'nombre': 'Menta granizada', 'color': '#B8E6C9', 'topping': 'chips', 'topping_color': '#2B1A10'},
    {'nombre': 'Cookies', 'color': '#EDE6DA', 'topping': 'chips', 'topping_color': '#2B2B2B'},
    {'nombre': 'Pistacho', 'color': '#B5C98E'},
    {'nombre': 'Coco', 'color': '#FBF7EE', 'topping': 'copos', 'topping_color': '#D8CBB0'},
    {'nombre': 'Banana split', 'color': '#F7E7A1', 'topping': 'remolino', 'topping_color': '#5A3825'},
    {'nombre': 'Frutilla a la crema', 'color': '#F4A6B7', 'topping': 'frutas', 'topping_color': '#C8102E'},
    {'nombre': 'Mascarpone con frutos rojos', 'color': '#FAF0F0', 'topping': 'remolino', 'topping_color': '#8E1B3A'},
    {'nombre': 'Cheesecake de maracuyá', 'color': '#FFF1C9', 'topping': 'remolino', 'topping_color': '#F2B705'},
    {'nombre': 'Mburucuyá', 'color': '#F5C342', 'topping': 'frutas', 'topping_color': '#3A2A12'},
    {'nombre': 'Limón', 'color': '#F6F2A8'},
    {'nombre': 'Frutilla al agua', 'color': '#E8435A'},
    {'nombre': 'Naranja', 'color': '#F7A440'},
    {'nombre': 'Durazno', 'color': '#F8B88B'},
    {'nombre': 'Ananá', 'color': '#F7DC6F', 'topping': 'frutas', 'topping_color': '#E0B83A'},
    {'nombre': 'Frutos del bosque', 'color': '#7B2D5B', 'topping': 'frutas', 'topping_color': '#3E0F2C'},
]

# forma: cono | vaso | pote (solo cambia el dibujo).
PRESENTACIONES = [
    {'nombre': 'Cucurucho 1 bocha', 'precio': 8000, 'max_sabores': 1, 'forma': 'cono'},
    {'nombre': 'Cucurucho 2 bochas', 'precio': 13000, 'max_sabores': 2, 'forma': 'cono'},
    {'nombre': 'Vasito 2 bochas', 'precio': 13000, 'max_sabores': 2, 'forma': 'vaso'},
    {'nombre': 'Vasito 3 bochas', 'precio': 17000, 'max_sabores': 3, 'forma': 'vaso'},
    {'nombre': 'Pote 1/4 kg', 'precio': 22000, 'max_sabores': 3, 'forma': 'pote'},
    {'nombre': 'Pote 1/2 kg', 'precio': 40000, 'max_sabores': 4, 'forma': 'pote'},
    {'nombre': 'Pote 1 kg', 'precio': 75000, 'max_sabores': 4, 'forma': 'pote'},
]


def _cargar(cliente_id, imagen):
    from gastronomia.services.modificadores_service import sincronizar_adicionales_precio

    sabores = [
        {'nombre': sabor['nombre'], 'imagen_url': imagen('helado', sabor['nombre'], lambda ruta, s=sabor: dibujar_sabor(s, ruta))}
        for sabor in SABORES
    ]
    categoria = asegurar_categoria(cliente_id, CATEGORIA, 5)
    for orden, presentacion in enumerate(PRESENTACIONES):
        maximo = presentacion['max_sabores']
        muestra = SABORES[orden * 3 % len(SABORES):][:maximo] or SABORES[:1]
        imagen_url = imagen('helado', presentacion['nombre'],
                            lambda ruta, p=presentacion, m=muestra: dibujar_presentacion(p, m, ruta))
        producto = guardar_producto_demo(cliente_id, categoria, {
            'nombre': presentacion['nombre'],
            'descripcion': f'Hasta {maximo} sabor{"es" if maximo > 1 else ""} a elección.',
            'precio': presentacion['precio'],
            'imagen_url': imagen_url,
            'orden': orden * 10,
        })
        guardar_grupo_demo(cliente_id, producto, {
            'nombre': GRUPO_SABORES, 'tipo': 'variante', 'obligatorio': True,
            'min_selecciones': 1, 'max_selecciones': maximo, 'orden': -120,  # antes que los adicionales (-90)
        }, sabores)
        sincronizar_adicionales_precio(cliente_id, producto.id_producto, ADICIONALES)
        print(f'  {producto.nombre}: hasta {maximo} de {len(SABORES)} sabores')
    print(f'Listo: cliente {cliente_id}, categoria "{CATEGORIA}", {len(PRESENTACIONES)} presentaciones.')


if __name__ == '__main__':
    ejecutar(__doc__.splitlines()[0], _cargar)
