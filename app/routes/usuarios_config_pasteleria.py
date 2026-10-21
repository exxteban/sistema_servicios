"""Encargos de pasteleria/cafeteria: flag y parametros por negocio (solo root)."""
from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app.routes.usuarios import usuarios_bp
from app.services.ia_backoffice.security import es_usuario_root
from gastronomia.services.pasteleria_config_service import guardar_config_encargos


@usuarios_bp.route('/modulos-sistema/pasteleria/<int:cliente_id>', methods=['POST'])
@login_required
def modulos_sistema_pasteleria(cliente_id):
    if not es_usuario_root(current_user):
        abort(403)
    try:
        config = guardar_config_encargos(
            cliente_id,
            request.form,
            usuario_id=getattr(current_user, 'id_usuario', None),
        )
    except ValueError as exc:
        flash(str(exc), 'warning')
        return redirect(url_for('usuarios.modulos_sistema', _anchor='pasteleria'))
    estado = 'activados' if config.encargos_activo else 'desactivados'
    flash(f'Encargos {estado} para el negocio #{cliente_id}.', 'success')
    return redirect(url_for('usuarios.modulos_sistema', _anchor='pasteleria'))
