"""Agrupa los nombres escritos a mano en productos del menu.

Ejemplo: 'flye dobke', 'flyedoble' y 'flyn doble' terminan en "Flye Doble".
La clave de agrupacion es (nombre base parecido, tamano). Lo que va despues de
'con'/'sin' se toma como nota (modificador), no como otro producto.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from decimal import Decimal

from gastronomia.services.importacion.texto import normalizar


TAMANOS = {
    'doble': ('doble', 'dobles', 'dobke', 'dob', 'dobel', 'doble1'),
    'triple': ('triple', 'tripel', 'triples'),
    'simple': ('simple', 'simpel', 'simples', 'normal', 'nomal', 'normail', 'normales', 'comun'),
}
CORTES_MODIFICADOR = {'con', 'sin', 'c', 's', 'extra', 'mas'}
CLAVE_VARIOS = '__varios__'
NOMBRE_VARIOS = 'Varios (importado)'
SIMILITUD_MINIMA = 0.75


def clave_alias(nombre: str) -> str:
    return normalizar(nombre)[:160]


def analizar_nombre(nombre: str) -> dict:
    """Separa un nombre en base, tamano y nota ('gus doble con panceta')."""
    texto = clave_alias(nombre)
    if ',' in str(nombre) or re.search(r'\d+\s*[a-z]+.*\d+\s*[a-z]+', texto):
        return {'base': '', 'tamano': None, 'extras': '', 'multiple': True}
    tokens = []
    for token in re.split(r'[\s/]+', texto):
        tokens.extend(_separar_tamano_pegado(token))
    tokens = [token for token in tokens if token and not token.isdigit()]
    tamano, base, extras, en_modificador = None, [], [], False
    for token in tokens:
        tamano_token = _tamano(token)
        if tamano_token:
            tamano = tamano_token
            continue
        if token in CORTES_MODIFICADOR and base:
            en_modificador = True
        (extras if en_modificador else base).append(token)
    return {'base': ' '.join(base), 'tamano': tamano, 'extras': ' '.join(extras), 'multiple': False}


def agrupar_alias(filas: list[dict], productos_menu: list[dict], aprendidos: dict[str, int | str]) -> list[dict]:
    """filas: [{'nombre', 'cantidad', 'monto'}]. Devuelve grupos sugeridos."""
    alias = _resumir_alias(filas)
    menu_por_id = {int(p['id_producto']): p for p in productos_menu}
    grupos: dict[str, dict] = {}
    pendientes = []
    for clave, info in alias.items():
        producto_id = aprendidos.get(clave)
        if producto_id == CLAVE_VARIOS:
            _agregar(grupos, CLAVE_VARIOS, info, nombre=NOMBRE_VARIOS, accion='varios', origen='aprendido')
        elif producto_id and producto_id in menu_por_id:
            _agregar(grupos, f'p{producto_id}', info, nombre=menu_por_id[producto_id]['nombre'],
                     accion='existente', producto_id=producto_id, origen='aprendido')
        elif info['analisis']['multiple'] or not info['analisis']['base']:
            _agregar(grupos, CLAVE_VARIOS, info, nombre=NOMBRE_VARIOS, accion='varios', origen='varios')
        else:
            pendientes.append(info)

    familias = _familias(pendientes)
    for familia in familias:
        tamanos_precio = _precio_por_tamano(familia['alias'])
        for info in familia['alias']:
            tamano = info['analisis']['tamano'] or _tamano_por_precio(info, tamanos_precio)
            sufijo = tamano or _sufijo_sin_tamano(info, tamanos_precio)
            nombre = _titulo(f"{familia['canonico']} {sufijo or ''}")
            existente = _buscar_en_menu(nombre, familia['canonico'], tamano, productos_menu)
            if existente:
                _agregar(grupos, f"p{existente['id_producto']}", info, nombre=existente['nombre'],
                         accion='existente', producto_id=int(existente['id_producto']), origen='menu')
            else:
                _agregar(grupos, f'n:{clave_alias(nombre)}', info, nombre=nombre, accion='crear', origen='nuevo')
    return _ordenar(grupos)


def _resumir_alias(filas: list[dict]) -> dict[str, dict]:
    alias: dict[str, dict] = {}
    for fila in filas:
        if fila.get('monto') is None:
            continue
        clave = clave_alias(fila['nombre'])
        info = alias.setdefault(clave, {
            'alias': clave,
            'ejemplo': str(fila['nombre']).strip()[:160],
            'veces': 0,
            'unidades': 0,
            'total': Decimal('0'),
            'precios': Counter(),
            'analisis': analizar_nombre(fila['nombre']),
        })
        cantidad = max(int(fila.get('cantidad') or 1), 1)
        monto = Decimal(str(fila['monto']))
        info['veces'] += 1
        info['unidades'] += cantidad
        info['total'] += monto
        info['precios'][(monto / cantidad).quantize(Decimal('1'))] += cantidad
    return alias


def _familias(pendientes: list[dict]) -> list[dict]:
    """Agrupa por la primera palabra del nombre (el nombre de la hamburguesa)."""
    por_palabra: dict[str, list[dict]] = defaultdict(list)
    for info in pendientes:
        por_palabra[info['analisis']['base'].split(' ')[0]].append(info)
    palabras = sorted(por_palabra, key=lambda p: -sum(i['unidades'] for i in por_palabra[p]))
    familias: list[dict] = []
    for palabra in palabras:
        destino = next((f for f in familias if any(_parecidas(palabra, m) for m in f['miembros'])), None)
        if destino is None:
            destino = {'miembros': [], 'alias': [], 'conteo': Counter()}
            familias.append(destino)
        destino['miembros'].append(palabra)
        destino['alias'].extend(por_palabra[palabra])
        destino['conteo'][palabra] += sum(i['unidades'] for i in por_palabra[palabra])
    for familia in familias:
        familia['canonico'] = familia['conteo'].most_common(1)[0][0]
    return familias


def _parecidas(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 3:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    if difflib.SequenceMatcher(None, a, b).ratio() >= SIMILITUD_MINIMA:
        return True
    esq_a, esq_b = _esqueleto(a), _esqueleto(b)
    if min(len(esq_a), len(esq_b)) >= 3 and difflib.SequenceMatcher(None, esq_a, esq_b).ratio() >= 0.85:
        return True
    # Nombres largos que arrancan igual ('heisen', 'heinseberg') suelen ser el mismo plato.
    return min(len(a), len(b)) >= 5 and a[:3] == b[:3]


def _esqueleto(palabra: str) -> str:
    return re.sub(r'[aeiouy]', '', palabra)


def _precio_por_tamano(alias: list[dict]) -> dict:
    precios: dict[str | None, Counter] = defaultdict(Counter)
    for info in alias:
        precios[info['analisis']['tamano']].update(info['precios'])
    return {tamano: conteo.most_common(1)[0][0] for tamano, conteo in precios.items() if conteo}


def _tamano_por_precio(info: dict, tamanos_precio: dict) -> str | None:
    con_tamano = {t: p for t, p in tamanos_precio.items() if t}
    if not con_tamano or not info['precios']:
        return None
    precio = info['precios'].most_common(1)[0][0]
    return min(con_tamano, key=lambda tamano: (abs(con_tamano[tamano] - precio), tamano != 'simple'))


def _sufijo_sin_tamano(info: dict, tamanos_precio: dict) -> str:
    """Sin tamanos en la familia ('coca personal', 'coca de medio') el resto del nombre distingue."""
    if any(tamanos_precio):
        return ''
    return ' '.join(info['analisis']['base'].split(' ')[1:])


def _buscar_en_menu(nombre: str, canonico: str, tamano: str | None, productos_menu: list[dict]) -> dict | None:
    objetivo = clave_alias(nombre)
    mejor, mejor_ratio = None, 0.0
    for producto in productos_menu:
        nombre_menu = clave_alias(producto['nombre'])
        if nombre_menu == objetivo:
            return producto
        analisis = analizar_nombre(producto['nombre'])
        primera = (analisis['base'].split(' ') or [''])[0]
        if not _parecidas(canonico, primera):
            continue
        if (analisis['tamano'] or 'simple') != (tamano or 'simple'):
            continue
        ratio = difflib.SequenceMatcher(None, objetivo, nombre_menu).ratio()
        if ratio > mejor_ratio:
            mejor, mejor_ratio = producto, ratio
    return mejor


def _agregar(grupos: dict, clave: str, info: dict, *, nombre: str, accion: str,
             producto_id: int | None = None, origen: str) -> None:
    grupo = grupos.setdefault(clave, {
        'clave': clave,
        'nombre': nombre[:160],
        'accion': accion,
        'producto_id': producto_id,
        'origen': origen,
        'unidades': 0,
        'total': Decimal('0'),
        'precios': Counter(),
        'alias': [],
    })
    grupo['unidades'] += info['unidades']
    grupo['total'] += info['total']
    grupo['precios'].update(info['precios'])
    grupo['alias'].append({
        'alias': info['alias'],
        'ejemplo': info['ejemplo'],
        'veces': info['veces'],
        'unidades': info['unidades'],
        'nota': info['analisis']['extras'],
        'multiple': info['analisis']['multiple'],
    })


def _ordenar(grupos: dict) -> list[dict]:
    resultado = []
    for grupo in grupos.values():
        precio = grupo['precios'].most_common(1)[0][0] if grupo['precios'] else Decimal('0')
        grupo['alias'].sort(key=lambda item: -item['unidades'])
        resultado.append({
            **{k: v for k, v in grupo.items() if k not in ('precios', 'total')},
            'precio': float(precio),
            'total': float(grupo['total']),
        })
    resultado.sort(key=lambda g: (g['clave'] == CLAVE_VARIOS, -g['unidades']))
    return resultado


def _separar_tamano_pegado(token: str) -> list[str]:
    for variantes in TAMANOS.values():
        for variante in variantes:
            if len(token) > len(variante) + 1 and token.endswith(variante):
                return [token[:-len(variante)], variante]
    return [token]


def _tamano(token: str) -> str | None:
    for tamano, variantes in TAMANOS.items():
        if token in variantes:
            return tamano
    if len(token) >= 5:
        for tamano, variantes in TAMANOS.items():
            if difflib.get_close_matches(token, variantes, n=1, cutoff=0.8):
                return tamano
    return None


def _titulo(texto: str) -> str:
    return ' '.join(palabra.capitalize() for palabra in texto.split())
