"""Base comun para los dibujos de los menus de demo (lienzo, colores y guardado).

Se dibuja al doble de tamano y se reduce al guardar para suavizar los bordes.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

LADO = 480
ESCALA = 2


def rgb(hex_color: str) -> tuple[int, int, int]:
    valor = hex_color.lstrip('#')
    return tuple(int(valor[i:i + 2], 16) for i in (0, 2, 4))


def mezclar(color: str, otro: str, peso: float) -> tuple[int, int, int]:
    a, b = rgb(color), rgb(otro)
    return tuple(round(x + (y - x) * peso) for x, y in zip(a, b))


def lienzo(color_fondo: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    fondo = mezclar(color_fondo, '#FFFFFF', 0.82)
    img = Image.new('RGB', (LADO * ESCALA, LADO * ESCALA), fondo)
    return img, ImageDraw.Draw(img, 'RGBA')


def guardar(img: Image.Image, ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    img.resize((LADO, LADO), Image.LANCZOS).save(ruta, 'WEBP', quality=88)
