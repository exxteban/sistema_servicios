from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import threading

from flask import Flask, current_app
import pytest

from app import db
from app.bootstrap import gastronomia_sugerencias_scheduler as scheduler
from gastronomia.sugerencias_models import GastronomiaSugerenciaCalculo as Estado
from gastronomia.services.sugerencias import tarea
from test_gastronomia_sugerencias import datos  # noqa: F401


@pytest.mark.parametrize('datos', ['archivo'], indirect=True)
def test_dos_workers_solo_uno_calcula(datos, monkeypatch):
    app = current_app._get_current_object()
    cliente = datos[0]
    db.session.remove()
    entro = threading.Event()
    liberar = threading.Event()
    original = tarea.analizar

    def analizar_lento(*args):
        entro.set()
        assert liberar.wait(10)
        return original(*args)

    monkeypatch.setattr(tarea, 'analizar', analizar_lento)

    def ejecutar():
        with app.app_context():
            try:
                return tarea.recalcular(cliente, solo_si_vencido=True)
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        primero = pool.submit(ejecutar)
        try:
            assert entro.wait(10)
            assert pool.submit(ejecutar).result(timeout=10) is False
        finally:
            liberar.set()
        assert primero.result(timeout=10) is True
    # Una vez finalizado, otro worker tampoco repite el cálculo del día.
    assert ejecutar() is False


def test_vencimiento_y_frecuencia(datos):
    cliente = datos[0]
    ahora = datetime.utcnow()
    assert tarea.recalcular(cliente, ahora, solo_si_vencido=True)
    assert tarea.recalcular(cliente, ahora + timedelta(hours=23), solo_si_vencido=True) is False
    assert tarea.recalcular(cliente, ahora + timedelta(hours=24), solo_si_vencido=True)
    estado = Estado.query.filter_by(cliente_id=cliente).one()
    estado.token = 'worker-caido'
    estado.inicio = ahora - timedelta(hours=3)
    db.session.commit()
    assert tarea.recalcular(cliente, ahora)


def test_worker_con_token_reemplazado_no_publica(datos, monkeypatch):
    cliente = datos[0]
    original = tarea.analizar

    def reemplazar_token(*args):
        resultado = original(*args)
        Estado.query.filter_by(cliente_id=cliente).update({'token': 'nuevo-worker'})
        db.session.commit()
        return resultado

    monkeypatch.setattr(tarea, 'analizar', reemplazar_token)
    assert tarea.recalcular(cliente) is False
    estado = Estado.query.filter_by(cliente_id=cliente).one()
    assert estado.token == 'nuevo-worker'
    assert estado.fin is None


@pytest.mark.parametrize('bloqueo', ['testing', 'env', 'reloader'])
def test_scheduler_no_arranca_cuando_corresponde(monkeypatch, bloqueo):
    app = Flask(__name__)
    monkeypatch.setattr(scheduler, '_iniciado', False)
    monkeypatch.delenv('GASTRONOMIA_SUGERENCIAS_CALCULO', raising=False)
    if bloqueo == 'testing':
        app.config['TESTING'] = True
    elif bloqueo == 'env':
        monkeypatch.setenv('GASTRONOMIA_SUGERENCIAS_CALCULO', '0')
    else:
        app.debug = True
        monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    def inesperado(*args, **kwargs):
        pytest.fail('No debe crear un hilo')
    monkeypatch.setattr(scheduler.threading, 'Thread', inesperado)
    scheduler.iniciar_scheduler_sugerencias_gastronomia(app)


def test_scheduler_hilo_unico_y_demora_inicial(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(scheduler, '_iniciado', False)
    monkeypatch.setenv('GASTRONOMIA_SUGERENCIAS_CALCULO', '1')
    hilos = []
    class Hilo:
        def __init__(self, **kwargs):
            hilos.append(kwargs)
        def start(self):
            pass
    monkeypatch.setattr(scheduler.threading, 'Thread', Hilo)
    scheduler.iniciar_scheduler_sugerencias_gastronomia(app)
    scheduler.iniciar_scheduler_sugerencias_gastronomia(app)
    assert len(hilos) == 1
    assert hilos[0]['daemon'] is True
    demoras = []
    class Detener(Exception):
        pass
    def dormir(segundos):
        demoras.append(segundos)
        if len(demoras) == 2:
            raise Detener()
    calculos = []
    monkeypatch.setattr(scheduler.time, 'sleep', dormir)
    monkeypatch.setattr(scheduler, 'calcular_pendientes', lambda app: calculos.append(app))
    with pytest.raises(Detener):
        hilos[0]['target']()
    assert demoras == [180, 3600]
    assert calculos == [app]


def test_scheduler_fallo_de_cliente_no_detiene_otros(datos, monkeypatch):
    from app.models import Cliente
    from gastronomia.models import GastronomiaClienteConfig
    otro = Cliente(nombre='Otro', ruc_ci='scheduler-otro')
    db.session.add(otro)
    db.session.flush()
    db.session.add(GastronomiaClienteConfig(cliente_id=otro.id_cliente, gastronomia_activo=True))
    db.session.commit()
    llamadas = []
    def calcular(cliente_id, **kwargs):
        llamadas.append(cliente_id)
        if cliente_id == datos[0]:
            raise RuntimeError('fallo simulado')
        assert kwargs == {'solo_si_vencido': True}
        return True
    monkeypatch.setattr(tarea, 'recalcular', calcular)
    scheduler.calcular_pendientes(current_app._get_current_object())
    assert set(llamadas) == {datos[0], otro.id_cliente}
