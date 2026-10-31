"""Porcentaje de comision de cada plataforma externa, guardado por cliente (BI-03).

Sin porcentaje configurado no se estima ninguna comision evitada: el dato faltante
nunca se convierte en cero. La clave incluye el id_cliente de la instalacion.
"""
from __future__ import annotations

from app import db
from app.models.configuracion import Configuracion
from gastronomia.services.bi.telemetria import TIPO_COMISION, registrar_evento
from gastronomia.services.channel_price_service import CANALES_PRECIOS

PREFIJO = 'bi.comision'
PORCENTAJE_MAX = 100.0


def _clave(cliente_id: int, canal: str) -> str:
    return f'{PREFIJO}.{int(cliente_id)}.{canal}'


def _porcentaje_guardado(valor: str | None) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if 0 < numero <= PORCENTAJE_MAX else None


def leer_porcentajes(cliente_id: int) -> dict[str, float | None]:
    """Un valor por plataforma: su porcentaje, o None si no esta configurado (o es cero)."""
    return {
        canal: _porcentaje_guardado(Configuracion.obtener(_clave(cliente_id, canal)))
        for canal in CANALES_PRECIOS
    }


def guardar_porcentajes(cliente_id: int, datos) -> None:
    """Valida todas las plataformas antes de guardar. Un campo vacio deja la plataforma sin configurar."""
    valores: dict[str, str] = {}
    for canal, nombre in CANALES_PRECIOS.items():
        bruto = str(datos.get(f'comision_{canal}') or '').strip().replace(',', '.')
        if not bruto:
            valores[canal] = ''
            continue
        try:
            numero = float(bruto)
        except ValueError:
            raise ValueError(f'La comisión de {nombre} tiene que ser un número.')
        if not 0 <= numero <= PORCENTAJE_MAX:
            raise ValueError(f'La comisión de {nombre} tiene que estar entre 0 y 100.')
        valores[canal] = f'{numero:g}'
    for canal, valor in valores.items():
        Configuracion.establecer(
            _clave(cliente_id, canal),
            valor,
            descripcion='Comision de plataformas externas (BI gastronomia)',
            commit=False,
        )
    registrar_evento(cliente_id, TIPO_COMISION)
    db.session.commit()
