"""Solicitud manual fuera del request; comparte el candado persistente del scheduler."""
import threading

_lock = threading.Lock()
_pendientes = set()


def solicitar(app, cliente_id):
    with _lock:
        if cliente_id in _pendientes:
            return False
        _pendientes.add(cliente_id)

    def ejecutar():
        from app import db
        from gastronomia.services.sugerencias.tarea import recalcular
        try:
            with app.app_context():
                try:
                    recalcular(cliente_id)
                except Exception:
                    app.logger.exception('[gastronomia] Falló el recálculo manual de sugerencias')
                finally:
                    db.session.remove()
        finally:
            with _lock:
                _pendientes.discard(cliente_id)
    try:
        threading.Thread(target=ejecutar, name='gastro-sugerencias-manual', daemon=True).start()
    except Exception:
        with _lock:
            _pendientes.discard(cliente_id)
        raise
    return True
