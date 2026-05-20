# Plan Asistente IA del Sistema

Este directorio concentra el plan de trabajo para agregar un asistente IA interno al backoffice del sistema.

El objetivo no es crear una IA que lea toda la base de datos, sino un asistente de negocio que use herramientas controladas para consultar datos agregados, responder con criterio y mantener bajo el consumo de tokens.

## Documentos

- `arquitectura.md`: diseño técnico propuesto y ubicación de módulos.
- `seguridad_root.md`: reglas de permisos, habilitación y auditoría.
- `tools_catalogo.md`: catálogo inicial de tools por área del sistema.
- `sprints.md`: plan de implementación por sprints.

## Principios

1. La IA no ejecuta SQL libre.
2. La IA no decide el `cliente_id` ni el alcance de datos.
3. Las tools devuelven datos compactos y agregados por defecto.
4. El detalle se consulta solo bajo pedido explícito.
5. La habilitación global queda reservada al usuario root.
6. Las acciones destructivas quedan fuera del MVP.
7. Cada archivo nuevo debe mantenerse bajo 600 líneas.
8. DeepSeek es el proveedor principal del asistente interno.

## Proveedor IA Principal

Configuración base deseada:

```text
AI_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
```

`deepseek-v4-flash` debe ser el modelo por defecto por costo/velocidad. `deepseek-v4-pro` queda reservado para consultas más complejas o modo análisis avanzado.

Los modelos `deepseek-chat` y `deepseek-reasoner` quedan como compatibilidad temporal y no deben usarse como default nuevo.

## Módulos Priorizados

1. Ventas.
2. Cobranzas.
3. Inventario y productos.
4. Gastos corrientes.
5. Clientes y CRM.
6. Caja.
7. Empleados.
8. Reparaciones.
9. Tienda online analytics.
10. Pedidos, compras y proveedores.
