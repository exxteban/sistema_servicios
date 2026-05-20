(function () {
    if (window.__dailyInsightsWidgetInit) return;
    window.__dailyInsightsWidgetInit = true;

    const cfg = window.__dailyInsightsConfig || {};
    const state = { payload: null, open: false };

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function todayPokeKey(fecha) {
        return `daily-insights-poked:${fecha || 'today'}`;
    }

    function dismissKey(fecha) {
        return `daily-insights-dismissed:${fecha || 'today'}`;
    }

    function isDismissed(payload) {
        try {
            return localStorage.getItem(dismissKey(payload && payload.fecha)) === '1';
        } catch {
            return false;
        }
    }

    function hideForToday(event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        if (state.payload) {
            try {
                localStorage.setItem(dismissKey(state.payload.fecha), '1');
            } catch { }
            markSeen(state.payload);
        }
        const host = document.querySelector('[data-daily-insights-host]');
        if (host) {
            host.classList.add('is-dismissed');
            host.setAttribute('aria-hidden', 'true');
            host.style.display = 'none';
        }
    }

    function sourceLabel(insight) {
        const tool = insight && insight.source_tool ? String(insight.source_tool) : 'tool interna';
        return tool.replaceAll('_', ' ');
    }

    function buildCard(insight) {
        const link = insight && insight.enlace ? insight.enlace : null;
        const href = link && link.url ? String(link.url) : '';
        const card = el(href ? 'a' : 'article', 'daily-insight-card');
        if (href) {
            card.href = href;
            card.classList.add('daily-insight-card--clickable', 'app-tab-link');
            card.setAttribute('data-tab-url', href);
            card.setAttribute('data-tab-title', link.tab_title || insight.titulo || 'Insight');
            card.setAttribute('data-tab-icon', link.tab_icon || 'fas fa-lightbulb');
            card.setAttribute('aria-label', `${insight.titulo || 'Insight'}: ${link.label || 'Ver detalle'}`);
            card.addEventListener('click', () => closePanel());
        }
        const header = el('div', 'daily-insight-card__header');
        const icon = el('span', 'daily-insight-card__icon');
        icon.innerHTML = '<i class="fas fa-lightbulb"></i>';
        const title = el('h3', 'daily-insight-card__title', insight.titulo || 'Insight');
        const source = el('span', 'daily-insight-card__source', sourceLabel(insight));
        header.append(icon, title);
        card.append(header);
        card.appendChild(el('p', 'daily-insight-card__text', insight.texto || ''));
        if (insight.accion_sugerida) {
            card.appendChild(el('p', 'daily-insight-card__action', insight.accion_sugerida));
        }
        if (href) {
            const cta = el('span', 'daily-insight-card__cta');
            cta.appendChild(el('span', '', link.label || 'Ver detalle'));
            const arrow = el('i', 'fas fa-arrow-right');
            arrow.setAttribute('aria-hidden', 'true');
            cta.appendChild(arrow);
            card.appendChild(cta);
        }
        card.appendChild(source);
        return card;
    }

    function markSeen(payload) {
        if (!cfg.seenUrl || !payload || payload.visto) return;
        fetch(cfg.seenUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({ fecha: payload.fecha })
        }).then(() => {
            payload.visto = true;
            payload.pendientes = 0;
            updateBadge();
        }).catch(() => { });
    }

    function updateBadge() {
        const badge = document.querySelector('[data-daily-insights-badge]');
        const button = document.querySelector('[data-daily-insights-button]');
        if (!badge || !button) return;
        const pending = Number(state.payload && state.payload.pendientes || 0);
        badge.hidden = pending <= 0;
        badge.textContent = pending > 9 ? '9+' : String(pending);
        button.classList.toggle('has-pending', pending > 0);
    }

    function renderPanel() {
        const panel = document.querySelector('[data-daily-insights-panel]');
        if (!panel || !state.payload) return;
        const insights = Array.isArray(state.payload.insights) ? state.payload.insights : [];
        panel.innerHTML = '';

        const head = el('div', 'daily-insights-panel__head');
        const titleWrap = el('div');
        titleWrap.appendChild(el('p', 'daily-insights-panel__eyebrow', 'Insights de hoy'));
        titleWrap.appendChild(el('h2', 'daily-insights-panel__title', 'Lectura rapida del negocio'));
        const close = el('button', 'daily-insights-panel__close');
        close.type = 'button';
        close.setAttribute('aria-label', 'Cerrar panel de insights');
        close.innerHTML = '&times;';
        close.addEventListener('click', closePanel);
        head.append(titleWrap, close);
        panel.appendChild(head);

        const list = el('div', 'daily-insights-panel__list');
        insights.forEach((insight) => list.appendChild(buildCard(insight)));
        panel.appendChild(list);

        const footer = el('div', 'daily-insights-panel__footer');
        footer.appendChild(el('span', '', `Datos: ${(state.payload.tools_usadas || []).length} tools`));
        const dismiss = el('button', 'daily-insights-panel__dismiss', 'Cerrar por hoy');
        dismiss.type = 'button';
        dismiss.addEventListener('click', hideForToday);
        const chat = el('a', 'daily-insights-panel__chat', 'Abrir asistente');
        chat.href = cfg.chatUrl || '/asistente-ia/';
        chat.setAttribute('data-tab-url', chat.href);
        chat.setAttribute('data-tab-title', 'Asistente IA');
        chat.setAttribute('data-tab-icon', 'fas fa-robot');
        chat.classList.add('app-tab-link');
        footer.appendChild(dismiss);
        footer.appendChild(chat);
        panel.appendChild(footer);
    }

    function openPanel() {
        state.open = true;
        const host = document.querySelector('[data-daily-insights-host]');
        if (!host) return;
        host.classList.add('is-open');
        renderPanel();
        markSeen(state.payload);
    }

    function closePanel() {
        state.open = false;
        const host = document.querySelector('[data-daily-insights-host]');
        if (host) host.classList.remove('is-open');
    }

    function buildShell() {
        const host = el('div', 'daily-insights-widget');
        host.dataset.dailyInsightsHost = '1';
        const panel = el('section', 'daily-insights-panel');
        panel.dataset.dailyInsightsPanel = '1';
        const button = el('button', 'daily-insights-button');
        button.type = 'button';
        button.dataset.dailyInsightsButton = '1';
        button.title = 'Insights diarios';
        button.setAttribute('aria-label', 'Abrir insights diarios');
        button.innerHTML = '<i class="fas fa-lightbulb"></i><span data-daily-insights-badge hidden></span>';
        button.addEventListener('click', () => state.open ? closePanel() : openPanel());
        const dismissButton = el('button', 'daily-insights-hide');
        dismissButton.type = 'button';
        dismissButton.title = 'Cerrar insights por hoy';
        dismissButton.setAttribute('aria-label', 'Cerrar insights por hoy');
        dismissButton.innerHTML = '&times;';
        dismissButton.addEventListener('click', hideForToday);
        host.append(panel, button, dismissButton);
        document.body.appendChild(host);
    }

    function maybePoke(payload) {
        const pending = Number(payload && payload.pendientes || 0);
        if (pending <= 0) return;
        const key = todayPokeKey(payload.fecha);
        try {
            if (localStorage.getItem(key) === '1') return;
            localStorage.setItem(key, '1');
        } catch { }
        const button = document.querySelector('[data-daily-insights-button]');
        if (!button) return;
        button.classList.add('is-poking');
        window.setTimeout(() => button.classList.remove('is-poking'), 5000);
        if (window.mostrarNotificacion) {
            window.mostrarNotificacion('Hay insights nuevos del negocio para mirar.', 'info');
        }
    }

    function loadInsights() {
        if (!cfg.url) return;
        let url = cfg.url;
        if (cfg.preview) {
            const sep = url.includes('?') ? '&' : '?';
            url = `${url}${sep}preview=1`;
        }
        fetch(url, { headers: { 'Accept': 'application/json' } })
            .then((response) => response.ok ? response.json() : null)
            .then((payload) => {
                if (!payload || !payload.ok) return;
                state.payload = payload;
                const host = document.querySelector('[data-daily-insights-host]');
                if (host && isDismissed(payload)) {
                    host.classList.add('is-dismissed');
                    host.setAttribute('aria-hidden', 'true');
                    host.style.display = 'none';
                    return;
                }
                updateBadge();
                maybePoke(payload);
            })
            .catch(() => { });
    }

    function init() {
        if (!document.body) return;
        buildShell();
        loadInsights();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
