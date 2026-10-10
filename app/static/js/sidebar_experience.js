(function () {
    'use strict';

    const EXPANDED_STORAGE_KEY = 'app-sidebar-expanded';
    const DEFAULT_FAVORITES = [
        { sourceTitle: 'POS', label: 'Nueva venta', icon: 'fas fa-plus' },
        { sourceTitle: 'Productos', label: 'Productos', icon: 'fas fa-box' },
        { sourceTitle: 'Compras', label: 'Compras', icon: 'fas fa-truck' },
        { sourceTitle: 'Caja', label: 'Caja', icon: 'fas fa-wallet' }
    ];

    function normalizeText(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .trim()
            .toLowerCase();
    }

    function normalizeUrl(value) {
        try {
            const url = new URL(value, window.location.origin);
            const path = url.pathname.replace(/\/+$/, '') || '/';
            return `${path}${url.search}`;
        } catch (_) {
            return String(value || '').replace(/\/+$/, '') || '/';
        }
    }

    function sidebarTemplates(sidebar) {
        return Array.from(sidebar.querySelectorAll('template'));
    }

    function navigationLinks(sidebar) {
        const links = Array.from(sidebar.querySelectorAll('a[href], a[data-tab-url]'));
        sidebarTemplates(sidebar).forEach((template) => {
            links.push(...template.content.querySelectorAll('a[href], a[data-tab-url]'));
        });
        return links;
    }

    function rootLinks(sidebar) {
        const links = [];
        Array.from(sidebar.children).forEach((child) => {
            if (child.matches && child.matches('.sidebar-link')) {
                links.push(child);
                return;
            }
            if (!child.querySelector) return;
            const link = child.querySelector(':scope > .sidebar-link');
            if (link) links.push(link);
        });
        return links;
    }

    function labelForRoot(link) {
        return String(
            link.getAttribute('aria-label')
            || link.getAttribute('data-tab-title')
            || link.getAttribute('title')
            || ''
        ).trim();
    }

    function enhanceRootLinks(sidebar) {
        rootLinks(sidebar).forEach((link) => {
            const label = labelForRoot(link);
            if (!label) return;

            link.setAttribute('aria-label', label);
            link.setAttribute('title', label);
            link.querySelectorAll(':scope > i').forEach((icon) => icon.setAttribute('aria-hidden', 'true'));

            const legacyTooltip = Array.from(link.children).find((child) => (
                child.tagName === 'SPAN'
                && child.classList.contains('absolute')
                && child.classList.contains('left-full')
            ));
            if (legacyTooltip) legacyTooltip.classList.add('sidebar-legacy-tooltip');

            if (link.querySelector(':scope > .sidebar-item-label')) return;
            const labelNode = document.createElement('span');
            labelNode.className = 'sidebar-item-label';
            labelNode.setAttribute('aria-hidden', 'true');
            labelNode.textContent = label;
            link.appendChild(labelNode);
        });
    }

    function readExpandedPreference() {
        try {
            const stored = window.localStorage.getItem(EXPANDED_STORAGE_KEY);
            if (stored === null) return null;
            return stored === 'true';
        } catch (_) {
            return null;
        }
    }

    function preferredExpandedState() {
        const stored = readExpandedPreference();
        if (stored !== null) return stored;
        // Sin preferencia guardada arranca colapsada en escritorio y tablet;
        // en movil el drawer siempre se muestra expandido (ver setExpanded).
        return false;
    }

    function saveExpandedPreference(expanded) {
        try {
            window.localStorage.setItem(EXPANDED_STORAGE_KEY, String(expanded));
        } catch (_) {
        }
    }

    function setExpanded(sidebar, button, expanded, persist) {
        const desktop = window.matchMedia('(min-width: 768px)').matches;
        // En móvil funciona como drawer descriptivo: siempre muestra icono + nombre.
        const next = desktop ? Boolean(expanded) : true;
        sidebar.classList.toggle('is-expanded', next);
        button.setAttribute('aria-expanded', String(next));
        button.setAttribute('aria-label', next ? 'Contraer menú lateral' : 'Expandir menú lateral');
        button.setAttribute('title', next ? 'Contraer menú' : 'Expandir menú');
        button.setAttribute('data-tooltip', next ? 'Contraer menú' : 'Expandir menú');
        if (persist) saveExpandedPreference(Boolean(expanded));
    }

    function createExpansionControl(sidebar) {
        const tools = document.createElement('div');
        tools.className = 'sidebar-experience-tools';

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'sidebar-expand-toggle';
        button.innerHTML = '<i class="fas fa-chevron-right" aria-hidden="true"></i>';
        button.addEventListener('click', () => {
            setExpanded(sidebar, button, !sidebar.classList.contains('is-expanded'), true);
        });

        tools.appendChild(button);
        sidebar.prepend(tools);
        setExpanded(sidebar, button, preferredExpandedState(), false);

        window.addEventListener('resize', () => {
            setExpanded(sidebar, button, preferredExpandedState(), false);
        }, { passive: true });
    }

    function enhanceMobileMenus(sidebar) {
        sidebar.querySelectorAll('[data-sidebar-menu]').forEach((menu) => {
            if (menu.querySelector(':scope > .sidebar-mobile-menu-close')) return;

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'sidebar-mobile-menu-close';
            button.setAttribute('data-tab-ignore-click', '1');
            button.setAttribute('aria-label', 'Volver al menú lateral');
            button.innerHTML = '<i class="fas fa-arrow-left" aria-hidden="true"></i><span>Volver al menú</span>';
            button.addEventListener('click', () => {
                const name = menu.getAttribute('data-sidebar-menu');
                if (!name) return;
                const trigger = sidebar.querySelector(`[data-sidebar-trigger="${name}"]`);
                menu.dispatchEvent(new CustomEvent('sidebar-menu-close-now', {
                    detail: { name },
                    bubbles: true
                }));
                window.requestAnimationFrame(() => {
                    if (trigger) trigger.focus({ preventScroll: true });
                });
            });
            menu.prepend(button);
            if (window.matchMedia('(max-width: 767px)').matches) {
                window.requestAnimationFrame(() => button.focus({ preventScroll: true }));
            }
        });
    }

    function setupMobileDrawerAutoClose(sidebar) {
        window.addEventListener('click', (event) => {
            if (!window.matchMedia('(max-width: 767px)').matches) return;
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

            const target = event.target instanceof Element ? event.target : null;
            const link = target ? target.closest('a') : null;
            if (!link || !sidebar.contains(link)) return;
            if (link.id !== 'sidebar-home-link' && !link.classList.contains('app-tab-link')) return;
            if (link.getAttribute('target') === '_blank') return;
            if (!link.getAttribute('href') && !link.getAttribute('data-tab-url')) return;

            window.dispatchEvent(new CustomEvent('sidebar-close-request'));
        }, true);
    }

    function copyNavigationAttributes(source, target) {
        Array.from(source.attributes).forEach((attribute) => {
            if (attribute.name === 'class' || attribute.name === 'aria-current') return;
            target.setAttribute(attribute.name, attribute.value);
        });
    }

    function favoriteDestination(link) {
        const sourceTitle = String(link.getAttribute('data-tab-title') || '').trim();
        const rawUrl = link.getAttribute('data-tab-url') || link.getAttribute('href');
        if (!sourceTitle || !rawUrl || link.classList.contains('sidebar-favorite-link')) return null;

        const preset = DEFAULT_FAVORITES.find((favorite) => (
            normalizeText(favorite.sourceTitle) === normalizeText(sourceTitle)
        ));
        return {
            id: normalizeUrl(rawUrl),
            sourceTitle,
            label: preset ? preset.label : sourceTitle,
            icon: preset ? preset.icon : (link.getAttribute('data-tab-icon') || 'fas fa-star'),
            source: link
        };
    }

    function availableFavoriteDestinations(sidebar) {
        const byId = new Map();
        navigationLinks(sidebar).forEach((link) => {
            const destination = favoriteDestination(link);
            if (destination && !byId.has(destination.id)) byId.set(destination.id, destination);
        });
        return Array.from(byId.values());
    }

    function favoritesStorageKey(sidebar) {
        const userId = String(sidebar.getAttribute('data-sidebar-user-id') || 'anonymous');
        return `app-sidebar-favorites:${userId}`;
    }

    function readFavoriteIds(sidebar) {
        try {
            const stored = window.localStorage.getItem(favoritesStorageKey(sidebar));
            if (stored === null) return null;
            const parsed = JSON.parse(stored);
            return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : null;
        } catch (_) {
            return null;
        }
    }

    function saveFavoriteIds(sidebar, ids) {
        try {
            window.localStorage.setItem(favoritesStorageKey(sidebar), JSON.stringify(ids));
        } catch (_) {
        }
    }

    function defaultFavoriteIds(destinations) {
        return DEFAULT_FAVORITES.map((favorite) => {
            const destination = destinations.find((item) => (
                normalizeText(item.sourceTitle) === normalizeText(favorite.sourceTitle)
            ));
            return destination ? destination.id : null;
        }).filter(Boolean);
    }

    function createFavoriteLink(destination) {
        const link = document.createElement('a');
        copyNavigationAttributes(destination.source, link);
        link.className = 'app-tab-link sidebar-favorite-link';
        link.setAttribute('data-sidebar-favorite-id', destination.id);
        link.setAttribute('aria-label', destination.label);
        link.setAttribute('title', destination.label);

        const icon = document.createElement('i');
        icon.className = destination.icon;
        icon.setAttribute('aria-hidden', 'true');

        const label = document.createElement('span');
        label.textContent = destination.label;
        link.replaceChildren(icon, label);
        return link;
    }

    function createFavorites(sidebar) {
        if (sidebar.querySelector(':scope > .sidebar-favorites')) return true;
        const destinations = availableFavoriteDestinations(sidebar);
        if (!destinations.length) return false;
        const destinationsById = new Map(destinations.map((item) => [item.id, item]));
        const storedIds = readFavoriteIds(sidebar);
        let selectedIds = (storedIds === null ? defaultFavoriteIds(destinations) : storedIds)
            .filter((id, index, ids) => destinationsById.has(id) && ids.indexOf(id) === index);

        const section = document.createElement('section');
        section.className = 'sidebar-favorites';
        section.setAttribute('aria-label', 'Accesos favoritos');

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'sidebar-favorites-toggle';
        button.setAttribute('aria-label', 'Abrir accesos favoritos');
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-controls', 'sidebar-favorites-panel');
        button.setAttribute('title', 'Accesos favoritos');
        button.innerHTML = '<i class="fas fa-star" aria-hidden="true"></i><span>Favoritos</span>';

        const panel = document.createElement('div');
        panel.id = 'sidebar-favorites-panel';
        panel.className = 'sidebar-favorites-panel';

        const header = document.createElement('div');
        header.className = 'sidebar-favorites-header';
        const title = document.createElement('span');
        title.className = 'sidebar-favorites-title';
        title.textContent = 'Favoritos';

        const manageButton = document.createElement('button');
        manageButton.type = 'button';
        manageButton.className = 'sidebar-favorites-manage';
        manageButton.setAttribute('aria-label', 'Personalizar favoritos');
        manageButton.setAttribute('title', 'Personalizar favoritos');
        manageButton.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i>';
        header.append(title, manageButton);

        const favoritesList = document.createElement('div');
        favoritesList.className = 'sidebar-favorites-list';

        const editor = document.createElement('div');
        editor.className = 'sidebar-favorites-editor';
        const editorHint = document.createElement('p');
        editorHint.className = 'sidebar-favorites-editor-hint';
        editorHint.textContent = 'Marcá los accesos que querés tener a mano.';
        const editorList = document.createElement('div');
        editorList.className = 'sidebar-favorites-editor-list';
        const editorActions = document.createElement('div');
        editorActions.className = 'sidebar-favorites-editor-actions';

        const resetButton = document.createElement('button');
        resetButton.type = 'button';
        resetButton.className = 'sidebar-favorites-reset';
        resetButton.textContent = 'Restablecer';
        const doneButton = document.createElement('button');
        doneButton.type = 'button';
        doneButton.className = 'sidebar-favorites-done';
        doneButton.textContent = 'Listo';
        editorActions.append(resetButton, doneButton);
        editor.append(editorHint, editorList, editorActions);
        panel.append(header, favoritesList, editor);

        function persistAndRender() {
            saveFavoriteIds(sidebar, selectedIds);
            renderFavorites();
            renderEditor();
            window.requestAnimationFrame(() => syncCurrentState(sidebar));
        }

        function renderFavorites() {
            const nodes = selectedIds
                .map((id) => destinationsById.get(id))
                .filter(Boolean)
                .map(createFavoriteLink);
            if (!nodes.length) {
                const empty = document.createElement('p');
                empty.className = 'sidebar-favorites-empty';
                empty.textContent = 'Todavía no elegiste favoritos.';
                favoritesList.replaceChildren(empty);
                return;
            }
            favoritesList.replaceChildren(...nodes);
        }

        function renderEditor() {
            const selectedOrder = new Map(selectedIds.map((id, index) => [id, index]));
            const ordered = [...destinations].sort((left, right) => {
                const leftSelected = selectedOrder.has(left.id);
                const rightSelected = selectedOrder.has(right.id);
                if (leftSelected && rightSelected) return selectedOrder.get(left.id) - selectedOrder.get(right.id);
                if (leftSelected !== rightSelected) return leftSelected ? -1 : 1;
                return left.label.localeCompare(right.label, 'es');
            });

            const rows = ordered.map((destination) => {
                const selected = selectedOrder.has(destination.id);
                const row = document.createElement('button');
                row.type = 'button';
                row.className = `sidebar-favorites-editor-item${selected ? ' is-selected' : ''}`;
                row.setAttribute('aria-pressed', String(selected));
                row.setAttribute('aria-label', `${selected ? 'Quitar' : 'Agregar'} ${destination.label}`);

                const star = document.createElement('i');
                star.className = selected ? 'fas fa-star' : 'far fa-star';
                star.setAttribute('aria-hidden', 'true');
                const label = document.createElement('span');
                label.textContent = destination.label;
                row.append(star, label);
                row.addEventListener('click', () => {
                    selectedIds = selected
                        ? selectedIds.filter((id) => id !== destination.id)
                        : [...selectedIds, destination.id];
                    persistAndRender();
                });
                return row;
            });
            editorList.replaceChildren(...rows);
        }

        function setEditing(editing) {
            section.classList.toggle('is-editing', editing);
            manageButton.setAttribute('aria-pressed', String(editing));
            manageButton.setAttribute('aria-label', editing ? 'Cerrar personalización' : 'Personalizar favoritos');
            manageButton.setAttribute('title', editing ? 'Cerrar personalización' : 'Personalizar favoritos');
        }

        function closeFavorites() {
            section.classList.remove('is-open');
            button.setAttribute('aria-expanded', 'false');
            setEditing(false);
        }

        button.addEventListener('click', (event) => {
            event.stopPropagation();
            const open = section.classList.toggle('is-open');
            button.setAttribute('aria-expanded', String(open));
        });
        panel.addEventListener('click', (event) => {
            if (event.target.closest('a')) closeFavorites();
        });
        manageButton.addEventListener('click', () => setEditing(!section.classList.contains('is-editing')));
        resetButton.addEventListener('click', () => {
            selectedIds = defaultFavoriteIds(destinations);
            persistAndRender();
        });
        doneButton.addEventListener('click', () => setEditing(false));
        document.addEventListener('click', (event) => {
            if (!section.contains(event.target)) closeFavorites();
        });
        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            closeFavorites();
            if (document.activeElement && section.contains(document.activeElement)) button.focus();
        });

        renderFavorites();
        renderEditor();
        section.append(button, panel);
        const home = sidebar.querySelector(':scope > #sidebar-home-link');
        if (home) home.insertAdjacentElement('beforebegin', section);
        else sidebar.appendChild(section);
        return true;
    }

    function ensureFavorites(sidebar) {
        if (!sidebar.querySelector(':scope > .sidebar-favorites')) createFavorites(sidebar);
    }

    function selectedTabTitle() {
        const selected = document.querySelector('#app-tab-bar [aria-selected="true"]');
        const label = selected ? selected.querySelector('span.whitespace-nowrap') : null;
        return label ? label.textContent.trim() : '';
    }

    function currentCandidates() {
        const currentUrl = normalizeUrl(`${window.location.pathname}${window.location.search}`);
        return { currentUrl, currentTitle: normalizeText(selectedTabTitle()) };
    }

    function isCurrentLink(link, state) {
        const rawUrl = link.getAttribute('data-tab-url') || link.getAttribute('href');
        if (rawUrl && normalizeUrl(rawUrl) === state.currentUrl) return true;
        const title = normalizeText(link.getAttribute('data-tab-title'));
        return Boolean(title && state.currentTitle && title === state.currentTitle);
    }

    function ownerTrigger(sidebar, link) {
        const liveMenu = link.closest ? link.closest('[data-sidebar-menu]') : null;
        if (liveMenu) {
            return sidebar.querySelector(`[data-sidebar-trigger="${liveMenu.getAttribute('data-sidebar-menu')}"]`);
        }

        const template = sidebarTemplates(sidebar).find((candidate) => candidate.content.contains(link));
        if (!template) return null;
        const owner = template.closest('.group');
        return owner ? owner.querySelector(':scope > [data-sidebar-trigger]') : null;
    }

    function clearCurrentState(sidebar) {
        rootLinks(sidebar).forEach((link) => {
            link.classList.remove('is-current', 'is-current-section');
            link.removeAttribute('aria-current');
        });
        navigationLinks(sidebar).forEach((link) => {
            link.classList.remove('is-current');
            link.removeAttribute('aria-current');
        });
        sidebar.querySelectorAll('.sidebar-favorite-link').forEach((link) => {
            link.classList.remove('is-current');
            link.removeAttribute('aria-current');
        });
    }

    function syncCurrentState(sidebar) {
        clearCurrentState(sidebar);
        const state = currentCandidates();

        navigationLinks(sidebar).forEach((link) => {
            if (!isCurrentLink(link, state)) return;
            link.classList.add('is-current');
            link.setAttribute('aria-current', 'page');

            if (link.classList.contains('sidebar-link')) return;
            const trigger = ownerTrigger(sidebar, link);
            if (!trigger) return;
            trigger.classList.add('is-current-section');
            trigger.setAttribute('aria-current', 'page');
        });

        sidebar.querySelectorAll('.sidebar-favorite-link').forEach((link) => {
            if (!isCurrentLink(link, state)) return;
            link.classList.add('is-current');
            link.setAttribute('aria-current', 'page');
        });
    }

    function observeNavigation(sidebar) {
        let scheduled = false;
        const scheduleSync = function () {
            if (scheduled) return;
            scheduled = true;
            window.requestAnimationFrame(() => {
                scheduled = false;
                enhanceRootLinks(sidebar);
                enhanceMobileMenus(sidebar);
                ensureFavorites(sidebar);
                syncCurrentState(sidebar);
            });
        };

        const tabBar = document.getElementById('app-tab-bar');
        if (tabBar) {
            new MutationObserver(scheduleSync).observe(tabBar, {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: ['aria-selected']
            });
        }
        new MutationObserver(scheduleSync).observe(sidebar, { subtree: true, childList: true });
        window.addEventListener('popstate', scheduleSync);
        window.addEventListener('pageshow', scheduleSync);
    }

    function initSidebarExperience() {
        const sidebar = document.querySelector('.app-shell-sidebar');
        if (!sidebar || sidebar.dataset.sidebarExperience === 'ready') return;

        sidebar.dataset.sidebarExperience = 'ready';
        createExpansionControl(sidebar);
        enhanceRootLinks(sidebar);
        enhanceMobileMenus(sidebar);
        setupMobileDrawerAutoClose(sidebar);
        createFavorites(sidebar);
        syncCurrentState(sidebar);
        observeNavigation(sidebar);

        // Los perfiles con pocos permisos suelen tener todos sus accesos dentro
        // de menús x-if. Alpine puede materializarlos después de este primer pase.
        window.addEventListener('alpine:initialized', () => ensureFavorites(sidebar), { once: true });
        window.requestAnimationFrame(() => ensureFavorites(sidebar));
        window.setTimeout(() => ensureFavorites(sidebar), 250);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSidebarExperience, { once: true });
    } else {
        initSidebarExperience();
    }
})();
