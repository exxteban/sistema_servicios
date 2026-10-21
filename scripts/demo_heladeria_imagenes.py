"""Dibujos simples (bocha, cucurucho, vasito, pote) para la demo de heladeria.

Deterministico por nombre: correr el script dos veces genera la misma imagen.
"""
from __future__ import annotations

import random

from demo_menu_dibujo import ESCALA, guardar, lienzo, mezclar, rgb

COLOR_CONO = '#D9A066'
COLOR_CONO_LINEA = '#B07A3C'


def _bocha(draw, cx: float, cy: float, r: float, sabor: dict, semilla: str) -> None:
    s = ESCALA
    color = sabor['color']
    oscuro = mezclar(color, '#000000', 0.18)
    # Volado inferior: la bocha "cae" sobre el cono o el vaso.
    for i in range(9):
        x = cx - r * 0.95 + i * (r * 1.9 / 8)
        draw.ellipse([(x - r * 0.2) * s, (cy + r * 0.38) * s, (x + r * 0.2) * s, (cy + r * 0.72) * s], fill=oscuro)
    draw.ellipse([(cx - r) * s, (cy - r * 0.92) * s, (cx + r) * s, (cy + r * 0.62) * s], fill=rgb(color))
    _topping(draw, cx, cy, r, sabor, random.Random(semilla))
    # Brillo arriba a la izquierda.
    draw.ellipse(
        [(cx - r * 0.62) * s, (cy - r * 0.7) * s, (cx - r * 0.12) * s, (cy - r * 0.38) * s],
        fill=(255, 255, 255, 90),
    )


def _topping(draw, cx, cy, r, sabor: dict, rnd: random.Random) -> None:
    tipo, color = sabor.get('topping'), sabor.get('topping_color')
    if not tipo or not color:
        return
    s = ESCALA
    color_rgb = rgb(color)
    if tipo == 'remolino':
        for k in range(3):
            y = cy - r * 0.45 + k * r * 0.35
            draw.arc(
                [(cx - r * 0.8) * s, (y - r * 0.25) * s, (cx + r * 0.8) * s, (y + r * 0.25) * s],
                start=200 if k % 2 else 20, end=340 if k % 2 else 160, fill=color_rgb, width=int(r * 0.09 * s),
            )
        return
    cantidad = {'chips': 22, 'frutas': 16, 'copos': 28}.get(tipo, 18)
    for _ in range(cantidad):
        dx, dy = rnd.uniform(-0.75, 0.75), rnd.uniform(-0.7, 0.4)
        if dx * dx + (dy + 0.15) ** 2 > 0.6:
            continue
        x, y = cx + dx * r, cy + dy * r
        if tipo == 'chips':
            t = r * rnd.uniform(0.05, 0.09)
            draw.rounded_rectangle([(x - t) * s, (y - t * 0.7) * s, (x + t) * s, (y + t * 0.7) * s], radius=3 * s, fill=color_rgb)
        elif tipo == 'copos':
            t = r * 0.08
            draw.line([(x - t) * s, y * s, (x + t) * s, (y - t * 0.4) * s], fill=color_rgb, width=int(3 * s))
        else:
            t = r * rnd.uniform(0.06, 0.1)
            draw.ellipse([(x - t) * s, (y - t) * s, (x + t) * s, (y + t) * s], fill=color_rgb)


def dibujar_sabor(sabor: dict, ruta: str) -> None:
    img, draw = lienzo(sabor['color'])
    _bocha(draw, 240, 250, 165, sabor, sabor['nombre'])
    guardar(img, ruta)


def dibujar_presentacion(presentacion: dict, sabores: list[dict], ruta: str) -> None:
    """Cucurucho, vasito o pote con tantas bochas como sabores permite."""
    s = ESCALA
    img, draw = lienzo(sabores[0]['color'])
    forma = presentacion['forma']
    bochas = min(presentacion['max_sabores'], 3)
    if forma == 'cono':
        # Cono en una sola columna: las bochas se apilan.
        _cono(draw)
        r = 100 if bochas == 1 else 88
        posiciones = [(240, 215 - i * 105) for i in range(bochas)] if bochas < 3 else [(240, 225), (240, 125)]
    else:
        r = 88
        base_y = 245 if forma == 'vaso' else 230
        posiciones = {1: [(240, base_y)], 2: [(190, base_y), (290, base_y)],
                      3: [(175, base_y), (305, base_y), (240, base_y - 85)]}[bochas]
    for (x, y), sabor in zip(posiciones, sabores):
        _bocha(draw, x, y, r, sabor, presentacion['nombre'] + sabor['nombre'])
    if forma == 'vaso':
        # El vaso va encima para que las bochas queden "adentro".
        draw.polygon([(130 * s, 285 * s), (350 * s, 285 * s), (315 * s, 455 * s), (165 * s, 455 * s)], fill=(252, 252, 252))
        draw.rectangle([150 * s, 340 * s, 330 * s, 372 * s], fill=rgb(sabores[-1]['color']))
    elif forma == 'pote':
        draw.rounded_rectangle([105 * s, 275 * s, 375 * s, 460 * s], radius=22 * s, fill=(252, 252, 252))
        draw.rectangle([105 * s, 335 * s, 375 * s, 385 * s], fill=rgb(sabores[-1]['color']))
    guardar(img, ruta)


def _cono(draw) -> None:
    s = ESCALA
    draw.polygon([(140 * s, 270 * s), (340 * s, 270 * s), (240 * s, 465 * s)], fill=rgb(COLOR_CONO))
    linea = rgb(COLOR_CONO_LINEA)
    for k in range(1, 7):
        draw.line([(140 + k * 28) * s, 270 * s, (200 + k * 6) * s, 400 * s], fill=linea, width=3 * s)
        draw.line([(340 - k * 28) * s, 270 * s, (280 - k * 6) * s, 400 * s], fill=linea, width=3 * s)
