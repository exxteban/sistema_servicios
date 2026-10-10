(function () {
    if (window.__appZoomStabilityInit) return;
    window.__appZoomStabilityInit = true;

    const root = document.documentElement;
    const zoomTolerance = 0.015;
    const trackedAttributePrefix = 'data-app-zoom-';
    let zooming = false;
    let settleTimer = null;
    let mutationObserver = null;
    let scanTimer = null;
    const pendingScanRoots = new Set();

    function safeRequestIdleCallback(callback, timeout) {
        if (typeof window.requestIdleCallback === 'function') {
            return window.requestIdleCallback(callback, { timeout: timeout || 250 });
        }
        return window.setTimeout(callback, Math.min(120, timeout || 120));
    }

    function safeCancelIdleCallback(handle) {
        if (handle === null) return;
        if (typeof window.cancelIdleCallback === 'function') {
            window.cancelIdleCallback(handle);
            return;
        }
        window.clearTimeout(handle);
    }

    function normalizeScale(rawScale) {
        const scale = Number(rawScale);
        if (!Number.isFinite(scale) || scale <= 0) return 1;
        return Math.abs(scale - 1) <= zoomTolerance ? 1 : scale;
    }

    function getViewportScale() {
        const vv = window.visualViewport;
        return normalizeScale(vv && typeof vv.scale === 'number' ? vv.scale : 1);
    }

    function setZoomState(nextZooming, reason) {
        const scale = getViewportScale();
        if (zooming === nextZooming && window.__appShellZoomScale === scale) return;

        zooming = nextZooming;
        window.__appShellZoomScale = scale;
        root.classList.toggle('app-zooming', zooming);
        root.style.setProperty('--app-zoom-scale', String(scale));
        if (zooming) {
            initMutationTracking();
        } else {
            stopMutationTracking();
        }

        window.dispatchEvent(new CustomEvent('app:zoom-state-change', {
            detail: {
                zooming,
                scale,
                reason: reason || 'unknown'
            }
        }));
    }

    function markShellRoot() {
        if (!document.body || !document.body.classList.contains('app-shell-body')) return;
        if (!document.body.hasAttribute('data-app-shell-root')) {
            document.body.setAttribute('data-app-shell-root', 'true');
        }
    }

    function clearSettleTimer() {
        if (settleTimer !== null) {
            window.clearTimeout(settleTimer);
            settleTimer = null;
        }
    }

    function scheduleSettle(reason, delayMs) {
        clearSettleTimer();
        settleTimer = window.setTimeout(() => {
            settleTimer = null;
            setZoomState(getViewportScale() !== 1, reason || 'settled');
        }, Math.max(60, Number(delayMs) || 180));
    }

    function handleViewportActivity(reason) {
        const scale = getViewportScale();
        if (scale !== 1) {
            setZoomState(true, reason || 'visualViewport');
            return;
        }
        scheduleSettle(reason || 'visualViewport', 140);
    }

    window.__appShellIsZooming = function () {
        return zooming;
    };

    window.__appShellShouldFreezeViewportHeight = function () {
        return getViewportScale() !== 1;
    };

    window.__appShellGetZoomScale = getViewportScale;
    window.__appZoomStabilityRescan = function () {
        if (!mutationObserver) return;
        queueScan(document.body || document.documentElement);
    };

    function isTrackableElement(element) {
        if (!(element instanceof HTMLElement)) return false;
        const tagName = element.tagName;
        return ![
            'HTML',
            'HEAD',
            'BODY',
            'SCRIPT',
            'STYLE',
            'META',
            'LINK',
            'NOSCRIPT'
        ].includes(tagName);
    }

    function hasNonZeroTiming(value) {
        return String(value || '')
            .split(',')
            .some((part) => {
                const token = part.trim();
                return token && token !== '0s' && token !== '0ms';
            });
    }

    function collectZoomTypes(element) {
        if (!isTrackableElement(element)) return [];

        const styles = window.getComputedStyle(element);
        const types = [];
        const backdropFilter = String(styles.backdropFilter || styles.webkitBackdropFilter || 'none');
        const filter = String(styles.filter || 'none');
        const boxShadow = String(styles.boxShadow || 'none');
        const position = String(styles.position || '');
        const willChange = String(styles.willChange || '');
        const contain = String(styles.contain || '');
        const hasAnimation = styles.animationName !== 'none' && hasNonZeroTiming(styles.animationDuration);
        const hasTransition = hasNonZeroTiming(styles.transitionDuration);
        const hasBlurLikeFilter = /\bblur\(|\bdrop-shadow\(/i.test(filter);
        const hasBackdrop = backdropFilter && backdropFilter !== 'none';
        const hasTransformIntent = /\btransform\b|\bfilter\b|\bbackdrop-filter\b/i.test(willChange);
        const isFixedLike = position === 'fixed' || position === 'sticky';
        const isPaintHeavy = /\bpaint\b|\bstrict\b|\bcontent\b/i.test(contain);

        if (hasBackdrop || hasBlurLikeFilter) {
            types.push('filter');
        }
        if (boxShadow && boxShadow !== 'none') {
            types.push('shadow');
        }
        if (hasAnimation || hasTransition) {
            types.push('animate');
        }
        if (isFixedLike || hasTransformIntent || isPaintHeavy) {
            types.push('overlay');
        }

        return types;
    }

    function applyTrackingMetadata(element, types) {
        if (!isTrackableElement(element)) return;

        if (!types.length) {
            element.removeAttribute('data-app-zoom-costly');
            element.removeAttribute('data-app-zoom-types');
            return;
        }

        element.setAttribute('data-app-zoom-costly', 'true');
        element.setAttribute('data-app-zoom-types', types.join(' '));
    }

    function scanElement(element) {
        if (!isTrackableElement(element)) return;
        applyTrackingMetadata(element, collectZoomTypes(element));
    }

    function scanTree(scanRoot) {
        if (!scanRoot) return;

        if (scanRoot instanceof HTMLElement) {
            scanElement(scanRoot);
        }

        if (!(scanRoot instanceof Element) || typeof scanRoot.querySelectorAll !== 'function') {
            return;
        }

        const descendants = scanRoot.querySelectorAll('*');
        descendants.forEach((element) => {
            scanElement(element);
        });
    }

    function flushPendingScans() {
        scanTimer = null;
        const roots = Array.from(pendingScanRoots);
        pendingScanRoots.clear();
        roots.forEach((entry) => scanTree(entry));
    }

    function queueScan(scanRoot) {
        if (!scanRoot) return;
        pendingScanRoots.add(scanRoot);
        if (scanTimer !== null) return;
        scanTimer = safeRequestIdleCallback(flushPendingScans, 280);
    }

    function shouldIgnoreMutationAttribute(attributeName) {
        return String(attributeName || '').startsWith(trackedAttributePrefix);
    }

    // El escaneo de estilos solo corre mientras hay zoom real: los atributos
    // data-app-zoom-* solo se usan bajo html.app-zooming. Asi, pantallas que
    // nunca hacen zoom (p. ej. cocina en una TV) no pagan el costo de observar
    // cada re-render del DOM.
    function initMutationTracking() {
        if (mutationObserver || !document.body || typeof MutationObserver !== 'function') return;

        markShellRoot();

        mutationObserver = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes') {
                    if (shouldIgnoreMutationAttribute(mutation.attributeName)) return;
                    queueScan(mutation.target);
                    return;
                }

                mutation.addedNodes.forEach((node) => {
                    if (node instanceof Element) {
                        queueScan(node);
                    }
                });
            });
        });

        mutationObserver.observe(document.body, {
            subtree: true,
            childList: true,
            attributes: true,
            attributeFilter: ['class', 'style']
        });

        queueScan(document.body);
    }

    function stopMutationTracking() {
        safeCancelIdleCallback(scanTimer);
        scanTimer = null;
        pendingScanRoots.clear();
        if (mutationObserver) {
            mutationObserver.disconnect();
            mutationObserver = null;
        }
    }

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => handleViewportActivity('visualViewport:resize'), { passive: true });
        window.visualViewport.addEventListener('scroll', () => handleViewportActivity('visualViewport:scroll'), { passive: true });
    }

    window.addEventListener('wheel', (event) => {
        if (!event || !event.ctrlKey) return;
        setZoomState(true, 'ctrlWheel');
        scheduleSettle('ctrlWheel:settled', 220);
    }, { passive: true });

    window.addEventListener('resize', () => {
        if (getViewportScale() === 1) {
            scheduleSettle('window:resize', 120);
        }
    }, { passive: true });

    window.addEventListener('beforeunload', () => {
        clearSettleTimer();
        stopMutationTracking();
    }, { passive: true });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            markShellRoot();
            if (zooming) initMutationTracking();
        }, { once: true });
    } else {
        markShellRoot();
    }

    handleViewportActivity('init');
})();
