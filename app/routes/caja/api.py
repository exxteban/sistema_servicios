import hashlib
from datetime import datetime

from flask import jsonify, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import ColaCobro, Configuracion, MetodoPago, SesionCaja
from app.routes.caja import caja_bp
from app.routes.caja.cola_cobro import (
    VALID_QUEUE_STATES,
    VALID_QUEUE_TYPES,
    aplicar_filtros_cola_cobro,
    construir_query_base_cola_cobro,
    normalizar_filtros_cola_cobro,
    puede_acceder_cola_cobro,
)
from app.routes.ventas import (
    _build_pos_data_from_cola_cobro,
    _build_venta_items_payload_from_pos_items,
    _procesar_venta_payload,
    _venta_existente_response,
)
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.helpers import local_strftime
from cobranzas.services import registrar_cobro_credito_desde_cola
from pedidos.services import registrar_cobro_pedido_desde_cola


def _payload_request():
    return request.get_json(silent=True) or request.form.to_dict() or {}


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_iso(value):
    if value is None:
        return ''
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _sesion_abierta_actual():
    return SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()


def _registrar_auditoria_cola(accion, item, descripcion, datos_anteriores=None, datos_nuevos=None):
    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion=accion,
                modulo='caja',
                descripcion=descripcion,
                referencia_tipo='cola_cobro',
                referencia_id=item.id,
                datos_anteriores=datos_anteriores or None,
                datos_nuevos=datos_nuevos or None,
                commit=False
            )
    except Exception:
        pass


def _resolver_metodo_pago(payload):
    metodo_id = payload.get('id_metodo_pago')
    if metodo_id not in (None, ''):
        try:
            metodo_id = int(metodo_id)
        except Exception:
            return None, ({'error': 'id_metodo_pago inválido'}, 400)
        metodo = db.session.get(MetodoPago, metodo_id)
        if not metodo or not bool(getattr(metodo, 'activo', True)):
            return None, ({'error': 'Método de pago no encontrado o inactivo'}, 400)
        return metodo, None

    metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
    if metodo:
        return metodo, None

    metodo = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc()).first()
    if metodo:
        return metodo, None

    return None, ({'error': 'No hay métodos de pago activos configurados'}, 400)


def _asegurar_en_proceso(cola_id, commit=True):
    usuario_id = int(current_user.id_usuario)
    ahora = datetime.utcnow()

    filas_actualizadas = (
        db.session.query(ColaCobro)
        .filter(
            ColaCobro.id == cola_id,
            ColaCobro.estado == 'pendiente',
            or_(ColaCobro.id_usuario_destino.is_(None), ColaCobro.id_usuario_destino == usuario_id)
        )
        .update(
            {
                ColaCobro.estado: 'en_proceso',
                ColaCobro.id_usuario_destino: usuario_id,
                ColaCobro.fecha_toma: ahora,
            },
            synchronize_session=False
        )
    )

    if filas_actualizadas:
        db.session.expire_all()
        item = db.session.get(ColaCobro, cola_id)
        _registrar_auditoria_cola(
            'tomar_pendiente_caja',
            item,
            f'Tomó pendiente de caja #{item.id}',
            datos_anteriores={'estado': 'pendiente'},
            datos_nuevos={
                'estado': item.estado,
                'id_usuario_destino': int(current_user.id_usuario),
                'fecha_toma': item.fecha_toma.isoformat() if item.fecha_toma else None,
            }
        )
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return item, None, None

    db.session.expire_all()
    item = db.session.get(ColaCobro, cola_id)
    if not item:
        return None, {'error': 'Pendiente de cobro no encontrado'}, 404
    if item.estado in ('cobrado', 'cancelado'):
        return item, {'error': 'Este pendiente ya no está disponible'}, 400
    if item.id_usuario_destino and int(item.id_usuario_destino) != usuario_id:
        return item, {'error': 'Este pendiente está asignado a otro cajero'}, 400
    if item.estado == 'en_proceso':
        if item.fecha_toma is None:
            item.fecha_toma = ahora
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        return item, None, None
    return item, {'error': 'No se pudo tomar el pendiente. Intente nuevamente'}, 409


@caja_bp.route('/api/pagos-detalle/<int:id_metodo>')
@login_required
def detalle_pagos_metodo(id_metodo):
    """Obtener detalle de pagos por método para la sesión actual"""
    sesion = _sesion_abierta_actual()
    if not sesion:
        return jsonify({'error': 'No hay sesión abierta'}), 404

    from sqlalchemy.orm import joinedload
    from app.models import PagoVenta, Venta
    from pedidos.models import PedidoCliente, PedidoClientePago

    pagos_ventas = db.session.query(
        PagoVenta, Venta
    ).join(
        Venta, PagoVenta.id_venta == Venta.id_venta
    ).options(
        joinedload(Venta.cliente)
    ).filter(
        Venta.id_sesion_caja == sesion.id_sesion,
        Venta.estado == 'completada',
        PagoVenta.id_metodo_pago == id_metodo
    ).order_by(Venta.fecha_venta.desc()).all()

    pagos_pedidos = db.session.query(
        PedidoClientePago, PedidoCliente
    ).join(
        PedidoCliente, PedidoClientePago.id_pedido == PedidoCliente.id_pedido
    ).options(
        joinedload(PedidoCliente.cliente)
    ).filter(
        PedidoClientePago.id_sesion_caja == sesion.id_sesion,
        PedidoClientePago.estado == 'activo',
        PedidoClientePago.id_metodo_pago == id_metodo
    ).order_by(PedidoClientePago.fecha_pago.desc()).all()

    resultado = []
    for pago, venta in pagos_ventas:
        cliente_nombre = 'Consumidor Final'
        if venta.cliente:
            cliente_nombre = venta.cliente.nombre or 'Consumidor Final'

        resultado.append((venta.fecha_venta, {
            'row_key': f'venta-{int(venta.id_venta)}-{int(pago.id_pago)}',
            'tipo_origen': 'venta',
            'id_venta': venta.id_venta,
            'id_referencia': venta.id_venta,
            'fecha': local_strftime(venta.fecha_venta),
            'monto': float(pago.monto or 0),
            'cliente': cliente_nombre,
            'referencia_label': f'Venta #{int(venta.id_venta)}',
            'referencia': pago.referencia or ''
        }))

    for pago, pedido in pagos_pedidos:
        cliente_nombre = 'Consumidor Final'
        if pedido.cliente:
            cliente_nombre = pedido.cliente.nombre or 'Consumidor Final'

        venta_generada_id = int(pedido.id_venta_generada) if pedido.id_venta_generada else None
        resultado.append((pago.fecha_pago, {
            'row_key': f'pedido-{int(pedido.id_pedido)}-{int(pago.id_pago_pedido)}',
            'tipo_origen': 'pedido',
            'id_venta': venta_generada_id,
            'id_referencia': int(pedido.id_pedido),
            'fecha': local_strftime(pago.fecha_pago),
            'monto': float(pago.monto or 0),
            'cliente': cliente_nombre,
            'referencia_label': pedido.numero_pedido_display,
            'referencia': pago.referencia or ''
        }))

    resultado.sort(key=lambda item: item[0] or datetime.min, reverse=True)

    return jsonify([item for _, item in resultado])


@caja_bp.route('/api/cola-cobro/resumen')
@login_required
def cola_cobro_resumen():
    if not puede_acceder_cola_cobro(current_user):
        return jsonify({'error': 'Sin permisos'}), 403

    forzar_activa = (request.args.get('forzar_activa', '0') or '0').strip().lower() in {'1', 'true', 'si', 'sí', 'yes'}
    alerta_activa = Configuracion.obtener_bool('caja_alerta_pendientes_activa', default=False) or forzar_activa
    if not alerta_activa:
        return jsonify({'count': 0, 'pendientes': [], 'alerta_activa': False})

    incluir_detalle = (request.args.get('detalle', '1') or '1').strip().lower() not in {'0', 'false', 'no'}
    incluir_firma = (request.args.get('firma', '0') or '0').strip().lower() in {'1', 'true', 'si', 'sí', 'yes'}
    filtros = normalizar_filtros_cola_cobro(
        cola_tipo=request.args.get('cola_tipo', 'todas'),
        cola_estado=request.args.get('cola_estado', 'todas'),
        cola_scope=request.args.get('cola_scope', 'todas'),
        default_estado='todas',
    )

    query_base = construir_query_base_cola_cobro()
    total, total_pendiente, total_en_proceso = (
        query_base.with_entities(
            func.count(ColaCobro.id),
            func.coalesce(func.sum(case((ColaCobro.estado == 'pendiente', 1), else_=0)), 0),
            func.coalesce(func.sum(case((ColaCobro.estado == 'en_proceso', 1), else_=0)), 0),
        ).one()
    )
    total_venta, total_reparacion, total_cobro_credito, total_pedido = (
        query_base.with_entities(
            func.coalesce(func.sum(case((ColaCobro.tipo_origen == 'venta', 1), else_=0)), 0),
            func.coalesce(func.sum(case((ColaCobro.tipo_origen == 'reparacion', 1), else_=0)), 0),
            func.coalesce(func.sum(case((ColaCobro.tipo_origen == 'cobro_credito', 1), else_=0)), 0),
            func.coalesce(func.sum(case((ColaCobro.tipo_origen == 'pedido', 1), else_=0)), 0),
        ).one()
    )
    totales = {
        'total': _safe_int(total),
        'pendiente': _safe_int(total_pendiente),
        'en_proceso': _safe_int(total_en_proceso),
        'venta': _safe_int(total_venta),
        'reparacion': _safe_int(total_reparacion),
        'cobro_credito': _safe_int(total_cobro_credito),
        'pedido': _safe_int(total_pedido),
    }

    query = aplicar_filtros_cola_cobro(query_base, filtros, usuario=current_user)
    count = query.count()

    items = []
    if incluir_detalle:
        limit = request.args.get('limit', 20, type=int) or 20
        limit = max(1, min(limit, 100))
        pendientes = query.order_by(ColaCobro.fecha_envio.asc()).limit(limit).all()
        for p in pendientes:
            try:
                items.append({
                    'id': _safe_int(getattr(p, 'id', 0)),
                    'tipo_origen': getattr(p, 'tipo_origen', None) or 'venta',
                    'id_origen': _safe_int(getattr(p, 'id_origen', 0)),
                    'estado': getattr(p, 'estado', None) or 'pendiente',
                    'monto_total': _safe_float(getattr(p, 'monto_total', 0)),
                    'cliente': ((p.cliente.nombre if p.cliente else '') or '').strip() or 'Consumidor Final',
                    'fecha_envio': local_strftime(p.fecha_envio) if p.fecha_envio else '',
                    'id_usuario_destino': _safe_int(p.id_usuario_destino) if getattr(p, 'id_usuario_destino', None) else None,
                    'usuario_destino': ((p.usuario_destino.nombre_completo if p.usuario_destino else '') or '').strip(),
                })
            except Exception:
                continue

    firma = None
    if incluir_firma:
        firma_row = (
            query.with_entities(
                func.count(ColaCobro.id),
                func.coalesce(func.sum(ColaCobro.id), 0),
                func.coalesce(func.sum(case((ColaCobro.estado == 'pendiente', ColaCobro.id), else_=0)), 0),
                func.coalesce(func.sum(case((ColaCobro.estado == 'en_proceso', ColaCobro.id), else_=0)), 0),
                func.coalesce(func.sum(ColaCobro.id_usuario_destino), 0),
                func.coalesce(func.sum(ColaCobro.id_origen), 0),
                func.coalesce(func.sum(case((ColaCobro.tipo_origen == 'reparacion', ColaCobro.id), else_=0)), 0),
                func.coalesce(func.max(ColaCobro.id), 0),
                func.max(ColaCobro.fecha_envio),
                func.max(ColaCobro.fecha_toma),
            ).one()
        )
        firma = hashlib.sha1(
            '|'.join([
                str(_safe_int(firma_row[0])),
                str(_safe_int(firma_row[1])),
                str(_safe_int(firma_row[2])),
                str(_safe_int(firma_row[3])),
                str(_safe_int(firma_row[4])),
                str(_safe_int(firma_row[5])),
                str(_safe_int(firma_row[6])),
                str(_safe_int(firma_row[7])),
                _safe_iso(firma_row[8]),
                _safe_iso(firma_row[9]),
            ]).encode('utf-8')
        ).hexdigest()

    payload = {
        'count': count,
        'pendientes': items,
        'alerta_activa': True,
        'totales': totales,
        'filtros': {
            'cola_tipo': filtros['tipo'],
            'cola_estado': filtros['estado'],
            'cola_scope': filtros['scope'],
        },
    }
    if firma is not None:
        payload['firma'] = firma
    return jsonify(payload)


@caja_bp.route('/api/cola-cobro/<int:cola_id>/tomar', methods=['POST'])
@login_required
def cola_cobro_tomar(cola_id):
    if not current_user.es_admin() and not current_user.tiene_permiso('tomar_cola_cobro'):
        return jsonify({'error': 'Sin permisos'}), 403

    sesion = _sesion_abierta_actual()
    if not sesion:
        return jsonify({'error': 'Debe abrir caja para cobrar pendientes'}), 400

    item, error, status = _asegurar_en_proceso(cola_id)
    if error:
        return jsonify(error), status

    tipo_origen = (item.tipo_origen or '').strip().lower()
    if tipo_origen == 'cobro_credito':
        redirect_url = url_for('cobranzas_cobros.pos_cobro_cola', cola_id=item.id, rt=int(datetime.utcnow().timestamp() * 1000))
    elif tipo_origen == 'pedido':
        redirect_url = url_for('pedidos_caja.pos_cobro_cola', cola_id=item.id, rt=int(datetime.utcnow().timestamp() * 1000))
    else:
        redirect_url = url_for('ventas.pos', cola_id=item.id, rt=int(datetime.utcnow().timestamp() * 1000))
    return jsonify({'success': True, 'redirect_url': redirect_url})


@caja_bp.route('/api/cola-cobro/<int:cola_id>/liberar', methods=['POST'])
@login_required
def cola_cobro_liberar(cola_id):
    if not current_user.es_admin() and not current_user.tiene_permiso('tomar_cola_cobro'):
        return jsonify({'error': 'Sin permisos'}), 403

    sesion = _sesion_abierta_actual()
    if not sesion:
        return jsonify({'error': 'Debe abrir caja para administrar pendientes'}), 400

    item = db.session.get(ColaCobro, cola_id)
    if not item:
        return jsonify({'error': 'Pendiente de cobro no encontrado'}), 404
    if item.estado in ('cobrado', 'cancelado'):
        return jsonify({'error': 'Este pendiente ya no está disponible'}), 400
    if item.id_usuario_destino and int(item.id_usuario_destino) != int(current_user.id_usuario) and not current_user.es_admin():
        return jsonify({'error': 'Este pendiente está asignado a otro cajero'}), 400
    if item.estado == 'pendiente' and not item.id_usuario_destino and item.fecha_toma is None:
        return jsonify({'success': True, 'message': f'Pendiente #{item.id} ya estaba liberado'})
    if item.estado != 'en_proceso':
        return jsonify({'error': 'Solo se puede liberar un pendiente tomado por caja'}), 400

    estado_anterior = item.estado
    item.estado = 'pendiente'
    item.id_usuario_destino = None
    item.fecha_toma = None
    _registrar_auditoria_cola(
        'liberar_pendiente_caja',
        item,
        f'Liberó pendiente de caja #{item.id}',
        datos_anteriores={'estado': estado_anterior},
        datos_nuevos={'estado': 'pendiente', 'id_usuario_destino': None}
    )
    db.session.commit()
    return jsonify({'success': True, 'message': f'Pendiente #{item.id} liberado'})


@caja_bp.route('/api/cola-cobro/<int:cola_id>/cancelar', methods=['POST'])
@login_required
def cola_cobro_cancelar(cola_id):
    if not current_user.es_admin() and not current_user.tiene_permiso('tomar_cola_cobro'):
        return jsonify({'error': 'Sin permisos'}), 403

    sesion = _sesion_abierta_actual()
    if not sesion:
        return jsonify({'error': 'Debe abrir caja para administrar pendientes'}), 400

    item = db.session.get(ColaCobro, cola_id)
    if not item:
        return jsonify({'error': 'Pendiente de cobro no encontrado'}), 404
    if item.estado == 'cobrado':
        return jsonify({'error': 'Este pendiente ya fue cobrado'}), 400
    if item.estado == 'cancelado':
        return jsonify({'success': True, 'message': f'Pendiente #{item.id} ya estaba cancelado'})
    if item.id_usuario_destino and int(item.id_usuario_destino) != int(current_user.id_usuario) and not current_user.es_admin():
        return jsonify({'error': 'Este pendiente está asignado a otro cajero'}), 400

    payload = _payload_request()
    motivo = (payload.get('motivo') or '').strip() or None
    estado_anterior = item.estado
    metadata = item.get_metadata()
    metadata['cancelado_por_usuario'] = int(current_user.id_usuario)
    if motivo:
        metadata['cancelacion_motivo'] = motivo
    item.estado = 'cancelado'
    item.id_usuario_destino = current_user.id_usuario
    item.set_metadata(metadata)
    _registrar_auditoria_cola(
        'cancelar_pendiente_caja',
        item,
        f'Canceló pendiente de caja #{item.id}',
        datos_anteriores={'estado': estado_anterior},
        datos_nuevos={'estado': 'cancelado', 'motivo': motivo}
    )
    db.session.commit()
    return jsonify({'success': True, 'message': f'Pendiente #{item.id} cancelado'})


@caja_bp.route('/api/cola-cobro/<int:cola_id>/cobrar', methods=['POST'])
@login_required
def cola_cobro_cobrar(cola_id):
    if not current_user.es_admin() and not current_user.tiene_permiso('tomar_cola_cobro'):
        return jsonify({'error': 'Sin permisos'}), 403

    sesion = _sesion_abierta_actual()
    if not sesion:
        return jsonify({'error': 'Debe abrir caja para cobrar pendientes'}), 400

    item = db.session.get(ColaCobro, cola_id)
    if not item:
        return jsonify({'error': 'Pendiente de cobro no encontrado'}), 404
    metadata = item.get_metadata()
    if item.estado == 'cobrado':
        return jsonify({
            'success': True,
            'id_venta': metadata.get('venta_id'),
            'message': f'Pendiente #{item.id} ya estaba cobrado'
        })
    if item.estado == 'cancelado':
        return jsonify({'error': 'Este pendiente fue cancelado'}), 400

    payload = _payload_request()
    metodo_pago, metodo_error = _resolver_metodo_pago(payload)
    if metodo_error:
        error_payload, error_status = metodo_error
        return jsonify(error_payload), error_status

    item, error, status = _asegurar_en_proceso(cola_id, commit=False)
    if error:
        if item and item.estado == 'cobrado':
            metadata = item.get_metadata()
            response_payload = {
                'success': True,
                'id_venta': metadata.get('venta_id'),
                'message': f'Pendiente #{item.id} ya estaba cobrado'
            }
            if (item.tipo_origen or '').strip().lower() == 'cobro_credito':
                response_payload['id_pago_cuenta'] = metadata.get('id_pago_cuenta')
            return jsonify(response_payload)
        return jsonify(error), status

    tipo_origen = (item.tipo_origen or '').strip().lower()
    if tipo_origen == 'pedido':
        try:
            resultado = registrar_cobro_pedido_desde_cola(
                item,
                id_usuario=int(current_user.id_usuario),
                id_metodo_pago=int(metodo_pago.id_metodo_pago),
                monto=payload.get('monto') or float(item.monto_total or 0),
                tipo_pago=(payload.get('tipo_pago') or 'pago_total').strip(),
                referencia=(payload.get('referencia') or '').strip(),
                observaciones=(payload.get('observaciones') or f'Cobro rapido pedido caja #{item.id}').strip(),
                sesion=sesion,
            )
            pago, pedido, movimiento = resultado['pago'], resultado['pedido'], resultado['movimiento_caja']
            db.session.commit()
            return jsonify({'success': True, 'id_pago_pedido': int(pago.id_pago_pedido), 'id_pedido': int(pedido.id_pedido), 'saldo_pendiente': float(pedido.saldo_pendiente or 0), 'estado_pedido': pedido.estado, 'movimiento_caja_id': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 500

    if tipo_origen == 'cobro_credito':
        try:
            estado_anterior = item.estado
            resultado = registrar_cobro_credito_desde_cola(
                item,
                id_usuario=int(current_user.id_usuario),
                id_metodo_pago=int(metodo_pago.id_metodo_pago),
                monto=payload.get('monto') or float(item.monto_total or 0),
                referencia=(payload.get('referencia') or '').strip(),
                observaciones=(payload.get('observaciones') or f'Cobro rápido pendiente caja #{item.id}').strip(),
                sesion=sesion,
            )
            pago = resultado['pago']
            cuenta = resultado['cuenta']
            movimiento = resultado['movimiento_caja']
            saldo_anterior = float(resultado['saldo_anterior'] or 0)
            saldo_nuevo = float(resultado['saldo_nuevo'] or 0)
            detalle_aplicacion = pago.get_detalle_aplicacion() if hasattr(pago, 'get_detalle_aplicacion') else {}

            registrar_auditoria(
                accion='registrar_cobro_credito',
                modulo='cobranzas',
                descripcion=f'Registró cobro a cuenta #{cuenta.id_cuenta_cobrar} desde caja rápida',
                referencia_tipo='cuenta_por_cobrar',
                referencia_id=int(cuenta.id_cuenta_cobrar),
                datos_nuevos={
                    'id_pago_cuenta': int(pago.id_pago_cuenta),
                    'id_venta': int(cuenta.id_venta),
                    'id_cliente': int(cuenta.id_cliente),
                    'monto': float(pago.monto or 0),
                    'saldo_anterior': saldo_anterior,
                    'saldo_nuevo': saldo_nuevo,
                    'metodo_pago': metodo_pago.nombre if metodo_pago else None,
                    'id_movimiento_caja': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
                    'cliente_nombre': detalle_aplicacion.get('cliente_nombre'),
                    'cuota_principal': detalle_aplicacion.get('cuota_principal'),
                    'cuotas_aplicadas': detalle_aplicacion.get('cuotas_aplicadas'),
                },
                commit=False,
            )
            _registrar_auditoria_cola(
                'cobrar_pendiente_credito_caja',
                item,
                f'Cobró pendiente de crédito #{item.id}',
                datos_anteriores={'estado': estado_anterior},
                datos_nuevos={
                    'estado': item.estado,
                    'id_pago_cuenta': int(pago.id_pago_cuenta),
                    'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
                    'id_venta': int(cuenta.id_venta),
                    'numero_cuota_principal': int(pago.numero_cuota_principal or 0) or None,
                },
            )
            db.session.commit()
            return jsonify({
                'success': True,
                'id_pago_cuenta': int(pago.id_pago_cuenta),
                'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
                'id_venta': int(cuenta.id_venta),
                'saldo_pendiente': float(cuenta.saldo_pendiente or 0),
                'estado_cuenta': cuenta.estado,
                'movimiento_caja_id': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
                'numero_cuota_principal': int(pago.numero_cuota_principal or 0) or None,
            })
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 500

    cola_data = _build_pos_data_from_cola_cobro(item)
    items_payload = _build_venta_items_payload_from_pos_items(cola_data.get('items'))

    venta_payload = {
        'items': items_payload,
        'pagos': [{
            'id_metodo_pago': int(metodo_pago.id_metodo_pago),
            'monto': float(item.monto_total or 0),
            'referencia': (payload.get('referencia') or '').strip(),
        }],
        'id_cliente': int(cola_data.get('cliente_id') or 1),
        'id_usuario_vendedor': int(cola_data.get('id_usuario_vendedor') or item.id_usuario_origen),
        'descuento': float(cola_data.get('descuento') or 0),
        'observaciones': (payload.get('observaciones') or cola_data.get('observaciones') or f'Cobro rápido pendiente caja #{item.id}').strip(),
        'cola_cobro_id': int(item.id),
        'client_request_id': (payload.get('client_request_id') or f'cola-cobro-{item.id}').strip(),
    }
    if cola_data.get('reparacion_id'):
        venta_payload['reparacion_id'] = int(cola_data['reparacion_id'])

    try:
        resultado, status = _procesar_venta_payload(venta_payload)
        if status != 200:
            db.session.rollback()
            return jsonify(resultado), status

        item_actual = db.session.get(ColaCobro, item.id)
        if item_actual and item_actual.estado == 'en_proceso':
            db.session.rollback()
        return jsonify(resultado), status
    except IntegrityError:
        db.session.rollback()
        client_request_id = (venta_payload.get('client_request_id') or '').strip()
        if client_request_id:
            from app.models import Venta

            existente = Venta.query.filter_by(client_request_id=client_request_id).first()
            if existente:
                return jsonify(_venta_existente_response(existente))
        return jsonify({'error': 'Conflicto al cobrar pendiente'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
