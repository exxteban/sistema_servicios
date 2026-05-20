from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.reparacion_seguimiento import ReparacionHistorialEstado
from app.services.reparaciones_tecnicos import (
    tomar_reparacion,
    usuario_es_tecnico,
    usuarios_asignables_reparacion_activos,
)

from .base import _get_reparacion_or_404_safe, reparaciones_bp


@reparaciones_bp.route('/<int:id>/tecnico', methods=['POST'])
@login_required
def asignar_tecnico(id):
    accion = (request.form.get('accion') or 'asignar').strip().lower()
    puede_asignar = current_user.es_admin() or current_user.tiene_permiso('editar_reparacion')
    puede_tomar = usuario_es_tecnico(current_user)

    if accion == 'tomar':
        if not puede_tomar:
            if getattr(current_user, 'modo_demo', False):
                flash('Modo demo: esta acción está deshabilitada.', 'warning')
            else:
                flash('Solo un técnico puede tomar reparaciones.', 'danger')
            return redirect(url_for('reparaciones.detalle', id=id))
    elif not puede_asignar:
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para asignar técnicos.', 'danger')
        return redirect(url_for('reparaciones.detalle', id=id))

    reparacion = _get_reparacion_or_404_safe(id)
    tecnicos = {int(u.id_usuario): u for u in usuarios_asignables_reparacion_activos()}

    try:
        if accion == 'tomar':
            estado_anterior = reparacion.estado
            tomar_reparacion(reparacion, current_user)
            if estado_anterior != reparacion.estado:
                db.session.add(ReparacionHistorialEstado(
                    id_reparacion=reparacion.id_reparacion,
                    estado_anterior=estado_anterior,
                    estado_nuevo=reparacion.estado,
                    nota='Reparación tomada por técnico',
                ))
            flash('Reparación tomada correctamente.', 'success')
        else:
            tecnico_raw = (request.form.get('id_usuario_tecnico') or '').strip()
            tecnico_id = int(tecnico_raw) if tecnico_raw else None
            if not tecnico_id or tecnico_id not in tecnicos:
                raise ValueError('Selecciona un técnico válido.')
            reparacion.id_usuario_tecnico = tecnico_id
            flash('Técnico asignado correctamente.', 'success')

        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception as exc:
        db.session.rollback()
        flash(f'No se pudo actualizar el técnico: {exc}', 'danger')

    return redirect(url_for('reparaciones.detalle', id=id))
