"""Funciones que la instalacion usa alguna vez, para el panel de salud de uso (BI-05).

Cada chequeo mira datos ya guardados de este cliente: sin rastro, la funcion figura como «sin usar».
No cuentan las vistas (no se registran) ni el sugeridor del POS (su medicion es de exposicion, no de uso).
"""
from __future__ import annotations

from app.models.configuracion import Configuracion
from gastronomia.bi_models import GastronomiaBiConsentimiento
from gastronomia.models import GastronomiaPedido
from gastronomia.services.bi.consentimiento import ACEPTA
from gastronomia.services.bi.pedidos_validos import CANAL_POS, CANAL_TIENDA, criterios_base
from gastronomia.services.bi.telemetria import TIPOS_COLA, existe_evento


def _pedido_con(cliente_id: int, *filtros) -> bool:
    return GastronomiaPedido.query.filter(*criterios_base(cliente_id), *filtros).first() is not None


def _config_guardada(cliente_id: int, prefijo: str, solo_con_valor: bool = False) -> bool:
    consulta = Configuracion.query.filter(Configuracion.clave.like(f'{prefijo}.{int(cliente_id)}.%'))
    if solo_con_valor:
        consulta = consulta.filter(Configuracion.valor != '')
    return consulta.first() is not None


def _pedidos_en_pos(cliente_id: int) -> bool:
    return _pedido_con(cliente_id, GastronomiaPedido.origen_pedido == CANAL_POS)


def _telefono_en_pedidos(cliente_id: int) -> bool:
    return _pedido_con(
        cliente_id,
        GastronomiaPedido.celular_cliente.isnot(None),
        GastronomiaPedido.celular_cliente != '',
    )


def _pedidos_desde_tienda(cliente_id: int) -> bool:
    return _pedido_con(cliente_id, GastronomiaPedido.origen_pedido == CANAL_TIENDA)


def _consentimiento_en_pos(cliente_id: int) -> bool:
    return GastronomiaBiConsentimiento.query.filter_by(cliente_id=int(cliente_id), estado=ACEPTA).first() is not None


def _cola_de_clientes(cliente_id: int) -> bool:
    return existe_evento(cliente_id, TIPOS_COLA)


def _lista_de_activacion(cliente_id: int) -> bool:
    return _config_guardada(cliente_id, 'bi.activacion')


def _comision_evitada(cliente_id: int) -> bool:
    return _config_guardada(cliente_id, 'bi.comision', solo_con_valor=True)


def _configuracion_de_cola(cliente_id: int) -> bool:
    return _config_guardada(cliente_id, 'bi.cola')


CHEQUEOS = (
    ('Pedidos en el POS', _pedidos_en_pos),
    ('Teléfono del cliente en los pedidos', _telefono_en_pedidos),
    ('Pedidos desde la tienda online', _pedidos_desde_tienda),
    ('Casilla de consentimiento en el POS', _consentimiento_en_pos),
    ('Cola de clientes que vuelven', _cola_de_clientes),
    ('Lista de activación comercial', _lista_de_activacion),
    ('Comisión evitada', _comision_evitada),
    ('Configuración de la cola', _configuracion_de_cola),
)


def uso_funciones(cliente_id: int) -> list[dict]:
    return [{'nombre': nombre, 'usada': chequeo(cliente_id)} for nombre, chequeo in CHEQUEOS]
