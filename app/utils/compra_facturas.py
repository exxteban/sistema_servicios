import os

from app.utils.imagenes import procesar_y_guardar_imagen


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def extension_permitida(filename: str) -> bool:
    nombre = (filename or '').strip().lower()
    return '.' in nombre and nombre.rsplit('.', 1)[1] in ALLOWED_IMAGE_EXTENSIONS


def guardar_factura_compra(archivo, static_folder: str, fecha_compra, id_compra: int) -> str:
    fecha_dir = fecha_compra.strftime('%Y/%m/%d')
    carpeta_destino = os.path.join(
        static_folder,
        'tienda_uploads',
        'compras',
        'facturas',
        *fecha_dir.split('/'),
    )
    nombre_final = procesar_y_guardar_imagen(
        archivo,
        carpeta_destino,
        prefijo=f'compra_{id_compra}_factura',
        max_size=(1800, 1800),
        calidad=82,
    )
    return f'/static/tienda_uploads/compras/facturas/{fecha_dir}/{nombre_final}'


def eliminar_factura_compra(url_factura: str, static_folder: str) -> bool:
    if not url_factura or not static_folder:
        return False
    prefijo = '/static/'
    if not url_factura.startswith(prefijo):
        return False

    relativo = url_factura[len(prefijo):].replace('/', os.sep)
    ruta_absoluta = os.path.abspath(os.path.join(static_folder, relativo))
    static_absoluto = os.path.abspath(static_folder)

    try:
        if os.path.commonpath([static_absoluto, ruta_absoluta]) != static_absoluto:
            return False
    except ValueError:
        return False

    if not os.path.isfile(ruta_absoluta):
        return False

    os.remove(ruta_absoluta)
    return True
