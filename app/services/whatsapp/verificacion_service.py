"""
Servicio de verificacion con codigos de 6 digitos.
Genera, hashea y valida codigos para acceso a datos sensibles.
"""
import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta

from app import db
from app.models.whatsapp import WhatsAppCodigoVerificacion, WhatsAppConversacion
from app.utils.phone_utils import normalizar_telefono

logger = logging.getLogger(__name__)


def _hash_codigo(codigo: str) -> str:
    """Hash SHA-256 de un codigo."""
    return hashlib.sha256(codigo.encode('utf-8')).hexdigest()


def generar_codigo(telefono: str, id_reparacion: int, dias_expiracion: int = None) -> str | None:
    """
    Genera un codigo de verificacion de 6 digitos para una reparacion.
    Retorna el codigo en texto plano (para entregar al cliente).
    En BD se guarda solo el hash.
    """
    if dias_expiracion is None:
        dias_expiracion = int(os.environ.get('WHATSAPP_CODIGO_EXPIRACION_DIAS', '30'))

    tel_norm = normalizar_telefono(telefono)
    if not tel_norm:
        logger.warning(f"Telefono invalido para generar codigo: {telefono}")
        return None

    # Generar codigo de 6 digitos
    codigo = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    codigo_hash = _hash_codigo(codigo)

    # Invalidar codigos anteriores del mismo telefono+reparacion
    WhatsAppCodigoVerificacion.query.filter_by(
        telefono=tel_norm,
        id_reparacion=id_reparacion,
        usado=False
    ).update({'usado': True})

    nuevo = WhatsAppCodigoVerificacion(
        telefono=tel_norm,
        id_reparacion=id_reparacion,
        codigo_hash=codigo_hash,
        expira_at=datetime.utcnow() + timedelta(days=dias_expiracion),
        usado=False,
        intentos_fallidos=0
    )
    db.session.add(nuevo)
    db.session.commit()

    logger.info(f"Codigo generado para tel={tel_norm} rep={id_reparacion}")
    return codigo


def verificar_codigo(telefono: str, codigo: str) -> dict:
    """
    Verifica un codigo de 6 digitos.
    El código impreso puede reutilizarse hasta vencer o ser reemplazado.
    Retorna dict con resultado de la verificacion.
    """
    max_intentos = int(os.environ.get('WHATSAPP_MAX_INTENTOS_CODIGO', '3'))

    tel_norm = normalizar_telefono(telefono)
    if not tel_norm:
        return {'verificado': False, 'error': 'Telefono invalido'}

    codigo = (codigo or '').strip()
    if not codigo or len(codigo) != 6 or not codigo.isdigit():
        return {'verificado': False, 'error': 'El codigo debe ser de 6 digitos numericos'}

    # Verificar si la conversacion esta bloqueada
    conv = WhatsAppConversacion.query.filter_by(telefono=tel_norm, activa=True).first()
    if conv and conv.bloqueado_hasta and conv.bloqueado_hasta > datetime.utcnow():
        minutos_restantes = int((conv.bloqueado_hasta - datetime.utcnow()).total_seconds() / 60) + 1
        return {
            'verificado': False,
            'bloqueado': True,
            'error': f'Acceso bloqueado por demasiados intentos. Intenta en {minutos_restantes} minutos.'
        }

    codigo_hash = _hash_codigo(codigo)

    # Buscar codigo valido
    registro = WhatsAppCodigoVerificacion.query.filter_by(
        telefono=tel_norm,
        codigo_hash=codigo_hash,
        usado=False
    ).filter(
        WhatsAppCodigoVerificacion.expira_at > datetime.utcnow()
    ).first()

    if registro:
        # Codigo correcto
        if conv:
            conv.intentos_codigo_fallidos = 0
            conv.bloqueado_hasta = None
        db.session.commit()

        logger.info(f"Codigo verificado OK para tel={tel_norm} rep={registro.id_reparacion}")
        return {
            'verificado': True,
            'id_reparacion': registro.id_reparacion,
            'mensaje': 'Codigo verificado correctamente. Ahora podes ver todos los detalles de tu reparacion.'
        }

    # Codigo incorrecto - incrementar intentos
    if conv:
        conv.intentos_codigo_fallidos = (conv.intentos_codigo_fallidos or 0) + 1
        if conv.intentos_codigo_fallidos >= max_intentos:
            conv.bloqueado_hasta = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            logger.warning(f"Conversacion bloqueada por intentos fallidos: tel={tel_norm}")
            return {
                'verificado': False,
                'bloqueado': True,
                'error': 'Demasiados intentos fallidos. Acceso bloqueado por 1 hora.'
            }
        db.session.commit()
        intentos_restantes = max_intentos - conv.intentos_codigo_fallidos
        return {
            'verificado': False,
            'error': f'Codigo incorrecto. Te quedan {intentos_restantes} intentos.'
        }

    # Sin conversacion activa
    return {'verificado': False, 'error': 'Codigo incorrecto o expirado.'}
