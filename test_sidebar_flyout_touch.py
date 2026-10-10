from pathlib import Path


SHELL = Path("app/templates/layout/app_shell.html")
HEAD = Path("app/templates/layout/head_assets.html")
RUNTIME = Path("app/templates/layout/_tab_link_navigation_js.html")


def test_flyout_max_height_descuenta_la_barra_superior():
    """El menu nace dentro del sidebar (debajo del topbar); si su alto maximo usa
    el viewport completo las primeras opciones quedan tapadas por la barra."""
    css = HEAD.read_text(encoding="utf-8")

    assert (
        "max-height: calc(var(--app-shell-vh) - var(--app-shell-topbar-height) - 1.5rem);"
        in css
    )


def test_position_menu_clampea_dentro_del_area_visible_del_sidebar():
    source = Path("app/static/js/sidebar_menu.js").read_text(encoding="utf-8")

    assert "const sidebarRect = this.$el.getBoundingClientRect();" in source
    assert "const topLimit = Math.max(padding, sidebarRect.top + padding);" in source
    assert "const bottomLimit = viewportHeight - padding;" in source
    assert "menu.offsetHeight" in source
    assert "if (desiredTop < topLimit) {" in source


def test_link_de_tab_no_se_abre_en_pointerdown():
    """En touch el pointerdown puede ser el inicio de un scroll: solo un tap abre."""
    source = RUNTIME.read_text(encoding="utf-8")

    pointerdown_handler = source.split("document.addEventListener('pointerdown'", 1)[1]
    pointerdown_handler = pointerdown_handler.split("}, true);", 1)[0]

    assert "handleAppTabLink" not in pointerdown_handler
    assert "pendingPointer = {" in pointerdown_handler


def test_arrastre_suprime_el_click_posterior():
    source = RUNTIME.read_text(encoding="utf-8")

    assert "const TAP_MOVE_TOLERANCE_PX = 12;" in source
    assert "document.addEventListener('pointercancel', markPointerDragged, true);" in source
    assert "window.addEventListener('scroll', markPointerDragged, true);" in source
    assert "if (link === draggedLink && (Date.now() - draggedAt) < DRAG_SUPPRESS_MS) {" in source
