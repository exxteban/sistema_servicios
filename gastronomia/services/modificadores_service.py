"""Modificadores configurables del menu gastronomico."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app import db
from gastronomia.models import GastronomiaGrupoOpciones, GastronomiaOpcionProducto
from gastronomia.services.menu_service import obtener_producto, parse_bool, parse_int, parse_price


TIPOS_GRUPO = {'variante', 'extra', 'ingrediente_removible', 'combo'}


def listar_grupos_producto(cliente_id: int, producto_id: int, *, incluir_ocultos: bool = True):
    query = GastronomiaGrupoOpciones.query.filter(
        GastronomiaGrupoOpciones.cliente_id == int(cliente_id),
        GastronomiaGrupoOpciones.producto_id == int(producto_id),
        GastronomiaGrupoOpciones.activo.is_(True),
    )
    if not incluir_ocultos:
        query = query.filter(GastronomiaGrupoOpciones.visible.is_(True))
    return query.order_by(GastronomiaGrupoOpciones.orden.asc(), GastronomiaGrupoOpciones.nombre.asc()).all()


def obtener_grupo(cliente_id: int, grupo_id: int) -> GastronomiaGrupoOpciones | None:
    return GastronomiaGrupoOpciones.query.filter(
        GastronomiaGrupoOpciones.cliente_id == int(cliente_id),
        GastronomiaGrupoOpciones.id_grupo == int(grupo_id),
        GastronomiaGrupoOpciones.activo.is_(True),
    ).first()


def obtener_opcion(cliente_id: int, opcion_id: int) -> GastronomiaOpcionProducto | None:
    return GastronomiaOpcionProducto.query.filter(
        GastronomiaOpcionProducto.cliente_id == int(cliente_id),
        GastronomiaOpcionProducto.id_opcion == int(opcion_id),
        GastronomiaOpcionProducto.activo.is_(True),
    ).first()


def guardar_grupo(cliente_id: int, producto_id: int, data: dict, grupo=None) -> GastronomiaGrupoOpciones:
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        raise ValueError('El producto no existe para este cliente.')
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        raise ValueError('El nombre del grupo es obligatorio.')
    tipo = (data.get('tipo') or 'extra').strip().lower()
    if tipo not in TIPOS_GRUPO:
        raise ValueError('Tipo de grupo invalido.')
    min_sel = max(0, parse_int(data.get('min_selecciones'), 0))
    max_default = 1 if tipo in {'variante', 'combo'} else 99
    max_sel = max(1, parse_int(data.get('max_selecciones'), max_default))
    obligatorio = parse_bool(data.get('obligatorio'), min_sel > 0)
    if obligatorio and min_sel == 0:
        min_sel = 1
    if max_sel < min_sel:
        raise ValueError('El maximo de selecciones no puede ser menor al minimo.')

    grupo = grupo or GastronomiaGrupoOpciones(cliente_id=int(cliente_id), producto_id=int(producto_id))
    grupo.nombre = nombre[:140]
    grupo.tipo = tipo
    grupo.obligatorio = obligatorio
    grupo.min_selecciones = min_sel
    grupo.max_selecciones = max_sel
    grupo.orden = parse_int(data.get('orden'), 0)
    grupo.visible = parse_bool(data.get('visible'), True)
    db.session.add(grupo)
    db.session.commit()
    return grupo


def guardar_opcion(cliente_id: int, grupo_id: int, data: dict, opcion=None) -> GastronomiaOpcionProducto:
    grupo = obtener_grupo(cliente_id, grupo_id)
    if not grupo:
        raise ValueError('El grupo no existe para este cliente.')
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        raise ValueError('El nombre de la opcion es obligatorio.')
    opcion = opcion or GastronomiaOpcionProducto(cliente_id=int(cliente_id), grupo_id=int(grupo_id))
    opcion.nombre = nombre[:140]
    opcion.precio_delta = parse_price(data.get('precio_delta', 0))
    if 'imagen_url' in data:
        opcion.imagen_url = (data.get('imagen_url') or '').strip()[:500] or None
    opcion.disponible = parse_bool(data.get('disponible'), True)
    opcion.visible = parse_bool(data.get('visible'), True)
    opcion.orden = parse_int(data.get('orden'), 0)
    db.session.add(opcion)
    db.session.commit()
    return opcion


def sincronizar_ingredientes_removibles(cliente_id: int, producto_id: int, ingredientes) -> GastronomiaGrupoOpciones | None:
    """Crea/actualiza el grupo usado por el POS para quitar ingredientes."""
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        raise ValueError('El producto no existe para este cliente.')

    nombres = _normalizar_nombres_ingredientes(ingredientes)
    grupos = GastronomiaGrupoOpciones.query.filter(
        GastronomiaGrupoOpciones.cliente_id == int(cliente_id),
        GastronomiaGrupoOpciones.producto_id == int(producto_id),
        GastronomiaGrupoOpciones.tipo == 'ingrediente_removible',
        GastronomiaGrupoOpciones.activo.is_(True),
    ).order_by(GastronomiaGrupoOpciones.id_grupo.asc()).all()
    grupo = grupos[0] if grupos else None
    for grupo_extra in grupos[1:]:
        grupo_extra.activo = False
        for opcion in grupo_extra.opciones.filter_by(activo=True).all():
            opcion.activo = False

    if not nombres:
        if grupo:
            grupo.activo = False
            for opcion in grupo.opciones.filter_by(activo=True).all():
                opcion.activo = False
            db.session.commit()
        return None

    if not grupo:
        grupo = GastronomiaGrupoOpciones(cliente_id=int(cliente_id), producto_id=int(producto_id))
    grupo.nombre = 'Ingredientes removibles'
    grupo.tipo = 'ingrediente_removible'
    grupo.obligatorio = False
    grupo.min_selecciones = 0
    grupo.max_selecciones = max(1, len(nombres))
    grupo.orden = -100
    grupo.visible = True
    grupo.activo = True
    db.session.add(grupo)
    db.session.flush()

    opciones_activas = {
        opcion.nombre.strip().lower(): opcion
        for opcion in grupo.opciones.filter_by(activo=True).all()
    }
    nombres_activos = {nombre.lower() for nombre in nombres}
    for orden, nombre in enumerate(nombres):
        opcion = opciones_activas.get(nombre.lower())
        if not opcion:
            opcion = GastronomiaOpcionProducto(cliente_id=int(cliente_id), grupo_id=grupo.id_grupo)
        opcion.nombre = nombre[:140]
        opcion.precio_delta = 0
        opcion.disponible = True
        opcion.visible = True
        opcion.orden = orden
        opcion.activo = True
        db.session.add(opcion)
    for nombre, opcion in opciones_activas.items():
        if nombre not in nombres_activos:
            opcion.activo = False
    db.session.commit()
    return grupo


def eliminar_grupo(cliente_id: int, grupo_id: int) -> bool:
    grupo = obtener_grupo(cliente_id, grupo_id)
    if not grupo:
        return False
    grupo.activo = False
    for opcion in grupo.opciones.filter_by(activo=True).all():
        opcion.activo = False
    db.session.commit()
    return True


def eliminar_opcion(cliente_id: int, opcion_id: int) -> bool:
    opcion = obtener_opcion(cliente_id, opcion_id)
    if not opcion:
        return False
    opcion.activo = False
    db.session.commit()
    return True


def producto_con_modificadores(cliente_id: int, producto_id: int) -> dict:
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        raise ValueError('Producto no encontrado.')
    data = producto.to_dict()
    data['grupos_opciones'] = [
        grupo.to_dict()
        for grupo in listar_grupos_producto(cliente_id, producto_id, incluir_ocultos=False)
    ]
    return data


def validar_selecciones_producto(cliente_id: int, producto_id: int, opciones_ids: list[int]) -> dict:
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        raise ValueError('Producto no encontrado.')
    grupos = listar_grupos_producto(cliente_id, producto_id, incluir_ocultos=False)
    opciones_por_id = {}
    grupos_por_id = {}
    for grupo in grupos:
        grupos_por_id[int(grupo.id_grupo)] = grupo
        for opcion in grupo.opciones_ordenadas():
            opciones_por_id[int(opcion.id_opcion)] = opcion

    seleccionadas = []
    total_modificadores = Decimal('0.00')
    for opcion_id in _normalizar_ids(opciones_ids):
        opcion = opciones_por_id.get(opcion_id)
        if not opcion:
            raise ValueError('Una opcion seleccionada no pertenece al producto.')
        if not opcion.disponible or not opcion.visible:
            raise ValueError(f'La opcion "{opcion.nombre}" no esta disponible.')
        seleccionadas.append(opcion)
        total_modificadores += Decimal(str(opcion.precio_delta or 0))

    conteo_por_grupo = Counter(int(opcion.grupo_id) for opcion in seleccionadas)
    for grupo in grupos:
        cantidad = conteo_por_grupo.get(int(grupo.id_grupo), 0)
        if cantidad < int(grupo.min_selecciones or 0):
            raise ValueError(f'Debes seleccionar al menos {grupo.min_selecciones} en {grupo.nombre}.')
        if cantidad > int(grupo.max_selecciones or 0):
            raise ValueError(f'Solo puedes seleccionar {grupo.max_selecciones} en {grupo.nombre}.')

    precio_base = Decimal(str(producto.precio or 0))
    total = precio_base + total_modificadores
    return {
        'producto': producto.to_dict(),
        'selecciones': [_opcion_con_grupo(opcion, grupos_por_id) for opcion in seleccionadas],
        'total_modificadores': float(total_modificadores),
        'total': float(total),
    }


def _opcion_con_grupo(opcion: GastronomiaOpcionProducto, grupos_por_id: dict[int, GastronomiaGrupoOpciones]) -> dict:
    data = opcion.to_dict()
    grupo = grupos_por_id.get(int(opcion.grupo_id))
    data['nombre_grupo'] = grupo.nombre if grupo else 'Opcion'
    data['tipo_grupo'] = grupo.tipo if grupo else 'extra'
    return data


def _normalizar_nombres_ingredientes(ingredientes) -> list[str]:
    if isinstance(ingredientes, str):
        partes = ingredientes.replace(';', '\n').replace(',', '\n').splitlines()
    elif isinstance(ingredientes, list):
        partes = [item.get('nombre') if isinstance(item, dict) else item for item in ingredientes]
    else:
        partes = []
    nombres = []
    vistos = set()
    for item in partes:
        nombre = str(item or '').strip()
        if not nombre:
            continue
        clave = nombre.lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        nombres.append(nombre[:140])
    return nombres


def _normalizar_ids(opciones_ids: list[int]) -> list[int]:
    ids = []
    for item in opciones_ids or []:
        raw = item.get('id_opcion') if isinstance(item, dict) else item
        try:
            opcion_id = int(raw)
        except (TypeError, ValueError):
            continue
        if opcion_id > 0:
            ids.append(opcion_id)
    return ids
