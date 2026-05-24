from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from app.routes.usuarios import usuarios_bp
from app.services.dashboard_negocio import (
    establecer_dashboard_negocio_actual,
    listar_dashboards_negocio,
    obtener_dashboard_negocio_actual,
)
from app.services.ia_backoffice.security import es_usuario_root
from app.services.system_modules import iter_system_modules, list_system_modules_with_state
from gastronomia.services.modo_operacion import (
    establecer_modo_operacion,
    obtener_modo_operacion,
)


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
    if 'dashboard_negocio' in request.form:
        dashboard = establecer_dashboard_negocio_actual(request.form.get('dashboard_negocio'))
        mensajes.append(f"dashboard {dashboard['nombre']}")
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
        dashboards_negocio=listar_dashboards_negocio(),
        dashboard_negocio_actual=obtener_dashboard_negocio_actual(),
        modo_operacion_gastronomia=obtener_modo_operacion(),
    )


@usuarios_bp.route('/configuracion/modulos', methods=['POST'])
@login_required
def configuracion_modulos():
    _require_root()
    mensajes = _guardar_modulos()
    flash(f"Configuracion de modulos actualizada: {', '.join(mensajes)}.", 'success')
    return redirect(url_for('usuarios.modulos_sistema'))


@usuarios_bp.route('/modulos-sistema/gastronomia-modo', methods=['POST'])
@login_required
def modulos_sistema_gastronomia_modo():
    _require_root()
    modo_operacion = request.form.get('modo_operacion')
    config = establecer_modo_operacion(
        modo_operacion,
        usuario_id=getattr(current_user, 'id_usuario', None),
    )

    estado = 'Gastronomia' if config['gastronomia_activo'] else 'Servicios'
    flash(f'Modo operativo global actualizado: {estado}.', 'success')
    return redirect(url_for('usuarios.modulos_sistema'))
