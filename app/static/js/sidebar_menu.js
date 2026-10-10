function sidebarMenu() {
    return {
        activeMenu: null,
        menuOffsets: {},

        init() {
            const repositionMenus = () => {
                if (typeof window.__appShellIsZooming === 'function' && window.__appShellIsZooming()) {
                    return;
                }
                if (this.activeMenu) {
                    this.$nextTick(() => this.positionMenu(this.activeMenu));
                }
            };

            window.addEventListener('resize', repositionMenus, { passive: true });
            window.addEventListener('orientationchange', repositionMenus, { passive: true });
            window.addEventListener('app:zoom-state-change', (event) => {
                const detail = event && event.detail ? event.detail : {};
                if (!detail.zooming) {
                    repositionMenus();
                }
            }, { passive: true });
            if (window.visualViewport) {
                window.visualViewport.addEventListener('resize', repositionMenus, { passive: true });
            }
        },

        openMenu(name) {
            this.activeMenu = name;
            this.$nextTick(() => {
                this.positionMenu(name);
                // Segunda pasada cuando el menu ya tiene su alto final.
                window.requestAnimationFrame(() => this.positionMenu(name));
            });
        },

        toggleMenu(name) {
            if (this.activeMenu === name) {
                this.activeMenu = null;
                return;
            }
            this.openMenu(name);
        },

        handleGlobalPointer(event) {
            if (!this.activeMenu || !event || !event.target || typeof event.target.closest !== 'function') {
                return;
            }
            if (event.target.closest('[data-sidebar-trigger]') || event.target.closest('[data-sidebar-menu]')) {
                return;
            }
            this.activeMenu = null;
        },

        closeMenuNow(name) {
            if (this.activeMenu === name) {
                this.activeMenu = null;
            }
        },

        getMenuStyle(name) {
            const offset = Number(this.menuOffsets[name] || 0);
            return `top: ${offset}px;`;
        },

        positionMenu(name) {
            const trigger = this.$el.querySelector(`[data-sidebar-trigger="${name}"]`);
            const menu = this.$el.querySelector(`[data-sidebar-menu="${name}"]`);
            if (!trigger || !menu) {
                return;
            }

            const padding = 12;
            const viewportHeight = Number(window.__appShellViewportHeight || 0)
                || (typeof window.__appShellGetViewportHeight === 'function'
                    ? window.__appShellGetViewportHeight()
                    : (window.innerHeight || document.documentElement.clientHeight || 0));
            const triggerRect = trigger.getBoundingClientRect();
            // offsetHeight y no getBoundingClientRect: al abrirse el menu
            // esta a mitad de la transicion de escala y el rect mide de menos.
            const menuOuterHeight = menu.offsetHeight || menu.getBoundingClientRect().height;

            // El limite superior no es el borde del viewport sino el borde
            // visible del sidebar: arriba de eso esta la barra superior fija
            // y el menu quedaria tapado.
            const sidebarRect = this.$el.getBoundingClientRect();
            const topLimit = Math.max(padding, sidebarRect.top + padding);
            const bottomLimit = viewportHeight - padding;
            const available = Math.max(0, bottomLimit - topLimit);
            const menuHeight = Math.min(menuOuterHeight, available);

            let desiredTop = triggerRect.top;
            if (desiredTop + menuHeight > bottomLimit) {
                desiredTop = bottomLimit - menuHeight;
            }
            if (desiredTop < topLimit) {
                desiredTop = topLimit;
            }

            const offset = desiredTop - triggerRect.top;

            this.menuOffsets = {
                ...this.menuOffsets,
                [name]: Math.round(offset)
            };
        }
    };
}
