"""Dibujos simples de bebidas para la demo de cafeteria: tazas y vasos con capas.

Cada bebida se describe con datos (ver `BEBIDAS` en demo_cafeteria.py):
- taza: `liquido`, `superficie` (crema/espuma) y `arte` ('corazon' | 'cacao' | None).
- vaso: `capas` de abajo hacia arriba [(color, proporcion)], `tope` ('crema' | 'espuma' | 'bocha'),
  `hielo` y `drizzle` (hilo de salsa sobre la crema).
"""
from __future__ import annotations

from demo_menu_dibujo import ESCALA, guardar, lienzo, mezclar, rgb

COLOR_TAZA = (250, 249, 246)
COLOR_BORDE = (214, 208, 200)
VASO_ARRIBA = (140, 150, 340)  # y, x izquierda, x derecha
VASO_ABAJO = (440, 168, 312)


def _caja(cx, cy, ancho, alto):
    s = ESCALA
    return [(cx - ancho / 2) * s, (cy - alto / 2) * s, (cx + ancho / 2) * s, (cy + alto / 2) * s]


def dibujar_taza(bebida: dict, ruta: str, escala: float = 1.0) -> None:
    img, draw = lienzo(bebida['liquido'])
    s = ESCALA
    cx, borde_y = 228, 215
    ancho = 330 * escala
    fondo_y = borde_y + 165 * escala
    # Plato y sombra.
    draw.ellipse(_caja(cx + 10, fondo_y + 14, ancho * 1.28, 80 * escala), fill=(0, 0, 0, 30))
    draw.ellipse(_caja(cx, fondo_y + 4, ancho * 1.24, 78 * escala), fill=COLOR_TAZA, outline=COLOR_BORDE, width=2 * s)
    # Asa: anillo con borde a la derecha del cuerpo.
    asa = _caja(cx + ancho / 2, borde_y + 70 * escala, 100 * escala, 90 * escala)
    draw.ellipse(asa, outline=COLOR_BORDE, width=int(26 * escala * s))
    draw.ellipse([asa[0] + 3 * s, asa[1] + 3 * s, asa[2] - 3 * s, asa[3] - 3 * s], outline=COLOR_TAZA, width=int(20 * escala * s))
    # Cuerpo: mitad inferior de una elipse.
    draw.chord(
        [(cx - ancho / 2) * s, (2 * borde_y - fondo_y) * s, (cx + ancho / 2) * s, fondo_y * s],
        0, 180, fill=COLOR_TAZA, outline=COLOR_BORDE, width=2 * s,
    )
    # Boca vista desde arriba en angulo: asi se ven la crema y el arte.
    draw.ellipse(_caja(cx, borde_y, ancho, 120 * escala), fill=COLOR_TAZA, outline=COLOR_BORDE, width=2 * s)
    draw.ellipse(_caja(cx, borde_y + 4, ancho - 30 * escala, 98 * escala), fill=rgb(bebida['liquido']))
    superficie = bebida.get('superficie')
    if superficie:
        draw.ellipse(_caja(cx, borde_y + 4, ancho - 56 * escala, 80 * escala), fill=rgb(superficie))
    _arte(draw, cx, borde_y + 4, escala * 1.5, bebida)
    guardar(img, ruta)


def _arte(draw, cx, cy, escala, bebida) -> None:
    s = ESCALA
    arte = bebida.get('arte')
    if arte == 'corazon':
        color = rgb(bebida.get('color_arte', '#FBF4EA'))
        r = 16 * escala
        draw.ellipse(_caja(cx - r * 0.8, cy - 4 * escala, r * 2, r * 1.3), fill=color)
        draw.ellipse(_caja(cx + r * 0.8, cy - 4 * escala, r * 2, r * 1.3), fill=color)
        draw.polygon([((cx - r * 1.75) * s, cy * s), ((cx + r * 1.75) * s, cy * s), (cx * s, (cy + 16 * escala) * s)], fill=color)
    elif arte == 'cacao':
        color = rgb('#5A3825')
        for i in range(14):
            x = cx + ((i * 37) % 120 - 60) * escala
            y = cy + ((i * 23) % 26 - 13) * escala
            draw.ellipse(_caja(x, y, 6 * escala, 4 * escala), fill=color)


def _x_en(y: float, lado: int) -> float:
    """X del borde del vaso (lado 1 = izquierda, 2 = derecha) a la altura y."""
    (y0, *xs0), (y1, *xs1) = VASO_ARRIBA, VASO_ABAJO
    t = (y - y0) / (y1 - y0)
    return xs0[lado - 1] + (xs1[lado - 1] - xs0[lado - 1]) * t


def _franja(draw, y_desde, y_hasta, color) -> None:
    s = ESCALA
    draw.polygon([
        (_x_en(y_desde, 1) * s, y_desde * s), (_x_en(y_desde, 2) * s, y_desde * s),
        (_x_en(y_hasta, 2) * s, y_hasta * s), (_x_en(y_hasta, 1) * s, y_hasta * s),
    ], fill=color)


def dibujar_vaso(bebida: dict, ruta: str) -> None:
    capas = bebida['capas']
    img, draw = lienzo(capas[0][0])
    s = ESCALA
    tope_y, fondo_y = VASO_ARRIBA[0] + 30, VASO_ABAJO[0]
    draw.ellipse(_caja(240, fondo_y + 6, 190, 26), fill=(0, 0, 0, 30))
    _franja(draw, VASO_ARRIBA[0], fondo_y, (255, 255, 255, 120))
    total = sum(p for _, p in capas)
    y = fondo_y
    for color, proporcion in capas:
        alto = (fondo_y - tope_y) * proporcion / total
        _franja(draw, y - alto, y, rgb(color))
        y -= alto
    if bebida.get('hielo'):
        for i, (x, yy) in enumerate([(200, 200), (262, 190), (230, 245), (285, 250)]):
            draw.rounded_rectangle(_caja(x, yy, 46, 40), radius=8 * s, fill=(255, 255, 255, 110), outline=(255, 255, 255, 170), width=2 * s)
    _tope(draw, tope_y, bebida)
    # Brillo del vidrio y borde.
    draw.line([(_x_en(160, 1) + 16) * s, 160 * s, (_x_en(420, 1) + 14) * s, 420 * s], fill=(255, 255, 255, 140), width=8 * s)
    draw.line([_x_en(VASO_ARRIBA[0], 1) * s, VASO_ARRIBA[0] * s, _x_en(fondo_y, 1) * s, fondo_y * s], fill=COLOR_BORDE, width=3 * s)
    draw.line([_x_en(VASO_ARRIBA[0], 2) * s, VASO_ARRIBA[0] * s, _x_en(fondo_y, 2) * s, fondo_y * s], fill=COLOR_BORDE, width=3 * s)
    draw.line([_x_en(fondo_y, 1) * s, fondo_y * s, _x_en(fondo_y, 2) * s, fondo_y * s], fill=COLOR_BORDE, width=3 * s)
    guardar(img, ruta)


def _tope(draw, tope_y, bebida) -> None:
    s = ESCALA
    tope = bebida.get('tope')
    if tope == 'espuma':
        _franja(draw, tope_y - 18, tope_y + 8, rgb('#FBF4EA'))
    elif tope == 'crema':
        for x, y, r in [(190, tope_y - 6, 42), (240, tope_y - 14, 48), (290, tope_y - 6, 42), (240, tope_y - 55, 36), (240, tope_y - 88, 20)]:
            draw.ellipse(_caja(x, y, r * 2, r * 1.6), fill=(255, 252, 246), outline=(236, 228, 216), width=2 * s)
    elif tope == 'bocha':
        oscuro = mezclar('#F3E5AB', '#000000', 0.12)
        draw.ellipse(_caja(240, tope_y - 10, 190, 60), fill=oscuro)
        draw.ellipse(_caja(240, tope_y - 50, 170, 120), fill=rgb('#F3E5AB'))
    drizzle = bebida.get('drizzle')
    if drizzle and tope in ('crema', 'bocha'):
        for k in range(3):
            y = tope_y - 70 + k * 22
            draw.arc(_caja(240, y, 150 - k * 20, 26), 200, 340, fill=rgb(drizzle), width=6 * s)
