from __future__ import annotations

import time

try:
    from flask_caching import Cache as BaseCache
except Exception:
    class BaseCache:  # pragma: no cover - fallback solo para entornos sin dependencia instalada
        def __init__(self):
            self._store = {}

        def init_app(self, app, config=None):
            if config:
                app.config.update(config)

        def cached(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def memoize(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def get(self, *args, **kwargs):
            key = args[0] if args else None
            if key is None:
                return None
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at is not None and expires_at <= time.time():
                self._store.pop(key, None)
                return None
            return value

        def set(self, *args, **kwargs):
            if not args:
                return False
            key = args[0]
            value = args[1] if len(args) > 1 else None
            timeout = kwargs.get('timeout')
            if timeout is None and len(args) > 2:
                timeout = args[2]
            expires_at = None if not timeout else (time.time() + float(timeout))
            self._store[key] = (expires_at, value)
            return True

        def delete(self, *args, **kwargs):
            key = args[0] if args else None
            if key is None:
                return False
            return self._store.pop(key, None) is not None


cache = BaseCache()
