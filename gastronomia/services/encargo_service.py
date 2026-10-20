"""Encargos: pedidos de retiro programados para otro dia.

Un encargo es un `GastronomiaPedido` con `es_encargo = True` y `fecha_programada`.
Reutiliza `crear_pedido` / `actualizar_pedido_abierto`; aqui solo viven las
reglas propias (flag, fecha, capacidad). Ver docs/pasteleria_fase1_diseno.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app import db
from app.utils.helpers import get_app_timezone, now_local
from gastronomia.config_flags import FLAG_ENCARGOS
from gastronomia.models import GastronomiaPedido
from gastronomia.services.pasteleria_flags import flag_activo, parametros_encargos
from gastronomia.services.pedido_service import (
    actualizar_pedido_abierto,
    crear_pedido,
    enviar_pedido_cocina,
    obtener_pedido,
)


FORMATOS_FECHA = ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S')
ESTADOS_ENCARGO_ACTIVOS = ('abierto', 'enviado_cocina', 'preparando', 'listo', 'en_camino', 'entregado')


class EncargosDeshabilitadosError(ValueError):
    """El local no tiene habilitados los encargos (flag apagado)."""


def encargos_habilitados(cliente_id: int) -> bool:
    return flag_activo(cliente_id, FLAG_ENCARGOS)


def exigir_encargos_habilitados(cliente_id: int) -> None:
    if not encargos_habilitados(cliente_id):
        raise EncargosDeshabilitadosError('Los encargos no estan habilitados para este local.')


def parsear_fecha_programada(valor) -> datetime:
    """Interpreta la fecha/hora de retiro como hora local naive (sin zona)."""
    if isinstance(valor, datetime):
        fecha = valor
    else:
        texto = str(valor or '').strip()
        if not texto:
            raise ValueError('La fecha y hora de retiro son obligatorias.')
        fecha = _parsear_texto(texto)
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(get_app_timezone()).replace(tzinfo=None)
    return fecha.replace(second=0, microsecond=0)


def _parsear_texto(texto: str) -> datetime:
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        raise ValueError('La fecha y hora de retiro no son validas.')


def crear_encargo(cliente_id: int, usuario_id: int, data: dict) -> GastronomiaPedido:
    exigir_encargos_habilitados(cliente_id)
    fecha = parsear_fecha_programada(data.get('fecha_programada'))
    payload = _payload_encargo(data)
    _validar_anticipo(cliente_id, fecha)
    _validar_capacidad(cliente_id, fecha)
    return crear_pedido(cliente_id, usuario_id, payload, es_encargo=True, fecha_programada=fecha)


def actualizar_encargo(cliente_id: int, pedido_id: int, data: dict) -> GastronomiaPedido:
    exigir_encargos_habilitados(cliente_id)
    pedido = obtener_encargo(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Encargo no encontrado.')
    fecha = parsear_fecha_programada(data.get('fecha_programada') or pedido.fecha_programada)
    payload = _payload_encargo(data)
    if fecha != pedido.fecha_programada:
        _validar_anticipo(cliente_id, fecha)
    if _dia(fecha) != _dia(pedido.fecha_programada):
        _validar_capacidad(cliente_id, fecha, excluir_pedido_id=pedido_id)
    from gastronomia.services.adelanto_service import sena_vigente  # evita import circular

    return actualizar_pedido_abierto(
        cliente_id, pedido_id, payload, fecha_programada=fecha, total_minimo=sena_vigente(pedido) or None,
    )


def enviar_a_produccion(cliente_id: int, pedido_id: int) -> GastronomiaPedido:
    """Pasa el encargo a cocina. Es una decision humana: no hay ventana horaria automatica."""
    exigir_encargos_habilitados(cliente_id)
    pedido = obtener_encargo(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Encargo no encontrado.')
    if pedido.estado != 'abierto':
        raise ValueError('Solo se pueden enviar a produccion encargos abiertos.')
    return enviar_pedido_cocina(cliente_id, pedido_id)


def obtener_encargo(cliente_id: int, pedido_id: int) -> GastronomiaPedido | None:
    pedido = obtener_pedido(cliente_id, pedido_id)
    return pedido if pedido is not None and pedido.es_encargo else None


def listar_encargos(
    cliente_id: int,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    estados: list[str] | None = None,
) -> list[GastronomiaPedido]:
    """Encargos ordenados por fecha de retiro. Sin `estados` excluye los cancelados."""
    consulta = GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.es_encargo.is_(True),
    )
    if desde is not None:
        consulta = consulta.filter(GastronomiaPedido.fecha_programada >= desde)
    if hasta is not None:
        consulta = consulta.filter(GastronomiaPedido.fecha_programada < hasta)
    consulta = consulta.filter(GastronomiaPedido.estado.in_(list(estados or ESTADOS_ENCARGO_ACTIVOS)))
    return consulta.order_by(GastronomiaPedido.fecha_programada.asc(), GastronomiaPedido.id_pedido.asc()).all()


def limites_del_dia(dia: datetime) -> tuple[datetime, datetime]:
    inicio = datetime(dia.year, dia.month, dia.day)
    return inicio, inicio + timedelta(days=1)


def _payload_encargo(data: dict) -> dict:
    tipo = (data.get('tipo_pedido') or 'retiro').strip().lower()
    if tipo != 'retiro':
        raise ValueError('Los encargos solo admiten retiro en el local.')
    if not (data.get('nombre_cliente') or data.get('referencia_entrega') or '').strip():
        raise ValueError('El nombre del cliente es obligatorio en un encargo.')
    return {**data, 'tipo_pedido': 'retiro', 'origen_pedido': 'pos'}


def _validar_anticipo(cliente_id: int, fecha: datetime) -> None:
    ahora = now_local().replace(tzinfo=None)
    if fecha <= ahora:
        raise ValueError('La fecha de retiro tiene que ser posterior a este momento.')
    horas = parametros_encargos(cliente_id)['anticipo_horas']
    if horas and fecha < ahora + timedelta(hours=horas):
        raise ValueError(f'Los encargos requieren al menos {horas} horas de anticipacion.')


def _validar_capacidad(cliente_id: int, fecha: datetime, *, excluir_pedido_id: int | None = None) -> None:
    tope = parametros_encargos(cliente_id)['max_por_dia']
    if not tope:
        return
    inicio, fin = limites_del_dia(fecha)
    consulta = db.session.query(db.func.count(GastronomiaPedido.id_pedido)).filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.es_encargo.is_(True),
        GastronomiaPedido.estado != 'cancelado',
        GastronomiaPedido.fecha_programada >= inicio,
        GastronomiaPedido.fecha_programada < fin,
    )
    if excluir_pedido_id is not None:
        consulta = consulta.filter(GastronomiaPedido.id_pedido != int(excluir_pedido_id))
    if int(consulta.scalar() or 0) >= int(tope):
        raise ValueError(f'Se alcanzo el limite de {int(tope)} encargos para ese dia.')


def _dia(fecha: datetime | None):
    return fecha.date() if fecha else None
