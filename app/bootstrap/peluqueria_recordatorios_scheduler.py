"""Job de recordatorios de turnos por WhatsApp (mismo esquema que `fe_scheduler`).

Cada tanto revisa si hay turnos próximos sin recordatorio. Si los recordatorios están
desactivados o WhatsApp no está configurado, `enviar_recordatorios_pendientes` no hace nada.
"""
import os
import threading
import time

_lock = threading.Lock()
_iniciado = False


def _intervalo_segundos():
    try:
        return max(60, int(os.environ.get('PELUQUERIA_RECORDATORIOS_INTERVAL_SECONDS', '300')))
    except Exception:
        return 300


def iniciar_scheduler_recordatorios_peluqueria(app):
    global _iniciado
    if app.config.get('TESTING', False):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    with _lock:
        if _iniciado:
            return
        intervalo = _intervalo_segundos()

        def _loop():
            while True:
                try:
                    with app.app_context():
                        from app.services.peluqueria_recordatorios import enviar_recordatorios_pendientes

                        resumen = enviar_recordatorios_pendientes()
                        if any(resumen.values()):
                            app.logger.info(f'[peluqueria] recordatorios de turnos: {resumen}')
                except Exception:
                    app.logger.exception('Error en scheduler de recordatorios de peluquería')
                time.sleep(intervalo)

        threading.Thread(target=_loop, name='peluqueria-recordatorios', daemon=True).start()
        _iniciado = True
        app.logger.info(f'Scheduler de recordatorios de peluquería iniciado cada {intervalo}s')
