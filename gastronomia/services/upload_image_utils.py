"""Guardado y borrado seguro de imagenes subidas bajo una raiz de `static/`.

Comun a las imagenes del menu y a las fotos de encargos: cada servicio pasa su
propia raiz, y el borrado nunca sale de esa raiz.
"""
from __future__ import annotations

import os

from app.utils.imagenes import procesar_y_guardar_imagen


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def extension_permitida(filename: str) -> bool:
    nombre = (filename or '').strip().lower()
    return '.' in nombre and nombre.rsplit('.', 1)[1] in ALLOWED_IMAGE_EXTENSIONS


def guardar_imagen_en_raiz(
    archivo,
    static_folder: str,
    raiz: tuple[str, ...],
    cliente_id: int,
    prefijo: str,
    *,
    max_size=(1400, 1400),
    calidad: int = 82,
) -> str:
    """Guarda la imagen en `static/<raiz>/<cliente_id>/` y devuelve su URL `/static/...`."""
    carpeta_destino = os.path.join(static_folder, *raiz, str(int(cliente_id)))
    nombre_final = procesar_y_guardar_imagen(
        archivo,
        carpeta_destino,
        prefijo=f'{prefijo}_{int(cliente_id)}',
        max_size=max_size,
        calidad=calidad,
    )
    return '/static/' + '/'.join([*raiz, str(int(cliente_id)), nombre_final])


def eliminar_imagen_en_raiz(url_imagen: str, static_folder: str, raiz: tuple[str, ...]) -> bool:
    """Borra el archivo de una URL `/static/...` solo si vive dentro de `raiz`."""
    if not url_imagen or not static_folder:
        return False
    prefijo = '/static/'
    if not url_imagen.startswith(prefijo):
        return False

    relativo = url_imagen[len(prefijo):].replace('/', os.sep)
    ruta_absoluta = os.path.abspath(os.path.join(static_folder, relativo))
    static_absoluto = os.path.abspath(static_folder)
    base_uploads = os.path.abspath(os.path.join(static_folder, *raiz))

    try:
        if os.path.commonpath([static_absoluto, ruta_absoluta]) != static_absoluto:
            return False
        if os.path.commonpath([base_uploads, ruta_absoluta]) != base_uploads:
            return False
    except ValueError:
        return False

    if not os.path.isfile(ruta_absoluta):
        return False

    os.remove(ruta_absoluta)
    return True
