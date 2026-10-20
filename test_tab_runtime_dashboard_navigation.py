from pathlib import Path


RUNTIME = Path("app/templates/layout/tab_runtime_js_part2.html")


def test_dashboard_reload_forces_principal_tab_after_restoring_saved_tabs():
    source = RUNTIME.read_text(encoding="utf-8")

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
    source = RUNTIME.read_text(encoding="utf-8")

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
    source = RUNTIME.read_text(encoding="utf-8")
    inicio = source.index("function navigateToDashboard()")
    cuerpo = source[inicio:source.index("if (principalBtn) {", inicio)]

    assert "shouldNavigateToDashboard()" not in cuerpo
    assert "refreshPrincipalDashboardInPlace();" in cuerpo


def test_refresco_silencioso_solo_en_dashboards_que_lo_declaran():
    soft = Path("app/templates/layout/_dashboard_soft_refresh_js.html").read_text(encoding="utf-8")
    servicios = Path("app/templates/dashboard/servicios.html").read_text(encoding="utf-8")
    totales = Path("app/templates/dashboard/_refresh_totals_js.html").read_text(encoding="utf-8")

    assert "{% include 'layout/_dashboard_soft_refresh_js.html' %}" in RUNTIME.read_text(encoding="utf-8")
    assert 'data-dashboard-soft-refresh="1"' in soft
    assert 'data-dashboard-soft-refresh="1"' in servicios
    # La instancia vieja del script de totales suelta sus listeners al quedar sin DOM.
    assert "function unbind()" in totales
    assert "window.removeEventListener('storage', onStorage);" in totales
