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

    reload_branch = (
        "if (!principalPanelShowsDashboard() || shouldNavigateToDashboard()) {"
    )
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
