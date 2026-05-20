# Catálogo Inicial De Tools

Las tools deben devolver JSON pequeño, estable y pensado para ser explicado por la IA.

## Convenciones

Cada tool debe aceptar:

```json
{
  "periodo": "mes|hoy|ayer|7d|30d|trimestre|anio|custom",
  "desde": "YYYY-MM-DD",
  "hasta": "YYYY-MM-DD",
  "top_n": 5
}
```

Reglas:

- `top_n` máximo 20.
- Fechas custom validadas en backend.
- Periodo por defecto: `mes`.
- Montos como números, no como texto formateado.
- Labels humanos opcionales, pero no reemplazan valores numéricos.

## Ventas

### `ventas_resumen_periodo`

Responde preguntas como:

- "Cómo van mis ventas este mes?"
- "Cuánto vendí hoy?"
- "Comparame contra el mes pasado."

Devuelve:

```json
{
  "periodo_label": "Este mes",
  "total_ventas": 15400000,
  "cantidad_ventas": 219,
  "ticket_promedio": 70319,
  "variacion_vs_anterior_pct": 18.4
}
```

### `ventas_top_productos`

Devuelve productos más vendidos por unidades e ingreso.

### `ventas_por_categoria`

Devuelve categorías líderes, participación y variación.

### `ventas_por_vendedor`

Devuelve ventas agrupadas por vendedor si el usuario tiene permiso.

### `ventas_tendencia`

Devuelve serie resumida por día o semana.

## Cobranzas

### `cobranzas_resumen`

Devuelve:

```json
{
  "saldo_total": 12500000,
  "cuentas_abiertas": 42,
  "cuentas_vencidas": 9,
  "cobrado_periodo": 3200000
}
```

### `cobranzas_clientes_morosos`

Devuelve top clientes por saldo vencido.

### `cobranzas_proximos_vencimientos`

Devuelve cuotas o cuentas próximas a vencer.

### `cobranzas_cobros_periodo`

Devuelve total cobrado por periodo, método y usuario.

## Inventario Y Productos

### `inventario_resumen`

Usa servicios existentes de inteligencia.

Devuelve:

- productos con riesgo de quiebre
- stock inmovilizado
- rotación rápida
- productos con vistas de tienda pero poca venta

### `inventario_productos_reponer`

Devuelve productos recomendados para reposición.

### `inventario_productos_inmovilizados`

Devuelve productos sin salida en el periodo configurado.

### `productos_buscar_interno`

Busca productos del backoffice para responder preguntas internas.

## Gastos Corrientes

### `gastos_resumen_periodo`

Basado en `construir_panel_gastos_corrientes`.

Devuelve:

```json
{
  "periodo": "2026-04",
  "total_estimado": 5000000,
  "total_pagado": 3500000,
  "total_pendiente": 1500000,
  "vencidos": 3,
  "alertas_activas": 4
}
```

### `gastos_por_categoria`

Devuelve gastos agrupados por categoría.

### `gastos_vencidos`

Devuelve lista compacta de gastos vencidos.

## Clientes Y CRM

### `clientes_resumen_inteligencia`

Usa el centro de inteligencia comercial.

Devuelve:

- clientes para activar
- clientes valiosos dormidos
- clientes frecuentes en pausa
- segmentos principales

### `clientes_top_valor`

Devuelve clientes por facturación histórica o reciente.

### `clientes_para_contactar`

Devuelve una lista corta con motivo sugerido.

### `crm_sugerir_mensaje`

Genera borrador de mensaje, no lo envía automáticamente.

## Caja

### `caja_resumen_periodo`

Devuelve ingresos, egresos, efectivo y métodos de pago.

### `caja_anulaciones_periodo`

Devuelve anulaciones y reversas relevantes.

### `caja_estado_actual`

Devuelve caja abierta/cerrada, usuario y resumen parcial.

## Empleados

### `empleados_resumen`

Devuelve cantidad de empleados activos, pagos del periodo, extras y descuentos.

### `empleados_ausencias_periodo`

Devuelve ausencias por empleado y tipo.

### `empleados_pagos_periodo`

Devuelve pagos realizados y pendientes.

### `empleados_aguinaldo_resumen`

Devuelve proyección o cálculo agregado de aguinaldo.

## Reparaciones

### `reparaciones_resumen`

Devuelve trabajos por estado.

### `reparaciones_atrasadas`

Devuelve reparaciones con fecha estimada vencida.

### `reparaciones_por_tecnico`

Devuelve carga de trabajo por técnico.

### `reparaciones_fallas_frecuentes`

Devuelve fallas más repetidas.

## Tienda Online Analytics

### `tienda_resumen_analytics`

Devuelve visitas, consultas, conversión y productos más vistos.

### `tienda_productos_mucha_vista_poca_consulta`

Detecta productos que atraen interés pero no convierten.

### `tienda_ofertas_rendimiento`

Evalúa promociones activas.

## Pedidos, Compras Y Proveedores

### `pedidos_resumen`

Devuelve pedidos pendientes, entregados y pagos incompletos.

### `compras_resumen_periodo`

Devuelve total comprado por periodo.

### `proveedores_top`

Devuelve proveedores por volumen de compra y frecuencia.
