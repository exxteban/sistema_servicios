"""Configuracion de la cola de envio asistido, guardada por cliente en Configuracion (BI-02).

La clave incluye el id_cliente: una instalacion puede alojar mas de un cliente.
"""
from __future__ import annotations

from app import db
from app.models.configuracion import Configuracion
from gastronomia.services.bi.plantillas import PLANTILLAS_DEFAULT

PREFIJO = 'bi.cola'
# nombre: (valor por defecto, minimo, maximo)
ENTEROS = {
    'limite_dia': (20, 1, 200),
    'frecuencia_dias': (14, 1, 90),
    'segunda_min': (5, 1, 60),
    'segunda_max': (15, 1, 90),
}
ETIQUETAS = {
    'limite_dia': 'límite diario',
    'frecuencia_dias': 'frecuencia en días',
    'segunda_min': 'mínimo de días para segunda compra',
    'segunda_max': 'máximo de días para segunda compra',
}
LARGO_PLANTILLA_MAX = 500
SEGMENTOS_PLANTILLA = tuple(PLANTILLAS_DEFAULT)


def _clave(cliente_id: int, nombre: str) -> str:
    return f'{PREFIJO}.{int(cliente_id)}.{nombre}'


def _entero_guardado(valor: str | None, defecto: int, minimo: int, maximo: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return numero if minimo <= numero <= maximo else defecto


def _entero_recibido(valor, nombre: str, minimo: int, maximo: int) -> int:
    etiqueta = ETIQUETAS[nombre]
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(f'El {etiqueta} tiene que ser un número.')
    if not minimo <= numero <= maximo:
        raise ValueError(f'El {etiqueta} tiene que estar entre {minimo} y {maximo}.')
    return numero


def leer_config(cliente_id: int) -> dict:
    return {
        nombre: _entero_guardado(Configuracion.obtener(_clave(cliente_id, nombre)), defecto, minimo, maximo)
        for nombre, (defecto, minimo, maximo) in ENTEROS.items()
    }


def plantilla(cliente_id: int, segmento: str) -> str:
    guardada = (Configuracion.obtener(_clave(cliente_id, f'pl_{segmento}')) or '').strip()
    return guardada or PLANTILLAS_DEFAULT[segmento]


def guardar_config(cliente_id: int, datos) -> None:
    valores: dict[str, str] = {}
    for nombre, (_defecto, minimo, maximo) in ENTEROS.items():
        valores[nombre] = str(_entero_recibido(datos.get(nombre), nombre, minimo, maximo))
    if int(valores['segunda_min']) > int(valores['segunda_max']):
        raise ValueError('En segunda compra, el mínimo de días no puede superar al máximo.')
    for segmento in SEGMENTOS_PLANTILLA:
        texto = str(datos.get(f'pl_{segmento}') or '').strip()
        if not texto:
            raise ValueError('Una plantilla de mensaje no puede quedar vacía.')
        if len(texto) > LARGO_PLANTILLA_MAX:
            raise ValueError(f'Una plantilla de mensaje no puede superar {LARGO_PLANTILLA_MAX} caracteres.')
        valores[f'pl_{segmento}'] = texto
    for nombre, valor in valores.items():
        Configuracion.establecer(
            _clave(cliente_id, nombre),
            valor,
            descripcion='Cola de envio asistido (BI gastronomia)',
            commit=False,
        )
    db.session.commit()
