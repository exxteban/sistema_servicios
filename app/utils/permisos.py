"""
Utilidades para gestión de permisos
"""
from functools import wraps
from flask import session, jsonify, request
from flask_login import current_user


def requiere_permiso(codigo_permiso):
    """
    Decorador para proteger rutas que requieren un permiso específico
    
    Uso:
        @app.route('/api/ventas/anular/<int:id>', methods=['POST'])
        @requiere_permiso('anular_venta')
        def anular_venta(id):
            # Lógica de anulación
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'No autenticado'}), 401
            
            if not current_user.tiene_permiso(codigo_permiso):
                modo_demo = bool(getattr(current_user, 'modo_demo', False))
                mensaje = 'No tienes permiso para realizar esta acción'
                if modo_demo:
                    mensaje = 'Modo demo: esta acción está deshabilitada'
                return jsonify({
                    'error': 'Sin permisos',
                    'mensaje': mensaje,
                    'permiso_requerido': codigo_permiso,
                    'modo_demo': modo_demo,
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def requiere_autorizacion(codigo_permiso):
    """
    Verifica si un permiso requiere autorización de administrador
    
    Returns:
        bool: True si requiere autorización, False si no
    """
    from app.models.permiso import Permiso
    return Permiso.requiere_autorizacion_admin(codigo_permiso)


def validar_autorizacion(id_autorizacion, codigo_permiso):
    from app.models import Autorizacion, Permiso

    if current_user.es_admin():
        return True, None

    if current_user.tiene_permiso(codigo_permiso):
        return True, None

    permiso = Permiso.query.filter_by(codigo=codigo_permiso, activo=True).first()
    if not permiso:
        return False, 'Permiso no encontrado'
    if not permiso.requiere_autorizacion:
        return False, 'Sin permisos'

    if not id_autorizacion:
        return False, 'Se requiere autorización de administrador'

    autorizacion = Autorizacion.query.get(id_autorizacion)
    if not autorizacion or autorizacion.estado != 'aprobada':
        return False, 'Autorización inválida'

    if autorizacion.id_usuario_solicitante != current_user.id_usuario:
        return False, 'Autorización inválida'

    if autorizacion.id_permiso != permiso.id_permiso:
        return False, 'Autorización inválida'

    return True, autorizacion


def verificar_permiso(usuario, codigo_permiso):
    """
    Verifica si un usuario tiene un permiso específico
    
    Args:
        usuario: Instancia de Usuario
        codigo_permiso: Código del permiso a verificar
        
    Returns:
        bool: True si tiene el permiso, False si no
    """
    if not usuario or not usuario.activo:
        return False
    
    return usuario.tiene_permiso(codigo_permiso)


def obtener_permisos_usuario(usuario):
    """
    Obtiene todos los permisos de un usuario
    
    Args:
        usuario: Instancia de Usuario
        
    Returns:
        list: Lista de códigos de permisos
    """
    if not usuario:
        return []
    
    return usuario.get_permisos()
