"""Fotos de referencia de encargos (adaptador delgado sobre `upload_image_utils`).

Las fotos van en `static/tienda_uploads/gastronomia/encargos/<cliente_id>/`,
separadas de las del menu. No se publican en la tienda ni en la TV.
Ver plan_pasteleria.md, Fase 1, "Fotos: como se reutiliza lo existente".
"""
from __future__ import annotations

from flask import current_app

from app import db
from gastronomia.encargo_models import GastronomiaPedidoFoto
from gastronomia.models import GastronomiaPedido
from gastronomia.services.encargo_service import exigir_encargos_habilitados, obtener_encargo
from gastronomia.services.pasteleria_flags import parametros_encargos
from gastronomia.services.upload_image_utils import (
    eliminar_imagen_en_raiz,
    extension_permitida,
    guardar_imagen_en_raiz,
)


ENCARGOS_UPLOAD_ROOT = ('tienda_uploads', 'gastronomia', 'encargos')
ESTADOS_SIN_FOTOS = {'cancelado', 'cobrado'}
# Fotos de celular: se guardan algo mas grandes que las del menu para ver detalles de la torta.
MAX_LADO_FOTO = (1600, 1600)


def listar_fotos_encargo(pedido: GastronomiaPedido) -> list[GastronomiaPedidoFoto]:
    return (
        pedido.fotos
        .filter(GastronomiaPedidoFoto.cliente_id == int(pedido.cliente_id))
        .order_by(GastronomiaPedidoFoto.orden.asc(), GastronomiaPedidoFoto.id_foto.asc())
        .all()
    )


def agregar_foto_encargo(
    cliente_id: int,
    usuario_id: int | None,
    pedido_id: int,
    archivo,
    static_folder: str,
) -> GastronomiaPedidoFoto:
    exigir_encargos_habilitados(cliente_id)
    pedido = obtener_encargo(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Encargo no encontrado.')
    if pedido.estado in ESTADOS_SIN_FOTOS or pedido.pago:
        raise ValueError('Este encargo ya no admite fotos.')
    if archivo is None or not getattr(archivo, 'filename', ''):
        raise ValueError('Selecciona una foto.')
    if not extension_permitida(archivo.filename):
        raise ValueError('La foto debe ser PNG, JPG, JPEG, WEBP o GIF.')

    fotos = listar_fotos_encargo(pedido)
    tope = parametros_encargos(cliente_id)['max_fotos']
    if len(fotos) >= tope:
        raise ValueError(f'El encargo admite hasta {tope} foto(s).')

    try:
        url = guardar_imagen_en_raiz(
            archivo, static_folder, ENCARGOS_UPLOAD_ROOT, cliente_id, 'encargo', max_size=MAX_LADO_FOTO,
        )
    except ValueError as exc:
        raise ValueError('El archivo no es una imagen valida o es demasiado grande.') from exc

    foto = GastronomiaPedidoFoto(
        cliente_id=int(cliente_id),
        pedido_id=int(pedido.id_pedido),
        usuario_id=int(usuario_id) if usuario_id else None,
        url=url,
        orden=max((int(f.orden or 0) for f in fotos), default=-1) + 1,
    )
    db.session.add(foto)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        eliminar_imagen_en_raiz(url, static_folder, ENCARGOS_UPLOAD_ROOT)
        raise
    return foto


def eliminar_foto_encargo(cliente_id: int, pedido_id: int, foto_id: int, static_folder: str) -> None:
    """Borra una foto. No exige el flag: con encargos apagados se debe poder limpiar igual."""
    foto = GastronomiaPedidoFoto.query.filter_by(
        cliente_id=int(cliente_id),
        pedido_id=int(pedido_id),
        id_foto=int(foto_id),
    ).first()
    if not foto:
        raise ValueError('Foto no encontrada.')
    url = foto.url
    db.session.delete(foto)
    db.session.commit()
    eliminar_imagen_en_raiz(url, static_folder, ENCARGOS_UPLOAD_ROOT)


def eliminar_fotos_encargo(pedido: GastronomiaPedido, static_folder: str | None = None) -> int:
    """Borra todas las fotos de un encargo (al cancelarlo). Un archivo que falla no frena la cancelacion."""
    carpeta = static_folder or current_app.static_folder
    fotos = listar_fotos_encargo(pedido)
    if not fotos:
        return 0
    urls = [foto.url for foto in fotos]
    for foto in fotos:
        db.session.delete(foto)
    db.session.commit()
    for url in urls:
        try:
            eliminar_imagen_en_raiz(url, carpeta, ENCARGOS_UPLOAD_ROOT)
        except OSError:
            current_app.logger.exception('No se pudo borrar la foto de encargo %s', url)
    return len(urls)

