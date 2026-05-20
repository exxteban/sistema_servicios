/**
 * Sistema de Autorizaciones
 * Gestiona las solicitudes de autorización de administrador
 */

// Variable global para almacenar permisos del usuario
window.permisosUsuario = [];
window.rolUsuario = '';
window.esAdmin = false;
window.modoDemo = false;

/**
 * Carga los permisos del usuario actual
 */
async function cargarPermisosUsuario() {
    try {
        const response = await fetch('/api/autorizacion/permisos');
        if (response.ok) {
            const data = await response.json();
            window.permisosUsuario = data.permisos || [];
            window.rolUsuario = data.rol || '';
            window.esAdmin = data.es_admin || false;
            window.modoDemo = data.modo_demo || false;
        }
    } catch (error) {
        console.error('Error al cargar permisos:', error);
    }
}

/**
 * Verifica si el usuario tiene un permiso específico
 * @param {string} codigoPermiso - Código del permiso a verificar
 * @returns {boolean} True si tiene el permiso
 */
function tienePermiso(codigoPermiso) {
    return window.permisosUsuario.includes(codigoPermiso);
}

/**
 * Solicita autorización de administrador para una acción
 * @param {string} codigoPermiso - Código del permiso requerido
 * @param {string} accion - Descripción de la acción
 * @param {string} referenciaTipo - Tipo de referencia (ej: 'venta')
 * @param {number} referenciaId - ID de la referencia
 * @returns {Promise<object>} Resultado de la autorización
 */
function solicitarAutorizacion(codigoPermiso, accion, referenciaTipo = null, referenciaId = null) {
    return new Promise((resolve, reject) => {
        // Abrir modal usando evento de Alpine.js
        window.dispatchEvent(new CustomEvent('abrir-autorizacion', {
            detail: {
                codigoPermiso,
                accion,
                referenciaTipo,
                referenciaId
            }
        }));

        // Escuchar resultado
        const cleanup = () => {
            window.removeEventListener('autorizacion-exitosa', handleExito);
            window.removeEventListener('autorizacion-cancelada', handleCancel);
        };

        const handleExito = (event) => {
            cleanup();
            resolve(event.detail);
        };

        const handleCancel = () => {
            cleanup();
            reject(new Error('Autorización cancelada'));
        };

        window.addEventListener('autorizacion-exitosa', handleExito, { once: true });
        window.addEventListener('autorizacion-cancelada', handleCancel, { once: true });

        // Timeout de 5 minutos
        setTimeout(() => {
            cleanup();
            reject(new Error('Timeout de autorización'));
        }, 300000);
    });
}

/**
 * Ejecuta una acción que puede requerir autorización
 * @param {string} codigoPermiso - Código del permiso requerido
 * @param {string} accion - Descripción de la acción
 * @param {function} callback - Función a ejecutar si se autoriza
 * @param {string} referenciaTipo - Tipo de referencia
 * @param {number} referenciaId - ID de la referencia
 */
async function ejecutarConAutorizacion(codigoPermiso, accion, callback, referenciaTipo = null, referenciaId = null) {
    try {
        // Verificar si el usuario ya tiene el permiso
        if (!tienePermiso(codigoPermiso)) {
            window.mostrarNotificacion('No tienes permisos para esta acción', 'error');
            return;
        }

        // Verificar si requiere autorización
        const response = await fetch(`/api/autorizacion/verificar/${codigoPermiso}`);
        const data = await response.json();

        let idAutorizacion = null;

        if (data.requiere_autorizacion && !window.esAdmin) {
            // Solicitar autorización
            const autorizacion = await solicitarAutorizacion(codigoPermiso, accion, referenciaTipo, referenciaId);
            idAutorizacion = autorizacion.id_autorizacion;
        }

        // Ejecutar callback
        return await callback(idAutorizacion);

    } catch (error) {
        console.error('Error en autorización:', error);
        if (error.message !== 'Timeout de autorización' && error.message !== 'Autorización cancelada') {
            window.mostrarNotificacion('Error al solicitar autorización', 'error');
        }
        throw error;
    }
}

/**
 * Oculta/muestra elementos según permisos
 */
function aplicarPermisosUI() {
    console.log('🔒 Aplicando permisos UI - Total permisos:', window.permisosUsuario);

    // Buscar todos los elementos con data-permiso
    document.querySelectorAll('[data-permiso]').forEach(elemento => {
        const permiso = elemento.getAttribute('data-permiso');
        const tieneElPermiso = tienePermiso(permiso);

        console.log(`📋 Elemento con permiso "${permiso}":`, {
            tienePermiso: tieneElPermiso,
            tag: elemento.tagName,
            id: elemento.id,
            text: elemento.textContent?.substring(0, 30)
        });

        if (!tieneElPermiso) {
            const esModoDemo = window.modoDemo === true;
            const msg = esModoDemo ? 'Modo demo: esta acción está deshabilitada' : 'No tienes permisos para esta acción';

            console.log(`❌ SIN PERMISO - Bloqueando elemento:`, {
                permiso,
                modoDemo: esModoDemo,
                tag: elemento.tagName
            });

            // Marcar elemento visualmente
            if (elemento.dataset.permisoInterceptado === '1') return;
            elemento.dataset.permisoInterceptado = '1';
            elemento.title = msg;
            elemento.classList.add('opacity-50', 'cursor-not-allowed');

            const tag = (elemento.tagName || '').toUpperCase();

            // Para botones y enlaces, interceptar el click
            if (tag === 'A' || tag === 'BUTTON') {
                elemento.addEventListener('click', (e) => {
                    console.log('🚫 CLICK BLOQUEADO en', tag, '- Sin permiso:', permiso);
                    e.preventDefault();
                    e.stopPropagation();
                    if (window.mostrarNotificacion) {
                        window.mostrarNotificacion(msg, 'warning');
                    }
                }, { capture: true });

                // Deshabilitar si es un botón
                if (tag === 'BUTTON') {
                    elemento.disabled = true;
                }
                return;
            }

            // Para inputs tipo submit or button
            if (tag === 'INPUT') {
                const type = (elemento.getAttribute('type') || '').toLowerCase();
                if (type === 'submit' || type === 'button') {
                    elemento.addEventListener('click', (e) => {
                        console.log('🚫 CLICK BLOQUEADO en INPUT', type, '- Sin permiso:', permiso);
                        e.preventDefault();
                        e.stopPropagation();
                        if (window.mostrarNotificacion) {
                            window.mostrarNotificacion(msg, 'warning');
                        }
                    }, { capture: true });
                }
                elemento.disabled = true;
                return;
            }

            // Para otros elementos, simplemente ocultar
            elemento.style.display = 'none';
        }
    });

    console.log('✅ Permisos UI aplicados');
}

async function manejarSubmitConAutorizacion(event) {
    const form = event.target;
    if (!form || form.dataset.procesandoAutorizacion === '1') {
        return;
    }

    const codigoPermiso = form.getAttribute('data-codigo-permiso');
    const accion = form.getAttribute('data-accion') || 'Acción crítica';
    const confirmMsg = form.getAttribute('data-confirm');

    if (!codigoPermiso) {
        return;
    }

    event.preventDefault();

    if (confirmMsg && !window.confirm(confirmMsg)) {
        return;
    }

    await ejecutarConAutorizacion(codigoPermiso, accion, async (idAutorizacion) => {
        if (idAutorizacion) {
            const input = form.querySelector('input[name="id_autorizacion"]');
            if (input) {
                input.value = String(idAutorizacion);
            }
        }
        form.dataset.procesandoAutorizacion = '1';
        form.submit();
    });
}

function inicializarAutorizacionesEnForms() {
    document.querySelectorAll('form[data-autorizacion-form="1"]').forEach(form => {
        form.addEventListener('submit', manejarSubmitConAutorizacion);
    });
}

function setByPath(obj, path, value) {
    if (!obj || !path) return false;
    const keys = path.split('.');
    let current = obj;
    for (let i = 0; i < keys.length - 1; i += 1) {
        const key = keys[i];
        if (!Object.prototype.hasOwnProperty.call(current, key) || current[key] == null) {
            return false;
        }
        current = current[key];
    }
    current[keys[keys.length - 1]] = value;
    return true;
}

function getByPath(obj, path) {
    if (!obj || !path) return undefined;
    const keys = path.split('.');
    let current = obj;
    for (let i = 0; i < keys.length; i += 1) {
        if (current == null || !Object.prototype.hasOwnProperty.call(current, keys[i])) {
            return undefined;
        }
        current = current[keys[i]];
    }
    return current;
}

function removerIndicadoresSwitchDistribucion() {
    const selectors = [
        "span[x-text*=\"timeout_no_aceptado.enabled\"]",
        "span[x-text*=\"timeout_sin_respuesta.enabled\"]"
    ];
    document.querySelectorAll(selectors.join(',')).forEach((el) => el.remove());
}

function getRadioDistribucionDesdeTarget(target) {
    if (!target) return null;
    const nodo = target.nodeType === Node.TEXT_NODE ? target.parentElement : target;
    if (!nodo || typeof nodo.closest !== 'function') return null;

    let radio = nodo.closest('input[type="radio"][x-model]');
    if (radio) return radio;

    const label = nodo.closest('label');
    if (!label) return null;
    radio = label.querySelector('input[type="radio"][x-model]');
    return radio || null;
}

function setValorModeloRadio(radio, data, model, value) {
    if (radio && radio._x_model && typeof radio._x_model.set === 'function') {
        radio._x_model.set(value);
        return true;
    }
    return setByPath(data, model, value);
}

const MARCA_RADIO_RECLICK = 'distribucionReclick';

function getValorModeloRadio(radio, data, model) {
    if (radio && radio._x_model && typeof radio._x_model.get === 'function') {
        return radio._x_model.get();
    }
    if (data && model) {
        return getByPath(data, model);
    }
    return undefined;
}

function marcarRadioPendienteDeseleccion(event) {
    const radio = getRadioDistribucionDesdeTarget(event.target);
    if (!radio) return;

    const model = radio.getAttribute('x-model') || '';
    const isDistribucionAccion = /distribucion\.timeout_(no_aceptado|sin_respuesta)\.accion/.test(model);
    if (!isDistribucionAccion) return;

    let data = null;
    const root = radio.closest('[x-data]');
    if (window.Alpine && typeof window.Alpine.$data === 'function' && root) {
        data = window.Alpine.$data(root);
    }
    const valorActual = getValorModeloRadio(radio, data, model);
    const estabaSeleccionado = valorActual === radio.value || radio.checked === true;
    radio.dataset[MARCA_RADIO_RECLICK] = estabaSeleccionado ? '1' : '0';
}

function manejarToggleRadiosDistribucion(event) {
    const radio = getRadioDistribucionDesdeTarget(event.target);
    if (!radio) return;

    const model = radio.getAttribute('x-model') || '';
    const isDistribucionAccion = /distribucion\.timeout_(no_aceptado|sin_respuesta)\.accion/.test(model);
    if (!isDistribucionAccion) return;
    const fueReclick = radio.dataset[MARCA_RADIO_RECLICK] === '1';
    if (!fueReclick) return;

    let data = null;
    const root = radio.closest('[x-data]');
    if (window.Alpine && typeof window.Alpine.$data === 'function' && root) {
        data = window.Alpine.$data(root);
    }

    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === 'function') {
        event.stopImmediatePropagation();
    }

    setValorModeloRadio(radio, data, model, null);

    const limpiarSeleccionVisual = () => {
        radio.checked = false;
        radio.removeAttribute('checked');
        radio.defaultChecked = false;
        delete radio.dataset[MARCA_RADIO_RECLICK];
    };
    limpiarSeleccionVisual();
    queueMicrotask(limpiarSeleccionVisual);
}

let interaccionesDistribucionInicializadas = false;

function inicializarInteraccionesDistribucion() {
    if (interaccionesDistribucionInicializadas) return;
    interaccionesDistribucionInicializadas = true;
    removerIndicadoresSwitchDistribucion();
    document.addEventListener('pointerdown', marcarRadioPendienteDeseleccion, true);
    document.addEventListener('mousedown', marcarRadioPendienteDeseleccion, true);
    document.addEventListener('touchstart', marcarRadioPendienteDeseleccion, true);
    document.addEventListener('click', manejarToggleRadiosDistribucion, true);
    const observer = new MutationObserver(() => removerIndicadoresSwitchDistribucion());
    observer.observe(document.body, { childList: true, subtree: true });
}

// Cargar permisos al cargar la página
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        await cargarPermisosUsuario();
        aplicarPermisosUI();
        inicializarAutorizacionesEnForms();
        inicializarInteraccionesDistribucion();
    });
} else {
    // DOM ya cargado
    cargarPermisosUsuario().then(() => {
        aplicarPermisosUI();
        inicializarAutorizacionesEnForms();
        inicializarInteraccionesDistribucion();
    });
}
