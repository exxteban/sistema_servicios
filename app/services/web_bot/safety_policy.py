"""
Guardrails de seguridad y tono para el bot web de tienda.
"""
from datetime import datetime
import re
import unicodedata


COMMERCIAL_REDIRECT_REPLY = (
    "Solo puedo ayudarte con consultas comerciales de la tienda: productos, precios, stock, "
    "envios, horarios, garantia y medios de pago."
)
WARNING_REPLY = (
    "Puedo ayudarte solo con consultas comerciales de la tienda. "
    "Si volves a insistir con mensajes inapropiados o pedidos internos del sistema, "
    "esta conversacion se va a bloquear."
)
INTERNAL_WARNING_REPLY = (
    "No puedo compartir detalles internos del sistema. "
    "Si volves a insistir con pedidos tecnicos internos, esta conversacion se va a bloquear."
)
SESSION_BLOCKED_REPLY = (
    "Esta conversacion fue bloqueada por uso indebido del asistente. "
    "Si necesitas atencion comercial real, contacta a la tienda por los canales habituales."
)
INTERNAL_INFO_DENIAL_REPLY = (
    "No puedo compartir detalles tecnicos internos del sistema. "
    "Si queres, te ayudo con informacion comercial de la tienda."
)
PROFESSIONAL_TONE_REPLY = (
    "Puedo ayudarte con consultas comerciales de la tienda. "
    "Contame que producto o dato necesitas y te respondo de forma clara."
)

SEXUAL_OR_ABUSIVE_PATTERNS = [
    re.compile(r"\bprostitut(?:a|as)\b", re.IGNORECASE),
    re.compile(r"\bescort(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bsexo\b", re.IGNORECASE),
    re.compile(r"\bsexual(?:es)?\b", re.IGNORECASE),
    re.compile(r"\bculo(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bporno\b", re.IGNORECASE),
]

TECHNICAL_PROBING_PATTERNS = [
    re.compile(r"\bendpoint(?:s)?\b", re.IGNORECASE),
    re.compile(r"\burl(?:es)?\b", re.IGNORECASE),
    re.compile(r"\bapi(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bjson\b", re.IGNORECASE),
    re.compile(r"\bpostman\b", re.IGNORECASE),
    re.compile(r"\btoken(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bservicio(?:s)?\b", re.IGNORECASE),
]

INTERNAL_TOOL_NAMES = [
    "buscar_productos_tienda",
    "obtener_precio_preciso_producto",
    "obtener_stock_preciso_producto",
    "listar_promociones_activas",
    "obtener_info_tienda",
]

UNPROFESSIONAL_OUTPUT_MARKERS = [
    "jaja",
    "papu",
    "carajo",
    "al pedo",
    "crack",
]

def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _detect_violation_reason(text: str) -> str:
    normalized = _normalize(text)
    if any(pattern.search(text or "") for pattern in SEXUAL_OR_ABUSIVE_PATTERNS):
        return "sexual_or_abusive"
    if any(pattern.search(text or "") for pattern in TECHNICAL_PROBING_PATTERNS) and any(
        marker in normalized for marker in ("intern", "endpoint", "api", "json", "postman", "token")
    ):
        return "technical_internal_request"
    if any(tool_name in normalized for tool_name in INTERNAL_TOOL_NAMES):
        return "internal_tool_disclosure"
    return ""


def evaluate_user_message_guardrail(text: str, metadata: dict | None = None) -> dict:
    """
    Evalua si el mensaje del usuario debe bloquearse por seguridad/alcance.
    """
    meta = metadata if isinstance(metadata, dict) else {}
    safety = meta.setdefault("safety", {})
    if safety.get("blocked"):
        return {
            "blocked": True,
            "reason": "session_blocked",
            "reply": SESSION_BLOCKED_REPLY,
            "close_now": True,
            "warning_issued": False,
            "session_blocked": True,
            "should_block_session": False,
        }

    reason = _detect_violation_reason(text)
    if reason:
        warning_count = int(safety.get("warning_count") or 0) + 1
        safety["warning_count"] = warning_count
        safety["last_reason"] = reason
        safety["last_violation_at"] = datetime.utcnow().isoformat()
        if warning_count >= 2:
            safety["blocked"] = True
            return {
                "blocked": True,
                "reason": reason,
                "reply": SESSION_BLOCKED_REPLY,
                "close_now": True,
                "warning_issued": False,
                "session_blocked": True,
                "should_block_session": True,
            }
        return {
            "blocked": True,
            "reason": reason,
            "reply": INTERNAL_WARNING_REPLY if reason != "sexual_or_abusive" else WARNING_REPLY,
            "close_now": False,
            "warning_issued": True,
            "session_blocked": False,
            "should_block_session": False,
        }

    return {
        "blocked": False,
        "reason": "",
        "reply": "",
        "close_now": False,
        "warning_issued": False,
        "session_blocked": False,
        "should_block_session": False,
    }


def enforce_assistant_output_guardrail(text: str) -> str:
    """
    Sanitiza respuestas del modelo cuando se salen del tono o exponen detalles internos.
    """
    raw_text = (text or "").strip()
    normalized = _normalize(raw_text)
    if not raw_text:
        return COMMERCIAL_REDIRECT_REPLY
    if any(tool_name in normalized for tool_name in INTERNAL_TOOL_NAMES):
        return INTERNAL_INFO_DENIAL_REPLY
    if any(marker in normalized for marker in UNPROFESSIONAL_OUTPUT_MARKERS):
        return PROFESSIONAL_TONE_REPLY
    return raw_text
