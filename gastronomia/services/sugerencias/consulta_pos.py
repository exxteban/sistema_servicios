"""Consulta compartida por el endpoint y su diagnóstico: solo lee resultados preparados."""
from time import monotonic

from gastronomia.services.channel_price_service import normalizar_canal_precio
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.candidatos import previsualizar
from gastronomia.services.sugerencias.pos import config_para_pos


def consultar(cliente_id, productos, *, canal_precio=None, plazo=None):
    plazo = monotonic() + C.PRESUPUESTO_POS_SEGUNDOS if plazo is None else plazo
    config = config_para_pos(cliente_id)
    respuesta = {'sugerencias': [], 'max': config['max'], 'estado': 'desactivado'}
    if not config['activo']:
        return respuesta
    respuesta['estado'] = 'sin_productos'
    if not productos:
        return respuesta
    respuesta['estado'] = 'tiempo_agotado'
    if monotonic() >= plazo:
        return respuesta
    canal = normalizar_canal_precio(canal_precio)
    try:
        resultado = previsualizar(cliente_id, productos, canal_precio=canal, plazo=plazo)
    except TimeoutError:
        return respuesta
    if monotonic() >= plazo:
        return respuesta
    respuesta['sugerencias'] = [
        {k: fila[k] for k in ('id_producto', 'motivo', 'fuente', 'id_origen')}
        for fila in resultado['sugerencias'][:C.MAX_EN_LISTA]
    ]
    respuesta['estado'] = 'ok'
    return respuesta
