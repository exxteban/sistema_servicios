# Plan de Mejoras: Gastronomía para Pastelería / Cafetería / Panadería

## Objetivo

Hacer que el modo gastronomía sirva también a locales que venden **bollería, café, tortas, porciones y encargos**, no solo a hamburgueserías, lomiterías y pizzerías.

Hoy el flujo es *pedir → cocina → entregar → cobrar*. Una pastelería vende distinto:

- una parte importante de la venta son **encargos para otro día** (torta de cumpleaños para el sábado a las 15:00), normalmente con seña y con una foto de referencia;
- las **tortas enteras se venden por peso**;
- gran parte del producto se **hornea por tanda** (hoy se hicieron 24 medialunas) y lo que sobra es merma;
- una torta entera se vende **entera o por porciones**;
- el cliente de mostrador (café + medialuna) **no necesita pasar por cocina**.

Los clientes actuales son hamburgueserías y similares. **Nada de lo que sigue puede cambiar su comportamiento.**

---

## Decisiones tomadas

| # | Tema | Decisión |
|---|---|---|
| 1 | Seña de un encargo cancelado | Se decide **al cancelar**, con opción múltiple que elige el operador: devolver total, retener total o retener un monto parcial (resto se devuelve). Ver Fase 1. |
| 2 | Quién enciende los flags | **Solo root**, igual que `modo_operacion`, desde "módulos del sistema". |
| 3 | Descuento de stock del encargo | **Al pasar a producción** (`preparando`), no al crear ni al confirmar. |
| 4 | Encargo sin seña | **Permitido**. La seña es opcional por encargo (casilla en el formulario). |
| 5 | Venta por peso | **Sí hace falta ya**: hay clientes que venden tortas enteras por peso. Pasa a ser la Fase 2. |
| 6 | Foto de referencia | **Entra en la Fase 1.** |
| 7 | Balanza | **No hay balanza conectable.** El peso se carga a mano. Muchos locales además tienen tortas de peso fijo (1 kg, 1,5 kg) ya cargadas como producto, o las venden en el mostrador ya pesadas. |
| 8 | Seña retenida en contabilidad | Se desconoce el tratamiento correcto y puede variar por cliente. Se define un **tratamiento por defecto prudente** (ver Fase 1) y las opciones de cancelación disponibles se pueden ajustar por cliente (solo root). Queda pendiente confirmarlo con un contador. |
| 9 | Fotos en la tienda online | **Sí.** El cliente final puede adjuntar foto al pedir un encargo, dentro del mismo panel de pedido que ya existe para hamburguesería, con una versión para tortas/cafetería (Fase 6). |
| 10 | Stock de tortas | **Alcanza con controlar por pieza.** Además, muchas tortas y otros productos se venden también por porciones, lo que refuerza la Fase 3 (abrir torta → porciones). |

---

## Qué ya existe y se reutiliza (no se duplica)

Verificado en el código antes de escribir este plan (regla 3 de `AGENTS.md`):

| Necesidad | Pieza existente | Archivo |
|---|---|---|
| Plantilla de arranque `cafeteria` | `PLANTILLAS['cafeteria']` | `gastronomia/services/menu_plantillas_data.py` |
| Stock por receta con unidades `g`, `ml`, `porcion`, `mazo` | `UNIDADES_STOCK`, `GastronomiaRecetaInsumo` | `gastronomia/services/stock_service.py`, `stock_models.py` |
| Entrada de stock por presentación (bolsa 1 kg = 1000 g) | `registrar_entrada` + `ProductoPresentacionStock` | `stock_service.py` |
| Stock simple de producto del menú (se descuenta al vender) | `control_stock_venta` + `stock_disponible` | `gastronomia/models.py`, `menu_service.py` |
| Modificadores (leche vegetal, shot extra, texto) | `GastronomiaGrupoOpciones` / `GastronomiaOpcionProducto` | `gastronomia/models.py` |
| Cobro y caja del pedido | `cobrar_pedido`, `GastronomiaPedidoPago` | `gastronomia/services/caja_service.py` |
| Retiro en local, mostrador, mesa | `TIPOS_PEDIDO` | `gastronomia/services/pedido_service.py` |
| Alta de columnas sin romper bases existentes | `ensure_gastronomia_schema` | `gastronomia/schema.py` |
| Clientes finales con historial y favoritos | `GastronomiaClienteFinal`, `GastronomiaClienteFavorito` | `gastronomia/customer_models.py` |
| Procesado de imágenes (reduce, convierte a WebP, nombre aleatorio) | `procesar_y_guardar_imagen` | `app/utils/imagenes.py` |
| Guardado y borrado seguro de imágenes del menú | `guardar_imagen_menu`, `eliminar_imagen_producto_menu` | `gastronomia/services/menu_image_service.py` |

### Corrección sobre el diagnóstico inicial

Se había dicho que el stock "no soporta decimales". Es **parcialmente incorrecto**: el stock es entero, pero ya trabaja en la **unidad base** (`g`, `ml`) con presentaciones. Cargar 250 g de harina o una bolsa de 1 kg (= 1000 g) ya funciona. Por eso **este plan NO cambia `Producto.stock_actual` a decimal**: esa tabla es compartida con el backoffice y el riesgo no se justifica. Lo que sí falta es producción por tanda, porciones y merma (Fase 3).

---

## Reglas de protección (valen para todas las fases)

Si un cambio no puede cumplirlas, se frena y se replantea.

1. **Todo detrás de un flag, apagado por defecto.** Cada funcionalidad nueva se activa con un campo booleano en `GastronomiaClienteConfig` con `default=False`. Con el flag apagado, la pantalla, la API y el cálculo de stock/caja deben ser idénticos a hoy.
2. **Columnas nuevas siempre con `default` o `nullable=True`** (regla 4 de `AGENTS.md`). No se renombran ni se reinterpretan columnas existentes ni valores de `estado` / `tipo_pedido` ya usados.
3. **Migraciones en archivo nuevo.** `gastronomia/schema.py` ya tiene 344 líneas y dos caminos (SQLite y MySQL). Lo nuevo va en `gastronomia/schema_pasteleria.py`, que se llama desde `ensure_gastronomia_schema` con el mismo patrón y los mismos dos dialectos.
4. **Archivos nuevos por fase, no engordar los existentes.** `gastronomia/models.py` tiene 578 líneas: los modelos nuevos van en `gastronomia/encargo_models.py` y `gastronomia/produccion_models.py` (como ya se hizo con `stock_models.py`, `channel_models.py`, `customer_models.py`).
5. **Límite de 600 líneas por archivo.** `pedido_service.py` y `pos.js` son candidatos a pasarse: se extrae antes de seguir.
6. **Reutilizar antes de crear.** Si hay lógica parecida que no encaja limpiamente, se extrae la parte común o se crea un adaptador delgado; no se deforma la función existente con condicionales de un solo caso.
7. **Dinero siempre a caja.** Todo cobro adelantado (seña) genera movimiento de caja en la sesión abierta del operador, igual que el abono de reparaciones, para que el arqueo cuadre y no haya doble conteo. Toda devolución de seña genera el egreso correspondiente.
8. **La tienda online solo habla por `/api/tienda/...`** y vive solo en `tienda_online/` (regla 1 de `AGENTS.md`).
9. **Cada fase se cierra con la batería de protección en verde.**

### Batería de tests de protección

```bash
.venv/Scripts/python.exe -m pytest -q test_gastronomia_*.py test_pos_*.py test_caja_*.py test_ventas_*.py test_tienda_*.py
```

### Batería nueva del módulo

```bash
.venv/Scripts/python.exe -m pytest -q test_pasteleria_*.py
```

---

## Flags de configuración (se agregan por fase)

Todos en `GastronomiaClienteConfig`, `Boolean NOT NULL DEFAULT 0`. **Solo root los modifica** (decisión 2).

| Flag | Fase | Qué habilita |
|---|---|---|
| `encargos_activo` | 1 | Pedidos programados con fecha de retiro, seña opcional, fotos y tablero de producción |
| `venta_por_peso_activa` | 2 | Productos que se venden por kilo (tortas enteras) |
| `produccion_diaria_activa` | 3 | Producción por tanda, porciones y merma |
| `venta_rapida_activa` | 4 | Venta de mostrador en un solo paso, sin cocina |
| `propina_activa` | 5 | Propina sugerida en el cobro |

Parámetros asociados (con default que reproduce el comportamiento actual): `encargos_anticipo_horas` (default 0), `encargos_max_por_dia` (default NULL = sin tope), `encargos_max_fotos` (default 5), `encargos_cancelacion_opciones` (default: las tres opciones).

---

## Fase 0 — Red de seguridad

**Objetivo:** línea base medida antes de tocar nada.

- Correr la batería de protección y guardar cantidad de tests y tiempo.
- Crear `test_pasteleria_no_afecta_gastronomia.py` con pruebas de humo:
  - sin ningún flag, crear un pedido de mesa, enviarlo a cocina y cobrarlo da el mismo resultado de caja y stock que hoy;
  - `ensure_gastronomia_schema()` es idempotente: correrlo dos veces sobre una base vieja no falla ni duplica columnas;
  - los flags nuevos existen y valen `False` en una instancia existente.
- Crear `gastronomia/schema_pasteleria.py` (solo estructura y llamada desde `ensure_gastronomia_schema`) para que las fases siguientes sólo agreguen columnas.

**Terminado cuando:** la batería pasa y el test de humo existe y pasa.

---

## Fase 1 — Encargos con seña opcional, fotos y tablero de producción

**Prioridad más alta.** Es lo que más cambia el negocio de una pastelería.

> **Diseño detallado:** [docs/pasteleria_fase1_diseno.md](docs/pasteleria_fase1_diseno.md). Donde ese documento y este plan difieran, **manda el documento de diseño**: se escribió después de leer el código de caja, stock y cocina y corrige varios supuestos de este plan (los ya corregidos están marcados abajo).

### Alcance

1. **Pedido programado.** Un pedido puede tener fecha y hora de retiro (`fecha_programada`, `DATETIME NULL`, hora local). **En esta fase los encargos son solo de tipo `retiro`**; el delivery de encargos queda como extensión. Si es `NULL`, el pedido es inmediato como hoy. (`fecha_programada`, `DATETIME NULL`). Si es `NULL`, el pedido es inmediato como hoy.
2. **Seña opcional.** El formulario de encargo tiene una casilla "Cobrar seña". Si está marcada, se pide monto y método de pago y se cobra en el momento (a caja). Si no, el encargo se guarda sin adelanto. Puede haber más de un adelanto por pedido.
3. **Cancelación con opción múltiple.** Al cancelar un encargo con seña vigente, el operador elige una de tres opciones y ninguna viene preseleccionada:
   - **Devolver todo:** egreso de caja por el total de lo adelantado.
   - **Retener todo:** la seña queda como ingreso del local (no se devuelve nada).
   - **Retener una parte:** el operador indica el monto retenido; el resto se devuelve con un egreso de caja.
   Cada adelanto queda con su estado (`vigente`, `devuelto`, `retenido`) y el monto devuelto, para auditoría.
   **Opciones por cliente:** como la política varía según el local, root puede deshabilitar opciones con el parámetro `encargos_cancelacion_opciones` (lista; por defecto las tres). Un local que nunca retiene seña deja solo "Devolver todo".
4. **Foto de referencia desde esta fase.** Una o más fotos por encargo (tope `encargos_max_fotos`, default 5), subidas desde la cámara o galería del celular y visibles en el tablero y en la hoja de producción.
5. **Personalización.** Texto en la torta ("Feliz cumple Ana") y observaciones. Se apoya en `notas` del pedido y del ítem que ya existen; solo se agrega `texto_personalizado` en el ítem si hace falta mostrarlo destacado en el tablero y el ticket.
6. **Tablero de producción por día.** Pantalla nueva: encargos de hoy y de los próximos días, agrupados por hora, con totales de producción ("mañana: 3 tortas, 40 medialunas"), fotos y estados.
7. **Reglas de capacidad.** Anticipo mínimo (`encargos_anticipo_horas`) y tope de encargos por día (`encargos_max_por_dia`).

### Modelo de datos

- `GastronomiaPedido`: `fecha_programada` (DATETIME NULL), `es_encargo` (BOOLEAN NOT NULL DEFAULT 0). *(Se eliminó `stock_diferido`: todo encargo difiere el stock, no hace falta otra columna.)*
- Tabla nueva `gastronomia_pedido_adelantos` en `gastronomia/encargo_models.py`: `id_adelanto`, `cliente_id`, `pedido_id`, `usuario_id`, `id_sesion_caja`, `id_metodo_pago`, `metodo_pago`, `id_movimiento_caja` (NULL si no fue efectivo), `monto`, `estado` (`vigente` / `aplicado` / `devuelto` / `retenido`, default `vigente`), `monto_devuelto` (default 0), `id_movimiento_devolucion` (NULL), `id_venta`, `observacion`, `fecha`, `fecha_resolucion`, `id_sesion_resolucion`, `usuario_resolucion_id`.
- Tabla nueva `gastronomia_pedido_fotos`: `id_foto`, `cliente_id`, `pedido_id`, `url`, `orden`, `usuario_id`, `fecha`.
- Se **reutiliza** el valor `retiro` de `tipo_pedido`; un encargo es un pedido `retiro` con `es_encargo = 1`. No se agrega un tipo nuevo para no tocar los filtros existentes. *(Se descartó `delivery` en esta fase: `crear_pedido` manda los delivery directo a cocina y `listar_pedidos_cocina` muestra los delivery `abierto`.)*
- La seña **no** se modela con `GastronomiaPedidoPago`, porque `pedido_id` es único ahí (un pedido, un pago). Se reutiliza `app/services/caja_senas.py` (`registrar_movimiento_sena`) y el patrón de `app/services/peluqueria_senas.py`.

### Fotos: cómo se reutiliza lo existente

`menu_image_service.guardar_imagen_menu` ya recibe un `prefijo`, pero la carpeta raíz (`tienda_uploads/gastronomia/menu`) está fija y `eliminar_imagen_producto_menu` solo borra dentro de esa raíz. Las fotos de encargos **no deben ir mezcladas con las del menú**. Se extrae la lógica común a un helper que recibe la raíz como parámetro, y `menu_image_service` pasa a usarlo sin cambiar su comportamiento; el servicio nuevo `encargo_foto_service.py` es un adaptador delgado con raíz `tienda_uploads/gastronomia/encargos/<cliente_id>/`.

Puntos a cuidar:
- **Límite de subida.** `MAX_CONTENT_LENGTH` es 5 MB (`config.py`) y una foto de celular suele pesar más. Se reduce en el navegador antes de enviar (canvas, lado mayor ~1600 px) y además se devuelve un error claro si el servidor rechaza el archivo; no se sube el límite global.
- **Privacidad.** Las imágenes quedan bajo `/static/...`. Los nombres incluyen marca de tiempo y 8 caracteres aleatorios, así que no son adivinables, pero no hay control de acceso. Una foto de torta de cumpleaños es de bajo riesgo; igual no se publican en la API de la tienda ni en la TV.
- **Limpieza.** Al borrar la foto, o al cancelar y archivar un encargo, se elimina el archivo físico con la verificación de ruta segura que ya usa `eliminar_imagen_producto_menu`.

### Puntos delicados (revisar antes de codificar)

- **Consumo de stock (decisión 3).** Hoy `consumir_stock_item` se ejecuta al crear el ítem (`pedido_service.py`). En un encargo el consumo se hace al pasar a `preparando`, con una función idempotente nueva en `pedido_stock.py`. Hay que revisar la rama `cancelado → reabierto`, que hoy vuelve a consumir **todos** los ítems, para que no consuma dos veces ni restaure lo que nunca se consumió.
- **Cierre de caja.** `resumen_pedidos_impagos_para_cierre` no debe tratar un encargo futuro con seña como "pedido impago olvidado". Revisar y excluir encargos programados a futuro.
- **Cocina.** El KDS no debe llenarse con encargos de dentro de 4 días. Un encargo `abierto` ya no aparece en cocina (`listar_pedidos_cocina` no lo lista): aparece cuando alguien pulsa "Enviar a producción". No hay ventana horaria automática. Cocina nunca ve montos de seña ni saldo.
- **Seña retenida — tratamiento por defecto.** Es un ingreso de caja que no corresponde a ninguna venta. Mientras no se confirme con un contador, el sistema hace lo mínimo que no deja diferencias ni decide nada fiscal:
  1. el dinero **queda en caja** con el ingreso original de la seña; **no se crea un movimiento nuevo** (duplicaría el ingreso). Retener solo cambia el estado del adelanto;
  2. el resumen del cierre de caja lo muestra en una **línea propia** ("Señas retenidas"), calculada desde la tabla de adelantos y separada de las ventas, para que se vea de dónde viene;
  3. **no se emite factura ni se registra como venta** automáticamente;
  4. el pedido cancelado conserva el motivo, el monto retenido y quién lo decidió.
  Si más adelante un cliente necesita otro tratamiento (por ejemplo, emitir un comprobante por la retención), se agrega como parámetro; no hace falta decidirlo ahora.
- **Devolución sin caja abierta.** Devolver seña genera un egreso: sin sesión de caja abierta, la devolución se rechaza con mensaje claro, igual que el abono de reparaciones.
- **Factura electrónica.** Siguiendo el precedente de reparaciones y peluquería, la seña se aplica como descuento al cobrar, por lo que la factura se emite sobre el **saldo**. Es una decisión fiscal pendiente (ver "Pendientes por confirmar" y el documento de diseño). Una seña retenida sin venta asociada no se factura automáticamente.

### Archivos

- Nuevos: `gastronomia/encargo_models.py`, `gastronomia/services/encargo_service.py`, `gastronomia/services/adelanto_service.py`, `gastronomia/services/encargo_foto_service.py`, `gastronomia/routes/encargos_routes.py`, `gastronomia/routes/encargos_api_routes.py`, `gastronomia/templates/gastronomia/encargos.html`, `gastronomia/static/js/encargos.js`, `gastronomia/static/js/encargos_fotos.js`.
- Modificados (cambios aditivos, comportamiento actual intacto sin flag): `pedido_service.py`, `caja_service.py`, `cocina_presenter.py`, `menu_image_service.py` (solo extraer helper), `schema_pasteleria.py`, `models.py` (solo las columnas nuevas de `GastronomiaPedido`), tarjeta nueva en `dashboard.html`.

### Tests

`test_pasteleria_encargos.py`, `test_pasteleria_adelantos_caja.py`, `test_pasteleria_encargos_fotos.py`:

- crear encargo con fecha futura y seña en efectivo → existe `MovimientoCaja` ingreso en la sesión abierta;
- crear encargo **sin** seña → no genera movimiento de caja;
- retirar → se cobra solo el saldo; suma de caja = seña + saldo = total, sin doble conteo;
- sin caja abierta, no se puede cobrar seña ni devolverla;
- cancelar con seña → las tres opciones (devolver todo, retener todo, retener parcial) generan los movimientos correctos; retener parcial con monto mayor a lo adelantado se rechaza; cancelar sin elegir opción se rechaza;
- encargo con stock diferido no descuenta al crearse y sí al pasar a `preparando`; cancelar no restaura de más;
- tope diario y anticipo mínimo rechazan correctamente;
- foto: se guarda en la carpeta de encargos del cliente, respeta el tope, rechaza archivos que no son imagen y se borra al eliminarla; un cliente no puede ver ni borrar fotos de otro;
- con `encargos_activo = False` los endpoints nuevos devuelven 404/403 y el POS no muestra los controles;
- el cierre de caja no marca como impago un encargo futuro con seña.

**Terminado cuando:** se puede tomar un encargo con o sin seña y con foto, verlo en el tablero del día de retiro, retirarlo cobrando el saldo, cancelarlo eligiendo qué hacer con la seña, y el arqueo cuadra en todos los casos.

---

## Fase 2 — Venta por peso (tortas enteras)

Se adelantó porque ya hay clientes que lo necesitan.

### Problema

`GastronomiaPedidoItem.cantidad` es entero y ese valor atraviesa ticket, factura electrónica (`venta_integration_service.py` crea el detalle de venta con `cantidad` entera y precio unitario = subtotal / cantidad), stock y caja. Cambiarlo a decimal sería un cambio transversal de alto riesgo.

### Enfoque elegido: la pieza pesada es una unidad

Una torta pesada se vende como **1 unidad cuyo precio resulta de peso × precio por kilo**. `cantidad` sigue siendo 1, así que venta, factura, caja y stock siguen funcionando sin tocarse. El peso queda registrado en el ítem y se muestra en ticket y comanda.

### Alcance

1. Producto marcado "se vende por kilo": su `precio` pasa a significar precio por kg (se agrega `unidad_venta` para no reinterpretar la columna sin avisar).
2. En el POS, al agregar un producto por kilo se pide el **peso (kg, hasta 3 decimales)** y se calcula el precio de la línea. Un solo kilo no se repite: dos tortas = dos líneas, cada una con su peso.
3. El nombre del ítem se congela con el peso ("Torta de chocolate · 1,250 kg") para que ticket, factura y reportes lo muestren sin cambiar sus plantillas.
4. Menú, TV y tienda online muestran "$X / kg".
5. **Atajos de peso** en el modal (por ejemplo 1 kg, 1,5 kg, 2 kg, configurables) para los pedidos "torta de 1 kg o 1,5 kg", más un campo libre para el peso real. No hay balanza: el peso siempre se carga a mano.

**Dos formas de vender una torta, ambas soportadas:** (a) producto **por kilo** con peso variable (esta fase); (b) producto de **peso fijo** ya cargado ("Torta de chocolate 1 kg" a precio fijo), que funciona hoy sin cambios y en la Fase 4 puede agruparse como variantes de un mismo producto.
5. **Encargo por peso:** el precio es estimado con el peso solicitado y se **ajusta con el peso real al retirar**, recalculando el saldo.

### Modelo de datos

- `GastronomiaProducto`: `unidad_venta` (VARCHAR(10) NOT NULL DEFAULT `'unidad'`; valores `unidad` / `kg`).
- `GastronomiaPedidoItem`: `peso_kg` (NUMERIC(10,3) NULL), `precio_por_kg` (NUMERIC(15,2) NULL).

### Puntos delicados

- **Promociones.** El cálculo de promociones asume cantidades enteras (`calculate_promotion_totals`). Un producto por kilo queda **excluido** de promociones por cantidad.
- **Precios por canal.** `GastronomiaProductoPrecioCanal` guarda un precio por canal; para productos por kilo ese precio es por kg. Verificar que `channel_price_service.py` no asuma unidad.
- **Cantidad forzada a 1.** Validar en `pedido_service.py` / `pedido_validation_utils.py` que un producto por kilo no admita `cantidad > 1` ni peso ≤ 0.
- **Stock.** Un producto por kilo se controla con `control_stock_venta` (cuenta tortas, no gramos). La receta por insumos es **por unidad**, así que descuenta la cantidad de una torta estándar aunque la pesada sea distinta. Es una limitación **aceptada** (decisión 10); se documenta en la pantalla de receta.
- **Encargo con seña y peso real menor.** Si el peso real baja el total por debajo de lo adelantado, el excedente se devuelve con un egreso de caja (misma regla de devolución de la Fase 1).
- **Modificadores y descuentos de línea.** `precio_unitario` y `subtotal` de una pieza pesada deben quedar consistentes con el cálculo actual (`precio_unitario = subtotal / cantidad`).
- **Factura electrónica.** Como `cantidad = 1`, se factura la pieza por su importe. Confirmar con el flujo de `factura_electronica_service.py` que la descripción con el peso no excede el largo permitido.
- **Balanza.** El peso se carga siempre a mano (decisión 7). Conectar una balanza (USB/serie/Bluetooth) queda fuera de alcance salvo que un cliente lo pida.

### Archivos

- Nuevos: `gastronomia/services/peso_service.py` (cálculo y validación de peso), `gastronomia/static/js/pos_peso.js`.
- Modificados (aditivos): `models.py` (columnas), `pedido_service.py` (rama de ítem por peso), `menu_service.py` (alta del producto), `menu_config.html` / `menu_config.js` (casilla y unidad), `pos.js` (modal de peso, vía el archivo nuevo), `ticket.html` (línea de peso), `menu_tv_service.py` y la API de la tienda (mostrar "/ kg"), `schema_pasteleria.py`.

### Tests

`test_pasteleria_venta_por_peso.py`:

- 1,250 kg × $X/kg crea una línea de cantidad 1 con precio correcto y la cobra con caja y venta consistentes;
- peso 0, negativo o cantidad > 1 se rechazan;
- el producto por kilo no recibe promociones por cantidad;
- el ticket muestra el peso;
- encargo por peso: ajustar al peso real recalcula el saldo, y si el total queda por debajo de la seña se devuelve el excedente;
- con `venta_por_peso_activa = False` no aparece la opción en el menú ni en el POS, y los productos existentes no cambian.

**Terminado cuando:** una torta se pesa, se cobra por su peso real y el ticket, la venta y la caja coinciden.

---

## Fase 3 — Producción diaria, porciones y merma

> **Diseño detallado:** [docs/pasteleria_fase3_diseno.md](docs/pasteleria_fase3_diseno.md). Manda sobre este plan; corrige en particular que la tanda **suma** al stock en lugar de fijarlo.

### Alcance

1. **Producción por tanda.** Registrar "hoy hice 24 medialunas" que fija `stock_disponible` del producto (ya existe y ya se descuenta al vender) y deja un registro con fecha y usuario. No se crea un segundo mecanismo de stock.
2. **Cierre del día.** Registrar lo que sobró; la merma = producido − vendido − sobrante, con motivo (vencido, golpeado, regalado, consumo propio).
3. **Torta entera → porciones.** Relación entre un producto "entero" y su producto "porción" (1 torta = 12 porciones). Acción "abrir torta": resta 1 al entero y suma N al stock de porciones. No toca el camino de venta. Muchas tortas y otros productos se venden también por porciones, así que esta relación es de uso frecuente y debe poder cargarse en pocos toques desde el propio listado de stock.
4. **Reporte de merma** por producto y por período, con valorización al costo de receta.

### Modelo de datos (`gastronomia/produccion_models.py`)

- `gastronomia_produccion_registros`: `cliente_id`, `producto_id`, `fecha`, `tipo` (`produccion` / `cierre` / `merma`), `cantidad`, `motivo`, `usuario_id`.
- `gastronomia_producto_porciones`: `cliente_id`, `producto_entero_id`, `producto_porcion_id`, `porciones` (entero ≥ 1), `activo`.

### Puntos delicados

- Hoy `control_stock_venta` es un switch por producto. Producción diaria debe leerlo, no reemplazarlo.
- "Abrir torta" debe ser atómica (bloqueo de fila como ya hace `_bloquear_producto_menu`) y registrar su movimiento.
- Una torta vendida por peso (Fase 2) y una torta abierta en porciones coexisten: abrir una torta por peso descuenta 1 del stock de piezas, igual que cualquier otra.
- No hay que mezclar merma de insumos (materia prima) con merma de producto terminado: son dos reportes distintos.

### Tests

`test_pasteleria_produccion.py`: registrar tanda, vender, cerrar y verificar merma; abrir torta con y sin stock suficiente; concurrencia básica; sin flag no aparecen los controles.

**Terminado cuando:** a la mañana se carga la producción, al cierre se declara el sobrante y el reporte muestra la merma del día.

---

## Fase 4 — Venta rápida de mostrador y variantes

### Alcance

1. **Venta rápida.** Con `venta_rapida_activa`, un pedido de mostrador se arma y se cobra en un solo paso, sin pasar por el estado de cocina. Productos marcados "requiere preparación" (café, tostado) sí generan aviso a barra; los demás (medialuna, porción) no.
2. **Pantalla de barra simple** para lo que sí se prepara, más liviana que el KDS actual.
3. **Variantes de tamaño y formato.** Torta de 8/12/20 porciones, docena y media docena: un producto con variantes y precio propio, en lugar de forzar `precio_delta` en un grupo de opciones.
4. **Promoción por horario** ("promo desayuno" de 7 a 11). **Verificar primero** qué admite el sistema de promociones actual (`promociones.js`, `inteligencia_promos.py`); si ya soporta franjas, solo se configura; si no, se extiende con campos nuevos nullable.

### Modelo de datos

- `GastronomiaProducto`: `requiere_preparacion` (BOOLEAN NOT NULL DEFAULT 1, así el comportamiento actual no cambia).
- Variantes: tabla nueva `gastronomia_producto_variantes` (`producto_id`, `nombre`, `precio`, `orden`, `activo`), con el nombre de la variante congelado en el ítem del pedido. Debe convivir con los precios por canal (`GastronomiaProductoPrecioCanal`) y con la venta por peso: definir en el diseño detallado si una variante aplica a productos por kilo (propuesta: no, son excluyentes).

### Tests

`test_pasteleria_venta_rapida.py`, `test_pasteleria_variantes.py`: cobro en un paso genera pedido cobrado, venta y movimiento de caja correctos; ítems sin preparación no llegan a cocina; variante cambia el precio y queda congelada en el ítem; con el flag apagado el flujo es idéntico al actual.

**Terminado cuando:** vender café + medialuna en el mostrador toma pocos toques y deja caja y stock correctos.

---

## Fase 5 — Propina, alérgenos y fidelización

Mejoras chicas y de bajo riesgo.

1. **Propina** (`propina_activa`). Campo `propina` en el pago (`NUMERIC NOT NULL DEFAULT 0`). **Importante:** la propina no forma parte del total facturable; revisar `factura_electronica_service.py` para que no entre en la factura y sí en el arqueo de caja.
2. **División de cuenta** simple en el cobro de mesa (partes iguales). **Ojo:** `GastronomiaPedidoPago.pedido_id` es único (un pedido, un pago) y `cobrar_pedido` cobra el pedido completo, así que la división no se resuelve reutilizando esa tabla. Hay que diseñarla aparte, probablemente como varios `PagoVenta` en una sola venta (como el método `mixto`), antes de comprometerla.
3. **Alérgenos y etiquetas** en el producto: gluten, frutos secos, lácteos, huevo; marcas "sin TACC", "vegano", "sin azúcar". Visibles en el menú, la TV y la API `/api/tienda/...`. Columna `etiquetas` (texto, nullable).
4. **Tarjeta de sellos** ("10 cafés, 1 gratis") sobre `GastronomiaClienteFinal`, con tabla propia de sellos. Se revisa antes que no se duplique con la fidelización de `test_clientes_fidelizacion.py`.

### Tests

`test_pasteleria_propina_caja.py`, `test_pasteleria_etiquetas.py`: la propina entra a caja pero no a la factura; las etiquetas aparecen en la API pública; sin flags, nada cambia.

---

## Fase 6 — Plantilla y reportes

1. **Plantilla `pasteleria`** en `menu_plantillas_data.py`: medialunas, facturas, tortas (por kilo y por tamaño), porciones, sándwiches de miga, cafés con modificadores y bebidas. Verificar que el formato de plantilla soporte `unidad_venta` y variantes; si no, se actualiza el formato.
2. **Reportes por franja horaria** (mañana / tarde) y por categoría, para decidir cuánto producir. Reutilizar `reportes_service.py` y `inteligencia_service.py`.
3. **Rentabilidad por producto** con costo de receta en gramos, apoyada en `inteligencia_margen.py` (ya existe).
4. **Tienda online para cafetería/tortas** (ver sección siguiente). Se hace al final porque depende de las Fases 1, 2 y 3.

### Tienda online: encargos con foto (versión cafetería/tortas)

**Qué existe hoy** (revisado): el pedido web de gastronomía vive en `tienda_online/src/components/ui/GastronomiaOrderPanel.jsx` (283 líneas), con modalidades delivery y retiro (`tienda_delivery_activo`, `tienda_retiro_activo`) y el endpoint `POST /api/tienda/<slug>/gastronomia/pedido` (`app/routes/tienda_gastronomia_api.py`). **No hay subida de archivos ni selección de fecha/hora.** Por eso la foto en la tienda requiere un endpoint público nuevo.

**Alcance** (misma experiencia que hamburguesería, con lo que necesita una pastelería):
1. **Modalidad "Encargo"** junto a delivery y retiro, activable con `tienda_encargos_activo` (junto a las otras dos en `app/models/tienda.py` y `app/bootstrap/tienda_schema.py`). Solo puede activarse si root habilitó `encargos_activo`.
2. **Fecha y hora de retiro** (respetando `encargos_anticipo_horas` y `encargos_max_por_dia`), **texto de personalización** y **fotos de referencia**.
3. **Catálogo:** etiqueta "disponible hoy / sobre pedido", precio "/ kg" en productos por kilo, y etiquetas de alérgenos (Fase 5) si existen.
4. **El encargo web es una solicitud, no un pedido cerrado.** Entra a `pedidos_tienda` como pendiente de confirmación: el local revisa foto, peso y precio (en tortas por kilo el total es estimado), acuerda la seña por WhatsApp y recién ahí lo confirma. **No hay cobro online** en esta versión.

**Subida pública de fotos (diseño):**
- Endpoint nuevo `POST /api/tienda/<slug>/gastronomia/encargo/foto` (multipart), que guarda la imagen como **foto huérfana** y devuelve un identificador. El pedido (`POST .../gastronomia/pedido`) referencia esos identificadores; al crearse el encargo, las fotos pasan a ser del pedido.
- **Anti-abuso:** limitador por IP y por tienda (reutilizar el patrón de `_is_lead_rate_limited` en `tienda_api.py`, extrayéndolo a un helper compartido en lugar de copiarlo), tope de fotos por solicitud, validación real del contenido de la imagen (ya lo hace `procesar_y_guardar_imagen`), campo trampa (honeypot) como el de los leads, y el flag del local debe estar activo.
- **Limpieza:** las fotos huérfanas (subidas pero nunca asociadas a un pedido) se borran pasadas unas horas.
- **Peso del archivo:** reducción en el navegador antes de subir, por el límite de 5 MB.
- **CSRF:** igual que el pedido público actual (`@csrf.exempt`), por lo tanto la protección real es el limitador y la validación; no se asume que el endpoint sea confiable.

**Estructura del código (límite de 600 líneas):** `GastronomiaOrderPanel.jsx` no se engorda. Se crea `tienda_online/src/components/ui/encargo/` con `EncargoFields.jsx`, `FotosReferencia.jsx` y `FechaRetiroPicker.jsx`, un hook `useEncargoFotos.js` en `hooks/` y las llamadas nuevas en `services/` (separadas de `tiendaApi.js`, que ya tiene 262 líneas). Todo dentro de `tienda_online/`, hablando solo con `/api/tienda/...` (regla 1 de `AGENTS.md`).

**Tests:** `test_pasteleria_tienda_encargos.py` (rate limit, tope de fotos, archivo no imagen, foto huérfana no accesible desde otro slug, encargo web entra como pendiente, flag apagado devuelve 404/403) y la batería existente `test_tienda_gastronomia_modalidades.py` / `test_tienda_gastronomia_presupuesto.py` sigue en verde.

---

## Orden de ejecución y dependencias

```text
Fase 0 ──> Fase 1 ──> Fase 2 ──> Fase 3 ──> Fase 6 (tienda y reportes)
              │                     │
              └──────> Fase 4 ──────┘
                       Fase 5 (independiente, puede ir en cualquier momento tras la 0)
```

- Fase 1 es la que más valor da y la que más riesgo tiene (toca caja y stock): se hace primero y con más tests.
- Fase 2 depende de la 1 solo en el caso "encargo por peso"; la venta por peso en el mostrador puede salir antes si algún cliente la necesita primero (se prueba con encargos desactivados).
- Fases 3 y 4 son independientes entre sí.
- Fase 5 puede intercalarse como trabajo de relleno.

## Pendientes por confirmar

No quedan decisiones de diseño abiertas. Quedan dos verificaciones externas:

1. **Seña retenida:** confirmar con un contador (o con el primer cliente real que la use) si el tratamiento por defecto de la Fase 1 (ingreso de caja en línea propia, sin factura) es suficiente o si necesita emitir comprobante. Si cambia, se agrega como parámetro sin tocar el flujo.

2. **Factura electrónica con seña:** confirmar con un contador si facturar solo el saldo (como hacen hoy reparaciones y peluquería) es correcto, o si hay que facturar el total con dos pagos. Hasta confirmarlo, no activar `encargos_activo` en un cliente con facturación electrónica real.

Quedan para después, solo si un cliente lo pide: conexión con balanza, descuento de insumos proporcional al peso y cobro online de la seña.

## Primer paso sugerido

Fase 0 completa y, en la Fase 1, un diseño detallado por escrito de los puntos delicados (stock diferido, cierre de caja, cocina, seña retenida) **antes** de escribir código.
