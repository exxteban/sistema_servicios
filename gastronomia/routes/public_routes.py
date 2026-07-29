"""Seguimiento publico de pedidos gastronomicos."""
from flask import abort, jsonify, make_response, render_template
from flask_login import current_user

from app.utils.helpers import utc_isoformat
from gastronomia.models import GastronomiaDeliveryUbicacion, GastronomiaPedido, GastronomiaPedidoEvento
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.delivery_gps import ubicacion_delivery_publicable_filter
from gastronomia.services.delivery_privacy import puede_ver_localizacion_delivery


MENSAJES_SEGUIMIENTO = {
    'abierto': 'Recibimos tu pedido.',
    'enviado_cocina': 'Tu pedido fue enviado a cocina.',
    'preparando': 'Estamos preparando tu pedido.',
    'listo': 'Tu pedido esta listo.',
    'en_camino': 'Tu pedido ya salio con el delivery.',
    'entregado': 'Tu pedido fue entregado.',
    'cobrado': 'Tu pedido fue cobrado.',
    'cancelado': 'Tu pedido fue cancelado.',
}


@gastronomia_bp.route('/pedido/<codigo_publico>')
def seguimiento_pedido_publico(codigo_publico):
    pedido = _obtener_pedido_publico(codigo_publico)
    eventos = _eventos_pedido(pedido)
    tracking = _tracking_delivery(pedido)
    response = make_response(
        render_template(
            'gastronomia/seguimiento_pedido.html',
            pedido=pedido,
            eventos=eventos,
            mensajes=MENSAJES_SEGUIMIENTO,
            tracking=tracking,
        )
    )
    return _sin_cache(response)


@gastronomia_bp.route('/pedido/<codigo_publico>/estado')
def seguimiento_pedido_estado_publico(codigo_publico):
    pedido = _obtener_pedido_publico(codigo_publico)
    response = jsonify({
        'ok': True,
        'pedido': {
            'estado': pedido.estado,
            'estado_label': _estado_label(pedido.estado),
            'mensaje': MENSAJES_SEGUIMIENTO.get(pedido.estado, 'Tu pedido fue actualizado.'),
            'fecha_modificacion': utc_isoformat(pedido.fecha_modificacion),
        },
        'tracking': _tracking_delivery(pedido),
        'eventos': [_evento_dict(evento) for evento in _eventos_pedido(pedido)],
    })
    return _sin_cache(response)


def _obtener_pedido_publico(codigo_publico):
    codigo = (codigo_publico or '').strip().upper()[:32]
    if not codigo:
        abort(404)
    pedido = GastronomiaPedido.query.filter_by(codigo_publico=codigo).first()
    if pedido is None:
        abort(404)
    return pedido


def _eventos_pedido(pedido):
    return (
        GastronomiaPedidoEvento.query
        .filter_by(cliente_id=pedido.cliente_id, pedido_id=pedido.id_pedido)
        .order_by(GastronomiaPedidoEvento.fecha_evento.asc())
        .all()
    )


def _evento_dict(evento):
    return {
        'tipo': evento.tipo,
        'label': _estado_label((evento.tipo or '').replace('pedido_', '')),
        'fecha_evento': utc_isoformat(evento.fecha_evento),
    }


def _tracking_delivery(pedido):
    if pedido.tipo_pedido != 'delivery' or pedido.estado != 'en_camino':
        return {'visible': False}
    if not puede_ver_localizacion_delivery(current_user):
        return {'visible': False}
    destino = None
    if pedido.destino_latitud is not None and pedido.destino_longitud is not None:
        destino = {'latitud': pedido.destino_latitud, 'longitud': pedido.destino_longitud}
    ultima_ubicacion = (
        GastronomiaDeliveryUbicacion.query
        .filter_by(cliente_id=pedido.cliente_id, pedido_id=pedido.id_pedido)
        .order_by(GastronomiaDeliveryUbicacion.fecha_registro.desc(), GastronomiaDeliveryUbicacion.id_ubicacion.desc())
        .first()
    )
    ubicacion_publicable = (
        GastronomiaDeliveryUbicacion.query
        .filter_by(cliente_id=pedido.cliente_id, pedido_id=pedido.id_pedido)
        .filter(ubicacion_delivery_publicable_filter())
        .order_by(GastronomiaDeliveryUbicacion.fecha_registro.desc(), GastronomiaDeliveryUbicacion.id_ubicacion.desc())
        .first()
    )
    gps_impreciso = ultima_ubicacion and not ubicacion_publicable
    return {
        'visible': True,
        'delivery': _ubicacion_dict(ubicacion_publicable),
        'delivery_impreciso': _ubicacion_dict(ultima_ubicacion) if gps_impreciso else None,
        'destino': destino,
    }


def _ubicacion_dict(ubicacion):
    if not ubicacion:
        return None
    data = ubicacion.to_dict()
    data['fecha_registro'] = utc_isoformat(ubicacion.fecha_registro)
    return data


def _estado_label(estado):
    return (estado or '').replace('_', ' ').title()


def _sin_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
