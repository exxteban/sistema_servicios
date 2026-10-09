"""Los mensajes del servidor tienen que verse aunque el runtime de tabs cambie de panel.

Dos formas en que se perdían (portado de sistema_silvio_cel):

- En una carga completa de página el flash se renderiza dentro de
  `#app-tab-panel-principal`. Al restaurar las pestañas guardadas ese panel queda
  `hidden` y el mensaje desaparecía sin que el usuario lo leyera.
- Un formulario dentro de una pestaña que guarda y redirige: el fetch sigue el
  redirect y se lleva el flash, y después `loadContent` vuelve a pedir la página
  ya sin él. "Guardar" en Facturación electrónica no mostraba nada.
"""

import unittest
from pathlib import Path


LAYOUT = Path('app/templates/layout_refactored.html')
OVERLAY = Path('app/templates/layout/flash_overlay_script.html')
RECUPERO = Path('app/templates/layout/tab_runtime_flash_recovery.html')
APP_SHELL = Path('app/templates/layout/app_shell.html')
PART1 = Path('app/templates/layout/tab_runtime_js_part1.html')
PART2 = Path('app/templates/layout/tab_runtime_js_part2.html')


class TestFlashOverlay(unittest.TestCase):
    def test_el_layout_incluye_el_rescate_de_flashes(self):
        source = LAYOUT.read_text(encoding='utf-8')
        self.assertIn("{% include 'layout/flash_overlay_script.html' %}", source)
        # El recupero tiene que estar definido antes de que el runtime lo use.
        self.assertLess(
            source.index("{% include 'layout/tab_runtime_flash_recovery.html' %}"),
            source.index("{% include 'layout/tab_runtime_js_part1.html' %}"),
        )

    def test_los_flashes_se_sacan_del_panel_principal(self):
        source = OVERLAY.read_text(encoding='utf-8')
        self.assertIn("getElementById('app-tab-panel-principal')", source)
        self.assertIn("querySelectorAll('.flash-message')", source)
        self.assertIn("document.body.appendChild(stack)", source)

    def test_los_avisos_de_error_no_se_autocierran(self):
        source = OVERLAY.read_text(encoding='utf-8')
        self.assertIn("categoria === 'danger' || categoria === 'warning'", source)

    def test_el_panel_principal_sigue_siendo_el_origen_de_los_flashes(self):
        source = APP_SHELL.read_text(encoding='utf-8')
        panel = source.split('id="app-tab-panel-principal"', 1)[1]
        antes_del_contenido = panel.split('{% block content %}', 1)[0]
        self.assertIn('flash-message', antes_del_contenido)
        self.assertIn('data-flash-category', antes_del_contenido)

    def test_el_redirect_de_un_formulario_recupera_los_flashes(self):
        self.assertIn('window.appInjectFlashesFromHtml = function', RECUPERO.read_text(encoding='utf-8'))
        part1 = PART1.read_text(encoding='utf-8')
        despues_de_recargar = part1.split('await loadContent(response.url);', 1)[1][:300]
        self.assertIn('window.appInjectFlashesFromHtml(panel, rawHtml)', despues_de_recargar)
        # Redirect a una pestaña que ya estaba abierta: formulario y navegación.
        for source in (part1, PART2.read_text(encoding='utf-8')):
            self.assertIn(
                'window.appInjectFlashesFromHtml(tabPanelsById.get(existingId), rawHtml)', source,
            )

    def test_los_templates_compilan(self):
        from app import create_app

        app = create_app('testing')
        for nombre in ('layout_refactored.html', 'layout/flash_overlay_script.html',
                       'layout/tab_runtime_flash_recovery.html'):
            app.jinja_env.get_template(nombre)


if __name__ == '__main__':
    unittest.main()
