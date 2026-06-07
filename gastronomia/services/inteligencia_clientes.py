"""Clientes frecuentes detectados desde pedidos gastronomicos cobrados."""
from __future__ import annotations

from collections import defaultdict

from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from app.utils.phone_utils import formatear_telefono_display, normalizar_telefono
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago


def clientes_frecuentes_gastronomia(cliente_id: int, periodo: dict, limite: int = 6) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    pedidos = (
        GastronomiaPedido.query
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .all()
    )
    if not pedidos:
        return []

    clientes = {}
    pedido_ids_por_cliente = defaultdict(list)
    for pedido in pedidos:
        clave = _clave_cliente(pedido)
        if not clave:
            continue
        item = clientes.setdefault(clave, _cliente_base(pedido))
        item['pedidos'] += 1
        item['total'] += float(pedido.pago.total_cobrado or 0) if pedido.pago else 0
        item['canales'].add((pedido.tipo_pedido or 'mostrador').strip().lower())
        fecha_pago = pedido.pago.fecha_pago if pedido.pago else None
        if fecha_pago and (not item['ultima_visita'] or fecha_pago > item['ultima_visita']):
            item['ultima_visita'] = fecha_pago
        pedido_ids_por_cliente[clave].append(int(pedido.id_pedido))

    frecuentes = [item for item in clientes.values() if item['pedidos'] >= 2]
    if not frecuentes:
        return []

    claves_frecuentes = {item['clave'] for item in frecuentes}
    favoritos = _productos_favoritos(
        cliente_id,
        {clave: ids for clave, ids in pedido_ids_por_cliente.items() if clave in claves_frecuentes},
    )
    for item in frecuentes:
        item['producto_favorito'] = favoritos.get(item['clave'], 'Menu variado')

    frecuentes.sort(key=lambda item: (-item['pedidos'], -item['total'], item['nombre'].lower()))
    return [_serializar_cliente(item) for item in frecuentes[:max(1, min(20, int(limite or 6)))]]


def _clave_cliente(pedido: GastronomiaPedido) -> str | None:
    telefono = normalizar_telefono((pedido.celular_cliente or '').strip()) if pedido.celular_cliente else None
    if telefono:
        return f'tel:{telefono}'
    nombre = (pedido.nombre_cliente or pedido.referencia_entrega or '').strip().lower()
    return f'nombre:{nombre}' if nombre else None


def _cliente_base(pedido: GastronomiaPedido) -> dict:
    telefono_normalizado = normalizar_telefono((pedido.celular_cliente or '').strip()) if pedido.celular_cliente else None
    return {
        'clave': _clave_cliente(pedido),
        'nombre': (pedido.nombre_cliente or pedido.referencia_entrega or 'Cliente frecuente').strip(),
        'telefono_normalizado': telefono_normalizado,
        'telefono': (pedido.celular_cliente or '').strip(),
        'pedidos': 0,
        'total': 0.0,
        'canales': set(),
        'ultima_visita': None,
        'producto_favorito': 'Menu variado',
    }


def _productos_favoritos(cliente_id: int, pedido_ids_por_cliente: dict[str, list[int]]) -> dict[str, str]:
    pedido_a_cliente = {
        pedido_id: clave
        for clave, pedido_ids in pedido_ids_por_cliente.items()
        for pedido_id in pedido_ids
    }
    if not pedido_a_cliente:
        return {}
    filas = (
        GastronomiaPedidoItem.query
        .filter(
            GastronomiaPedidoItem.cliente_id == int(cliente_id),
            GastronomiaPedidoItem.pedido_id.in_(list(pedido_a_cliente.keys())),
        )
        .all()
    )
    productos = defaultdict(lambda: defaultdict(int))
    for item in filas:
        clave = pedido_a_cliente.get(int(item.pedido_id))
        if not clave:
            continue
        productos[clave][item.nombre_producto or 'Producto'] += int(item.cantidad or 0)
    return {
        clave: sorted(items.items(), key=lambda row: (-row[1], row[0].lower()))[0][0]
        for clave, items in productos.items()
        if items
    }


def _serializar_cliente(cliente: dict) -> dict:
    ticket_promedio = cliente['total'] / cliente['pedidos'] if cliente['pedidos'] else 0
    telefono_normalizado = cliente.get('telefono_normalizado') or ''
    telefono_label = formatear_telefono_display(telefono_normalizado) if telefono_normalizado else 'Sin telefono'
    ultima_visita = utc_naive_to_local(cliente.get('ultima_visita')) if cliente.get('ultima_visita') else None
    return {
        'nombre': cliente['nombre'],
        'telefono_label': telefono_label,
        'whatsapp_url': f"https://wa.me/{telefono_normalizado.replace('+', '')}" if telefono_normalizado else None,
        'pedidos': int(cliente['pedidos']),
        'total': round(cliente['total'], 2),
        'total_label': _formatear_moneda(cliente['total']),
        'ticket_promedio_label': _formatear_moneda(ticket_promedio),
        'ultima_visita_label': ultima_visita.strftime('%d/%m %H:%M') if ultima_visita else 'Sin fecha',
        'producto_favorito': cliente.get('producto_favorito') or 'Menu variado',
        'canales_label': ', '.join(_canal_label(canal) for canal in sorted(cliente['canales'])) or 'Mostrador',
        'accion': 'Cuidarlo con beneficio, combo o mensaje directo antes de que deje de volver.',
    }


def _canal_label(canal: str) -> str:
    labels = {'mesa': 'Salon', 'salon': 'Salon', 'mostrador': 'Mostrador', 'retiro': 'Retiro', 'delivery': 'Delivery'}
    return labels.get((canal or '').strip().lower(), (canal or 'Mostrador').title())


def _formatear_moneda(valor: float) -> str:
    return f'₲ {float(valor or 0):,.0f}'.replace(',', '.')
