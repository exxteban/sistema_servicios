"""Vista previa, en lenguaje claro, de lo que haria cada tool de escritura. NO guarda nada.

El texto lo arma el servidor a partir de los datos reales (no lo redacta la IA), asi lo que el
usuario confirma con el boton es exactamente lo que se va a ejecutar. Un error aca vuelve a la
IA para que corrija o pregunte antes de proponer.
"""
from __future__ import annotations

from types import SimpleNamespace

from gastronomia.services.asistente import combinar, resolver
from gastronomia.services.asistente.tools_escritura import (
    CATEGORIA_INSUMOS,
    _lote,
    plan_mesas,
    plato_existente,
)
from gastronomia.services.stock_service import UNIDADES_STOCK, obtener_receta

_n = resolver.normalizar


class Pendientes:
    """Lo que ya se propuso crear en este mismo turno (todavia no existe en la base)."""

    def __init__(self):
        self.categorias: set[str] = set()
        self.platos: set[str] = set()
        self.insumos: dict[str, str] = {}


def dinero(valor) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return str(valor)
    texto = f'{numero:,.0f}' if numero.is_integer() else f'{numero:,.2f}'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def _si_no(valor) -> str:
    return 'si' if valor else 'no'


def _cambio(etiqueta: str, antes, despues) -> str | None:
    return None if antes == despues else f'{etiqueta} {antes} -> {despues}'


def _errores(errores: list[str]):
    if errores:
        raise ValueError('No propuse nada todavia, corregi esto: ' + ' | '.join(errores))


def crear_categorias(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    lineas = []
    for item in _lote(args, 'categorias'):
        nombre = str((item.get('nombre') if isinstance(item, dict) else item) or '').strip()
        if not nombre:
            continue
        if resolver.categoria(cliente_id, nombre, exacto=True) or _n(nombre) in p.categorias:
            lineas.append(f"Categoria '{nombre}': ya existe, no cambia")
            continue
        p.categorias.add(_n(nombre))
        lineas.append(f"Crear categoria '{nombre}'")
    return lineas


def _categoria_nombre(cliente_id: int, item: dict, existente, p: Pendientes) -> str:
    if item.get('categoria') and _n(item['categoria']) in p.categorias:
        return str(item['categoria'])
    if item.get('categoria'):
        return resolver.categoria_para_escribir(cliente_id, item['categoria']).nombre
    if existente:
        return existente.categoria.nombre
    raise ValueError(f"Falta la categoria del plato nuevo '{item.get('nombre')}'.")


def guardar_platos(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    lineas, errores = [], []
    for item in _lote(args, 'platos'):
        try:
            if not isinstance(item, dict):
                raise ValueError(f"Formato invalido: {item}")
            existente = plato_existente(cliente_id, item)
            categoria = _categoria_nombre(cliente_id, item, existente, p)
        except ValueError as exc:
            errores.append(str(exc))
            continue
        if not existente:
            precio = dinero(item.get('precio')) if item.get('precio') not in (None, '') else 'SIN PRECIO'
            p.platos.add(_n(item.get('nombre')))
            lineas.append(f"Crear plato '{item.get('nombre')}' en '{categoria}' a {precio}")
            continue
        cambios = [c for c in (
            _cambio('nombre', existente.nombre, item.get('nuevo_nombre') or existente.nombre),
            _cambio('categoria', existente.categoria.nombre, categoria),
            _cambio('precio', dinero(existente.precio), dinero(item['precio'])) if 'precio' in item else None,
            _cambio('disponible', _si_no(existente.disponible), _si_no(item['disponible'])) if 'disponible' in item else None,
            'descripcion nueva' if 'descripcion' in item and (item['descripcion'] or '') != (existente.descripcion or '') else None,
        ) if c]
        lineas.append(f"Editar plato '{existente.nombre}': " + ('; '.join(cambios) if cambios else 'sin cambios'))
    _errores(errores)
    return lineas


def cambiar_estado_plato(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    plato = resolver.plato_para_escribir(cliente_id, args.get('plato'))
    cambios = [c for c in (
        _cambio('precio', dinero(plato.precio), dinero(args['precio'])) if 'precio' in args else None,
        _cambio('disponible', _si_no(plato.disponible), _si_no(args['disponible'])) if 'disponible' in args else None,
        _cambio('visible en menu', _si_no(plato.visible), _si_no(args['visible'])) if 'visible' in args else None,
        _cambio('publicado en tienda', _si_no(plato.publicado_tienda), _si_no(args['publicado_tienda'])) if 'publicado_tienda' in args else None,
        _cambio('costo extra', dinero(plato.costo_extra), dinero(args['costo_extra'])) if 'costo_extra' in args else None,
    ) if c]
    return [f"Plato '{plato.nombre}': " + ('; '.join(cambios) if cambios else 'sin cambios')]


def _aviso_inventario(insumo) -> str:
    categoria = getattr(getattr(insumo, 'categoria', None), 'nombre', '')
    if insumo.id_cliente is None or categoria != CATEGORIA_INSUMOS:
        return ' (OJO: es un producto del inventario general, el cambio tambien se ve alli)'
    return ''


def guardar_insumos(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    lineas, errores = [], []
    for item in _lote(args, 'insumos'):
        nombre = str((item.get('nombre') if isinstance(item, dict) else '') or '').strip()
        unidad = str(item.get('unidad') or 'unidad').strip().lower() if isinstance(item, dict) else ''
        if not nombre or unidad not in UNIDADES_STOCK:
            errores.append(f"Insumo '{nombre or item}': nombre o unidad invalida ({', '.join(sorted(UNIDADES_STOCK))}).")
            continue
        existente = resolver.insumo(cliente_id, nombre, exacto=True)
        if not existente:
            p.insumos[_n(nombre)] = unidad
            inicial = int(item.get('stock_inicial') or 0)
            lineas.append(f"Crear insumo '{nombre}' en {unidad}, costo {dinero(item.get('precio_compra'))} por {unidad}"
                          + (f', stock inicial {inicial}' if inicial else ''))
            continue
        cambios = [c for c in (
            _cambio('unidad', existente.unidad_stock or 'unidad', unidad) if item.get('unidad') else None,
            _cambio('costo', dinero(existente.precio_compra), dinero(item['precio_compra'])) if item.get('precio_compra') is not None else None,
            _cambio('stock minimo', int(existente.stock_minimo or 0), int(item['stock_minimo'])) if item.get('stock_minimo') is not None else None,
        ) if c]
        lineas.append(f"Editar insumo '{existente.nombre}': " + ('; '.join(cambios) if cambios else 'sin cambios')
                      + (_aviso_inventario(existente) if cambios else ''))
    _errores(errores)
    return lineas


def _plato_o_pendiente(cliente_id: int, valor, p: Pendientes):
    """(plato existente o None si se crea en esta misma propuesta, nombre a mostrar)."""
    if _n(valor) in p.platos:
        return None, str(valor)
    plato = resolver.plato_para_escribir(cliente_id, valor)
    return plato, plato.nombre


def guardar_receta_plato(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    plato, nombre_plato = _plato_o_pendiente(cliente_id, args.get('plato'), p)
    modo = combinar.modo(args)
    nombres, unidades, pedido, errores = {}, {}, {}, []
    for fila in _lote(args, 'ingredientes'):
        fila = fila if isinstance(fila, dict) else {'insumo': fila}
        valor = fila.get('insumo')
        insumo = resolver.insumo(cliente_id, valor, exacto=True)
        if not insumo and _n(valor) in p.insumos:
            insumo = SimpleNamespace(id_producto=f'nuevo:{_n(valor)}', nombre=str(valor), unidad_stock=p.insumos[_n(valor)])
        if not insumo:
            errores.append(resolver._no_encontrado('un insumo', valor, resolver.listar_insumos(cliente_id)) + ' Crealo primero.')
            continue
        nombres[insumo.id_producto], unidades[insumo.id_producto] = insumo.nombre, insumo.unidad_stock or 'unidad'
        try:
            pedido[insumo.id_producto] = 0 if modo == 'quitar' else combinar.cantidad_receta(fila.get('cantidad'), insumo)
        except ValueError as exc:
            errores.append(str(exc))
    _errores(errores)
    previos = {}
    if plato:
        for item in obtener_receta(cliente_id, plato.id_producto)['items']:
            previos[item['insumo_id']] = item['cantidad']
            nombres[item['insumo_id']] = item['insumo_nombre']
            unidades[item['insumo_id']] = item['unidad_stock']
    final = combinar.combinar(previos, pedido, modo)
    texto = ', '.join(f'{nombres[k]} {v} {unidades[k]}' for k, v in final.items()) or 'VACIA (sin ingredientes)'
    antes = ', '.join(f'{nombres[k]} {v} {unidades[k]}' for k, v in previos.items())
    return [f"Receta de '{nombre_plato}' quedaria: {texto}" + (f' (antes: {antes})' if previos and previos != final else '')]


def configurar_extras_plato(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    plato, nombre_plato = _plato_o_pendiente(cliente_id, args.get('plato'), p)
    modo = combinar.modo(args)
    lineas = []
    if 'adicionales' in args:
        actuales = combinar.adicionales_actuales(cliente_id, plato.id_producto) if plato else {}
        pedido = {
            _n(a.get('nombre')): (a.get('nombre'), a.get('precio') or 0)
            for a in _lote(args, 'adicionales') if isinstance(a, dict) and a.get('nombre')
        }
        final = combinar.combinar(actuales, pedido, modo)
        texto = ', '.join(f'{n} +{dinero(pr)}' for n, pr in final.values()) or 'NINGUNO'
        lineas.append(f"Adicionales de '{nombre_plato}' quedarian: {texto}")
    if 'quitables' in args:
        actuales = combinar.quitables_actuales(cliente_id, plato.id_producto) if plato else {}
        pedido = {_n(q): (str(q), 0) for q in _lote(args, 'quitables') if str(q or '').strip()}
        final = combinar.combinar(actuales, pedido, modo)
        texto = ', '.join(n for n, _ in final.values()) or 'NINGUNO'
        lineas.append(f"Se podra pedir '{nombre_plato}' sin: {texto}")
    return lineas or [f"Plato '{nombre_plato}': sin cambios de extras"]


def crear_mesas(cliente_id: int, args: dict, p: Pendientes) -> list[str]:
    plan, capacidad = plan_mesas(cliente_id, args)
    if not plan:
        return ['Mesas: ya existen todas, no se crea ninguna']
    nombres = [n for n, _ in plan]
    rango = nombres[0] if len(nombres) == 1 else f'{nombres[0]} a {nombres[-1]}'
    return [f'Crear {len(nombres)} mesa(s): {rango} (capacidad {capacidad})']


VISTAS = {
    'crear_categorias': crear_categorias,
    'guardar_platos': guardar_platos,
    'cambiar_estado_plato': cambiar_estado_plato,
    'guardar_insumos': guardar_insumos,
    'guardar_receta_plato': guardar_receta_plato,
    'configurar_extras_plato': configurar_extras_plato,
    'crear_mesas': crear_mesas,
}
