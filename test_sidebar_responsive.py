from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_refuerzo_responsive_se_carga_despues_de_la_experiencia_base():
    head = _read("app/templates/layout/head_assets.html")

    base = head.index("css/sidebar_experience.css")
    responsive = head.index("css/sidebar_responsive.css")
    assert base < responsive


def test_arranca_colapsada_sin_pisar_preferencia_del_usuario():
    script = _read("app/static/js/sidebar_experience.js")

    assert "if (stored === null) return null;" in script
    assert "function preferredExpandedState()" in script
    # Sin preferencia guardada arranca colapsada, tambien en tablet/touch.
    assert "if (stored !== null) return stored;" in script
    assert "window.matchMedia('(pointer: coarse)')" not in script.split(
        "function preferredExpandedState()")[1].split("}")[0]
    assert "saveExpandedPreference(Boolean(expanded))" in script


def test_drawer_movil_tiene_scroll_seguro_y_respeta_el_area_inferior():
    css = _read("app/static/css/sidebar_responsive.css")

    assert "@media (max-width: 767px)" in css
    assert "overflow-y: auto;" in css
    assert "overscroll-behavior: contain;" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "-webkit-overflow-scrolling: touch;" in css


def test_submenus_moviles_quedan_dentro_del_drawer_y_pueden_cerrarse():
    css = _read("app/static/css/sidebar_responsive.css")
    script = _read("app/static/js/sidebar_experience.js")

    assert ".app-shell-sidebar.is-expanded .app-shell-flyout-menu" in css
    assert "position: static !important;" in css
    assert "position: absolute !important;" in css
    assert "inset: 0 !important;" in css
    assert "z-index: 200 !important;" in css
    assert "background: rgb(17, 24, 39) !important;" in css
    assert "max-height: 100% !important;" in css
    assert "'has-active-menu': activeMenu !== null" in _read("app/templates/layout/app_shell.html")
    assert ".app-shell-sidebar.has-active-menu > *" in css
    assert "visibility: hidden;" in css
    assert "visibility: visible;" in css
    assert "sidebar-mobile-menu-close" in script
    assert "Volver al menú lateral" in script
    assert "sidebar-menu-close-now" in script


def test_volver_del_submenu_permanece_visible_durante_el_scroll():
    css = _read("app/static/css/sidebar_responsive.css")

    assert "position: sticky;" in css
    assert "top: 0;" in css
    assert "trigger.focus({ preventScroll: true })" in _read("app/static/js/sidebar_experience.js")


def test_navegar_desde_el_drawer_movil_solicita_cierre_sin_interferir_con_gestos():
    script = _read("app/static/js/sidebar_experience.js")
    layouts = _read("app/templates/layout.html") + _read("app/templates/layout_refactored.html")

    assert "function setupMobileDrawerAutoClose(sidebar)" in script
    assert "window.addEventListener('click'" in script
    assert "window.addEventListener('pointerdown'" not in script
    assert "event.button !== 0" in script
    assert "sidebar-close-request" in script
    assert layouts.count('@sidebar-close-request.window="sidebarOpen = false"') == 2


def test_objetivos_touch_tienen_al_menos_44_pixeles():
    css = _read("app/static/css/sidebar_responsive.css")

    assert "@media (pointer: coarse), (any-pointer: coarse)" in css
    assert "min-height: 44px;" in css
    assert "min-width: 44px;" in css
    assert "touch-action: manipulation;" in css
    assert ".sidebar-experience-tools" in css
    assert "flex-basis: 44px;" in css


def test_archivos_nuevos_de_experiencia_se_mantienen_modulares():
    for path in (
        "app/static/css/sidebar_experience.css",
        "app/static/css/sidebar_responsive.css",
        "app/static/js/sidebar_experience.js",
    ):
        assert len(_read(path).splitlines()) <= 600, path
