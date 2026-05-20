from datetime import datetime, timedelta

from flask import current_app, flash, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user

from app import db

DEMO_BLOCKED_UNTIL_PREF = 'demo_access_blocked_until'
DEMO_LOGIN_STARTED_SESSION_KEY = 'demo_login_started_at'
DEFAULT_DEMO_SESSION_MINUTES = 10
DEFAULT_DEMO_BLOCK_MINUTES = 30


def _utcnow():
    return datetime.utcnow()


def _get_int_config(name, default):
    try:
        value = current_app.config.get(name, default)
        return max(1, int(value))
    except Exception:
        return default


def demo_session_minutes():
    return _get_int_config('DEMO_SESSION_MINUTES', DEFAULT_DEMO_SESSION_MINUTES)


def demo_block_minutes():
    return _get_int_config('DEMO_BLOCK_MINUTES', DEFAULT_DEMO_BLOCK_MINUTES)


def is_demo_user(usuario):
    username = ((getattr(usuario, 'username', '') or '')).strip().lower()
    if username == 'demo':
        return True
    try:
        return bool(usuario.modo_demo)
    except Exception:
        return False


def parse_demo_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def format_demo_timestamp(value):
    return value.replace(microsecond=0).isoformat()


def get_demo_blocked_until(usuario):
    if not is_demo_user(usuario):
        return None
    return parse_demo_timestamp(usuario.get_preferencia(DEMO_BLOCKED_UNTIL_PREF))


def clear_expired_demo_block(usuario, now=None):
    blocked_until = get_demo_blocked_until(usuario)
    if not blocked_until:
        return False
    if blocked_until > (now or _utcnow()):
        return False
    usuario.set_preferencia(DEMO_BLOCKED_UNTIL_PREF, None)
    db.session.commit()
    return True


def is_demo_blocked(usuario, now=None):
    blocked_until = get_demo_blocked_until(usuario)
    if not blocked_until:
        return False, None
    now = now or _utcnow()
    if blocked_until <= now:
        usuario.set_preferencia(DEMO_BLOCKED_UNTIL_PREF, None)
        db.session.commit()
        return False, None
    return True, blocked_until


def start_demo_session_if_needed(usuario, now=None):
    if not is_demo_user(usuario):
        session.pop(DEMO_LOGIN_STARTED_SESSION_KEY, None)
        return
    session[DEMO_LOGIN_STARTED_SESSION_KEY] = format_demo_timestamp(now or _utcnow())


def block_demo_user(usuario, now=None):
    now = now or _utcnow()
    blocked_until = now + timedelta(minutes=demo_block_minutes())
    usuario.set_preferencia(DEMO_BLOCKED_UNTIL_PREF, format_demo_timestamp(blocked_until))
    db.session.commit()
    return blocked_until


def demo_block_message(blocked_until=None):
    minutes = demo_block_minutes()
    if not blocked_until:
        return (
            'La sesion se cerro automaticamente porque esta en modo demo. '
            f'Intente nuevamente en {minutes} minutos.'
        )
    remaining = max(1, int((blocked_until - _utcnow()).total_seconds() // 60) + 1)
    return (
        'La sesion se cerro automaticamente porque esta en modo demo. '
        f'Intente nuevamente en aproximadamente {remaining} minutos.'
    )


def demo_session_expired_response(blocked_until):
    session.pop(DEMO_LOGIN_STARTED_SESSION_KEY, None)
    logout_user()
    message = demo_block_message(blocked_until)
    if _wants_json():
        return jsonify({'error': 'demo_blocked', 'mensaje': message}), 403
    flash(message, 'warning')
    return redirect(url_for('auth.login'))


def enforce_demo_session_limit():
    if request.path.startswith('/static/'):
        return None
    if not current_user.is_authenticated or not is_demo_user(current_user):
        return None

    now = _utcnow()
    blocked, blocked_until = is_demo_blocked(current_user, now)
    if blocked:
        return demo_session_expired_response(blocked_until)

    started_at = parse_demo_timestamp(session.get(DEMO_LOGIN_STARTED_SESSION_KEY))
    if not started_at:
        start_demo_session_if_needed(current_user, now)
        return None

    elapsed = now - started_at
    if elapsed < timedelta(minutes=demo_session_minutes()):
        return None

    blocked_until = block_demo_user(current_user, now)
    return demo_session_expired_response(blocked_until)


def _wants_json():
    try:
        if (request.path or '').startswith('/api/'):
            return True
        if request.is_json:
            return True
        if (request.headers.get('X-Requested-With') or '') == 'XMLHttpRequest':
            return True
        if 'application/json' in (request.headers.get('Accept') or ''):
            return True
    except Exception:
        pass
    return False
