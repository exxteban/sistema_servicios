import json

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models.venta import Venta
from app.services.system_modules import system_module_enabled
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO, TIPOS_CONTRIBUYENTE
from facturacion_electronica.services import (
    construir_data_venta,
    construir_params_emisor,
    firmar_documento,
    generar_documento,
    generar_xml,
    geo,
    guardar_configuracion,
    obtener_configuracion,
    obtener_documento,
    validar_configuracion,
)


facturacion_electronica_bp = Blueprint(
    'facturacion_electronica',
    __name__,
    template_folder='templates',
)


def _puede_configurar():
    return current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')


@facturacion_electronica_bp.before_request
def _require_modulo_activo():
    if system_module_enabled(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, default=False):
        return None
    mensaje = 'El modulo de facturacion electronica esta desactivado.'
    wants_json = (
        request.is_json
        or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
    )
    if wants_json:
        return jsonify({
            'error': 'Modulo desactivado',
            'mensaje': mensaje,
            'modulo': 'facturacion_electronica',
        }), 403
    flash(mensaje, 'warning')
    return redirect(url_for('main.dashboard'))


@facturacion_electronica_bp.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    if not _puede_configurar():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta accion esta deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para configurar facturacion electronica.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        _config, error_cert = guardar_configuracion(
            request.form,
            archivo_cert=request.files.get('certificado'),
        )
        if error_cert:
            flash(error_cert, 'warning')
        else:
            flash('Configuracion de facturacion electronica guardada.', 'success')
        return redirect(url_for('facturacion_electronica.configuracion'))

    config = obtener_configuracion()
    return render_template(
        'facturacion_electronica/configuracion.html',
        config=config,
        tipos_contribuyente=TIPOS_CONTRIBUYENTE,
        faltantes=validar_configuracion(config),
        departamentos=geo.departamentos(),
    )


@facturacion_electronica_bp.route('/geo/distritos')
@login_required
def geo_distritos():
    return jsonify(geo.distritos_de(request.args.get('departamento')))


@facturacion_electronica_bp.route('/geo/ciudades')
@login_required
def geo_ciudades():
    return jsonify(geo.ciudades_de(request.args.get('distrito')))


@facturacion_electronica_bp.route('/vista-previa')
@login_required
def vista_previa():
    if not _puede_configurar():
        flash('No tienes permisos para facturacion electronica.', 'danger')
        return redirect(url_for('main.dashboard'))

    venta_id = (request.args.get('venta') or '').strip()
    venta = Venta.query.get(venta_id) if venta_id.isdigit() else None
    documento_json = None
    xml_generado = None
    xml_error = None

    if venta_id and venta is None:
        flash(f'No se encontró la venta {venta_id}.', 'warning')
    elif venta is not None:
        config = obtener_configuracion()
        params = construir_params_emisor(config)
        data = construir_data_venta(venta, config)
        documento_json = json.dumps(
            {'params': params, 'data': data}, indent=2, ensure_ascii=False, default=str
        )
        if request.args.get('generar'):
            xml_generado, xml_error = generar_xml(params, data)

    return render_template(
        'facturacion_electronica/vista_previa.html',
        venta_id=venta_id,
        venta=venta,
        documento_json=documento_json,
        xml_generado=xml_generado,
        xml_error=xml_error,
        documento=obtener_documento(venta.id_venta) if venta is not None else None,
    )


@facturacion_electronica_bp.route('/emitir/<int:venta_id>', methods=['POST'])
@login_required
def emitir(venta_id):
    if not _puede_configurar():
        flash('No tienes permisos para facturacion electronica.', 'danger')
        return redirect(url_for('main.dashboard'))

    venta = Venta.query.get(venta_id)
    if venta is None:
        flash(f'No se encontró la venta {venta_id}.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa'))

    documento, error = generar_documento(venta)
    if error:
        flash(f'No se pudo generar el documento: {error}', 'danger')
    else:
        flash(f'Documento generado y guardado. CDC: {documento.cdc}', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/firmar/<int:venta_id>', methods=['POST'])
@login_required
def firmar(venta_id):
    if not _puede_configurar():
        flash('No tienes permisos para facturacion electronica.', 'danger')
        return redirect(url_for('main.dashboard'))

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('Primero generá el documento para esta venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    _doc, error = firmar_documento(documento)
    if error:
        flash(f'No se pudo firmar: {error}', 'danger')
    else:
        flash('Documento firmado correctamente.', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))
