from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

LOGO_EXTENSIONES_PERMITIDAS = {'.png', '.jpg', '.jpeg', '.webp'}
LOGO_TAMANO_MAXIMO = 2 * 1024 * 1024


def guardar_logo_empresa(archivo, *, ruta_anterior: str = ''):
    if not archivo or not getattr(archivo, 'filename', ''):
        return None, None

    nombre_seguro = secure_filename(archivo.filename or '')
    extension = Path(nombre_seguro).suffix.lower()
    if extension not in LOGO_EXTENSIONES_PERMITIDAS:
        return None, 'Formato no permitido. Usa PNG, JPG, JPEG o WEBP.'

    try:
        archivo.stream.seek(0, 2)
        tamano = archivo.stream.tell()
        archivo.stream.seek(0)
    except Exception:
        tamano = 0
    if tamano > LOGO_TAMANO_MAXIMO:
        return None, 'El logo supera el tamaño máximo de 2 MB.'

    carpeta_destino = Path(current_app.root_path) / 'static' / 'uploads' / 'branding'
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    nombre_archivo = f'logo_empresa_{uuid4().hex}{extension}'
    ruta_destino = carpeta_destino / nombre_archivo
    try:
        archivo.save(ruta_destino)
    except PermissionError:
        return None, 'No se pudo guardar el logo por permisos del servidor. Ajusta permisos de escritura en app/static/uploads/branding.'
    except OSError:
        return None, 'No se pudo guardar el logo por un error del sistema de archivos. Verifica permisos y espacio disponible en disco.'

    ruta_relativa = f'uploads/branding/{nombre_archivo}'
    if ruta_anterior and ruta_anterior != ruta_relativa:
        try:
            static_base = Path(current_app.static_folder).resolve()
            branding_base = (static_base / 'uploads' / 'branding').resolve()
            archivo_anterior = (static_base / Path(ruta_anterior)).resolve()
            if str(archivo_anterior).startswith(str(branding_base)) and archivo_anterior.exists() and archivo_anterior.is_file():
                archivo_anterior.unlink()
        except Exception:
            pass

    return ruta_relativa, None
