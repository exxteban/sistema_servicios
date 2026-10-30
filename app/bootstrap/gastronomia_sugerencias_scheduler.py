"""Cálculo diario fuera del POS; cada worker comparte el candado de base."""
import os
import threading
import time

_lock = threading.Lock()
_iniciado = False
DEMORA_INICIAL_SEGUNDOS = 180
INTERVALO_REVISION_SEGUNDOS = 3600


def calcular_pendientes(app):
    from app import db
    from gastronomia.models import GastronomiaClienteConfig
    from gastronomia.services.sugerencias.tarea import recalcular

    with app.app_context():
        try:
            clientes = [fila[0] for fila in db.session.query(GastronomiaClienteConfig.cliente_id)
                        .filter(GastronomiaClienteConfig.gastronomia_activo.is_(True)).all()]
            db.session.rollback()
            for cliente_id in clientes:
                try:
                    if recalcular(cliente_id, solo_si_vencido=True):
                        app.logger.info('[gastronomia] Sugerencias recalculadas: cliente %s', cliente_id)
                except Exception:
                    db.session.rollback()
                    app.logger.exception('[gastronomia] Error calculando sugerencias: cliente %s', cliente_id)
                finally:
                    db.session.remove()
        finally:
            db.session.remove()


def iniciar_scheduler_sugerencias_gastronomia(app):
    global _iniciado
    if os.environ.get('GASTRONOMIA_SUGERENCIAS_CALCULO', '1').strip().lower() in ('0', 'false', 'no', 'off'):
        return
    if app.config.get('TESTING', False):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    with _lock:
        if _iniciado:
            return

        def _loop():
            time.sleep(DEMORA_INICIAL_SEGUNDOS)
            while True:
                try:
                    calcular_pendientes(app)
                except Exception:
                    app.logger.exception('[gastronomia] Error en scheduler de sugerencias')
                time.sleep(INTERVALO_REVISION_SEGUNDOS)

        threading.Thread(target=_loop, name='gastronomia-sugerencias', daemon=True).start()
        _iniciado = True
        app.logger.info('Scheduler de sugerencias gastronómicas iniciado (demora inicial: 180 s)')
