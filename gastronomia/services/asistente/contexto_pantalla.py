"""Contexto de pantalla que acompana cada mensaje del usuario al asistente.

Viene del navegador, asi que se trata como dato no confiable: solo claves conocidas,
textos cortos y sin saltos de linea. Se guarda pegado a cada mensaje del historial.
"""
from __future__ import annotations

CLAVES = ('pantalla', 'subpestana', 'seccion', 'plato', 'insumo')
ETIQUETAS = {
    'pantalla': 'pantalla',
    'subpestana': 'pestana',
    'seccion': 'seccion',
    'plato': 'plato abierto',
    'insumo': 'insumo abierto',
}
MAX_TEXTO = 80
MAX_PESTANAS = 8


def _limpio(valor) -> str:
    texto = ' '.join(str(valor or '').replace('[', '(').replace(']', ')').split())
    return texto[:MAX_TEXTO]


def sanitizar_contexto(data) -> dict:
    if not isinstance(data, dict):
        return {}
    salida = {clave: _limpio(data.get(clave)) for clave in CLAVES}
    pestanas = data.get('pestanas_abiertas')
    if isinstance(pestanas, list):
        salida['pestanas_abiertas'] = [p for p in (_limpio(x) for x in pestanas[:MAX_PESTANAS]) if p]
    return {k: v for k, v in salida.items() if v}


def etiqueta_contexto(contexto: dict | None) -> str:
    """Ej: '[viendo: pestana Stock y recetas · plato abierto Clasica]'."""
    if not contexto:
        return ''
    partes = [f'{ETIQUETAS[c]} {contexto[c]}' for c in CLAVES if contexto.get(c) and c != 'pantalla']
    if not partes and contexto.get('pantalla'):
        partes.append(f"pantalla {contexto['pantalla']}")
    if contexto.get('pestanas_abiertas'):
        partes.append('pestanas del sistema abiertas: ' + ', '.join(contexto['pestanas_abiertas']))
    return f"[viendo: {' · '.join(partes)}]" if partes else ''
