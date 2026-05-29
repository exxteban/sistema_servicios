(function () {
  const TARGET = 'gastro-whatsapp';

  function absoluteUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
      return new URL(raw, window.location.origin).toString();
    } catch (error) {
      return raw;
    }
  }

  function trackingUrl(order) {
    return absoluteUrl(order?.url_seguimiento_publica || order?.url_seguimiento || '');
  }

  async function copyTrackingUrl(order) {
    const url = trackingUrl(order);
    if (!url) return false;
    const clipboard = window.navigator?.clipboard;
    if (clipboard?.writeText) {
      await clipboard.writeText(url);
      return true;
    }
    return fallbackCopy(url);
  }

  function orderCode(order) {
    if (order?.codigo_entrega) return order.codigo_entrega;
    if (order?.id_pedido) return `#${String(order.id_pedido).padStart(3, '0')}`;
    return '';
  }

  function buildOrderMessage(order) {
    const code = orderCode(order);
    const url = trackingUrl(order);
    const intro = code ? `Hola! Tu pedido ${code} ya esta en proceso.` : 'Hola! Tu pedido ya esta en proceso.';
    if (!url) return intro;
    return `${intro} Podes seguir el estado aca:\n\n${url}`;
  }

  function buildWhatsAppUrl(phone, message) {
    const digits = phoneDigits(phone);
    if (!digits) return '';
    return `https://wa.me/${digits}?text=${encodeURIComponent(message || 'Hola')}`;
  }

  function buildOrderWhatsAppUrl(order, phone) {
    return buildWhatsAppUrl(phone, buildOrderMessage(order));
  }

  function phoneDigits(phone) {
    const digits = String(phone || '').replace(/\D+/g, '');
    if (!digits) return '';
    return digits.startsWith('595') ? digits : `595${digits.replace(/^0+/, '')}`;
  }

  function fallbackCopy(text) {
    const input = document.createElement('textarea');
    input.value = text;
    input.setAttribute('readonly', '');
    input.style.position = 'fixed';
    input.style.left = '-9999px';
    document.body.appendChild(input);
    input.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    input.remove();
    return ok;
  }

  window.GastroWhatsApp = {
    target: TARGET,
    absoluteUrl,
    trackingUrl,
    copyTrackingUrl,
    buildOrderMessage,
    buildWhatsAppUrl,
    buildOrderWhatsAppUrl,
    phoneDigits,
  };
}());
