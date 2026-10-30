// Instancia independiente por POS. Solo abre el mismo configurador que el menú.
(() => {
  const create = (root, {getState, openProduct, money}) => {
    const host = root?.querySelector('[data-pos-sugerencias]');
    if (!host) return null;
    let timer, controller, timeout, generation = 0;
    let hidden = false, destroyed = false, signature = '', catalog = null, rows = [];
    let inViewport = typeof IntersectionObserver !== 'function';
    const exposureTargets = new Map(), visibleTargets = new Set();
    const shown = new Map(), touched = new Map();
    const keyFor = (origin, target) => `${origin}:${target}`;
    const markShown = (items) => items.forEach((item) => {
      if (Number.isInteger(item.id_origen) && shown.size < 180) {
        shown.set(keyFor(item.id_origen, item.id_producto), [item.id_origen, item.id_producto]);
      }
    });
    const recordVisible = () => {
      if (!inViewport || host.hidden || document.visibilityState === 'hidden'
          || (host.getClientRects && !host.getClientRects().length)) return;
      const visible = [...exposureTargets].filter(([node, target]) =>
        (!observer || visibleTargets.has(node)) && (!target.detail || !list.hidden));
      markShown(visible.map(([, target]) => target.item));
    };
    const max = Math.min(3, Math.max(1, Number(host.dataset.max || 3)));
    const element = (tag, className, text) => {
      const node = document.createElement(tag);
      node.className = className;
      if (text) node.textContent = text;
      return node;
    };
    const row = element('div', 'gs-pos-row');
    row.append(element('span', 'gs-pos-label', '✦ Suelen llevar'));
    const chips = element('div', 'gs-pos-chips');
    const more = element('button', 'gs-pos-control', '⋯');
    more.type = 'button';
    more.setAttribute('aria-label', 'Más sugerencias y motivos');
    more.setAttribute('aria-expanded', 'false');
    more.dataset.action = 'more';
    const close = element('button', 'gs-pos-control', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Ocultar sugerencias de este pedido');
    close.dataset.action = 'close';
    row.append(chips, more, close);
    const list = element('ul', 'gs-pos-list');
    list.hidden = true;
    host.append(row, list);

    const stateSignature = (state) => JSON.stringify([
      state.channel || '', state.cart.map((item) => [item.producto_id, item.canal_precio || '']),
    ]);
    const usable = (product) => product && product.disponible && product.activo !== false
      && product.visible !== false && (!product.control_stock_venta || Number(product.stock_disponible) > 0);
    const productFor = (id, state) => state.products.find((p) => Number(p.id_producto) === Number(id));
    const eligible = (item, state) => {
      const product = productFor(item.id_producto, state);
      return usable(product) && (product.canal_precio || '') === (state.channel || '')
        && !state.cart.some((line) => Number(line.producto_id) === Number(item.id_producto));
    };
    const hide = () => {
      host.hidden = true;
      list.hidden = true;
      more.setAttribute('aria-expanded', 'false');
    };
    const cancel = () => {
      generation += 1;
      clearTimeout(timer);
      clearTimeout(timeout);
      controller?.abort();
    };
    const label = (product) => {
      const variablePrice = product.unidad_venta === 'kg' || (product.grupos_opciones || [])
        .some((group) => (group.opciones || []).some((option) => Number(option.precio_delta || 0) !== 0));
      return variablePrice ? product.nombre : `${product.nombre} ${money(product.precio)}`;
    };
    const render = (items, state, maximum) => {
      rows = items.filter((item) => eligible(item, state));
      observer?.disconnect();
      exposureTargets.clear();
      visibleTargets.clear();
      chips.replaceChildren();
      list.replaceChildren();
      rows.forEach((item, index) => {
        const product = productFor(item.id_producto, state);
        const button = element('button', 'gs-pos-chip', `+ ${label(product)}`);
        button.type = 'button';
        button.title = product.nombre;
        button.dataset.product = String(item.id_producto);
        if (index < maximum) {
          chips.append(button);
          exposureTargets.set(button, {item, detail: false});
        }
        const li = element('li', '');
        const detail = button.cloneNode(true);
        exposureTargets.set(detail, {item, detail: true});
        li.append(detail, element('span', 'gs-pos-reason', item.motivo));
        list.append(li);
      });
      host.hidden = rows.length === 0;
      observer?.observe(host);
      for (const node of exposureTargets.keys()) observer?.observe(node);
      recordVisible();
    };
    const current = (version, key) => !destroyed && !hidden && root.isConnected
      && navigator.onLine !== false && version === generation && key === stateSignature(getState());

    const query = async (version, key, attempt = 0) => {
      if (!current(version, key)) return;
      const state = getState();
      controller = new AbortController();
      const requestController = controller;
      // El timeout de la franja es independiente de guardar/enviar/cobrar.
      timeout = setTimeout(() => requestController.abort(), 1200);
      try {
        const params = new URLSearchParams({
          productos: state.cart.map((item) => item.producto_id).slice(-60).join(','),
          canal_precio: state.channel || '',
        });
        const response = await fetch(`${host.dataset.url}?${params}`, {signal: requestController.signal, cache: 'no-store'});
        if (!response.ok) throw new Error('Consulta de sugerencias no disponible');
        const data = await response.json();
        if (current(version, key)) {
          render(Array.isArray(data.sugerencias) ? data.sugerencias.slice(0, 6) : [], getState(),
            Math.min(max, Math.max(0, Number(data.max ?? max))));
        }
      } catch (_) {
        if (current(version, key)) {
          hide();
          if (attempt === 0) timer = setTimeout(() => query(version, key, 1), 500);
        }
      } finally {
        // Una petición vieja nunca limpia el timeout de la nueva.
        if (controller === requestController) clearTimeout(timeout);
      }
    };

    const refresh = () => {
      if (destroyed) return;
      if (!root.isConnected) { destroy(); return; }
      const state = getState();
      const nextSignature = stateSignature(state);
      if (signature === nextSignature && catalog === state.products) return;
      signature = nextSignature;
      catalog = state.products;
      cancel();
      hide();
      const compatible = state.cart.every((item) => (item.canal_precio || '') === (state.channel || ''))
        && state.products.every((product) => (product.canal_precio || '') === (state.channel || ''));
      if (hidden || navigator.onLine === false || !state.cart.length || !state.products.length || !compatible) return;
      const version = generation;
      timer = setTimeout(() => query(version, signature), 500);
    };
    const onClick = (event) => {
      const button = event.target.closest('button');
      if (!button || !host.contains(button)) return;
      if (button.dataset.action === 'close') {
        hidden = true;
        cancel();
        hide();
      } else if (button.dataset.action === 'more') {
        list.hidden = !list.hidden;
        more.setAttribute('aria-expanded', String(!list.hidden));
        if (!list.hidden) recordVisible();
      } else if (button.dataset.product && navigator.onLine !== false) {
        const state = getState();
        const item = rows.find((s) => String(s.id_producto) === button.dataset.product);
        if (item && eligible(item, state)) openProduct(productFor(item.id_producto, state), item.id_origen);
      }
    };
    const onOffline = () => { cancel(); hide(); };
    const onOnline = () => { signature = ''; refresh(); };
    const destroy = () => {
      destroyed = true;
      cancel();
      hide();
      host.removeEventListener('click', onClick);
      window.removeEventListener('offline', onOffline);
      window.removeEventListener('online', onOnline);
      document.removeEventListener?.('visibilitychange', recordVisible);
      observer?.disconnect();
    };
    const observer = typeof IntersectionObserver === 'function'
      ? new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.target === host) inViewport = entry.isIntersecting;
          else if (exposureTargets.has(entry.target)) {
            if (entry.isIntersecting) visibleTargets.add(entry.target);
            else visibleTargets.delete(entry.target);
          }
        }
        recordVisible();
      }) : null;
    observer?.observe(host);
    document.addEventListener?.('visibilitychange', recordVisible);
    host.addEventListener('click', onClick);
    window.addEventListener('offline', onOffline);
    window.addEventListener('online', onOnline);
    return {
      refresh, destroy,
      payload: () => ({mostradas: [...shown.values()], tocadas: [...touched.values()]}),
      accepted: (item) => {
        const key = keyFor(item.origen_sugerencia, item.producto_id);
        if (shown.has(key)) touched.set(key, shown.get(key));
      },
      restore: (data) => {
        for (const pair of data?.mostradas || []) shown.set(keyFor(...pair), pair);
        for (const pair of data?.tocadas || []) touched.set(keyFor(...pair), pair);
      },
      reset: () => { hidden = false; signature = ''; shown.clear(); touched.clear(); cancel(); hide(); },
    };
  };
  window.GastronomiaSugerencias = {create};
})();
