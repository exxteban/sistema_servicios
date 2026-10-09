"""Job de envio automatico de facturacion electronica (igual que en el sistema padre).

Avanza los documentos pendientes (firmar -> QR -> enviar -> consultar) sin que
nadie tenga que entrar a una pantalla, y renueva la tabla geografica del modo
API cuando vence (ver `facturacion_electronica.services.tareas_periodicas`). Si la configuracion de FE esta
incompleta, `procesar_pendientes` no hace nada.
"""
import os
import threading
import time

_fe_scheduler_lock = threading.Lock()
_fe_scheduler_started = False


def _intervalo_segundos():
    try:
        return max(30, int(os.environ.get('FACTURACION_ELECTRONICA_INTERVAL_SECONDS', '300')))
    except Exception:
        return 300


def iniciar_scheduler_facturacion_electronica(app, habilitado):
    global _fe_scheduler_started
    if not habilitado or app.config.get('TESTING', False):
        return
    is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if app.debug and not is_reloader_child:
        return

    with _fe_scheduler_lock:
        if _fe_scheduler_started:
            return
        intervalo = _intervalo_segundos()

        def _fe_envio_loop():
            while True:
                try:
                    with app.app_context():
                        from facturacion_electronica.services.tareas_periodicas import ejecutar

                        resumen = ejecutar()
                        if resumen['procesados']:
                            app.logger.info(f"[facturacion_electronica] pendientes procesados: {resumen}")
                except Exception:
                    app.logger.exception('Error en scheduler de envio de facturacion electronica')
                time.sleep(intervalo)

        threading.Thread(target=_fe_envio_loop, name='fe-envio-scheduler', daemon=True).start()
        _fe_scheduler_started = True
        app.logger.info(f"Scheduler de envio de facturacion electronica iniciado cada {intervalo}s")
