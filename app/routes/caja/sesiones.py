from datetime import datetime
from math import isfinite

from flask import current_app, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Caja, ColaCobro, Configuracion, MovimientoCaja, SesionCaja
from app.routes.caja import caja_bp
from app.routes.caja.common import _enriquecer_motivos_movimientos
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.helpers import local_strftime


def _resumen_pendientes_para_cierre(pendientes):
    items = []
    for pendiente in pendientes[:5]:
        cliente = ((pendiente.cliente.nombre if pendiente.cliente else '') or '').strip() or 'Consumidor Final'
        tipo = 'Reparación' if pendiente.tipo_origen == 'reparacion' else 'Venta'
        if pendiente.tipo_origen == 'cobro_credito':
            tipo = 'Cobro crédito'
        elif pendiente.tipo_origen == 'pedido':
            tipo = 'Pedido'
        monto = f'₲ {float(pendiente.monto_total or 0):,.0f}'
        items.append(f'#{pendiente.id} {tipo} · {cliente} · {monto}')
    return ' | '.join(items)


def _cajas_disponibles_contexto():
    cajas = Caja.query.filter_by(activa=True).all()
    sesiones_abiertas = SesionCaja.query.filter_by(estado='abierta').all()
    return cajas, {s.id_caja: s for s in sesiones_abiertas}


def _render_abrir_caja():
    cajas, sesiones_abiertas_por_caja = _cajas_disponibles_contexto()
    return render_template('caja/abrir.html', cajas=cajas, sesiones_abiertas_por_caja=sesiones_abiertas_por_caja)


def _es_monto_no_negativo(valor):
    try:
        monto = float(valor)
    except (TypeError, ValueError):
        return False
    return isfinite(monto) and monto >= 0


def _construir_estado_caja_payload(sesion):
    from app.models import MetodoPago, PagoCuentaCobrar, PagoVenta, PedidoClientePago, Venta
    from sqlalchemy import func

    total_efectivo = float(sesion.calcular_total_efectivo() or 0)
    desglose_ventas_rows = (
        db.session.query(
            MetodoPago.id_metodo_pago,
            MetodoPago.nombre,
            func.sum(PagoVenta.monto).label('total'),
            func.count(PagoVenta.id_pago).label('cantidad'),
        )
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .join(MetodoPago, PagoVenta.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(
            Venta.id_sesion_caja == sesion.id_sesion,
            Venta.estado == 'completada',
        )
        .group_by(MetodoPago.id_metodo_pago, MetodoPago.nombre)
        .all()
    )
    desglose_pedidos_rows = (
        db.session.query(
            MetodoPago.id_metodo_pago,
            MetodoPago.nombre,
            func.sum(PedidoClientePago.monto).label('total'),
            func.count(PedidoClientePago.id_pago_pedido).label('cantidad'),
        )
        .join(MetodoPago, PedidoClientePago.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(
            PedidoClientePago.id_sesion_caja == sesion.id_sesion,
            PedidoClientePago.estado == 'activo',
        )
        .group_by(MetodoPago.id_metodo_pago, MetodoPago.nombre)
        .all()
    )
    desglose_por_metodo = {}
    for row in desglose_ventas_rows:
        key = int(getattr(row, 'id_metodo_pago', 0) or 0)
        desglose_por_metodo[key] = {
            'id_metodo_pago': key,
            'nombre': str(getattr(row, 'nombre', '') or ''),
            'total': float(getattr(row, 'total', 0) or 0),
            'cantidad': int(getattr(row, 'cantidad', 0) or 0),
        }
    for row in desglose_pedidos_rows:
        key = int(getattr(row, 'id_metodo_pago', 0) or 0)
        actual = desglose_por_metodo.setdefault(
            key,
            {
                'id_metodo_pago': key,
                'nombre': str(getattr(row, 'nombre', '') or ''),
                'total': 0.0,
                'cantidad': 0,
            },
        )
        actual['total'] += float(getattr(row, 'total', 0) or 0)
        actual['cantidad'] += int(getattr(row, 'cantidad', 0) or 0)
    desglose_pagos = list(desglose_por_metodo.values())
    desglose_pagos.sort(key=lambda item: (item['nombre'] or '').lower())

    total_cobrado_ventas_sesion = sum(float(d.total or 0) for d in desglose_ventas_rows) if desglose_ventas_rows else 0.0
    total_ventas_sesion = total_cobrado_ventas_sesion
    total_cobros_creditos_sesion = (
        db.session.query(func.sum(PagoCuentaCobrar.monto))
        .filter(
            PagoCuentaCobrar.id_sesion_caja == sesion.id_sesion,
            PagoCuentaCobrar.estado != 'anulado',
        )
        .scalar()
    )
    total_cobros_creditos_sesion = float(total_cobros_creditos_sesion or 0)
    total_cobros_pedidos_sesion = (
        db.session.query(func.sum(PedidoClientePago.monto))
        .filter(
            PedidoClientePago.id_sesion_caja == sesion.id_sesion,
            PedidoClientePago.estado == 'activo',
        )
        .scalar()
    )
    total_cobros_pedidos_sesion = float(total_cobros_pedidos_sesion or 0)
    total_ingresos_operativos_sesion = total_cobrado_ventas_sesion + total_cobros_creditos_sesion + total_cobros_pedidos_sesion
    total_egresos_sesion = (
        db.session.query(func.sum(MovimientoCaja.monto))
        .filter(
            MovimientoCaja.id_sesion_caja == sesion.id_sesion,
            MovimientoCaja.tipo == 'egreso',
            func.lower(func.coalesce(MovimientoCaja.referencia_tipo, '')) != 'anulacion_venta',
        )
        .scalar()
    )
    total_egresos_sesion = float(total_egresos_sesion or 0)
    total_neto_sesion = total_ingresos_operativos_sesion - total_egresos_sesion

    movimientos = sesion.movimientos.order_by(MovimientoCaja.fecha_movimiento.desc()).all()
    _enriquecer_motivos_movimientos(movimientos)

    return {
        'total_efectivo': total_efectivo,
        'desglose_pagos': desglose_pagos,
        'total_cobrado_ventas_sesion': total_cobrado_ventas_sesion,
        'total_cobros_creditos_sesion': total_cobros_creditos_sesion,
        'total_cobros_pedidos_sesion': total_cobros_pedidos_sesion,
        'total_ingresos_operativos_sesion': total_ingresos_operativos_sesion,
        'total_ventas_sesion': total_ventas_sesion,
        'total_egresos_sesion': total_egresos_sesion,
        'total_neto_sesion': total_neto_sesion,
        'movimientos': movimientos,
        'desglose_pagos_json': desglose_pagos,
        'movimientos_json': [
            {
                'fecha': local_strftime(mov.fecha_movimiento, '%d/%m/%Y %H:%M'),
                'tipo': str(mov.tipo or ''),
                'monto': float(mov.monto or 0),
                'motivo': str((mov.motivo_detallado or mov.motivo or '').strip()),
                'usuario': str((mov.usuario.username if mov.usuario else 'Sistema') or 'Sistema'),
            }
            for mov in movimientos
        ],
    }


@caja_bp.route('/')
@login_required
def estado():
    """Estado actual de la caja"""
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()

    if not sesion:
        return redirect(url_for('caja.abrir'))

    resumen = _construir_estado_caja_payload(sesion)
    total_efectivo = resumen['total_efectivo']
    desglose_pagos = resumen['desglose_pagos']
    total_cobrado_ventas_sesion = resumen['total_cobrado_ventas_sesion']
    total_cobros_creditos_sesion = resumen['total_cobros_creditos_sesion']
    total_cobros_pedidos_sesion = resumen['total_cobros_pedidos_sesion']
    total_ingresos_operativos_sesion = resumen['total_ingresos_operativos_sesion']
    total_ventas_sesion = resumen['total_ventas_sesion']
    total_egresos_sesion = resumen['total_egresos_sesion']
    total_neto_sesion = resumen['total_neto_sesion']
    movimientos = resumen['movimientos']
    caja_alerta_pendientes_activa = Configuracion.obtener_bool('caja_alerta_pendientes_activa', default=False)
    cola_tipo = request.args.get('cola_tipo', 'todas')
    cola_estado = request.args.get('cola_estado', 'todas')
    cola_scope = request.args.get('cola_scope', 'todas')

    cola_pendientes = []
    cola_totales = {
        'total': 0,
        'pendiente': 0,
        'en_proceso': 0,
        'venta': 0,
        'reparacion': 0,
        'cobro_credito': 0,
        'pedido': 0,
    }
    if current_user.tiene_permiso('ver_cola_cobro'):
        cola_base_query = ColaCobro.query.filter(ColaCobro.estado.in_(['pendiente', 'en_proceso']))
        cola_base = cola_base_query.all()
        cola_totales = {
            'total': len(cola_base),
            'pendiente': sum(1 for item in cola_base if item.estado == 'pendiente'),
            'en_proceso': sum(1 for item in cola_base if item.estado == 'en_proceso'),
            'venta': sum(1 for item in cola_base if item.tipo_origen == 'venta'),
            'reparacion': sum(1 for item in cola_base if item.tipo_origen == 'reparacion'),
            'cobro_credito': sum(1 for item in cola_base if item.tipo_origen == 'cobro_credito'),
            'pedido': sum(1 for item in cola_base if item.tipo_origen == 'pedido'),
        }

        cola_query = cola_base_query
        if cola_tipo in {'venta', 'reparacion', 'cobro_credito', 'pedido'}:
            cola_query = cola_query.filter(ColaCobro.tipo_origen == cola_tipo)
        else:
            cola_tipo = 'todas'

        if cola_estado in {'pendiente', 'en_proceso'}:
            cola_query = cola_query.filter(ColaCobro.estado == cola_estado)
        else:
            cola_estado = 'todas'

        if cola_scope == 'mias':
            cola_query = cola_query.filter(ColaCobro.id_usuario_destino == current_user.id_usuario)
        elif cola_scope == 'disponibles':
            cola_query = cola_query.filter(ColaCobro.id_usuario_destino.is_(None))
        else:
            cola_scope = 'todas'

        cola_pendientes = (
            cola_query
            .order_by(ColaCobro.fecha_envio.asc())
            .limit(50)
            .all()
        )

    return render_template(
        'caja/estado.html',
        sesion=sesion,
        total_efectivo=total_efectivo,
        movimientos=movimientos,
        desglose_pagos=desglose_pagos,
        total_cobrado_ventas_sesion=total_cobrado_ventas_sesion,
        total_cobros_creditos_sesion=total_cobros_creditos_sesion,
        total_cobros_pedidos_sesion=total_cobros_pedidos_sesion,
        total_ingresos_operativos_sesion=total_ingresos_operativos_sesion,
        total_ventas_sesion=total_ventas_sesion,
        total_egresos_sesion=total_egresos_sesion,
        total_neto_sesion=total_neto_sesion,
        cola_pendientes=cola_pendientes,
        cola_totales=cola_totales,
        cola_filtros={
            'tipo': cola_tipo,
            'estado': cola_estado,
            'scope': cola_scope,
        },
        caja_alerta_pendientes_activa=caja_alerta_pendientes_activa,
    )


@caja_bp.route('/api/estado/resumen')
@login_required
def estado_resumen():
    if not current_user.tiene_permiso('ver_caja'):
        return jsonify({'error': 'Sin permisos'}), 403

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()
    if not sesion:
        return jsonify({'error': 'No hay sesión abierta'}), 404

    resumen = _construir_estado_caja_payload(sesion)
    return jsonify({
        'success': True,
        'total_efectivo': resumen['total_efectivo'],
        'total_cobrado_ventas_sesion': resumen['total_cobrado_ventas_sesion'],
        'total_cobros_creditos_sesion': resumen['total_cobros_creditos_sesion'],
        'total_cobros_pedidos_sesion': resumen['total_cobros_pedidos_sesion'],
        'total_ingresos_operativos_sesion': resumen['total_ingresos_operativos_sesion'],
        'total_ventas_sesion': resumen['total_ventas_sesion'],
        'total_egresos_sesion': resumen['total_egresos_sesion'],
        'total_neto_sesion': resumen['total_neto_sesion'],
        'desglose_pagos': resumen['desglose_pagos_json'],
        'movimientos': resumen['movimientos_json'],
    })


@caja_bp.route('/abrir', methods=['GET', 'POST'])
@login_required
def abrir():
    """Abrir caja"""
    if not current_user.tiene_permiso('abrir_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para abrir caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion_existente = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()

    if sesion_existente:
        flash('Ya tiene una caja abierta.', 'info')
        return redirect(url_for('caja.estado'))

    if request.method == 'POST':
        id_caja = request.form.get('id_caja', type=int)
        monto_inicial = request.form.get('monto_inicial', 0, type=float)

        if not id_caja:
            flash('Debe seleccionar una caja.', 'warning')
            return _render_abrir_caja()

        caja = Caja.query.filter_by(id_caja=id_caja).first()
        if not caja or not bool(caja.activa):
            flash('La caja seleccionada no existe o está inactiva.', 'warning')
            return _render_abrir_caja()

        if not _es_monto_no_negativo(monto_inicial):
            flash('El monto inicial debe ser un número válido mayor o igual a cero.', 'warning')
            return _render_abrir_caja()

        caja_en_uso = SesionCaja.query.filter_by(
            id_caja=id_caja,
            estado='abierta'
        ).first()

        if caja_en_uso:
            usuario_caja = caja_en_uso.usuario
            username_caja = (getattr(usuario_caja, 'username', '') or '').strip().lower()
            usuario_caja_es_demo = bool(getattr(usuario_caja, 'modo_demo', False)) or username_caja in {'demo', 'demostracion', 'demostración'}

            if caja_en_uso.id_usuario != current_user.id_usuario and usuario_caja_es_demo:
                total_sistema = float(caja_en_uso.calcular_total_efectivo() or 0)
                caja_en_uso.monto_final_declarado = total_sistema
                caja_en_uso.monto_final_sistema = total_sistema
                caja_en_uso.diferencia = 0
                caja_en_uso.estado = 'cerrada'
                caja_en_uso.fecha_cierre = datetime.utcnow()
                caja_en_uso.id_usuario_cierre = current_user.id_usuario
                obs = (caja_en_uso.observaciones or '').strip()
                caja_en_uso.observaciones = (obs + '\n' if obs else '') + 'Cierre automático para liberar caja (demo)'
                flash('Se liberó una sesión demo previa para poder abrir la caja.', 'info')
            else:
                nombre_usuario = (usuario_caja.nombre_completo if usuario_caja else 'Usuario desconocido')
                username = (usuario_caja.username if usuario_caja else '')
                fecha = local_strftime(caja_en_uso.fecha_apertura) if caja_en_uso.fecha_apertura else ''
                quien = f'{nombre_usuario} ({username})' if username else nombre_usuario
                flash(f'Esta caja ya está siendo utilizada por {quien} desde {fecha}. Debe cerrarse primero por ese usuario.', 'danger')
                return _render_abrir_caja()

        sesion = SesionCaja(
            id_caja=id_caja,
            id_usuario=current_user.id_usuario,
            monto_inicial=monto_inicial
        )

        db.session.add(sesion)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='abrir_caja',
                    modulo='caja',
                    descripcion=f'Apertura de caja #{id_caja} (sesión #{sesion.id_sesion})',
                    referencia_tipo='sesion_caja',
                    referencia_id=sesion.id_sesion,
                    datos_nuevos={
                        'id_caja': id_caja,
                        'monto_inicial': float(monto_inicial or 0),
                    },
                    commit=False
                )
        except Exception:
            pass
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('La caja fue abierta por otro usuario hace un momento. Actualice el estado antes de volver a intentar.', 'warning')
            return redirect(url_for('caja.abrir'))

        flash('Caja abierta correctamente.', 'success')
        return redirect(url_for('caja.estado'))

    return _render_abrir_caja()


@caja_bp.route('/cerrar', methods=['GET', 'POST'])
@login_required
def cerrar():
    """Cerrar caja"""
    if not current_user.tiene_permiso('cerrar_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para cerrar caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()

    if not sesion:
        try:
            req_id = getattr(g, 'request_id', None)
            prefix = f'[{req_id}] ' if req_id else ''
            current_app.logger.info(f"{prefix}Caja cerrar: sin sesión abierta user_id={current_user.id_usuario}")
        except Exception:
            pass
        flash('No tiene ninguna caja abierta.', 'warning')
        return redirect(url_for('caja.abrir'))

    total_sistema = sesion.calcular_total_efectivo()
    pendientes_en_proceso = (
        ColaCobro.query
        .filter(
            ColaCobro.estado == 'en_proceso',
            ColaCobro.id_usuario_destino == current_user.id_usuario
        )
        .order_by(ColaCobro.fecha_toma.asc(), ColaCobro.id.asc())
        .all()
    )
    if pendientes_en_proceso:
        pendientes_mostrados = _resumen_pendientes_para_cierre(pendientes_en_proceso)
        sufijo = '...' if len(pendientes_en_proceso) > 5 else ''
        flash(
            f'No puede cerrar la caja mientras tenga pendientes en proceso asignados. Revise y cobre o libere: {pendientes_mostrados}{sufijo}.',
            'warning'
        )
        return redirect(url_for('caja.estado', cola_estado='en_proceso', cola_scope='mias'))
    otras_sesiones_abiertas = (
        SesionCaja.query
        .filter(
            SesionCaja.estado == 'abierta',
            SesionCaja.id_sesion != sesion.id_sesion
        )
        .count()
    )
    if otras_sesiones_abiertas == 0:
        pendientes_bloqueantes = (
            ColaCobro.query
            .filter(ColaCobro.estado.in_(['pendiente', 'en_proceso']))
            .order_by(ColaCobro.fecha_envio.asc(), ColaCobro.id.asc())
            .all()
        )
        if pendientes_bloqueantes:
            pendientes_mostrados = _resumen_pendientes_para_cierre(pendientes_bloqueantes)
            sufijo = '...' if len(pendientes_bloqueantes) > 5 else ''
            estados_bloqueantes = {item.estado for item in pendientes_bloqueantes}
            cola_estado = 'todas' if len(estados_bloqueantes) > 1 else next(iter(estados_bloqueantes), 'todas')
            flash(
                f'No puede cerrar la última caja abierta mientras existan cobros pendientes o en proceso. Revise y resuelva: {pendientes_mostrados}{sufijo}.',
                'warning'
            )
            return redirect(url_for('caja.estado', cola_estado=cola_estado))
    try:
        req_id = getattr(g, 'request_id', None)
        prefix = f'[{req_id}] ' if req_id else ''
        current_app.logger.info(
            f"{prefix}Caja cerrar: inicio method={request.method} sesion_id={sesion.id_sesion} user_id={current_user.id_usuario} total_sistema={float(total_sistema or 0)}"
        )
    except Exception:
        pass

    if request.method == 'POST':
        monto_declarado = request.form.get('monto_declarado', 0, type=float)
        observaciones = request.form.get('observaciones', '')
        if not _es_monto_no_negativo(monto_declarado):
            flash('El monto declarado debe ser un número válido mayor o igual a cero.', 'warning')
            return redirect(url_for('caja.cerrar'))
        try:
            req_id = getattr(g, 'request_id', None)
            prefix = f'[{req_id}] ' if req_id else ''
            current_app.logger.info(
                f"{prefix}Caja cerrar: POST sesion_id={sesion.id_sesion} declarado={float(monto_declarado or 0)} obs_len={len(observaciones or '')}"
            )
        except Exception:
            pass

        datos_anteriores = {
            'monto_final_declarado': float(sesion.monto_final_declarado or 0) if sesion.monto_final_declarado is not None else None,
            'monto_final_sistema': float(sesion.monto_final_sistema or 0) if sesion.monto_final_sistema is not None else None,
            'diferencia': float(sesion.diferencia or 0) if sesion.diferencia is not None else None,
            'estado': sesion.estado,
            'fecha_cierre': sesion.fecha_cierre.isoformat() if sesion.fecha_cierre else None,
            'id_usuario_cierre': sesion.id_usuario_cierre,
            'observaciones': sesion.observaciones,
        }

        sesion.monto_final_declarado = monto_declarado
        sesion.monto_final_sistema = total_sistema
        sesion.diferencia = monto_declarado - total_sistema
        sesion.fecha_cierre = datetime.utcnow()
        sesion.estado = 'cerrada'
        sesion.id_usuario_cierre = current_user.id_usuario
        sesion.observaciones = observaciones

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='cerrar_caja',
                    modulo='caja',
                    descripcion=f'Cierre de sesión de caja #{sesion.id_sesion}',
                    referencia_tipo='sesion_caja',
                    referencia_id=sesion.id_sesion,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos={
                        'monto_final_declarado': float(monto_declarado or 0),
                        'monto_final_sistema': float(total_sistema or 0),
                        'diferencia': float((monto_declarado - total_sistema) or 0),
                        'estado': 'cerrada',
                        'fecha_cierre': sesion.fecha_cierre.isoformat() if sesion.fecha_cierre else None,
                        'id_usuario_cierre': current_user.id_usuario,
                        'observaciones': observaciones,
                    },
                    commit=False
                )
        except Exception:
            pass
        db.session.commit()
        try:
            req_id = getattr(g, 'request_id', None)
            prefix = f'[{req_id}] ' if req_id else ''
            current_app.logger.info(
                f"{prefix}Caja cerrar: commit sesion_id={sesion.id_sesion} estado={sesion.estado} diferencia={float(sesion.diferencia or 0)} redirect_cierre_id={sesion.id_sesion}"
            )
        except Exception:
            pass

        if sesion.diferencia != 0:
            if sesion.diferencia > 0:
                flash(f'Caja cerrada con sobrante de ₲ {sesion.diferencia:,.0f}', 'warning')
            else:
                flash(f'Caja cerrada con faltante de ₲ {abs(sesion.diferencia):,.0f}', 'danger')
        else:
            flash('Caja cerrada correctamente. Cuadre perfecto.', 'success')

        return redirect(url_for('main.dashboard', cierre_id=sesion.id_sesion))

    return render_template(
        'caja/cerrar.html',
        sesion=sesion,
        total_sistema=total_sistema
    )
