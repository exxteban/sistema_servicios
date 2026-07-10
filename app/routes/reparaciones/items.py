from datetime import datetime

from flask import jsonify, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Configuracion, DetalleReparacion, Producto, Venta
from app.utils.auditoria_utils import registrar_auditoria

from .base import (
    CLAVE_CAJA_EXIGIR_CAJERO,
    CLAVE_CAJA_FLUJO_ENVIADO,
    _buscar_pendiente_cobro_reparacion_activa,
    _get_detalle_reparacion_or_404_safe,
    _get_reparacion_or_404_safe,
    _motivo_bloqueo_financiero_reparacion,
    _obtener_o_crear_pendiente_cobro_reparacion,
    _puede_cobrar_reparacion_pos,
    _reparacion_tiene_saldo_pendiente,
    reparaciones_bp,
)


@reparaciones_bp.route('/<int:id>/items/agregar', methods=['POST'])
@login_required
def agregar_item(id):
    if not current_user.tiene_permiso('editar_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'No tienes permisos para editar reparaciones', 'modo_demo': False}), 403
    reparacion = _get_reparacion_or_404_safe(id)
    bloqueo = _motivo_bloqueo_financiero_reparacion(reparacion)
    if bloqueo:
        return jsonify({'error': bloqueo}), 409

    id_producto = request.form.get('id_producto')
    cantidad = request.form.get('cantidad', 1, type=int)

    if not id_producto:
        return jsonify({'error': 'Producto no especificado'}), 400
    if cantidad is None or cantidad <= 0:
        return jsonify({'error': 'La cantidad debe ser mayor a cero'}), 400

    producto = db.session.get(Producto, id_producto)
    if not producto:
        return jsonify({'error': 'Producto no encontrado'}), 404

    detalle = DetalleReparacion.query.filter_by(
        id_reparacion=id,
        id_producto=id_producto
    ).first()

    try:
        if detalle:
            detalle.cantidad += cantidad
            detalle.subtotal = detalle.cantidad * detalle.precio_unitario
        else:
            detalle = DetalleReparacion(
                id_reparacion=id,
                id_producto=id_producto,
                cantidad=cantidad,
                precio_unitario=producto.precio_venta,
                subtotal=producto.precio_venta * cantidad,
                nombre_producto=producto.nombre,
                es_servicio=producto.es_servicio
            )
            db.session.add(detalle)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Item agregado',
            'detalle': {
                'id': detalle.id_detalle,
                'nombre': detalle.nombre_producto,
                'cantidad': detalle.cantidad,
                'precio': float(detalle.precio_unitario),
                'subtotal': float(detalle.subtotal),
                'es_servicio': detalle.es_servicio,
                'incluye_costo_final': bool(getattr(detalle, 'incluye_costo_final', False)),
            },
            'costo_final': float(reparacion.costo_final_calculado or 0)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@reparaciones_bp.route('/<int:id>/items/eliminar/<int:id_detalle>', methods=['POST'])
@login_required
def eliminar_item(id, id_detalle):
    if not current_user.tiene_permiso('editar_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'No tienes permisos para editar reparaciones', 'modo_demo': False}), 403
    reparacion = _get_reparacion_or_404_safe(id)
    bloqueo = _motivo_bloqueo_financiero_reparacion(reparacion)
    if bloqueo:
        return jsonify({'error': bloqueo}), 409
    detalle = _get_detalle_reparacion_or_404_safe(id_detalle)

    if detalle.id_reparacion != id:
        return jsonify({'error': 'El detalle no pertenece a esta reparación'}), 400

    try:
        db.session.delete(detalle)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Item eliminado',
            'costo_final': float(reparacion.costo_final_calculado or 0)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@reparaciones_bp.route('/<int:id>/items/toggle_costo/<int:id_detalle>', methods=['POST'])
@login_required
def toggle_item_costo(id, id_detalle):
    if not current_user.tiene_permiso('editar_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'No tienes permisos para editar reparaciones', 'modo_demo': False}), 403
    reparacion = _get_reparacion_or_404_safe(id)
    bloqueo = _motivo_bloqueo_financiero_reparacion(reparacion)
    if bloqueo:
        return jsonify({'error': bloqueo}), 409
    detalle = _get_detalle_reparacion_or_404_safe(id_detalle)

    if detalle.id_reparacion != id:
        return jsonify({'error': 'El detalle no pertenece a esta reparación'}), 400

    try:
        if bool(getattr(detalle, 'incluye_costo_final', False)):
            detalle.incluye_costo_final = False
        else:
            detalle.incluye_costo_final = True

        db.session.commit()
        return jsonify({
            'success': True,
            'incluye_costo_final': bool(getattr(detalle, 'incluye_costo_final', False)),
            'costo_final': float(reparacion.costo_final_calculado or 0),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@reparaciones_bp.route('/<int:id>/generar_venta', methods=['POST'])
@login_required
def generar_venta(id):
    if not _puede_cobrar_reparacion_pos(current_user):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'No tienes permisos para cobrar reparaciones', 'modo_demo': False}), 403
    reparacion = _get_reparacion_or_404_safe(id)

    costo_final_base = float(reparacion.costo_final or 0)
    detalles_cobrables = reparacion.detalles.filter_by(incluye_costo_final=True).all()
    if not detalles_cobrables and costo_final_base <= 0:
        return jsonify({'error': 'No hay costo final ni items marcados para cobrar'}), 400
    if not _reparacion_tiene_saldo_pendiente(reparacion):
        return jsonify({'error': 'La reparación no tiene saldo pendiente para cobrar'}), 400

    errores_stock = []
    for det in detalles_cobrables:
        if not det.es_servicio:
            prod = db.session.get(Producto, det.id_producto)
            if prod.stock_actual < det.cantidad:
                errores_stock.append(f"Stock insuficiente para {prod.nombre} (Stock: {prod.stock_actual}, Req: {det.cantidad})")

    if errores_stock:
        return jsonify({'error': ' | '.join(errores_stock)}), 400

    pendiente_activo = _buscar_pendiente_cobro_reparacion_activa(id)
    if pendiente_activo:
        if (
            current_user.es_admin()
            or current_user.tiene_permiso('ver_cola_cobro')
            or current_user.tiene_permiso('tomar_cola_cobro')
        ):
            return jsonify({
                'success': True,
                'redirect_url': url_for('ventas.pos', cola_id=pendiente_activo.id, rt=int(datetime.utcnow().timestamp() * 1000))
            })
        return jsonify({'error': f'La reparación ya fue enviada a caja como pendiente #{pendiente_activo.id}'}), 400

    modo_cobro_exclusivo_cajero = (
        Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
        and Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
    )
    if (
        modo_cobro_exclusivo_cajero
        and not current_user.es_admin()
        and not current_user.tiene_permiso('tomar_cola_cobro')
    ):
        return jsonify({'error': 'Debe enviar la reparación a caja para que un cajero complete el cobro'}), 403

    from app.models import SesionCaja

    sesion_activa = SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()
    if not sesion_activa:
        return jsonify({'error': 'No tienes una caja abierta para cobrar'}), 400

    return jsonify({
        'success': True,
        'redirect_url': url_for('ventas.pos', reparacion_id=id, rt=int(datetime.utcnow().timestamp() * 1000))
    })


@reparaciones_bp.route('/<int:id>/enviar_a_caja', methods=['POST'])
@login_required
def enviar_a_caja(id):
    if not Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False):
        return jsonify({'error': 'El flujo de envío a caja no está habilitado'}), 403

    if not current_user.es_admin() and not current_user.tiene_permiso('enviar_caja_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    reparacion = _get_reparacion_or_404_safe(id)
    if (reparacion.estado or '').strip().lower() == 'cancelado':
        return jsonify({'error': 'La reparación está cancelada y no puede enviarse a caja'}), 400

    cliente = reparacion.cliente
    if not cliente or not bool(getattr(cliente, 'activo', False)):
        return jsonify({'error': 'Cliente no encontrado o inactivo'}), 400

    venta_existente = (
        Venta.query
        .filter(Venta.id_reparacion == reparacion.id_reparacion, Venta.estado != 'anulada')
        .order_by(Venta.fecha_venta.desc())
        .first()
    )
    if venta_existente:
        return jsonify({'error': f'La reparación ya fue cobrada en la venta #{venta_existente.id_venta}'}), 400

    try:
        pendiente, creado = _obtener_o_crear_pendiente_cobro_reparacion(reparacion, current_user)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except IntegrityError:
        return jsonify({'error': 'No se pudo enviar la reparación a caja'}), 500

    if creado:
        metadata = pendiente.get_metadata()
        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='enviar_a_caja',
                    modulo='reparaciones',
                    descripcion=f'Envió reparación #{reparacion.id_reparacion} a caja como pendiente #{pendiente.id}',
                    referencia_tipo='cola_cobro',
                    referencia_id=pendiente.id,
                    datos_nuevos={
                        'tipo_origen': 'reparacion',
                        'reparacion_id': int(reparacion.id_reparacion),
                        'cliente_id': int(reparacion.cliente_id),
                        'id_usuario_vendedor': int(metadata.get('id_usuario_vendedor') or current_user.id_usuario),
                        'monto_total': float(pendiente.monto_total or 0),
                    },
                    commit=False
                )
            db.session.commit()
        except Exception:
            db.session.rollback()

    return jsonify({
        'success': True,
        'cola_id': int(pendiente.id),
        'mensaje': (
            f'Reparación enviada a caja como pendiente #{pendiente.id}'
            if creado
            else f'La reparación ya estaba enviada a caja como pendiente #{pendiente.id}'
        )
    })
