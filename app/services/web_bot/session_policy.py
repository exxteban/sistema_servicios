"""
Políticas de expiración de sesiones del bot web.
"""
from datetime import datetime, timedelta


WEB_BOT_SESSION_TTL = timedelta(hours=24)


def utcnow() -> datetime:
    return datetime.utcnow()


def get_session_activity_at(session) -> datetime | None:
    return (
        getattr(session, 'ultima_actividad', None)
        or getattr(session, 'fecha_modificacion', None)
        or getattr(session, 'fecha_creacion', None)
    )


def get_session_expires_at(session) -> datetime | None:
    activity_at = get_session_activity_at(session)
    if not activity_at:
        return None
    return activity_at + WEB_BOT_SESSION_TTL


def is_session_expired(session, now: datetime | None = None) -> bool:
    expires_at = get_session_expires_at(session)
    if not expires_at:
        return False
    return (now or utcnow()) >= expires_at
