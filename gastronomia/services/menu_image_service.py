"""Persistencia de imagenes para productos del menu gastronomico."""
from __future__ import annotations

import os

from app.utils.imagenes import procesar_y_guardar_imagen


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
GASTRONOMIA_MENU_UPLOAD_ROOT = ('tienda_uploads', 'gastronomia', 'menu')


def extension_permitida(filename: str) -> bool:
    nombre = (filename or '').strip().lower()
    return '.' in nombre and nombre.rsplit('.', 1)[1] in ALLOWED_IMAGE_EXTENSIONS


def guardar_imagen_menu(archivo, static_folder: str, cliente_id: int, prefijo: str) -> str:
    carpeta_destino = os.path.join(
        static_folder,
        *GASTRONOMIA_MENU_UPLOAD_ROOT,
        str(int(cliente_id)),
    )
    nombre_final = procesar_y_guardar_imagen(
        archivo,
        carpeta_destino,
        prefijo=f'{prefijo}_{int(cliente_id)}',
        max_size=(1400, 1400),
        calidad=82,
    )
    return '/static/{}/{}/{}/{}/{}'.format(
        GASTRONOMIA_MENU_UPLOAD_ROOT[0],
        GASTRONOMIA_MENU_UPLOAD_ROOT[1],
        GASTRONOMIA_MENU_UPLOAD_ROOT[2],
        int(cliente_id),
        nombre_final,
    )


def guardar_imagen_producto_menu(archivo, static_folder: str, cliente_id: int) -> str:
    return guardar_imagen_menu(archivo, static_folder, cliente_id, 'gastro_menu')


def guardar_imagen_opcion_menu(archivo, static_folder: str, cliente_id: int) -> str:
    return guardar_imagen_menu(archivo, static_folder, cliente_id, 'gastro_opcion')


def eliminar_imagen_producto_menu(url_imagen: str, static_folder: str) -> bool:
    if not url_imagen or not static_folder:
        return False
    prefijo = '/static/'
    if not url_imagen.startswith(prefijo):
        return False

    relativo = url_imagen[len(prefijo):].replace('/', os.sep)
    ruta_absoluta = os.path.abspath(os.path.join(static_folder, relativo))
    static_absoluto = os.path.abspath(static_folder)
    base_uploads = os.path.abspath(os.path.join(static_folder, *GASTRONOMIA_MENU_UPLOAD_ROOT))

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
