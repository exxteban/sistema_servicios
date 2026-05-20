from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import MetodoPago, SesionCaja
from app.utils.auditoria_utils import registrar_auditoria
from pedidos.models import PedidoCliente
from pedidos.services.caja_queue_service import (
    construir_contexto_cobro_pedido_caja,
    obtener_o_crear_pendiente_cobro_pedido,
    registrar_cobro_pedido_desde_cola,
)
from pedidos.services.pago_service import TIPOS_PAGO_PEDIDO


pedidos_caja_bp = Blueprint(
    'pedidos_caja',
    __name__,
    template_folder='templates',
)


def _puede_editar_pedidos() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('editar_cliente') or current_user.tiene_permiso('crear_cliente')


def _puede_tomar_cola() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('tomar_cola_cobro')


def _sesion_caja_activa():
    return SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()


def _metodo_pago_es_credito_tienda(metodo: MetodoPago | None) -> bool:
    nombre = ' '.join((getattr(metodo, 'nombre', '') or '').strip().lower().split())
    return nombre in {'credito tienda', 'venta a credito'}


def _metodos_pago_disponibles():
    metodos = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc()).all()
    return [metodo for metodo in metodos if not _metodo_pago_es_credito_tienda(metodo)]


def _redirigir_despues_de_enviar_a_caja(pendiente, id_pedido: int):
    if _puede_tomar_cola():
        sesion_activa = _sesion_caja_activa()
        if sesion_activa is not None:
            return redirect(url_for('pedidos_caja.pos_cobro_cola', cola_id=int(pendiente.id)))
        return redirect(url_for('caja.abrir'))
    if current_user.es_admin() or current_user.tiene_permiso('ver_cola_cobro') or current_user.tiene_permiso('ver_caja'):
        return redirect(url_for('caja.estado'))
    return redirect(url_for('pedidos.detalle', id_pedido=int(id_pedido)))


def _redireccion_si_item_cola_no_cobrable(item):
    estado = (getattr(item, 'estado', '') or '').strip().lower()
    if estado == 'cobrado':
        flash('Este pendiente ya fue cobrado.', 'warning')
        return redirect(url_for('caja.estado'))
    if estado == 'cancelado':
        flash('Este pendiente fue cancelado.', 'warning')
        return redirect(url_for('caja.estado'))
    if estado not in ('pendiente', 'en_proceso'):
        flash('Este pendiente ya no esta disponible.', 'warning')
        return redirect(url_for('caja.estado'))
    return None


def _obtener_item_cola_en_proceso_html(cola_id: int):
    from app.models import ColaCobro
    from app.routes.caja.api import _asegurar_en_proceso

    item = db.session.get(ColaCobro, int(cola_id))
    if item is None:
        return None, redirect(url_for('caja.estado'))

    redireccion_estado = _redireccion_si_item_cola_no_cobrable(item)
    if redireccion_estado:
        return None, redireccion_estado

    item, error, _status = _asegurar_en_proceso(int(cola_id), commit=True)
    if error:
        flash((error.get('error') or '').strip() or 'No se pudo tomar el pendiente.', 'warning')
        return None, redirect(url_for('caja.estado'))
    return item, None


@pedidos_caja_bp.route('/<int:id_pedido>/enviar-a-caja', methods=['POST'])
@login_required
def enviar_a_caja_html(id_pedido: int):
    if not _puede_editar_pedidos():
        flash('No tienes permisos para enviar pedidos a caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    pedido = db.session.get(PedidoCliente, int(id_pedido))
    if pedido is None:
        flash('Pedido no encontrado.', 'danger')
        return redirect(url_for('pedidos.listar'))

    try:
        pendiente, creado = obtener_o_crear_pendiente_cobro_pedido(
            pedido,
            id_usuario_origen=int(current_user.id_usuario),
            datos_cobro={
                'tipo_pago': request.form.get('tipo_pago'),
                'id_metodo_pago': request.form.get('id_metodo_pago'),
                'monto': request.form.get('monto'),
                'referencia': request.form.get('referencia'),
                'observaciones': request.form.get('observaciones'),
            },
        )
        registrar_auditoria(
            accion='enviar_cobro_pedido_a_caja',
            modulo='pedidos',
            descripcion=f'Envio pedido {pedido.numero_pedido_display} a caja',
            referencia_tipo='cola_cobro',
            referencia_id=int(pendiente.id),
            datos_nuevos={
                'id_pedido': int(pedido.id_pedido),
                'id_cliente': int(pedido.id_cliente),
                'estado': pendiente.estado,
                'monto_total': float(pendiente.monto_total or 0),
            },
            commit=False,
        )
        db.session.commit()
        mensaje = (
            f'Pedido enviado a caja como pendiente #{pendiente.id}.'
            if creado else f'El pedido ya estaba en caja como pendiente #{pendiente.id}.'
        )
        flash(mensaje, 'success')
        return _redirigir_despues_de_enviar_a_caja(pendiente, int(id_pedido))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo enviar el pedido a caja.', 'danger')

    return redirect(url_for('pedidos.detalle', id_pedido=int(id_pedido)))


@pedidos_caja_bp.route('/cola-cobro/<int:cola_id>/pos')
@login_required
def pos_cobro_cola(cola_id: int):
    if not _puede_tomar_cola():
        flash('No tienes permisos para cobrar pendientes enviados a caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion_activa = _sesion_caja_activa()
    if sesion_activa is None:
        flash('Debes abrir caja para cobrar pendientes.', 'warning')
        return redirect(url_for('caja.abrir'))

    item, redireccion = _obtener_item_cola_en_proceso_html(int(cola_id))
    if redireccion:
        return redireccion

    try:
        contexto = construir_contexto_cobro_pedido_caja(item)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
        return redirect(url_for('caja.estado'))
    return render_template(
        'pedidos/cobro_pos.html',
        contexto=contexto,
        metodos_pago=_metodos_pago_disponibles(),
        tipos_pago=TIPOS_PAGO_PEDIDO,
        sesion_activa=sesion_activa,
    )


@pedidos_caja_bp.route('/cola-cobro/<int:cola_id>/cobrar', methods=['POST'])
@login_required
def cobrar_cola_pedido_html(cola_id: int):
    if not _puede_tomar_cola():
        flash('No tienes permisos para cobrar pendientes enviados a caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion_activa = _sesion_caja_activa()
    if sesion_activa is None:
        flash('Debes abrir caja para cobrar pendientes.', 'warning')
        return redirect(url_for('caja.abrir'))

    item, redireccion = _obtener_item_cola_en_proceso_html(int(cola_id))
    if redireccion:
        return redireccion

    try:
        estado_anterior = item.estado
        resultado = registrar_cobro_pedido_desde_cola(
            item,
            id_usuario=int(current_user.id_usuario),
            id_metodo_pago=int(request.form.get('id_metodo_pago')),
            monto=request.form.get('monto'),
            tipo_pago=request.form.get('tipo_pago'),
            referencia=(request.form.get('referencia') or '').strip(),
            observaciones=(request.form.get('observaciones') or '').strip(),
            sesion=sesion_activa,
        )
        pedido = resultado['pedido']
        pago = resultado['pago']
        movimiento = resultado['movimiento_caja']

        registrar_auditoria(
            accion='registrar_cobro_pedido',
            modulo='pedidos',
            descripcion=f'Registro cobro del pedido {pedido.numero_pedido_display} desde caja',
            referencia_tipo='pedido_cliente',
            referencia_id=int(pedido.id_pedido),
            datos_nuevos={
                'id_pago_pedido': int(pago.id_pago_pedido),
                'monto': float(pago.monto or 0),
                'tipo_pago': pago.tipo_pago,
                'estado_pedido': pedido.estado,
                'saldo_pendiente': float(pedido.saldo_pendiente or 0),
                'id_movimiento_caja': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
            },
            commit=False,
        )
        registrar_auditoria(
            accion='cobrar_pendiente_pedido_caja',
            modulo='caja',
            descripcion=f'Cobro pendiente de pedido #{item.id}',
            referencia_tipo='cola_cobro',
            referencia_id=int(item.id),
            datos_anteriores={'estado': estado_anterior},
            datos_nuevos={
                'estado': item.estado,
                'id_pedido': int(pedido.id_pedido),
                'id_pago_pedido': int(pago.id_pago_pedido),
            },
            commit=False,
        )
        db.session.commit()
        flash(
            f'Cobro registrado correctamente. Saldo pendiente: Gs. {float(pedido.saldo_pendiente or 0):,.0f}'.replace(',', '.'),
            'success',
        )
        return render_template(
            'pedidos/cobro_confirmado_imprimir.html',
            ticket_url=url_for(
                'pedidos.ticket_pedido',
                id_pedido=int(pedido.id_pedido),
                id_pago_pedido=int(pago.id_pago_pedido),
            ),
            destino=url_for('pedidos.detalle', id_pedido=int(pedido.id_pedido)),
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo registrar el cobro del pedido.', 'danger')

    return redirect(url_for('pedidos_caja.pos_cobro_cola', cola_id=int(cola_id)))
