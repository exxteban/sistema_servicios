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

La API pide un registro por tipo de documento aunque el número sea el mismo.
En el motor propio el timbrado es uno solo para todo, así que por defecto se
cargan juntos factura y nota de crédito, y si igual falta el de la NC se copia
del de factura al emitirla (ver `resolver_timbrado_nc`).
"""
import re
from datetime import datetime

from facturacion_electronica import AMBIENTE_PRODUCCION, TIPO_FACTURA, TIPO_NOTA_CREDITO
from facturacion_electronica.services.proveedores.api_emisor import actualizar_perfil_remoto
from facturacion_electronica.services.proveedores.api_perfil import (
    AMBIENTES_API,
    normalizar_codigo,
    obtener_perfil,
    resolver_timbrado,
    seleccionar_timbrado,
)

TIPO_AMBOS = 'ambos'
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

    valor_tipo = (form.get('tipo_documento') or '').strip()
    try:
        tipo = TIPO_FACTURA if valor_tipo in ('', TIPO_AMBOS) else int(valor_tipo)
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

    # Sin ambiente la API lo guarda en el del modo actual: un timbrado de
    # producción cargado estando en test quedaba como de test y, al pasar a
    # producción, la emisión respondía 422 `stamp_environment_mismatch`.
    ambiente = (form.get('ambiente_api') or '').strip().lower()
    if ambiente:
        if ambiente not in AMBIENTES_API:
            return None, 'Ambiente del timbrado inválido.'
        item['environment'] = ambiente

    inicial = (form.get('initial_number') or '').strip()
    if inicial:
        if not re.fullmatch(r'\d{1,7}', inicial) or int(inicial) < 1:
            return None, 'El número inicial va de 1 a 9999999.'
        item['initial_number'] = inicial.zfill(7)
    return item, None


def copia_para_nota_credito(timbrado):
    """El mismo timbrado como registro de NC.

    Sin `initial_number`: el de la factura es el piso de *su* rango, y la NC
    numera aparte. Vacío, la API usa el suyo.
    """
    item = {
        'number': str(timbrado.get('number') or '').strip(),
        'establishment': normalizar_codigo(timbrado.get('establishment')),
        'expedition_point': normalizar_codigo(timbrado.get('expedition_point')),
        'document_type': TIPO_NOTA_CREDITO,
        'valid_from': str(timbrado.get('valid_from') or '')[:10],
    }
    if timbrado.get('environment'):
        item['environment'] = timbrado['environment']
    if timbrado.get('valid_to'):
        item['valid_to'] = str(timbrado['valid_to'])[:10]
    return item


def armar_timbrados(form):
    """Los items a subir: el elegido, o factura + NC si se eligió "ambos"."""
    item, error = armar_timbrado(form)
    if error:
        return None, error
    if (form.get('tipo_documento') or TIPO_AMBOS).strip() != TIPO_AMBOS:
        return [item], None
    return [item, copia_para_nota_credito(item)], None


def resolver_timbrado_nc(config, perfil):
    """`resolver_timbrado` de NC, copiando el de factura si la API no tiene ninguno.

    Sólo cuando para nuestro punto no hay *ningún* timbrado de NC y sí uno de
    factura vigente: si hay uno de NC con fecha a futuro, eso es un dato
    cargado a propósito y no se pisa. Devuelve (timbrado_id, error).
    """
    timbrado_id, error = resolver_timbrado(config, perfil, TIPO_NOTA_CREDITO)
    if not error:
        return timbrado_id, None
    estab = normalizar_codigo(config.establecimiento)
    punto = normalizar_codigo(config.punto_expedicion)
    factura, _del_punto, _otros = seleccionar_timbrado(perfil, estab, punto, TIPO_FACTURA)
    _nc, nc_del_punto, _otros_nc = seleccionar_timbrado(perfil, estab, punto, TIPO_NOTA_CREDITO)
    if factura is None or nc_del_punto:
        return None, error

    _resumen, error_carga = actualizar_perfil_remoto(
        config, {'stamps': [copia_para_nota_credito(factura)]},
    )
    if error_carga:
        return None, f'{error} (No se pudo copiar el de factura: {error_carga})'
    perfil, error_perfil = obtener_perfil(config)
    if error_perfil:
        return None, error_perfil
    return resolver_timbrado(config, perfil, TIPO_NOTA_CREDITO)


def cargar_timbrado(config, form):
    """Sube el timbrado a la API y resincroniza. Devuelve (resumen, error)."""
    items, error = armar_timbrados(form)
    if error:
        return None, error

    item = items[0]
    if item.get('environment') == 'prod' and item['number'] == (config.ruc or '').strip():
        return None, (
            f'{item["number"]} es el RUC sin dígito verificador: es el timbrado de prueba y '
            'SIFEN lo rechaza en producción. Cargá el número de timbrado real.'
        )
    resumen, error = actualizar_perfil_remoto(config, {'stamps': items})
    if error:
        return None, f'La API no aceptó el timbrado. {error}'
    tipos = ' (factura y nota de crédito)' if len(items) > 1 else ''
    ambiente = {'prod': ' de producción', 'test': ' de prueba'}.get(item.get('environment'), '')
    # `resumen` nombra el timbrado que se usa hoy, que no es el recién cargado
    # si se cargó el de producción estando todavía en prueba.
    en_prod = config.ambiente == AMBIENTE_PRODUCCION
    espera = ''
    if item.get('environment') == 'prod' and not en_prod:
        espera = (' Se va a usar cuando el proveedor pase la empresa a producción; '
                  'mientras tanto se sigue con el de prueba.')
    return (
        f'Timbrado {item["number"]}{tipos}{ambiente} cargado en la API para '
        f'{item["establishment"]}-{item["expedition_point"]}.{espera} {resumen}'
    ), None
