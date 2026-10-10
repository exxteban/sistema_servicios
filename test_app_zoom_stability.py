from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_layout_carga_zoom_stability_antes_del_viewport_shell():
    layout = _read("app/templates/layout_refactored.html")

    zoom_script = "js/app_zoom_stability.js"
    head_assets = "{% include 'layout/head_assets.html' %}"

    assert zoom_script in layout
    assert layout.index(zoom_script) < layout.index(head_assets)
    assert 'data-app-shell-root="true"' in layout


def test_css_de_zoom_no_reescribe_flujo_del_shell():
    css = _read("app/static/css/app_zoom_stability.css")

    assert "body[data-app-shell-root=\"true\"]::before" in css
    assert "html.dark body.app-shell-body" in css
    assert "overflow: visible !important" not in css
    assert "position: absolute !important" not in css


def test_js_congela_altura_solo_cuando_el_zoom_visual_es_real():
    js = _read("app/static/js/app_zoom_stability.js")

    assert "function markShellRoot()" in js
    assert "document.body.setAttribute('data-app-shell-root', 'true')" in js
    assert "window.__appShellShouldFreezeViewportHeight = function ()" in js
    assert "return getViewportScale() !== 1;" in js


def test_escaneo_de_estilos_solo_corre_con_zoom_real():
    """Pantallas sin zoom (cocina en una TV) no deben observar cada re-render."""
    js = _read("app/static/js/app_zoom_stability.js")

    set_state = js.split("function setZoomState(", 1)[1].split("window.dispatchEvent(", 1)[0]
    assert "initMutationTracking();" in set_state
    assert "stopMutationTracking();" in set_state
    assert "function stopMutationTracking()" in js
    assert "if (zooming) initMutationTracking();" in js
    assert "if (!mutationObserver) return;" in js
