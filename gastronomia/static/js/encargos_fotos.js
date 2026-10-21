// Fotos de referencia de encargos: reduce la foto del celular en el navegador y la sube.
// El servidor limita la subida a 5 MB (MAX_CONTENT_LENGTH); por eso se achica antes de enviar.
(() => {
  const MAX_SIDE = 1600;
  const QUALITY = 0.85;

  const loadImage = (file) => new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('El archivo no es una imagen valida.')); };
    img.src = url;
  });

  // Devuelve un Blob JPEG con el lado mayor <= MAX_SIDE. Si el navegador no puede, sube el original.
  const reduce = async (file) => {
    if (!file || !String(file.type || '').startsWith('image/')) {
      throw new Error('Elegi una imagen (foto de la camara o de la galeria).');
    }
    const img = await loadImage(file);
    const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth || 1, img.naturalHeight || 1));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    const context = canvas.getContext('2d');
    if (!context) return file;
    context.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', QUALITY));
    return blob || file;
  };

  const csrfToken = () => document.getElementById('csrf-token')?.value
    || document.querySelector('meta[name="csrf-token"]')?.content || '';

  const parseResponse = async (response) => {
    if (response.status === 413) throw new Error('La foto es demasiado pesada. Proba con otra o sacala con menos resolucion.');
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.mensaje || 'No se pudo guardar la foto.');
    return data;
  };

  const upload = async (pedidoId, file) => {
    const blob = await reduce(file);
    const form = new FormData();
    form.append('foto', blob, 'foto.jpg');
    const response = await fetch(`/api/gastronomia/encargos/${Number(pedidoId)}/fotos`, {
      method: 'POST',
      headers: {'X-CSRFToken': csrfToken()},
      body: form,
      credentials: 'same-origin',
    });
    return (await parseResponse(response)).foto;
  };

  const remove = async (pedidoId, fotoId) => {
    const response = await fetch(`/api/gastronomia/encargos/${Number(pedidoId)}/fotos/${Number(fotoId)}`, {
      method: 'DELETE',
      headers: {'X-CSRFToken': csrfToken()},
      credentials: 'same-origin',
    });
    return parseResponse(response);
  };

  window.EncargoFotos = {reduce, upload, remove};
})();
