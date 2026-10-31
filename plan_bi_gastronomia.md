# Plan de evolución del BI para gastronomía

Fecha: 31/10/2026. Estado: propuesta de implementación por fases (revisión 2, reorientada a generar ventas).

Este documento organiza el trabajo; sus casillas pendientes no representan funcionalidades implementadas. No establece fechas de entrega: el esfuerzo se ajustará después de la fase 0. Los avances documentados de otros módulos conservan sus propios planes y validaciones.

## 1. Objetivo de producto

Ayudar al dueño de un pequeño negocio gastronómico a **conseguir más pedidos y que sus clientes vuelvan**, con acciones concretas que pueda hacer en pocos minutos, y hacer visible el resultado de esas acciones.

El cliente que abandona el sistema suele ser el que vende poco. Ese negocio tiene poco historial, así que un BI que solo analiza ventas pasadas le dirá casi siempre «datos insuficientes». Por eso el plan se ordena así:

1. **Primero generar demanda** con lo que funciona sin historial: canal propio (tienda online, QR, link en redes), clientes identificados por teléfono y mensajes de regreso.
2. **Después optimizar** con análisis: acciones priorizadas, menú rentable, días flojos y preparación.
3. **Siempre mostrar el valor**: qué hizo el dueño con el sistema y qué ocurrió después.

El ciclo que debe resolver el producto es:

**Detectar una oportunidad → explicar la evidencia → preparar una acción → registrar su ejecución → medir el resultado → ajustar la recomendación.**

Para el proveedor del sistema, la hipótesis es que el valor visible mejora la continuidad de uso. Se valida con el piloto; no se asume.

### Principios

- Cada entrega debe aportar algo útil a un negocio **con poco o ningún historial**. Si una función solo sirve con meses de datos, no va primero.
- Mostrar como máximo tres acciones prioritarias en la portada; conservar el detalle en vistas secundarias.
- Usar lenguaje cotidiano: pedidos, platos, clientes que vuelven y dinero estimado que queda.
- Explicar por qué se recomienda algo, qué datos se usaron y qué información falta.
- Preferir acciones de un clic o pocos minutos: mensaje listo, link listo, QR listo.
- No recomendar descuentos sistemáticamente ni promociones sin evaluar sus costos disponibles.
- Evitar recomendaciones comerciales que agraven faltantes o saturación de cocina.
- Mantener pedidos, cocina y caja operativos aunque falle el BI.
- Usar reglas y cálculos verificables como base. La IA generativa solo redacta o explica y nunca decide.

### Decisión sobre WhatsApp

**Este plan no usa la WhatsApp Cloud API** (`app/services/whatsapp/`, Graph API). Todo contacto se hace con **enlaces `wa.me` con texto precargado**, que abren el WhatsApp del propio negocio; el dueño pulsa enviar. Ese patrón ya existe en gastronomía (`inteligencia_clientes.py` y `whatsapp_pedido_url` en `cliente_final_service.py`).

Consecuencias de diseño:

- El sistema **no puede saber** si el mensaje se envió, llegó o se leyó; solo registra lo que el dueño marca.
- El envío es uno por uno. Para que sea rápido se usa una **cola de envío asistido** (fase 2): abrir, enviar, volver, siguiente.
- Enviar muchos mensajes no solicitados desde un número común puede provocar bloqueos de WhatsApp. Se limitan las tandas diarias, se contacta solo a clientes que ya compraron y se respeta «no quiero recibir mensajes».

## 2. Punto de partida y reutilización

Inventario obtenido del código. La fase 0 confirma contratos y comportamiento antes de modificar cada área.

### Piezas para generar demanda (casi no usadas por el BI actual)

| Pieza existente | Ubicación | Uso previsto |
| --- | --- | --- |
| Tienda online con pedidos gastronómicos | `tienda_online/`, `app/services/tienda_gastronomia_catalogo.py` | Canal propio sin comisión; destino de los links de mensajes y QR. |
| Visitas e intenciones de la tienda | `TiendaVisitaEvento`, `TiendaLead`, `app/services/tienda_estadisticas.py` | Medir visitas, platos vistos y pedidos web; detectar «miran pero no piden». |
| Promociones de la tienda | `app/services/tienda_promociones.py`, `TiendaPromocionGastronomiaProducto` | Mecanismo de ejecución de promociones de las fases 6 y 4; no crear otro. |
| Versión directa para QR o chat | `app/templates/tienda_admin/panel.html` | Generar QR de mesa, bolsa y mostrador en la activación comercial. |
| Origen del pedido y cliente final | `GastronomiaPedido.origen_pedido`, `cliente_final_id`, `gastronomia/customer_models.py`, `cliente_final_service.py` | Separar canal propio de apps; identidad por teléfono. |
| Precios por plataforma externa | `gastronomia/services/channel_price_service.py` (PedidosYa, Monchis) | Comparar canal propio contra apps y estimar comisión evitada. |
| Fidelización por compras | `app/services/clientes_fidelizacion*.py` | Incentivo para dejar el teléfono y volver; revisar si aplica a pedidos de gastronomía. |
| Enlaces `wa.me` con texto | `inteligencia_clientes.py`, `cliente_final_service.whatsapp_pedido_url` | Base de la cola de envío asistido. |
| Imágenes del menú | `gastronomia/services/menu_image_service.py` | Material para publicaciones y mensajes. |
| Proveedor de IA existente | `app/services/ia/gpt_service.py`, `app/services/ia_backoffice/` | Redacción opcional de mensajes y publicaciones, después del MVP; no agregar otro proveedor. |

### Piezas de análisis

| Pieza existente | Ubicación | Tratamiento previsto |
| --- | --- | --- |
| Panel y acciones comerciales generales | `app/services/inteligencia/comercial.py`, `panel.py` | Integrar la experiencia gastronómica sin duplicar alertas ni alterar otros rubros. |
| BI gastronómico: ventas, ticket, canales, horarios y cocina | `gastronomia/services/inteligencia_service.py` | Reutilizar consultas válidas y separar responsabilidades al crecer. |
| Radar y tarjetas gastronómicas | `app/templates/inteligencia/gastronomia/` | Evolucionar hacia acciones con estado, evidencia y seguimiento. |
| Promociones por hora | `gastronomia/services/inteligencia_promos.py` | Corregir comparación temporal y convertir sugerencias en propuestas evaluables. |
| Clientes frecuentes | `gastronomia/services/inteligencia_clientes.py` | Extender con historial amplio, identidad confiable y detección de ausencia. |
| Alertas de margen y stock | `inteligencia_margen.py`, `inteligencia_stock.py` | Unificar bases de costo y vincular alertas con decisiones comerciales. |
| Costos y ganancia estimada | `costos_service.py`, `ganancia_service.py` | Distinguir margen de contribución y resultado estimado. |
| Sugerencias del POS | `gastronomia/services/sugerencias/` | Conectar con BI y ampliar solo lo faltante. |

El sugeridor del POS ya tiene reglas, asociaciones, complementos iniciales, filtros, fatiga y medición. **Este proyecto no construye un segundo sugeridor ni otro registro de exposición/aceptación.**

Referencias internas:

- [Plan del sugeridor y estado de implementación](plan_sugerencias_gastronomia.md).
- [Complementos gastronómicos iniciales](docs/sugerencias_gastronomia_complementos.md).
- [Diagnóstico y limitaciones de medición](docs/sugerencias_gastronomia_diagnostico.md).
- [Integración gastronómica](docs/gastronomia_integracion.md).
- [Producción gastronómica](docs/gastronomia_produccion.md).

### Brechas observadas

- El BI analiza ventas existentes pero no ayuda a conseguir pedidos nuevos ni a usar el canal propio.
- No se mide qué parte de los pedidos llega por canal propio ni cuántos tienen un cliente identificable.
- Las recomendaciones del radar son textos; falta un ciclo persistente de ejecución y evaluación.
- Los frecuentes se calculan dentro del período consultado; quien dejó de comprar puede quedar fuera.
- La identidad de frecuentes admite nombre como alternativa; no alcanza para contactar o atribuir retornos.
- Las promociones actuales agrupan horas de distintos días y parten de horas con ventas.
- El radar de margen usa costo de receta, mientras el servicio de costos también contempla costo extra.
- El dueño no ve en ningún lugar qué le aportó el sistema en el mes.

## 3. Experiencia propuesta

### Organización en pestañas

Cada fase suma información; si todo se apila en una vista, el dueño deja de mirarla. Por eso la experiencia se organiza en pestañas, con **una pregunta por pestaña** y poco desplazamiento vertical.

Hoy el tablero de inteligencia ya tiene pestañas (Resumen, Comercial, Operación, Gastronomía), y la pestaña Gastronomía apila KPIs, sugerencias, menú, radar y ritmo en una sola columna. Para no poner pestañas dentro de pestañas, la propuesta es una vista propia **«Tu negocio»** para instalaciones gastronómicas, con estas pestañas:

| Pestaña | Pregunta que responde | Contenido | Fases |
| --- | --- | --- | --- |
| **Hoy** | ¿Qué hago hoy? | Hasta 3 acciones y hasta 4 indicadores del día | 1–4 |
| **Clientes** | ¿A quién le escribo? | Cola de envío asistido; segmentos como filtros | 2 |
| **Crecer** | ¿Por dónde me llegan pedidos? | Lista de activación, canal propio frente a apps, embudo de la tienda | 1 |
| **Menú** | ¿Qué platos empujo o reviso? | Cuatro situaciones de platos, sugeridor y promociones | 5–6 |
| **Resultados** | ¿Sirvió lo que hice? | Reporte del mes, acciones en evaluación e historial | 3–4 |

Reglas de diseño:

- **Máximo cinco pestañas para el dueño.** Preparación, merma y demoras (fase 7) se suman a la pestaña Operación existente o se agregan como sexta solo cuando estén listas.
- **Sin pestañas anidadas.** Dentro de una pestaña se usan filtros tipo chip (por ejemplo, «Primera compra», «Ausentes», «Reseñas» en Clientes), no sub-pestañas.
- **Lo importante se ve sin desplazarse:** la respuesta principal de cada pestaña entra en la primera pantalla de una notebook de 1366×768 y de un celular. Lo demás va en «Ver más», con el modal de detalles existente (`_modal_detalles.html`).
- **Topes por vista:** hasta 3 tarjetas de acción y hasta 4 indicadores. Las listas largas (cola, platos, historial) se paginan o cargan de a poco.
- **Contadores en las pestañas** (por ejemplo, «Clientes 8») para saber dónde hay algo pendiente sin abrir cada una. Una pestaña sin novedades no muestra contador.
- **Carga por pestaña:** cada pestaña se pide al abrirla, como parcial, y no se calcula todo al entrar.
- **Enlaces directos:** cada acción abre la pestaña y el filtro correspondientes (por ejemplo, de Hoy a Clientes con «Ausentes»), y se recuerda la última pestaña abierta.
- **Estados vacíos de una línea** con un paso concreto, sin bloques grandes de «datos insuficientes».
- En celular, las pestañas son una barra horizontal desplazable y fija arriba; la cola de mensajes está pensada para usarse desde el teléfono.
- El panel de salud de uso (fase 3) no es una pestaña del dueño: es una vista aparte, solo para root.

### Pestaña «Hoy»

1. Hasta 4 indicadores: pedidos, ventas, ticket promedio y uno de crecimiento (canal propio o clientes identificados), con comparación con días equivalentes cuando haya datos.
2. **Tres acciones para hoy**, cada una con un único paso principal. Con poco historial, las acciones vienen de la activación comercial y de la recuperación de clientes, que no necesitan historial.
3. Nada más: el detalle vive en las otras pestañas.

Ejemplos ilustrativos, sin datos reales:

> **8 clientes habituales no volvieron esta semana.**
> Su última compra supera su intervalo habitual. Tenés un mensaje listo con el plato favorito de cada uno.
> **Acción:** enviar mensajes (8 en la cola, unos 3 minutos).

> **Solo 2 de cada 10 pedidos tienen teléfono del cliente.**
> Sin teléfono no podés avisarles cuando vuelvan a tener su plato favorito.
> **Acción:** activar el pedido de teléfono en el POS.

Cada tarjeta responde: qué ocurre, por qué importa, qué hacer, cuánto tiempo lleva y cuándo revisar el resultado. No mostrar ganancias potenciales numéricas sin un cálculo y supuestos verificables.

### Momentos de uso

- Antes del turno: acciones del día, faltantes y mensajes pendientes.
- Durante la venta: sugeridor existente y pedido de teléfono; sin avisos que interrumpan el cobro.
- Al cierre o semanalmente: qué se hizo, qué ocurrió después y qué conviene repetir.
- Una vez al mes: reporte de valor.

## 4. Roadmap y dependencias

| Fase | Entrega | Prioridad | Sirve sin historial | Dependencias |
| --- | --- | --- | --- | --- |
| 0 | Datos mínimos para empezar | Obligatoria | — | Ninguna |
| 1 | Canal propio y clientes identificados | Alta | Sí | 0 |
| 2 | Clientes que vuelven: cola de envío asistido | Alta | Parcial | 0 y 1 |
| 3 | Reporte de valor y salud de uso | Alta | Sí | 1 y 2 |
| 4 | Tres acciones para hoy con seguimiento | Alta | Parcial | 0–3 |
| 5 | Menú rentable e integración con el sugeridor | Media | No | 0 y 4; costos confiables |
| 6 | Días flojos y promociones medibles | Media | Parcial | 4 y 5 |
| 7 | Preparación, reposición, merma y capacidad | Baja | No | 0, 4 e historial operativo |
| 8 | Piloto y despliegue progresivo | Transversal | — | Se aplica a cada entrega |

**MVP recomendado: fases 0 a 3.** La fase 0 se limita a lo que necesitan esas entregas; el resto del diagnóstico de datos se hace antes de las fases que lo usan. La telemetría mínima (acciones vistas, iniciadas y completadas) se registra desde la fase 1.

## 5. Fase 0 — Datos mínimos para empezar

Solo lo imprescindible para las fases 1 a 3. Las definiciones de costos, turnos y comparaciones avanzadas se cierran al inicio de las fases 4 a 7.

### Trabajo

- [x] Definir pedido válido para contar pedidos y retornos: excluir anulaciones y documentar devoluciones, encargos y ventas importadas.
- [x] Confirmar los valores reales de `origen_pedido` y `canal_precio` y clasificarlos en canal propio (POS, tienda online, teléfono/WhatsApp) y plataformas externas (PedidosYa, Monchis).
- [ ] Auditar identidad de cliente final: normalización de teléfono, duplicados y separación respecto al `id_cliente` de la instalación; no agrupar personas solo por nombre.
- [ ] Medir cobertura actual: porcentaje de pedidos con cliente identificado por canal y por modalidad.
- [ ] Confirmar zona horaria local y días de apertura configurados, para no comparar días cerrados.
- [ ] Verificar si la fidelización por compras aplica a pedidos de gastronomía o si necesita un adaptador.
- [ ] Preparar escenarios ficticios: negocio nuevo sin historial, comida rápida con delivery y cafetería de mostrador.

### Criterios de aceptación

- Un pedido válido cuenta una sola vez y un pedido anulado no cuenta como retorno.
- Cada pedido queda clasificado como canal propio, plataforma externa o desconocido.
- Datos faltantes aparecen como desconocidos, no como cero.
- Se entrega un diccionario breve de métricas de las fases 1 a 3.

## 6. Fase 1 — Canal propio y clientes identificados

Objetivo: que el negocio tenga por dónde recibir pedidos sin comisión y que cada venta deje un cliente contactable. Funciona desde el primer día.

### Trabajo

- [ ] **Lista de activación comercial** con progreso visible: tienda online publicada con fotos y precios, horario cargado, QR impreso (mesa, mostrador, bolsa de delivery), link en la bio de Instagram y en el estado de WhatsApp, mensaje de bienvenida listo para copiar.
- [x] Detectar automáticamente lo que ya está hecho (tienda activa, platos sin foto o sin precio) y pedir confirmación manual solo de lo externo (bio de Instagram, QR impreso).
- [ ] Generar materiales listos: QR descargable e imprimible, texto para la bio, texto para el estado de WhatsApp con el link de la tienda.
- [x] Indicador **pedidos por canal propio frente a plataformas externas**, por semana.
- [x] **Comisión evitada estimada**: solo si el dueño configura el porcentaje de comisión de cada plataforma; sin dato, no se muestra.
- [x] Indicador **porcentaje de pedidos con cliente identificado**, por canal.
- [ ] En el POS, campo de teléfono rápido y visible para mostrador y retiro, opcional y sin bloquear el cobro; reutilizar la normalización existente.
- [ ] Mostrar al cajero un texto sugerido para pedir el teléfono, vinculado a la fidelización cuando esté activa («con tu número sumás para tu beneficio»).
- [ ] Registrar si el cliente aceptó recibir mensajes; por defecto, sin consentimiento confirmado no entra en las colas de la fase 2.
- [ ] Embudo de la tienda online con `TiendaVisitaEvento`: visitas, platos vistos y pedidos web, para detectar platos muy vistos y poco pedidos.

### Criterios de aceptación

- Un negocio sin ventas previas ve su lista de activación y al menos una acción útil.
- Pedir el teléfono no agrega pasos obligatorios ni demora el cobro.
- Un teléfono mal formado no crea un cliente nuevo duplicado.
- La comisión evitada no aparece si no hay porcentaje configurado.
- Los pedidos de plataformas externas no se cuentan como canal propio.

## 7. Fase 2 — Clientes que vuelven: cola de envío asistido

Objetivo: convertir clientes identificados en segundas compras y retornos, usando el WhatsApp del negocio sin API.

### Segmentos iniciales

| Segmento | Regla inicial | Con poco historial |
| --- | --- | --- |
| Primera compra sin segunda | Compró una vez hace entre X e Y días | Regla fija configurable (ejemplo: 5 a 15 días) |
| Habitual ausente | Superó su intervalo habitual de compra | Solo con al menos 3 compras previas |
| Favorito disponible | Su plato favorito vuelve a estar disponible o es novedad | No requiere historial del negocio |
| Pedido de reseña | Pedido entregado recientemente | Requiere link de reseña configurado |

### Trabajo

- [x] Consultar historial más amplio que el período visible para encontrar a quienes dejaron de comprar.
- [x] Calcular los segmentos con identidad estable por teléfono; resolver ambigüedades sin fusionar por nombre.
- [x] Mostrar última compra, frecuencia, plato favorito y por qué está en la lista.
- [x] **Plantillas de mensaje** editables por segmento, con variables (nombre, plato favorito, link de la tienda o del plato). Ofrecer valor sin descuento obligatorio: novedad, disponibilidad del favorito, recordatorio.
- [x] **Cola de envío asistido**: un cliente a la vez con el mensaje ya armado; botón «Abrir WhatsApp» (`wa.me` con texto), al volver «Enviado» u «Omitir», y pasa al siguiente.
- [x] Límite diario configurable de mensajes por cola y frecuencia máxima por cliente (ejemplo: uno cada 14 días).
- [x] Marca «no quiere mensajes» con un clic; ese cliente sale de todas las colas.
- [ ] Link de reseña de Google configurable; mensaje de reseña después de entregas, con el mismo límite.
- [ ] Opcional: exportar contactos con consentimiento para listas de difusión de WhatsApp Business, explicando que solo llegan a quien guardó el número del negocio.
- [x] Asociar compras posteriores al mensaje marcado como enviado, con ventana de observación por segmento y excluyendo anulaciones.

### Criterios de aceptación

- Un habitual ausente aparece aunque no haya comprado en el período actual del panel.
- Homónimos no se mezclan ni reciben atribuciones ajenas.
- Nadie recibe dos mensajes dentro de la frecuencia máxima ni después de marcar «no quiere mensajes».
- Abrir WhatsApp no marca el mensaje como enviado; solo la confirmación del dueño.
- El sistema no envía nada por su cuenta ni usa la WhatsApp Cloud API.
- El resultado se llama «volvió después del mensaje», sin afirmar causalidad.
- Sin clientes identificados, la pantalla explica cómo conseguirlos (fase 1) en lugar de quedar vacía.

## 8. Fase 3 — Reporte de valor y salud de uso

Objetivo: que el dueño vea lo que obtuvo y que el proveedor detecte a tiempo una instalación en riesgo.

### Reporte mensual para el dueño

- [ ] Resumen dentro del sistema, también descargable o imprimible para compartir, con:
  - pedidos y ventas por canal propio y su evolución;
  - comisión evitada estimada, si está configurada;
  - clientes nuevos identificados;
  - mensajes enviados y clientes que volvieron después del mensaje;
  - acompañamientos sugeridos aceptados y su importe (telemetría actual del sugeridor);
  - acciones completadas en el mes.
- [x] Redacción honesta: «después de», no «gracias a»; mostrar muestra y cobertura.
- [ ] Si el mes fue malo, proponer las tres acciones con más potencial en lugar de solo mostrar la caída.

### Salud de uso para el proveedor

- [ ] Panel visible solo para el usuario root dentro de **cada instalación**, sin centralizar datos ni comparar instalaciones: último uso del POS y del BI, porcentaje de la activación comercial completado, colas sin atender, tendencia de pedidos de las últimas semanas y funciones nunca usadas.
- [ ] Semáforo simple (activo, en riesgo, inactivo) con reglas explícitas y documentadas.
- [ ] Cualquier envío de esta información fuera de la instalación queda como decisión pendiente (sección 15) y requiere autorización del cliente.

### Criterios de aceptación

- El reporte coincide con los reportes existentes cuando usan la misma definición y período.
- Una métrica sin datos se omite o se marca como no disponible, nunca como cero.
- Un usuario no root no ve el panel de salud ni por UI ni por API.

## 9. Fase 4 — Tres acciones para hoy con seguimiento

Unifica el motor de oportunidades y el seguimiento. Las fuentes de acciones incluyen las fases 1 a 3 además de los detectores analíticos.

### Trabajo

- [ ] Contrato común de oportunidad: tipo, entidad afectada, evidencia, período, confianza, urgencia, tiempo estimado y acción disponible.
- [ ] Fuentes iniciales: pasos de activación pendientes, colas de mensajes, caída de pedidos, caída de ticket, falta de stock y revisión de margen (con los detectores actuales corregidos).
- [ ] **Acciones de calendario** que no necesitan historial, como reglas explícitas y configurables: cobro de quincena y fin de mes, feriados, fechas especiales y partidos importantes. Proponen preparar un mensaje o destacar un combo con anticipación.
- [ ] Separar observación de recomendación: una caída de ventas no demuestra su causa.
- [ ] Priorizar de forma explicable: primero lo que impide vender (faltantes, tienda caída), luego acciones rápidas con evidencia; sin puntajes monetarios ficticios.
- [ ] Persistir acciones con identificador estable para evitar duplicados en cada recálculo.
- [ ] Estados: pendiente, pospuesta, en curso, en evaluación, completada, descartada y vencida; validar transiciones.
- [ ] Motivo de descarte y posposición, sin volver a mostrar la misma alerta inmediatamente.
- [ ] Vincular cada acción a la pantalla existente con contexto precargado, respetando permisos.
- [ ] Guardar fecha, responsable, evidencia, acción realizada y ventana de evaluación por tipo de acción.
- [ ] Resumen antes del turno y cierre semanal dentro del sistema; silencio cuando no haya novedades.
- [ ] Acciones «repetir», «ajustar» y «dejar de recomendar» con motivo.
- [ ] Avisos de la portada y del BI general con estado y conteo compartidos.

### Criterios de aceptación

- Cada tarjeta tiene evidencia verificable, motivo y un paso concreto.
- Posponer, descartar o completar sobrevive a recarga y recálculo.
- Abrir una pantalla no marca una acción como ejecutada.
- Una acción sin muestra suficiente queda «sin evidencia suficiente», no como éxito o fracaso.
- Un usuario sin permiso de edición no puede ejecutar la acción por UI ni API.
- El BI no bloquea pedidos, cocina ni caja; ante un error muestra indisponibilidad o datos fechados.

## 10. Fase 5 — Menú rentable y sugerencias existentes

### Trabajo previo de datos

- [ ] Unificar semántica de costos: receta, extras y modificadores, descuentos, envases y comisiones registradas, sin contar el mismo costo dos veces.
- [ ] Indicar si el costo es histórico o estimado con precios actuales; no reconstruir ganancias históricas en silencio.

### Trabajo

- [ ] Clasificar platos por popularidad y contribución estimada, por categoría y canal.
- [ ] Cuatro situaciones: vende y aporta; vende pero aporta poco; aporta pero vende poco; baja venta y bajo aporte.
- [ ] Recomendar visibilidad, revisión de receta, porción o precio, o una prueba comercial; nunca retirar platos automáticamente.
- [ ] Para «aporta pero vende poco»: destacarlo en la tienda online, como foto principal o en un mensaje de novedad (reutilizar fases 1 y 2).
- [ ] Usar el embudo de la tienda: plato muy visto y poco pedido sugiere revisar foto, descripción o precio.
- [ ] Conectar oportunidades de acompañamientos con la administración y vista previa del sugeridor existente.
- [ ] Ordenar por contribución solo donde haya costos suficientes, manteniendo afinidad, reglas, exclusiones, stock, canal y fatiga.
- [ ] Revalidar disponibilidad y precios al ejecutar una acción guardada.

### Criterios de aceptación

- Un plato sin costos completos no se clasifica como altamente rentable.
- El BI y los reportes coinciden con la misma definición, período y base de costos.
- No aparecen un segundo sugeridor ni eventos equivalentes a los existentes.
- Se conservan los flujos de modificadores, peso, edición, canal y cobro del POS.

## 11. Fase 6 — Días flojos y promociones medibles

### Trabajo previo de datos

- [ ] Turnos que cruzan medianoche, cierres excepcionales y comparación al mismo corte horario.
- [ ] Mínimo de observaciones por indicador. Propuesta inicial: entre 4 y 8 días equivalentes, calibrado con históricos.

### Trabajo

- [ ] Analizar días, turnos y canales equivalentes, incluyendo horas abiertas con cero pedidos.
- [ ] Identificar si la baja está en cantidad de pedidos, ticket o mezcla de platos; presentar hipótesis por separado.
- [ ] Proponer acciones con productos concretos, horario, canal, duración, stock y capacidad.
- [ ] Ejecutar promociones con `tienda_promociones` y los combos existentes; no crear otro mecanismo.
- [ ] Cada promoción genera su mensaje y su texto para el estado de WhatsApp o Instagram, para la cola de la fase 2.
- [ ] Calcular contribución estimada después del beneficio y costos variables conocidos; mostrar costos faltantes.
- [ ] Revisión y activación explícita por el dueño; sin cambios automáticos de precio ni publicaciones automáticas.
- [ ] Medir pedidos, ticket, descuento y contribución frente a períodos equivalentes, y posibles desplazamientos entre horarios o productos.
- [ ] Después del MVP, redacción opcional de mensajes y publicaciones con el proveedor de IA existente, siempre editable por el dueño.

### Criterios de aceptación

- No se recomienda un producto agotado ni una franja cerrada.
- Una promoción puede subir la facturación y bajar la contribución; el resultado muestra ambas.
- Se distingue resultado observado de incremento causado.

## 12. Fase 7 — Preparación, disponibilidad y servicio

Mejora margen y operación más que ventas; por eso va al final.

### Trabajo

- [ ] Estimar demanda por turno con días equivalentes y un rango, con mínimos de datos por producto.
- [ ] Vincularla a recetas, existencias, reservas y producción registrada; revisar unidades fraccionarias.
- [ ] Proponer preparación y reposición con fundamento, sin emitir compras automáticamente.
- [ ] Incorporar merma registrada y límites de conservación cuando existan datos; no inventar vencimientos.
- [ ] Detectar demoras por turno, producto y modalidad con umbrales configurables.
- [ ] No impulsar demanda (fases 2 y 6) cuando hay faltantes críticos o cocina saturada.

### Criterios de aceptación

- La previsión informa rango, muestra y fecha; con pocos datos ofrece orientación manual.
- Las cantidades respetan unidades y no duplican producción o reservas existentes.
- Las alertas distinguen demoras registradas de causas no comprobadas.

## 13. Arquitectura y compatibilidad

- Una instalación independiente por cliente; sin infraestructura multi-tenant ni comparaciones entre instalaciones.
- Preservar `id_cliente`/`cliente_id`, verificando el significado de cada campo, y filtrar en lecturas, escrituras, tareas y cachés.
- Antes de crear servicios, modelos o utilidades, buscar implementaciones existentes con CodeGraph y revisar sus contratos.
- Separar detectores, priorización, persistencia, colas de mensajes, reporte y evaluación en archivos pequeños. Ningún archivo nuevo o modificado supera 600 líneas.
- Paquete `gastronomia/services/bi/` para las responsabilidades nuevas (por ejemplo `activacion.py`, `segmentos.py`, `cola_mensajes.py`, `plantillas.py`, `reporte_valor.py`, `salud_uso.py`), con los servicios existentes como adaptadores.
- Rutas delgadas, plantillas parciales y scripts acotados; no agregar todo a `inteligencia_service.py` o `comercial.py`.
- Una plantilla parcial y un endpoint por pestaña de «Tu negocio», compatibles con el motor de pestañas existente (`?partial=1`); reutilizar el patrón `role="tablist"` del tablero de inteligencia.
- Nuevos modelos previstos: acción/oportunidad, eventos de seguimiento, contacto de cola (cliente, segmento, plantilla, estado, fecha) y preferencia de contacto del cliente final. Reutilizar identidad, pedidos, promociones y telemetría actuales.
- Los enlaces de WhatsApp se generan con una utilidad compartida a partir de la existente en `cliente_final_service.py`; no usar `app/services/whatsapp/`.
- Clave de deduplicación por instalación, detector, entidad y ventana; registrar versión de regla y evidencia.
- Migraciones aditivas, campos con valores por defecto o nulos; preservar registros anteriores.
- Cálculos pesados fuera del pedido, el cobro y la carga interactiva, reutilizando patrones existentes de tareas y candados.
- Conservar el último resultado válido con fecha ante fallos.
- Permisos de lectura separados de acciones que editan, activan promociones o preparan contactos; validación de servidor y CSRF.
- Cualquier cambio en la tienda online queda dentro de `/tienda_online` y consume `/api/tienda/...`; no importar código del backoffice desde la tienda.
- En el MVP: sin proveedores de IA nuevos, sin WhatsApp Cloud API ni mensajería automática, y sin cambios automáticos de precio.

## 14. Validación y liberación por entrega

### Pruebas relevantes

- Cálculos: pedidos válidos, anulaciones, clasificación de canal, pocos datos, días cerrados y costos incompletos.
- Identidad y contacto: teléfonos normalizados, homónimos, duplicados, consentimiento, «no quiere mensajes», frecuencia máxima y límite diario.
- Cola: enviar, omitir, recargar y retomar sin duplicar contactos; retorno dentro y fuera de ventana.
- Aislamiento y permisos: dos contextos de cliente, acceso directo a API, panel root, caché y tareas.
- Estado: recálculos, solicitudes repetidas, transiciones inválidas, caducidad y persistencia de descartes.
- Integración: oportunidad → mensaje o pantalla → pedido válido → resultado → reporte mensual.
- Regresión: BI general, gastronomía desactivada, otros rubros, POS, cocina, caja, tienda online y sugeridor.
- UI: escritorio y móvil (la cola se usará mucho desde el celular), tema claro/oscuro, estados vacíos y error; topes por vista, respuesta principal visible sin desplazarse, carga por pestaña y enlaces directos a pestaña y filtro.
- Rendimiento: historial y catálogo representativos, latencia HTTP y fallos de tareas.
- Base de datos: migraciones y consultas en los motores soportados, con datos ficticios.

Reutilizar `test_inteligencia_comercial.py`, `test_inteligencia_bi_context.py`, `test_gastronomia_reportes.py`, `test_gastronomia_ganancia.py`, `test_tienda_estadisticas_panel.py`, `test_clientes_fidelizacion.py` y las suites del sugeridor. Agregar pruebas de comportamiento para los riesgos nuevos.

### Piloto y salida gradual

- [ ] Elegir instalaciones autorizadas, **incluyendo al menos una con pocas ventas**, y registrar una línea base.
- [ ] Liberar por configuración de instalación, empezando por la activación comercial y la cola de mensajes.
- [ ] Acompañar la primera semana: completar la activación con el dueño y enviar juntos la primera cola.
- [ ] Revisar avisos descartados, colas abandonadas, falsos positivos y tiempo de uso.
- [ ] Definir objetivos cuantitativos después de la línea base; no prometer porcentajes sin evidencia.
- [ ] Permitir desactivar la experiencia conservando historial, reportes y operación.

## 15. Cómo medir si sirve

| Dimensión | Indicadores | Interpretación |
| --- | --- | --- |
| Activación | Pasos de activación completados, tienda con pedidos | Sin canal propio no hay base para crecer. |
| Canal propio | Pedidos propios frente a plataformas, comisión evitada | Comisión solo con porcentaje configurado. |
| Clientes | Porcentaje de pedidos identificados, clientes con consentimiento | Base de todo lo que sigue. |
| Retorno | Segunda compra y retorno después del mensaje | Solo clientes identificables; informar cobertura. |
| Utilidad | Acciones vistas, iniciadas, completadas y descartadas; colas atendidas | Abrir una tarjeta no es hacer la acción. |
| Venta | Pedidos, ticket y acompañamientos por pedido | Comparar períodos equivalentes. |
| Margen | Contribución estimada y descuentos | Informar costos faltantes; no llamarlo ganancia neta. |
| Continuidad | Semáforo de salud de uso por instalación | Hipótesis del proveedor; datos dentro de cada instalación. |

## 16. Decisiones a cerrar

| Decisión | Momento | Propuesta inicial |
| --- | --- | --- |
| Rubros del piloto | Fase 0 | Comida rápida con delivery y cafetería; al menos un negocio con pocas ventas. |
| Clasificación de canales | Fase 0 | Según `origen_pedido` y `canal_precio` reales; desconocido como categoría propia. |
| Consentimiento de mensajes | Fase 1 | Registro explícito en POS y tienda; sin consentimiento no entra en colas. |
| Límite diario y frecuencia de mensajes | Fase 2 | Configurable; valores iniciales conservadores para evitar bloqueos de WhatsApp. |
| Ventanas de segunda compra y ausencia | Fase 2 | Reglas fijas con poco historial; recurrencia cuando haya evidencia. |
| Ubicación de «Tu negocio» | Fase 1 | Vista propia con 5 pestañas para gastronomía; la pestaña Gastronomía del tablero general enlaza a ella en vez de duplicar contenido. |
| Envío de la salud de uso al proveedor | Después del MVP | Por ahora solo visible dentro de cada instalación; exportarla requiere autorización. |
| WhatsApp Cloud API | Fuera del plan | No se usa; solo enlaces `wa.me`. |
| Redacción con IA | Después del MVP | Proveedor existente, editable, medido por costo y uso. |
| Definiciones de costos y turnos | Fases 5–6 | Una base compartida, coherente con reportes. |

## 17. Próxima unidad de trabajo

**Verificación pendiente:** ver en navegador la tarjeta «Clientes que vuelven» (BI-02) y el bloque «Tu mes en el sistema» (BI-03), en escritorio, celular y tema oscuro.

**BI-04: resto de la fase 1 y salud de uso.** Materiales de activación (QR, texto de bio y de estado de WhatsApp), teléfono rápido en el POS sin bloquear el cobro, registro de consentimiento para mensajes y embudo de la tienda online. Después, el panel de salud de uso solo para root (fase 3).

Actualizar este documento al cerrar cada entrega con alcance real, pruebas realizadas, limitaciones y siguiente paso. Marcar una casilla como terminada únicamente cuando la implementación y sus criterios de aceptación estén verificados.

## 18. Registro de entregas

### BI-01 — núcleo implementado (31/10/2026)

**Alcance real**

- Fase 0 (código): clasificación de pedidos y canales en `gastronomia/services/bi/pedidos_validos.py`; identidad por teléfono en `identidad.py`; cobertura por canal.
  - Valores confirmados en código: `origen_pedido` ∈ {`pos`, `tienda_online`, `importado`}; `canal_precio`, que vive en el ítem y no en el pedido, ∈ {`pedidosya`, `monchis`, nulo}.
  - Exclusiones: cancelados, importados y encargos. No hay devoluciones como estado: una anulación pasa a `cancelado`.
  - Teléfono/WhatsApp no es un origen propio: el pedido entra como `pos` con el teléfono cargado.
- Fase 1 parcial:
  - Lista de activación (`activacion.py`): pasos automáticos (platos, tienda, fotos, precios, horario) y pasos manuales (QR impreso, bio de Instagram, estado de WhatsApp) que confirma el dueño. Se guardan en `Configuracion` con la clave incluyendo el `id_cliente`.
  - Indicadores de canal propio frente a plataformas por semana, y cobertura de identidad por canal (`canales.py`).
- Presentación: bloque «Crecer» en el tab Gastronomía (`_crecer.html`, incluido desde `_tab_gastronomia.html`). Se calcula dentro de `obtener_inteligencia_gastronomia` con degradación segura (`crecer.py`). Ruta nueva `POST /gastronomia/bi/activacion/<paso>` con permiso `gastronomia_menu` y CSRF.

**Pruebas**

- `test_gastronomia_bi_fase0.py`: 11 pruebas nuevas, todas en verde. Cubren clasificación, exclusiones, pedido con varios ítems, identidad por teléfono sin mezclar nombres, cobertura nula, semanas, activación de negocio nuevo, detección de fotos y precios, aislamiento de pasos manuales por cliente, integración con el dashboard y el POST, y degradación del bloque.
- Suites `test_gastronomia_*`, `test_inteligencia_*` y `test_tienda_*`: 303 pasaron y 42 se omitieron. Las omitidas son las de MariaDB de `test_gastronomia_sugerencias_mysql.py`, que requieren `scripts/probar_sugerencias_mysql.py`.
- No verificado visualmente en navegador (layout, tema oscuro, celular). Solo se comprobó el HTML renderizado en las pruebas.

**Limitaciones y pendiente**

- Sin medición sobre datos reales: la cobertura actual de cada instalación queda para el piloto.
- `inteligencia_clientes.py` (frecuentes) todavía agrupa por nombre cuando no hay teléfono. Es una brecha ya registrada en la sección 2; el código nuevo no lo hace.
- Fuera de BI-01: comisión evitada (requiere porcentaje configurado), materiales (QR, textos de bio y de estado), mensaje de bienvenida, campo de teléfono en el POS, consentimiento, embudo de la tienda, y la vista «Tu negocio» con pestañas. Por ahora el bloque vive en el tab Gastronomía del tablero.
- Días de apertura: no encontré configuración de días de apertura en el código; sigue sin confirmar.
- Permisos: no hay prueba de que un usuario sin `gastronomia_menu` reciba rechazo en el POST.

**Siguiente paso**

- Cerrar BI-01 con medición en datos reales del piloto y los materiales de activación. Después, BI-02: cola de envío asistido.

### BI-02 — cola de envío asistido (31/10/2026)

**Alcance real**

- Historial amplio por teléfono (`gastronomia/services/bi/historial.py`): pedidos válidos sin límite de periodo. Nunca agrupa por nombre. Un pedido sin teléfono válido usa el del cliente final.
- Segmentos (`segmentos.py`):
  - Segunda compra: una sola fecha de compra, entre `segunda_min` y `segunda_max` días.
  - Habitual ausente: 3 o más fechas de compra, y más días sin comprar que su intervalo mediano, con tope de 120 días.
  - Las fechas se cuentan por día: dos pedidos el mismo día cuentan como uno.
- Cola (`cola.py`, `cola_acciones.py`): un contacto a la vez. Cada acción vuelve a validar el contacto contra la cola actual. Límite diario (por defecto 20) y frecuencia máxima por cliente (por defecto 14 días). «No quiere mensajes» saca el teléfono de todas las colas. Abrir WhatsApp registra la apertura y no marca el mensaje como enviado.
- Plantillas (`plantillas.py`, `cola_config.py`): una por segmento, editables, con `{nombre}`, `{plato}`, `{negocio}` y `{link}`. No incluyen descuento. El enlace `wa.me` es compartido (`whatsapp.py`); `whatsapp_pedido_url` lo usa ahora, con la misma salida.
- Atribución (`retorno.py`): compras posteriores al envío marcado, dentro de una ventana cerrada (15 días para segunda compra, 30 para habitual ausente), excluyendo anulados. El texto dice «volvió después del mensaje», sin afirmar causa.
- Telemetría (`gastronomia/bi_models.py`): eventos `whatsapp_abierto`, `mensaje_enviado`, `mensaje_omitido` y `no_contactar`. Las vistas no se registran, porque requerirían una escritura en cada carga del tablero.
- Modelos nuevos, todos aditivos y creados por `create_all()`: contactos de la cola, no-contactar y eventos.
- Presentación: tarjeta «Clientes que vuelven» en el tab Gastronomía. Los formularios son POST con CSRF y el permiso `gastronomia_menu`. «Abrir WhatsApp» abre en una pestaña nueva.

**Pruebas**

- `test_gastronomia_bi_cola.py`: 15 pruebas nuevas, en verde. Cubren reglas de segmentos, historial fuera de periodo y homónimos, habitual ausente fuera de periodo, «no quiere mensajes», abrir sin marcar enviado, límite diario, omitidos, frecuencia, atribución con anulados, configuración fuera de rango, plantilla sin tienda, enlace `wa.me`, acciones y configuración por POST, y degradación del bloque.
- Con BI-01 suman 26 pruebas en verde.
- Suites `test_gastronomia_*`, `test_inteligencia_*` y `test_tienda_*`: 318 pasaron y 42 se omitieron (las de MariaDB).

**Decisiones**

- Deduplicación por cliente, teléfono, segmento y último pedido. Una compra nueva crea un contacto nuevo; un envío o un descarte no se repite para el mismo último pedido.
- Valores por defecto configurables en la tarjeta: 20 mensajes por día, 14 días de frecuencia y segunda compra entre 5 y 15 días.
- Constantes, no configurables: tope de ausencia de 120 días y ventanas de atribución de 15 y 30 días.

**Limitaciones y pendiente**

- Sin verificar en navegador: el formulario con `target="_blank"` que abre WhatsApp, y el layout en celular y tema oscuro.
- El historial completo se recalcula en cada carga del tablero. Con historiales grandes conviene caché o carga por pestaña (fase 4 del roadmap).
- Sin link de reseña, sin exportación de contactos y sin segmento «favorito disponible». Los dos primeros son opcionales en la fase 2; el tercero no está en el alcance de BI-02.
- El estado vacío («sin clientes con teléfono») no tiene prueba propia.
- No hay prueba de rechazo para un usuario sin `gastronomia_menu` en las acciones.
- Sin medición con datos reales.

**Siguiente paso**

- Verificar la tarjeta y el formulario en navegador. Después, piloto con una instalación real.

### BI-03 — reporte de valor del mes (31/10/2026)

**Alcance real**

- Fase 3, primera parte: bloque «Tu mes en el sistema» en el tab Gastronomía (`_reporte_valor.html`), con el mes en curso hasta hoy y la comparación con los mismos días del mes anterior (`reporte_valor.py`).
  - Pedidos y ventas por canal propio, plataformas y desconocido. Pedidos válidos por fecha del pedido, con el total del pedido.
  - Clientes nuevos identificados: teléfonos cuya primera compra válida cae en el mes. No se agrupa por nombre.
  - Mensajes de vuelta: envíos del mes de la cola de BI-02. «Volvieron» solo con ventana cerrada.
  - Acompañamientos aceptados del sugeridor existente, con el importe de los renglones aceptados.
  - Cobertura de pedidos identificados por teléfono del mes.
- Fase 1, comisión evitada: porcentaje por plataforma en el mismo bloque (`comision.py`, `POST /gastronomia/bi/comision`, permiso `gastronomia_menu`, CSRF). Sin porcentaje no se muestra nada. Es una estimación: ventas de la plataforma × porcentaje.
- Reutilización: `retorno.py` separa el conteo por rango en `resumen_envios` y el resumen de BI-02 lo usa sin cambiar. `canales.py` suma ventas y desglose por plataforma. `pedidos_validos.py` agrega el total a cada fila. `medicion.py` (sugeridor) agrega `importe`. Todos cambios aditivos.

**Pruebas**

- `test_gastronomia_bi_reporte.py`: 11 pruebas nuevas, en verde. Cubren periodos equivalentes, variación sin base previa, canal propio frente a apps con cancelados excluidos, clientes nuevos por teléfono con homónimos separados, mensajes (cerrados, volvieron, en observación y fuera del mes), comisión solo con porcentaje, rechazo de valores inválidos sin guardar nada, reporte sin pedidos, degradación del bloque, render del tab con datos y POST.
- `test_gastronomia_sugerencias_medicion.py`: aserción del importe de los renglones aceptados.
- Suites `test_gastronomia_*`, `test_inteligencia_*` y `test_tienda_*`: 329 pasaron y 42 se omitieron (las de MariaDB).

**Decisiones**

- Ventas por fecha del pedido, no por fecha de cobro. El panel de Gastronomía usa el cobro (`GastronomiaPedidoPago`), así que en un mismo mes el total del reporte puede diferir de «Ventas» del panel. Se mantiene la fecha del pedido porque coincide con los indicadores de canal de BI-01 y con la definición de pedido válido de la fase 0. Está rotulado en el bloque.
- Acompañamientos por fecha de cobro, como su medición original. También rotulado.
- Mes sin base en el período anterior: se muestra «sin base», nunca 0 %.

**Limitaciones y pendiente**

- Sin descarga ni versión imprimible. Sin acciones completadas (fase 4) ni «Si el mes fue malo, proponer acciones» (depende de la fase 4). Sin panel de salud de uso (fase 3, segunda parte).
- La comparación es mensual; no hay serie semanal de ventas.
- Pendiente decidir si «Ventas» del reporte debe usar cobro para igualar el panel.
- `historial_clientes` se calcula varias veces por carga (cola, mensajes y clientes nuevos). Conviene una caché junto con la de BI-02.
- No verificado visualmente en navegador (layout, celular, tema oscuro). Pendiente junto con la tarjeta de BI-02.
- Permisos: no hay prueba de rechazo para un usuario sin `gastronomia_menu` en el POST, igual que en BI-02.
- Sin medición con datos reales.

**Siguiente paso**

- Verificar en navegador BI-02 y BI-03. Después, BI-04 (resto de la fase 1 y salud de uso).
