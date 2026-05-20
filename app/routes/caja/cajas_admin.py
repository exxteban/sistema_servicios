from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Caja, SesionCaja
from app.routes.caja import caja_bp
from app.utils.auditoria_utils import registrar_auditoria


def _puede_gestionar_cajas():
    return current_user.es_admin() or current_user.tiene_permiso('gestionar_cajas')


def _guard_gestionar_cajas():
    """Retorna redirect si no tiene acceso, None si puede continuar."""
    if _puede_gestionar_cajas():
        return None
    if getattr(current_user, 'modo_demo', False):
        flash('Modo demo: esta acción está deshabilitada.', 'warning')
    else:
        flash('No tienes permisos para gestionar cajas.', 'danger')
    return redirect(url_for('main.dashboard'))


@caja_bp.route('/cajas')
@login_required
def cajas_listar():
    bloqueo = _guard_gestionar_cajas()
    if bloqueo:
        return bloqueo

    cajas = Caja.query.order_by(Caja.nombre.asc()).all()
    sesiones_abiertas = SesionCaja.query.filter_by(estado='abierta').all()
    sesiones_abiertas_por_caja = {s.id_caja: s for s in sesiones_abiertas}
    return render_template(
        'caja/cajas_listar.html',
        cajas=cajas,
        sesiones_abiertas_por_caja=sesiones_abiertas_por_caja
    )


@caja_bp.route('/cajas/nueva', methods=['GET', 'POST'])
@login_required
def cajas_nueva():
    bloqueo = _guard_gestionar_cajas()
    if bloqueo:
        return bloqueo

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        ubicacion = (request.form.get('ubicacion') or '').strip()
        activa = bool(request.form.get('activa'))

        if not nombre:
            flash('El nombre es obligatorio.', 'warning')
            return render_template('caja/cajas_form.html', caja=None)

        existente = Caja.query.filter(Caja.nombre == nombre).first()
        if existente:
            flash('Ya existe una caja con ese nombre.', 'danger')
            return render_template('caja/cajas_form.html', caja=None)

        caja = Caja(nombre=nombre, ubicacion=ubicacion or None, activa=activa)
        db.session.add(caja)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_caja',
                    modulo='caja',
                    descripcion=f'Creó caja "{caja.nombre}"',
                    referencia_tipo='caja',
                    referencia_id=caja.id_caja,
                    datos_nuevos={
                        'id_caja': caja.id_caja,
                        'nombre': caja.nombre,
                        'ubicacion': caja.ubicacion,
                        'activa': bool(caja.activa),
                    },
                    commit=False
                )
        except Exception:
            pass

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('No se pudo crear la caja (nombre duplicado).', 'danger')
            return render_template('caja/cajas_form.html', caja=None)

        flash('Caja creada correctamente.', 'success')
        return redirect(url_for('caja.cajas_listar'))

    return render_template('caja/cajas_form.html', caja=None)


@caja_bp.route('/cajas/<int:id_caja>/editar', methods=['GET', 'POST'])
@login_required
def cajas_editar(id_caja):
    bloqueo = _guard_gestionar_cajas()
    if bloqueo:
        return bloqueo

    caja = Caja.query.get_or_404(id_caja)

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        ubicacion = (request.form.get('ubicacion') or '').strip()
        activa = bool(request.form.get('activa'))

        if not nombre:
            flash('El nombre es obligatorio.', 'warning')
            return render_template('caja/cajas_form.html', caja=caja)

        existente = Caja.query.filter(Caja.nombre == nombre, Caja.id_caja != caja.id_caja).first()
        if existente:
            flash('Ya existe una caja con ese nombre.', 'danger')
            return render_template('caja/cajas_form.html', caja=caja)

        datos_anteriores = {
            'nombre': caja.nombre,
            'ubicacion': caja.ubicacion,
            'activa': bool(caja.activa),
        }

        if not activa and caja.sesion_activa():
            flash('No se puede desactivar una caja con sesión abierta.', 'danger')
            return render_template('caja/cajas_form.html', caja=caja)

        caja.nombre = nombre
        caja.ubicacion = ubicacion or None
        caja.activa = activa

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='editar_caja',
                    modulo='caja',
                    descripcion=f'Editó caja "{caja.nombre}"',
                    referencia_tipo='caja',
                    referencia_id=caja.id_caja,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos={
                        'nombre': caja.nombre,
                        'ubicacion': caja.ubicacion,
                        'activa': bool(caja.activa),
                    },
                    commit=False
                )
        except Exception:
            pass

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('No se pudo guardar (nombre duplicado).', 'danger')
            return render_template('caja/cajas_form.html', caja=caja)

        flash('Caja actualizada correctamente.', 'success')
        return redirect(url_for('caja.cajas_listar'))

    return render_template('caja/cajas_form.html', caja=caja)


@caja_bp.route('/cajas/<int:id_caja>/toggle', methods=['POST'])
@login_required
def cajas_toggle(id_caja):
    bloqueo = _guard_gestionar_cajas()
    if bloqueo:
        return bloqueo

    caja = Caja.query.get_or_404(id_caja)
    if caja.activa and caja.sesion_activa():
        flash('No se puede desactivar una caja con sesión abierta.', 'danger')
        return redirect(url_for('caja.cajas_listar'))

    datos_anteriores = {'activa': bool(caja.activa)}
    caja.activa = not bool(caja.activa)
    accion = 'activar_caja' if caja.activa else 'desactivar_caja'

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion=accion,
                modulo='caja',
                descripcion=f'Actualizó estado de caja "{caja.nombre}"',
                referencia_tipo='caja',
                referencia_id=caja.id_caja,
                datos_anteriores=datos_anteriores,
                datos_nuevos={'activa': bool(caja.activa)},
                commit=False
            )
    except Exception:
        pass

    db.session.commit()
    flash('Estado de caja actualizado.', 'success')
    return redirect(url_for('caja.cajas_listar'))
