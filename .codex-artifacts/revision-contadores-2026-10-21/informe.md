# Revisión del módulo Contadores — 21/10/2026

Revisión de `080ea71`, con árbol de trabajo inicialmente limpio. Se inspeccionó la incorporación desde `98c12a6` y se comparó con `C:/Users/csarl/Documents/proyectos/saas/sistema_con_whats/sistema_silvio_cel`.

## Evaluación

La separación del área contable en rutas y servicios propios está bien planteada. Las pantallas, detalles y exportaciones reutilizan los cálculos del resumen. El rol Contador/a tiene pruebas de acceso independiente de caja y POS. Los nuevos campos de las tablas existentes son opcionales o tienen valores por defecto.

No corresponde dar el módulo por libre de errores: hay cuatro defectos reproducidos, detallados abajo. Los tres primeros están en código idéntico al del padre; el cuarto está en la adaptación del flujo vendedor → caja.

## Hallazgos

### 1. [P1] Quitar el número de una venta deja su nota de crédito restando IVA

- Ubicación: `app/routes/contador/talonarios.py:105-111`, en combinación con `app/services/notas_credito_papel.py:87-88`.
- Reproducción: venta de Gs. 110.000 con IVA de Gs. 10.000 y devolución con NC de Gs. 55.000/IVA Gs. 5.000. El débito inicial es Gs. 5.000. Enviar el formulario de corrección con número vacío devuelve HTTP 302 y guarda `numero_factura = None`.
- Resultado: la venta sale del débito, pero la NC permanece; el débito pasa a −Gs. 5.000. El formulario de NC también queda oculto porque exige que la venta tenga número.
- Impacto: resumen e informes contables inconsistentes. En la reproducción, esta edición no agregó movimientos de caja.
- Corrección recomendada: impedir quitar la factura mientras haya NC asociadas y ofrecer un flujo explícito de corrección que conserve la relación documental. No eliminar comprobantes históricos silenciosamente.

### 2. [P2] Un talonario nuevo puede aparecer agotado por facturas del anterior

- Ubicación: `app/services/talonario_facturas.py:96-111`.
- Reproducción: timbrado A con rango 1–100 y última factura 100; después, timbrado B con el mismo prefijo y rango 1–100, con vigencia posterior y ninguna venta.
- Resultado: `siguiente(B)` devuelve `None`, aunque debería ofrecer 1. La consulta mezcla todas las ventas con el prefijo, sin discriminar timbrado ni vigencia.
- Impacto: el POS anuncia que se terminó un talonario nuevo o sugiere una numeración adelantada. No bloquea por sí mismo el cobro.
- Corrección recomendada: resolver qué ventas pertenecen al talonario por timbrado y, para datos históricos sin timbrado, por vigencia y rango.

### 3. [P2] Facturas de distintos timbrados se marcan como duplicadas

- Ubicación: `app/services/resumen_contadora_ventas.py:77-83`.
- Reproducción: dos ventas del mismo mes con `001-001-0000001`, una antes y otra después de cambiar el timbrado, cada una con su timbrado válido.
- Resultado: el resumen registra un duplicado porque agrupa únicamente por número, aunque las filas ya contienen el timbrado.
- Impacto: pendientes falsos en el cierre y en los informes del mes.
- Corrección recomendada: identificar comprobantes por timbrado y número normalizado, con una política explícita para los históricos sin timbrado.

### 4. [P2] Vaciar el número en caja recupera silenciosamente el del vendedor

- Ubicación: `app/services/pos_numero_factura.py:59-61`.
- Reproducción: `numero_factura_del_pedido({'numero_factura': ''}, {'numero_factura': '123'})` devuelve `('123', None)`.
- Resultado: se interpreta un campo vaciado explícitamente igual que un campo no enviado. El cajero puede creer que quitó el número, pero el cobro conserva el del pendiente.
- Impacto: una venta puede terminar vinculada a un número que el cajero descartó y entrar incorrectamente al resumen de facturas.
- Corrección recomendada: distinguir ausencia de la clave de un valor vacío explícito; usar el dato del pendiente solamente cuando no se envió la clave.

## Verificaciones

- Suite general: **1.683 aprobadas, 0 fallidas**, en 731,61 segundos. Incluye 139 pruebas en archivos relacionados con caja y 91 del área contable (conteo por nombre de módulo en el XML). Comando: `.venv/Scripts/python.exe -m pytest -q -n 8 --junitxml=.pytest_cache/revision_contadores_suite.xml`, con `DATABASE_URL` fijado explícitamente a la base de pruebas del repositorio.
- Única advertencia: Pillow advierte sobre una imagen demasiado grande dentro de la prueba que verifica precisamente el rechazo de imágenes con exceso de píxeles; esa prueba pasó.
- Cuatro reproducciones adicionales fallaron en las aserciones esperadas, confirmando los cuatro hallazgos.
- Prueba de migración: **1 aprobada**. En una base SQLite aislada se quitaron las columnas nuevas de ventas y gastos, se ejecutó dos veces la inicialización, y se verificó que se preservaron la venta de Gs. 110.000 y el movimiento de caja de Gs. 12.345.
- Las pruebas usan datos de prueba, IA desactivada y WhatsApp desactivado/en modo simulación.
- Se instalaron en `.venv` los complementos declarados por el proyecto que faltaban: `pytest-xdist` y `pytest-timeout`.

## Alcance y límites

Se revisaron rutas, modelos, migración, permisos, integración con POS/cola de caja, devoluciones, compras, gastos, resumen mensual y exportaciones. Se comparó el núcleo contable con el padre: los servicios principales y las rutas de operaciones son idénticos; existen adaptaciones de moneda, permisos y facturación electrónica.

No se modificó código productivo ni se operó sobre datos reales. No se comprobó una migración sobre MySQL de producción ni se hizo una inspección visual completa en navegador. Las pruebas automatizadas no garantizan ausencia absoluta de regresiones.

## Evidencia guardada

En esta misma carpeta están `casos.py` (cuatro reproducciones que fallan con el código actual y una comprobación de migración que pasa), los tres logs de esas comprobaciones y el log/XML de la suite general. Estos casos se mantienen fuera de la suite habitual porque son evidencia de revisión, no correcciones aplicadas.

Conclusión: no se detectaron regresiones de caja en las comprobaciones ejecutadas. La integración está bien encaminada, pero el módulo contable necesita corregir los hallazgos antes de considerarlo cerrado.
