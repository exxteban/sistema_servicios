"""Envío por lote del motor propio (siRecepLoteDE + siConsLoteDE).

Es la alternativa al envío síncrono (`siRecepDE`) y la forma en que transmite
la API externa. La diferencia que importa:

- **Síncrono:** SIFEN contesta aprobado/rechazado en el mismo pedido.
- **Lote:** SIFEN sólo dice "recibí el lote N" (`0300`). El documento queda en
  'enviado' y el resultado se pide después con el número de lote: `0361`
  sigue procesando, `0362` concluyó y trae el resultado de cada DE. El job de
  FE consulta en cada pasada hasta que haya respuesta.

Se manda **un DE por lote**. El lote admite hasta 50, pero juntarlos no le
sirve a un comercio y suma problemas: un lote no puede mezclar tipos de
documento (`0363`) y el rechazo de uno se mezcla con el resultado de los demás.

El número de lote se guarda en `api_lote_id`, la columna que quedó sin uso
cuando el loteo de la API pasó a hacerlo su pipeline. Un documento de la API
siempre tiene `api_documento_id`; uno del motor propio, nunca. Por eso
`es_de_lote_propio` mira las dos.

Mientras el lote está en proceso, consultar el CDC (`siConsDE`) devuelve
`0420` "no existe": con el envío síncrono eso es definitivo, con lote no. Un
documento de lote pendiente se consulta **por lote**, nunca por CDC; recién
cuando el lote ya no se puede consultar (`0360`/`0364`) se cae al CDC.
"""
from datetime import datetime, timedelta

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    CLAVE_MODO_ENVIO,
    ESTADO_APROBADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_RECHAZADO,
    MODO_ENVIO_LOTE,
    MODO_ENVIO_SINCRONO,
)
from facturacion_electronica.services.respuesta_sifen import (
    _buscar_clave,
    _nombre_local,
    _serializar_respuesta,
)
from facturacion_electronica.services.retransmision import (
    CONFIRMADO,
    aplicar_consulta,
    evidencia_cdc,
)

LOTE_RECIBIDO = '0300'
LOTE_EN_PROCESO = '0361'
LOTE_CONCLUIDO = '0362'
# Sin resultado por lote: el número no existe o pasaron las 48h. Lo que SIFEN
# sabe del documento se pregunta entonces por CDC.
LOTE_NO_CONSULTABLE = frozenset({'0360', '0364'})

# La DNIT recomienda no consultar un lote antes de los 10 minutos: antes casi
# siempre da 0361 y sólo suma pedidos. Aplica al job; el botón "Consultar
# estado" pregunta cuando la persona quiere.
ESPERA_PRIMERA_CONSULTA = timedelta(minutes=10)
# Pasado este tiempo con el lote sin resultado, se pregunta además por CDC:
# SIFEN puede tener el DE resuelto aunque la consulta del lote siga atrasada.
RESPALDO_POR_CDC_DESDE = timedelta(hours=1)


def modo_envio():
    """El modo de envío configurado; ante cualquier valor raro, síncrono."""
    from app.models.configuracion import Configuracion

    valor = (Configuracion.obtener(CLAVE_MODO_ENVIO) or '').strip().lower()
    return MODO_ENVIO_LOTE if valor == MODO_ENVIO_LOTE else MODO_ENVIO_SINCRONO


def modo_envio_efectivo(config):
    """El modo con el que se transmite de verdad: en producción, siempre lote.

    SIFEN no admite `siRecepDE` en producción; sólo el ambiente de prueba lo
    acepta. Elegir "síncrono" sirve para probar rápido en test, pero no puede
    dejar a una instalación productiva mandando por un camino que no existe.
    """
    if getattr(config, 'ambiente', None) == AMBIENTE_PRODUCCION:
        return MODO_ENVIO_LOTE
    return modo_envio()


def guardar_modo_envio(valor):
    from app.models.configuracion import Configuracion

    valor = (valor or '').strip().lower()
    if valor not in (MODO_ENVIO_SINCRONO, MODO_ENVIO_LOTE):
        valor = MODO_ENVIO_SINCRONO
    Configuracion.establecer(
        CLAVE_MODO_ENVIO, valor,
        descripcion='Facturación electrónica (motor propio): envío síncrono o por lotes.',
    )


def es_de_lote_propio(documento):
    return bool(getattr(documento, 'api_lote_id', None)) and not getattr(
        documento, 'api_documento_id', None)


def _como_lista(valor):
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _buscar_lista(obj, clave):
    """Todas las apariciones de `clave` (sin prefijo de namespace), aplanadas.

    xml2js con `explicitArray: false` devuelve un dict si hay un solo
    elemento y una lista si hay varios; se normaliza a lista siempre.
    """
    encontrados = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _nombre_local(k) == clave:
                encontrados.extend(_como_lista(v))
            else:
                encontrados.extend(_buscar_lista(v, clave))
    elif isinstance(obj, list):
        for item in obj:
            encontrados.extend(_buscar_lista(item, clave))
    return encontrados


def enviar_en_lote(documento, enviar, aviso_plazo=None):
    """Manda el DE en un lote de uno. Devuelve (documento, error).

    `enviar` es `enviar_lote` ya atado al certificado y al ambiente: recibe
    la lista de XML y devuelve (respuesta, error).
    """
    respuesta, error = enviar([documento.xml_qr])
    # El número de un lote anterior (un rechazo que se corrigió) deja de valer
    # en cuanto se manda otro, haya llegado o no.
    documento.api_lote_id = None
    if error:
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error
        db.session.commit()
        return documento, error

    codigo = str(_buscar_clave(respuesta, {'dCodRes'}) or '').strip()
    mensaje = _buscar_clave(respuesta, {'dMsgRes'})
    numero_lote = str(_buscar_clave(respuesta, {'dProtConsLote'}) or '').strip()
    documento.respuesta_codigo = codigo or None
    documento.respuesta_raw = _serializar_respuesta(respuesta)

    if codigo != LOTE_RECIBIDO or not numero_lote or numero_lote == '0':
        # 0301 "lote no encolado" u otra cosa: SIFEN no tomó nada, se puede
        # reenviar tal cual cuando se resuelva lo que dice.
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = (
            f'SIFEN no recibió el lote: {codigo or "sin código"} — {mensaje or "sin mensaje"}'
        )
        db.session.commit()
        return documento, documento.respuesta_mensaje

    documento.estado = ESTADO_ENVIADO
    documento.api_lote_id = numero_lote
    documento.protocolo_autorizacion = None
    documento.respuesta_mensaje = ' '.join(p for p in (
        f'Lote {numero_lote} recibido por SIFEN; el resultado se consulta en unos minutos.',
        aviso_plazo or '',
    ) if p)
    documento.fecha_envio = datetime.utcnow()
    db.session.commit()
    return documento, None


def _resultado_del_documento(respuesta, cdc):
    """El bloque `gResProcLote` de este CDC, y sólo de este CDC.

    Aunque el lote tenga un único resultado, si su `id` no es el CDC del
    documento no es suyo: aprobarlo así daría por autorizado un CDC que SIFEN
    nunca recibió.
    """
    for resultado in _buscar_lista(respuesta, 'gResProcLote'):
        if isinstance(resultado, dict) and                 str(_buscar_clave(resultado, {'id', 'Id'}) or '').strip() == cdc:
            return resultado
    return None


def _aplicar_resultado(documento, resultado):
    estado_txt = str(_buscar_clave(resultado, {'dEstRes'}) or '').lower()
    procesos = [p for p in _buscar_lista(resultado, 'gResProc') if isinstance(p, dict)]
    codigos = [str(_buscar_clave(p, {'dCodRes'}) or '').strip() for p in procesos]
    mensajes = [str(_buscar_clave(p, {'dMsgRes'}) or '').strip() for p in procesos]
    protocolo = _buscar_clave(resultado, {'dProtAut'})

    if 'aprob' in estado_txt:
        documento.estado = ESTADO_APROBADO
    elif 'rechaz' in estado_txt:
        documento.estado = ESTADO_RECHAZADO
    else:
        return False
    documento.respuesta_codigo = ', '.join(c for c in codigos if c) or documento.respuesta_codigo
    documento.respuesta_mensaje = ' | '.join(m for m in mensajes if m) or estado_txt.capitalize()
    if protocolo and str(protocolo).strip() not in ('', '0'):
        documento.protocolo_autorizacion = str(protocolo).strip()
    return True


def _antiguedad_del_envio(documento, ahora=None):
    if not documento.fecha_envio:
        return None
    return (ahora or datetime.utcnow()) - documento.fecha_envio


def lote_recien_enviado(documento, ahora=None):
    """¿Es un DE de lote propio enviado hace menos de 10 minutos?"""
    antiguedad = _antiguedad_del_envio(documento, ahora)
    return (es_de_lote_propio(documento) and antiguedad is not None
            and antiguedad < ESPERA_PRIMERA_CONSULTA)


def _respaldo_por_cdc(documento, consultar_cdc, ahora=None):
    """Si el lote lleva más de una hora sin resultado, pregunta por CDC.

    Sólo **aprueba**, con el protocolo a la vista. Un `0420` "no existe" no
    se toma como rechazo: con el lote en proceso es lo que SIFEN contesta
    siempre, y marcar rechazado un DE que después se aprueba es peor que
    seguir esperando. Devuelve True si el documento quedó aprobado.
    """
    antiguedad = _antiguedad_del_envio(documento, ahora)
    if antiguedad is None or antiguedad < RESPALDO_POR_CDC_DESDE:
        return False
    respuesta, error = consultar_cdc(documento.cdc)
    if error or evidencia_cdc(respuesta)[0] != CONFIRMADO:
        return False
    aplicar_consulta(documento, respuesta)
    documento.respuesta_mensaje = (
        f'Aprobado según la consulta por CDC; el lote {documento.api_lote_id} '
        'seguía sin resultado.'
    )
    db.session.commit()
    return True


def consultar_lote_del_documento(documento, consultar, consultar_cdc, ahora=None):
    """Pregunta a SIFEN cómo terminó el lote del documento. Devuelve (respuesta, error).

    `consultar` recibe el número de lote y `consultar_cdc` el CDC; los dos
    devuelven (respuesta, error). Sólo mueve el estado con un resultado claro.
    """
    respuesta, error = consultar(documento.api_lote_id)
    if error:
        return respuesta, error

    codigo = str(_buscar_clave(respuesta, {'dCodResLot', 'dCodRes'}) or '').strip()
    mensaje = _buscar_clave(respuesta, {'dMsgResLot', 'dMsgRes'})

    if codigo in LOTE_NO_CONSULTABLE:
        respuesta_cdc, error = consultar_cdc(documento.cdc)
        if error:
            return respuesta_cdc, error
        aplicar_consulta(documento, respuesta_cdc)
        return respuesta_cdc, None

    if codigo == LOTE_CONCLUIDO:
        resultado = _resultado_del_documento(respuesta, documento.cdc)
        if resultado is not None and _aplicar_resultado(documento, resultado):
            documento.respuesta_raw = _serializar_respuesta(respuesta)
            db.session.commit()
            return respuesta, None
        if _respaldo_por_cdc(documento, consultar_cdc, ahora):
            return respuesta, None
        return respuesta, (f'El lote {documento.api_lote_id} terminó pero SIFEN no informó '
                           'el resultado de este documento. Se vuelve a consultar más tarde.')

    # 0361 "en procesamiento" o algo desconocido: se deja como está, a la vista.
    if _respaldo_por_cdc(documento, consultar_cdc, ahora):
        return respuesta, None
    documento.respuesta_codigo = codigo or documento.respuesta_codigo
    # SIFEN ya nombra el lote en su mensaje ("Lote {N} en procesamiento").
    documento.respuesta_mensaje = (
        f'{mensaje or f"Lote {documento.api_lote_id}: sin respuesta todavía"}'
        f'{"; SIFEN todavía no lo terminó" if codigo == LOTE_EN_PROCESO else ""}.'
    )
    db.session.commit()
    return respuesta, None


__all__ = [
    'consultar_lote_del_documento', 'enviar_en_lote', 'es_de_lote_propio', 'lote_recien_enviado',
    'guardar_modo_envio', 'modo_envio', 'modo_envio_efectivo',
]
