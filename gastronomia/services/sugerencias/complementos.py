"""Complementos del menú para arrancar sin historial ni reglas cargadas."""
from gastronomia.services.sugerencias.afinidad import todas_las_palabras
from gastronomia.services.sugerencias.complementos_datos import (
    ALIAS, ACOMPANAN, GRUPOS, ETIQUETAS, ALCOHOL, COMBOS,
)


# Una sola normalización, compartida con la afinidad existente.
_PREFIJOS = sorted(((tuple(todas_las_palabras(alias)), tipo)
                    for tipo, aliases in ALIAS.items() for alias in aliases),
                   key=lambda fila: -len(fila[0]))


def _tipo(tokens):
    for prefijo, tipo in _PREFIJOS:
        if tuple(tokens[:len(prefijo)]) == prefijo:
            return tipo
    return None


def _incluidos(tokens):
    """Solo lo explícito tras 'con', '+', 'incluye' o 'sin'; nunca ingredientes adivinados.

    'Sin papas' tampoco pide papas. Leche/cheddar no se consideran otra bebida/comida.
    """
    incluidos = set()
    for i, token in enumerate(tokens):
        if token not in {'con', 'incluye', 'incluido', 'incluidos', 'sin'}:
            continue
        for posicion in range(i + 1, len(tokens)):
            if tokens[posicion] in {'bebida', 'bebidas', 'guarnicion', 'guarniciones'}:
                incluidos.add('bebida' if tokens[posicion].startswith('bebida') else 'guarnicion')
            tipo = _tipo(tokens[posicion:])
            if tipo:
                incluidos.add(tipo)
    return incluidos


class Complementos:
    def __init__(self, productos, categorias, carrito):
        self.tipos, self.incluidos, self.combos = {}, {}, set()
        for p in productos.values():
            nombre = todas_las_palabras(p.nombre.replace('+', ' con '))
            categoria = todas_las_palabras(categorias.get(p.categoria_id, ''))
            if set(nombre + categoria) & COMBOS:
                # El combo armado por el sistema no conserva una relación de ítems
                # consultable aquí. Es más seguro no inventar lo que le falta.
                self.combos.add(p.id_producto)
                continue
            if set(nombre + categoria) & ALCOHOL:
                continue
            tipo = _tipo(nombre) or _tipo(categoria)
            if tipo is None and categoria in (['bebidas', 'con', 'gas'], ['bebidas', 'gaseosas']):
                tipo = 'gaseosa'
            self.tipos[p.id_producto] = tipo
            descripcion = todas_las_palabras(p.descripcion)
            # La descripción solo aporta inclusiones cuando las declara como tales;
            # una lista de ingredientes no define el tipo del producto.
            declarados = set()
            for i, palabra in enumerate(descripcion):
                if palabra in {'incluye', 'incluido', 'incluidos'}:
                    declarados |= _incluidos(descripcion[i:])
            self.incluidos[p.id_producto] = _incluidos(nombre) | declarados
        self.grupos_carrito = {
            GRUPOS.get(t, t) for numero in carrito
            for t in ({self.tipos.get(numero)} | self.incluidos.get(numero, set())) if t
        }
        # Un combo en el pedido puede traer bebida/guarnición sin decirlo en el
        # nombre. No se añaden complementos de fábrica a ese carrito.
        self.carrito_con_combo = bool(set(carrito) & self.combos)
        self.productos = productos

    def para(self, origen):
        if self.carrito_con_combo:
            return
        tipo_origen = self.tipos.get(origen.id_producto)
        for prioridad, tipo in enumerate(ACOMPANAN.get(tipo_origen, ())):
            if GRUPOS.get(tipo, tipo) in self.grupos_carrito:
                continue
            for p in self.productos.values():
                if self.tipos.get(p.id_producto) != tipo:
                    continue
                # No ofrecer, por ejemplo, 'Papas con hamburguesa' como guarnición
                # ni 'Café con medialuna' como una bebida sola.
                if self.incluidos.get(p.id_producto, set()) - {tipo}:
                    continue
                yield p, prioridad, f'Complemento habitual para {ETIQUETAS[tipo_origen]}'
