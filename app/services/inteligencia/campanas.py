from __future__ import annotations

from datetime import date

from app.models import CrmPlantilla
from app.services.inteligencia.common import formatear_rango


def obtener_sugerencias_campanas(
    fecha_corte: date,
    periodo_actual: dict,
    clientes: dict,
    tienda: dict,
    inventario: dict,
) -> dict:
    plantillas = _listar_plantillas_activas()
    campanas = _construir_campanas(fecha_corte, clientes, tienda, inventario, plantillas)
    automatizaciones = _construir_automatizaciones(fecha_corte, clientes, tienda, inventario)

    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    campanas.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))
    automatizaciones.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))

    return {
        'periodo_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': {
            'campanas_activables': len(campanas),
            'automatizaciones_sugeridas': len(automatizaciones),
        },
        'campanas': campanas[:3],
        'automatizaciones': automatizaciones[:3],
    }


def _construir_campanas(
    fecha_corte: date,
    clientes: dict,
    tienda: dict,
    inventario: dict,
    plantillas: list[CrmPlantilla],
) -> list[dict]:
    campanas = []
    clientes_para_activar = clientes.get('clientes_para_activar', [])
    plantilla_reactivacion = _resolver_plantilla(plantillas, ['reactivacion', 'seguimiento', 'beneficio'])
    plantilla_beneficio = _resolver_plantilla(plantillas, ['beneficio', 'fidelizacion', 'vip'])
    plantilla_producto = _resolver_plantilla(plantillas, ['promocion', 'producto', 'oferta'])

    if clientes.get('valiosos_dormidos', 0) > 0:
        muestra = _tomar_nombres(clientes_para_activar, cantidad=3, prioridad='alta')
        campanas.append({
            'prioridad': 'alta',
            'titulo': 'Reactivar clientes valiosos dormidos',
            'segmento': 'Alto valor',
            'cantidad_objetivo': clientes['valiosos_dormidos'],
            'cantidad_objetivo_label': _formatear_cantidad(clientes['valiosos_dormidos'], 'cliente'),
            'canal': 'WhatsApp o llamada',
            'detalle': (
                f"Hay clientes con buen gasto acumulado fuera de su ritmo normal al {fecha_corte.strftime('%d/%m/%Y')}."
            ),
            'accion': 'Preparar un beneficio corto y ejecutar contacto prioritario en las próximas 48 horas.',
            'muestra': muestra,
            **_datos_plantilla(
                plantilla_beneficio,
                _mensaje_fallback(
                    'Hola, tenemos un beneficio especial para vos y queríamos ayudarte a retomar tu próxima compra.',
                    muestra,
                ),
            ),
        })

    if clientes.get('frecuentes_en_pausa', 0) > 0:
        muestra = _tomar_nombres(clientes_para_activar, cantidad=3, accion='Enviar reactivación')
        campanas.append({
            'prioridad': 'media',
            'titulo': 'Recuperar clientes frecuentes en pausa',
            'segmento': 'Frecuencia perdida',
            'cantidad_objetivo': clientes['frecuentes_en_pausa'],
            'cantidad_objetivo_label': _formatear_cantidad(clientes['frecuentes_en_pausa'], 'cliente'),
            'canal': 'WhatsApp',
            'detalle': 'Conviene recordar la recurrencia que ya tenían antes de que se enfríe la relación.',
            'accion': 'Enviar reactivación simple con recordatorio de recompra o novedad de catálogo.',
            'muestra': muestra,
            **_datos_plantilla(
                plantilla_reactivacion,
                _mensaje_fallback(
                    'Hola, hace un tiempo no sabemos de vos. Si querés, te ayudamos a repetir tu compra de forma rápida.',
                    muestra,
                ),
            ),
        })

    if inventario.get('resumen', {}).get('stock_inmovilizado', 0) > 0:
        productos = _tomar_productos(inventario.get('stock_inmovilizado', []))
        campanas.append({
            'prioridad': 'media',
            'titulo': 'Mover stock inmovilizado con promoción puntual',
            'segmento': 'Salida de inventario',
            'cantidad_objetivo': inventario['resumen']['stock_inmovilizado'],
            'cantidad_objetivo_label': _formatear_cantidad(inventario['resumen']['stock_inmovilizado'], 'producto'),
            'canal': 'Difusión o estado',
            'detalle': 'Hay capital detenido en productos sin salida reciente que conviene volver a poner en circulación.',
            'accion': 'Armar promo corta, combo o liquidación selectiva para recuperar rotación.',
            'muestra': productos,
            **_datos_plantilla(
                plantilla_producto,
                _mensaje_fallback(
                    'Tenemos productos destacados con promo por tiempo limitado. Es una buena ventana para acelerar su salida.',
                    productos,
                ),
            ),
        })
    elif inventario.get('resumen', {}).get('atencion_sin_rotacion', 0) > 0 or tienda.get('productos_atencion'):
        productos = _tomar_productos(inventario.get('atencion_sin_rotacion', []) or tienda.get('productos_atencion', []))
        campanas.append({
            'prioridad': 'media',
            'titulo': 'Empujar productos con interés y baja salida',
            'segmento': 'Interés desaprovechado',
            'cantidad_objetivo': max(
                inventario.get('resumen', {}).get('atencion_sin_rotacion', 0),
                len(tienda.get('productos_atencion', [])),
            ),
            'cantidad_objetivo_label': _formatear_cantidad(
                max(
                    inventario.get('resumen', {}).get('atencion_sin_rotacion', 0),
                    len(tienda.get('productos_atencion', [])),
                ),
                'producto',
            ),
            'canal': 'WhatsApp o redes',
            'detalle': 'Los productos ya generan atención real, así que conviene insistir con una oferta o mensaje más claro.',
            'accion': 'Reforzar propuesta de valor, precio o CTA sobre los productos con más miradas.',
            'muestra': productos,
            **_datos_plantilla(
                plantilla_producto,
                _mensaje_fallback(
                    'Estos productos ya están llamando la atención. Vale la pena destacarlos mejor para convertir ese interés en venta.',
                    productos,
                ),
            ),
        })

    if not campanas:
        campanas.append({
            'prioridad': 'baja',
            'titulo': 'Todavía no hay campaña prioritaria',
            'segmento': 'Radar inicial',
            'cantidad_objetivo': 0,
            'cantidad_objetivo_label': '0 contactos',
            'canal': 'Seguimiento manual',
            'detalle': 'El período actual no muestra un segmento o producto que justifique una campaña dedicada.',
            'accion': 'Seguir acumulando datos para habilitar sugerencias más específicas.',
            'muestra': '',
            **_datos_plantilla(
                None,
                'Todavía no hay una plantilla prioritaria porque el radar no detecta un grupo suficientemente fuerte.',
            ),
        })

    return campanas


def _construir_automatizaciones(
    fecha_corte: date,
    clientes: dict,
    tienda: dict,
    inventario: dict,
) -> list[dict]:
    automatizaciones = []

    if clientes.get('total_para_activar', 0) > 0:
        automatizaciones.append({
            'prioridad': 'alta',
            'titulo': 'Cola diaria de reactivación',
            'detalle': (
                f"Cada mañana, detectar clientes con más de 45 días sin compra y dejarles una tarea lista al corte {fecha_corte.strftime('%d/%m/%Y')}."
            ),
            'accion': 'Crear una salida diaria con prioridad y mensaje sugerido para el equipo comercial.',
        })

    if inventario.get('hay_senales_tienda') and inventario.get('resumen', {}).get('atencion_sin_rotacion', 0) > 0:
        automatizaciones.append({
            'prioridad': 'media',
            'titulo': 'Seguimiento a interés sin salida',
            'detalle': 'Cuando un producto tenga varias visitas o consultas sin ventas, dejarlo marcado para revisión comercial.',
            'accion': 'Disparar una alerta que proponga revisar precio, publicación o seguimiento por WhatsApp.',
        })

    if inventario.get('resumen', {}).get('riesgo_quiebre', 0) > 0:
        automatizaciones.append({
            'prioridad': 'media',
            'titulo': 'Aviso interno por quiebre probable',
            'detalle': 'Los productos con salida rápida y cobertura corta pueden entrar a una cola interna de reposición.',
            'accion': 'Notificar al responsable para revisar compra o redistribución antes de perder ventas.',
        })

    if tienda.get('resumen', {}).get('consultas_iniciadas', 0) > 0 and tienda.get('productos_atencion'):
        automatizaciones.append({
            'prioridad': 'baja',
            'titulo': 'Seguimiento de consultas iniciadas',
            'detalle': 'Las consultas que nacen en tienda pueden transformarse en tareas breves de respuesta o cierre.',
            'accion': 'Armar una bandeja de seguimiento para leads con producto, horario pico y contexto del interés.',
        })

    if not automatizaciones:
        automatizaciones.append({
            'prioridad': 'baja',
            'titulo': 'Todavía no hay automatización urgente',
            'detalle': 'El radar actual no reúne suficiente señal repetitiva como para justificar un disparador fijo.',
            'accion': 'Esperar más volumen y revisar de nuevo cuando haya más recurrencia en clientes o tienda.',
        })

    return automatizaciones


def _listar_plantillas_activas() -> list[CrmPlantilla]:
    return (
        CrmPlantilla.query
        .filter(CrmPlantilla.activa.is_(True))
        .order_by(CrmPlantilla.orden.asc(), CrmPlantilla.titulo.asc())
        .all()
    )


def _resolver_plantilla(plantillas: list[CrmPlantilla], palabras_clave: list[str]) -> dict | None:
    if not plantillas:
        return None

    palabras = [_normalizar_texto(valor) for valor in palabras_clave if valor]
    for plantilla in plantillas:
        bolsa = ' '.join([
            _normalizar_texto(plantilla.categoria),
            _normalizar_texto(plantilla.titulo),
            _normalizar_texto(plantilla.contenido),
        ])
        if any(palabra in bolsa for palabra in palabras):
            return _serializar_plantilla(plantilla)

    for plantilla in plantillas:
        if _normalizar_texto(plantilla.categoria) == 'general':
            return _serializar_plantilla(plantilla)

    return _serializar_plantilla(plantillas[0])


def _serializar_plantilla(plantilla: CrmPlantilla) -> dict:
    return {
        'plantilla_id': int(plantilla.id),
        'plantilla_titulo': plantilla.titulo,
        'plantilla_categoria': (plantilla.categoria or 'general').strip() or 'general',
        'plantilla_preview': _recortar_texto(plantilla.contenido),
    }


def _datos_plantilla(plantilla: dict | None, fallback_preview: str) -> dict:
    if plantilla:
        return plantilla
    return {
        'plantilla_id': None,
        'plantilla_titulo': 'Mensaje sugerido',
        'plantilla_categoria': 'sugerida',
        'plantilla_preview': _recortar_texto(fallback_preview),
    }


def _normalizar_texto(valor: str | None) -> str:
    texto = (valor or '').strip().lower()
    reemplazos = {
        'á': 'a',
        'é': 'e',
        'í': 'i',
        'ó': 'o',
        'ú': 'u',
        'ñ': 'n',
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    return texto


def _formatear_cantidad(cantidad: int, etiqueta: str) -> str:
    return f'{cantidad} {etiqueta}' + ('' if cantidad == 1 else 's')


def _tomar_nombres(
    clientes: list[dict],
    cantidad: int,
    prioridad: str | None = None,
    accion: str | None = None,
) -> str:
    filtrados = clientes
    if prioridad:
        filtrados = [cliente for cliente in filtrados if cliente.get('prioridad') == prioridad]
    if accion:
        filtrados = [cliente for cliente in filtrados if cliente.get('accion') == accion]
    nombres = [cliente['nombre'] for cliente in filtrados[:cantidad]]
    return _unir_muestra(nombres)


def _tomar_productos(productos: list[dict], cantidad: int = 3) -> str:
    nombres = [producto['nombre'] for producto in productos[:cantidad]]
    return _unir_muestra(nombres)


def _unir_muestra(items: list[str]) -> str:
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} y {items[1]}'
    return f"{', '.join(items[:-1])} y {items[-1]}"


def _mensaje_fallback(base: str, muestra: str) -> str:
    if not muestra:
        return base
    return f'{base} Ejemplos para empezar: {muestra}.'


def _recortar_texto(texto: str, limite: int = 180) -> str:
    limpio = ' '.join((texto or '').split())
    if len(limpio) <= limite:
        return limpio
    return limpio[:limite - 1].rstrip() + '…'
