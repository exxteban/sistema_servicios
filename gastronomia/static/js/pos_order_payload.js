// Payload del pedido: comparte los campos del POS y conserva la atribución al editar.
(() => {
  const build = (root, cart, location, suggestions) => {
    const value = (id) => root.querySelector(`#${id}`)?.value || '';
    const type = value('order-type') || 'mostrador';
    return {
      tipo_pedido: type,
      mesa: value('table-name').trim(),
      referencia_entrega: value('delivery-reference').trim(),
      nombre_cliente: value('delivery-reference').trim(),
      celular_cliente: value('delivery-phone').trim(),
      direccion_entrega: value('delivery-address').trim(),
      ...location,
      tiempo_estimado_minutos: value('delivery-estimate') || null,
      costo_envio: type === 'delivery' ? Math.max(0, Number(value('delivery-shipping-cost'))) : 0,
      notas: value('order-notes').trim(),
      ...(suggestions ? {sugerencias: suggestions.payload()} : {}),
      items: cart.map((item) => ({
        producto_id: item.producto_id, canal_precio: item.canal_precio || null,
        cantidad: item.cantidad, peso_kg: item.peso_kg ?? null,
        opciones: item.opciones, notas: item.notas,
        ...(item.origen_sugerencia ? {origen_sugerencia: item.origen_sugerencia} : {}),
      })),
    };
  };
  window.GastronomiaOrderPayload = {build};
})();
