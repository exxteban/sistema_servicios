"""Cifrado de la contraseña del certificado en reposo.

Usa Fernet con una clave derivada del SECRET_KEY de la instalación, así no
hace falta configurar nada extra en el deploy. Es resiliente: si la librería
no estuviera disponible degrada a texto plano (sin romper) y soporta valores
ya guardados en plano (compatibilidad hacia atrás).
"""
import base64
import hashlib
import logging

from flask import current_app

try:
    from cryptography.fernet import Fernet, InvalidToken
    _DISPONIBLE = True
except Exception:
    _DISPONIBLE = False

_PREFIJO = 'fe1:'
_log = logging.getLogger(__name__)


def _fernet():
    secret = (current_app.config.get('SECRET_KEY') or '').encode()
    clave = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(clave)


def cifrar(texto):
    if not texto:
        return texto
    if not _DISPONIBLE:
        _log.warning('cryptography no disponible: la contraseña del certificado se guarda sin cifrar.')
        return texto
    token = _fernet().encrypt(texto.encode()).decode()
    return _PREFIJO + token


def descifrar(valor):
    if not valor or not valor.startswith(_PREFIJO) or not _DISPONIBLE:
        return valor
    try:
        return _fernet().decrypt(valor[len(_PREFIJO):].encode()).decode()
    except InvalidToken:
        return valor


__all__ = ['cifrar', 'descifrar']
