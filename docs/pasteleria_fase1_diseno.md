# Diseño detallado — Fase 1: Encargos con seña, fotos y tablero

Complementa `plan_pasteleria.md` (Fase 1). Es un documento de diseño: **no hay código todavía**. Todo lo que dice "existe" fue verificado leyendo el código actual.

---

## 0. Hallazgos que cambian el plan

Al leer el código aparecieron cosas que corrigen o simplifican lo escrito en `plan_pasteleria.md`:

| # | Hallazgo | Consecuencia |
|---|---|---|
| 1 | Ya existe `app/services/caja_senas.py` (`registrar_movimiento_sena`) y un servicio equivalente para peluquería (`app/services/peluqueria_senas.py`) con seña → caja → descuento al cobrar. | La seña de encargos **reutiliza** `registrar_movimiento_sena` y copia el patrón de peluquería. No se inventa un mecanismo nuevo. |
| 2 | `GastronomiaPedidoPago.pedido_id` es **único**: un pedido admite un solo pago. | La Fase 5 decía que "ya admite pagos múltiples": es **falso**. La seña **no** puede modelarse como un `GastronomiaPedidoPago`; va en una tabla propia. La "división de cuenta" de la Fase 5 se rediseña aparte. |
| 3 | El efectivo esperado del arqueo (`SesionCaja.calcular_total_efectivo`) suma **todo** `MovimientoCaja` ingreso y resta todo egreso, sin mirar el método. | Una seña por tarjeta o transferencia **no debe** crear `MovimientoCaja`, o el arqueo mostraría efectivo que no existe. Solo la seña en efectivo mueve caja. |
| 4 | La seña retenida **no necesita un movimiento nuevo**: el dinero ya está en caja como ingreso desde que se cobró. | Se corrige el plan, que proponía un movimiento `gastronomia_sena_retenida` (duplicaría el ingreso). Retener cambia el estado del adelanto y se informa por consulta. |
| 5 | `crear_pedido` manda los pedidos **delivery** (no tienda) directo a `enviado_cocina`, y `listar_pedidos_cocina` muestra los delivery `abierto`. | Un encargo delivery caería en cocina el mismo día que se toma. **La Fase 1 limita los encargos a `retiro`.** Delivery de encargos queda como extensión. |
| 6 | La cocina solo lista `enviado_cocina`, `preparando`, `listo`, `en_camino`. Un pedido `abierto` no aparece. | Un encargo `abierto` ya es invisible para cocina sin tocar `listar_pedidos_cocina`. Basta un botón explícito "Enviar a producción". No hace falta una ventana horaria automática. |
| 7 | La columna `stock_diferido` del plan es redundante. | Con la decisión 3, **todo encargo difiere el stock**. Se usa solo `es_encargo`. |
| 8 | `pedido_service.py` tiene 551 líneas. | Cualquier lógica nueva va en archivos nuevos; `pedido_service.py` solo delega con cambios mínimos. |

---

## 1. Modelo de datos (resumen)

`GastronomiaPedido` (3 columnas, todas con `default`/`NULL`):
- `es_encargo` BOOLEAN NOT NULL DEFAULT 0.
- `fecha_programada` DATETIME NULL, hora **local** del negocio (como la ingresa el operador). Para compararla se usa `app.utils.helpers.now_local()`; el resto de las fechas del módulo usa `utcnow()`, no se mezclan.
- `texto_personalizado` en el ítem (`GastronomiaPedidoItem`, VARCHAR(240) NULL), solo si se necesita destacarlo en tablero y ticket.

Tabla `gastronomia_pedido_adelantos` (`gastronomia/encargo_models.py`):

| Columna | Detalle |
|---|---|
| `id_adelanto`, `cliente_id`, `pedido_id` | claves; índices por `pedido_id` |
| `usuario_id`, `id_sesion_caja`, `id_movimiento_caja` | quién y en qué caja; `id_movimiento_caja` es NULL si no fue efectivo |
| `id_metodo_pago`, `metodo_pago` | método con el que se cobró la seña |
| `monto` | NUMERIC(15,2) > 0 |
| `estado` | `vigente` → `aplicado` / `devuelto` / `retenido` |
| `monto_devuelto` | NUMERIC DEFAULT 0 (devolución parcial si se retiene una parte) |
| `id_movimiento_devolucion` | egreso de caja, NULL si no hubo |
| `id_venta` | venta donde se aplicó como descuento |
| `fecha`, `fecha_resolucion`, `id_sesion_resolucion`, `usuario_resolucion_id` | auditoría |
| `observacion` | motivo |

Retención parcial = `estado = 'retenido'` con `monto_devuelto > 0`. Monto retenido = `monto − monto_devuelto`.

Constante de referencia de caja: `REF_SENA_ENCARGO = 'gastronomia_sena'` (se define en el servicio, como hace peluquería, sin importar el paquete de rutas de caja).

---

## 2. Punto delicado A — Stock diferido (decisión 3)

### Cómo funciona hoy
`_crear_item_desde_payload` llama a `consumir_stock_item(item)` **al crear cada ítem**. `_reemplazar_items_pedido` primero restaura el stock de los ítems anteriores y luego crea los nuevos. `cambiar_estado_pedido` restaura al pasar a `cancelado` y, al salir de `cancelado`, **vuelve a consumir todos los ítems sin preguntar** si ya estaban consumidos. La fuente de verdad de qué se consumió es `GastronomiaPedidoItemConsumo` (con `restaurado`).

### Diseño
1. Nuevo archivo `gastronomia/services/pedido_stock.py`, que concentra la política de stock por pedido:
   - `consumir_stock_pedido(pedido)`: consume solo los ítems que **no tienen consumo activo** (idempotente).
   - `restaurar_stock_pedido(pedido)`: restaura consumos activos; sin consumos activos no hace nada.
   - `aplicar_stock_por_transicion(pedido, estado_anterior, estado_nuevo)`: única función que decide.
2. **Pedido normal (`es_encargo = 0`)**: el comportamiento es **exactamente el actual** (consumo al crear, restaurar al cancelar, reconsumir al reabrir). Es regla de protección: los tests de humo de la Fase 0 ya lo fijan.
3. **Encargo**:

| Transición | Acción de stock |
|---|---|
| Crear / editar encargo (`abierto`) | ninguna (no se consume) |
| A `preparando` (o `listo` / `entregado` sin haber pasado por `preparando`) | `consumir_stock_pedido`: consume lo que no esté consumido |
| A `cancelado` | `restaurar_stock_pedido` (restaura solo lo realmente consumido) |
| Reabrir desde `cancelado` | **no** consume; vuelve a la espera. Consume recién al pasar a `preparando` |
| `preparando` → `abierto` / `enviado_cocina` (marcha atrás) | no restaura (decisión simple: lo hecho, hecho). Se registra evento |

4. `_crear_item_desde_payload` recibe un parámetro `diferir_stock` (False por defecto) y se lo pasa desde `crear_pedido` / `actualizar_pedido_abierto` según `es_encargo`. Es el único cambio dentro de `pedido_service.py` además de delegar `cambiar_estado_pedido` a `aplicar_stock_por_transicion`.
5. **Faltantes**: el stock es "blando": consumir nunca bloquea, deja `faltante` y alerta, igual que hoy. Al pasar a `preparando` puede aparecer un faltante que al tomar el encargo no se veía. Para anticiparlo, el tablero muestra una **proyección de faltantes por día** reutilizando `previsualizar_stock_carrito` (`stock_preview_service.py`), sin reservar nada.
6. Los pedidos con `control_stock_venta` (producto terminado con `stock_disponible`) siguen el mismo calendario: se descuentan al pasar a producción, no al tomar el encargo.

### Alternativa descartada
**Reserva real** (stock "comprometido" al tomar el encargo). Evitaría sorpresas pero obligaría a un segundo contador de stock en inventario central, compartido con el backoffice. Se descarta para esta fase.

### Riesgos y cómo se prueban
- Doble consumo al reabrir un cancelado: test "cancelar y reabrir un encargo no consume dos veces ni consume sin producción".
- Anulación de venta (`registrar_anulacion_gastronomia_desde_venta_central`) llama a `_restaurar_stock_items`: debe seguir funcionando para encargos (restaura lo consumido).
- Pedidos normales idénticos: la batería de protección completa + `test_pasteleria_no_afecta_gastronomia.py`.

---

## 3. Punto delicado B — Cierre de caja

### Cómo funciona hoy
- `listar_pedidos_caja` y `resumen_pedidos_impagos_para_cierre` usan `_query_pedidos_caja`: pedidos en `abierto`, `enviado_cocina`, `preparando`, `listo`, `entregado` **sin pago**.
- Agrupa en `en_curso` (`abierto`/`enviado_cocina`/`preparando`, informativo) y `terminados` (`listo`/`entregado`, **exige confirmar** al cerrar).
- `app/routes/caja/gastronomia_cierre.py` arma el aviso y agrega una observación al cierre.

### Problemas con encargos
1. Un encargo para dentro de 5 días aparecería en la lista de cobro de la caja del día.
2. Una torta `lista` esperando retiro mañana forzaría la confirmación de "pedidos terminados sin cobrar" todas las noches.

### Diseño
1. **Lista de cobro de caja**: un encargo aparece cuando está `listo`/`entregado`, o cuando su `fecha_programada` es de hoy o anterior. Los futuros no se listan. Con badge "Encargo" y el **saldo** (no el total).
2. **Resumen de cierre**: se agrega un grupo nuevo `encargos_pendientes` (informativo, **no bloquea**) con encargos programados para después de hoy: cantidad, total, seña recibida y saldo.
   - Un encargo `listo`/`entregado` cuya fecha programada es **hoy o anterior** sigue en `terminados` (requiere atención: debió retirarse).
   - Los encargos futuros salen de `en_curso` y `terminados` para no duplicarse.
3. **Arqueo**: no requiere cambios. La seña en efectivo es un `MovimientoCaja` ingreso y `calcular_total_efectivo` ya lo suma; la devolución es un egreso y ya lo resta.
4. **Informe de señas del turno**: un bloque nuevo en el cierre, calculado por consulta sobre `gastronomia_pedido_adelantos` (no sobre movimientos):
   - señas recibidas en la sesión, con desglose por método;
   - devoluciones hechas en la sesión;
   - señas retenidas resueltas en la sesión (**línea propia**, separada de ventas);
   - señas aplicadas al cobrar un saldo en la sesión.
5. Se extiende el módulo ya existente `app/routes/caja/gastronomia_cierre.py` y su bloque en la plantilla, sin tocar el cálculo del arqueo.

### Seña por método de pago
- **Efectivo**: crea `MovimientoCaja` (ingreso) con `registrar_movimiento_sena`; requiere caja abierta del operador.
- **Tarjeta / transferencia / QR**: se registra el adelanto con su método, **sin** `MovimientoCaja`. Aparece en el informe de señas del cierre, pero no altera el efectivo esperado.
- **Devolución**: en efectivo → egreso de caja (requiere caja abierta). Si fue por otro método → solo se marca `devuelto` con la nota "devuelta por el mismo medio fuera de caja".

### Cobro del saldo (cómo se descuenta la seña)
Siguiendo el precedente de reparaciones y peluquería, **la seña se aplica como descuento** al cobrar:
- `cobrar_pedido` calcula `sena = adelantos vigentes` y exige `descuento_manual + sena <= subtotal`.
- `crear_venta_central_desde_pedido` recibe un parámetro opcional nuevo `sena_aplicada` (default 0): `Venta.descuento_monto = descuento + sena`, `Venta.descuento_manual_monto = descuento` (el manual no se contamina con la seña), `Venta.total = subtotal − descuento − sena`, y se deja constancia en las observaciones ("Seña aplicada: X").
- `GastronomiaPedidoPago`: `subtotal` = total del pedido, `descuento_monto` = descuento + seña, `total_cobrado` = saldo.
- Los adelantos pasan a `aplicado` con `id_venta`. La caja suma seña + saldo = total, sin doble conteo.
- **Regla**: la seña debe ser **menor** que el total (igual que peluquería). Si el cliente paga todo por adelantado, se usa el cobro normal.
- Si se edita el encargo (solo estando `abierto`), el nuevo total debe seguir siendo mayor que la suma de adelantos vigentes.
- **Cobro por cola central** (`crear_cola_cobro_central_desde_pedido`): en la Fase 1, un encargo con adelantos vigentes **se cobra solo desde la caja de gastronomía**; la función rechaza con mensaje claro. El caso se amplía luego si hace falta.
- **Anulación de la venta**: `registrar_anulacion_gastronomia_desde_venta_central` devuelve los adelantos `aplicado` a `vigente` (el pedido queda `cancelado`; el operador decide después devolver o retener). Sin esto, la seña quedaría "aplicada" a una venta anulada.

### Facturación electrónica (pendiente de confirmar)
Con este diseño la factura se emite sobre el **saldo** (`validar_factura_antes_de_cobrar(cliente, subtotal − descuento − sena)`), igual que en reparaciones y peluquería. Hoy `facturacion_electronica` no tiene tratamiento de señas. Una alternativa más correcta fiscalmente es facturar el total con dos pagos (seña ya cobrada + saldo), pero cambia cómo se crea y se anula la venta. **Se deja como decisión a confirmar con un contador antes de activar encargos con facturación electrónica en un cliente real.** Mientras tanto, el flag `encargos_activo` convive con el comportamiento heredado.

---

## 4. Punto delicado C — Cocina

### Cómo funciona hoy
- `listar_pedidos_cocina`: estados `enviado_cocina`, `preparando`, `listo`, `en_camino` **más** delivery `abierto` que no sea de tienda.
- `crear_pedido` fija `enviado_cocina` para delivery que no sea de tienda.
- `cocina.js` solo muestra `kitchenStates`; el presentador de cocina oculta datos de dinero.

### Diseño
1. **Sin cambios en `listar_pedidos_cocina`** ni en `cocina.js`: un encargo `retiro` en `abierto` no aparece.
2. **Encargos solo `retiro` en la Fase 1** (validación en `encargo_service`). Evita el atajo delivery→cocina descrito en el hallazgo 5.
3. **Enviar a producción**: botón en el tablero que usa `enviar_pedido_cocina` (ya existente) y deja el encargo en `enviado_cocina`; desde ahí es el flujo normal de cocina (`tomar` → `preparando` consume stock → `listo`). No hay ventana horaria automática: lo decide una persona, y el tablero resalta los de hoy y los vencidos.
4. **Qué ve cocina de un encargo**: nombre del cliente, hora y fecha de retiro, **texto de personalización**, notas, fotos de referencia y estado. **Nunca** montos de seña ni saldo: las claves nuevas (`adelantos`, `sena_total`, `saldo`) se agregan a `_CLAVES_PRIVADAS_COCINA` en `cocina_presenter.py`.
5. Las fotos se sirven por URL estática (sin control de acceso, ver plan); la tarjeta de cocina las muestra como miniatura que abre la foto.
6. **Otras listas que tratan `abierto` como "en curso"** y que hay que revisar una por una antes de codificar (auditadas con búsqueda en el código):

| Lugar | Qué hacer |
|---|---|
| `pos_routes.py:29` (reabrir pedido abierto en el POS) | los encargos se editan desde su propia pantalla; en el POS se excluyen o se redirigen |
| `pedido_api_routes.py` → `listar_pedidos` (GET `/pedidos`) | excluir encargos del listado operativo por defecto; filtro explícito `es_encargo` |
| `salon_service.py` (mesas) | no aplica: solo mira pedidos de mesa y los encargos son `retiro` |
| `tienda_pedido_service.py` (solicitudes web) | no aplica en la Fase 1; se revisa en la Fase 6 |
| `delivery_service.py` | no aplica: encargos no son delivery |
| `caja_service.py` | ver sección 3 |

---

## 5. Punto delicado D — Seña retenida

### Reglas
- Al cancelar un encargo con adelantos **vigentes**, el operador **debe elegir** una opción; ninguna viene preseleccionada:
  1. **Devolver todo**: egreso de caja por el total (solo en efectivo, ver arriba).
  2. **Retener todo**: sin movimiento de caja. El adelanto queda `retenido`.
  3. **Retener una parte**: el operador indica el monto retenido; el resto se devuelve. `monto_devuelto = monto − retenido`. El monto retenido debe ser mayor que 0 y menor que `monto`.
- Root puede quitar opciones por cliente con `encargos_cancelacion_opciones` (por defecto las tres). Si el local solo ofrece "Devolver todo", la pantalla no muestra las otras.
- Con varios adelantos, la decisión se toma **una vez** sobre el total adelantado y se reparte en orden cronológico.
- **Permiso**: devolver o retener requiere el permiso de caja de gastronomía (`PERMISO_CAJA`) o ser admin. Tomar el encargo con seña solo requiere el permiso de POS y caja abierta propia.
- **No se puede cancelar** si el pedido ya tiene pago (regla ya vigente en `cambiar_estado_pedido`). Para un encargo ya cobrado se anula la venta y recién ahí se cancela.
- **Cancelación en una transacción**: validar → decidir adelantos → egreso(s) de caja → estado del pedido → restaurar stock (si había consumo) → evento. Si falla algo (por ejemplo, sin caja abierta para devolver) no se cancela nada.

### Tratamiento contable por defecto (hasta confirmar con un contador)
- El dinero retenido **ya está en caja** como ingreso desde que se cobró la seña. No se agrega movimiento.
- El cierre de caja lo muestra en una **línea propia** ("Señas retenidas"), calculada desde `gastronomia_pedido_adelantos`, atribuida a la sesión en la que se resolvió (`id_sesion_resolucion`).
- **No** se factura ni se registra como venta.
- Quedan registrados quién decidió, cuándo y por qué (`observacion` del adelanto + evento del pedido).

### Pendiente
Confirmar si la seña retenida requiere comprobante. Si cambia, se agrega como parámetro sin tocar el flujo de caja.

---

## 6. Orden de implementación sugerido dentro de la Fase 1

Cada paso termina con tests y batería de protección en verde:

1. **Modelos y migración**: columnas de `es_encargo` / `fecha_programada`, tablas de adelantos y fotos, `texto_personalizado`. Test de humo de migración ampliado.
2. **`pedido_stock.py`** + delegación mínima en `pedido_service.py`. Sin encargos todavía; se prueba con un pedido marcado `es_encargo` por código. *(Punto A)*
3. **`encargo_service.py`**: alta/edición de encargo `retiro` con `fecha_programada`, anticipo y tope por día.
4. **`adelanto_service.py`**: cobrar seña (efectivo y otros métodos), devolver, retener, retener parcial. *(Puntos B y D)*
5. **Cobro del saldo**: `sena_aplicada` en `cobrar_pedido` / `crear_venta_central_desde_pedido`, rechazo en cola central, reversa en anulación de venta. *(Punto B)*
6. **Cierre de caja**: grupo `encargos_pendientes`, filtro de la lista de caja, informe de señas. *(Punto B)*
7. **Cocina**: botón "Enviar a producción", miniaturas y privacidad de montos. *(Punto C)*
8. **Fotos** (`encargo_foto_service.py` + extraer helper de `menu_image_service.py`).
9. **Tablero** (`encargos.html` / `encargos.js`) y tarjeta en el dashboard.
10. **Pantalla de root** para encender `encargos_activo` y los parámetros (hoy no existe).

---

## 7. Matriz de pruebas por punto delicado

| Punto | Prueba |
|---|---|
| A | encargo no consume al crear; consume al pasar a `preparando`; cancelar antes de producción no restaura nada; cancelar después restaura; reabrir no consume; no se consume dos veces |
| A | pedido normal: consumo al crear y restauración exactamente como antes |
| A | anular la venta de un encargo restaura el stock consumido |
| B | seña en efectivo → un `MovimientoCaja` ingreso; seña en tarjeta → ninguno; sin caja abierta → rechazo |
| B | cobro del saldo: `Venta.total` = saldo, `descuento_manual_monto` sin la seña, caja = seña + saldo |
| B | seña mayor o igual al total → rechazo; editar el total por debajo de las señas → rechazo |
| B | encargo futuro no aparece en la lista de caja ni bloquea el cierre; encargo vencido `listo` sí requiere confirmación |
| B | anular la venta devuelve los adelantos de `aplicado` a `vigente` |
| B | cola central rechaza encargos con señas vigentes |
| C | encargo `abierto` ausente en `/cocina/pedidos`; tras "Enviar a producción" aparece; la respuesta de cocina no contiene `adelantos`, `sena_total` ni `saldo` |
| C | encargo `delivery` rechazado en la Fase 1 |
| D | cancelar sin elegir opción → rechazo; devolver todo, retener todo, retener parcial (montos límite); devolución sin caja abierta → rechazo y nada cambia |
| D | señas por tarjeta devueltas sin egreso de caja; permiso insuficiente → 403 |
| D | el informe de cierre muestra recibidas, devueltas, retenidas y aplicadas por separado |

---

## 8. Decisiones que quedan fuera de la Fase 1

- **Delivery de encargos** (requiere sacar el atajo a cocina en `crear_pedido` y en `listar_pedidos_cocina`).
- **Factura por el total con dos pagos** en lugar de descuento por seña (a definir con contador).
- **Devolución del excedente** cuando el peso real de una torta deja el total por debajo de la seña (Fase 2).
- **Pago de seña desde la tienda online** (Fase 6 y fuera de alcance).
