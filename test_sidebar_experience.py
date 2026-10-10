from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_layout_carga_la_experiencia_del_sidebar():
    head = _read("app/templates/layout/head_assets.html")

    assert "css/sidebar_experience.css" in head
    assert "css/sidebar_responsive.css" in head
    assert "js/sidebar_experience.js" in head


def test_todos_los_grupos_principales_tienen_nombre_accesible():
    source = "".join(
        _read(f"app/templates/layout/{name}")
        for name in (
            "app_shell.html",
            "_sales_menu.html",
            "_financial_menu.html",
            "_sidebar_management_menus.html",
        )
    )

    expected = {
        "ventas": "Ventas",
        "finanzas": "Finanzas",
        "whatsapp": "WhatsApp",
        "inventario": "Inventario",
        "directorio": "Directorio",
        "sistema": "Sistema",
    }
    for trigger, label in expected.items():
        marker = f'data-sidebar-trigger="{trigger}"'
        block = source[source.index(marker): source.index(marker) + 700]
        assert f'aria-label="{label}"' in block
        assert f"""aria-controls="sidebar-menu-{trigger}\"""" in block


def test_menus_laterales_se_abren_por_toque_y_no_por_hover():
    """En touch el mouseenter emulado abria el menu y el click lo volvia a cerrar."""
    for name in (
        "app_shell.html",
        "_sales_menu.html",
        "_financial_menu.html",
        "_sidebar_management_menus.html",
    ):
        source = _read(f"app/templates/layout/{name}")
        assert "sidebar-menu-open" not in source, name
        assert "sidebar-menu-close'" not in source, name


def test_app_shell_respeta_limite_de_lineas():
    for name in (
        "app_shell.html",
        "_sales_menu.html",
        "_sidebar_notifications_js.html",
        "_sidebar_management_menus.html",
        "_tab_link_navigation_js.html",
        "tab_runtime_js_part2.html",
        "head_assets.html",
    ):
        assert len(_read(f"app/templates/layout/{name}").splitlines()) <= 600, name


def test_expansion_persistente_y_movimiento_reducido():
    script = _read("app/static/js/sidebar_experience.js")
    css = _read("app/static/css/sidebar_experience.css")

    assert "app-sidebar-expanded" in script
    assert "desktop ? Boolean(expanded) : true" in script
    assert "preferredExpandedState()" in script
    assert "aria-expanded" in script
    assert "prefers-reduced-motion: reduce" in css
    assert ".app-shell-sidebar.is-expanded" in css
    assert "data-tooltip" in script
    assert "border-radius: 999px" in css
    assert "right: -1.05rem" not in css


def test_favoritos_personalizables_reutilizan_enlaces_autorizados():
    script = _read("app/static/js/sidebar_experience.js")
    shell = _read("app/templates/layout/app_shell.html")

    for title in ("POS", "Productos", "Compras", "Caja"):
        assert f"sourceTitle: '{title}'" in script
    assert "availableFavoriteDestinations(sidebar)" in script
    assert "copyNavigationAttributes(destination.source, link)" in script
    assert "app-sidebar-favorites:${userId}" in script
    assert "saveFavoriteIds(sidebar, selectedIds)" in script
    assert "Personalizar favoritos" in script
    assert "Restablecer" in script
    assert "home.insertAdjacentElement('beforebegin', section)" in script
    assert "ensureFavorites(sidebar)" in script
    assert "alpine:initialized" in script
    assert "if (!destinations.length) return false" in script
    assert 'data-sidebar-user-id="{{ current_user.id_usuario }}"' in shell


def test_seccion_actual_se_sincroniza_con_url_y_pestana_activa():
    script = _read("app/static/js/sidebar_experience.js")
    css = _read("app/static/css/sidebar_experience.css")

    assert "selectedTabTitle()" in script
    assert "normalizeUrl" in script
    assert "aria-current" in script
    assert "is-current-section" in script
    assert ".sidebar-link.is-current-section" in css
