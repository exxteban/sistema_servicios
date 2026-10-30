# Plan de evolución del BI para gastronomía

Fecha: 30/10/2026. Estado: propuesta de implementación por fases.

Este documento organiza el trabajo; sus casillas pendientes no representan funcionalidades implementadas. No establece fechas de entrega: el esfuerzo se ajustará después de la fase 0. Los avances documentados de otros módulos conservan sus propios planes y validaciones.

## 1. Objetivo de producto

Ayudar al dueño de un pequeño negocio gastronómico a decidir qué hacer hoy para aumentar pedidos, conseguir que los clientes vuelvan y conservar margen, con poco tiempo de configuración y seguimiento.

El ciclo que debe resolver el producto es:

**Detectar una oportunidad → explicar la evidencia → preparar una acción → registrar su ejecución → medir el resultado → ajustar la recomendación.**

El valor para el negocio debe ser visible. Para el proveedor del sistema, la hipótesis es que ese valor mejora la continuidad de uso; debe validarse y no asumirse como una consecuencia garantizada de aumentar ventas.

### Principios

- Mostrar como máximo tres acciones prioritarias en la portada; conservar el detalle en vistas secundarias.
- Usar lenguaje cotidiano: pedidos, platos, clientes que vuelven y dinero estimado que queda.
- Explicar por qué se recomienda algo, qué datos se usaron y qué información falta.
- No recomendar descuentos sistemáticamente ni promociones sin evaluar sus costos disponibles.
- Evitar recomendaciones comerciales que agraven faltantes o saturación de cocina.
- Funcionar desde negocios pequeños: si falta historial, ofrecer configuración guiada y reglas explícitas, sin inventar patrones.
- Mantener pedidos, cocina y caja operativos aunque falle el BI.
- Usar reglas y cálculos verificables como base. La IA generativa puede redactar o explicar posteriormente.

## 2. Punto de partida y reutilización

Inventario inicial obtenido del código y la documentación del repositorio. La fase 0 debe confirmar contratos, cobertura y comportamiento antes de modificar cada área.

| Pieza existente | Ubicación | Tratamiento previsto |
| --- | --- | --- |
| Panel y acciones comerciales generales | `app/services/inteligencia/comercial.py`, `panel.py` | Integrar la nueva experiencia gastronómica sin duplicar alertas ni alterar otros rubros. |
| BI gastronómico: ventas, ticket, canales, horarios y cocina | `gastronomia/services/inteligencia_service.py` | Reutilizar consultas válidas y separar responsabilidades al crecer. |
| Radar y tarjetas gastronómicas | `app/templates/inteligencia/gastronomia/` | Evolucionar hacia acciones con estado, evidencia y seguimiento. |
| Promociones por hora | `gastronomia/services/inteligencia_promos.py` | Corregir comparación temporal y convertir sugerencias en propuestas evaluables. |
| Clientes frecuentes | `gastronomia/services/inteligencia_clientes.py` | Extender con historial suficiente, identidad confiable y detección de ausencia. |
| Alertas de margen y stock | `inteligencia_margen.py`, `inteligencia_stock.py` dentro de `gastronomia/services/` | Unificar bases de costo y vincular alertas con decisiones comerciales. |
| Costos y ganancia estimada | `gastronomia/services/costos_service.py`, `ganancia_service.py` | Aprovechar receta, costo extra y cobertura; distinguir margen de contribución y resultado estimado. |
| Sugerencias del POS, reglas, complementos y medición | `gastronomia/services/sugerencias/` | Conectar con BI y ampliar solo las capacidades faltantes. |

El sugeridor del POS ya tiene reglas, asociaciones, complementos iniciales, filtros, fatiga y medición. Su plan también documenta una tarjeta de BI. **Este proyecto no debe construir un segundo sugeridor ni otro registro de exposición/aceptación.**

Referencias internas:

- [Plan del sugeridor y estado de implementación](plan_sugerencias_gastronomia.md).
- [Complementos gastronómicos iniciales](docs/sugerencias_gastronomia_complementos.md).
- [Diagnóstico y limitaciones de medición](docs/sugerencias_gastronomia_diagnostico.md).
- [Integración gastronómica](docs/gastronomia_integracion.md).
- [Producción gastronómica](docs/gastronomia_produccion.md).

### Brechas observadas

- Las recomendaciones del radar son principalmente textos; falta un ciclo persistente de ejecución y evaluación.
- Las promociones actuales agrupan horas de cobro de distintos días y parten de horas con ventas; falta distinguir apertura, cero pedidos y días comparables.
- Los frecuentes se calculan dentro del período consultado; quien dejó de comprar puede quedar fuera de esa lista.
- La identidad de frecuentes admite nombre como alternativa; no alcanza para contactar o atribuir retornos con confianza.
- El radar de margen usa costo de receta, mientras el servicio de costos también contempla costo extra. Debe definirse una base consistente.
- Falta conectar oportunidades, acciones realizadas y resultados observados en una experiencia sencilla.

## 3. Experiencia propuesta

### Portada: «Tu negocio hoy»

1. Resumen de ventas, pedidos, ticket promedio y margen estimado con cobertura de costos visible.
2. Comparación con días y turnos equivalentes, hasta la misma hora si la jornada sigue abierta.
3. Tres acciones priorizadas, cada una con un único paso principal.
4. Acceso a acciones en evaluación y a resultados recientes.
5. Acceso secundario a menú, clientes, horarios, canales, operación y reportes existentes.

Ejemplo ilustrativo, sin datos reales:

> **Hay clientes habituales que todavía no volvieron.**
> Identificamos 8 clientes cuya última compra supera su intervalo habitual.
> Revisá la lista y prepará un mensaje relacionado con su plato favorito.
> **Acción:** revisar clientes. **Datos:** período observado y nivel de confianza.

Cada tarjeta debe responder: qué ocurre, por qué importa, qué hacer, qué esfuerzo requiere y cuándo revisar el resultado. No mostrar ganancias potenciales numéricas sin un cálculo y supuestos verificables.

### Momentos de uso

- Antes del turno: oportunidades, faltantes y preparación.
- Durante la venta: aprovechar el sugeridor existente y evitar avisos que interrumpan el cobro.
- Al cierre o semanalmente: qué se hizo, qué ocurrió después y qué conviene repetir o revisar.

La primera entrega usa avisos dentro del sistema. Canales externos y envíos automáticos quedan fuera del MVP.

## 4. Roadmap y dependencias

| Fase | Entrega | Prioridad | Dependencias |
| --- | --- | --- | --- |
| 0 | Contrato de datos y diagnóstico | Obligatoria | Ninguna |
| 1 | Motor de oportunidades y tres acciones para hoy | Alta | 0 |
| 2 | Recuperación de clientes y segunda compra | Alta | 0 y 1 |
| 3 | Seguimiento, resultados y resumen proactivo interno | Alta | 1 y 2; telemetría mínima desde 1 |
| 4 | Menú rentable e integración con el sugeridor | Media | 0 y 1; medición de 3 |
| 5 | Promociones para días, turnos y canales | Media | 3 y costos confiables de 4 |
| 6 | Preparación, reposición, merma y capacidad | Media | 0, 3 e historial operativo suficiente |
| 7 | Evaluación del piloto y despliegue progresivo | Transversal | Se aplica a cada entrega |

**MVP recomendado: fases 0 a 3**, reutilizando las señales actuales y el sugeridor. Las bases de medición se construyen desde la fase 1; la fase 3 completa su presentación y evaluación.

## 5. Fase 0 — Datos confiables antes de recomendar

### Trabajo

- [ ] Documentar qué cuenta como pedido, venta cobrada, devolución, anulación y descuento; resolver pagos y ventas relacionadas sin duplicar importes.
- [ ] Separar fecha del pedido para demanda de fecha de cobro para ingresos; documentar tratamiento de encargos y ventas históricas importadas.
- [ ] Definir zona horaria local, turnos que cruzan medianoche, días de apertura y cierres excepcionales.
- [ ] Diferenciar modalidad de entrega (salón, retiro, delivery) de canal de precios u origen comercial; revisar los campos existentes antes de agregar otros.
- [ ] Establecer comparaciones por día de semana, turno y canal; excluir períodos incompletos o compararlos al mismo corte.
- [ ] Definir mínimo de observaciones por indicador y estado «datos insuficientes». Propuesta inicial: evaluar entre 4 y 8 días equivalentes; calibrar con históricos y no usarlo como regla universal.
- [ ] Unificar semántica de costos: receta, extras y modificadores, descuentos, envases y comisiones cuando estén registrados; evitar contabilizar el mismo costo dos veces.
- [ ] Indicar si el costo es histórico o estimado con precios actuales. No reconstruir silenciosamente ganancias históricas con costos actuales.
- [ ] Medir cobertura de costos e identificación de clientes. Costo desconocido no equivale a costo cero.
- [ ] Auditar identidad de cliente final y separación respecto al identificador de la instalación; no agrupar personas solo por nombre.
- [ ] Inventariar telemetría del sugeridor, tareas programadas, permisos y servicios reutilizables.
- [ ] Preparar escenarios ficticios de restaurante, comida rápida, cafetería y negocio sin historial.

### Criterios de aceptación

- Un mismo pedido válido contribuye una sola vez a cada métrica según su definición.
- Anulaciones y ajustes tienen un tratamiento explícito y probado.
- Un negocio cerrado no recibe una alerta de baja demanda por ese horario.
- Datos faltantes aparecen como desconocidos y no como estabilidad, cero ventas confirmado o alto margen.
- Se entrega un diccionario de métricas, fuentes, filtros, cobertura y decisiones pendientes.

## 6. Fase 1 — Tres acciones para hoy

### Trabajo

- [ ] Definir un contrato común de oportunidad: tipo, entidad afectada, evidencia, período, confianza, urgencia, esfuerzo y acción disponible.
- [ ] Integrar inicialmente caída de pedidos, caída de ticket, falta de stock y revisión de margen, aprovechando los detectores actuales corregidos.
- [ ] Separar observación y recomendación: una caída de ventas no demuestra por sí sola su causa.
- [ ] Priorizar de forma explicable: problemas operativos que impiden vender, oportunidades con evidencia y esfuerzo razonable; evitar puntajes monetarios ficticios.
- [ ] Persistir acciones y eventos mínimos con identificador estable para impedir duplicados en cada recálculo.
- [ ] Implementar estados: pendiente, pospuesta, en curso, en evaluación, completada, descartada y vencida; validar transiciones.
- [ ] Añadir motivo de descarte y posposición, sin volver a mostrar la misma alerta inmediatamente.
- [ ] Construir la portada gastronómica con máximo tres acciones y acceso al resto.
- [ ] Vincular acciones a pantallas existentes con contexto precargado cuando sea posible y respetando permisos.
- [ ] Hacer que los avisos de la portada y los del BI general compartan estado y conteo.

### Criterios de aceptación

- Cada tarjeta contiene evidencia verificable, período, motivo y un paso concreto.
- Posponer, descartar o completar sobrevive a recarga y nuevo cálculo.
- Abrir una pantalla no marca automáticamente una acción como ejecutada.
- Un usuario sin permiso de edición no puede ejecutar la acción mediante UI ni API.
- El BI no bloquea pedidos, cocina ni caja; un error muestra estado de indisponibilidad o datos fechados, no un falso «todo bien».

## 7. Fase 2 — Clientes que vuelven y segunda compra

### Trabajo

- [ ] Consultar historial más amplio que el período visible para reconocer clientes que dejaron de aparecer.
- [ ] Reutilizar identidad estable de cliente final y normalización de teléfono; resolver ambigüedades sin fusionar por nombre.
- [ ] Detectar habituales que superaron su intervalo de compra y compradores nuevos sin segunda visita; definir umbrales distintos y mínimos de evidencia.
- [ ] Mostrar fecha de última compra, frecuencia, preferencia y fundamento de selección.
- [ ] Preparar mensajes editables con revisión del dueño, producto disponible y vínculo al menú cuando corresponda.
- [ ] Registrar contacto confirmado manualmente; abrir WhatsApp no prueba envío, recepción ni lectura.
- [ ] Respetar preferencias de contacto, exclusiones y frecuencia máxima; evitar listas repetitivas.
- [ ] Ofrecer acciones útiles sin descuento obligatorio: novedad, disponibilidad del favorito o recordatorio pertinente.
- [ ] Asociar compras posteriores con el contacto y su ventana de observación, excluyendo ventas anuladas.

### Criterios de aceptación

- Un habitual ausente aparece aunque no haya comprado en el período actual del panel.
- Personas homónimas no se mezclan ni reciben atribuciones ajenas.
- Sin historial o identificación suficiente se explica la limitación y no se inventa un segmento.
- No se envían mensajes automáticamente en esta fase.
- El resultado se denomina «volvió después del contacto», sin afirmar causalidad demostrada.

## 8. Fase 3 — Seguimiento y proactividad

### Trabajo

- [ ] Guardar fecha, responsable, evidencia de origen, acción realizada y ventana de evaluación.
- [ ] Definir ventanas por tipo de acción: resolver un faltante no se evalúa igual que recuperar clientes.
- [ ] Medir adopción, resultados observados y cambios frente a una referencia comparable.
- [ ] Incorporar las métricas existentes del sugeridor sin duplicar exposición, aceptación ni venta atribuida a la franja.
- [ ] Distinguir «sugerido», «agregado al pedido», «cobrado» y «anulado»; no contar pedidos abiertos como rechazo.
- [ ] Presentar resumen antes del turno y cierre semanal dentro del sistema, según horarios y preferencias.
- [ ] Establecer deduplicación, caducidad y límites de avisos; silencio cuando no haya novedades relevantes.
- [ ] Habilitar acciones «repetir», «ajustar» y «dejar de recomendar» con motivo.
- [ ] Mostrar muestra, cobertura y fecha de actualización en resultados; no atribuir todo crecimiento al BI.

### Criterios de aceptación

- Cada acción evaluable puede recorrerse desde la recomendación hasta su resultado.
- Recargar, reintentar o recalcular no duplica eventos ni resultados.
- Una acción sin muestra suficiente queda «sin evidencia suficiente», no como éxito o fracaso.
- El resumen semanal informa qué se hizo y qué ocurrió después, con comparaciones verificables.

## 9. Fase 4 — Menú rentable y sugerencias existentes

### Trabajo

- [ ] Clasificar platos por popularidad y contribución estimada en guaraníes, comparando categorías y canales pertinentes.
- [ ] Mostrar cuatro situaciones: vende y aporta; vende pero aporta poco; aporta pero vende poco; baja venta y bajo aporte.
- [ ] Recomendar visibilidad, revisión de receta/porción/precio o prueba comercial; evitar retirar platos automáticamente.
- [ ] Mostrar componentes de costo y cobertura; diferenciar contribución por plato del resultado después de gastos del negocio.
- [ ] Conectar oportunidades de acompañamientos con la administración y vista previa del sugeridor existente.
- [ ] Evaluar ordenamiento por contribución solo donde haya costos suficientes, manteniendo afinidad, reglas, exclusiones, stock, canal y fatiga.
- [ ] Mostrar aceptación y ventas asociadas a sugerencias usando su telemetría actual.
- [ ] Revalidar disponibilidad y precios al ejecutar una acción; una recomendación guardada puede quedar desactualizada.

### Criterios de aceptación

- Un plato sin costos completos no se clasifica como altamente rentable.
- El BI y los reportes coinciden cuando usan la misma definición, período y base de costos.
- No aparecen un segundo sugeridor ni nuevos eventos equivalentes a los ya existentes.
- Los cambios conservan los flujos de modificadores, peso, edición, canal y cobro del POS.

## 10. Fase 5 — Días flojos y promociones medibles

### Trabajo

- [ ] Analizar días, turnos y canales equivalentes, incluyendo horas abiertas con cero pedidos.
- [ ] Identificar si la baja está en cantidad de pedidos, ticket o mezcla de platos; presentar hipótesis por separado.
- [ ] Preparar propuestas con productos concretos, horario, canal, duración, stock y capacidad disponibles.
- [ ] Calcular contribución estimada después del beneficio y costos variables conocidos; mostrar costos faltantes.
- [ ] Simular escenarios, diferenciando supuesto de venta adicional y ventas que podrían ocurrir igualmente.
- [ ] Definir un identificador de promoción y reutilizar mecanismos de combos/promociones existentes si encajan.
- [ ] Permitir revisión y activación explícita por el dueño; no cambiar precios ni publicar automáticamente.
- [ ] Medir pedidos asociados, ticket, descuento y contribución, comparando períodos equivalentes y posibles desplazamientos entre horarios/productos.

### Criterios de aceptación

- La propuesta no recomienda un producto agotado ni una franja cerrada.
- Una promoción puede aumentar facturación y empeorar contribución; el resultado muestra ambas cosas.
- Si falta un mecanismo compatible de promociones, se documenta como dependencia antes de ofrecer un botón que prometa ejecutarla.
- Se distingue resultado observado de incremento causado; una prueba controlada puede incorporarse cuando el volumen lo permita.

## 11. Fase 6 — Preparación, disponibilidad y servicio

### Trabajo

- [ ] Estimar demanda por turno usando días equivalentes y un rango, con mínimos de datos por producto.
- [ ] Vincularla a recetas, existencias, reservas y producción ya registrada; revisar unidades y cantidades fraccionarias.
- [ ] Proponer preparación y reposición con horizonte y fundamento, sin emitir compras automáticamente.
- [ ] Incorporar merma registrada y límites de conservación cuando existan datos; no inventar vencimientos ni vida útil.
- [ ] Mostrar desvíos entre preparación, venta y desperdicio para ajustar recomendaciones.
- [ ] Detectar demoras por turno, producto y modalidad con umbrales configurables, evitando un único límite universal.
- [ ] Evitar impulsar demanda cuando hay faltantes críticos o cocina saturada; priorizar resolver la restricción.

### Criterios de aceptación

- La previsión informa rango, muestra y fecha; con pocos datos ofrece orientación manual.
- Las cantidades sugeridas respetan unidades y no duplican producción/reservas existentes.
- Se puede comparar lo sugerido con ventas, faltantes y merma posterior.
- Las alertas de servicio distinguen demoras registradas de posibles causas todavía no comprobadas.

## 12. Arquitectura y compatibilidad

- Mantener una instalación independiente por cliente; no agregar infraestructura multi-tenant ni comparaciones entre instalaciones.
- Preservar `id_cliente`/`cliente_id`, verificando el significado de cada campo, y aplicar filtros en lecturas, escrituras, tareas y cachés.
- Antes de crear servicios, modelos o utilidades, buscar implementaciones existentes con CodeGraph y revisar sus contratos.
- Separar detectores, priorización, persistencia, ejecución y evaluación en archivos pequeños. Ningún archivo nuevo o modificado debe superar 600 líneas; dividir antes de crecer.
- Evaluar un paquete `gastronomia/services/bi/` para las responsabilidades nuevas, dejando los servicios existentes como integraciones o adaptadores donde corresponda.
- Mantener rutas delgadas, plantillas parciales y scripts acotados. Evitar agregar todo a `inteligencia_service.py` o `comercial.py`.
- Nuevos modelos propuestos: oportunidad/acción y eventos de seguimiento; evaluar configuración y evaluaciones separadas solo si son necesarias. Reutilizar identidad, pedidos, promociones y telemetría actuales.
- Definir clave de deduplicación por instalación, detector, entidad y ventana; registrar versión de regla y evidencia usada.
- Migraciones aditivas, campos compatibles con valores por defecto o nulos; preservar registros anteriores.
- Cálculos pesados fuera del pedido/cobro y de la carga interactiva. Reutilizar patrones existentes de tareas, candados y publicación de resultados sin compartir responsabilidades de negocio indebidamente.
- Conservar el último resultado válido con fecha ante fallos; definir presupuesto de tiempo y volumen después de medir en fase 0.
- Permisos de lectura separados de acciones que editan, activan promociones o preparan contactos; aplicar validación de servidor y CSRF.
- Cualquier trabajo del frontend público queda exclusivamente en `/tienda_online` y consume `/api/tienda/...`; no importar código del backoffice desde la tienda.
- En el MVP, no agregar proveedores de IA, infraestructura de mensajería ni cambios automáticos de precio.

## 13. Validación y liberación por entrega

### Pruebas relevantes

- Cálculos: períodos comparables, medianoche, apertura, pocos datos, costos incompletos, descuentos y anulaciones.
- Aislamiento y permisos: dos contextos de cliente, acceso directo a API, caché, tareas y acciones guardadas.
- Estado: recálculos, solicitudes repetidas, transiciones inválidas, caducidad y persistencia de descartes.
- Identidad y recuperación: homónimos, teléfonos normalizados, clientes ausentes y retorno fuera de ventana.
- Integración: oportunidad → pantalla de acción → ejecución → pedido/cobro válido → resultado.
- Regresión: BI general, gastronomía desactivada y módulos de otros rubros; POS, cocina, caja y sugeridor.
- UI: escritorio y móvil, tema claro/oscuro, teclado, estados vacíos, error y datos desactualizados.
- Rendimiento: catálogo e historial representativos, latencia HTTP además del servicio, cálculos concurrentes y fallos de tareas.
- Base de datos: migraciones y consultas sobre los motores soportados; usar datos ficticios o copias autorizadas, sin experimentar en bases productivas.

Reutilizar inicialmente `test_inteligencia_comercial.py`, `test_inteligencia_bi_context.py`, `test_gastronomia_reportes.py`, `test_gastronomia_ganancia.py` y las suites del sugeridor. Agregar pruebas de comportamiento para riesgos nuevos, evitando repetir la implementación en los asserts.

### Piloto y salida gradual

- [ ] Seleccionar instalaciones autorizadas con operaciones distintas y registrar una línea base.
- [ ] Liberar primero lectura/diagnóstico y luego acciones por configuración de instalación.
- [ ] Verificar que las recomendaciones sean comprensibles y ejecutables con dueños reales.
- [ ] Revisar avisos descartados, falsos positivos, datos insuficientes y esfuerzo de uso.
- [ ] Definir objetivos cuantitativos del piloto después de la línea base; no prometer porcentajes de mejora sin evidencia.
- [ ] Comparar resultados por períodos equivalentes y documentar factores externos conocidos.
- [ ] Permitir desactivar la nueva experiencia conservando historial, reportes y operación actual.

## 14. Cómo medir si sirve

| Dimensión | Indicadores | Interpretación |
| --- | --- | --- |
| Utilidad | Acciones vistas, iniciadas, ejecutadas y descartadas con motivo | Abrir una tarjeta no equivale a hacer la acción. |
| Venta | Pedidos, ticket y acompañamientos por pedido | Comparar turnos y canales equivalentes. |
| Repetición | Segunda compra y retorno posterior al contacto | Solo clientes identificables; informar cobertura. |
| Margen | Contribución estimada y descuentos | Informar costos incluidos/faltantes; no llamarlo ganancia neta. |
| Operación | Faltantes, merma registrada y demora | Separar ausencia de registros de ausencia de problemas. |
| Calidad del BI | Recomendaciones válidas, repetidas, vencidas y sin evidencia | Preferir pocas acciones útiles a muchas alertas. |

La retención del cliente del sistema se evaluará como hipótesis comercial del proveedor, con información autorizada. No requiere centralizar datos de las instalaciones ni agregar telemetría externa en este plan.

## 15. Decisiones a cerrar durante la implementación

| Decisión | Momento | Propuesta inicial |
| --- | --- | --- |
| Rubros del primer piloto | Fase 0 | Comida rápida y cafetería; adaptar por turnos y tipo de operación. |
| Apertura y turnos | Fase 0 | Reutilizar configuración existente y pedir solo datos que falten. |
| Definiciones de costos y cobertura | Fase 0 | Una base compartida, visible y coherente con reportes. |
| Mínimos de datos y frecuencia de cálculo | Fases 0–1 | Configurables y calibrados con diagnóstico; no fijarlos por intuición. |
| Ventanas de ausencia y segunda compra | Fase 2 | Basadas en recurrencia cuando haya evidencia; reglas explícitas para pocos datos. |
| Canales externos | Después del MVP | Evaluar necesidad y permisos; no condicionan las primeras entregas. |
| Uso de IA generativa | Después del MVP | Solo si mejora explicación/redacción y puede medirse su costo y utilidad. |

## 16. Próxima unidad de trabajo

**BI-01: diagnóstico y contrato de métricas de gastronomía.**

Entregables: fuentes y filtros confirmados, escenarios de prueba, cobertura de datos, mapa de reutilización y criterios temporales/de costos. Luego implementar **BI-02: estado persistente de acciones y portada con tres oportunidades**, con telemetría desde el inicio.

Actualizar este documento al cerrar cada entrega con alcance real, pruebas realizadas, limitaciones y siguiente paso. Marcar una casilla como terminada únicamente cuando la implementación y sus criterios de aceptación estén verificados.
