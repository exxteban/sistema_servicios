"""
Utilidades para el sistema de seguimiento público de reparaciones
"""
import secrets
import hashlib
import io
try:
    import segno
except ImportError:
    segno = None


def generar_token() -> str:
    """
    Genera un token URL-safe de 256 bits (43 caracteres)
    
    Returns:
        str: Token aleatorio seguro para URLs
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """
    Calcula el hash SHA-256 de un token
    
    Args:
        token: Token en texto plano
        
    Returns:
        str: Hash hexadecimal del token
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generar_qr_svg(url: str, scale: int = 3, border: int = 2) -> str:
    """
    Genera un código QR como SVG string
    
    Args:
        url: URL a codificar en el QR
        scale: Escala del QR (tamaño de cada módulo)
        border: Borde alrededor del QR (en módulos)
        
    Returns:
        str: SVG como string, listo para insertar en HTML
        
    Raises:
        ImportError: Si segno no está instalado
    """
    if segno is None:
        raise ImportError("El módulo 'segno' no está instalado. Ejecute: pip install segno")
    
    qr = segno.make(url, error='h')  # Error correction high
    buffer = io.BytesIO()
    qr.save(buffer, kind='svg', scale=scale, border=border, xmldecl=False, svgns=False)
    return buffer.getvalue().decode('utf-8')


def verificar_token(token: str, token_hash_guardado: str) -> bool:
    """
    Verifica si un token coincide con su hash guardado
    
    Args:
        token: Token en texto plano a verificar
        token_hash_guardado: Hash SHA-256 guardado en la base de datos
        
    Returns:
        bool: True si el token es válido
    """
    return hash_token(token) == token_hash_guardado
