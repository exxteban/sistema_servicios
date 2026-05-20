from __future__ import annotations

import mimetypes
import os
import uuid
from datetime import date

from werkzeug.utils import secure_filename


ALLOWED_COMPROBANTE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'pdf'}


def extension_comprobante_permitida(filename: str) -> bool:
    nombre = (filename or '').strip().lower()
    return '.' in nombre and nombre.rsplit('.', 1)[1] in ALLOWED_COMPROBANTE_EXTENSIONS


def _uploads_root(project_root: str) -> str:
    return os.path.abspath(os.path.join(project_root, 'uploads', 'gastos_corrientes', 'comprobantes'))


def _safe_storage_key(storage_key: str) -> str:
    return (storage_key or '').replace('\\', '/').lstrip('/')


def guardar_comprobante_pago(
    archivo,
    project_root: str,
    *,
    fecha_referencia: date,
    pago_id: int,
) -> dict:
    nombre_original = os.path.basename((archivo.filename or '').strip())
    if not extension_comprobante_permitida(nombre_original):
        raise ValueError('extension_invalida')

    extension = os.path.splitext(nombre_original)[1].lower()
    fecha_dir = fecha_referencia.strftime('%Y/%m')
    carpeta_destino = os.path.join(_uploads_root(project_root), *fecha_dir.split('/'))
    os.makedirs(carpeta_destino, exist_ok=True)

    nombre_base = secure_filename(os.path.splitext(nombre_original)[0])[:40] or 'comprobante'
    nombre_archivo = f'pago_{int(pago_id)}_{uuid.uuid4().hex[:8]}_{nombre_base}{extension}'
    ruta_absoluta = os.path.abspath(os.path.join(carpeta_destino, nombre_archivo))
    raiz_uploads = _uploads_root(project_root)

    try:
        if os.path.commonpath([raiz_uploads, ruta_absoluta]) != raiz_uploads:
            raise ValueError('ruta_invalida')
    except ValueError as exc:
        raise ValueError('ruta_invalida') from exc

    archivo.save(ruta_absoluta)
    mime_type = mimetypes.guess_type(nombre_archivo)[0] or 'application/octet-stream'
    storage_key = os.path.relpath(ruta_absoluta, raiz_uploads).replace(os.sep, '/')
    return {
        'storage_key': storage_key,
        'nombre_original': nombre_original[:255] or nombre_archivo,
        'mime_type': mime_type,
    }


def resolver_ruta_comprobante(storage_key: str | None, project_root: str) -> str | None:
    clave = _safe_storage_key(storage_key or '')
    if not clave:
        return None

    raiz_uploads = _uploads_root(project_root)
    ruta_absoluta = os.path.abspath(os.path.join(raiz_uploads, clave.replace('/', os.sep)))
    try:
        if os.path.commonpath([raiz_uploads, ruta_absoluta]) != raiz_uploads:
            return None
    except ValueError:
        return None

    if not os.path.isfile(ruta_absoluta):
        return None
    return ruta_absoluta


def eliminar_comprobante_pago(storage_key: str | None, project_root: str) -> bool:
    ruta_absoluta = resolver_ruta_comprobante(storage_key, project_root)
    if not ruta_absoluta:
        return False
    os.remove(ruta_absoluta)
    return True
