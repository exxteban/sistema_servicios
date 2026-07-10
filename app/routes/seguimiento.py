"""
Blueprint público para seguimiento de reparaciones (sin autenticación)
"""
from flask import Blueprint, render_template, jsonify, abort, request
from app import db
from app.models.reparacion import Reparacion
from app.models.reparacion_seguimiento import ReparacionSeguimiento, SeguimientoAcceso
from app.utils.seguimiento_utils import hash_token
from datetime import datetime


seguimiento_bp = Blueprint('seguimiento', __name__)


def _registrar_acceso(seguimiento):
    """Registra un acceso al seguimiento"""
    try:
        # Obtener IP del cliente
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        
        # Obtener User-Agent
        user_agent = request.headers.get('User-Agent', '')[:256]
        
        # Registrar acceso
        acceso = SeguimientoAcceso(
            id_seguimiento=seguimiento.id,
            ip_address=ip,
            user_agent=user_agent
        )
        db.session.add(acceso)
        
        # Actualizar contador y última vez
        seguimiento.access_count += 1
        seguimiento.last_accessed_at = datetime.utcnow()
        
        db.session.commit()
    except Exception:
        db.session.rollback()


@seguimiento_bp.route('/<token>')
def ver_seguimiento(token):
    """
    Página pública de seguimiento de reparación
    No requiere autenticación
    """
    # Buscar por hash del token
    token_hash = hash_token(token)
    seguimiento = ReparacionSeguimiento.query.filter_by(
        token_hash=token_hash,
        revoked_at=None  # Solo tokens activos
    ).first()
    
    if not seguimiento:
        abort(404)
    
    # Registrar acceso
    _registrar_acceso(seguimiento)
    
    reparacion = seguimiento.reparacion
    
    # Obtener historial de estados
    historial = reparacion.historial_estados.order_by(
        db.desc('fecha_cambio')
    ).all()
    
    return render_template(
        'seguimiento/seguimiento.html',
        reparacion=reparacion,
        historial=historial,
        token=token
    )


@seguimiento_bp.route('/api/<token>')
def api_seguimiento(token):
    """
    API JSON para polling (actualización en tiempo real)
    Headers: Cache-Control: no-store
    """
    # Buscar por hash del token
    token_hash = hash_token(token)
    seguimiento = ReparacionSeguimiento.query.filter_by(
        token_hash=token_hash,
        revoked_at=None
    ).first()
    
    if not seguimiento:
        return jsonify({'error': 'Token inválido o revocado'}), 404
    
    reparacion = seguimiento.reparacion
    
    # Preparar estados traducidos
    estados_display = {
        'pendiente': 'Pendiente',
        'diagnostico': 'En Diagnóstico',
        'espera_presupuesto': 'Esperando Presupuesto',
        'espera_repuesto': 'Esperando Repuesto',
        'espera_cliente': 'Esperando Aprobación',
        'en_proceso': 'En Reparación',
        'listo': 'Listo para Retirar',
        'no_se_pudo': 'No se pudo reparar',
        'entregado': 'Entregado',
        'cancelado': 'Cancelado',
        'antiguos': 'Antiguos',
    }
    
    # Calcular costo a mostrar
    costo = None
    if reparacion.mostrar_costo:
        costo_final = float(reparacion.costo_final_calculado or 0)
        if costo_final > 0:
            costo = costo_final
        elif reparacion.costo_estimado and reparacion.costo_estimado > 0:
            costo = float(reparacion.costo_estimado)
    
    ultimo_cambio = reparacion.historial_estados.order_by(
        db.desc('fecha_cambio')
    ).first()
    fecha_actualizacion = (
        ultimo_cambio.fecha_cambio if ultimo_cambio else reparacion.fecha_ingreso
    )

    # Preparar respuesta
    data = {
        'estado': reparacion.estado,
        'estado_display': estados_display.get(reparacion.estado, reparacion.estado),
        'nota_cliente': reparacion.nota_cliente,
        'costo': costo,
        'fecha_estimada': reparacion.fecha_estimada.isoformat() if reparacion.fecha_estimada else None,
        'fecha_estimada_hora': reparacion.fecha_estimada_hora.isoformat() if reparacion.fecha_estimada_hora else None,
        'updated_at': fecha_actualizacion.isoformat() if fecha_actualizacion else None
    }
    
    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
