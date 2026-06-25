import os
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from app import db
from facturacion_electronica import AMBIENTE_PRODUCCION, AMBIENTE_TEST
from facturacion_electronica.models import FacturacionElectronicaConfig
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


def guardar_configuracion(form, archivo_cert=None):
    config = obtener_configuracion()

    for campo in CAMPOS_TEXTO:
        valor = (form.get(campo) or '').strip()
        setattr(config, campo, valor or None)

    config.departamento_desc = geo.descripcion_departamento(config.departamento_codigo)
    config.distrito_desc = geo.descripcion_distrito(config.distrito_codigo)
    config.ciudad_desc = geo.descripcion_ciudad(config.ciudad_codigo)

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

    nueva_password = form.get('cert_password')
    if nueva_password:
        config.cert_password = cifrar(nueva_password)

    error_cert = None
    if archivo_cert is not None:
        _ok, error_cert = guardar_certificado(config, archivo_cert)

    db.session.commit()
    return config, error_cert
