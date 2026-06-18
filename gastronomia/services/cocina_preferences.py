"""Preferencias de sonido del KDS de cocina."""
from __future__ import annotations


COCINA_SOUND_ENABLED_PREF_KEY = 'gastronomia_cocina_sound_enabled'
COCINA_SOUND_PROFILE_PREF_KEY = 'gastronomia_cocina_sound_profile'
COCINA_SOUND_VOLUME_PREF_KEY = 'gastronomia_cocina_sound_volume'

DEFAULT_COCINA_SOUND_SETTINGS = {
    'enabled': True,
    'profile': 'clasico',
    'volume': 65,
}

ALLOWED_COCINA_SOUND_PROFILES = {'clasico', 'suave', 'urgente'}


def get_cocina_sound_settings(user) -> dict:
    enabled_raw = str(user.get_preferencia(COCINA_SOUND_ENABLED_PREF_KEY, '1') or '1').strip().lower()
    profile = str(user.get_preferencia(COCINA_SOUND_PROFILE_PREF_KEY, DEFAULT_COCINA_SOUND_SETTINGS['profile']) or '').strip().lower()
    volume_raw = user.get_preferencia(COCINA_SOUND_VOLUME_PREF_KEY, DEFAULT_COCINA_SOUND_SETTINGS['volume'])
    return {
        'enabled': enabled_raw not in {'0', 'false', 'no', 'off'},
        'profile': profile if profile in ALLOWED_COCINA_SOUND_PROFILES else DEFAULT_COCINA_SOUND_SETTINGS['profile'],
        'volume': _parse_volume(volume_raw),
    }


def save_cocina_sound_settings(user, payload: dict | None) -> dict:
    payload = payload or {}
    current = get_cocina_sound_settings(user)
    enabled = _parse_enabled(payload.get('enabled'), current['enabled'])
    profile = _parse_profile(payload.get('profile'), current['profile'])
    volume = _parse_volume(payload.get('volume'), current['volume'])
    user.set_preferencia(COCINA_SOUND_ENABLED_PREF_KEY, '1' if enabled else '0')
    user.set_preferencia(COCINA_SOUND_PROFILE_PREF_KEY, profile)
    user.set_preferencia(COCINA_SOUND_VOLUME_PREF_KEY, str(volume))
    return {'enabled': enabled, 'profile': profile, 'volume': volume}


def _parse_enabled(value, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'si', 'sí', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    return bool(default)


def _parse_profile(value, default: str) -> str:
    normalized = str(value or default or '').strip().lower()
    return normalized if normalized in ALLOWED_COCINA_SOUND_PROFILES else DEFAULT_COCINA_SOUND_SETTINGS['profile']


def _parse_volume(value, default: int = DEFAULT_COCINA_SOUND_SETTINGS['volume']) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = int(default)
    return max(0, min(100, parsed))
