from decimal import Decimal
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.models import Configuracion, CuentaPorCobrar, MetodoPago, PagoCuentaCobrar, SesionCaja
from app.utils.auditoria_utils import registrar_auditoria
from cobranzas import CLAVE_COBRANZAS_ACTIVO
from cobranzas.models import CuotaCreditoVenta
from cobranzas.services import (
    anular_cobro_credito,
    construir_contexto_cobro_credito_caja,
    obtener_o_crear_pendiente_cobro_credito,
    registrar_cobro_credito,
    registrar_cobro_credito_desde_cola,
)
from cobranzas.services.cobranza_service import _metodo_pago_es_credito_tienda


cobranzas_cobros_bp = Blueprint('cobranzas_cobros', __name__)


def _resolver_denegacion_api(permiso: str):
    if not Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False):
        return jsonify({'error': 'forbidden', 'mensaje': 'El modulo de cobranzas esta desactivado.'}), 403
    if current_user.es_admin() or current_user.tiene_permiso(permiso):
        return None
    return jsonify({'error': 'forbidden', 'mensaje': 'No tienes permisos para operar en cobranzas.'}), 403


def _resolver_denegacion_html(permiso: str):
    if not Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False):
        flash('El modulo de cobranzas esta desactivado.', 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.es_admin() or current_user.tiene_permiso(permiso):
        return None
    flash('No tienes permisos para operar en cobranzas.', 'danger')
    return redirect(url_for('main.dashboard'))


def _ejecutar_registro_cobro(cuenta: CuentaPorCobrar, payload: dict):
    resultado = registrar_cobro_credito(
        cuenta,
        id_usuario=int(current_user.id_usuario),
        id_metodo_pago=int(payload.get('id_metodo_pago')),
        monto=payload.get('monto'),
        referencia=(payload.get('referencia') or '').strip(),
        observaciones=(payload.get('observaciones') or '').strip(),
    )
    pago = resultado['pago']
    cuenta = resultado['cuenta']
    metodo = resultado['metodo']
    movimiento = resultado['movimiento_caja']
    saldo_anterior = Decimal(str(resultado['saldo_anterior'] or 0))
    saldo_nuevo = Decimal(str(resultado['saldo_nuevo'] or 0))
    detalle_aplicacion = pago.get_detalle_aplicacion() if hasattr(pago, 'get_detalle_aplicacion') else {}

    registrar_auditoria(
        accion='registrar_cobro_credito',
        modulo='cobranzas',
        descripcion=f'Registró cobro a cuenta #{cuenta.id_cuenta_cobrar}',
        referencia_tipo='cuenta_por_cobrar',
        referencia_id=int(cuenta.id_cuenta_cobrar),
        datos_nuevos={
            'id_pago_cuenta': int(pago.id_pago_cuenta),
            'id_venta': int(cuenta.id_venta),
            'id_cliente': int(cuenta.id_cliente),
            'monto': float(pago.monto or 0),
            'saldo_anterior': float(saldo_anterior),
            'saldo_nuevo': float(saldo_nuevo),
            'metodo_pago': metodo.nombre if metodo else None,
            'id_movimiento_caja': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
            'cliente_nombre': detalle_aplicacion.get('cliente_nombre'),
            'cuota_principal': detalle_aplicacion.get('cuota_principal'),
            'cuotas_aplicadas': detalle_aplicacion.get('cuotas_aplicadas'),
        },
        commit=False,
    )
    db.session.commit()
    return resultado


def _metodos_pago_disponibles():
    metodos_pago = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc()).all()
    return [metodo for metodo in metodos_pago if not _metodo_pago_es_credito_tienda(metodo)]


def _sesion_caja_activa():
    return SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()


def _normalizar_destino_local(raw_destino: str, *, fallback: str = '') -> str:
    destino = (raw_destino or '').strip()
    if not destino:
        return fallback
    parsed = urlparse(destino)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not parsed.path.startswith('/') or parsed.path.startswith('//'):
        return fallback
    return destino


def _construir_detalle_ticket_cobro(pago: PagoCuentaCobrar, cuenta: CuentaPorCobrar, detalle_aplicacion: dict) -> dict:
    venta = getattr(cuenta, 'venta', None)
    cuota_principal = detalle_aplicacion.get('cuota_principal') or {}
    cuotas_aplicadas = detalle_aplicacion.get('cuotas_aplicadas') or []
    plan = getattr(getattr(pago, 'cuota_principal', None), 'plan', None)
    tipo_comprobante = ((getattr(venta, 'tipo_comprobante', '') or '').strip().replace('_', ' ').title() if venta else '')
    numero_comprobante = ((getattr(venta, 'numero_comprobante', '') or '').strip() if venta else '')
    if not numero_comprobante and venta is not None and getattr(venta, 'id_venta', None):
        numero_comprobante = f'#{int(venta.id_venta)}'
    return {
        'comprobante_pago': f'COB-{int(pago.id_pago_cuenta):06d}',
        'tipo_comprobante_venta': tipo_comprobante or 'Ticket',
        'numero_comprobante_venta': numero_comprobante or '-',
        'cuota_principal_numero': cuota_principal.get('numero_cuota') or int(getattr(pago, 'numero_cuota_principal', 0) or 0) or None,
        'cuota_principal_monto': float(cuota_principal.get('monto_aplicado') or 0),
        'total_cuotas_plan': int(getattr(plan, 'cantidad_cuotas', 0) or 0) or None,
        'cantidad_cuotas_aplicadas': len(cuotas_aplicadas),
        'cuotas_aplicadas': cuotas_aplicadas,
    }


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
        abort(404)

    redireccion_estado = _redireccion_si_item_cola_no_cobrable(item)
    if redireccion_estado:
        return None, redireccion_estado

    item, error, _status = _asegurar_en_proceso(int(cola_id), commit=True)
    if error:
        flash((error.get('error') or '').strip() or 'No se pudo tomar el pendiente.', 'warning')
        return None, redirect(url_for('caja.estado'))
    return item, None


def _auditar_cola_cobro_credito(item, *, estado_anterior: str):
    metadata = item.get_metadata()
    registrar_auditoria(
        accion='cobrar_pendiente_credito_caja',
        modulo='caja',
        descripcion=f'CobrÃ³ pendiente de crÃ©dito #{item.id}',
        referencia_tipo='cola_cobro',
        referencia_id=int(item.id),
        datos_anteriores={'estado': estado_anterior},
        datos_nuevos={
            'estado': item.estado,
            'id_cuenta_cobrar': metadata.get('id_cuenta_cobrar'),
            'id_venta': metadata.get('id_venta'),
            'id_cliente': metadata.get('id_cliente'),
            'cliente_nombre': metadata.get('cliente_nombre'),
            'id_pago_cuenta': metadata.get('id_pago_cuenta'),
            'numero_cuota_principal': metadata.get('numero_cuota_principal'),
        },
        commit=False,
    )


@cobranzas_cobros_bp.route('/api/cuentas/<int:id_cuenta>/cobros', methods=['POST'])
@login_required
def registrar_cobro(id_cuenta: int):
    denegacion = _resolver_denegacion_api('registrar_cobro_credito')
    if denegacion:
        return denegacion

    payload = request.get_json(silent=True) or {}
    cuenta = db.session.get(CuentaPorCobrar, int(id_cuenta))
    if cuenta is None:
        return jsonify({'error': 'not_found', 'mensaje': 'Cuenta por cobrar no encontrada.'}), 404

    try:
        resultado = _ejecutar_registro_cobro(cuenta, payload)
        pago = resultado['pago']
        cuenta = resultado['cuenta']
        movimiento = resultado['movimiento_caja']
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    except Exception:
        db.session.rollback()
        raise

    return jsonify(
        {
            'success': True,
            'id_pago_cuenta': int(pago.id_pago_cuenta),
            'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
            'id_venta': int(cuenta.id_venta),
            'monto': float(pago.monto or 0),
            'saldo_pendiente': float(cuenta.saldo_pendiente or 0),
            'estado_cuenta': cuenta.estado,
            'tipo_venta': cuenta.venta.tipo_venta if cuenta.venta else None,
            'movimiento_caja_id': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
        }
    )


@cobranzas_cobros_bp.route('/cuentas/<int:id_cuenta>/cobrar', methods=['GET', 'POST'])
@login_required
def registrar_cobro_html(id_cuenta: int):
    denegacion = _resolver_denegacion_html('registrar_cobro_credito')
    if denegacion:
        return denegacion

    cuenta = db.session.get(CuentaPorCobrar, int(id_cuenta))
    if cuenta is None:
        flash('Cuenta por cobrar no encontrada.', 'danger')
        return redirect(url_for('cobranzas_cuentas.listar_cuentas'))

    if request.method == 'GET':
        return redirect(url_for('cobranzas_cuentas.detalle_cuenta', id_cuenta=int(id_cuenta)))

    payload = {
        'id_metodo_pago': request.form.get('id_metodo_pago'),
        'monto': request.form.get('monto'),
        'referencia': request.form.get('referencia', ''),
        'observaciones': request.form.get('observaciones', ''),
    }
    imprimir_ticket = (request.form.get('imprimir_ticket') or '').strip().lower() in {'1', 'true', 'on', 'yes'}
    destino = (request.form.get('next_url') or '').strip() or url_for('cobranzas_cuentas.detalle_cuenta', id_cuenta=int(id_cuenta))

    try:
        resultado = _ejecutar_registro_cobro(cuenta, payload)
        pago = resultado['pago']
        cuenta_actualizada = resultado['cuenta']
        flash(
            f'Cobro registrado correctamente. Saldo pendiente: ₲ {float(cuenta_actualizada.saldo_pendiente or 0):,.0f}'.replace(',', '.'),
            'success',
        )
        if imprimir_ticket:
            return render_template(
                'cobranzas/cobro_confirmado_imprimir.html',
                ticket_url=url_for('cobranzas_cobros.ticket_cobro_html', id_pago=int(pago.id_pago_cuenta)),
                destino=destino,
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        raise

    return redirect(destino)


@cobranzas_cobros_bp.route('/cobros/<int:id_pago>/ticket')
@login_required
def ticket_cobro_html(id_pago: int):
    denegacion = _resolver_denegacion_html('registrar_cobro_credito')
    if denegacion:
        return denegacion

    preview = request.args.get('preview') == '1'
    embedded = request.args.get('embedded') == '1'
    return_to = _normalizar_destino_local(request.args.get('return_to') or '', fallback='')
    pago = (
        PagoCuentaCobrar.query.options(
            joinedload(PagoCuentaCobrar.cuenta).joinedload(CuentaPorCobrar.cliente),
            joinedload(PagoCuentaCobrar.metodo),
            joinedload(PagoCuentaCobrar.usuario),
            joinedload(PagoCuentaCobrar.cuota_principal).joinedload(CuotaCreditoVenta.plan),
        )
        .filter(PagoCuentaCobrar.id_pago_cuenta == int(id_pago))
        .first()
    )
    if pago is None:
        abort(404)

    cuenta = pago.cuenta
    detalle_aplicacion = pago.get_detalle_aplicacion() if hasattr(pago, 'get_detalle_aplicacion') else {}
    ticket_detalle = _construir_detalle_ticket_cobro(pago, cuenta, detalle_aplicacion)
    empresa = {
        'nombre': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or '',
    }
    footer_text = Configuracion.obtener('ticket_footer_text', 'Gracias por su pago') or 'Gracias por su pago'
    paper_width_mm = Configuracion.obtener_int('ticket_paper_width_mm', 58)
    if paper_width_mm not in (48, 58, 80):
        paper_width_mm = 58

    monto_pago = float(pago.monto or 0)
    saldo_despues = float(getattr(cuenta, 'saldo_pendiente', 0) or 0)
    saldo_antes = saldo_despues + monto_pago

    return render_template(
        'cobranzas/ticket_cobro.html',
        pago=pago,
        cuenta=cuenta,
        empresa=empresa,
        detalle_aplicacion=detalle_aplicacion,
        ticket_detalle=ticket_detalle,
        saldo_antes=saldo_antes,
        saldo_despues=saldo_despues,
        preview=preview,
        embedded=embedded,
        return_to=return_to,
        moneda_simbolo='₲' if preview else 'Gs.',
        footer_text=footer_text,
        paper_width_mm=paper_width_mm,
    )


@cobranzas_cobros_bp.route('/api/cuentas/<int:id_cuenta>/enviar-a-caja', methods=['POST'])
@login_required
def enviar_cobro_a_caja(id_cuenta: int):
    denegacion = _resolver_denegacion_api('registrar_cobro_credito')
    if denegacion:
        return denegacion

    cuenta = db.session.get(CuentaPorCobrar, int(id_cuenta))
    if cuenta is None:
        return jsonify({'error': 'not_found', 'mensaje': 'Cuenta por cobrar no encontrada.'}), 404

    try:
        pendiente, creado = obtener_o_crear_pendiente_cobro_credito(
            cuenta,
            id_usuario_origen=int(current_user.id_usuario),
        )
        registrar_auditoria(
            accion='enviar_cobro_credito_a_caja',
            modulo='cobranzas',
            descripcion=f'EnviÃ³ cuenta #{cuenta.id_cuenta_cobrar} a caja',
            referencia_tipo='cola_cobro',
            referencia_id=int(pendiente.id),
            datos_nuevos={
                'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
                'id_cliente': int(cuenta.id_cliente),
                'id_venta': int(cuenta.id_venta),
                'estado': pendiente.estado,
                'monto_total': float(pendiente.monto_total or 0),
            },
            commit=False,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    except Exception:
        db.session.rollback()
        raise

    return jsonify({
        'success': True,
        'cola_id': int(pendiente.id),
        'creado': bool(creado),
        'mensaje': f'Cuenta #{cuenta.id_cuenta_cobrar} enviada a caja.',
    })


@cobranzas_cobros_bp.route('/cuentas/<int:id_cuenta>/enviar-a-caja', methods=['POST'])
@login_required
def enviar_cobro_a_caja_html(id_cuenta: int):
    denegacion = _resolver_denegacion_html('registrar_cobro_credito')
    if denegacion:
        return denegacion

    cuenta = db.session.get(CuentaPorCobrar, int(id_cuenta))
    if cuenta is None:
        flash('Cuenta por cobrar no encontrada.', 'danger')
        return redirect(url_for('cobranzas_cuentas.listar_cuentas'))

    try:
        pendiente, _ = obtener_o_crear_pendiente_cobro_credito(
            cuenta,
            id_usuario_origen=int(current_user.id_usuario),
        )
        registrar_auditoria(
            accion='enviar_cobro_credito_a_caja',
            modulo='cobranzas',
            descripcion=f'EnviÃ³ cuenta #{cuenta.id_cuenta_cobrar} a caja',
            referencia_tipo='cola_cobro',
            referencia_id=int(pendiente.id),
            datos_nuevos={
                'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
                'id_cliente': int(cuenta.id_cliente),
                'id_venta': int(cuenta.id_venta),
                'estado': pendiente.estado,
                'monto_total': float(pendiente.monto_total or 0),
            },
            commit=False,
        )
        db.session.commit()
        flash(f'Cuenta #{cuenta.id_cuenta_cobrar} enviada a caja correctamente.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        raise

    return redirect(url_for('cobranzas_cuentas.detalle_cuenta', id_cuenta=int(id_cuenta)))


@cobranzas_cobros_bp.route('/cola-cobro/<int:cola_id>/pos')
@login_required
def pos_cobro_cola(cola_id: int):
    denegacion = _resolver_denegacion_html('tomar_cola_cobro')
    if denegacion:
        return denegacion

    sesion_activa = _sesion_caja_activa()
    if sesion_activa is None:
        flash('Debes abrir caja para cobrar pendientes.', 'warning')
        return redirect(url_for('caja.abrir'))

    item, redireccion = _obtener_item_cola_en_proceso_html(int(cola_id))
    if redireccion:
        return redireccion

    contexto = construir_contexto_cobro_credito_caja(item)
    return render_template(
        'cobranzas/cobro_pos.html',
        contexto=contexto,
        metodos_pago=_metodos_pago_disponibles(),
        sesion_activa=sesion_activa,
    )


@cobranzas_cobros_bp.route('/cola-cobro/<int:cola_id>/cobrar', methods=['POST'])
@login_required
def cobrar_cola_credito_html(cola_id: int):
    denegacion = _resolver_denegacion_html('tomar_cola_cobro')
    if denegacion:
        return denegacion

    sesion_activa = _sesion_caja_activa()
    if sesion_activa is None:
        flash('Debes abrir caja para cobrar pendientes.', 'warning')
        return redirect(url_for('caja.abrir'))

    item, redireccion = _obtener_item_cola_en_proceso_html(int(cola_id))
    if redireccion:
        return redireccion

    payload = {
        'id_metodo_pago': request.form.get('id_metodo_pago'),
        'monto': request.form.get('monto'),
        'referencia': request.form.get('referencia', ''),
        'observaciones': request.form.get('observaciones', ''),
    }

    try:
        estado_anterior = item.estado
        resultado = registrar_cobro_credito_desde_cola(
            item,
            id_usuario=int(current_user.id_usuario),
            id_metodo_pago=int(payload.get('id_metodo_pago')),
            monto=payload.get('monto'),
            referencia=(payload.get('referencia') or '').strip(),
            observaciones=(payload.get('observaciones') or '').strip(),
            sesion=sesion_activa,
        )
        pago = resultado['pago']
        cuenta = resultado['cuenta']
        movimiento = resultado['movimiento_caja']
        metodo = resultado['metodo']
        saldo_anterior = Decimal(str(resultado['saldo_anterior'] or 0))
        saldo_nuevo = Decimal(str(resultado['saldo_nuevo'] or 0))
        detalle_aplicacion = pago.get_detalle_aplicacion() if hasattr(pago, 'get_detalle_aplicacion') else {}

        registrar_auditoria(
            accion='registrar_cobro_credito',
            modulo='cobranzas',
            descripcion=f'RegistrÃ³ cobro a cuenta #{cuenta.id_cuenta_cobrar} desde caja',
            referencia_tipo='cuenta_por_cobrar',
            referencia_id=int(cuenta.id_cuenta_cobrar),
            datos_nuevos={
                'id_pago_cuenta': int(pago.id_pago_cuenta),
                'id_venta': int(cuenta.id_venta),
                'id_cliente': int(cuenta.id_cliente),
                'monto': float(pago.monto or 0),
                'saldo_anterior': float(saldo_anterior),
                'saldo_nuevo': float(saldo_nuevo),
                'metodo_pago': metodo.nombre if metodo else None,
                'id_movimiento_caja': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
                'cliente_nombre': detalle_aplicacion.get('cliente_nombre'),
                'cuota_principal': detalle_aplicacion.get('cuota_principal'),
                'cuotas_aplicadas': detalle_aplicacion.get('cuotas_aplicadas'),
            },
            commit=False,
        )
        _auditar_cola_cobro_credito(item, estado_anterior=estado_anterior)
        db.session.commit()
        flash(
            f'Cobro registrado correctamente. Saldo pendiente: Gs. {float(cuenta.saldo_pendiente or 0):,.0f}'.replace(',', '.'),
            'success',
        )
        return redirect(url_for('cobranzas_cuentas.detalle_cuenta', id_cuenta=int(cuenta.id_cuenta_cobrar)))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        raise

    return redirect(url_for('cobranzas_cobros.pos_cobro_cola', cola_id=int(cola_id)))


@cobranzas_cobros_bp.route('/api/cobros/<int:id_pago>/anular', methods=['POST'])
@login_required
def anular_cobro(id_pago: int):
    denegacion = _resolver_denegacion_api('anular_cobro_credito')
    if denegacion:
        return denegacion

    payload = request.get_json(silent=True) or {}
    pago = db.session.get(PagoCuentaCobrar, int(id_pago))
    if pago is None:
        return jsonify({'error': 'not_found', 'mensaje': 'Cobro de credito no encontrado.'}), 404

    try:
        resultado = anular_cobro_credito(
            pago,
            id_usuario=int(current_user.id_usuario),
            motivo_anulacion=(payload.get('motivo_anulacion') or '').strip(),
        )
        cuenta = resultado['cuenta']
        movimiento = resultado['movimiento_caja']
        saldo_anterior = Decimal(str(resultado['saldo_anterior'] or 0))
        saldo_nuevo = Decimal(str(resultado['saldo_nuevo'] or 0))

        registrar_auditoria(
            accion='anular_cobro_credito',
            modulo='cobranzas',
            descripcion=f'Anuló cobro a cuenta #{cuenta.id_cuenta_cobrar}',
            referencia_tipo='pago_cuenta_cobrar',
            referencia_id=int(pago.id_pago_cuenta),
            datos_anteriores={
                'estado': 'activo',
                'saldo_anterior': float(saldo_anterior),
            },
            datos_nuevos={
                'estado': pago.estado,
                'motivo_anulacion': pago.motivo_anulacion,
                'saldo_nuevo': float(saldo_nuevo),
                'id_movimiento_reversa': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
            },
            commit=False,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    except Exception:
        db.session.rollback()
        raise

    return jsonify(
        {
            'success': True,
            'id_pago_cuenta': int(pago.id_pago_cuenta),
            'estado_pago': pago.estado,
            'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
            'id_venta': int(cuenta.id_venta),
            'saldo_pendiente': float(cuenta.saldo_pendiente or 0),
            'estado_cuenta': cuenta.estado,
            'tipo_venta': cuenta.venta.tipo_venta if cuenta.venta else None,
            'movimiento_caja_id': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
        }
    )
