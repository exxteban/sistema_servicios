"""Perfil fiscal, timbrados y readiness del emisor en la API externa.

`GET /sifen/me/` trae el emisor, los timbrados y `sifen_config` (certificado y
CSC). Se cachea por proceso: lo necesitan la emisión, la pantalla y el job.
"""
import threading
import time
from datetime import date, datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    AMBIENTE_TEST,
    TIPO_FACTURA as TIPO_DOC_FACTURA,
    TIPO_NOTA_CREDITO,
    TIPOS_EMITIBLES,
)
from facturacion_electronica.services.numeracion_service import sembrar_minimo
from facturacion_electronica.services.proveedores import api_client

TIPO_FACTURA = TIPO_DOC_FACTURA
NOMBRE_TIPO = {TIPO_DOC_FACTURA: 'factura', TIPO_NOTA_CREDITO: 'nota de crédito'}
CSC_CONFIGURADO = 'configured'

VIGENCIA_PERFIL_SEGUNDOS = 300
_PERFILES = {}
_CANDADO = threading.Lock()


def _clave_perfil(config):
    client_id, _secreto = api_client.credenciales(config)
    return (api_client.base_url(config), client_id)


def olvidar_perfil(config=None):
    """Sin argumento vacía el cache entero (ver api_client.olvidar_token)."""
    with _CANDADO:
        if config is None:
            _PERFILES.clear()
        else:
            _PERFILES.pop(_clave_perfil(config), None)


def normalizar_codigo(valor, default='001'):
    return ((valor or '').strip() or default).zfill(3)[-3:]


def obtener_perfil(config, refrescar=False):
    """Perfil fiscal de la empresa del token. Devuelve (perfil, error).

    De paso valida que el RUC de la API sea el mismo que el de esta
    instalación: con las credenciales equivocadas se estaría facturando a
    nombre de otro contribuyente y nada lo avisaría después.
    """
    clave = _clave_perfil(config)
    if not refrescar:
        with _CANDADO:
            cacheado = _PERFILES.get(clave)
        if cacheado and cacheado[1] > time.time():
            return cacheado[0], None

    perfil, error = api_client.solicitar(config, 'GET', '/sifen/me/')
    if error:
        return None, error
    if not isinstance(perfil, dict):
        return None, 'La API devolvió un perfil de emisor ilegible.'

    ruc_local = (config.ruc or '').strip()
    ruc_api = str(perfil.get('ruc') or '').strip()
    if ruc_local and ruc_api and ruc_local != ruc_api:
        return None, (
            f'El RUC de la API ({ruc_api}) no coincide con el de esta instalación '
            f'({ruc_local}). Revisá las credenciales antes de emitir.'
        )

    with _CANDADO:
        _PERFILES[clave] = (perfil, time.time() + VIGENCIA_PERFIL_SEGUNDOS)
    return perfil, None


def sincronizar_ambiente(config, perfil):
    """Copia el modo de la API a `config.ambiente` antes de congelarlo en el DE."""
    ambiente = AMBIENTE_PRODUCCION if perfil.get('sifen_mode') == 'production' else AMBIENTE_TEST
    if config.ambiente != ambiente:
        config.ambiente = ambiente
        db.session.commit()


def _parsear_fecha(valor):
    texto = str(valor or '').strip()[:10]
    if not texto:
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return None


def _timbrado_vigente(timbrado, hoy):
    """`StampProfile` no trae `valid_to`; si aparece, igual se respeta."""
    inicio = _parsear_fecha(timbrado.get('valid_from'))
    if inicio is not None and inicio > hoy:
        return False
    fin = _parsear_fecha(timbrado.get('valid_to'))
    if fin is not None and fin < hoy:
        return False
    return True


def _numero_timbrado(valor):
    try:
        return int(str(valor or '').strip() or 0)
    except (TypeError, ValueError):
        return 0


def _clave_eleccion(timbrado):
    """En una renovación gana el `valid_from` más reciente, después el número."""
    inicio = _parsear_fecha(timbrado.get('valid_from')) or date.min
    return (inicio, _numero_timbrado(timbrado.get('number')), str(timbrado.get('id') or ''))


def _candidatos_timbrado(perfil, establecimiento, punto, tipo_documento):
    del_punto = []
    otros = []
    for timbrado in perfil.get('stamps') or []:
        if int(timbrado.get('document_type') or 0) != tipo_documento:
            continue
        estab = normalizar_codigo(timbrado.get('establishment'))
        pto = normalizar_codigo(timbrado.get('expedition_point'))
        if (estab, pto) == (establecimiento, punto):
            del_punto.append(timbrado)
        else:
            otros.append(f'{estab}-{pto}')
    return del_punto, otros


def seleccionar_timbrado(perfil, establecimiento, punto, tipo_documento, hoy=None):
    """Timbrado vigente de ese tipo/punto, o (None, del_punto, otros)."""
    hoy = hoy or date.today()
    del_punto, otros = _candidatos_timbrado(perfil, establecimiento, punto, tipo_documento)
    vigentes = [t for t in del_punto if _timbrado_vigente(t, hoy)]
    if not vigentes:
        return None, del_punto, otros
    return max(vigentes, key=_clave_eleccion), del_punto, otros


def resolver_timbrado(config, perfil, tipo_documento=TIPO_FACTURA, hoy=None):
    """UUID del timbrado de ese tipo de documento para nuestro establecimiento/punto.

    Cada tipo tiene su propio timbrado del lado de la API: el de la nota de
    crédito es otro registro, no el de la factura. Si hay dos vigentes (una
    renovación sin `valid_to`), se elige el de `valid_from` más reciente.
    """
    establecimiento = normalizar_codigo(config.establecimiento)
    punto = normalizar_codigo(config.punto_expedicion)
    nombre = NOMBRE_TIPO.get(tipo_documento, f'tipo {tipo_documento}')
    elegido, del_punto, otros = seleccionar_timbrado(
        perfil, establecimiento, punto, tipo_documento, hoy=hoy,
    )
    if elegido is not None:
        return elegido.get('id'), None
    if not del_punto and not otros:
        return None, (
            f'La API no tiene ningún timbrado de {nombre} cargado para esta empresa. '
            'Hay que cargarlo del lado del proveedor antes de emitir.'
        )
    if del_punto:
        return None, (
            f'La API tiene timbrado de {nombre} para {establecimiento}-{punto}, '
            'pero ninguno está vigente todavía (la fecha de inicio es a futuro).'
        )
    return None, (
        f'La API no tiene timbrado de {nombre} para {establecimiento}-{punto}. '
        f'Los cargados para ese tipo son: {", ".join(sorted(set(otros)))}.'
    )


def congelar_identidad(documento, config, perfil, timbrado_id):
    """Ambiente y timbrado del momento de emisión, no los de la config actual.

    Tiene que correr **después** de `sincronizar_ambiente`: si se asigna
    antes, una factura de prueba queda grabada con el ambiente viejo y el
    KuDE, al reimprimirse en producción, pierde la leyenda.
    """
    documento.ambiente = config.ambiente
    numero = None
    for timbrado in perfil.get('stamps') or []:
        if str(timbrado.get('id') or '') == str(timbrado_id or ''):
            numero = str(timbrado.get('number') or '').strip()
            break
    documento.timbrado = numero or documento.timbrado or config.timbrado_numero
    db.session.commit()


def faltantes_locales(config):
    faltantes = []
    if not api_client.base_url(config):
        faltantes.append('URL de la API de facturación electrónica')
    client_id, secreto = api_client.credenciales(config)
    if not client_id:
        faltantes.append('Client ID de la API')
    if not secreto:
        faltantes.append('Client Secret de la API')
    if not config.establecimiento:
        faltantes.append('Establecimiento')
    if not config.punto_expedicion:
        faltantes.append('Punto de expedición')
    return faltantes


def faltantes_sifen_config(perfil):
    """Certificado y CSC viven en la API (`sifen_config` de `GET /sifen/me/`)."""
    faltantes = []
    sifen = perfil.get('sifen_config') if isinstance(perfil, dict) else None
    if not isinstance(sifen, dict):
        return ['Certificado digital en la API', 'CSC en la API']
    if not sifen.get('certificate'):
        faltantes.append('Certificado digital en la API')
    csc = (sifen.get('csc') or '').strip().lower()
    if csc != CSC_CONFIGURADO:
        faltantes.append('CSC en la API')
    return faltantes


def faltantes_readiness_api(config):
    """Lo local, y si eso está, certificado/CSC remotos del perfil.

    Pega a la red: va en la pantalla de configuración y antes de emitir, no
    en las compuertas del POS ni del job (ver `ProveedorFE.faltantes_configuracion`).
    """
    faltantes = faltantes_locales(config)
    if faltantes:
        return faltantes
    perfil, error = obtener_perfil(config)
    if error:
        faltantes.append(f'Perfil del emisor en la API: {error}')
        return faltantes
    return faltantes_sifen_config(perfil)


def _adoptar_timbrado_config(config, perfil):
    """El timbrado vigente de factura para nuestro punto, o el único que haya."""
    estab = normalizar_codigo(config.establecimiento)
    punto = normalizar_codigo(config.punto_expedicion)
    propio, _del_punto, _otros = seleccionar_timbrado(perfil, estab, punto, TIPO_FACTURA)
    if propio is None:
        timbrados = [
            t for t in (perfil.get('stamps') or [])
            if int(t.get('document_type') or 0) == TIPO_FACTURA
        ]
        if len(timbrados) == 1:
            propio = timbrados[0]
            config.establecimiento = normalizar_codigo(propio.get('establishment'))
            config.punto_expedicion = normalizar_codigo(propio.get('expedition_point'))
    if propio is None:
        return None
    config.timbrado_numero = str(propio.get('number') or '') or config.timbrado_numero
    vigencia = _parsear_fecha(propio.get('valid_from'))
    if vigencia:
        config.timbrado_fecha_inicio = vigencia
    return propio


def sembrar_correlativos(config, perfil):
    """Sube el correlativo local al piso de cada timbrado nuestro.

    `dNumIni` (`initial_number`) es el primer número que el timbrado reserva
    para ese establecimiento/punto, y no siempre es 1: un cliente que ya
    venía facturando arranca donde quedó. Nuestro contador nace en 0, así
    que sin esto la primera factura saldría 0000001, fuera del rango
    declarado, y SIFEN la rechaza sin que nada lo hubiera avisado antes.
    """
    estab = normalizar_codigo(config.establecimiento)
    punto = normalizar_codigo(config.punto_expedicion)
    sembrados = []
    for timbrado in perfil.get('stamps') or []:
        tipo = int(timbrado.get('document_type') or 0)
        if tipo not in TIPOS_EMITIBLES:
            continue
        if (normalizar_codigo(timbrado.get('establishment')),
                normalizar_codigo(timbrado.get('expedition_point'))) != (estab, punto):
            continue
        proximo = sembrar_minimo(estab, punto, timbrado.get('initial_number'), tipo)
        if proximo:
            nombre = NOMBRE_TIPO.get(tipo, f'tipo {tipo}')
            sembrados.append(f'{nombre} desde {proximo}')
    return sembrados


def aplicar_perfil_al_config(config, perfil):
    """Copia el perfil remoto a nuestra fila local (sólo para imprimir el KuDE)."""
    config.razon_social = perfil.get('legal_name') or perfil.get('name') or config.razon_social
    config.ruc = str(perfil.get('ruc') or '').strip() or config.ruc
    dv = perfil.get('dv')
    config.dv_ruc = str(dv) if dv is not None else config.dv_ruc
    tipo = perfil.get('taxpayer_type')
    config.tipo_contribuyente = str(tipo) if tipo else config.tipo_contribuyente
    config.direccion = perfil.get('address') or config.direccion
    config.numero_casa = str(perfil.get('house_number') or '') or config.numero_casa
    config.telefono = perfil.get('phone') or config.telefono
    config.email = perfil.get('email') or config.email
    config.departamento_codigo = str(perfil.get('department_code') or '') or config.departamento_codigo
    config.departamento_desc = perfil.get('department_name') or config.departamento_desc
    config.distrito_codigo = str(perfil.get('district_code') or '') or config.distrito_codigo
    config.distrito_desc = perfil.get('district_name') or config.distrito_desc
    config.ciudad_codigo = str(perfil.get('city_code') or '') or config.ciudad_codigo
    config.ciudad_desc = perfil.get('city_name') or config.ciudad_desc

    actividades = perfil.get('economic_activities') or []
    if actividades:
        primera = actividades[0]
        config.actividad_economica_codigo = str(
            primera.get('code') or primera.get('codigo') or ''
        ) or config.actividad_economica_codigo
        config.actividad_economica_desc = (
            primera.get('description') or primera.get('name') or config.actividad_economica_desc
        )

    propio = _adoptar_timbrado_config(config, perfil)
    sembrados = sembrar_correlativos(config, perfil)
    sincronizar_ambiente(config, perfil)
    db.session.commit()

    modo = perfil.get('sifen_mode_display') or perfil.get('sifen_mode') or ''
    aviso_numeracion = (
        f' Numeración ajustada al rango del timbrado: {"; ".join(sembrados)}.'
        if sembrados else ''
    )
    if propio is None:
        # El motivo exacto (ninguno, otro punto, fecha a futuro) es lo que
        # permite arreglarlo sin adivinar del lado del proveedor.
        _id, motivo = resolver_timbrado(config, perfil)
        return f'Datos del emisor actualizados (modo {modo}). Ojo: {motivo}{aviso_numeracion}'
    return (
        f'Datos del emisor actualizados desde la API (modo {modo}, '
        f'timbrado {config.timbrado_numero}).{aviso_numeracion}'
    )


__all__ = [
    'NOMBRE_TIPO',
    'TIPO_FACTURA',
    'aplicar_perfil_al_config',
    'congelar_identidad',
    'faltantes_locales',
    'faltantes_readiness_api',
    'normalizar_codigo',
    'obtener_perfil',
    'olvidar_perfil',
    'resolver_timbrado',
    'seleccionar_timbrado',
    'sincronizar_ambiente',
]
