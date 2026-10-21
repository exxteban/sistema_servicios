"""Tablero de produccion de encargos: encargos por dia y totales a producir.

Arma la vista del tablero sobre `listar_encargos` y `serializar_pedidos`; no
agrega reglas nuevas de encargos (viven en encargo_service / adelanto_service).
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta

from app.models import Usuario
from app import db
from app.services.caja_senas import sesion_caja_abierta_usuario
from app.utils.helpers import now_local
from gastronomia.services.adelanto_service import MENSAJE_SIN_CAJA, registrar_adelanto
from gastronomia.services.encargo_service import crear_encargo, exigir_encargos_habilitados, listar_encargos
from gastronomia.services.pasteleria_flags import parametros_encargos
from gastronomia.services.pedido_service import serializar_pedidos
from gastronomia.services.venta_integration_service import _resolver_metodo_pago


DIAS_TABLERO_DEFAULT = 7
DIAS_TABLERO_MAX = 31
# Encargos de dias pasados que siguen sin retirar ni cobrar: el tablero los resalta.
ESTADOS_VENCIDOS = ['abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado']


def tablero_encargos(cliente_id: int, *, desde: date | None = None, dias: int = DIAS_TABLERO_DEFAULT) -> dict:
    exigir_encargos_habilitados(cliente_id)
    hoy = now_local().replace(tzinfo=None).date()
    desde = desde or hoy
    dias = max(1, min(int(dias or DIAS_TABLERO_DEFAULT), DIAS_TABLERO_MAX))
    inicio = datetime(desde.year, desde.month, desde.day)
    fin = inicio + timedelta(days=dias)

    encargos = serializar_pedidos(listar_encargos(cliente_id, desde=inicio, hasta=fin))
    por_dia: OrderedDict[str, list[dict]] = OrderedDict(
        ((inicio + timedelta(days=offset)).date().isoformat(), []) for offset in range(dias)
    )
    for encargo in encargos:
        por_dia.setdefault((encargo.get('fecha_programada') or '')[:10], []).append(encargo)

    vencidos = []
    if desde <= hoy:
        hoy_inicio = datetime(hoy.year, hoy.month, hoy.day)
        vencidos = serializar_pedidos(listar_encargos(cliente_id, hasta=hoy_inicio, estados=ESTADOS_VENCIDOS))

    return {
        'hoy': hoy.isoformat(),
        'desde': desde.isoformat(),
        'dias': [
            {
                'fecha': fecha,
                'encargos': items,
                'cantidad': len(items),
                'produccion': totales_produccion(items),
            }
            for fecha, items in por_dia.items()
        ],
        'vencidos': vencidos,
        'parametros': parametros_encargos(cliente_id),
    }


def totales_produccion(encargos: list[dict]) -> list[dict]:
    """Unidades a producir por producto ("3 tortas, 40 medialunas")."""
    totales: dict[str, int] = {}
    for encargo in encargos:
        for item in encargo.get('items') or []:
            nombre = item.get('nombre_producto') or 'Producto'
            totales[nombre] = totales.get(nombre, 0) + int(item.get('cantidad') or 0)
    return [
        {'producto': nombre, 'cantidad': cantidad}
        for nombre, cantidad in sorted(totales.items(), key=lambda par: (-par[1], par[0].lower()))
    ]


def crear_encargo_desde_tablero(cliente_id: int, usuario_id: int, data: dict) -> tuple:
    """Crea el encargo y, si se pidio, cobra la sena. Devuelve `(pedido, aviso)`.

    Lo que puede fallar de la sena (caja cerrada, metodo, referencia) se valida
    antes de crear el encargo. Si igual falla despues (monto >= total), el encargo
    queda guardado sin sena y se devuelve el motivo en `aviso`.
    """
    sena = data.get('sena') if isinstance(data.get('sena'), dict) else None
    if sena:
        _validar_sena_previa(usuario_id, sena)
    pedido = crear_encargo(cliente_id, usuario_id, data)
    aviso = None
    if sena:
        try:
            registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, sena)
        except ValueError as exc:
            db.session.rollback()
            aviso = f'El encargo se guardo, pero la sena no se registro: {exc}'
    return pedido, aviso


def _validar_sena_previa(usuario_id: int, sena: dict) -> None:
    try:
        monto = float(sena.get('monto') or 0)
    except (TypeError, ValueError):
        raise ValueError('Monto de sena invalido.')
    if monto <= 0:
        raise ValueError('Ingresa un monto de sena mayor a cero.')
    usuario = db.session.get(Usuario, int(usuario_id))
    if not usuario or not sesion_caja_abierta_usuario(usuario):
        raise ValueError(MENSAJE_SIN_CAJA)
    _resolver_metodo_pago(sena)
