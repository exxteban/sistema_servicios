/* Foto corta de lo que el usuario esta viendo al enviar un mensaje al asistente IA.
   Solo nombres de pantalla/subpestana y el plato o insumo abierto: nunca contenido de la pantalla. */
(function () {
    const MAX = 80;

    function texto(el) {
        return el ? (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, MAX) : '';
    }

    function activo(scope, selector) {
        return texto(scope.querySelector(selector + '.activa') || scope.querySelector(selector + '[aria-selected="true"]'));
    }

    function opcionElegida(scope, selector) {
        const select = scope.querySelector(selector);
        if (!select || !select.value || select.selectedIndex < 0) return '';
        return texto(select.options[select.selectedIndex]);
    }

    function pestanasSistema() {
        const botones = Array.from(document.querySelectorAll('.app-tab-btn'));
        const nombre = (b) => texto(b.querySelector('.whitespace-nowrap') || b).replace(/×/g, '').trim();
        const abiertas = Array.from(new Set(botones.map(nombre).filter(Boolean))).slice(0, 8);
        return { abiertas };
    }

    function contextoMenu(scope, ctx) {
        const principal = scope.querySelector('.gastro-main-tab.activa');
        if (!principal) return;
        ctx.subpestana = texto(principal);
        const clave = principal.dataset.mainTab;
        if (clave === 'menu') {
            ctx.seccion = activo(scope, '[data-entry-tab]');
            const form = scope.querySelector('#producto-form');
            const panelProducto = scope.querySelector('[data-entry-tab-panel="producto"]');
            if (form && panelProducto && !panelProducto.classList.contains('hidden')) {
                const id = (form.querySelector('[name="id_producto"]') || {}).value;
                const nombre = ((form.querySelector('[name="nombre"]') || {}).value || '').trim().slice(0, MAX);
                if (nombre) ctx.plato = nombre + (id ? '' : ' (nuevo, sin guardar)');
            }
        } else if (clave === 'menu-cargado') {
            ctx.seccion = activo(scope, '[data-menu-tab]');
        } else if (clave === 'stock') {
            ctx.seccion = activo(scope, '[data-stock-subtab]');
            const plato = opcionElegida(scope, '#stock-recipe-product');
            if (plato) ctx.plato = plato;
            const insumo = opcionElegida(scope, '#stock-insumo-select');
            if (insumo && /insumo/i.test(ctx.seccion || '')) ctx.insumo = insumo;
        }
    }

    function capturar(root) {
        const scope = root.closest('[data-app-tab-content], .app-tab-content')
            || document.querySelector('#app-tab-panels > .app-tab-panel:not([hidden])')
            || document;
        const ctx = { pantalla: (document.title || '').split(' - ')[0].slice(0, MAX) };
        contextoMenu(scope, ctx);
        const sistema = pestanasSistema();
        if (sistema.abiertas.length) ctx.pestanas_abiertas = sistema.abiertas;
        Object.keys(ctx).forEach((k) => { if (!ctx[k]) delete ctx[k]; });
        return ctx;
    }

    window.GastroAsistenteContexto = { capturar };
})();
