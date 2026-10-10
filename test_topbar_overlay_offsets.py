from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_flash_y_toasts_respetan_altura_real_del_navbar():
    flash = _read("app/templates/layout/flash_overlay_script.html")
    css = _read("app/static/css/app_overlay_offsets.css")
    head = _read("app/templates/layout/head_assets.html")

    dynamic_top = "top: calc(var(--app-shell-topbar-height, 3.5rem) + 0.75rem);"
    available_height = (
        "max-height: calc(var(--app-shell-vh, 100vh) - "
        "var(--app-shell-topbar-height, 3.5rem) - 1.5rem);"
    )

    assert dynamic_top in flash
    assert available_height in flash
    assert dynamic_top in css
    assert available_height in css
    assert "css/app_overlay_offsets.css" in head
    assert "top: 1rem" not in flash


def test_alertas_agenda_son_visibles_y_desplazables_en_mobile():
    css = _read("app/static/css/app_overlay_offsets.css")

    assert "top: calc(var(--app-shell-topbar-height, 3.5rem) + 4.25rem);" in css
    assert "top: max(8rem" not in css
    assert "overscroll-behavior: contain;" in css

