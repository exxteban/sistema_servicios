"""Lectura de las respuestas de SIFEN: buscar campos sin asumir el árbol del
SOAP, serializarlas para diagnóstico y traducirlas a un estado del DE."""
import json

from facturacion_electronica import ESTADO_APROBADO, ESTADO_ENVIADO, ESTADO_RECHAZADO


def _nombre_local(clave):
    """`ns2:dEstRes` → `dEstRes`.

    La respuesta real de SIFEN llega con el prefijo de namespace pegado a cada
    nombre. Comparando la clave entera, un rechazo (`ns2:dEstRes: Rechazado`)
    no se reconocía: el documento quedaba en 'enviado' para siempre, sin
    código ni motivo a la vista, aunque todo estuviera en `respuesta_raw`.
    """
    return clave.split(':')[-1] if isinstance(clave, str) else clave


def _buscar_clave(obj, claves):
    """Busca recursivamente la primera de `claves` en un dict/list anidado."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _nombre_local(k) in claves and v not in (None, ''):
                return v
        for v in obj.values():
            encontrado = _buscar_clave(v, claves)
            if encontrado is not None:
                return encontrado
    elif isinstance(obj, list):
        for item in obj:
            encontrado = _buscar_clave(item, claves)
            if encontrado is not None:
                return encontrado
    return None


def _serializar_respuesta(respuesta):
    """JSON completo de la respuesta de SIFEN, para diagnosticar rechazos sin
    depender de que _interpretar_respuesta haya encontrado los campos."""
    if respuesta is None:
        return None
    try:
        return json.dumps(respuesta, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(respuesta)


def _detalle_sifen(codigo, mensaje):
    """Texto del rechazo para la pantalla: código **y** mensaje.

    `dMsgRes` de los eventos suele ser genérico ("Error Inesperado"): sin el
    `dCodRes` al lado no hay nada que buscar en el manual de la DNIT.
    """
    codigo = str(codigo).strip() if codigo is not None else ''
    mensaje = str(mensaje).strip() if mensaje is not None else ''
    if codigo and mensaje:
        return f'{codigo} — {mensaje}'
    return codigo or mensaje or 'respuesta desconocida'


def _interpretar_respuesta(respuesta):
    """Extrae (estado, codigo, mensaje, protocolo) de la respuesta de SIFEN.

    Defensivo: la estructura exacta del SOAP recién se puede verificar contra el
    ambiente real, así que se busca por nombre de campo sin asumir el árbol.
    """
    codigo = _buscar_clave(respuesta, {'dCodRes', 'dCodResLot'})
    mensaje = _buscar_clave(respuesta, {'dMsgRes', 'dMsg'})
    protocolo = _buscar_clave(respuesta, {'dProtAut', 'dProtConsLote', 'dNumLote'})
    estado_txt = (_buscar_clave(respuesta, {'dEstRes'}) or '').lower()

    if 'aprob' in estado_txt:
        estado = ESTADO_APROBADO
    elif 'rechaz' in estado_txt:
        estado = ESTADO_RECHAZADO
    else:
        estado = ESTADO_ENVIADO
    return estado, codigo, mensaje, protocolo
