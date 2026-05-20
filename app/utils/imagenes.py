import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

CARD_IMAGE_SIZE = (480, 480)


def nombre_derivado_imagen(nombre_archivo: str, variante: str, extension: str = ".webp") -> str:
    nombre_seguro = secure_filename(os.path.basename(nombre_archivo or ""))
    base, _ = os.path.splitext(nombre_seguro)
    if not base:
        raise ValueError('nombre_imagen_invalido')
    return f"{base}__{variante}{extension}"


def _recortar_bordes(img: Image.Image) -> Image.Image:
    trabajo = img.convert("RGBA") if img.mode != "RGBA" else img.copy()
    bbox_alpha = trabajo.getchannel("A").getbbox()
    if bbox_alpha:
        trabajo = trabajo.crop(bbox_alpha)

    if trabajo.width == 0 or trabajo.height == 0:
        return img

    fondo = Image.new("RGBA", trabajo.size, trabajo.getpixel((0, 0)))
    diff = ImageChops.difference(trabajo, fondo)
    diff = ImageChops.add(diff, diff, 2.0, -12)
    bbox = diff.getbbox()
    if bbox:
        trabajo = trabajo.crop(bbox)

    return trabajo


def _max_image_pixels() -> int:
    raw_value = os.environ.get('MAX_IMAGE_PIXELS', '').strip()
    if raw_value.isdigit():
        return max(1_000_000, int(raw_value))
    return 80_000_000


def rotar_imagen_guardada(ruta_imagen: str, grados: int, calidad: int = 80) -> None:
    grados_normalizados = int(grados or 0) % 360
    if grados_normalizados == 0:
        return

    ruta_absoluta = os.path.abspath(ruta_imagen)
    if not os.path.isfile(ruta_absoluta):
        raise FileNotFoundError(ruta_absoluta)

    extension = os.path.splitext(ruta_absoluta)[1].lower()
    formato = 'WEBP' if extension == '.webp' else 'PNG' if extension == '.png' else 'JPEG'
    ruta_temporal = f'{ruta_absoluta}.tmp'

    try:
        with Image.open(ruta_absoluta) as img:
            img = ImageOps.exif_transpose(img)
            if img.width <= 0 or img.height <= 0:
                raise ValueError('imagen_invalida')
            if img.width * img.height > _max_image_pixels():
                raise ValueError('imagen_demasiado_grande')

            if formato == 'JPEG' and img.mode != 'RGB':
                img = img.convert('RGB')
            elif formato in ('PNG', 'WEBP') and img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')

            rotada = img.rotate(-grados_normalizados, expand=True, resample=Image.Resampling.BICUBIC)
            save_kwargs = {'optimize': True}
            if formato in ('WEBP', 'JPEG'):
                save_kwargs['quality'] = calidad

            rotada.save(ruta_temporal, format=formato, **save_kwargs)

        os.replace(ruta_temporal, ruta_absoluta)
    except (UnidentifiedImageError, OSError) as exc:
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)
        raise ValueError('imagen_invalida') from exc


def generar_derivado_imagen(
    ruta_origen: str,
    variante: str = "card",
    max_size=CARD_IMAGE_SIZE,
    calidad: int = 76,
) -> str:
    ruta_absoluta = os.path.abspath(ruta_origen)
    if not os.path.isfile(ruta_absoluta):
        raise FileNotFoundError(ruta_absoluta)

    nombre_derivado = nombre_derivado_imagen(os.path.basename(ruta_absoluta), variante)
    ruta_derivada = os.path.join(os.path.dirname(ruta_absoluta), nombre_derivado)
    ruta_temporal = f'{ruta_derivada}.tmp'

    try:
        with Image.open(ruta_absoluta) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            if width <= 0 or height <= 0:
                raise ValueError('imagen_invalida')
            if width * height > _max_image_pixels():
                raise ValueError('imagen_demasiado_grande')

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(ruta_temporal, format="WEBP", quality=calidad, optimize=True)

        os.replace(ruta_temporal, ruta_derivada)
    except (UnidentifiedImageError, OSError) as exc:
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)
        raise ValueError('imagen_invalida') from exc

    return nombre_derivado


def procesar_y_guardar_imagen(
    archivo,
    carpeta_destino,
    prefijo="",
    max_size=(1200, 1200),
    calidad=80,
    recortar_bordes=False,
    generar_card=False,
) -> str:
    """
    Procesa una imagen subida, la redimensiona si es necesario, 
    la convierte a formato WebP para optimizar espacio y la guarda.
    
    :param archivo: El archivo FileStorage de Flask.
    :param carpeta_destino: Ruta absoluta donde se guardará.
    :param prefijo: Prefijo opcional para el nombre del archivo.
    :param max_size: Tupla (ancho, alto) máximo permitido.
    :param calidad: Calidad de compresión (0-100).
    :return: Nombre del archivo guardado.
    """
    os.makedirs(carpeta_destino, exist_ok=True)
    
    ext = ".webp"
    timestamp = int(datetime.utcnow().timestamp())
    random_id = uuid.uuid4().hex[:8]
    
    nombre_base = f"{prefijo}_{timestamp}_{random_id}" if prefijo else f"{timestamp}_{random_id}"
    nombre_final = f"{nombre_base}{ext}"
    ruta_completa = os.path.join(carpeta_destino, nombre_final)
    
    try:
        with Image.open(archivo) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            if width <= 0 or height <= 0:
                raise ValueError('imagen_invalida')
            if width * height > _max_image_pixels():
                raise ValueError('imagen_demasiado_grande')

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if recortar_bordes:
                img = _recortar_bordes(img)

            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(ruta_completa, format="WEBP", quality=calidad, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError('imagen_invalida') from exc

    if generar_card:
        try:
            generar_derivado_imagen(ruta_completa)
        except (FileNotFoundError, PermissionError, ValueError):
            pass
        
    return nombre_final
