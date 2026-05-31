"""API interna para configuracion de menu gastronomico."""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app import db
from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.dashboard_preferences import set_dashboard_card_order
from gastronomia.services.channel_price_service import aplicar_precio_canal, normalizar_canal_precio
from gastronomia.services.menu_image_service import (
    eliminar_imagen_producto_menu,
    extension_permitida as extension_imagen_permitida,
    guardar_imagen_opcion_menu,
    guardar_imagen_producto_menu,
)
from gastronomia.services.menu_service import (
    actualizar_estado_producto,
    eliminar_categoria,
    eliminar_producto,
    guardar_categoria,
    guardar_producto,
    listar_categorias,
    listar_productos,
    obtener_categoria,
    obtener_producto,
    reordenar_categorias,
)
from gastronomia.services.modificadores_service import (
    eliminar_grupo,
    eliminar_opcion,
    guardar_grupo,
    guardar_opcion,
    listar_grupos_producto,
    obtener_grupo,
    obtener_opcion,
    producto_con_modificadores,
    sincronizar_adicionales_precio,
    sincronizar_ingredientes_removibles,
    validar_selecciones_producto,
)
from gastronomia.services.permisos import (
    PERMISO_ACCESO,
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_DELIVERY,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_REPORTES,
    PERMISO_SALON,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)


gastronomia_api_bp = Blueprint('gastronomia_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _adjuntar_imagen_producto(cliente_id: int, data: dict, producto_actual=None):
    archivo = request.files.get('imagen_archivo')
    quitar_imagen = str(data.get('quitar_imagen') or '').strip().lower() in {'1', 'true', 'on', 'si', 'yes'}
    imagen_anterior = producto_actual.imagen_url if producto_actual else None
    if quitar_imagen:
        data['imagen_url'] = ''
    if not archivo or not getattr(archivo, 'filename', ''):
        return data, imagen_anterior, None
    if not extension_imagen_permitida(archivo.filename):
        raise ValueError('La imagen debe ser PNG, JPG, JPEG, WEBP o GIF.')
    nueva_imagen = guardar_imagen_producto_menu(archivo, current_app.static_folder, cliente_id)
    data['imagen_url'] = nueva_imagen
    return data, imagen_anterior, nueva_imagen


def _adjuntar_imagen_opcion(cliente_id: int, data: dict, opcion_actual=None):
    archivo = request.files.get('imagen_archivo')
    quitar_imagen = str(data.get('quitar_imagen') or '').strip().lower() in {'1', 'true', 'on', 'si', 'yes'}
    imagen_anterior = opcion_actual.imagen_url if opcion_actual else None
    if quitar_imagen:
        data['imagen_url'] = ''
    if not archivo or not getattr(archivo, 'filename', ''):
        return data, imagen_anterior, None
    if not extension_imagen_permitida(archivo.filename):
        raise ValueError('La imagen debe ser PNG, JPG, JPEG, WEBP o GIF.')
    nueva_imagen = guardar_imagen_opcion_menu(archivo, current_app.static_folder, cliente_id)
    data['imagen_url'] = nueva_imagen
    return data, imagen_anterior, nueva_imagen


def _limpiar_imagen_subida(url_imagen: str | None) -> None:
    if not url_imagen:
        return
    try:
        eliminar_imagen_producto_menu(url_imagen, current_app.static_folder)
    except OSError:
        current_app.logger.warning('No se pudo limpiar una imagen de menu gastronomico temporal.')


@gastronomia_api_bp.route('/config', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_ACCESO)
def config():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return jsonify({'ok': True, 'cliente_id': cliente_id})


@gastronomia_api_bp.route('/dashboard/orden', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(
    PERMISO_ACCESO,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_COCINA,
    PERMISO_CAJA,
    PERMISO_SALON,
    PERMISO_DELIVERY,
    PERMISO_REPORTES,
)
def actualizar_orden_dashboard():
    data = _payload()
    card_ids = data.get('cards') or data.get('card_ids') or data.get('ids') or []
    if not isinstance(card_ids, list):
        return jsonify({'error': 'validation_error', 'mensaje': 'El orden recibido no es valido.'}), 400
    order = set_dashboard_card_order(current_user, card_ids, _permisos_dashboard())
    db.session.commit()
    return jsonify({'ok': True, 'cards': order})


@gastronomia_api_bp.route('/categorias', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU, PERMISO_POS)
def categorias():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    incluir_ocultas = request.args.get('publico') != '1'
    items = listar_categorias(cliente_id, incluir_ocultas=incluir_ocultas)
    return jsonify({'ok': True, 'categorias': [item.to_dict() for item in items]})


def _permisos_dashboard() -> dict[str, bool]:
    return {
        'menu': tiene_permiso_gastronomia(PERMISO_MENU),
        'pos': tiene_permiso_gastronomia(PERMISO_POS),
        'salon': tiene_permiso_gastronomia(PERMISO_SALON),
        'cocina': tiene_permiso_gastronomia(PERMISO_COCINA),
        'caja': tiene_permiso_gastronomia(PERMISO_CAJA),
        'delivery': tiene_permiso_gastronomia(PERMISO_DELIVERY),
        'entregas': tiene_permiso_gastronomia(PERMISO_CAJA, PERMISO_COCINA, PERMISO_SALON),
        'reportes': tiene_permiso_gastronomia(PERMISO_REPORTES),
    }


@gastronomia_api_bp.route('/categorias/orden', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU, PERMISO_POS)
def actualizar_orden_categorias():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    data = _payload()
    categoria_ids = data.get('categorias') or data.get('categoria_ids') or data.get('ids') or []
    if not isinstance(categoria_ids, list):
        return jsonify({'error': 'validation_error', 'mensaje': 'El orden recibido no es valido.'}), 400
    try:
        categorias_ordenadas = reordenar_categorias(cliente_id, categoria_ids)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'categorias': [item.to_dict() for item in categorias_ordenadas]})


@gastronomia_api_bp.route('/categorias', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear_categoria():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        categoria = guardar_categoria(cliente_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'categoria': categoria.to_dict()}), 201


@gastronomia_api_bp.route('/categorias/<int:categoria_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_categoria(categoria_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    categoria = obtener_categoria(cliente_id, categoria_id)
    if not categoria:
        return jsonify({'error': 'not_found'}), 404
    try:
        categoria = guardar_categoria(cliente_id, _payload(), categoria=categoria)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'categoria': categoria.to_dict()})


@gastronomia_api_bp.route('/categorias/<int:categoria_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def borrar_categoria(categoria_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not eliminar_categoria(cliente_id, categoria_id):
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True})


@gastronomia_api_bp.route('/productos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU, PERMISO_POS)
def productos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    categoria_id = request.args.get('categoria_id', type=int)
    incluir_ocultos = request.args.get('publico') != '1'
    incluir_agotados = request.args.get('agotados') == '1'
    try:
        canal_precio = normalizar_canal_precio(request.args.get('canal_precio'))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    items = listar_productos(
        cliente_id,
        categoria_id=categoria_id,
        incluir_ocultos=incluir_ocultos,
        incluir_agotados=incluir_agotados,
    )
    if request.args.get('modificadores') == '1':
        productos_data = [
            producto_con_modificadores(cliente_id, item.id_producto, canal_precio=canal_precio)
            for item in items
        ]
    else:
        productos_data = [aplicar_precio_canal(item, item.to_dict(), canal_precio) for item in items]
    return jsonify({'ok': True, 'productos': productos_data})


@gastronomia_api_bp.route('/productos', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear_producto():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    imagen_nueva = None
    try:
        data = _payload()
        data, _, imagen_nueva = _adjuntar_imagen_producto(cliente_id, data)
        producto = guardar_producto(cliente_id, data)
        if 'ingredientes_removibles' in data:
            sincronizar_ingredientes_removibles(
                cliente_id,
                producto.id_producto,
                data.get('ingredientes_removibles'),
            )
        if 'adicionales_precio' in data:
            sincronizar_adicionales_precio(
                cliente_id,
                producto.id_producto,
                data.get('adicionales_precio'),
            )
    except PermissionError:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'sin_permisos_uploads', 'mensaje': 'No hay permisos para guardar la imagen.'}), 500
    except ValueError as exc:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'producto': producto.to_dict()}), 201


@gastronomia_api_bp.route('/productos/<int:producto_id>', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU, PERMISO_POS)
def producto_detalle(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        return jsonify({'error': 'not_found'}), 404
    incluir_modificadores = request.args.get('modificadores') == '1'
    try:
        canal_precio = normalizar_canal_precio(request.args.get('canal_precio'))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    if incluir_modificadores:
        return jsonify({
            'ok': True,
            'producto': producto_con_modificadores(cliente_id, producto_id, canal_precio=canal_precio),
        })
    return jsonify({'ok': True, 'producto': aplicar_precio_canal(producto, producto.to_dict(), canal_precio)})


@gastronomia_api_bp.route('/productos/<int:producto_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_producto(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        return jsonify({'error': 'not_found'}), 404
    imagen_anterior = None
    imagen_nueva = None
    try:
        data = _payload()
        data, imagen_anterior, imagen_nueva = _adjuntar_imagen_producto(cliente_id, data, producto_actual=producto)
        producto = guardar_producto(cliente_id, data, producto=producto)
        if 'ingredientes_removibles' in data:
            sincronizar_ingredientes_removibles(
                cliente_id,
                producto.id_producto,
                data.get('ingredientes_removibles'),
            )
        if 'adicionales_precio' in data:
            sincronizar_adicionales_precio(
                cliente_id,
                producto.id_producto,
                data.get('adicionales_precio'),
            )
        if imagen_anterior and imagen_anterior != producto.imagen_url:
            try:
                eliminar_imagen_producto_menu(imagen_anterior, current_app.static_folder)
            except OSError:
                current_app.logger.warning(
                    'No se pudo eliminar la imagen anterior del producto gastronomico %s',
                    producto.id_producto,
                )
    except PermissionError:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'sin_permisos_uploads', 'mensaje': 'No hay permisos para guardar la imagen.'}), 500
    except ValueError as exc:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'producto': producto.to_dict()})


@gastronomia_api_bp.route('/productos/<int:producto_id>/estado', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_estado_producto_api(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    producto = actualizar_estado_producto(cliente_id, producto_id, _payload())
    if not producto:
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True, 'producto': producto.to_dict()})


@gastronomia_api_bp.route('/productos/<int:producto_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def borrar_producto(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not eliminar_producto(cliente_id, producto_id):
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True})


@gastronomia_api_bp.route('/productos/<int:producto_id>/grupos-opciones', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU, PERMISO_POS)
def grupos_producto(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not obtener_producto(cliente_id, producto_id):
        return jsonify({'error': 'not_found'}), 404
    grupos = listar_grupos_producto(cliente_id, producto_id)
    return jsonify({'ok': True, 'grupos': [grupo.to_dict() for grupo in grupos]})


@gastronomia_api_bp.route('/productos/<int:producto_id>/grupos-opciones', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear_grupo_producto(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        grupo = guardar_grupo(cliente_id, producto_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'grupo': grupo.to_dict()}), 201


@gastronomia_api_bp.route('/grupos-opciones/<int:grupo_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_grupo(grupo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    grupo = obtener_grupo(cliente_id, grupo_id)
    if not grupo:
        return jsonify({'error': 'not_found'}), 404
    try:
        grupo = guardar_grupo(cliente_id, grupo.producto_id, _payload(), grupo=grupo)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'grupo': grupo.to_dict()})


@gastronomia_api_bp.route('/grupos-opciones/<int:grupo_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def borrar_grupo(grupo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not eliminar_grupo(cliente_id, grupo_id):
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True})


@gastronomia_api_bp.route('/grupos-opciones/<int:grupo_id>/opciones', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear_opcion_grupo(grupo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    imagen_nueva = None
    try:
        data = _payload()
        data, _, imagen_nueva = _adjuntar_imagen_opcion(cliente_id, data)
        opcion = guardar_opcion(cliente_id, grupo_id, data)
    except PermissionError:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'sin_permisos_uploads', 'mensaje': 'No hay permisos para guardar la imagen.'}), 500
    except ValueError as exc:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'opcion': opcion.to_dict()}), 201


@gastronomia_api_bp.route('/opciones/<int:opcion_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_opcion(opcion_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    opcion = obtener_opcion(cliente_id, opcion_id)
    if not opcion:
        return jsonify({'error': 'not_found'}), 404
    imagen_anterior = None
    imagen_nueva = None
    try:
        data = _payload()
        data, imagen_anterior, imagen_nueva = _adjuntar_imagen_opcion(cliente_id, data, opcion_actual=opcion)
        opcion = guardar_opcion(cliente_id, opcion.grupo_id, data, opcion=opcion)
        if imagen_anterior and imagen_anterior != opcion.imagen_url:
            try:
                eliminar_imagen_producto_menu(imagen_anterior, current_app.static_folder)
            except OSError:
                current_app.logger.warning(
                    'No se pudo eliminar la imagen anterior de la opcion gastronomica %s',
                    opcion.id_opcion,
                )
    except PermissionError:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'sin_permisos_uploads', 'mensaje': 'No hay permisos para guardar la imagen.'}), 500
    except ValueError as exc:
        _limpiar_imagen_subida(imagen_nueva)
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'opcion': opcion.to_dict()})


@gastronomia_api_bp.route('/opciones/<int:opcion_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def borrar_opcion(opcion_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not eliminar_opcion(cliente_id, opcion_id):
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True})


@gastronomia_api_bp.route('/productos/<int:producto_id>/validar-selecciones', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU, PERMISO_POS)
def validar_modificadores_producto(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    data = _payload()
    try:
        resultado = validar_selecciones_producto(
            cliente_id,
            producto_id,
            data.get('opciones') or [],
            canal_precio=data.get('canal_precio'),
        )
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, **resultado})
