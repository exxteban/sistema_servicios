"""Combina lo que pide la IA con lo que ya tiene el plato (receta, adicionales, quitables).

Los servicios del modulo reemplazan la lista completa. Si la IA manda solo lo nuevo
("agregale extra bacon"), reemplazar borraria lo anterior; por eso el modo por defecto es
'agregar' y la lista final se arma aca, antes de llamar al servicio.
"""
from __future__ import annotations

from gastronomia.services.asistente import resolver
from gastronomia.services.modificadores_service import listar_grupos_producto

MODOS = ('agregar', 'quitar', 'reemplazar')
UNIDADES_FRACCIONABLES = {'g', 'ml'}


def modo(args: dict) -> str:
    valor = str(args.get('modo') or 'agregar').strip().lower()
    if valor not in MODOS:
        raise ValueError(f"Modo '{valor}' invalido. Usa: {', '.join(MODOS)}.")
    return valor


def combinar(actual: dict, pedido: dict, modo_: str) -> dict:
    """actual/pedido: {clave: valor}, en orden. Devuelve el resultado segun el modo."""
    if modo_ == 'reemplazar':
        return dict(pedido)
    if modo_ == 'quitar':
        return {k: v for k, v in actual.items() if k not in pedido}
    return {**actual, **pedido}


def cantidad_receta(valor, insumo) -> int:
    """Cantidad entera en la unidad del insumo, con un error claro si no tiene sentido."""
    unidad = (getattr(insumo, 'unidad_stock', None) or 'unidad').lower()
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cantidad invalida para '{insumo.nombre}'.") from exc
    entero = int(round(numero))
    if unidad not in UNIDADES_FRACCIONABLES and abs(numero - entero) > 0.01:
        raise ValueError(
            f"'{insumo.nombre}' se mide en '{unidad}' y las recetas usan cantidades enteras: "
            f'{numero:g} no se puede guardar. Redondea, o crea el insumo en g/ml.'
        )
    if entero <= 0:
        raise ValueError(f"La cantidad de '{insumo.nombre}' debe ser mayor a cero (vino {numero:g}).")
    return entero


def _opciones(cliente_id: int, plato_id: int, tipo: str, nombre: str | None = None) -> list:
    for grupo in listar_grupos_producto(cliente_id, plato_id):
        if grupo.tipo == tipo and (nombre is None or grupo.nombre == nombre):
            return grupo.opciones_ordenadas()
    return []


def adicionales_actuales(cliente_id: int, plato_id: int) -> dict:
    """{nombre_normalizado: (nombre, precio)}"""
    return {
        resolver.normalizar(o.nombre): (o.nombre, float(o.precio_delta or 0))
        for o in _opciones(cliente_id, plato_id, 'extra', 'Adicionales')
    }


def quitables_actuales(cliente_id: int, plato_id: int) -> dict:
    """{nombre_normalizado: (nombre, descuento)}; conserva el descuento ya cargado."""
    return {
        resolver.normalizar(o.nombre): (o.nombre, abs(float(o.precio_delta or 0)))
        for o in _opciones(cliente_id, plato_id, 'ingrediente_removible')
    }
