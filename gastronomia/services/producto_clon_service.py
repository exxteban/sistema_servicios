"""Copia de lo que el formulario de producto no transporta al duplicar: receta y grupos de opciones.

El formulario ya recrea "ingredientes removibles" y "Adicionales" desde su texto (y el usuario pudo
editarlos), asi que esos grupos solo se emparejan por nombre de opcion. El resto de grupos
(variantes, combos, extras propios) se copian completos.
"""
from __future__ import annotations

from app import db
from gastronomia.models import GastronomiaGrupoOpciones, GastronomiaOpcionProducto
from gastronomia.services.menu_service import obtener_producto
from gastronomia.stock_models import GastronomiaOpcionInsumo, GastronomiaRecetaInsumo


def copiar_receta_y_opciones(cliente_id: int, origen_id: int, destino_id: int) -> None:
    origen = obtener_producto(cliente_id, origen_id)
    destino = obtener_producto(cliente_id, destino_id)
    if not origen or not destino or origen.id_producto == destino.id_producto:
        return
    _copiar_receta(cliente_id, origen.id_producto, destino.id_producto)
    grupos_destino = _grupos_activos(cliente_id, destino.id_producto)
    for grupo in _grupos_activos(cliente_id, origen.id_producto):
        par = _grupo_equivalente(grupo, grupos_destino)
        if par is None:
            if _grupo_del_formulario(grupo):
                continue  # El usuario lo vacio al duplicar: respetarlo.
            par = _clonar_grupo(cliente_id, grupo, destino.id_producto)
        _copiar_insumos_opciones(cliente_id, grupo, par)
    db.session.commit()


def _copiar_receta(cliente_id: int, origen_id: int, destino_id: int) -> None:
    existentes = {
        item.insumo_id
        for item in GastronomiaRecetaInsumo.query.filter_by(cliente_id=int(cliente_id), producto_id=destino_id).all()
    }
    for item in GastronomiaRecetaInsumo.query.filter_by(
        cliente_id=int(cliente_id), producto_id=origen_id, activo=True,
    ).all():
        if item.insumo_id in existentes:
            continue
        db.session.add(GastronomiaRecetaInsumo(
            cliente_id=int(cliente_id),
            producto_id=destino_id,
            insumo_id=item.insumo_id,
            cantidad=item.cantidad,
        ))


def _grupos_activos(cliente_id: int, producto_id: int) -> list[GastronomiaGrupoOpciones]:
    return (
        GastronomiaGrupoOpciones.query
        .filter_by(cliente_id=int(cliente_id), producto_id=int(producto_id), activo=True)
        .order_by(GastronomiaGrupoOpciones.id_grupo.asc())
        .all()
    )


def _grupo_del_formulario(grupo: GastronomiaGrupoOpciones) -> bool:
    return grupo.tipo == 'ingrediente_removible' or (grupo.tipo == 'extra' and grupo.nombre == 'Adicionales')


def _grupo_equivalente(grupo, candidatos):
    for candidato in candidatos:
        if candidato.tipo != grupo.tipo:
            continue
        if grupo.tipo == 'ingrediente_removible' or candidato.nombre == grupo.nombre:
            return candidato
    return None


def _clonar_grupo(cliente_id: int, grupo: GastronomiaGrupoOpciones, producto_id: int) -> GastronomiaGrupoOpciones:
    copia = GastronomiaGrupoOpciones(
        cliente_id=int(cliente_id),
        producto_id=int(producto_id),
        nombre=grupo.nombre,
        tipo=grupo.tipo,
        obligatorio=grupo.obligatorio,
        min_selecciones=grupo.min_selecciones,
        max_selecciones=grupo.max_selecciones,
        orden=grupo.orden,
        visible=grupo.visible,
    )
    db.session.add(copia)
    db.session.flush()
    for opcion in grupo.opciones.filter_by(activo=True).all():
        db.session.add(GastronomiaOpcionProducto(
            cliente_id=int(cliente_id),
            grupo_id=copia.id_grupo,
            nombre=opcion.nombre,
            precio_delta=opcion.precio_delta,
            imagen_url=opcion.imagen_url,
            disponible=opcion.disponible,
            visible=opcion.visible,
            orden=opcion.orden,
        ))
    db.session.flush()
    return copia


def _copiar_insumos_opciones(cliente_id: int, grupo_origen, grupo_destino) -> None:
    opciones_destino = {
        _clave(opcion.nombre): opcion
        for opcion in grupo_destino.opciones.filter_by(activo=True).all()
    }
    for opcion in grupo_origen.opciones.filter_by(activo=True).all():
        par = opciones_destino.get(_clave(opcion.nombre))
        if not par:
            continue
        ya_vinculados = {
            item.insumo_id
            for item in GastronomiaOpcionInsumo.query.filter_by(cliente_id=int(cliente_id), opcion_id=par.id_opcion).all()
        }
        for vinculo in GastronomiaOpcionInsumo.query.filter_by(
            cliente_id=int(cliente_id), opcion_id=opcion.id_opcion, activo=True,
        ).all():
            if vinculo.insumo_id in ya_vinculados:
                continue
            db.session.add(GastronomiaOpcionInsumo(
                cliente_id=int(cliente_id),
                opcion_id=par.id_opcion,
                insumo_id=vinculo.insumo_id,
                cantidad_delta=vinculo.cantidad_delta,
            ))


def _clave(nombre: str | None) -> str:
    return (nombre or '').strip().lower()
