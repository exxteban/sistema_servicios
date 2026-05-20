"""
Utilidades para auditoría de acciones
"""
from functools import wraps
from flask import request
from flask_login import current_user
from app.models.auditoria import Auditoria


def registrar_auditoria(accion, modulo, descripcion, 
                       referencia_tipo=None, referencia_id=None,
                       datos_anteriores=None, datos_nuevos=None,
                       id_autorizacion=None,
                       commit=True):
    """
    Registra una acción en la auditoría
    
    Args:
        accion: Código de la acción (ej: 'anular_venta')
        modulo: Módulo del sistema (ej: 'ventas')
        descripcion: Descripción legible de la acción
        referencia_tipo: Tipo de entidad afectada (ej: 'venta')
        referencia_id: ID de la entidad afectada
        datos_anteriores: Dict con datos antes del cambio
        datos_nuevos: Dict con datos después del cambio
        id_autorizacion: ID de la autorización si aplica
    
    Returns:
        Auditoria: Registro de auditoría creado
    """
    try:
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None
        id_usuario = current_user.id_usuario if current_user.is_authenticated else None
        if not id_usuario:
            return None
        return Auditoria.registrar(
            id_usuario=id_usuario,
            accion=accion,
            modulo=modulo,
            descripcion=descripcion,
            referencia_tipo=referencia_tipo,
            referencia_id=referencia_id,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            id_autorizacion=id_autorizacion,
            ip_address=ip_address,
            user_agent=user_agent,
            commit=commit
        )
    except Exception:
        return None


def auditar(accion, modulo, obtener_descripcion=None):
    """
    Decorador para auditar automáticamente una ruta
    
    Uso:
        @app.route('/api/ventas/anular/<int:id>', methods=['POST'])
        @auditar('anular_venta', 'ventas', 
                 lambda id: f'Anular venta #{id}')
        def anular_venta(id):
            # Lógica de anulación
            pass
    
    Args:
        accion: Código de la acción
        modulo: Módulo del sistema
        obtener_descripcion: Función que recibe los mismos argumentos que la ruta
                            y retorna la descripción de la acción
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Ejecutar la función original
            resultado = f(*args, **kwargs)
            
            # Generar descripción
            if obtener_descripcion:
                descripcion = obtener_descripcion(*args, **kwargs)
            else:
                descripcion = f'Acción {accion} en módulo {modulo}'
            
            # Registrar en auditoría
            try:
                registrar_auditoria(
                    accion=accion,
                    modulo=modulo,
                    descripcion=descripcion
                )
            except Exception as e:
                # No fallar la request si falla la auditoría
                print(f"Error al auditar: {e}")
            
            return resultado
        return decorated_function
    return decorator
