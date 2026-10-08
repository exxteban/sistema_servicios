"""Rutas de configuración que sólo existen en modo API.

Viven aparte de `routes.py` por tamaño; se cuelgan del mismo blueprint.
"""
from flask import flash, redirect, request, url_for
from flask_login import login_required

from facturacion_electronica.routes import _puede_configurar, facturacion_electronica_bp
from facturacion_electronica.services import obtener_configuracion
from facturacion_electronica.services.proveedores import PROVEEDOR_API
from facturacion_electronica.services.proveedores.api_emisor import cargar_datos_fiscales
from facturacion_electronica.services.proveedores.api_secretos import subir_certificado, subir_csc
from facturacion_electronica.services.proveedores.api_timbrado import cargar_timbrado


def _config_api_o_redireccion():
    """(config, None) si se puede cargar en la API; (None, redirect) si no."""
    if not _puede_configurar():
        flash('No tenés permisos para configurar facturación electrónica.', 'danger')
        return None, redirect(url_for('main.dashboard'))
    config = obtener_configuracion()
    if (config.proveedor or '') != PROVEEDOR_API:
        flash('Esto se carga en la API sólo con el proveedor "API externa".', 'warning')
        return None, redirect(url_for('facturacion_electronica.configuracion'))
    return config, None


def _responder(resumen, error):
    flash(error or resumen, 'danger' if error else 'success')
    return redirect(url_for('facturacion_electronica.configuracion'))


@facturacion_electronica_bp.route('/proveedor/certificado', methods=['POST'])
@login_required
def subir_certificado_api():
    config, salida = _config_api_o_redireccion()
    if salida:
        return salida
    return _responder(*subir_certificado(
        config, request.files.get('certificado'), request.form.get('cert_password'),
        request.form.get('ambiente_api'),
    ))


@facturacion_electronica_bp.route('/proveedor/csc', methods=['POST'])
@login_required
def subir_csc_api():
    config, salida = _config_api_o_redireccion()
    if salida:
        return salida
    return _responder(*subir_csc(
        config, request.form.get('csc_id'), request.form.get('csc'), request.form.get('ambiente_api'),
    ))


@facturacion_electronica_bp.route('/proveedor/timbrado', methods=['POST'])
@login_required
def cargar_timbrado_api():
    config, salida = _config_api_o_redireccion()
    if salida:
        return salida
    return _responder(*cargar_timbrado(config, request.form))


@facturacion_electronica_bp.route('/proveedor/datos-fiscales', methods=['POST'])
@login_required
def cargar_datos_fiscales_api():
    config, salida = _config_api_o_redireccion()
    if salida:
        return salida
    return _responder(*cargar_datos_fiscales(config))
