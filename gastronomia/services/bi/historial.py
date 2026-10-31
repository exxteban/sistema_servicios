"""Historial de compras por telefono para la cola de clientes que vuelven (BI-02).

- Cuenta solo pedidos validos (criterios_base): sin cancelados, importados ni encargos.
- No tiene limite de periodo: un cliente que dejo de comprar tambien aparece.
- Identidad: telefono normalizado del pedido; si no hay uno valido, el del cliente final.
- Nunca agrupa por nombre. El nombre mostrado es el del pedido mas reciente.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app import db
from app.utils.helpers import utc_naive_to_local
from gastronomia.customer_models import GastronomiaClienteFinal
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem
from gastronomia.services.bi.identidad import telefono_normalizado as normalizar_celular
from gastronomia.services.bi.pedidos_validos import criterios_base


@dataclass
class ClienteHistorial:
    telefono: str
    nombre: str = ''
    ultimo_pedido_id: int = 0
    fechas: list = field(default_factory=list)  # datetimes UTC de cada pedido valido
    dias: set = field(default_factory=set)  # dias locales con al menos un pedido valido
    productos: Counter = field(default_factory=Counter)

    @property
    def plato_favorito(self) -> str | None:
        return self.productos.most_common(1)[0][0] if self.productos else None


def historial_clientes(cliente_id: int) -> dict[str, ClienteHistorial]:
    filas = (
        db.session.query(
            GastronomiaPedido.id_pedido,
            GastronomiaPedido.fecha_creacion,
            GastronomiaPedido.nombre_cliente,
            GastronomiaPedido.celular_cliente,
            GastronomiaClienteFinal.telefono_normalizado.label('telefono_tienda'),
        )
        .outerjoin(GastronomiaClienteFinal, GastronomiaClienteFinal.id_cliente_final == GastronomiaPedido.cliente_final_id)
        .filter(*criterios_base(cliente_id))
        .order_by(GastronomiaPedido.fecha_creacion.asc(), GastronomiaPedido.id_pedido.asc())
        .all()
    )
    historial: dict[str, ClienteHistorial] = {}
    telefono_por_pedido: dict[int, str] = {}
    for fila in filas:
        telefono = normalizar_celular(fila.celular_cliente) or fila.telefono_tienda
        if not telefono:
            continue
        telefono_por_pedido[int(fila.id_pedido)] = telefono
        cliente = historial.setdefault(telefono, ClienteHistorial(telefono=telefono))
        cliente.fechas.append(fila.fecha_creacion)
        cliente.dias.add(utc_naive_to_local(fila.fecha_creacion).date())
        cliente.ultimo_pedido_id = int(fila.id_pedido)
        cliente.nombre = (fila.nombre_cliente or '').strip() or cliente.nombre
    _sumar_productos(cliente_id, historial, telefono_por_pedido)
    return historial


def _sumar_productos(cliente_id: int, historial: dict[str, ClienteHistorial], telefono_por_pedido: dict[int, str]) -> None:
    if not telefono_por_pedido:
        return
    items = (
        db.session.query(
            GastronomiaPedidoItem.pedido_id,
            GastronomiaPedidoItem.nombre_producto,
            GastronomiaPedidoItem.cantidad,
        )
        .join(GastronomiaPedido, GastronomiaPedido.id_pedido == GastronomiaPedidoItem.pedido_id)
        .filter(*criterios_base(cliente_id))
        .all()
    )
    for pedido_id, nombre, cantidad in items:
        telefono = telefono_por_pedido.get(int(pedido_id))
        if telefono:
            historial[telefono].productos[nombre or 'Producto'] += int(cantidad or 0)
