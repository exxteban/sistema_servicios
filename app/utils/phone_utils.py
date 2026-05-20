"""
Utilidades para normalizacion de numeros de telefono.
Soporta formato internacional (+595...) y formatos locales de Paraguay.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Codigo de pais por defecto (Paraguay)
DEFAULT_COUNTRY_CODE = '595'

# Prefijos de operadoras moviles Paraguay (sin 0)
_PY_MOBILE_PREFIXES = {'96', '97', '98', '99', '91', '92', '93', '94', '95',
                        '81', '82', '83', '84', '85', '86'}


def normalizar_telefono(telefono: str, codigo_pais: str = DEFAULT_COUNTRY_CODE) -> str | None:
    """
    Normaliza un numero de telefono a formato internacional E.164.
    
    Ejemplos Paraguay:
        '0981123456'   -> '+595981123456'
        '981123456'    -> '+595981123456'
        '+595981123456' -> '+595981123456'
        '595981123456'  -> '+595981123456'
    
    Retorna None si el numero no es valido.
    """
    if not telefono:
        return None

    # Limpiar: solo digitos y +
    limpio = re.sub(r'[^\d+]', '', telefono.strip())
    if not limpio:
        return None

    # Si empieza con +, remover para trabajar solo con digitos
    if limpio.startswith('+'):
        digitos = limpio[1:]
    else:
        digitos = limpio

    # Solo digitos a partir de aca
    digitos = re.sub(r'\D', '', digitos)
    if not digitos:
        return None

    # Si empieza con el codigo de pais, ya esta en formato internacional
    if digitos.startswith(codigo_pais):
        numero_local = digitos[len(codigo_pais):]
    elif digitos.startswith('0'):
        # Formato local con 0 adelante (ej: 0981123456)
        numero_local = digitos[1:]
    else:
        # Asumir que es numero local sin 0 (ej: 981123456)
        numero_local = digitos

    # Validar longitud minima
    if len(numero_local) < 6 or len(numero_local) > 12:
        logger.warning(f"Telefono con longitud invalida despues de normalizar: {telefono} -> {numero_local}")
        return None

    resultado = f'+{codigo_pais}{numero_local}'

    # Validar longitud total E.164 (max 15 digitos incluyendo codigo pais)
    total_digitos = len(codigo_pais) + len(numero_local)
    if total_digitos > 15:
        logger.warning(f"Telefono excede longitud E.164: {resultado}")
        return None

    return resultado


def formatear_telefono_display(telefono: str) -> str:
    """
    Formatea un telefono normalizado para mostrar al usuario.
    '+595981123456' -> '0981 123 456'
    """
    if not telefono:
        return ''

    limpio = re.sub(r'[^\d]', '', telefono)

    if limpio.startswith(DEFAULT_COUNTRY_CODE):
        local = limpio[len(DEFAULT_COUNTRY_CODE):]
        # Formato: 0XXX XXX XXX
        if len(local) >= 9:
            return f'0{local[:3]} {local[3:6]} {local[6:]}'
        return f'0{local}'

    return telefono


def extraer_telefono_whatsapp(wa_id: str) -> str:
    """
    Extrae y normaliza el telefono desde un WhatsApp ID.
    WhatsApp envia el numero sin + (ej: '595981123456').
    """
    if not wa_id:
        return ''
    # WhatsApp IDs son solo digitos, agregar +
    digitos = re.sub(r'\D', '', wa_id)
    if digitos:
        return f'+{digitos}'
    return ''


def son_mismo_telefono(tel1: str, tel2: str) -> bool:
    """Compara dos telefonos normalizandolos primero."""
    n1 = normalizar_telefono(tel1)
    n2 = normalizar_telefono(tel2)
    if n1 is None or n2 is None:
        return False
    return n1 == n2


def ocultar_telefono(telefono: str) -> str:
    """
    Oculta parte del telefono para privacidad.
    '+595981123456' -> '+595981***456'
    """
    if not telefono or len(telefono) < 8:
        return telefono or ''
    return telefono[:-6] + '***' + telefono[-3:]
