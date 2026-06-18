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


def marcar_pendiente_cancelado_por_cierre(pendiente, *, venta_id=None, usuario_id=None, motivo=None):
    metadata = pendiente.get_metadata()
    if venta_id:
        metadata['venta_id'] = int(venta_id)
    metadata['cerrado_por_usuario'] = int(usuario_id or current_user.id_usuario)
    metadata['regularizado_en_cierre_caja'] = True
    if motivo:
        metadata['regularizacion_motivo'] = motivo

    pendiente.estado = 'cancelado'
    pendiente.id_usuario_destino = int(usuario_id or current_user.id_usuario)
    pendiente.fecha_toma = pendiente.fecha_toma or datetime.utcnow()
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
        from app.models import Venta
        from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago

        pedido_id = metadata.get('gastronomia_pedido_id') or pendiente.id_origen
        pago = (
            GastronomiaPedidoPago.query
            .filter(GastronomiaPedidoPago.pedido_id == int(pedido_id or 0))
            .order_by(GastronomiaPedidoPago.id_pago.desc())
            .first()
        )
        if pago:
            venta_pago = None
            if pago.id_venta:
                venta_pago = Venta.query.filter(
                    Venta.id_venta == int(pago.id_venta),
                    Venta.estado.in_(('completada', 'anulada')),
                ).first()
            if venta_pago and venta_pago.estado == 'anulada':
                marcar_pendiente_cancelado_por_cierre(
                    pendiente,
                    venta_id=venta_pago.id_venta,
                    usuario_id=current_user.id_usuario,
                    motivo='venta_gastronomia_anulada',
                )
                return True
            marcar_pendiente_cobrado_por_cierre(
                pendiente,
                venta_id=pago.id_venta,
                usuario_id=current_user.id_usuario,
            )
            return True

        venta_id = metadata.get('venta_id')
        if venta_id not in (None, '', 0, '0'):
            venta = Venta.query.filter(
                Venta.id_venta == int(venta_id),
                Venta.estado.in_(('completada', 'anulada')),
            ).first()
            if venta and venta.estado == 'completada':
                marcar_pendiente_cobrado_por_cierre(
                    pendiente,
                    venta_id=venta.id_venta,
                    usuario_id=current_user.id_usuario,
                )
                return True
            if venta and venta.estado == 'anulada':
                marcar_pendiente_cancelado_por_cierre(
                    pendiente,
                    venta_id=venta.id_venta,
                    usuario_id=current_user.id_usuario,
                    motivo='venta_gastronomia_anulada',
                )
                return True

        pedido = GastronomiaPedido.query.filter(
            GastronomiaPedido.id_pedido == int(pedido_id or 0),
        ).first()
        if pedido and pedido.estado == 'cancelado':
            marcar_pendiente_cancelado_por_cierre(
                pendiente,
                usuario_id=current_user.id_usuario,
                motivo='pedido_gastronomia_cancelado',
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


def _pedido_gastronomia_sigue_activo(pendiente) -> bool:
    if (pendiente.tipo_origen or '').strip().lower() != 'gastronomia':
        return False
    from gastronomia.models import GastronomiaPedido

    metadata = pendiente.get_metadata()
    pedido_id = metadata.get('gastronomia_pedido_id') or pendiente.id_origen
    pedido = GastronomiaPedido.query.filter(
        GastronomiaPedido.id_pedido == int(pedido_id or 0),
    ).first()
    return bool(pedido and pedido.estado != 'cancelado')


def liberar_pendientes_en_proceso_huerfanos(pendientes) -> list:
    """Devuelve a 'pendiente' colas de gastronomía tomadas sin cobrar (checkout abandonado)."""
    restantes = []
    liberados = 0
    for pendiente in pendientes:
        if pendiente.estado == 'en_proceso' and _pedido_gastronomia_sigue_activo(pendiente):
            metadata = pendiente.get_metadata()
            metadata['liberado_por_cierre_caja'] = True
            pendiente.estado = 'pendiente'
            pendiente.id_usuario_destino = None
            pendiente.fecha_toma = None
            pendiente.set_metadata(metadata)
            liberados += 1
        else:
            restantes.append(pendiente)
    if liberados:
        db.session.commit()
        flash(f'Se liberaron {liberados} pendiente(s) de gastronomía que quedaron tomados sin cobrar.', 'info')
    return restantes


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
