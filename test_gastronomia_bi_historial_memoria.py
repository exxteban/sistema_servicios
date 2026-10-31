"""El historial de clientes se calcula una vez por solicitud y nunca se comparte entre solicitudes."""
from app import create_app
from gastronomia.services.bi import historial


def test_historial_se_calcula_una_vez_por_solicitud(monkeypatch):
    app = create_app('testing')
    llamadas = []
    monkeypatch.setattr(historial, '_calcular_historial', lambda cliente_id: llamadas.append(cliente_id) or {})

    with app.test_request_context('/'):
        historial.historial_clientes(7)
        historial.historial_clientes(7)
        historial.historial_clientes(8)
    assert llamadas == [7, 8]

    with app.test_request_context('/'):
        historial.historial_clientes(7)
    assert llamadas == [7, 8, 7]


def test_fuera_de_una_solicitud_no_guarda_memoria(monkeypatch):
    app = create_app('testing')
    llamadas = []
    monkeypatch.setattr(historial, '_calcular_historial', lambda cliente_id: llamadas.append(cliente_id) or {})
    with app.app_context():
        historial.historial_clientes(7)
        historial.historial_clientes(7)
    assert llamadas == [7, 7]
