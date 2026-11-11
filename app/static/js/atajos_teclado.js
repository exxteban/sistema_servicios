/*
 * Teclas rapidas (F2, F4, F8, F9, F10) desde cualquier pantalla.
 *
 * - Las teclas y sus pantallas vienen en window.__atajosTeclado (lo pinta el layout
 *   segun el usuario y el rubro: gastronomia o servicios).
 * - window.appSetAtajos(contexto) las cambia en vivo (lo usa el modal "Teclas rapidas"):
 *   el layout no se vuelve a pintar al navegar entre pestanas.
 * - Cualquier boton con data-atajo-accion="<id>" muestra su tecla en un chip; se pinta
 *   tambien en las pestanas que se cargan despues.
 * - El chip de F2 se anima hasta que el usuario usa una tecla por primera vez.
 * - Escucha en captura para que ninguna pantalla se lo trague, y no hace nada con la
 *   tecla mantenida (repeat) ni combinada con Ctrl/Alt/Shift/Meta.
 */
(function () {
    'use strict';

    if (window.__atajosTecladoReady) return;
    window.__atajosTecladoReady = true;

    const USOS_KEY = 'atajos_teclado_usos';
    const TECLA_ANIMADA = 'F2';

    function contexto() {
        const cfg = window.__atajosTeclado;
        return cfg && typeof cfg === 'object' ? cfg : { acciones: [], atajos: {} };
    }

    function acciones() {
        const lista = contexto().acciones;
        return Array.isArray(lista) ? lista : [];
    }

    function teclaDe(accionId) {
        const accion = acciones().find((item) => item && item.id === accionId);
        return accion ? accion.tecla : '';
    }

    function porAprender() {
        return document.documentElement.classList.contains('atajo-por-aprender');
    }

    // Chip de un boton: se crea la primera vez dentro de [data-atajo-slot] (o al final).
    function pintarBoton(el) {
        const tecla = teclaDe(el.getAttribute('data-atajo-accion'));
        let chip = el.querySelector(':scope [data-atajo-chip]');
        if (!tecla) {
            if (chip) chip.hidden = true;
            return;
        }
        if (!chip) {
            chip = document.createElement('kbd');
            chip.className = 'atajo-kbd';
            chip.setAttribute('data-atajo-chip', '');
            (el.querySelector('[data-atajo-slot]') || el).appendChild(chip);
        }
        chip.hidden = false;
        chip.textContent = tecla;
        chip.title = `Atajo: ${tecla} desde cualquier pantalla`;
        chip.toggleAttribute('data-atajo-kbd', tecla === TECLA_ANIMADA);
        if (tecla === TECLA_ANIMADA && porAprender()) observarVisible(chip);
    }

    function pintar(raiz) {
        const base = raiz && raiz.querySelectorAll ? raiz : document;
        if (base.matches && base.matches('[data-atajo-accion]')) pintarBoton(base);
        base.querySelectorAll('[data-atajo-accion]').forEach(pintarBoton);
    }

    // La tecla se anima una vez, cuando se ve entera (el inicio puede quedar abajo).
    const visto = ('IntersectionObserver' in window)
        ? new IntersectionObserver((entradas) => {
            entradas.forEach((entrada) => {
                if (!entrada.isIntersecting) return;
                entrada.target.classList.add('atajo-kbd--anima');
                visto.unobserve(entrada.target);
            });
        }, { threshold: 1 })
        : null;

    function observarVisible(chip) {
        if (visto && !chip.classList.contains('atajo-kbd--anima')) visto.observe(chip);
    }

    function contarUso() {
        try {
            const usos = (parseInt(window.localStorage.getItem(USOS_KEY) || '0', 10) || 0) + 1;
            window.localStorage.setItem(USOS_KEY, String(usos));
        } catch (e) { /* sin storage: no se cuenta */ }
        document.documentElement.classList.remove('atajo-por-aprender');
    }

    window.appSetAtajos = function (nuevo) {
        if (nuevo && Array.isArray(nuevo.acciones)) window.__atajosTeclado = nuevo;
        pintar(document);
    };

    function abrir(accion) {
        contarUso();
        if (typeof window.appOpenTab === 'function') {
            try {
                window.appOpenTab(accion.url, accion.title, accion.icon);
                return;
            } catch (e) { /* cae a navegacion normal */ }
        }
        window.location.href = accion.url;
    }

    document.addEventListener('keydown', (e) => {
        if (!e.key || e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;
        const accion = acciones().find((item) => item && item.tecla === e.key && item.url);
        if (!accion) return;
        e.preventDefault();
        e.stopPropagation();
        // Con el modal de asignar abierto la tecla no navega: se esta configurando.
        if (e.repeat || document.querySelector('[data-atajos-modal]')) return;
        abrir(accion);
    }, true);

    function iniciar() {
        pintar(document);
        if (!('MutationObserver' in window)) return;
        // Alpine pone :data-atajo-accion despues de insertar el nodo: tambien se mira el atributo.
        new MutationObserver((cambios) => {
            cambios.forEach((cambio) => {
                if (cambio.type === 'attributes') {
                    pintarBoton(cambio.target);
                    return;
                }
                cambio.addedNodes.forEach((nodo) => {
                    if (nodo.nodeType === 1) pintar(nodo);
                });
            });
        }).observe(document.body, {
            childList: true, subtree: true, attributes: true, attributeFilter: ['data-atajo-accion'],
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
