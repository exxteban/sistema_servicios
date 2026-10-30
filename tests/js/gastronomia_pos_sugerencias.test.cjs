const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// DOM mínimo: se prueba el controlador con fetch y reloj controlados, sin paquetes nuevos.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this.isConnected = true;
    this.textContent = '';
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.listeners[key] = callback; }
  removeEventListener(key) { delete this.listeners[key]; }
  closest() { return this; }
  contains(node) { return node === this || this.children.some((c) => c.contains(node)); }
  cloneNode() {
    return Object.assign(new Element(this.tagName), {textContent: this.textContent,
      className: this.className, dataset: {...this.dataset}});
  }
}
const flatten = (node) => [node, ...node.children.flatMap(flatten)];
const find = (node, predicate) => flatten(node).find(predicate);
const chips = (host) => find(host, (n) => n.className === 'gs-pos-chips').children;
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

test('editar pedido restaura su canal y la selección del catálogo', () => {
  const window = {};
  const context = vm.createContext({window});
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../gastronomia/static/js/pos_channel_prices.js'), 'utf8'), context);
  const buttons = ['', 'pedidosya', 'monchis'].map((channel) => ({dataset: {priceChannel: channel},
    classList: {toggle(name, active) { this.active = active; }}}));
  const root = {querySelectorAll: () => buttons};
  const changes = [];
  window.GastronomiaChannelPrices.hydrateOrderChannel({items: [{canal_precio: 'pedidosya'}]}, root, '', (value) => changes.push(value));
  assert.deepEqual(changes, ['pedidosya']);
  assert.deepEqual(buttons.map((b) => b.classList.active), [false, true, false]);
  window.GastronomiaChannelPrices.hydrateOrderChannel({items: [{canal_precio: 'pedidosya'}]}, root, 'pedidosya', () => assert.fail('No debe recargar el mismo canal'));
});

function setup({ignoreAbort = false} = {}) {
  let now = 0, nextTimer = 0;
  const timers = new Map(), requests = [];
  const window = new Element();
  const document = {createElement: (tag) => new Element(tag), activeElement: {name: 'buscador'}};
  const context = vm.createContext({window, document, navigator: {onLine: true},
    AbortController, URLSearchParams,
    setTimeout: (fn, delay) => { const id = ++nextTimer; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout: (id) => timers.delete(id),
    fetch: (url, options) => new Promise((resolve, reject) => {
      requests.push({url, options, resolve, reject});
      if (!ignoreAbort) options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    }),
  });
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../gastronomia/static/js/pos_sugerencias.js'), 'utf8'), context);
  const tick = async (ms) => {
    const end = now + ms;
    while (true) {
      const next = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      timers.delete(next[0]);
      now = next[1].at;
      next[1].fn();
      await flush();
    }
    now = end;
    await flush();
  };
  const instance = () => {
    const host = new Element();
    host.dataset = {max: '3', url: '/api/gastronomia/sugerencias'};
    const root = {isConnected: true, querySelector: () => host};
    const state = {channel: '', cart: [{producto_id: 1}], products: [
      {id_producto: 1, nombre: 'Hamburguesa', precio: 15000, disponible: true},
      {id_producto: 2, nombre: 'Papas', precio: 5000, disponible: true},
    ]};
    const opened = [];
    const controller = window.GastronomiaSugerencias.create(root, {
      getState: () => state, openProduct: (p) => opened.push(p), money: (v) => `Gs. ${v}`,
    });
    return {host, root, state, opened, controller,
      click: (button) => host.listeners.click({target: button})};
  };
  const respond = async (index, ids = [2]) => {
    requests[index].resolve({ok: true, json: async () => ({max: 3,
      sugerencias: ids.map((id) => ({id_producto: id, motivo: 'Regla del negocio'}))})});
    await flush();
  };
  return {tick, respond, requests, instance, document, window};
}

test('debounce, precio del catálogo y mismo configurador sin robar foco', async () => {
  const env = setup(), pos = env.instance();
  const focus = env.document.activeElement;
  pos.controller.refresh();
  await env.tick(499);
  assert.equal(env.requests.length, 0);
  await env.tick(1);
  await env.respond(0);
  assert.equal(pos.host.hidden, false);
  assert.equal(chips(pos.host)[0].textContent, '+ Papas Gs. 5000');
  assert.equal(env.document.activeElement, focus);
  pos.click(chips(pos.host)[0]);
  assert.equal(pos.opened[0], pos.state.products[1]);
  pos.state.cart.push({producto_id: 2});
  pos.click(chips(pos.host)[0]);
  assert.equal(pos.opened.length, 1, 'Revalida que todavía no esté en el carrito');
});

test('respuesta vieja se descarta aunque el servidor ignore AbortController', async () => {
  const env = setup({ignoreAbort: true}), pos = env.instance();
  pos.controller.refresh();
  await env.tick(500);
  pos.state.cart.push({producto_id: 2});
  pos.controller.refresh();
  assert.equal(env.requests[0].options.signal.aborted, true);
  await env.respond(0);
  assert.equal(pos.host.hidden, true);
  await env.tick(500);
  await env.respond(1);
  assert.equal(pos.host.hidden, true, 'Un destino ya presente tampoco se muestra en la respuesta actual');
});

test('timeout propio, un solo reintento y recuperación al cambiar el carrito', async () => {
  const env = setup(), pos = env.instance();
  pos.controller.refresh();
  await env.tick(500 + 1200 + 500);
  assert.equal(env.requests.length, 2);
  env.requests[1].reject(new Error('500'));
  await flush();
  await env.tick(5000);
  assert.equal(env.requests.length, 2);
  assert.equal(pos.host.hidden, true);
  pos.state.cart = [{producto_id: 1}, {producto_id: 3}];
  pos.controller.refresh();
  await env.tick(500);
  assert.equal(env.requests.length, 3);
  await env.respond(2);
  assert.equal(pos.host.hidden, false);
});

test('ocultar es por pedido e instancia y reset habilita el pedido siguiente', async () => {
  const env = setup(), a = env.instance(), b = env.instance();
  a.controller.refresh(); b.controller.refresh();
  await env.tick(500);
  await env.respond(0); await env.respond(1);
  a.click(find(a.host, (n) => n.dataset.action === 'close'));
  assert.equal(a.host.hidden, true);
  assert.equal(b.host.hidden, false);
  a.state.cart = [{producto_id: 1}, {producto_id: 3}];
  a.controller.refresh();
  await env.tick(500);
  assert.equal(env.requests.length, 2);
  a.controller.reset(); a.controller.refresh();
  await env.tick(500);
  await env.respond(2);
  assert.equal(a.host.hidden, false);
  a.controller.destroy(); b.controller.destroy();
});

test('canal incompatible no consulta; por peso y extras con precio no muestran importe', async () => {
  const env = setup(), pos = env.instance();
  pos.state.channel = 'pedidosya';
  pos.controller.refresh();
  await env.tick(500);
  assert.equal(env.requests.length, 0);
  pos.state.cart[0].canal_precio = 'pedidosya';
  pos.state.products = pos.state.products.map((p) => ({...p, canal_precio: 'pedidosya', precio: 7000}));
  pos.state.products[1].unidad_venta = 'kg';
  pos.controller.refresh();
  await env.tick(500);
  assert.match(env.requests[0].url, /canal_precio=pedidosya/);
  await env.respond(0);
  assert.equal(chips(pos.host)[0].textContent, '+ Papas');
  pos.state.products = pos.state.products.map((p) => ({...p, unidad_venta: 'unidad',
    grupos_opciones: [{opciones: [{precio_delta: 2000}]}]}));
  pos.controller.refresh();
  await env.tick(500); await env.respond(1);
  assert.equal(chips(pos.host)[0].textContent, '+ Papas');
});
