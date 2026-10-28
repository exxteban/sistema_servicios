"""API para importar ventas historicas desde Excel."""
from flask import current_app, jsonify, request
from flask_login import current_user, login_required

from gastronomia.routes.reportes_api_routes import _cliente_o_error, gastronomia_reportes_api_bp
from gastronomia.services.importacion.analisis import analizar, guardar_archivo
from gastronomia.services.importacion.aplicar import aplicar_importacion
from gastronomia.services.importacion.detalle import detalle_importacion
from gastronomia.services.importacion.revertir import listar_importaciones, revertir_importacion
from gastronomia.services.permisos import PERMISO_CAJA, PERMISO_REPORTES, requiere_permiso_gastronomia


@gastronomia_reportes_api_bp.route('/importar-ventas', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
@requiere_permiso_gastronomia(PERMISO_CAJA)
def importar_ventas_listado():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return jsonify({'ok': True, 'importaciones': listar_importaciones(cliente_id)})


@gastronomia_reportes_api_bp.route('/importar-ventas/analizar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
@requiere_permiso_gastronomia(PERMISO_CAJA)
def importar_ventas_analizar():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    archivo = request.files.get('archivo')
    if not archivo:
        return jsonify({'ok': False, 'error': 'Elegi un archivo de Excel.'}), 400
    try:
        token = guardar_archivo(archivo)
        data = analizar(cliente_id, token, archivo.filename or '')
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True, 'analisis': data})


@gastronomia_reportes_api_bp.route('/importar-ventas/aplicar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
@requiere_permiso_gastronomia(PERMISO_CAJA)
def importar_ventas_aplicar():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        resultado = aplicar_importacion(cliente_id, current_user.id_usuario, request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except Exception:
        current_app.logger.exception('Error importando ventas historicas')
        return jsonify({'ok': False, 'error': 'No se pudo completar la importacion. No se guardo nada.'}), 500
    return jsonify({'ok': True, 'importacion': resultado})


@gastronomia_reportes_api_bp.route('/importar-ventas/<int:importacion_id>/ventas', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
@requiere_permiso_gastronomia(PERMISO_CAJA)
def importar_ventas_detalle(importacion_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        data = detalle_importacion(cliente_id, importacion_id)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 404
    return jsonify({'ok': True, **data})


@gastronomia_reportes_api_bp.route('/importar-ventas/<int:importacion_id>/revertir', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
@requiere_permiso_gastronomia(PERMISO_CAJA)
def importar_ventas_revertir(importacion_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        resultado = revertir_importacion(cliente_id, importacion_id)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True, 'importacion': resultado})
