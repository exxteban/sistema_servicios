import re
from pathlib import Path


TIENDA_ADMIN_TEMPLATES = Path("app/templates/tienda_admin")


def test_tienda_admin_scripts_allow_tab_runtime_reload():
    reloadable_state = {
        "_panel_base_js.html": (
            "tiendaAdminAutoBusquedaTimer",
            "tiendaAdminUltimaBusqueda",
            "tiendaAdminBusquedaController",
        ),
        "_panel_media_js.html": (
            "productoActualImagenes",
            "imagenProductoPendiente",
            "productoActualOferta",
            "estadoActualOferta",
        ),
        "_panel_promociones_js.html": (
            "promocionProductosSeleccionados",
            "promocionBusquedaTimer",
        ),
        "_estadisticas_tienda_js.html": ("tiendaDashboardStatsState",),
        "_estadisticas_producto.html": ("tiendaStatsState",),
    }

    for template_name, state_names in reloadable_state.items():
        source = (TIENDA_ADMIN_TEMPLATES / template_name).read_text(encoding="utf-8")
        for state_name in state_names:
            assert re.search(rf"^var {state_name}\b", source, flags=re.MULTILINE), (
                template_name,
                state_name,
            )


def test_tienda_admin_header_buttons_use_single_click_handler():
    panel_source = (TIENDA_ADMIN_TEMPLATES / "panel.html").read_text(encoding="utf-8")
    script_source = (TIENDA_ADMIN_TEMPLATES / "_panel_base_js.html").read_text(encoding="utf-8")

    assert 'onclick="abrirConfiguracion()"' in panel_source
    assert 'onclick="abrirModalEstadisticasTienda()"' in panel_source
    assert "inicializarBotonesCabeceraTienda" not in script_source
