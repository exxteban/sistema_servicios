# Diseño detallado — Fase 3: Producción diaria, porciones y merma

Complementa `plan_pasteleria.md` (Fase 3). Todo lo que dice "existe" se verificó leyendo el código. Donde difiere del plan, manda este documento.

---

## 0. Hallazgos que cambian el plan

| # | Hallazgo | Consecuencia |
|---|---|---|
| 1 | `stock_disponible` es el único stock del producto terminado: lo descuenta `consumir_stock_item` (con bloqueo de fila) y lo restaura `restaurar_stock_items`, siempre que `control_stock_venta` esté encendido. | La producción **suma** a `stock_disponible` (no lo pisa, como decía el plan): pisarlo borraría el sobrante de ayer que sigue a la venta. No se crea un segundo stock. |
| 2 | Lo vendido ya queda registrado: cada venta de un producto con control deja un `GastronomiaPedidoItemConsumo` `producto_menu` (y se marca `restaurado` si se cancela). | "Vendido del día" se calcula desde esa tabla (consumos no restaurados con fecha local del día). No se duplica el registro de ventas. Un encargo cuenta como vendido el día que pasa a producción (decisión 3). |
| 3 | `control_stock_venta` es un switch por producto que el local maneja desde el menú. | Producción, merma, cierre y "abrir torta" solo operan sobre productos **con** control de stock. Un producto sin control se rechaza con un mensaje que indica dónde encenderlo. La fase lee el switch, no lo cambia. |
| 4 | El costo de receta por unidad ya se calcula en `inteligencia_margen._costos_unitarios_receta`. | Se expone como función pública (`costos_unitarios_receta`) y se reutiliza para valorizar la merma. El costo se **congela** en cada registro para que el reporte histórico no cambie si después cambia la receta o el precio del insumo. |

## 1. Modelo de datos (`gastronomia/produccion_models.py`)

- `gastronomia_produccion_registros`: `id_registro`, `cliente_id`, `producto_id`, `fecha` (DATE, día local del negocio), `tipo`, `cantidad` (entero > 0), `motivo` (NULL salvo merma), `stock_anterior`, `stock_nuevo`, `costo_unitario` (NUMERIC NULL, congelado), `referencia` (agrupa las dos filas de una apertura), `usuario_id`, `fecha_registro` (UTC).
- `tipo`: `produccion` (+), `merma` (−), `ajuste` (+, el conteo del cierre dio más que el teórico), `apertura` (− 1 entero), `porciones` (+ N porciones).
- `gastronomia_producto_porciones`: `id_relacion`, `cliente_id`, `producto_entero_id` (único por cliente), `producto_porcion_id`, `porciones` (1–100), `activo`.
- Flag `produccion_diaria_activa` (ya existe desde la Fase 0).

## 2. Operaciones (servidor, `produccion_service.py` / `porciones_service.py`)

Todas bloquean la fila del producto (`_bloquear_producto_menu`) y dejan un registro con stock anterior y nuevo.

- **Producción por tanda:** `stock += cantidad`.
- **Merma durante el día:** `stock -= cantidad`, con motivo (`vencido`, `golpeado`, `regalado`, `consumo_propio`, `otro`). Se permite dejar el stock en negativo solo si ya estaba así (igual que una venta sin stock); no se puede declarar más merma que el stock positivo.
- **Cierre del día:** por producto, el operador cuenta lo que **quedó** y elige qué se hace con eso:
  - si el conteo es menor que el teórico, la diferencia es merma con motivo `faltante` (no explicada);
  - si es mayor, la diferencia es un `ajuste` positivo (una venta no cargada, por ejemplo);
  - lo que quedó **sigue a la venta** o se **descarta** como merma con el motivo elegido (vencido, regalado, consumo propio).
- **Abrir torta:** con relación activa y stock del entero ≥ 1: entero −1, porción +N, dos registros con la misma `referencia`. Ambos productos deben tener control de stock. Bloqueo en orden de id para evitar abrazos mortales.
- **Relación entero → porción:** un entero tiene una sola relación; el entero no puede ser porción de otro ni la porción ser entero (sin ciclos). Varios enteros pueden compartir producto porción (torta grande y chica → misma porción).

## 3. Resumen del día y reporte de merma

- **Día:** por producto con control: stock actual, producido, vendido, merma y ajuste del día.
- **Reporte:** merma por producto y por motivo en un rango de fechas, en unidades y valorizada (`cantidad × costo_unitario` congelado). Productos sin receta valen 0 y se marcan "sin costo".
- Solo producto terminado: la merma de insumos (materia prima) sigue en el ajuste de stock de insumos y no se mezcla.

## 4. Flag y permisos

- Con `produccion_diaria_activa` apagado los endpoints responden 404, la pantalla redirige y la tarjeta del dashboard no aparece. Sin flag nada cambia: ninguna ruta existente se modifica.
- Operar (producción, merma, cierre, abrir torta): permiso POS o Cocina. Relaciones de porciones: permiso Menú. Reporte: Reportes o Menú.
- Apagar el flag no toca stock ni registros; solo oculta la pantalla.

## 5. Pruebas (`test_pasteleria_produccion.py`)

Registrar tanda, vender, cerrar y verificar merma y vendido; cierre con conteo mayor (ajuste) y con descarte; abrir torta con y sin stock suficiente; dos aperturas seguidas con stock 1 (la segunda se rechaza); relación inválida (mismo producto, ciclo, sin control); costo congelado en el reporte; producto sin control rechazado; otro cliente no ve ni opera productos ajenos; flag apagado → 404 y sin tarjeta; root enciende el flag.
