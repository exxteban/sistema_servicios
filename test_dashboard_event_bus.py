from pathlib import Path


HEAD_ASSETS = Path("app/templates/layout/head_assets.html")
EVENT_BUS = Path("app/static/js/dashboard_event_bus.js")


def test_dashboard_event_bus_is_loaded_globally():
    source = HEAD_ASSETS.read_text(encoding="utf-8")

    assert "js/dashboard_event_bus.js" in source


def test_dashboard_event_bus_refreshes_after_relevant_mutations():
    source = EVENT_BUS.read_text(encoding="utf-8")

    assert "dashboard-sync-v1" in source
    assert "BroadcastChannel" in source
    assert "dashboard:refresh-totals" in source
    assert "dashboard:cobros-pendientes-changed" in source
    assert "/^\\/clientes\\/\\d+\\/servicios\\/(?:asignar|\\d+\\/actualizar)$/" in source
    assert "/^\\/agenda\\/turnos\\/peluqueria\\/crear$/" in source
    assert "/^\\/ventas\\/(?:procesar|enviar-a-caja)$/" in source
