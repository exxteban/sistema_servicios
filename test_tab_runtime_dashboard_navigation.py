from pathlib import Path

from tab_runtime_testing import tab_runtime_source


def test_dashboard_reload_forces_principal_tab_after_restoring_saved_tabs():
    source = tab_runtime_source()

    restore_guard = (
        "const currentRequestIsDashboard = isDashboardUrl(window.location.href);"
    )
    force_principal = (
        "if (currentRequestIsDashboard) {\n"
        "                restoreState();\n"
        "                setActiveTab(principalTabId);\n"
        "                saveState();"
    )

    assert restore_guard in source
    assert force_principal in source
    assert source.index(restore_guard) < source.index(force_principal)


def test_dashboard_click_saves_principal_before_full_reload():
    source = tab_runtime_source()

    reload_branch = "if (!principalPanelShowsDashboard()) {"
    save_principal = (
        "setActiveTab(principalTabId);\n"
        "                        saveState();"
    )
    reload_dashboard = "window.location.assign(DASHBOARD_URL);"

    assert reload_branch in source
    assert save_principal in source
    assert reload_dashboard in source
    assert source.index(reload_branch) < source.index(save_principal)
    assert source.index(save_principal) < source.index(reload_dashboard)


def test_volver_al_dashboard_no_recarga_por_la_url_de_otra_pestana():
    """Al activar otra pestana la URL del navegador pasa a ser la suya; volver al
    Dashboard no debe decidir una recarga completa por eso (causaba un pestaneo)."""
    source = tab_runtime_source()
    inicio = source.index("function navigateToDashboard()")
    cuerpo = source[inicio:source.index("if (principalBtn) {", inicio)]

    assert "shouldNavigateToDashboard()" not in cuerpo
    assert "refreshPrincipalDashboardInPlace();" in cuerpo


def test_refresco_silencioso_solo_en_dashboards_que_lo_declaran():
    soft = Path("app/templates/layout/_dashboard_soft_refresh_js.html").read_text(encoding="utf-8")
    servicios = Path("app/templates/dashboard/servicios.html").read_text(encoding="utf-8")
    totales = Path("app/templates/dashboard/_refresh_totals_js.html").read_text(encoding="utf-8")

    assert "{% include 'layout/_dashboard_soft_refresh_js.html' %}" in tab_runtime_source()
    assert 'data-dashboard-soft-refresh="1"' in soft
    assert 'data-dashboard-soft-refresh="1"' in servicios
    # La instancia vieja del script de totales suelta sus listeners al quedar sin DOM.
    assert "function unbind()" in totales
    assert "window.removeEventListener('storage', onStorage);" in totales


def test_dashboard_gastronomia_es_el_dashboard_de_la_pestana_principal():
    """En gastronomia '/' redirige a /gastronomia/: el shell debe tratarlo como el
    dashboard; si no, volver a su pestana hacia una recarga completa (parpadeo)."""
    from app import create_app
    from test_gastronomia_permisos import _crear_cliente_usuario, _loguear

    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_usuario(app, 'admin_tab_dashboard', 'Administrador')
    _loguear(client, app, 'admin_tab_dashboard')

    html = client.get('/gastronomia/').get_data(as_text=True)

    assert 'data-page-is-dashboard="1"' in html
    assert 'const DASHBOARD_URL = "/gastronomia/";' in html
    assert 'data-dashboard-soft-refresh="1"' in html
    assert 'window.initGastroDashboardCardOrder?.();' in html

    partial = client.get('/gastronomia/?partial=1').get_data(as_text=True)
    assert 'id="partial-content"' in partial
    assert 'data-dashboard-soft-refresh="1"' in partial


def test_links_al_dashboard_dentro_de_pestanas_activan_la_principal():
    source = tab_runtime_source()
    assert "isDashboardUrl(linkUrl.toString()) && window.appNavigateToDashboard" in source
    assert "window.appNavigateToDashboard = navigateToDashboard;" in tab_runtime_source()


def test_tarjetas_del_dashboard_gastronomia_abren_en_pestanas():
    """Navegar con recarga completa dejaba el panel principal sin dashboard y volver
    a el obligaba a recargar la pagina."""
    from app import create_app
    from test_gastronomia_permisos import _crear_cliente_usuario, _loguear

    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_usuario(app, 'admin_tab_cards', 'Administrador')
    _loguear(client, app, 'admin_tab_cards')

    html = client.get('/gastronomia/').get_data(as_text=True)

    assert 'class="app-tab-link gastro-dashboard-card' in html
    assert 'data-tab-title="Cocina"' in html
    assert 'data-tab-ignore-click="1"' in html
    assert 'data-tab-title="Cargar menu"' in html


def test_carga_completa_de_otra_pantalla_la_muda_a_su_propia_pestana():
    """El panel principal es del Dashboard y de nadie mas.

    Una carga completa de otra URL (link sin app-tab-link, redirect de POST, F5)
    renderiza esa pantalla dentro del panel principal. Antes se quedaba ahi con la
    pestana rotulada "Dashboard"; ahora se muda a una pestana propia.
    """
    source = tab_runtime_source()

    relocate = (
        "restoreState({ activate: false, skipKey: window.location.href });\n"
        "                const adoptedTabId = relocatePrincipalIntoTab();\n"
        "                if (!adoptedTabId) setActiveTab(principalTabId);"
    )

    assert relocate in source
    assert "openTab(url, title, iconClass, { adoptContent: nodes, activate: true });" in source
    assert "renderDashboardIntoPrincipal();" in source


def test_el_contenido_adoptado_se_mueve_sin_volver_a_pedirlo():
    """Se mueven los nodos ya renderizados: nada de un segundo fetch de la misma URL."""
    source = tab_runtime_source()

    assert "if (!adoptContent) {\n                    (async () => {\n                        await loadContent(url);" in source
    assert "adoptContent.forEach((node) => adoptedDiv.appendChild(node));" in source
    assert "wireTabContent(adoptedDiv);" in source


def test_runtime_de_pestanas_respeta_limite_de_lineas():
    for name in ("part1", "open_tab", "wire_content", "part2", "bootstrap"):
        lines = Path(f"app/templates/layout/tab_runtime_js_{name}.html").read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 600, name
