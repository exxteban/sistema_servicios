/*
 * Modal "Teclas rapidas": a cada tecla (F2, F4...) se le asigna una accion del rubro.
 *
 * Se abre con cualquier boton [data-atajos-configurar] o con window.appAbrirTeclasRapidas().
 * Guarda en /api/atajos-teclado y avisa al script de teclas con window.appSetAtajos().
 * Una accion va en una sola tecla: al elegirla en una fila se le saca a la otra.
 */
(function () {
    'use strict';

    if (window.__atajosTecladoModalReady) return;
    window.__atajosTecladoModalReady = true;

    function contexto() {
        return window.__atajosTeclado || { teclas: [], atajos: {}, disponibles: [], defaults: {} };
    }

    function el(tag, attrs, children) {
        const node = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (k === 'text') node.textContent = v;
            else if (k === 'class') node.className = v;
            else node.setAttribute(k, v);
        });
        (children || []).forEach((child) => child && node.appendChild(child));
        return node;
    }

    function opciones(select, disponibles, valor) {
        select.appendChild(el('option', { value: '', text: 'Sin acción' }));
        const grupos = new Map();
        disponibles.forEach((accion) => {
            const nombre = accion.group || 'Otras';
            if (!grupos.has(nombre)) grupos.set(nombre, []);
            grupos.get(nombre).push(accion);
        });
        grupos.forEach((lista, nombre) => {
            const grupo = el('optgroup', { label: nombre });
            lista.forEach((accion) => grupo.appendChild(el('option', { value: accion.id, text: accion.title })));
            select.appendChild(grupo);
        });
        select.value = valor || '';
    }

    function cerrar(modal, anterior) {
        modal.remove();
        document.removeEventListener('keydown', modal.__onKey, true);
        if (anterior && typeof anterior.focus === 'function') anterior.focus();
    }

    function abrir() {
        if (document.querySelector('[data-atajos-modal]')) return;
        const ctx = contexto();
        const teclas = Array.isArray(ctx.teclas) ? ctx.teclas : [];
        const disponibles = Array.isArray(ctx.disponibles) ? ctx.disponibles : [];
        const anterior = document.activeElement;

        const selects = teclas.map((tecla) => {
            const select = el('select', { class: 'atajos-modal__select', 'aria-label': `Acción de la tecla ${tecla}` });
            opciones(select, disponibles, (ctx.atajos || {})[tecla]);
            select.dataset.tecla = tecla;
            return select;
        });
        selects.forEach((select) => select.addEventListener('change', () => {
            if (!select.value) return;
            selects.forEach((otro) => { if (otro !== select && otro.value === select.value) otro.value = ''; });
        }));

        const filas = teclas.map((tecla, i) => el('label', { class: 'atajos-modal__fila' }, [
            el('kbd', { class: 'atajo-kbd atajo-kbd--grande', text: tecla }),
            selects[i],
        ]));

        const error = el('p', { class: 'atajos-modal__error', role: 'alert' });
        error.hidden = true;
        const btnRestablecer = el('button', { type: 'button', class: 'atajos-modal__btn atajos-modal__btn--link', text: 'Volver a las de fábrica' });
        const btnCancelar = el('button', { type: 'button', class: 'atajos-modal__btn', text: 'Cancelar' });
        const btnGuardar = el('button', { type: 'button', class: 'atajos-modal__btn atajos-modal__btn--primario', text: 'Guardar' });

        const panel = el('div', { class: 'atajos-modal__panel', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'atajos-modal-titulo' }, [
            el('div', { class: 'atajos-modal__head' }, [
                el('h2', { id: 'atajos-modal-titulo', class: 'atajos-modal__titulo', text: 'Teclas rápidas' }),
                el('p', { class: 'atajos-modal__sub', text: 'Elegí qué abre cada tecla. Funciona desde cualquier pantalla del sistema.' }),
            ]),
            el('div', { class: 'atajos-modal__body' }, disponibles.length
                ? filas
                : [el('p', { class: 'atajos-modal__sub', text: 'Tu usuario no tiene pantallas para asignar.' })]),
            error,
            el('div', { class: 'atajos-modal__foot' }, [btnRestablecer, el('span', { class: 'atajos-modal__spacer' }), btnCancelar, btnGuardar]),
        ]);
        const modal = el('div', { class: 'atajos-modal', 'data-atajos-modal': '' }, [panel]);

        modal.addEventListener('mousedown', (e) => { if (e.target === modal) cerrar(modal, anterior); });
        btnCancelar.addEventListener('click', () => cerrar(modal, anterior));
        btnRestablecer.addEventListener('click', () => {
            const defaults = ctx.defaults || {};
            selects.forEach((select) => { select.value = defaults[select.dataset.tecla] || ''; });
        });
        btnGuardar.addEventListener('click', async () => {
            const atajos = {};
            selects.forEach((select) => { if (select.value) atajos[select.dataset.tecla] = select.value; });
            btnGuardar.disabled = true;
            error.hidden = true;
            try {
                const res = await fetch(window.__atajosTecladoUrl || '/api/atajos-teclado', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                    body: JSON.stringify({ atajos }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.ok) throw new Error(data.mensaje || 'No se pudo guardar.');
                if (typeof window.appSetAtajos === 'function') window.appSetAtajos(data.atajos);
                cerrar(modal, anterior);
            } catch (e) {
                error.textContent = (e && e.message) || 'No se pudo guardar. Probá de nuevo.';
                error.hidden = false;
                btnGuardar.disabled = false;
            }
        });

        modal.__onKey = (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                cerrar(modal, anterior);
            }
        };
        document.addEventListener('keydown', modal.__onKey, true);
        document.body.appendChild(modal);
        (selects[0] || btnCancelar).focus();
    }

    window.appAbrirTeclasRapidas = abrir;

    document.addEventListener('click', (e) => {
        const boton = e.target.closest && e.target.closest('[data-atajos-configurar]');
        if (!boton) return;
        e.preventDefault();
        abrir();
    });
})();
