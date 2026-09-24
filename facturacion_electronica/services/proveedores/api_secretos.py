"""Carga del certificado y el CSC del emisor en la API externa.

En modo API la firma vive del lado del proveedor. Estas funciones la mandan
directo desde la pantalla de configuración (`PUT /sifen/me/certificate/` y
`PUT /sifen/me/csc/`, scope `configure`) para que el `.p12` no tenga que viajar
por chat o mail hasta el proveedor.

Nada de esto se guarda de este lado: el archivo y la contraseña se leen del
request, se reenvían y se descartan. La API valida (contraseña, vencimiento,
RUC del certificado) y guarda cifrado en el ambiente que corresponde a su
`sifen_mode`.
"""
import base64
import re

from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_perfil import olvidar_perfil

# Límite del lado de la API (400 si el .p12 decodificado lo supera).
MAX_CERTIFICADO_BYTES = 64 * 1024
EXTENSIONES_CERTIFICADO = ('.p12', '.pfx')


def _leer_certificado(archivo):
    """Devuelve (bytes, error) del archivo subido, sin tocar el disco."""
    nombre = (getattr(archivo, 'filename', '') or '').strip()
    if not nombre:
        return None, 'Elegí el archivo del certificado (.p12 / .pfx).'
    if not nombre.lower().endswith(EXTENSIONES_CERTIFICADO):
        return None, 'El certificado tiene que ser un archivo .p12 o .pfx.'
    contenido = archivo.read(MAX_CERTIFICADO_BYTES + 1)
    if not contenido:
        return None, 'El archivo del certificado está vacío.'
    if len(contenido) > MAX_CERTIFICADO_BYTES:
        return None, 'El certificado supera los 64 KB que acepta la API.'
    return contenido, None


def _resumen_certificado(respuesta):
    certificado = (respuesta or {}).get('certificate') or {}
    partes = ['Certificado cargado en la API.']
    ruc = certificado.get('ruc_in_cert')
    if ruc:
        partes.append(f'RUC del certificado: {ruc}.')
    vence = (certificado.get('not_after') or '')[:10]
    if vence:
        partes.append(f'Vence el {vence}.')
    return ' '.join(partes)


def subir_certificado(config, archivo, password):
    """Manda el .p12 a la API. Devuelve (resumen, error)."""
    contenido, error = _leer_certificado(archivo)
    if error:
        return None, error
    respuesta, error = api_client.solicitar(
        config, 'PUT', '/sifen/me/certificate/',
        json={
            'p12_base64': base64.b64encode(contenido).decode('ascii'),
            'password': password or '',
        },
    )
    if error:
        return None, f'La API no aceptó el certificado. {error}'
    # El perfil cacheado todavía dice "sin certificado".
    olvidar_perfil()
    return _resumen_certificado(respuesta), None


def subir_csc(config, csc_id, csc):
    """Manda el CSC y su id a la API. Devuelve (resumen, error)."""
    csc_id = (csc_id or '').strip()
    csc = (csc or '').strip()
    if not re.fullmatch(r'\d{4}', csc_id):
        return None, 'El ID del CSC son 4 dígitos (por ejemplo 0001).'
    if not csc:
        return None, 'Falta el CSC.'
    _respuesta, error = api_client.solicitar(
        config, 'PUT', '/sifen/me/csc/', json={'csc_id': csc_id, 'csc': csc},
    )
    if error:
        return None, f'La API no aceptó el CSC. {error}'
    olvidar_perfil()
    return 'CSC cargado en la API.', None
