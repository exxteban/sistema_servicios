"""Serializacion de pedidos gastronomicos para la API y los eventos."""
from __future__ import annotations

from app.utils.public_url import build_public_url
from gastronomia.models import (
    GastronomiaDeliveryUbicacion,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaPedidoItemModificador,
    GastronomiaPedidoPago,
)
from gastronomia.services.delivery_gps import ubicacion_delivery_publicable_filter
from gastronomia.services.encargo_consultas import datos_encargo, fotos_por_pedido, senas_vigentes_por_pedido
from gastronomia.services.stock_service import alertas_stock_pedido


def serializar_pedidos(pedidos: list[GastronomiaPedido]) -> list[dict]:
    if not pedidos:
        return []

    pedido_ids = [int(pedido.id_pedido) for pedido in pedidos]
    cliente_ids = {int(pedido.cliente_id) for pedido in pedidos}
    pagos = (
        GastronomiaPedidoPago.query
        .filter(
            GastronomiaPedidoPago.cliente_id.in_(cliente_ids),
            GastronomiaPedidoPago.pedido_id.in_(pedido_ids),
        )
        .all()
    )
    pagos_por_pedido = {int(pago.pedido_id): pago for pago in pagos}

    items = (
        GastronomiaPedidoItem.query
        .filter(
            GastronomiaPedidoItem.cliente_id.in_(cliente_ids),
            GastronomiaPedidoItem.pedido_id.in_(pedido_ids),
        )
        .order_by(GastronomiaPedidoItem.id_item.asc())
        .all()
    )
    item_ids = [int(item.id_item) for item in items]
    modificadores_por_item = {item_id: [] for item_id in item_ids}
    if item_ids:
        modificadores = (
            GastronomiaPedidoItemModificador.query
            .filter(
                GastronomiaPedidoItemModificador.cliente_id.in_(cliente_ids),
                GastronomiaPedidoItemModificador.item_id.in_(item_ids),
            )
            .order_by(GastronomiaPedidoItemModificador.id_modificador.asc())
            .all()
        )
        for modificador in modificadores:
            modificadores_por_item.setdefault(int(modificador.item_id), []).append(modificador.to_dict())

    items_por_pedido = {pedido_id: [] for pedido_id in pedido_ids}
    for item in items:
        item_data = {
            'id_item': item.id_item,
            'producto_id': item.producto_id,
            'canal_precio': item.canal_precio,
            'nombre_producto': item.nombre_producto,
            'cantidad': int(item.cantidad or 0),
            'precio_unitario': float(item.precio_unitario or 0),
            'precio_original': float(item.precio_original or 0),
            'descuento_linea': float(item.descuento_linea or 0),
            'id_promocion_aplicada': item.id_promocion_aplicada,
            'promocion_descripcion': item.promocion_descripcion,
            'cantidad_bonificada': int(item.cantidad_bonificada or 0),
            'notas': item.notas,
            'subtotal': float(item.subtotal or 0),
            'modificadores': modificadores_por_item.get(int(item.id_item), []),
        }
        if item.texto_personalizado:
            item_data['texto_personalizado'] = item.texto_personalizado
        items_por_pedido.setdefault(int(item.pedido_id), []).append(item_data)

    ubicaciones_delivery = (
        GastronomiaDeliveryUbicacion.query
        .filter(
            GastronomiaDeliveryUbicacion.cliente_id.in_(cliente_ids),
            GastronomiaDeliveryUbicacion.pedido_id.in_(pedido_ids),
            ubicacion_delivery_publicable_filter(),
        )
        .order_by(GastronomiaDeliveryUbicacion.fecha_registro.desc(), GastronomiaDeliveryUbicacion.id_ubicacion.desc())
        .all()
    )
    ubicacion_por_pedido = {}
    for ubicacion in ubicaciones_delivery:
        ubicacion_por_pedido.setdefault(int(ubicacion.pedido_id), ubicacion)

    encargo_ids = [int(pedido.id_pedido) for pedido in pedidos if pedido.es_encargo]
    senas = senas_vigentes_por_pedido(encargo_ids)
    fotos = fotos_por_pedido(encargo_ids)
    resultado = []
    for pedido in pedidos:
        data = _pedido_to_dict_prearmado(
            pedido,
            pago=pagos_por_pedido.get(int(pedido.id_pedido)),
            items=items_por_pedido.get(int(pedido.id_pedido), []),
            ubicacion_delivery=ubicacion_por_pedido.get(int(pedido.id_pedido)),
        )
        if pedido.es_encargo:
            pedido_id = int(pedido.id_pedido)
            data.update(datos_encargo(pedido, sena=senas.get(pedido_id, 0), fotos=fotos.get(pedido_id, [])))
        resultado.append(data)
    return resultado


def _pedido_to_dict_prearmado(
    pedido: GastronomiaPedido,
    *,
    pago: GastronomiaPedidoPago | None,
    items: list[dict],
    ubicacion_delivery: GastronomiaDeliveryUbicacion | None = None,
) -> dict:
    pago_data = pago.to_dict() if pago else None
    url_seguimiento = f'/gastronomia/pedido/{pedido.codigo_publico}' if pedido.codigo_publico else None
    return {
        'id_pedido': pedido.id_pedido,
        'codigo_entrega': pedido.codigo_entrega,
        'cliente_id': pedido.cliente_id,
        'usuario_id': pedido.usuario_id,
        'tipo_pedido': pedido.tipo_pedido,
        'origen_pedido': pedido.origen_pedido,
        'es_encargo': bool(pedido.es_encargo),
        'fecha_programada': pedido.fecha_programada.isoformat() if pedido.fecha_programada else None,
        'codigo_publico': pedido.codigo_publico,
        'url_seguimiento': url_seguimiento,
        'url_seguimiento_publica': _url_seguimiento_publica(pedido.codigo_publico),
        'mesa': pedido.mesa,
        'referencia_entrega': pedido.referencia_entrega,
        'nombre_cliente': pedido.nombre_cliente,
        'celular_cliente': pedido.celular_cliente,
        'direccion_entrega': pedido.direccion_entrega,
        'ubicacion_entrega_url': pedido.ubicacion_entrega_url,
        'destino_latitud': pedido.destino_latitud,
        'destino_longitud': pedido.destino_longitud,
        'tiempo_estimado_minutos': pedido.tiempo_estimado_minutos,
        'repartidor_id': pedido.repartidor_id,
        'repartidor': pedido.repartidor.to_dict() if pedido.repartidor else None,
        'estado': pedido.estado,
        'notas': pedido.notas,
        'subtotal': float(pedido.subtotal or 0),
        'costo_envio': float(pedido.costo_envio or 0),
        'total': float(pedido.total or 0),
        'fecha_creacion': pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None,
        'fecha_envio_cocina': pedido.fecha_envio_cocina.isoformat() if pedido.fecha_envio_cocina else None,
        'fecha_inicio_preparacion': pedido.fecha_inicio_preparacion.isoformat() if pedido.fecha_inicio_preparacion else None,
        'fecha_listo': pedido.fecha_listo.isoformat() if pedido.fecha_listo else None,
        'fecha_asignacion_delivery': pedido.fecha_asignacion_delivery.isoformat() if pedido.fecha_asignacion_delivery else None,
        'fecha_entrega': pedido.fecha_entrega.isoformat() if pedido.fecha_entrega else None,
        'pagado': bool(pago),
        'estado_pago': 'pagado' if pago else 'pendiente',
        'pago': pago_data,
        'items': items,
        'ultima_ubicacion_delivery': ubicacion_delivery.to_dict() if ubicacion_delivery else None,
        'alertas_stock': alertas_stock_pedido(pedido.id_pedido),
    }


def _url_seguimiento_publica(codigo_publico: str | None) -> str | None:
    if not codigo_publico:
        return None
    return build_public_url(
        'gastronomia.seguimiento_pedido_publico',
        codigo_publico=codigo_publico,
    )
