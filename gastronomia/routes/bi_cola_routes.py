"""Acciones de la cola de clientes que vuelven y su configuracion (BI-02)."""
from flask import flash, redirect, request, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.bi.cola_acciones import (
    abrir_contacto,
    marcar_enviado,
    no_quiere_mensajes,
    omitir_contacto,
)
from gastronomia.services.bi.cola_config import guardar_config
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


def _volver_al_tablero():
    return redirect(url_for('inteligencia.dashboard', vista='gastronomia'))


def _responder_accion(accion, mensaje_ok: str | None = None):
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    try:
        resultado = accion(cliente_id, request.form)
    except ValueError as error:
        flash(str(error), 'warning')
        return _volver_al_tablero()
    if isinstance(resultado, str):
        return redirect(resultado)
    if mensaje_ok:
        flash(mensaje_ok, 'success')
    return _volver_al_tablero()


@gastronomia_bp.route('/bi/cola/abrir', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_cola_abrir():
    return _responder_accion(abrir_contacto)


@gastronomia_bp.route('/bi/cola/enviado', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_cola_enviado():
    return _responder_accion(marcar_enviado, 'Mensaje marcado como enviado.')


@gastronomia_bp.route('/bi/cola/omitir', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_cola_omitir():
    return _responder_accion(omitir_contacto, 'Contacto omitido.')


@gastronomia_bp.route('/bi/cola/no-quiere', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_cola_no_quiere():
    return _responder_accion(no_quiere_mensajes, 'Ese cliente ya no aparece en ninguna cola.')


@gastronomia_bp.route('/bi/cola/configuracion', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_cola_configuracion():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    try:
        guardar_config(cliente_id, request.form)
    except ValueError as error:
        flash(str(error), 'warning')
    else:
        flash('Configuración de la cola guardada.', 'success')
    return _volver_al_tablero()
