# Diseño detallado — Fase 2: Venta por peso

Complementa `plan_pasteleria.md` (Fase 2). Todo lo que dice "existe" se verificó leyendo el código. Donde difiere del plan, manda este documento.

---

## 0. Hallazgos que cambian el plan

| # | Hallazgo | Consecuencia |
|---|---|---|
| 1 | La venta central no guarda el nombre del ítem: cada `DetalleVenta` apunta a un `Servicio` **compartido por producto del menú** (`GASTRO-<cliente>-<producto>`), y `_servicio_para_item` le pisa el nombre con el del último ítem cobrado. El ticket de venta, el historial y la factura electrónica leen `servicio.nombre`. | El plan decía que congelar "Torta · 1,250 kg" en el ítem bastaba para que factura y reportes mostraran el peso. **Es falso**: dos tortas con pesos distintos en la misma venta saldrían con el mismo nombre, y una venta vieja cambiaría de nombre. Para ítems por peso, el `Servicio` conserva el **nombre base** del producto. El peso queda en el pedido, el ticket de cocina/gastronomía y la comanda, no en la factura. |
| 2 | `DetalleVenta.cantidad` es entero y la factura toma la unidad de medida de `producto.unidad_venta` (solo productos de inventario; los platos son `Servicio` → siempre "unidad"). | Se mantiene el enfoque del plan: la pieza pesada es **1 unidad** con precio = peso × precio/kg. La factura dice "1 unidad de Torta de chocolate" por su importe. Facturar en kg con 3 decimales queda fuera de alcance. |
| 3 | Ya existe `app/utils/unidades_venta.py` con `UNIDAD_VENTA_UNIDAD` / `UNIDAD_VENTA_KG`. | Se reutilizan esas constantes; no se inventan otras. |
| 4 | `pos.js` tiene 599 líneas. | Antes de tocarlo se extrae el render de grupos de modificadores a `pos_modifier_groups.js`. El modal de peso vive en `pos_peso.js`. |
| 5 | `gastronomia/models.py` tiene 587 líneas. | Columnas nuevas por mixin en `gastronomia/peso_models.py`, como los encargos. |
| 6 | Root solo tiene pantalla para encargos (Fase 1, paso 10). | Se agrega el bloque "Venta por peso" al mismo panel, con los atajos de peso como parámetro. |

---

## 1. Modelo de datos

- `GastronomiaProducto.unidad_venta` VARCHAR(10) NOT NULL DEFAULT `'unidad'` (`unidad` / `kg`). Con `kg`, `precio` significa **precio por kilo** (también en los precios por canal).
- `GastronomiaPedidoItem.peso_kg` NUMERIC(10,3) NULL y `precio_por_kg` NUMERIC(15,2) NULL: congelan el peso y el precio/kg con el que se calculó la línea.
- `GastronomiaClienteConfig.peso_atajos_kg` VARCHAR(60) NOT NULL DEFAULT `'1,1.5,2'`.

## 2. Cálculo de la línea (servidor, fuente de verdad)

Para un producto `kg`:
- `peso_kg` obligatorio, > 0, ≤ 50 kg, hasta 3 decimales. `cantidad` debe ser 1 (se rechaza > 1: dos tortas = dos líneas).
- **Sin promociones** (ni por cantidad ni por porcentaje): `promotion = None`.
- `subtotal = redondeo(peso × precio_kg) + modificadores` (los extras, como una decoración, se cobran por pieza). `precio_unitario = subtotal` (cantidad 1), `precio_original = subtotal`.
- `nombre_producto = "<nombre> · 1,250 kg"`.

Lo calcula `peso_service.linea_por_peso(...)`; `pedido_service` solo delega.

## 3. El flag

`venta_por_peso_activa` (solo root) habilita **marcar** un producto como "por kilo" en el menú y ver los atajos. El cálculo depende de `producto.unidad_venta`, no del flag: si root apaga el flag con productos por kilo cargados, esos productos siguen cobrándose por peso (no se reinterpreta un precio por kg como precio por unidad sin que alguien lo decida). Sin productos `kg`, nada cambia.

## 4. Encargo por peso

- Al tomar el encargo se carga el **peso pedido**; el total es estimado.
- "Ajustar peso" en el tablero recalcula la línea con el **peso real** y el `precio_por_kg` congelado, y el total del encargo. Solo antes del cobro y no en cancelados.
- Si el nuevo total queda **por debajo de la seña vigente**, el excedente se devuelve en el momento: egreso de caja si fue en efectivo (exige caja abierta), solo registro si fue por otro medio. Se reparte desde el adelanto más reciente y se registra en `monto_devuelto` del adelanto, que sigue `vigente`.
- Por eso la seña vigente pasa a calcularse como `monto − monto_devuelto` de los adelantos vigentes, en todos los lugares que la usan (cobro, cancelación, informe de cierre, serializador).
- **Límite conocido:** el informe de señas del cierre lista las devoluciones de cancelaciones; la devolución por ajuste de peso aparece como egreso en caja (el arqueo cuadra) pero no en la línea "Devueltas" del informe.

## 5. Dónde se muestra "/ kg"

POS (botón y modal), menú, TV y API de la tienda (`unidad_venta` en el producto). **Tienda online:** un producto por kilo se muestra con "/ kg" pero no se puede agregar al carrito (el pedido web no carga peso); el servidor rechaza un pedido web con productos por kilo. El encargo web con peso queda para la Fase 6.

## 6. Stock

Sin cambios: un producto por kilo cuenta **piezas** (`control_stock_venta`) y la receta descuenta una pieza estándar sin importar el peso (decisión 10 del plan, limitación aceptada).

## 7. Pruebas

`test_pasteleria_venta_por_peso.py`: línea de 1,250 kg con precio correcto y venta/caja consistentes; peso 0, negativo, > 50 o cantidad > 1 rechazados; sin promociones; dos tortas de pesos distintos en una venta no se pisan el nombre del servicio; encargo: ajustar peso recalcula y devuelve el excedente de la seña; producto `unidad` sin cambios; con el flag apagado no se puede marcar un producto por kilo.
