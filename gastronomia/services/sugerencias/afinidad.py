"""Afinidad por nombre y regla de conflicto (docs/sugerencias_venta.md §5).

La afinidad sirve para ORDENAR: compartir "A54" no garantiza que el producto
sirva. Lo que evita la funda equivocada es la regla de conflicto: un candidato
se descarta si tiene una palabra que aparece en OTRO producto de la categoria
del origen y no en el origen ("iphone" en celulares, para un Samsung A54).
"""
from __future__ import annotations

import math
import re
import unicodedata

# Palabras que nunca distinguen nada.
_VACIAS = frozenset((
    'de', 'del', 'la', 'el', 'los', 'las', 'y', 'e', 'o', 'con', 'para', 'por',
    'en', 'x', 'un', 'una', 'sin', 'al', 'a',
))
# Una palabra que esta en mas de esta fraccion del catalogo es generica. En un
# catalogo chico la fraccion sola marcaria todo como generico ("iphone" en 2 de
# 5 productos): hace falta ademas estar en mas de PRODUCTOS_MINIMOS_GENERICA.
FRACCION_GENERICA = 0.3
PRODUCTOS_MINIMOS_GENERICA = 3

_UNIR_GUION = re.compile(r'(?<=[a-z0-9])[-.](?=[a-z0-9])')
_SEPARADOR = re.compile(r'[^a-z0-9]+')


def todas_las_palabras(nombre: str | None) -> list[str]:
    """Como `palabras`, pero sin sacar "de", "con", "para"... (hacen falta para leer "X con Y")."""
    texto = unicodedata.normalize('NFKD', str(nombre or '').lower())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = _UNIR_GUION.sub('', texto)
    return [p for p in _SEPARADOR.split(texto) if p]


def palabras(nombre: str | None) -> list[str]:
    """Palabras normalizadas, en orden: sin tildes, minusculas, "A-54" -> "a54"."""
    return [p for p in todas_las_palabras(nombre) if p not in _VACIAS]


def tipo(nombre: str | None) -> str | None:
    """Primera palabra significativa (no numerica): "Labial mate rojo" -> "labial"."""
    for palabra in palabras(nombre):
        if not palabra.isdigit():
            return palabra
    return None


class Catalogo:
    """Palabras de los productos activos, con su peso y su categoria."""

    def __init__(self, productos):
        # productos: iterable de (id_producto, nombre, id_categoria)
        self.palabras_por_producto: dict[int, frozenset[str]] = {}
        self.categoria_por_producto: dict[int, int] = {}
        self._productos_por_categoria: dict[int, list[int]] = {}
        frecuencia: dict[str, int] = {}
        for id_producto, nombre, id_categoria in productos:
            conjunto = frozenset(palabras(nombre))
            self.palabras_por_producto[id_producto] = conjunto
            self.categoria_por_producto[id_producto] = id_categoria
            self._productos_por_categoria.setdefault(id_categoria, []).append(id_producto)
            for palabra in conjunto:
                frecuencia[palabra] = frecuencia.get(palabra, 0) + 1
        self.total = max(1, len(self.palabras_por_producto))
        self._peso = {p: math.log(self.total / n) for p, n in frecuencia.items()}
        limite = max(PRODUCTOS_MINIMOS_GENERICA, FRACCION_GENERICA * self.total)
        self._genericas = frozenset(p for p, n in frecuencia.items() if n > limite)
        self._palabras_de_categoria: dict[int, dict[str, int]] = {}

    def peso(self, palabra: str) -> float:
        return self._peso.get(palabra, 0.0)

    def distintivas(self, id_producto: int) -> frozenset[str]:
        return frozenset(
            p for p in self.palabras_por_producto.get(id_producto, ()) if p not in self._genericas
        )

    def afinidad(self, id_a: int, id_b: int) -> tuple[float, list[str]]:
        """Suma de pesos de las palabras distintivas compartidas, y cuales son."""
        compartidas = sorted(self.distintivas(id_a) & self.distintivas(id_b))
        return sum(self.peso(p) for p in compartidas), compartidas

    def _palabras_categoria(self, id_categoria: int) -> dict[str, int]:
        """Palabra -> en cuantos productos de la categoria aparece."""
        if id_categoria not in self._palabras_de_categoria:
            conteo: dict[str, int] = {}
            for id_producto in self._productos_por_categoria.get(id_categoria, ()):
                for palabra in self.distintivas(id_producto):
                    conteo[palabra] = conteo.get(palabra, 0) + 1
            self._palabras_de_categoria[id_categoria] = conteo
        return self._palabras_de_categoria[id_categoria]

    def conflicto(self, id_origen: int, id_candidato: int, ignorar=frozenset()) -> str | None:
        """Palabra que ata al candidato a OTRO producto de la categoria del origen.

        Devuelve la palabra (para mostrar el motivo del descarte) o None.
        `ignorar`: palabras que no atan a nadie (el tipo del candidato en los
        complementos: "guampa" en "Guampa de toro" no lo ata a "Termo con guampa").
        """
        categoria = self.categoria_por_producto.get(id_origen)
        if categoria is None:
            return None
        propias = self.palabras_por_producto.get(id_origen, frozenset())
        de_la_categoria = self._palabras_categoria(categoria)
        # Si el candidato es de la misma categoria, sus propias palabras ya
        # estan contadas ahi una vez: no lo atan a nadie.
        propio_conteo = 1 if self.categoria_por_producto.get(id_candidato) == categoria else 0
        for palabra in sorted(self.distintivas(id_candidato)):
            if palabra in propias or palabra in ignorar:
                continue
            # Aparece en otro producto de la categoria origen (ni el origen ni el candidato).
            if de_la_categoria.get(palabra, 0) > propio_conteo:
                return palabra
        return None
