"""Carga de un timbrado en la API externa (`PUT /sifen/me/` con `stamps[]`).

Contrato del lado de la API:
- Requiere `If-Match` con el `version` del último `GET /sifen/me/` (lock
  optimista; si otro lo cambió en el medio, 409 y hay que reintentar).
- Los timbrados se hacen upsert por (número, establecimiento, punto, tipo) y
  **nunca se borran**: cargar dos veces el mismo corrige sus fechas; cargar uno
  con otro número agrega otro.
- El RUC no se toca desde acá: el cambio de identidad fiscal es sólo por el
  admin del proveedor.

Después de cargarlo se trae el perfil de nuevo, así el timbrado, el ambiente y
el piso de numeración quedan copiados igual que con "Traer datos del emisor".
"""
import re
from datetime import datetime

from facturacion_electronica import TIPO_FACTURA, TIPO_NOTA_CREDITO
from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_perfil import (
    aplicar_perfil_al_config,
    obtener_perfil,
    olvidar_perfil,
)

TIPOS_TIMBRADO = (
    (TIPO_FACTURA, 'Factura electrónica'),
    (TIPO_NOTA_CREDITO, 'Nota de crédito electrónica'),
)


def _fecha(valor):
    texto = (valor or '').strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return False


def armar_timbrado(form):
    """Valida el formulario y arma el item de `stamps[]`. Devuelve (item, error).

    Se valida acá lo mismo que valida la API (8 dígitos, 3 dígitos, tipos)
    para que el error salga en castellano claro y sin ida y vuelta.
    """
    numero = (form.get('timbrado_numero') or '').strip()
    if not re.fullmatch(r'\d{8}', numero):
        return None, 'El número de timbrado son 8 dígitos (en test, el RUC sin dígito verificador).'

    codigos = {}
    for campo, etiqueta in (('establecimiento', 'establecimiento'), ('punto_expedicion', 'punto de expedición')):
        valor = (form.get(campo) or '').strip()
        if not re.fullmatch(r'\d{1,3}', valor):
            return None, f'El {etiqueta} son hasta 3 dígitos (por ejemplo 001).'
        codigos[campo] = valor.zfill(3)

    try:
        tipo = int(form.get('tipo_documento') or TIPO_FACTURA)
    except (TypeError, ValueError):
        tipo = 0
    if tipo not in dict(TIPOS_TIMBRADO):
        return None, 'Tipo de documento de timbrado inválido.'

    desde = _fecha(form.get('valid_from'))
    if not desde:
        return None, 'Falta la fecha de inicio de vigencia del timbrado.'
    hasta = _fecha(form.get('valid_to'))
    if hasta is False:
        return None, 'La fecha de fin de vigencia es inválida.'
    if hasta and hasta < desde:
        return None, 'El fin de vigencia no puede ser anterior al inicio.'

    item = {
        'number': numero,
        'establishment': codigos['establecimiento'],
        'expedition_point': codigos['punto_expedicion'],
        'document_type': tipo,
        'valid_from': desde.isoformat(),
    }
    if hasta:
        item['valid_to'] = hasta.isoformat()

    inicial = (form.get('initial_number') or '').strip()
    if inicial:
        if not re.fullmatch(r'\d{1,7}', inicial) or int(inicial) < 1:
            return None, 'El número inicial va de 1 a 9999999.'
        item['initial_number'] = inicial.zfill(7)
    return item, None


def cargar_timbrado(config, form):
    """Sube el timbrado a la API y resincroniza. Devuelve (resumen, error)."""
    item, error = armar_timbrado(form)
    if error:
        return None, error

    perfil, error = obtener_perfil(config, refrescar=True)
    if error:
        return None, error
    version = perfil.get('version')
    if version is None:
        return None, 'La API no informó la versión del perfil; no se puede cargar el timbrado.'

    _respuesta, error = api_client.solicitar(
        config, 'PUT', '/sifen/me/',
        json={'stamps': [item]},
        headers={'If-Match': str(version)},
    )
    if error:
        return None, f'La API no aceptó el timbrado. {error}'

    olvidar_perfil()
    perfil, error = obtener_perfil(config, refrescar=True)
    if error:
        return None, f'El timbrado se cargó, pero no se pudo releer el perfil: {error}'
    resumen = aplicar_perfil_al_config(config, perfil)
    return (
        f'Timbrado {item["number"]} cargado en la API para '
        f'{item["establishment"]}-{item["expedition_point"]}. {resumen}'
    ), None
