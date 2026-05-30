from datetime import datetime

from flask import flash
from flask_login import current_user

from app import db


def marcar_pendiente_cobrado_por_cierre(pendiente, *, venta_id=None, usuario_id=None):
    metadata = pendiente.get_metadata()
    if venta_id:
        metadata['venta_id'] = int(venta_id)
    metadata['cerrado_por_usuario'] = int(usuario_id or current_user.id_usuario)
    metadata['regularizado_en_cierre_caja'] = True

    pendiente.estado = 'cobrado'
    pendiente.id_usuario_destino = int(usuario_id or current_user.id_usuario)
    pendiente.fecha_toma = pendiente.fecha_toma or datetime.utcnow()
    pendiente.fecha_cobro = pendiente.fecha_cobro or datetime.utcnow()
    if venta_id and pendiente.tipo_origen == 'venta':
        pendiente.id_origen = int(venta_id)
    pendiente.set_metadata(metadata)


def venta_completada_por_id(venta_id):
    if venta_id in (None, '', 0, '0'):
        return None
    from app.models import Venta

    return Venta.query.filter(
        Venta.id_venta == int(venta_id),
        Venta.estado == 'completada',
    ).first()


def resolver_pendiente_ya_cobrado(pendiente) -> bool:
    tipo = (pendiente.tipo_origen or '').strip().lower()
    metadata = pendiente.get_metadata()

    if tipo == 'gastronomia':
        from gastronomia.models import GastronomiaPedidoPago

        pedido_id = metadata.get('gastronomia_pedido_id') or pendiente.id_origen
        pago = (
            GastronomiaPedidoPago.query
            .filter(GastronomiaPedidoPago.pedido_id == int(pedido_id or 0))
            .order_by(GastronomiaPedidoPago.id_pago.desc())
            .first()
        )
        if pago:
            marcar_pendiente_cobrado_por_cierre(
                pendiente,
                venta_id=pago.id_venta,
                usuario_id=current_user.id_usuario,
            )
            return True
        return False

    if tipo == 'venta':
        from app.models import Venta

        venta = venta_completada_por_id(metadata.get('venta_id') or pendiente.id_origen)
        client_request_id = (metadata.get('client_request_id') or '').strip()
        if venta is None and client_request_id:
            venta = Venta.query.filter_by(client_request_id=client_request_id, estado='completada').first()
        if venta:
            marcar_pendiente_cobrado_por_cierre(
                pendiente,
                venta_id=venta.id_venta,
                usuario_id=current_user.id_usuario,
            )
            return True
        return False

    if tipo == 'reparacion':
        from app.models import Venta

        reparacion_id = metadata.get('reparacion_id') or pendiente.id_origen
        venta = Venta.query.filter(
            Venta.id_reparacion == int(reparacion_id or 0),
            Venta.estado == 'completada',
        ).first()
        if venta:
            marcar_pendiente_cobrado_por_cierre(
                pendiente,
                venta_id=venta.id_venta,
                usuario_id=current_user.id_usuario,
            )
            return True
        return False

    if tipo == 'pedido':
        from pedidos.models import PedidoClientePago

        pedido_id = metadata.get('id_pedido') or pendiente.id_origen
        pago = (
            PedidoClientePago.query
            .filter(
                PedidoClientePago.id_pedido == int(pedido_id or 0),
                PedidoClientePago.estado == 'activo',
            )
            .order_by(PedidoClientePago.id_pago_pedido.desc())
            .first()
        )
        if pago:
            marcar_pendiente_cobrado_por_cierre(
                pendiente,
                usuario_id=current_user.id_usuario,
            )
            return True
        return False

    return False


def regularizar_pendientes_ya_cobrados_para_cierre(pendientes) -> list:
    bloqueantes = []
    regularizados = 0
    for pendiente in pendientes:
        if resolver_pendiente_ya_cobrado(pendiente):
            regularizados += 1
        else:
            bloqueantes.append(pendiente)
    if regularizados:
        db.session.commit()
        flash(f'Se regularizaron {regularizados} pendiente(s) que ya estaban cobrados.', 'info')
    return bloqueantes
