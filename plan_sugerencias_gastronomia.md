# Sugerencias de venta en el POS de gastronomía ("Suelen llevar")

Mientras se carga un pedido, el POS de gastronomía sugiere hasta 3 platos que
tiene sentido sumar. **Sin IA**: estadística sobre los pedidos cobrados del
propio negocio, más reglas del dueño.

Es la adaptación del módulo del padre
(`sistema_silvio_cel/docs/sugerencias_venta.md`,
`app/services/sugerencias_venta/`). Se mantienen sus principios y su
matemática; cambia de dónde salen los tickets, cómo se agrega un producto y
cómo se mide.

### Avance de implementación — 30/10/2026

Base, administración, POS, medición y aprendizaje implementados; pendientes
la validación con historial real y MySQL real:

- [x] Seis tablas nuevas: configuración (apagada por defecto), reglas,
  exclusiones, pares, orígenes y estado/candado del cálculo. Registradas antes
  del `create_all` habitual; sin columnas nuevas en tablas existentes.
- [x] Matemática pura portada del padre sin cambios de lógica.
- [x] Lectura por tramos de pedidos cobrados: fecha del pago, venta central
  no anulada, aislamiento por cliente, deduplicación, exclusión de encargos
  y de pedidos con más de 12 productos distintos.
- [x] Análisis por producto y categoría, respetando exclusiones.
- [x] Recálculo explícito con candado por cliente, vencimiento y reemplazo
  transaccional. Un fallo preserva los resultados previos.
- [x] Diagnóstico inicial de solo lectura con pedidos válidos, porcentaje de
  canastas múltiples, promedio de platos y pares con métricas y nombres.
- [x] Seis pruebas automatizadas en SQLite en memoria, independientes de la
  base configurada. Cubren matemática, filtros de tickets, aislamiento,
  exclusiones, candado ocupado, anulaciones, fecha del pago y rollback de una
  inserción fallida. Creación repetible y compilación de DDL para MySQL.
- [x] Diagnóstico ampliado: comparación de umbrales actuales y exploratorios,
  conteos de descartes por soporte/confianza/lift y límite de destinos, top y
  muestra acotada de rechazados con nombres. Cobertura teórica por origen,
  explícitamente anterior a filtros finales de stock, precio, reglas y carrito.
- [x] Scheduler con demora inicial de 180 s, revisión horaria y recálculo solo
  si el último resultado tiene 24 h. Se desactiva con
  `GASTRONOMIA_SUGERENCIAS_CALCULO=0`; no arranca en testing ni en el proceso
  padre del reloader. Un error por cliente no interrumpe los demás.
- [x] Prueba de dos workers con sesiones independientes sobre SQLite en
  archivo: un cálculo ocupado no se repite. Pruebas de vencimiento, frecuencia
  y rechazo de publicación si otro worker reemplazó el token del candado.
- [ ] Cobertura efectiva de franja y medición del endpoint con catálogo real.
- [ ] Ejecutar las pruebas contra MySQL real (compilar DDL no lo sustituye).
- [ ] Revisar diagnóstico con historial de 2 o 3 instalaciones autorizadas.
- [x] Pantalla del dueño en `/gastronomia/sugerencias`, accesible desde Menú
  con permiso `gastronomia_menu`: configuración, alta/edición/pausa/reanudación
  y eliminación de reglas, prioridad, búsqueda y exclusiones por plato/categoría.
  Guardar una combinación reemplaza la regla anterior de esa misma combinación.
- [x] Vista previa independiente de la activación: reglas y asociaciones ya
  calculadas, fallback por categoría, afinidad portada del padre, disponibilidad,
  stock, visibilidad, exclusiones, prohibiciones, precio y carrito. Muestra
  métricas y motivos de descarte, con atajos «Nunca con este» y «Nunca sugerir
  esto». La vista previa usa precios normales; el POS consulta con su canal.
- [x] Botón de recálculo en segundo plano, con protección contra solicitudes
  duplicadas en el proceso y candado compartido con el scheduler en la base.
- [x] Verificación en navegador con datos ficticios: guardar regla hamburguesa
  → papas y ver el resultado. Revisión de tema claro/oscuro y ancho de 390 px
  (sin desbordamiento horizontal). Servidor temporal cerrado al terminar.
- [x] Endpoint GET `/api/gastronomia/sugerencias`: permiso POS, contexto del
  cliente, configuración activa, máximo 60 productos, respuesta sin precios y
  `Cache-Control: no-store`. Errores devuelven sugerencias vacías.
- [x] Presupuesto cooperativo de 300 ms en el servidor (se comprueba entre
  consultas y durante el procesamiento; no interrumpe una consulta SQL ya
  bloqueada). El navegador tiene timeout independiente de 1200 ms y un solo
  reintento. Ninguna acción de pedido espera a este endpoint.
- [x] Franja al pie del carrito: hasta 3 botones, lista de hasta 6 con motivos,
  cierre por pedido, consulta tras 500 ms, cancelación y descarte de respuestas
  viejas. Cada instancia conserva su estado. Con la configuración apagada no
  se crea el contenedor ni se solicitan sugerencias.
- [x] Productos y precios de la franja tomados del catálogo del canal; abre
  `openProduct` para modificadores, notas, cantidades y peso. No muestra importe
  en productos por kg ni con opciones de precio variable. Canal incompatible
  con el carrito: franja oculta. La edición restaura el canal del pedido.
- [x] Controles del POS referenciados desde su raíz para conservar la instancia
  correcta al restaurar y alternar pestañas, incluso al limpiar y guardar.
- [x] Pruebas de navegador con datos ficticios: hamburguesa → papas con salsa
  obligatoria, torta por peso, guardado y edición de pedido, precios PedidosYa,
  ajuste a 390 px sin desbordamiento horizontal y guardado/envío a cocina con
  fallo HTTP del sugeridor. El entorno SQLite en memoria se ejecutó en forma
  serial para no compartir su única conexión entre requests simultáneos.
- [x] Medición, fatiga y factor de aceptación (segunda entrega, detalle abajo).

Validación actual: 110 pruebas de backend aprobadas entre
`test_gastronomia_sugerencias.py`,
`test_gastronomia_sugerencias_scheduler.py` y
`test_gastronomia_sugerencias_diagnostico.py` y
`test_gastronomia_sugerencias_admin.py` y `test_gastronomia_sugerencias_pos.py`,
más `test_gastronomia_sugerencias_medicion.py` y regresiones de pedidos, caja,
Inteligencia, precios por canal, venta por peso y modificadores.
Cubren arranque y funcionamiento del menú con base SQLite en memoria,
administración, aislamiento, validación, permisos, CSRF y escape de nombres HTML.
Además pasaron las 10 pruebas de JavaScript de
`node --test tests/js/gastronomia_pos_sugerencias.test.cjs`: restauración del
canal, debounce, configuración del producto, conservación del foco, respuesta
vieja aun ignorando abort, timeout, reintento limitado, ocultamiento por pedido
e instancia, compatibilidad de canales y etiquetas sin precio variable,
exposición visible, aceptación confirmada y payload con atribución.
No se ejecutaron migraciones ni recálculos sobre bases reales ni se activó la
franja en instalaciones reales; solo se habilitó en el entorno ficticio de QA.
El scheduler está conectado al arranque habitual: en ejecución normal
calculará asociaciones para las configuraciones de gastronomía activas,
respetando la demora y la variable de desactivación.

### Segunda entrega — medición y aprendizaje (30/10/2026)

- Dos tablas aditivas: `gastronomia_sugerencias_estadistica` y
  `gastronomia_sugerencias_pedido`. La segunda conserva **cada par mostrado**
  una sola vez por pedido (hasta 180), su aceptación y los ids de los renglones
  finales agregados desde la franja. Hace falta conservar la exposición para
  resolver ventas cobradas después y deduplicar al editar; no se guarda cada
  redibujo ni cada clic. Los contadores agregados siguen siendo uno por par.
- `registro.py`: sesión/transacción propia después del commit del pedido.
  Valida productos del mismo cliente, ignora telemetría inválida y deduplica
  reintentos. La atribución se conserva al reabrir y editar, distingue dos
  renglones del mismo producto, y se invalida si cambia el evento de guardado
  y falla la actualización estadística. Sin el campo opcional, el pedido sigue
  funcionando. El módulo apagado no registra nuevas exposiciones.
- El front cuenta solo las píldoras visibles y el resto al abrir «⋯».
  Una pestaña o franja oculta no suma. Abrir/cancelar el configurador no es
  tocar: se marca al confirmar el producto; quitarlo luego conserva la tocada
  histórica pero elimina su atribución como vendido desde la franja.
- `aprendizaje.py`: el cálculo diario resuelve vendidas cruzando pagos válidos
  y renglones actuales. No duplica al recalcular y corrige anulaciones.
  **Precisión sobre §6–7:** se conserva `mostradas` para todos los pedidos
  guardados, pero el denominador del aprendizaje/fatiga es `resueltas`
  (exposiciones en pedidos cobrados, sin venta anulada). Un pedido abierto no
  es un rechazo. Factor entre 0,5 y 1,5; 30 pedidos cobrados con aceptación
  menor al 2% ocultan el par 30 días y reinician su ventana. Los pedidos de la
  ventana anterior no lo vuelven a ocultar al vencer. Publicación y registro
  comparten el candado de la instalación.
- `medicion.py`: tarjeta en BI Gastronomía, por fecha local de cobro, sin
  anuladas ni encargos; pedidos/renglones desde la franja y productos pedidos
  por menú. Top 5 del período y pares sin ventas del acumulado (actualizado
  diariamente). Permanece visible con historial aunque se apague el módulo.
- QA en SQLite efímera: sugerencia → guardar → reabrir → editar cantidad →
  cocina → caja → tarjeta (1 pedido, 1 renglón, sin duplicar exposiciones).
  Escritorio y 390 px, temas claro/oscuro, sin desbordamiento horizontal.
  Pruebas fuerzan errores SQL reales en inserción y actualización estadística:
  guardar, enviar a cocina, cobrar y descontar stock siguen funcionando.

Tras crear las tablas mediante el arranque habitual de la aplicación, el
diagnóstico inicial se consulta con:

```powershell
python scripts/diagnostico_sugerencias_gastronomia.py --cliente-id N --limite 20
```

Ese script no usa `create_app`, no crea tablas ni ejecuta migraciones. Para
el recálculo explícito se dispone de
`gastronomia.services.sugerencias.tarea.recalcular(cliente_id)`, dentro de un
contexto de aplicación y una sesión sin cambios pendientes. No debe llamarse
desde el guardado ni desde el cobro de un pedido.

Para habilitar la franja en una instalación, revisar primero las reglas y la
vista previa, activar «Activar sugeridor» y «Mostrar sugerencias en el POS» en
Menú → Sugerencias, guardar y volver a abrir el POS. Ambos interruptores nacen
apagados. La aceptación y la fatiga se actualizan con el cálculo diario.

## 1. Principios (heredados del padre)

1. **Mejor callado que decir una pavada.** Sin evidencia suficiente no se
   sugiere nada y la franja no existe.
2. **Siempre explicable.** Cada sugerencia lleva su motivo: «Regla del
   negocio», «6 de cada 10 que piden X piden esto», «De la misma línea».
3. **No frena ni rompe el POS.** El cálculo pesado corre fuera del POS; el POS
   solo lee. Si la consulta falla o tarda, no se muestra nada y el pedido sigue
   igual: carga, envío a cocina y cobro no dependen de esto.
4. **Aprende del mostrador.** Lo que se muestra y nunca se pide baja; lo que se
   pide sube.
5. **Una instalación, sus datos.** Todo filtrado por `cliente_id`, como el
   resto de `gastronomia/`. Nada de cruzar datos entre clientes.

## 2. Qué cuenta como venta

Mismo criterio que `gastronomia/services/inteligencia_service.py`:

- Un pedido cuenta si tiene `GastronomiaPedidoPago` del mismo `cliente_id` y,
  si el pago tiene `id_venta`, esa `Venta` central **no** está `anulada`
  (`anulacion_service.py` anula la venta central, no cambia el pedido).
- **No** se filtra por `estado`: un pedido `entregado` sin cobro no es una
  venta, y un pedido cobrado no se puede cancelar (`pedido_service.py`).
- Fecha del ticket: `GastronomiaPedidoPago.fecha_pago`.
- Entran los dos orígenes (`pos` y `tienda_online`): la tienda también dice
  qué se pide junto.
- **Encargos** (`es_encargo`): afuera en la primera entrega. Son tortas,
  bandejas y catering; mezclan cosas que no se piden juntas en el mostrador.
  Queda como constante (`INCLUIR_ENCARGOS = False`) por si un cliente lo pide.
- **Tickets enormes**: afuera los pedidos con más de **12 productos
  distintos** (mesas grandes, eventos). Constante configurable.
- Un plato repetido en el pedido cuenta **una vez** (la canasta es un
  conjunto). Modificadores, peso y cantidad no importan para la asociación.
- Productos inactivos o excluidos por el dueño no cuentan ni como origen ni
  como destino.

## 3. De dónde salen las sugerencias (orden de prioridad)

1. **Prohibir** (dueño): «Nunca sugerir X» o «Nunca sugerir X con Y». Gana
   sobre todo.
2. **Forzar** (dueño): «Si piden [plato o categoría], sugerir [plato o
   categoría]». Es lo que hace funcionar al módulo desde el primer día en un
   negocio nuevo (hamburguesa → papas).
3. **Asociación por producto** (calculada, §4).
4. **Asociación por categoría** (calculada, §4.4): cuando el plato tiene poco
   historial. Solo dice dónde buscar; el plato concreto se elige por afinidad
   de nombre y ventas (§5).

**Complementos de fábrica** (fuente 5 del padre): **no** en la primera
entrega. En el padre hicieron falta porque el 90% de las ventas eran de un
solo producto. En gastronomía se espera más pedidos con varios platos; se
decide con el diagnóstico (§11): si menos del 15% de los pedidos tiene más de
un plato, se evalúa un diccionario gastronómico (pizza → bebida, café →
medialuna) como etapa aparte.

## 4. El cálculo

### 4.1 Reutilización del padre

`calculo.py` del padre separa la matemática pura de la lectura de datos. Se
**portan sin cambios de lógica** (copiadas, porque es otro repo):

- `_Conteo` (acumula soporte real y pesos ponderados por par y por origen),
- `medir()` (soporte, confianza, lift y puntaje, con los mínimos como
  parámetro),
- `peso_por_antiguedad()`.

Lo único nuevo es el **adaptador de tickets** `_tickets_gastronomia(cliente_id,
desde)`, que devuelve el mismo formato que `_tickets()` del padre
(`(fecha, conjunto_de_ids)`), leyendo por tramos de `id_pedido`:

```
GastronomiaPedido ⋈ GastronomiaPedidoPago (⟕ Venta)
  → GastronomiaPedidoItem.producto_id
```

Nunca cargar entidades completas: solo `(id_pedido, fecha_pago)` y
`(pedido_id, producto_id)`.

### 4.2 Medidas y umbrales de arranque

Con `N` = pedidos que cuentan, `n(A)` = pedidos con A, `n(A,B)` = pedidos con
A y B:

| Medida | Fórmula | Mínimo inicial |
|---|---|---|
| Soporte | `n(A,B)` en pedidos reales, sin ponderar | **4** |
| Confianza | `n(A,B) / n(A)` | **0,15** |
| Lift | `confianza / (n(B) / N)` | **1,5** |

- **El lift es lo que resuelve "la bebida está en todo"**: una gaseosa que
  aparece en el 50% de los pedidos tiene lift ≈ 1 con casi todo y no pasa.
  Solo pasa si con ese plato se pide **más de lo normal**.
- Puntaje: `confianza_ajustada × log(1 + lift)`, con
  `confianza_ajustada = n(A,B) / (n(A) + 5)` para que 4 de 5 no le gane a 60
  de 100.
- Las constantes van en `constantes.py`, en un solo lugar. Se ajustan con el
  diagnóstico (§11), no por intuición.

### 4.3 Recencia

Ventana de 12 meses. Peso 1,0 en los últimos 3 meses, bajando hasta 0,3 al
año. Se aplica a confianza, lift y puntaje, **nunca al soporte**: el mínimo de
soporte se mide en pedidos reales. Las cartas cambian por temporada; esto evita
sugerir el plato que salió del menú.

### 4.4 Nivel categoría

Mismo cálculo con `GastronomiaCategoria` en lugar de platos. Se usa cuando el
plato origen tiene menos de **10 pedidos** en la ventana. La asociación
categoría → misma categoría no se usa (pizza → otra pizza es un sustituto).

### 4.5 Cuándo y cómo se calcula

- Una vez por día y al arrancar si el último cálculo tiene más de 24 h, en un
  hilo propio, con el patrón de `app/bootstrap/peluqueria_recordatorios_scheduler.py`
  (lock, sin doble arranque con el reloader, `daemon=True`). Archivo nuevo:
  `app/bootstrap/gastronomia_sugerencias_scheduler.py`. Se apaga con
  `GASTRONOMIA_SUGERENCIAS_CALCULO=0`.
- Arranca 3 minutos después del inicio; no demora el arranque.
- **Candado en la base** (fila en `gastronomia_sugerencias_calculo`) para que
  dos workers no calculen a la vez.
- Calcula por cada `cliente_id` con gastronomía activa, en memoria, y reemplaza
  los resultados de **ese** cliente en una transacción: el POS nunca ve un
  cálculo a medias, y un cálculo que falla deja el anterior intacto.
- Como mucho **10 destinos por origen**.

## 5. Afinidad por nombre

Se porta `afinidad.py` del padre (palabras normalizadas, peso tipo IDF sobre el
catálogo del cliente). Uso en gastronomía: elegir el plato concreto en el nivel
categoría y desempatar («Pizza napolitana» → «Empanada napolitana» antes que
otra empanada).

La **regla de conflicto de nombres** del padre (§5.1) se porta pero queda
**apagada** por constante: está pensada para modelos de aparatos (funda A54 vs
funda iPhone) y en un menú puede descartar cosas razonables. Se prende solo si
el diagnóstico muestra sugerencias de categoría absurdas.

## 6. Filtros (siempre, en este orden)

1. Mismo `cliente_id`.
2. `activo` y `disponible`.
3. Con stock, si `control_stock_venta` está prendido (`stock_disponible > 0`).
4. `visible` en el POS (no sugerir algo que el cajero no podría elegir del
   menú).
5. No está ya en el carrito.
6. Prohibidos por el dueño y productos excluidos.
7. **Precio coherente**: no sugerir algo más caro que el plato principal del
   carrito, salvo regla del dueño o lift ≥ 4. (Que el postre no cueste más que
   la hamburguesa.)
8. **Fatiga**: un par mostrado en 30+ pedidos donde el destino terminó en
   menos del 2% se oculta 30 días, y sus contadores vuelven a cero (como en el
   padre, para que al volver tenga otra oportunidad real).

Si después de los filtros no queda nada con puntaje mínimo, la franja no se
muestra.

## 7. Orden final

`puntaje = puntaje_base × (1 + afinidad_normalizada) × factor_aceptacion`

- `factor_aceptacion = (vendidas + 1) / (mostradas + 10)`, relativo al
  promedio, **acotado entre 0,5 y 1,5**.
- Reglas forzadas primero (si pasan los filtros).
- Con varios platos en el carrito: se juntan los candidatos de cada uno, se
  suman puntajes del mismo destino y pesa más el último agregado. Se miran solo
  los **últimos 3** platos del carrito.
- Máximo **3** en la franja y **6** en la lista del «⋯».
- Sin `factor_margen` en la primera entrega (el margen depende de recetas y
  `costo_extra`; se suma cuando la medición lo justifique).

## 8. Datos (tablas nuevas, sin columnas en tablas existentes)

Todas con `cliente_id` (FK a `clientes.id_cliente`, `ondelete='CASCADE'`,
indexado). Las crea `create_all`; no hace falta `ALTER` en
`gastronomia/schema.py`. Nombres de índices y constraints de **menos de 64
caracteres** (MySQL).

| Tabla | Para qué |
|---|---|
| `gastronomia_sugerencias_par` | `nivel` (producto/categoria), `id_origen`, `id_destino`, `soporte`, `confianza`, `lift`, `puntaje`, `calculado_en`. Índice (`cliente_id`, `nivel`, `id_origen`, `puntaje`). |
| `gastronomia_sugerencias_origen` | Pedidos reales por plato y categoría en la ventana; decide nivel producto o categoría aunque no haya pares. |
| `gastronomia_sugerencias_regla` | `tipo` (forzar/prohibir), origen (cualquiera/producto/categoria + id), destino (producto/categoria + id), `prioridad`, `activa`, `creado_por_id`, fechas. |
| `gastronomia_sugerencias_excluido` | Plato o categoría que nunca se sugiere ni cuenta. |
| `gastronomia_sugerencias_config` | Una fila por `cliente_id`: `activo`, `mostrar_en_pos`, `max_franja` (1–3). Tabla propia para no tocar `gastronomia_cliente_config`. |
| `gastronomia_sugerencias_calculo` | Estado del último cálculo (inicio, fin, pedidos leídos, pares, error) y candado. |
| `gastronomia_sugerencias_estadistica` | Contadores por par: `mostradas`, `tocadas`, `vendidas`, `resueltas`, `ultima_vez`, `inicio_ventana`, `oculto_hasta`. Un contador por par. |
| `gastronomia_sugerencias_pedido` | Una exposición por pedido/par (`pedido_id`, `producto_id`, `id_origen`, `mostrada_en`, `tocada`); `items_aceptados` conserva ids de renglones desde la franja y `guardado_evento_id` identifica su guardado. |

Todos los campos nuevos con `default` o `nullable`; instalaciones existentes
siguen funcionando sin datos en estas tablas.

## 9. Integración con el POS

### 9.1 Endpoint

`GET /api/gastronomia/sugerencias?productos=1,2,3&canal_precio=...`
(orden de carga; el último pesa más):

- Devuelve hasta 6 `{id_producto, motivo, fuente, id_origen}`. **Solo ids y
  motivo**, sin precio.
- Respeta permisos del POS (`gastronomia/services/permisos.py`) y la config
  activa. Con la config apagada devuelve vacío.
- Tope de tiempo: si pasa de ~300 ms devuelve vacío (no hay `tope.py` en este
  repo; un `time.monotonic()` en el servicio alcanza).
- Ruta en archivo propio: `gastronomia/routes/sugerencias_api_routes.py`.

### 9.2 Front

Archivo nuevo **`gastronomia/static/js/pos_sugerencias.js`**, con el mismo
patrón de módulo que `pos_peso.js` o `pos_channel_prices.js`. `pos.js` ya tiene
574 líneas: solo recibe enganches de una línea.

- **El producto sale de `products` del front**, que ya viene con el precio del
  canal elegido, la disponibilidad y la promoción
  (`GastronomiaChannelPrices.fetchProducts`). Si el id no está en `products`
  (otro canal, no visible), se descarta. Así la píldora nunca muestra un precio
  distinto del que entra.
- **Precio en la píldora**: el de `products`. **Sin precio** si el plato se
  vende por peso o tiene grupos de opciones con `precio_delta`.
- **Al tocar**: se llama a `openProduct(product)`, el mismo flujo que tocar el
  plato en el menú. Hoy todo plato abre el modal (cantidad, nota, opciones), y
  la sugerencia hace lo mismo: no se crea un segundo camino de alta. Agregar en
  un toque los platos sin grupos de opciones queda como mejora posterior, y
  debería aplicarse igual al menú y a la franja.
- **Ubicación**: franja fina al pie de la lista del carrito, dentro de la misma
  tarjeta. Nada en la zona de totales y cobro.
- **Estilo**: texto chico y apagado, píldoras de borde 1px, ícono de destellos
  (no lamparita). Variables CSS propias con variante oscura; nada de
  `bg-white` fijo.
- **Comportamiento**:
  1. Consulta cuando el carrito se queda quieto ~500 ms.
  2. Cada consulta nueva cancela la anterior (`AbortController`); al llegar la
     respuesta se compara la firma del carrito (ids ordenados) y, si cambió, se
     descarta.
  3. Si falla o tarda, se reintenta una vez; si vuelve a fallar, el próximo
     cambio del carrito vuelve a probar. Nunca un error visible.
  4. No toma el foco al aparecer.
  5. «✕» la oculta para ese pedido; vuelve en el siguiente.
  6. «⋯» despliega la lista completa con motivos **dentro de la tarjeta** (en
     el padre, un popover flotante quedaba cortado por `overflow-hidden`).
  7. Al **editar un pedido existente** (mesa abierta, `cart` cargado desde
     `order.items`) la franja funciona igual.
  8. En celular: una sola línea con desplazamiento lateral; nunca empuja el
     botón de cobro.
- **Pestañas**: el POS puede estar abierto en varias; nada de ids fijos nuevos
  que choquen.

## 10. Pantalla del dueño

En el menú de gastronomía (junto a Menú o Inteligencia), permiso de edición de
menú:

- Activar / desactivar el módulo y «Mostrar en el POS», y «Hasta N por pedido»
  (1–3).
- **Reglas**: «Sugerir» / «Nunca sugerir»; origen = cualquier pedido, un plato
  o una categoría; destino = plato o categoría. Pausar / reanudar sin borrar.
  Sugerir y nunca para el mismo par se contradicen: **gana la última** (crear
  una borra la contraria).
- Prioridad como tilde «Ponerla antes que las otras reglas», no como número.
- **Excluidos**: platos y categorías.
- **«Ver qué se sugeriría»**: elegís un plato y ves sus sugerencias con
  soporte real, confianza, lift y motivo, y los candidatos descartados con el
  filtro que los sacó. Al lado, «Nunca con este» y «Nunca sugerir esto».
- Estado del último cálculo y «Recalcular ahora».
- Buscador de reglas que avise «sin stock» / «no disponible» (una regla hacia
  algo agotado no sale nunca) y «sin resultados».
- Plantilla en su propia carpeta
  (`gastronomia/templates/gastronomia/sugerencias/`), con la tarjeta de reglas
  en un include aparte para no pasar las 600 líneas.

## 11. Diagnóstico por cliente

`python scripts/diagnostico_sugerencias_gastronomia.py [--cliente-id N]`,
portado del padre. Solo lee. Muestra:

- % de pedidos con más de un plato y platos promedio por pedido;
- en qué umbral se cae cada par (soporte, confianza, lift);
- pares y cobertura de franja con los umbrales actuales y con variantes más
  bajas;
- top de pares con nombres;
- tiempo del endpoint con los platos más pedidos.

Cómo decidir:
1. Top con sentido y cobertura razonable → prender y revisar «Ver qué se
   sugeriría» antes de mostrarlo al cajero.
2. Menos del 15% de pedidos con más de un plato → ese negocio vive de reglas
   del dueño (o de complementos de fábrica, §3).
3. No pasa nada con los umbrales actuales y sí con una variante → mirar el top
   de esa variante en varios clientes antes de bajar la constante para todos.
4. Endpoint > 300 ms → cachear el catálogo de palabras por cliente.

## 12. Medición (etapa 6, segunda entrega)

- **Mostrada**: una vez por pedido y par, aunque la franja se redibuje.
- **Tocada**: se agregó desde la franja.
- **Vendida**: el destino terminó en un pedido **cobrado y no anulado** donde
  se mostró, por la franja o por el menú.

Cómo se registra, aislado del pedido:

1. El ítem agregado desde la franja lleva en el carrito `origen_sugerencia`.
   Al guardar el pedido, el payload suma un campo **opcional**
   `sugerencias: {mostradas, tocadas}`. Pedidos sin el campo se guardan igual.
2. El pedido se guarda y se **commitea** primero, por el camino de siempre.
3. Recién después se escriben `gastronomia_sugerencias_pedido` y los contadores
   de mostradas/tocadas, **en su propia transacción**. Si falla: rollback solo
   de eso, log, y la respuesta es la de un pedido guardado.
4. **Vendidas** no se cuentan al guardar: el cobro puede llegar después (caja)
   o no llegar. Las resuelve el cálculo diario cruzando
   `gastronomia_sugerencias_pedido` y los pares mostrados con pedidos cobrados
   no anulados (§2).

Pantalla: tarjeta en Inteligencia de gastronomía con «Pedidos desde "Suelen
llevar"» del período (cobrados, sin anulados), las 5 que más se venden y las 5
que se muestran mucho y no se venden. Es lo que entró por la franja, no «lo
que ganaste gracias a esto».

## 13. Restricciones del repo

- **600 líneas por archivo** (AGENTS §2). Servicio en
  `gastronomia/services/sugerencias/`: `constantes.py`, `calculo.py`
  (portado), `tickets.py` (adaptador §4.1), `afinidad.py` (portado),
  `candidatos.py`, `filtros.py`, `reglas.py`, `config.py`, `tarea.py`,
  `pos.py`, `diagnostico.py`; `medicion.py` en la etapa 6. Modelos en
  `gastronomia/sugerencias_models.py`.
- **Reutilizar** (AGENTS §3): `openProduct` y `products` del POS,
  `GastronomiaChannelPrices`, permisos de gastronomía, `utc_naive_to_local`,
  el patrón del scheduler de peluquería. No duplicar el alta de ítems.
- **Tienda online**: nada de esto toca `/tienda_online` en esta etapa.
- **SQLite y MySQL**: probar el cálculo en los dos (anchos de VARCHAR,
  identificadores < 64, fechas UTC contra cortes locales).
- **Tema oscuro y claro**, escritorio y celular.

## 14. Pruebas

Archivos nuevos (`test_gastronomia_sugerencias*.py`), con datos armados en la
prueba; correr solo esos.

**Cálculo**
- Una regla «hamburguesa → papas» muestra papas al cargar la hamburguesa.
- Una gaseosa presente en el 50% de los pedidos no se sugiere aunque aparezca
  mucho con A (lift). Un par con lift ≥ 1,5 y soporte ≥ 4 sí.
- 3 apariciones juntas no alcanzan (soporte).
- 4 pedidos viejos (peso 0,3) siguen siendo soporte 4.
- Pedidos sin pago, con venta central anulada, encargos y de más de 12
  platos no cuentan.
- Un plato repetido en un pedido cuenta una vez.
- Datos de otro `cliente_id` nunca entran ni salen.
- El candado evita dos cálculos simultáneos; un cálculo que falla deja el
  resultado anterior.

**Filtros**
- Agotado (con control de stock), no disponible, inactivo, no visible,
  excluido, prohibido y ya en el carrito no aparecen.
- Sin reglas ni evidencia: respuesta vacía.

**POS (navegador)**
- La franja aparece al pie del carrito sin mover filas, y el foco no se mueve.
- Tocar una sugerencia abre el mismo modal que el menú; un plato con
  modificadores obligatorios los pide; uno por peso sigue su flujo.
- La píldora muestra el precio del canal elegido; por peso o con opciones con
  precio va sin precio.
- Si el carrito cambia mientras se consulta, la respuesta vieja se descarta.
- Con el endpoint caído (500 o timeout) se carga, se envía a cocina y se cobra
  normal.
- Config apagada: el endpoint devuelve vacío y no hay franja.

**Medición (etapa 6)**
- Un error **de base de datos** forzado al escribir las estadísticas no impide
  guardar el pedido, enviarlo a cocina ni cobrarlo.
- Una franja redibujada varias veces suma 1 mostrada por par.
- Un pedido anulado no suma en «vendidos desde sugerencias».

**Compatibilidad**
- Una instalación existente arranca y crea las tablas sin tocar las demás.

## 15. Orden de entrega

Cada etapa con sus pruebas, verificada en el navegador y commiteada sola.

1. **Tablas + cálculo + diagnóstico.** Correr el diagnóstico con 2 o 3
   clientes reales antes de seguir; ajustar constantes si hace falta.
2. **Pantalla del dueño**: config, reglas, excluidos, «Ver qué se
   sugeriría». Con «Mostrar en el POS» apagado.
3. **Endpoint + franja en el POS.** Prender cliente por cliente.
4. *(Segunda entrega, implementada)* **Medición, fatiga y `factor_aceptacion`.**
   Sin pedidos cobrados expuestos, el orden usa factor 1.

Estimación: 3 a 5 días para las etapas 1–3 portando el código del padre;
2 a 3 días más para la etapa 4.

## 16. Fuera de esta etapa

- Agregar en un toque los platos sin opciones (menú y franja juntos).
- Complementos de fábrica gastronómicos (§3), según el diagnóstico.
- Sugerir el **combo** que contiene lo cargado (`menu_combo_service.py`).
- Sugerencias en la tienda online (respetando el aislamiento de
  `/tienda_online`).
- «Lo de siempre» por cliente final.
- IA: afuera.
