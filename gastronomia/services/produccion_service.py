"""Produccion diaria de producto terminado: tandas, merma y cierre del dia.

Opera sobre `GastronomiaProducto.stock_disponible` (el mismo stock que descuenta
la venta) y solo en productos con `control_stock_venta`. Cada movimiento queda
en `GastronomiaProduccionRegistro`. Diseno en docs/pasteleria_fase3_diseno.md.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func

from app import db
from app.utils.helpers import now_local, utc_bounds_for_local_dates
from gastronomia.config_flags import FLAG_PRODUCCION_DIARIA
from gastronomia.models import GastronomiaPedidoItem, GastronomiaProducto
from gastronomia.produccion_models import (
    MOTIVO_FALTANTE,
    MOTIVOS_MERMA,
    TIPO_AJUSTE,
    TIPO_MERMA,
    TIPO_PRODUCCION,
    GastronomiaProduccionRegistro,
)
from gastronomia.services.inteligencia_margen import costos_unitarios_receta
from gastronomia.services.pasteleria_flags import flag_activo
from gastronomia.services.stock_service import _bloquear_producto_menu
from gastronomia.stock_models import GastronomiaPedidoItemConsumo


CANTIDAD_MAX = 10000
DESTINO_SIGUE = 'sigue'
DESTINOS_DESCARTE = ('vencido', 'regalado', 'consumo_propio', 'otro')


class ProduccionDeshabilitadaError(Exception):
    """El local no tiene encendida la produccion diaria."""


def produccion_habilitada(cliente_id: int | None) -> bool:
    return flag_activo(cliente_id, FLAG_PRODUCCION_DIARIA)


def exigir_produccion_habilitada(cliente_id: int) -> None:
    if not produccion_habilitada(cliente_id):
        raise ProduccionDeshabilitadaError('La produccion diaria no esta habilitada para este local.')


def hoy_local() -> date:
    return now_local().date()


def obtener_producto_con_stock(cliente_id: int, producto_id) -> GastronomiaProducto:
    """Producto activo del cliente con control de stock; si no, ValueError."""
    producto = GastronomiaProducto.query.filter_by(
        cliente_id=int(cliente_id), id_producto=_entero(producto_id, 'Producto invalido.'), activo=True,
    ).first()
    if not producto:
        raise ValueError('Producto no encontrado.')
    if not producto.control_stock_venta:
        raise ValueError(
            f'"{producto.nombre}" no controla stock. Activalo en Menu > producto > '
            '"Agotar automaticamente por ventas".'
        )
    return producto


def mover_stock_producto(
    producto: GastronomiaProducto,
    diferencia: int,
    tipo: str,
    *,
    usuario_id: int | None,
    motivo: str | None = None,
    referencia: str | None = None,
    observacion: str | None = None,
    costo_unitario: float | None = None,
) -> GastronomiaProduccionRegistro:
    """Aplica la diferencia con bloqueo de fila y deja el registro (sin commit)."""
    producto = _bloquear_producto_menu(producto)
    stock_anterior = int(producto.stock_disponible or 0)
    producto.stock_disponible = stock_anterior + int(diferencia)
    registro = GastronomiaProduccionRegistro(
        cliente_id=int(producto.cliente_id),
        producto_id=int(producto.id_producto),
        fecha=hoy_local(),
        tipo=tipo,
        cantidad=abs(int(diferencia)),
        motivo=motivo,
        stock_anterior=stock_anterior,
        stock_nuevo=int(producto.stock_disponible),
        costo_unitario=costo_unitario,
        referencia=referencia,
        observacion=(observacion or '').strip()[:255] or None,
        usuario_id=int(usuario_id) if usuario_id else None,
    )
    db.session.add(registro)
    return registro


def registrar_produccion(cliente_id: int, usuario_id: int | None, data: dict) -> GastronomiaProduccionRegistro:
    exigir_produccion_habilitada(cliente_id)
    producto = obtener_producto_con_stock(cliente_id, data.get('producto_id'))
    cantidad = _cantidad(data.get('cantidad'))
    registro = mover_stock_producto(
        producto, cantidad, TIPO_PRODUCCION, usuario_id=usuario_id, observacion=data.get('observacion'),
    )
    db.session.commit()
    return registro


def registrar_merma(cliente_id: int, usuario_id: int | None, data: dict) -> GastronomiaProduccionRegistro:
    exigir_produccion_habilitada(cliente_id)
    producto = obtener_producto_con_stock(cliente_id, data.get('producto_id'))
    cantidad = _cantidad(data.get('cantidad'))
    motivo = _motivo(data.get('motivo'))
    producto = _bloquear_producto_menu(producto)
    disponible = max(0, int(producto.stock_disponible or 0))
    if cantidad > disponible:
        raise ValueError(f'Solo hay {disponible} de "{producto.nombre}" en stock.')
    registro = mover_stock_producto(
        producto, -cantidad, TIPO_MERMA, usuario_id=usuario_id, motivo=motivo,
        observacion=data.get('observacion'), costo_unitario=_costo(cliente_id, producto.id_producto),
    )
    db.session.commit()
    return registro


def cerrar_dia(cliente_id: int, usuario_id: int | None, data: dict) -> list[GastronomiaProduccionRegistro]:
    """Concilia el conteo de lo que quedo con el stock teorico de cada producto.

    `items`: [{producto_id, quedan, destino}] con destino `sigue` (queda a la venta)
    o un motivo de descarte. Valida todo antes de mover stock.
    """
    exigir_produccion_habilitada(cliente_id)
    items = data.get('items') or []
    if not isinstance(items, list) or not items:
        raise ValueError('Carga al menos un producto para cerrar el dia.')
    pedidos = []
    vistos = set()
    for item in items:
        producto = obtener_producto_con_stock(cliente_id, (item or {}).get('producto_id'))
        if producto.id_producto in vistos:
            raise ValueError(f'"{producto.nombre}" esta repetido en el cierre.')
        vistos.add(producto.id_producto)
        quedan = _entero(item.get('quedan'), f'Cantidad que quedo de "{producto.nombre}" invalida.')
        if quedan < 0 or quedan > CANTIDAD_MAX:
            raise ValueError(f'Cantidad que quedo de "{producto.nombre}" invalida.')
        destino = str(item.get('destino') or DESTINO_SIGUE).strip()
        if destino != DESTINO_SIGUE and destino not in DESTINOS_DESCARTE:
            raise ValueError('Destino del sobrante invalido.')
        pedidos.append((producto, quedan, destino))

    costos = costos_unitarios_receta(cliente_id, [p.id_producto for p, _, _ in pedidos])
    registros = []
    for producto, quedan, destino in pedidos:
        producto = _bloquear_producto_menu(producto)
        costo = costos.get(int(producto.id_producto)) or None
        diferencia = quedan - int(producto.stock_disponible or 0)
        if diferencia < 0:
            registros.append(mover_stock_producto(
                producto, diferencia, TIPO_MERMA, usuario_id=usuario_id, motivo=MOTIVO_FALTANTE,
                observacion='Cierre del dia', costo_unitario=costo,
            ))
        elif diferencia > 0:
            registros.append(mover_stock_producto(
                producto, diferencia, TIPO_AJUSTE, usuario_id=usuario_id, observacion='Cierre del dia',
            ))
        if destino != DESTINO_SIGUE and quedan > 0:
            registros.append(mover_stock_producto(
                producto, -quedan, TIPO_MERMA, usuario_id=usuario_id, motivo=destino,
                observacion='Sobrante del cierre', costo_unitario=costo,
            ))
    db.session.commit()
    return registros


def resumen_dia(cliente_id: int, dia: date | None = None) -> dict:
    """Productos con control de stock y sus movimientos del dia."""
    dia = dia or hoy_local()
    productos = (
        GastronomiaProducto.query
        .filter_by(cliente_id=int(cliente_id), activo=True, control_stock_venta=True)
        .order_by(GastronomiaProducto.nombre.asc())
        .all()
    )
    movimientos = _movimientos_dia(cliente_id, dia)
    vendidos = _vendidos_dia(cliente_id, dia)
    from gastronomia.services.porciones_service import relaciones_por_entero

    relaciones = relaciones_por_entero(cliente_id)
    filas = []
    for producto in productos:
        pid = int(producto.id_producto)
        mov = movimientos.get(pid, {})
        relacion = relaciones.get(pid)
        filas.append({
            'producto_id': pid,
            'nombre': producto.nombre,
            'stock': int(producto.stock_disponible or 0),
            'producido': mov.get(TIPO_PRODUCCION, 0),
            'vendido': vendidos.get(pid, 0),
            'merma': mov.get(TIPO_MERMA, 0),
            'ajuste': mov.get(TIPO_AJUSTE, 0),
            'relacion_porciones': relacion.to_dict() if relacion else None,
        })
    return {'fecha': dia.isoformat(), 'productos': filas, 'motivos': MOTIVOS_MERMA}


def productos_menu_sin_control(cliente_id: int) -> list[dict]:
    """Productos activos sin control de stock (para elegir porciones o avisar)."""
    return [
        {'producto_id': int(p.id_producto), 'nombre': p.nombre}
        for p in GastronomiaProducto.query
        .filter_by(cliente_id=int(cliente_id), activo=True)
        .filter(GastronomiaProducto.control_stock_venta.isnot(True))
        .order_by(GastronomiaProducto.nombre.asc())
        .all()
    ]


def _movimientos_dia(cliente_id: int, dia: date) -> dict[int, dict[str, int]]:
    filas = (
        db.session.query(
            GastronomiaProduccionRegistro.producto_id,
            GastronomiaProduccionRegistro.tipo,
            func.coalesce(func.sum(GastronomiaProduccionRegistro.cantidad), 0),
        )
        .filter(
            GastronomiaProduccionRegistro.cliente_id == int(cliente_id),
            GastronomiaProduccionRegistro.fecha == dia,
        )
        .group_by(GastronomiaProduccionRegistro.producto_id, GastronomiaProduccionRegistro.tipo)
        .all()
    )
    resultado: dict[int, dict[str, int]] = {}
    for producto_id, tipo, cantidad in filas:
        resultado.setdefault(int(producto_id), {})[tipo] = int(cantidad or 0)
    return resultado


def _vendidos_dia(cliente_id: int, dia: date) -> dict[int, int]:
    """Unidades descontadas por ventas (consumos `producto_menu` no restaurados)."""
    inicio, fin = utc_bounds_for_local_dates(dia, dia)
    filas = (
        db.session.query(
            GastronomiaPedidoItem.producto_id,
            func.coalesce(func.sum(GastronomiaPedidoItemConsumo.cantidad), 0),
        )
        .join(GastronomiaPedidoItem, GastronomiaPedidoItem.id_item == GastronomiaPedidoItemConsumo.item_id)
        .filter(
            GastronomiaPedidoItemConsumo.cliente_id == int(cliente_id),
            GastronomiaPedidoItemConsumo.tipo_origen == 'producto_menu',
            GastronomiaPedidoItemConsumo.restaurado.is_(False),
            GastronomiaPedidoItemConsumo.fecha_creacion >= inicio,
            GastronomiaPedidoItemConsumo.fecha_creacion < fin,
        )
        .group_by(GastronomiaPedidoItem.producto_id)
        .all()
    )
    return {int(producto_id): int(cantidad or 0) for producto_id, cantidad in filas}


def _costo(cliente_id: int, producto_id: int) -> float | None:
    return costos_unitarios_receta(cliente_id, [int(producto_id)]).get(int(producto_id)) or None


def _cantidad(valor) -> int:
    cantidad = _entero(valor, 'Cantidad invalida.')
    if cantidad <= 0 or cantidad > CANTIDAD_MAX:
        raise ValueError(f'La cantidad tiene que estar entre 1 y {CANTIDAD_MAX}.')
    return cantidad


def _motivo(valor) -> str:
    motivo = str(valor or '').strip()
    if motivo not in MOTIVOS_MERMA or motivo == MOTIVO_FALTANTE:
        raise ValueError('Elegi el motivo de la merma.')
    return motivo


def _entero(valor, mensaje: str) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(mensaje)
