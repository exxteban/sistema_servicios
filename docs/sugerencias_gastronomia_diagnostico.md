# Diagnóstico de sugerencias de gastronomía — 30/10/2026

Complementa [el plan](../plan_sugerencias_gastronomia.md), sin cambiar umbrales
ni activar módulos. `consulta_pos.py` comparte la lectura entre el GET y el
diagnóstico; no calcula asociaciones durante una consulta del POS.

El informe separa tres medidas:

- Cobertura teórica de asociaciones, previa a los filtros finales.
- Carritos simulados de un producto: los más pedidos disponibles hoy, con
  asociaciones publicadas, stock, precio, canal, reglas, fatiga y configuración
  actuales. Muestra mediana, p95, mínimo/máximo y errores/timeouts por canal.
  Es tiempo del servicio (configuración y candidatos), **sin autenticación,
  HTTP, red ni navegador**. No reconstruye escaneos reales.
- Exposición registrada en pedidos POS cobrados de los últimos 12 meses,
  deduplicada por pedido, sin encargos ni ventas anuladas. Incluye períodos
  desactivados y usuarios sin franja: no equivale a calidad ni conversión.

```powershell
python scripts/diagnostico_sugerencias_gastronomia.py --cliente-id N --muestra-pos 20 --repeticiones-pos 3 --canal todos
```

`--canal` admite `normal`, `pedidosya`, `monchis` y `todos`. La muestra tiene
un máximo de 100 productos y 5 repeticiones por producto/canal. Sin historial
evaluable, cobertura y tiempos son `null`, no un cero que parezca medido.

`--sqlite RUTA` permite revisar un archivo existente. El CLI verifica las
tablas y habilita `query_only` para SQLite; no crea bases ni tablas. Si falta
el esquema, no hay instalación activa o falla la conexión, informa el estado
y termina con código distinto de cero, sin mostrar detalles SQL/credenciales.
No ejecuta `create_app`, migraciones, recálculos ni escrituras estadísticas.

En la prueba local, la base original carecía de las ocho tablas del sugeridor.
Se prepararon, activaron y calcularon **solo en una copia temporal**, luego
eliminada. El hash de la base original fue idéntico antes y después.

Se encontraron 10 pedidos válidos, 0% con varios productos y 2 orígenes
evaluables. En 18 consultas en los tres canales: medianas 3,18–3,79 ms y
máximo 12,24 ms. Sin asociaciones ni sugerencias; corresponde cargar reglas
antes de habilitar el POS. Estos tiempos no prueban rendimiento con catálogos
grandes y esta muestra no sustituye revisar 2 o 3 instalaciones autorizadas.

Validación: 61 pruebas del sugeridor aprobadas, incluidas 12 nuevas para
filtros, canales, fatiga, límites, aislamiento, exposición registrada, tope de
tiempo y CLI sin escrituras (incluido hash del archivo antes y después).
En navegador se verificó el contrato del GET y la exclusión de productos ya
presentes en el carrito, con un servidor temporal y datos ficticios.
La [validación en MariaDB real](sugerencias_gastronomia_mysql.md) ya pasó.
La medición HTTP desplegada y los otros historiales siguen pendientes.
