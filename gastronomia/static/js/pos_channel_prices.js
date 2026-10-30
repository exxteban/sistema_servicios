(function () {
  let productsRequestVersion = 0;
  const normalize = (value) => value || '';

  const fetchProducts = async (apiJson, channel) => {
    const requestVersion = ++productsRequestVersion;
    const data = await apiJson(`/api/gastronomia/productos?publico=1&modificadores=1&agotados=1&canal_precio=${encodeURIComponent(channel || '')}`);
    return requestVersion === productsRequestVersion ? (data.productos || []) : null;
  };

  const ensureCanAdd = (cart, product) => {
    const activeChannel = normalize(product?.canal_precio);
    const existingChannels = new Set((cart || []).map((item) => normalize(item.canal_precio)));
    if (existingChannels.size > 1 || (existingChannels.size && !existingChannels.has(activeChannel))) {
      throw new Error('El pedido no puede mezclar precios normales, de PedidosYa y de Monchis. Limpia el pedido para cambiar de lista.');
    }
  };

  const hydrateOrderChannel = (order, root, currentChannel, apply) => {
    if (!order?.items?.length) return;
    const channel = normalize(order.items[0].canal_precio);
    if (channel === normalize(currentChannel)) return;
    root.querySelectorAll('.pos-category').forEach((button) => {
      button.classList.toggle('active', normalize(button.dataset.priceChannel) === channel && !button.dataset.category);
    });
    apply(channel);
  };

  window.GastronomiaChannelPrices = {ensureCanAdd, fetchProducts, hydrateOrderChannel};
}());
