(function () {
  const byId = (id) => document.getElementById(id);
  const locationUrlInput = () => byId('delivery-location-url');
  const latInput = () => byId('delivery-destination-lat');
  const lngInput = () => byId('delivery-destination-lng');
  const extractButton = () => byId('delivery-extract-location');
  const mapButton = () => byId('delivery-open-location-map');
  const modal = () => byId('delivery-location-modal');
  const mapBox = () => byId('delivery-location-map');
  const closeMapButton = () => byId('delivery-close-location-map');
  const confirmMapButton = () => byId('delivery-confirm-location-map');
  const mapStatus = () => byId('delivery-location-map-status');
  let map = null;
  let marker = null;
  let selectedCoords = null;
  let tileErrorShown = false;

  const coordsFromText = (value) => {
    const rawText = String(value || '').trim();
    let text = rawText;
    try {
      text = decodeURIComponent(rawText);
    } catch (_) {}
    const priorityPatterns = [
      /!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/,
      /[?&](?:q|query|ll|destination)=(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/,
    ];
    for (const pattern of priorityPatterns) {
      const match = text.match(pattern);
      if (match) return validateCoords(match[1], match[2]);
    }
    try {
      const url = new URL(text);
      for (const key of ['q', 'query', 'll', 'destination']) {
        const coords = coordsFromText(url.searchParams.get(key) || '');
        if (coords) return coords;
      }
    } catch (_) {}
    const fallbackPatterns = [
      /@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/,
      /(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/,
    ];
    for (const pattern of fallbackPatterns) {
      const match = text.match(pattern);
      if (match) return validateCoords(match[1], match[2]);
    }
    return null;
  };
  const validateCoords = (latValue, lngValue) => {
    const lat = Number(latValue);
    const lng = Number(lngValue);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return {lat, lng};
  };
  const fillFromLocationUrl = () => {
    const coords = coordsFromText(locationUrlInput()?.value || '');
    if (!coords) return false;
    latInput().value = coords.lat;
    lngInput().value = coords.lng;
    return true;
  };
  const currentOrDefaultCoords = () => validateCoords(latInput()?.value, lngInput()?.value) || {lat: -25.30066, lng: -57.63591};
  const setMapStatus = (message, visible = true) => {
    const status = mapStatus();
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('hidden', !visible || !message);
  };
  const waitForVisibleMap = (callback) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(callback));
  };
  const openMap = () => {
    if (!modal() || !mapBox()) return;
    modal().classList.remove('hidden');
    modal().classList.add('flex');
    setMapStatus('');
    waitForVisibleMap(() => {
      const center = currentOrDefaultCoords();
      selectedCoords = null;
      if (!window.L) {
        setMapStatus('No se pudo cargar el mapa. Verifica internet o pega un link/coordenadas y toca Extraer.');
        return;
      }
      if (!map) {
        map = window.L.map(mapBox()).setView([center.lat, center.lng], 15);
        const tiles = window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap',
        }).addTo(map);
        tiles.on('tileerror', () => {
          if (tileErrorShown) return;
          tileErrorShown = true;
          setMapStatus('El mapa esta tardando en cargar. Podes tocar el fondo gris para marcar el punto o reintentar con mejor conexion.');
        });
        map.on('click', (event) => setMapPoint(event.latlng.lat, event.latlng.lng));
      }
      map.setView([center.lat, center.lng], 15);
      setMapPoint(center.lat, center.lng);
      map.invalidateSize(true);
      window.setTimeout(() => map?.invalidateSize(true), 250);
    });
  };
  const closeMap = () => {
    modal()?.classList.add('hidden');
    modal()?.classList.remove('flex');
  };
  const setMapPoint = (lat, lng) => {
    selectedCoords = {lat, lng};
    if (!marker) {
      marker = window.L.marker([lat, lng]).addTo(map);
    } else {
      marker.setLatLng([lat, lng]);
    }
  };
  const confirmMap = () => {
    if (!selectedCoords) return;
    latInput().value = Number(selectedCoords.lat).toFixed(6);
    lngInput().value = Number(selectedCoords.lng).toFixed(6);
    closeMap();
  };

  window.GastronomiaDeliveryLocation = {
    payload: () => ({
      ubicacion_entrega_url: locationUrlInput()?.value.trim() || '',
      destino_latitud: latInput()?.value || null,
      destino_longitud: lngInput()?.value || null,
    }),
    hydrate: (order) => {
      if (locationUrlInput()) locationUrlInput().value = order?.ubicacion_entrega_url || '';
      if (latInput()) latInput().value = order?.destino_latitud ?? '';
      if (lngInput()) lngInput().value = order?.destino_longitud ?? '';
    },
    reset: () => {
      if (locationUrlInput()) locationUrlInput().value = '';
      if (latInput()) latInput().value = '';
      if (lngInput()) lngInput().value = '';
    },
  };

  extractButton()?.addEventListener('click', () => fillFromLocationUrl());
  locationUrlInput()?.addEventListener('change', () => fillFromLocationUrl());
  mapButton()?.addEventListener('click', openMap);
  closeMapButton()?.addEventListener('click', closeMap);
  confirmMapButton()?.addEventListener('click', confirmMap);
}());
