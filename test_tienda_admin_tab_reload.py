import re
from pathlib import Path


TIENDA_ADMIN_TEMPLATES = Path("app/templates/tienda_admin")
TAB_RUNTIME_PART1 = Path("app/templates/layout/tab_runtime_js_part1.html")
TAB_RUNTIME_PART2 = Path("app/templates/layout/tab_runtime_js_part2.html")
TIENDA_ADMIN_ROUTE = Path("app/routes/tienda_admin.py")
RELOADABLE_SCRIPT_GUARD = Path("app/templates/layout/reloadable_script_guard.html")
PROMOCIONES_RUNTIME = Path("app/templates/layout/tienda_admin_promociones_runtime.html")


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
            assert re.search(rf"^(?:var {state_name}\b|window\.{state_name}\s*=)", source, flags=re.MULTILINE), (
                template_name,
                state_name,
            )
            assert not re.search(rf"^(?:let|const) {state_name}\b", source, flags=re.MULTILINE), (
                template_name,
                state_name,
            )


def test_tienda_admin_header_buttons_use_single_click_handler():
    panel_source = (TIENDA_ADMIN_TEMPLATES / "panel.html").read_text(encoding="utf-8")
    script_source = (TIENDA_ADMIN_TEMPLATES / "_panel_base_js.html").read_text(encoding="utf-8")

    assert 'onclick="abrirConfiguracion()"' in panel_source
    assert 'onclick="abrirModalEstadisticasTienda()"' in panel_source
    assert "inicializarBotonesCabeceraTienda" not in script_source


def test_tab_runtime_normalizes_stale_reloadable_state_declarations():
    source = TAB_RUNTIME_PART1.read_text(encoding="utf-8")

    assert "normalizeReloadableInlineScript" in source
    assert "isRedeclarationError" in source
    assert "tiendaStatsState" in source
    assert "tiendaAdminAutoBusquedaTimer" in source


def test_tienda_admin_tab_loads_without_cache():
    runtime_source = TAB_RUNTIME_PART2.read_text(encoding="utf-8")
    route_source = TIENDA_ADMIN_ROUTE.read_text(encoding="utf-8")
    search_source = (TIENDA_ADMIN_TEMPLATES / "_panel_base_js.html").read_text(encoding="utf-8")

    assert "cache: 'no-store'" in runtime_source
    assert "cache: 'no-store'" in search_source
    assert "no-store, no-cache, must-revalidate, max-age=0" in route_source


def test_layout_installs_reloadable_script_guard_before_dynamic_tabs():
    guard_source = RELOADABLE_SCRIPT_GUARD.read_text(encoding="utf-8")
    layout_source = Path("app/templates/layout_refactored.html").read_text(encoding="utf-8")

    assert "Node.prototype.appendChild" in guard_source
    assert "tiendaStatsState" in guard_source
    assert "tiendaAdminAutoBusquedaTimer" in guard_source
    assert layout_source.index("reloadable_script_guard.html") < layout_source.index("tab_runtime_js_part1.html")


def test_tienda_admin_partial_does_not_reinject_page_scripts():
    base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
    panel_source = (TIENDA_ADMIN_TEMPLATES / "panel.html").read_text(encoding="utf-8")
    runtime_source = PROMOCIONES_RUNTIME.read_text(encoding="utf-8")
    layout_source = Path("app/templates/layout_refactored.html").read_text(encoding="utf-8")

    assert "request.endpoint != 'tienda_admin.panel'" in base_source
    assert "not request.args.get('partial')" in panel_source
    assert "abrirModalPromocion" in runtime_source
    assert "guardarPromocion" in runtime_source
    assert "tienda_admin_promociones_runtime.html" in layout_source
