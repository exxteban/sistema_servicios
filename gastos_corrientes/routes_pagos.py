from __future__ import annotations

import os
from datetime import date

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from gastos_corrientes.routes import gastos_corrientes_bp
from gastos_corrientes.services.comprobante_storage import (
    eliminar_comprobante_pago,
    extension_comprobante_permitida,
    guardar_comprobante_pago,
    resolver_ruta_comprobante,
)
from gastos_corrientes.services import (
    obtener_gasto_o_404,
    obtener_pago_o_404,
    parse_decimal,
    parse_fecha,
    parse_periodo,
    registrar_pago_gasto,
    revertir_pago_gasto,
)


def _project_root() -> str:
    return current_app.config.get('PROJECT_ROOT') or os.path.abspath(os.path.join(current_app.root_path, '..'))


def _denegacion_pago(permiso: str):
    if current_user.es_admin() or current_user.tiene_permiso(permiso):
        return None
    flash('No tienes permisos para operar pagos de gastos corrientes.', 'danger')
    return redirect(url_for('main.dashboard'))


@gastos_corrientes_bp.route('/pagos')
@login_required
def listar_pagos():
    denegacion = _denegacion_pago('ver_gastos_corrientes')
    if denegacion:
        return denegacion
    return redirect(url_for('gastos_corrientes.index', periodo=request.args.get('periodo')))


@gastos_corrientes_bp.route('/pago/<int:id_gasto_corriente>/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_pago(id_gasto_corriente: int):
    denegacion = _denegacion_pago('registrar_pago_gasto_corriente')
    if denegacion:
        return denegacion

    gasto = obtener_gasto_o_404(id_gasto_corriente)
    periodo_anio, periodo_mes, periodo = parse_periodo(request.values.get('periodo'))

    if request.method == 'POST':
        fecha_pago = parse_fecha(request.form.get('fecha_pago'))
        monto_pagado = parse_decimal(request.form.get('monto_pagado'))
        pagado_desde_caja = bool(request.form.get('pagado_desde_caja'))
        observacion = (request.form.get('observacion') or '').strip() or None
        numero_comprobante = (request.form.get('numero_comprobante') or '').strip() or None
        comprobante_adjunto = request.files.get('comprobante_adjunto')
        if fecha_pago is None:
            flash('La fecha de pago es obligatoria.', 'warning')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )
        if monto_pagado is None or monto_pagado <= 0:
            flash('El monto pagado debe ser mayor a cero.', 'warning')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )
        if (
            comprobante_adjunto
            and comprobante_adjunto.filename
            and not extension_comprobante_permitida(comprobante_adjunto.filename)
        ):
            flash('El adjunto debe ser PNG, JPG, JPEG, WEBP, GIF o PDF.', 'warning')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )

        storage_key_guardado = None
        try:
            pago, movimiento = registrar_pago_gasto(
                gasto,
                periodo_anio=periodo_anio,
                periodo_mes=periodo_mes,
                fecha_pago=fecha_pago,
                monto_pagado=monto_pagado,
                observacion=observacion,
                numero_comprobante=numero_comprobante,
                pagado_desde_caja=pagado_desde_caja,
            )
            if comprobante_adjunto and comprobante_adjunto.filename:
                comprobante_info = guardar_comprobante_pago(
                    comprobante_adjunto,
                    _project_root(),
                    fecha_referencia=fecha_pago,
                    pago_id=pago.id_pago_gasto_corriente,
                )
                storage_key_guardado = comprobante_info['storage_key']
                pago.comprobante_adjunto_path = comprobante_info['storage_key']
                pago.comprobante_adjunto_nombre = comprobante_info['nombre_original']
                pago.comprobante_adjunto_mime = comprobante_info['mime_type']
        except ValueError as exc:
            mensaje = str(exc)
            if mensaje in {'extension_invalida', 'ruta_invalida'}:
                mensaje = 'No se pudo guardar el adjunto del comprobante.'
            flash(mensaje, 'warning')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )
        except PermissionError:
            db.session.rollback()
            current_app.logger.exception('Sin permisos para guardar comprobante adjunto de gasto corriente')
            flash('No hay permisos para guardar el adjunto del comprobante.', 'danger')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )
        except OSError:
            db.session.rollback()
            current_app.logger.exception('No se pudo guardar el adjunto del comprobante de gasto corriente')
            flash('No se pudo guardar el adjunto del comprobante.', 'warning')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='registrar_pago_gasto_corriente',
                    modulo='gastos_corrientes',
                    descripcion=f'Registró pago del gasto "{gasto.nombre}"',
                    referencia_tipo='pago_gasto_corriente',
                    referencia_id=pago.id_pago_gasto_corriente,
                    datos_nuevos={
                        'periodo': pago.periodo,
                        'monto_pagado': str(pago.monto_pagado),
                        'pagado_desde_caja': bool(pago.pagado_desde_caja),
                        'id_movimiento_caja': pago.id_movimiento_caja,
                        'comprobante_adjunto': pago.comprobante_adjunto_nombre,
                    },
                    commit=False,
                )
                if movimiento:
                    registrar_auditoria(
                        accion='generar_movimiento_gasto_corriente',
                        modulo='gastos_corrientes',
                        descripcion=f'Generó egreso de caja para gasto "{gasto.nombre}"',
                        referencia_tipo='movimiento_caja',
                        referencia_id=movimiento.id_movimiento_caja,
                        datos_nuevos={
                            'tipo': movimiento.tipo,
                            'monto': str(movimiento.monto),
                            'referencia_tipo': movimiento.referencia_tipo,
                            'referencia_id': movimiento.referencia_id,
                        },
                        commit=False,
                    )
        except Exception:
            pass

        try:
            db.session.commit()
            flash('Pago registrado correctamente.', 'success')
            return redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=gasto.id_gasto_corriente))
        except Exception:
            db.session.rollback()
            if storage_key_guardado:
                try:
                    eliminar_comprobante_pago(storage_key_guardado, _project_root())
                except OSError:
                    current_app.logger.warning('No se pudo limpiar adjunto temporal de pago %s', pago.id_pago_gasto_corriente)
            current_app.logger.exception('Error al confirmar pago de gasto corriente')
            flash('Ocurrió un error al registrar el pago. Intente nuevamente.', 'danger')
            return render_template(
                'gastos_corrientes/pago_form.html',
                gasto=gasto,
                periodo=periodo,
                fecha_hoy=date.today().isoformat(),
            )

    return render_template(
        'gastos_corrientes/pago_form.html',
        gasto=gasto,
        periodo=periodo,
        fecha_hoy=date.today().isoformat(),
    )


@gastos_corrientes_bp.route('/pago/<int:id_pago>')
@login_required
def detalle_pago(id_pago: int):
    denegacion = _denegacion_pago('ver_gastos_corrientes')
    if denegacion:
        return denegacion

    pago = obtener_pago_o_404(id_pago)
    return redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=pago.id_gasto_corriente))


@gastos_corrientes_bp.route('/pago/<int:id_pago>/comprobante')
@login_required
def ver_comprobante_pago(id_pago: int):
    denegacion = _denegacion_pago('ver_gastos_corrientes')
    if denegacion:
        return denegacion

    pago = obtener_pago_o_404(id_pago)
    if not pago.tiene_comprobante_adjunto():
        abort(404)

    ruta = resolver_ruta_comprobante(pago.comprobante_adjunto_path, _project_root())
    if not ruta:
        abort(404)

    return send_file(
        ruta,
        mimetype=pago.comprobante_adjunto_mime or 'application/octet-stream',
        download_name=pago.comprobante_adjunto_nombre or 'comprobante',
        as_attachment=False,
    )


@gastos_corrientes_bp.route('/pago/<int:id_pago>/anular', methods=['POST'])
@login_required
def anular_pago(id_pago: int):
    denegacion = _denegacion_pago('anular_pago_gasto_corriente')
    if denegacion:
        return denegacion

    pago = obtener_pago_o_404(id_pago)
    motivo = (request.form.get('motivo_anulacion') or '').strip() or None
    try:
        movimiento_reversa = revertir_pago_gasto(pago, motivo_anulacion=motivo)
    except ValueError as exc:
        flash(str(exc), 'warning')
        return redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=pago.id_gasto_corriente))

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='anular_pago_gasto_corriente',
                modulo='gastos_corrientes',
                descripcion=f'Anuló pago del gasto "{pago.gasto_corriente.nombre}"',
                referencia_tipo='pago_gasto_corriente',
                referencia_id=pago.id_pago_gasto_corriente,
                datos_nuevos={
                    'estado': pago.estado,
                    'motivo_anulacion': pago.motivo_anulacion,
                    'id_movimiento_reversa': pago.id_movimiento_reversa,
                },
                commit=False,
            )
            if movimiento_reversa:
                registrar_auditoria(
                    accion='reversa_movimiento_gasto_corriente',
                    modulo='gastos_corrientes',
                    descripcion=f'Revirtió movimiento de caja de gasto "{pago.gasto_corriente.nombre}"',
                    referencia_tipo='movimiento_caja',
                    referencia_id=movimiento_reversa.id_movimiento_caja,
                    datos_nuevos={
                        'tipo': movimiento_reversa.tipo,
                        'monto': str(movimiento_reversa.monto),
                        'referencia_tipo': movimiento_reversa.referencia_tipo,
                        'referencia_id': movimiento_reversa.referencia_id,
                    },
                    commit=False,
                )
    except Exception:
        pass

    db.session.commit()
    flash('Pago anulado correctamente.', 'success')
    return redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=pago.id_gasto_corriente))
