from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import MovimientoCaja, SesionCaja
from app.routes.caja import caja_bp
from app.utils.auditoria_utils import registrar_auditoria


@caja_bp.route('/movimiento', methods=['GET', 'POST'])
@login_required
def registrar_movimiento():
    """Registrar ingreso/egreso de caja"""
    if not current_user.tiene_permiso('movimiento_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para registrar movimientos de caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()

    if not sesion:
        flash('Debe tener una caja abierta.', 'warning')
        return redirect(url_for('caja.abrir'))

    if request.method == 'POST':
        tipo = request.form.get('tipo')
        monto = request.form.get('monto', 0, type=float)
        motivo = request.form.get('motivo', '').strip()

        if tipo not in ['ingreso', 'egreso']:
            flash('Tipo de movimiento inválido.', 'danger')
            return render_template('caja/movimiento.html', sesion=sesion)

        if monto <= 0:
            flash('El monto debe ser mayor a cero.', 'warning')
            return render_template('caja/movimiento.html', sesion=sesion)

        if not motivo:
            flash('Debe indicar el motivo del movimiento.', 'warning')
            return render_template('caja/movimiento.html', sesion=sesion)

        movimiento = MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=current_user.id_usuario,
            tipo=tipo,
            monto=monto,
            motivo=motivo
        )

        db.session.add(movimiento)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='movimiento_caja',
                    modulo='caja',
                    descripcion=f'Movimiento de caja ({tipo}) en sesión #{sesion.id_sesion}',
                    referencia_tipo='movimiento_caja',
                    referencia_id=movimiento.id_movimiento_caja,
                    datos_nuevos={
                        'id_sesion_caja': sesion.id_sesion,
                        'tipo': tipo,
                        'monto': float(monto or 0),
                        'motivo': motivo,
                    },
                    commit=False
                )
        except Exception:
            pass
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error guardando movimiento de caja')
            flash('No se pudo guardar el movimiento. Revise el log del servidor.', 'danger')
            return render_template('caja/movimiento.html', sesion=sesion)

        tipo_texto = 'Ingreso' if tipo == 'ingreso' else 'Egreso'
        flash(f'{tipo_texto} de ₲ {monto:,.0f} registrado.', 'success')
        return redirect(url_for('caja.estado'))

    return render_template('caja/movimiento.html', sesion=sesion)

