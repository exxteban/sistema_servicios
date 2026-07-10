from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Configuracion, Reparacion, Venta
from app.models.reparacion_seguimiento import ReparacionHistorialEstado
from app.services.reparaciones_tecnicos import (
    aplicar_hitos_tecnicos,
    usuario_es_tecnico,
    usuarios_asignables_reparacion_activos,
)
from app.utils.seguimiento_utils import descifrar_token

from .base import (
    CLAVE_CAJA_EXIGIR_CAJERO,
    CLAVE_CAJA_FLUJO_ENVIADO,
    CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO,
    MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT,
    _buscar_pendiente_cobro_reparacion_activa,
    _get_reparacion_or_404_safe,
    _puede_cambiar_estado_reparacion,
    _reparacion_tiene_saldo_pendiente,
    _transicion_estado_reparacion_permitida,
    reparaciones_bp,
)


@reparaciones_bp.route('/<int:id>')
@login_required
def detalle(id):
    if not current_user.tiene_permiso('ver_reparaciones'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    reparacion = _get_reparacion_or_404_safe(id)
    venta_asociada = (
        Venta.query
        .filter(Venta.id_reparacion == reparacion.id_reparacion, Venta.estado != 'anulada')
        .order_by(Venta.fecha_venta.desc())
        .first()
    )

    caja_flujo_enviado_activo = Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
    caja_exigir_cajero_para_cobro = Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
    modo_cobro_exclusivo_cajero = caja_flujo_enviado_activo and caja_exigir_cajero_para_cobro
    puede_enviar_caja_reparacion = current_user.es_admin() or current_user.tiene_permiso('enviar_caja_reparacion')
    puede_ver_cola_cobro = current_user.es_admin() or current_user.tiene_permiso('ver_cola_cobro')
    puede_tomar_cola_cobro = current_user.es_admin() or current_user.tiene_permiso('tomar_cola_cobro')
    puede_cambiar_estado_reparacion = _puede_cambiar_estado_reparacion(current_user)
    puede_cobrar_pos_directo = (not modo_cobro_exclusivo_cajero) or puede_tomar_cola_cobro
    mensaje_whatsapp_seguimiento = (
        (Configuracion.obtener(CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO, MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT) or '').strip()
        or MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT
    )
    pendiente_caja_activo = None
    tecnicos_activos = usuarios_asignables_reparacion_activos()
    puede_asignar_tecnico = current_user.es_admin() or current_user.tiene_permiso('editar_reparacion')
    puede_tomar_reparacion = usuario_es_tecnico(current_user)
    puede_ver_credenciales_equipo = (
        current_user.es_admin() or current_user.tiene_permiso('editar_reparacion')
    )
    password_patron_visible = None
    if puede_ver_credenciales_equipo:
        password_patron_visible = (
            descifrar_token(getattr(reparacion, 'password_patron_cifrado', None))
            or getattr(reparacion, 'password_patron', None)
        )

    ventas_posibles = []
    if not venta_asociada:
        pendiente_caja_activo = _buscar_pendiente_cobro_reparacion_activa(reparacion.id_reparacion)
        try:
            total_reparacion = float(reparacion.saldo_pendiente or 0)
        except Exception:
            total_reparacion = 0.0
        if total_reparacion <= 0:
            total_reparacion = 0.0

        if total_reparacion > 0:
            base = reparacion.fecha_entrega or reparacion.fecha_ingreso or datetime.utcnow()
            inicio = (base - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            fin = (base + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
            query = (
                Venta.query
                .filter(Venta.id_cliente == reparacion.cliente_id)
                .filter(Venta.fecha_venta >= inicio, Venta.fecha_venta <= fin)
                .order_by(Venta.fecha_venta.desc())
            )
            for v in query.limit(25).all():
                try:
                    total_v = float(v.total or 0)
                except Exception:
                    total_v = 0.0
                if abs(total_v - total_reparacion) < 0.01:
                    ventas_posibles.append(v)

    return render_template(
        'reparaciones/detalle.html',
        reparacion=reparacion,
        venta_asociada=venta_asociada,
        ventas_posibles=ventas_posibles,
        caja_flujo_enviado_activo=caja_flujo_enviado_activo,
        caja_exigir_cajero_para_cobro=caja_exigir_cajero_para_cobro,
        modo_cobro_exclusivo_cajero=modo_cobro_exclusivo_cajero,
        puede_enviar_caja_reparacion=puede_enviar_caja_reparacion,
        puede_ver_cola_cobro=puede_ver_cola_cobro,
        puede_tomar_cola_cobro=puede_tomar_cola_cobro,
        puede_cambiar_estado_reparacion=puede_cambiar_estado_reparacion,
        puede_cobrar_pos_directo=puede_cobrar_pos_directo,
        mensaje_whatsapp_seguimiento=mensaje_whatsapp_seguimiento,
        pendiente_caja_activo=pendiente_caja_activo,
        tecnicos_activos=tecnicos_activos,
        puede_asignar_tecnico=puede_asignar_tecnico,
        puede_tomar_reparacion=puede_tomar_reparacion,
        puede_ver_credenciales_equipo=puede_ver_credenciales_equipo,
        password_patron_visible=password_patron_visible,
    )


@reparaciones_bp.route('/<int:id>/vincular_venta', methods=['POST'])
@login_required
def vincular_venta(id):
    if not current_user.tiene_permiso('vincular_venta_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para vincular ventas a reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    reparacion = _get_reparacion_or_404_safe(id)
    id_venta = request.form.get('id_venta')
    try:
        id_venta = int(id_venta)
    except Exception:
        flash('Venta inválida', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    venta = db.session.get(Venta, id_venta)
    if not venta:
        flash('Venta no encontrada', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    if venta.id_reparacion and int(venta.id_reparacion) != int(reparacion.id_reparacion):
        flash('Esa venta ya está vinculada a otra reparación', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    if int(venta.id_cliente) != int(reparacion.cliente_id):
        flash('La venta no corresponde al mismo cliente de la reparación', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    existente = (
        Venta.query
        .filter(Venta.id_reparacion == reparacion.id_reparacion, Venta.estado != 'anulada')
        .first()
    )
    if existente and int(existente.id_venta) != int(venta.id_venta):
        flash(f'La reparación ya tiene una venta asociada (#{existente.id_venta})', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    try:
        venta.id_reparacion = reparacion.id_reparacion
        db.session.commit()
        flash(f'Venta #{venta.id_venta} vinculada a la reparación #{reparacion.id_reparacion}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al vincular: {str(e)}', 'danger')

    return redirect(url_for('reparaciones.detalle', id=id))


@reparaciones_bp.route('/<int:id>/estado', methods=['POST'])
@login_required
def cambiar_estado(id):
    if not _puede_cambiar_estado_reparacion(current_user):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para cambiar el estado de reparaciones.', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))
    reparacion = _get_reparacion_or_404_safe(id)
    nuevo_estado = (request.form.get('estado') or request.args.get('estado') or '').strip().lower()
    estados_validos = {
        'pendiente', 'diagnostico', 'espera_presupuesto', 'espera_repuesto', 'espera_cliente',
        'en_proceso', 'listo', 'no_se_pudo', 'entregado', 'cancelado', 'antiguos'
    }

    if nuevo_estado and nuevo_estado not in estados_validos:
        flash('Estado inválido', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    if nuevo_estado:
        if not _transicion_estado_reparacion_permitida(reparacion.estado, nuevo_estado):
            flash(
                f'No se puede cambiar una reparacion de {reparacion.estado_display} a {nuevo_estado.replace("_", " ")}.',
                'warning'
            )
            return redirect(url_for('reparaciones.detalle', id=id))
        if nuevo_estado == 'entregado':
            venta_asociada = (
                Venta.query
                .filter(Venta.id_reparacion == reparacion.id_reparacion, Venta.estado != 'anulada')
                .first()
            )
            if not venta_asociada and _reparacion_tiene_saldo_pendiente(reparacion):
                pendiente_caja_activo = _buscar_pendiente_cobro_reparacion_activa(reparacion.id_reparacion)
                if pendiente_caja_activo:
                    flash(
                        f'La reparación tiene un pendiente de caja activo (#{pendiente_caja_activo.id}). Debe cobrarse antes de marcarla como entregada.',
                        'warning'
                    )
                else:
                    modo_cobro_exclusivo_cajero = (
                        Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
                        and Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
                    )
                    if modo_cobro_exclusivo_cajero:
                        flash('Debe enviar la reparación a caja antes de marcarla como entregada.', 'warning')
                    else:
                        flash('Debe cobrar la reparación en POS antes de marcarla como entregada.', 'warning')
                return redirect(url_for('reparaciones.detalle', id=id))

        estado_anterior = reparacion.estado
        reparacion.estado = nuevo_estado
        aplicar_hitos_tecnicos(
            reparacion,
            estado_anterior=estado_anterior,
            nuevo_estado=nuevo_estado,
            usuario=current_user,
        )
        if estado_anterior == 'entregado' and nuevo_estado != 'entregado':
            reparacion.fecha_entrega = None
        if nuevo_estado == 'entregado' and not reparacion.fecha_entrega:
            reparacion.fecha_entrega = datetime.utcnow()

        if estado_anterior != nuevo_estado:
            historial = ReparacionHistorialEstado(
                id_reparacion=reparacion.id_reparacion,
                estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado
            )
            db.session.add(historial)

        db.session.commit()
        flash(f'Estado actualizado a {reparacion.estado_display}', 'success')

    return redirect(url_for('reparaciones.detalle', id=id))
