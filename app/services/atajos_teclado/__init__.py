"""Teclas rapidas: una tecla de funcion abre una pantalla desde cualquier lado.

Portado del sistema del taller (sistema_silvio_cel), adaptado a esta instalacion:
alla las teclas van atadas a las 4 "acciones rapidas" del inicio; aca cada rubro
tiene su propio catalogo de acciones (gastronomia: POS, salon, cocina, caja, menu...;
servicios: cobrar, nuevo turno, agenda...) y el usuario le asigna una accion a cada
tecla desde el boton "Teclas rapidas" del inicio.

- Se guarda por usuario y por rubro: {tecla: id de accion}.
- Solo cuentan las acciones que el usuario puede abrir: si pierde el permiso, la
  tecla se apaga sola.
- Una accion va en una sola tecla: si se repite, gana la primera tecla.
- Solo se ofrecen teclas de funcion que el navegador deja usar: F1 abre la ayuda,
  F3 buscar, F5 recarga, F6 la barra de direcciones, F7 la navegacion con cursor,
  F11 pantalla completa y F12 las herramientas.
- Sin preferencia guardada valen las teclas por defecto del rubro.
"""
from __future__ import annotations

import json
from typing import Any

TECLAS = ('F2', 'F4', 'F8', 'F9', 'F10')
PERFIL_GASTRONOMIA = 'gastronomia'
PERFIL_SERVICIOS = 'servicios'
_PREF_PREFIX = 'atajos_teclado_'


def normalizar_tecla(value: Any) -> str:
    """La tecla en mayusculas, o '' si no es una de las que se ofrecen."""
    tecla = str(value or '').strip().upper()
    return tecla if tecla in TECLAS else ''


def perfil_actual() -> str:
    from gastronomia.services.modo_operacion import gastronomia_activa

    try:
        return PERFIL_GASTRONOMIA if gastronomia_activa() else PERFIL_SERVICIOS
    except Exception:
        return PERFIL_SERVICIOS


def _catalogo(perfil: str, user: Any) -> tuple[list[dict], dict[str, str]]:
    """(acciones disponibles para el usuario, teclas por defecto del rubro)."""
    if perfil == PERFIL_GASTRONOMIA:
        from gastronomia.services.atajos_catalogo import ATAJOS_DEFAULT, acciones_disponibles
    else:
        from app.services.atajos_teclado.catalogo_servicios import ATAJOS_DEFAULT, acciones_disponibles
    return acciones_disponibles(user), dict(ATAJOS_DEFAULT)


def _pref_key(perfil: str) -> str:
    return f'{_PREF_PREFIX}{perfil}'


def limpiar(data: Any, ids_validos: set[str]) -> dict[str, str]:
    """{tecla: accion} sin teclas raras, acciones ajenas ni acciones repetidas.

    Se recorre en el orden de TECLAS (no el del JSON, que Flask ordena alfabeticamente
    y pondria F10 antes que F2).
    """
    if not isinstance(data, dict):
        return {}
    por_tecla = {normalizar_tecla(k): str(v or '').strip() for k, v in data.items()}
    resultado: dict[str, str] = {}
    usadas: set[str] = set()
    for tecla in TECLAS:
        accion_id = por_tecla.get(tecla) or ''
        if not accion_id or accion_id not in ids_validos or accion_id in usadas:
            continue
        resultado[tecla] = accion_id
        usadas.add(accion_id)
    return resultado


def _leer_guardados(user: Any, perfil: str) -> dict | None:
    try:
        raw = user.get_preferencia(_pref_key(perfil), None)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def get_atajos(user: Any, perfil: str | None = None) -> dict[str, str]:
    perfil = perfil or perfil_actual()
    acciones, defaults = _catalogo(perfil, user)
    ids = {accion['id'] for accion in acciones}
    guardados = _leer_guardados(user, perfil)
    return limpiar(defaults if guardados is None else guardados, ids)


def set_atajos(user: Any, data: Any, perfil: str | None = None) -> dict[str, str]:
    perfil = perfil or perfil_actual()
    acciones, _ = _catalogo(perfil, user)
    atajos = limpiar(data, {accion['id'] for accion in acciones})
    # Se guarda aunque quede vacio: sin fila volverian las teclas por defecto.
    user.set_preferencia(_pref_key(perfil), json.dumps(atajos, ensure_ascii=False))
    return atajos


def contexto_atajos(user: Any, perfil: str | None = None) -> dict:
    """Lo que necesitan el script global de teclas y el modal "Asignar teclas"."""
    perfil = perfil or perfil_actual()
    acciones, defaults = _catalogo(perfil, user)
    by_id = {accion['id']: accion for accion in acciones}
    ids = set(by_id)
    guardados = _leer_guardados(user, perfil)
    atajos = limpiar(defaults if guardados is None else guardados, ids)
    return {
        'perfil': perfil,
        'teclas': list(TECLAS),
        'atajos': atajos,
        'acciones': [
            {
                'id': accion_id,
                'tecla': tecla,
                'url': by_id[accion_id]['url'],
                'title': by_id[accion_id]['title'],
                'icon': by_id[accion_id]['icon'],
            }
            for tecla, accion_id in atajos.items()
        ],
        'disponibles': [
            {
                'id': accion['id'],
                'title': accion['title'],
                'icon': accion['icon'],
                'group': accion.get('group') or '',
            }
            for accion in acciones
        ],
        'defaults': limpiar(defaults, ids),
    }
