# Verificación de la demo desplegada — 30/10/2026

Instalación autorizada: [demogastronomia.pysystems.online](https://demogastronomia.pysystems.online/).
Después de actualizar el código y reiniciar el servicio, el menú mostró
«Sugerencias» y el GET `/api/gastronomia/sugerencias` respondió correctamente.
Antes de la actualización devolvía 404.

Se solicitó un cálculo desde la pantalla del dueño: **303 pedidos válidos y
0 asociaciones** con los umbrales actuales. Este dato no revela por sí solo
el porcentaje de canastas múltiples ni justifica cambiar los umbrales.
El POS cargó un catálogo de **61 productos**.

Con autorización explícita del usuario, se creó y dejó activa la regla
**Cafe (10) → Medialuna (15)** y se guardaron ambos interruptores encendidos:
«Activar sugeridor» y «Mostrar sugerencias en el POS», máximo 3.

Comprobaciones realizadas en la sesión autenticada:

- Vista previa: «Medialuna · Regla del negocio».
- GET con Cafe: complemento 15, origen 10 y fuente `regla` en canal normal,
  PedidosYa y Monchis. Con ambos productos en el carrito, respuesta vacía.
- POS: «+ Medialuna Gs. 8.000» al agregar Cafe; al tocar abre el configurador
  habitual y agrega el renglón por Gs. 8.000. La sugerencia desaparece.
- «⋯» abre con Enter y muestra «Regla del negocio».
- La franja visible conserva el foco en `product-search`.
- A 390 px, el ancho del documento fue 390 px, sin desbordamiento horizontal.
- El borrador se descartó. No se guardaron pedidos ni se enviaron a cocina
  ni se cobraron; la prueba no generó ventas ni movimientos de stock.

Estado final: **regla y sugeridor activos**, según la decisión del usuario.

No se informa una latencia HTTP precisa: el navegador de automatización no
expone Resource Timing y sus tiempos de control incluyen trabajo adicional.
No corresponde compararlos con el presupuesto de 300 ms del servidor.
Siguen pendientes esa medición instrumentada, un catálogo grande y completar
el diagnóstico de 2 o 3 historiales autorizados. Esta demo cubre la verificación
funcional desplegada, no todas esas validaciones.
