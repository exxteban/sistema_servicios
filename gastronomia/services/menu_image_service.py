"""Persistencia de imagenes para productos del menu gastronomico."""
from __future__ import annotations

from gastronomia.services.upload_image_utils import (
    ALLOWED_IMAGE_EXTENSIONS,
    eliminar_imagen_en_raiz,
    extension_permitida,
    guardar_imagen_en_raiz,
)


GASTRONOMIA_MENU_UPLOAD_ROOT = ('tienda_uploads', 'gastronomia', 'menu')

__all__ = [
    'ALLOWED_IMAGE_EXTENSIONS',
    'GASTRONOMIA_MENU_UPLOAD_ROOT',
    'eliminar_imagen_producto_menu',
    'extension_permitida',
    'guardar_imagen_menu',
    'guardar_imagen_opcion_menu',
    'guardar_imagen_producto_menu',
]


def guardar_imagen_menu(archivo, static_folder: str, cliente_id: int, prefijo: str) -> str:
    return guardar_imagen_en_raiz(archivo, static_folder, GASTRONOMIA_MENU_UPLOAD_ROOT, cliente_id, prefijo)


def guardar_imagen_producto_menu(archivo, static_folder: str, cliente_id: int) -> str:
    return guardar_imagen_menu(archivo, static_folder, cliente_id, 'gastro_menu')


def guardar_imagen_opcion_menu(archivo, static_folder: str, cliente_id: int) -> str:
    return guardar_imagen_menu(archivo, static_folder, cliente_id, 'gastro_opcion')


def eliminar_imagen_producto_menu(url_imagen: str, static_folder: str) -> bool:
    return eliminar_imagen_en_raiz(url_imagen, static_folder, GASTRONOMIA_MENU_UPLOAD_ROOT)
