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

## Diagnóstico ejecutado en el servidor

Salida compartida por el usuario el 30/10/2026, cliente interno 2, corte
`2026-10-30T18:39:42.401391` UTC:

- 303 pedidos válidos, **0,99%** de canastas múltiples y 1,01 platos por pedido.
- Ningún par pasa el soporte mínimo 4; los pares observados aparecen como
  máximo 2 veces. La variante exploratoria (soporte 3) tampoco aporta pares,
  ni a nivel producto ni categoría. Se mantienen los umbrales actuales.
- Muestra: 20 orígenes más pedidos, 3 repeticiones por canal; **180 consultas
  con estado `ok`, sin errores ni timeouts**.

| Canal | Mediana (ms) | p95 (ms) | Máximo (ms) |
|---|---:|---:|---:|
| Normal | 22,683 | 30,363 | 40,756 |
| PedidosYa | 29,295 | 38,593 | 41,892 |
| Monchis | 24,516 | 32,658 | 41,081 |

El máximo de 41,892 ms está holgadamente por debajo del presupuesto de 300 ms
del servicio. Esta muestra no justifica agregar caché ni bajar los umbrales.
Son tiempos de configuración y candidatos, sin HTTP, autenticación o red.

La cobertura simulada fue 0% porque **Cafe (10) no está entre los 20 orígenes
muestreados**. Esto no contradice la prueba positiva Cafe → Medialuna del POS.
La cobertura registrada informa 0 exposiciones entre 56 pedidos POS cobrados:
incluye períodos anteriores a la activación y no mide todavía la aceptación
de la regla. Se necesitan nuevos pedidos cobrados con exposición para evaluarla.

Decisión para esta instalación: arrancar con reglas del negocio y observar
aceptación; el historial disponible todavía no sostiene asociaciones automáticas.

No se informa una latencia HTTP precisa: el navegador de automatización no
expone Resource Timing y sus tiempos de control incluyen trabajo adicional.
No corresponde compararlos con el presupuesto de 300 ms del servidor.
Siguen pendientes esa medición instrumentada, un catálogo grande y completar
el diagnóstico de 2 o 3 historiales autorizados. Esta demo cubre la verificación
funcional desplegada, no todas esas validaciones.
