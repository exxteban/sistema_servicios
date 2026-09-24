import os
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from app import db
from facturacion_electronica import AMBIENTE_PRODUCCION, AMBIENTE_TEST
from facturacion_electronica.models import DocumentoElectronico, FacturacionElectronicaConfig
from facturacion_electronica.services import geo
from facturacion_electronica.services.crypto import cifrar


EXTENSIONES_CERT = {'.p12', '.pfx'}

CAMPOS_TEXTO = (
    'razon_social',
    'nombre_fantasia',
    'ruc',
    'dv_ruc',
    'tipo_contribuyente',
    'tipo_regimen',
    'timbrado_numero',
    'establecimiento',
    'punto_expedicion',
    'actividad_economica_codigo',
    'actividad_economica_desc',
    'departamento_codigo',
    'distrito_codigo',
    'ciudad_codigo',
    'direccion',
    'numero_casa',
    'telefono',
    'email',
    'csc',
    'csc_id',
)

# Vaciarlos a NULL rompe el INSERT/UPDATE: tienen default y no aceptan nulo.
CAMPOS_NO_NULOS = frozenset(('tipo_contribuyente', 'establecimiento', 'punto_expedicion'))

# Cómo se llama cada campo en la pantalla, para que el aviso hable el idioma
# del formulario y no el de la tabla.
ETIQUETAS_CAMPOS = {
    'razon_social': 'Razón social',
    'nombre_fantasia': 'Nombre de fantasía',
    'ruc': 'RUC',
    'dv_ruc': 'Dígito verificador',
    'timbrado_numero': 'Número de timbrado',
    'establecimiento': 'Establecimiento',
    'punto_expedicion': 'Punto de expedición',
    'actividad_economica_codigo': 'Código de actividad económica',
    'actividad_economica_desc': 'Descripción de la actividad',
    'direccion': 'Dirección',
    'numero_casa': 'Número de casa',
    'telefono': 'Teléfono',
    'email': 'Correo electrónico',
    'csc': 'CSC',
    'csc_id': 'ID del CSC',
}

# Largo típico de un CSC: sirve para reconocer el error de cargarlo en el campo
# del ID, que es el que se cambia de lugar en la práctica.
LARGO_CSC = 32


def _errores_de_largo(config, campos=None):
    """Campos cuyo valor no entra en su columna.

    MySQL estricto **rechaza** el UPDATE entero (error 1406) y SQLite lo acepta
    truncando, así que la suite nunca ve el problema y el usuario se come un
    500 sin saber qué campo tocar. Se valida acá, antes de commitear.

    Sin `campos` mira todas las columnas de texto, incluidas las que no vienen
    crudas del formulario: la contraseña del certificado y el secreto de la API
    se guardan cifrados, y el cifrado los hace bastante más largos.
    """
    columnas = FacturacionElectronicaConfig.__table__.columns
    if campos is None:
        campos = [
            nombre for nombre, columna in columnas.items()
            if getattr(getattr(columna, 'type', None), 'length', None)
        ]
    errores = []
    for campo in campos:
        columna = columnas.get(campo)
        maximo = getattr(getattr(columna, 'type', None), 'length', None)
        valor = getattr(config, campo, None)
        if maximo and valor and len(valor) > maximo:
            errores.append((campo, len(valor), maximo))
    return errores


def _mensaje_de_largo(errores):
    partes = []
    for campo, largo, maximo in errores:
        etiqueta = ETIQUETAS_CAMPOS.get(campo, campo)
        partes.append(f'"{etiqueta}" tiene {largo} caracteres y el máximo es {maximo}')
    mensaje = 'No se guardó nada: ' + '; '.join(partes) + '.'
    if any(campo == 'csc_id' and largo == LARGO_CSC for campo, largo, _maximo in errores):
        mensaje += (
            ' Parece que el CSC y su ID están cambiados de lugar: el ID es el número '
            'del par que entrega la DNIT (1 o 2, se carga como 0001) y la cadena '
            'larga va en el campo CSC.'
        )
    return mensaje


def obtener_configuracion():
    return FacturacionElectronicaConfig.obtener()


def _carpeta_certificados():
    carpeta = os.path.join(current_app.instance_path, 'fe_certs')
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def guardar_certificado(config, archivo):
    """Guarda el .p12/.pfx en instance/fe_certs y devuelve (ok, error)."""
    if not archivo or not (archivo.filename or '').strip():
        return False, None

    nombre = secure_filename(archivo.filename)
    extension = os.path.splitext(nombre)[1].lower()
    if extension not in EXTENSIONES_CERT:
        return False, 'El certificado debe ser un archivo .p12 o .pfx.'

    carpeta = _carpeta_certificados()
    destino = os.path.join(carpeta, f'certificado{extension}')

    anterior = config.cert_path
    archivo.save(destino)

    if anterior and anterior != destino and os.path.exists(anterior):
        try:
            os.remove(anterior)
        except OSError:
            pass

    config.cert_path = destino
    config.cert_nombre_original = nombre
    return True, None


def hay_documentos_transmitidos():
    """¿Hay algún DE que ya exista fuera de esta instalación?

    Es lo único que ata la instalación a un proveedor. Las pruebas del motor
    propio que quedaron en generado/firmado/error nunca salieron y no cuentan.
    En modo API, `firmado` es PENDING_BATCH: el documento ya está del otro
    lado con CDC y su pipeline lo transmite solo. Eso se ve por
    `api_documento_id`, no metiendo 'firmado' en ESTADOS_TRANSMITIDOS.
    Lo transmitido en ambiente de prueba tampoco cuenta: una demo tiene que
    poder pasar de un proveedor al otro.
    """
    from facturacion_electronica.services.guarda import filtro_documentos_en_proveedor

    return DocumentoElectronico.query.filter(
        filtro_documentos_en_proveedor()
    ).first() is not None


def _olvidar_cache_api(config):
    """Token y perfil viven cacheados por proceso; si cambian las credenciales
    o la URL, el cache viejo haría fallar la próxima emisión sin explicación."""
    from facturacion_electronica.services.proveedores import api_client
    from facturacion_electronica.services.proveedores.api import olvidar_perfil

    api_client.olvidar_token()
    olvidar_perfil()


def guardar_configuracion(form, archivo_cert=None):
    config = obtener_configuracion()

    proveedor = (form.get('proveedor') or config.proveedor or 'propio').strip().lower()
    if proveedor not in ('propio', 'api'):
        return config, 'Proveedor de facturación electrónica inválido.'
    if proveedor != (config.proveedor or 'propio') and hay_documentos_transmitidos():
        return config, (
            'No se puede cambiar de proveedor: ya hay documentos transmitidos a SIFEN en producción. '
            'Sus CDC y su protocolo pertenecen al proveedor que los emitió.'
        )
    config.proveedor = proveedor

    for campo in CAMPOS_TEXTO:
        if proveedor == 'api' and campo in ('csc', 'csc_id'):
            continue
        valor = (form.get(campo) or '').strip() or None
        if valor is None and campo in CAMPOS_NO_NULOS:
            continue
        setattr(config, campo, valor)

    errores_largo = _errores_de_largo(config, CAMPOS_TEXTO)
    if errores_largo:
        # Se deshace todo: guardar "lo que entra" dejaría media configuración
        # nueva y media vieja, que es peor que no guardar.
        db.session.rollback()
        return obtener_configuracion(), _mensaje_de_largo(errores_largo)

    config.departamento_desc = geo.descripcion_departamento(config.departamento_codigo)
    config.distrito_desc = geo.descripcion_distrito(config.distrito_codigo)
    config.ciudad_desc = geo.descripcion_ciudad(config.ciudad_codigo)

    if proveedor == 'propio':
        ambiente = (form.get('ambiente') or '').strip().lower()
        config.ambiente = ambiente if ambiente in (AMBIENTE_TEST, AMBIENTE_PRODUCCION) else AMBIENTE_TEST

    fecha_raw = (form.get('timbrado_fecha_inicio') or '').strip()
    if fecha_raw:
        try:
            config.timbrado_fecha_inicio = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except ValueError:
            config.timbrado_fecha_inicio = None
    else:
        config.timbrado_fecha_inicio = None

    if proveedor == 'api':
        config.api_url = (form.get('api_url') or '').strip() or None
        config.api_client_id = (form.get('api_client_id') or '').strip() or None
        # El secreto sólo se pisa si escribieron uno nuevo: el formulario lo
        # muestra vacío siempre (no se devuelve al navegador).
        secreto = (form.get('api_credenciales') or '').strip()
        if secreto:
            config.api_credenciales = cifrar(secreto)
        _olvidar_cache_api(config)
    else:
        nueva_password = form.get('cert_password')
        if nueva_password:
            config.cert_password = cifrar(nueva_password)

    # Segunda pasada, ahora sobre todo lo que se va a escribir: los campos
    # cifrados y la ruta del certificado no pasaron por la primera.
    errores_largo = _errores_de_largo(config)
    if errores_largo:
        db.session.rollback()
        return obtener_configuracion(), _mensaje_de_largo(errores_largo)

    error_cert = None
    if proveedor == 'propio' and archivo_cert is not None:
        _ok, error_cert = guardar_certificado(config, archivo_cert)

    db.session.commit()
    return config, error_cert
