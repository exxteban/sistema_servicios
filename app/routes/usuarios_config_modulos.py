from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from app.routes.usuarios import usuarios_bp
from app.services.ia_backoffice.security import es_usuario_root
from app.services.system_modules import iter_system_modules, list_system_modules_with_state


def _checkbox_bool(form_key: str, default: bool = False) -> bool:
    valores = [str(v).strip() for v in request.form.getlist(form_key) if str(v).strip()]
    if not valores:
        return default
    return Configuracion.parse_bool(valores[-1], default=default)


def _require_root() -> None:
    if not es_usuario_root(current_user):
        abort(403)


def _guardar_modulos() -> list[str]:
    mensajes = []
    for modulo in iter_system_modules():
        activo = _checkbox_bool(modulo['clave'], default=bool(modulo.get('default', False)))
        Configuracion.establecer_bool(
            modulo['clave'],
            activo,
            modulo['descripcion'],
        )
        estado = 'activado' if activo else 'desactivado'
        mensajes.append(f"{modulo['nombre']} {estado}")
    return mensajes


@usuarios_bp.route('/modulos-sistema', methods=['GET', 'POST'])
@login_required
def modulos_sistema():
    _require_root()

    if request.method == 'POST':
        mensajes = _guardar_modulos()
        flash(f"Configuracion de modulos actualizada: {', '.join(mensajes)}.", 'success')
        return redirect(url_for('usuarios.modulos_sistema'))

    return render_template(
        'usuarios/modulos_sistema.html',
        modulos=list_system_modules_with_state(),
    )


@usuarios_bp.route('/configuracion/modulos', methods=['POST'])
@login_required
def configuracion_modulos():
    _require_root()
    mensajes = _guardar_modulos()
    flash(f"Configuracion de modulos actualizada: {', '.join(mensajes)}.", 'success')
    return redirect(url_for('usuarios.modulos_sistema'))
