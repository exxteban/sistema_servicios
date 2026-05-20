"""
Motor de busqueda de ayuda funcional del sistema.
Resuelve preguntas de uso sin llamar a la API de IA: cero tokens extra.
"""
import re
import unicodedata

from app.services.ia_backoffice.ayuda_kb import AYUDA_KB


def _normalizar(texto: str) -> str:
    texto = (texto or "").lower().strip()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto)


# Indice precalculado: lista de (claves_normalizadas, respuesta)
_INDICE: list[tuple[list[str], str]] = [
    ([_normalizar(c) for c in entrada["claves"]], entrada["respuesta"])
    for entrada in AYUDA_KB
]

# Palabras que indican intencion de ayuda de uso del sistema
_PALABRAS_AYUDA = {
    "como", "donde", "como se", "como hago", "como puedo", "como agrego",
    "como creo", "como registro", "como cargo", "como veo", "como abro",
    "como cierro", "como cambio", "como activo", "como habilito", "como uso",
    "donde esta", "donde veo", "donde estan", "donde se", "donde puedo",
    "que es", "para que sirve", "no aparece", "no veo", "no encuentro",
    "no tengo acceso", "no puedo", "ayuda", "ayudame", "explicame",
}

_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "en", "con", "por", "para", "que",
    "y", "o", "a", "se", "me", "te", "le", "lo",
}

# Claves de una sola palabra muy cortas que pueden causar falsos positivos
_MIN_CLAVE_SUBSTRING = 4


def _contiene_como_frase(texto: str, frase: str) -> bool:
    """Verifica que 'frase' aparezca como secuencia de palabras completas en 'texto'."""
    if not frase:
        return False
    # Escapar para regex y buscar con limites de palabra
    patron = r"(?<![a-z0-9])" + re.escape(frase) + r"(?![a-z0-9])"
    return bool(re.search(patron, texto))


def _score(texto_norm: str, claves_norm: list[str]) -> int:
    """Puntaje de coincidencia: mayor es mejor."""
    mejor = 0
    for clave in claves_norm:
        if not clave:
            continue
        if clave == texto_norm:
            return 100
        # Solo hacer match de substring si la clave tiene longitud suficiente
        if len(clave) >= _MIN_CLAVE_SUBSTRING and _contiene_como_frase(texto_norm, clave):
            mejor = max(mejor, 80 + len(clave))
        elif len(clave) >= _MIN_CLAVE_SUBSTRING and _contiene_como_frase(clave, texto_norm):
            mejor = max(mejor, 60 + len(texto_norm))
        else:
            # coincidencia por tokens individuales (solo tokens de 3+ chars)
            tokens_clave = {t for t in clave.split() if len(t) >= 3} - _STOPWORDS
            tokens_texto = {t for t in texto_norm.split() if len(t) >= 3} - _STOPWORDS
            if tokens_clave and tokens_texto:
                comunes = tokens_clave & tokens_texto
                if comunes:
                    ratio = len(comunes) / max(len(tokens_clave), len(tokens_texto))
                    mejor = max(mejor, int(ratio * 50))
    return mejor


def buscar_ayuda(consulta: str) -> str | None:
    """
    Busca en la KB de ayuda funcional.
    Devuelve el texto de respuesta si hay coincidencia suficiente, o None.
    Umbral conservador para no interceptar consultas de datos del negocio.
    """
    texto = _normalizar(consulta)
    if not texto or len(texto) < 5:
        return None

    if not _es_pregunta_de_ayuda(texto):
        return None

    mejor_score = 0
    mejor_respuesta = None

    for claves_norm, respuesta in _INDICE:
        score = _score(texto, claves_norm)
        if score > mejor_score:
            mejor_score = score
            mejor_respuesta = respuesta

    # Umbral: 30 puntos minimo para responder
    if mejor_score >= 30:
        return mejor_respuesta
    return None


def _es_pregunta_de_ayuda(texto_norm: str) -> bool:
    """Detecta si la consulta es sobre como usar el sistema (no sobre datos del negocio)."""
    for palabra in _PALABRAS_AYUDA:
        if _contiene_como_frase(texto_norm, palabra):
            return True
    return False
