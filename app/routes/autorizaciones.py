"""
Rutas para gestión de autorizaciones y permisos
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Usuario, Permiso, Autorizacion
from app.utils.permisos import requiere_permiso
from app.utils.auditoria_utils import registrar_auditoria

bp = Blueprint('autorizaciones', __name__, url_prefix='/api/autorizacion')


@bp.route('/solicitar', methods=['POST'])
@login_required
def solicitar_autorizacion():
    """
    Solicita autorización de un administrador para realizar una acción crítica
    
    Body JSON:
    {
        "codigo_permiso": "anular_venta",
        "accion": "Anular venta #123",
        "referencia_tipo": "venta",
        "referencia_id": 123,
        "username_admin": "admin",
        "password_admin": "***"
    }
    
    Returns:
        {
            "success": true,
            "id_autorizacion": 1,
            "mensaje": "Autorización concedida"
        }
    """
    try:
        data = request.json
        
        # Validar datos requeridos
        campos_requeridos = ['codigo_permiso', 'accion', 'username_admin', 'password_admin']
        for campo in campos_requeridos:
            if campo not in data:
                return jsonify({'error': f'Campo requerido: {campo}'}), 400
        
        # Verificar que el permiso existe
        permiso = Permiso.query.filter_by(codigo=data['codigo_permiso'], activo=True).first()
        if not permiso:
            return jsonify({'error': 'Permiso no encontrado'}), 404
        
        # Verificar que el permiso requiere autorización
        if not permiso.requiere_autorizacion:
            return jsonify({'error': 'Este permiso no requiere autorización'}), 400
        
        # Verificar credenciales del administrador
        admin = Usuario.query.filter_by(username=data['username_admin'], activo=True).first()
        if not admin or not admin.check_password(data['password_admin']):
            # Registrar intento fallido
            registrar_auditoria(
                accion='autorizacion_fallida',
                modulo='seguridad',
                descripcion=f'Intento fallido de autorización para: {data["accion"]}',
                referencia_tipo=data.get('referencia_tipo'),
                referencia_id=data.get('referencia_id')
            )
            return jsonify({'error': 'Credenciales de administrador inválidas'}), 401
        
        # Verificar que el admin puede autorizar este permiso
        if not admin.puede_autorizar(data['codigo_permiso']):
            return jsonify({
                'error': 'El usuario no tiene permisos para autorizar esta acción'
            }), 403
        
        # Crear registro de autorización
        autorizacion = Autorizacion.crear_autorizacion(
            id_solicitante=current_user.id_usuario,
            id_autorizador=admin.id_usuario,
            codigo_permiso=data['codigo_permiso'],
            accion=data['accion'],
            referencia_tipo=data.get('referencia_tipo'),
            referencia_id=data.get('referencia_id'),
            ip_address=request.remote_addr
        )
        
        # Registrar en auditoría
        registrar_auditoria(
            accion='autorizacion_concedida',
            modulo='seguridad',
            descripcion=f'Autorización concedida por {admin.username} para: {data["accion"]}',
            referencia_tipo=data.get('referencia_tipo'),
            referencia_id=data.get('referencia_id'),
            id_autorizacion=autorizacion.id_autorizacion
        )
        
        return jsonify({
            'success': True,
            'id_autorizacion': autorizacion.id_autorizacion,
            'mensaje': 'Autorización concedida'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/permisos', methods=['GET'])
@login_required
def obtener_permisos_usuario():
    """
    Obtiene los permisos del usuario actual
    
    Returns:
        {
            "permisos": ["crear_venta", "ver_ventas", ...],
            "rol": "Cajero"
        }
    """
    try:
        permisos = current_user.get_permisos()
        rol_nombre = current_user.rol.nombre if current_user.rol else 'Sin rol'
        
        return jsonify({
            'permisos': permisos,
            'rol': rol_nombre,
            'es_admin': current_user.es_admin(),
            'modo_demo': bool(getattr(current_user, 'modo_demo', False)),
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/verificar/<codigo_permiso>', methods=['GET'])
@login_required
def verificar_permiso(codigo_permiso):
    """
    Verifica si el usuario actual tiene un permiso específico
    
    Returns:
        {
            "tiene_permiso": true,
            "requiere_autorizacion": false
        }
    """
    try:
        tiene_permiso = current_user.tiene_permiso(codigo_permiso)
        
        permiso = Permiso.query.filter_by(codigo=codigo_permiso, activo=True).first()
        requiere_autorizacion = (
            bool(permiso and permiso.requiere_autorizacion)
            and not current_user.es_admin()
            and not tiene_permiso
        )
        
        return jsonify({
            'tiene_permiso': tiene_permiso,
            'requiere_autorizacion': requiere_autorizacion
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/permisos/todos', methods=['GET'])
@login_required
@requiere_permiso('gestionar_roles')
def listar_todos_permisos():
    """
    Lista todos los permisos del sistema (solo admin)
    
    Returns:
        {
            "permisos": [
                {
                    "id": 1,
                    "codigo": "crear_venta",
                    "nombre": "Crear Venta",
                    "modulo": "ventas",
                    "requiere_autorizacion": false
                },
                ...
            ]
        }
    """
    try:
        permisos = Permiso.query.filter_by(activo=True).order_by(Permiso.modulo, Permiso.nombre).all()
        
        return jsonify({
            'permisos': [{
                'id': p.id_permiso,
                'codigo': p.codigo,
                'nombre': p.nombre,
                'descripcion': p.descripcion,
                'modulo': p.modulo,
                'requiere_autorizacion': p.requiere_autorizacion
            } for p in permisos]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
