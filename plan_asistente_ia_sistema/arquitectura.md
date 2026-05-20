# Arquitectura Propuesta

## Objetivo

Agregar un asistente IA interno para usuarios del backoffice, separado del bot de WhatsApp y separado del frontend de `tienda_online`.

El asistente debe responder preguntas operativas y comerciales usando tools internas. El modelo redacta y razona sobre resultados compactos; los cálculos y filtros viven en Python.

## Ubicación Sugerida

Crear una nueva capa backend:

```text
app/services/ia_backoffice/
  __init__.py
  prompts.py
  tools.py
  tool_handlers.py
  response_engine.py
  context.py
  audit.py
  limits.py
```

Crear rutas separadas:

```text
app/routes/asistente_ia.py
```

Crear templates separados:

```text
app/templates/asistente_ia/
  chat.html
  _chat_panel.html
  _message.html
```

Si el chat crece mucho en JS, dividirlo:

```text
app/static/js/asistente_ia/
  api.js
  chat_state.js
  chat_ui.js
```

## Reutilización Existente

Se debe reutilizar la infraestructura existente:

- `app/services/ia/gpt_service.py`: cliente OpenAI-compatible, DeepSeek, tools y configuración.
- `app/services/ia/settings_resolver.py`: lectura de configuración desde DB/env.
- `app/services/inteligencia/`: métricas agregadas de ventas, inventario, tienda y clientes.
- `gastos_corrientes/services/gasto_corriente_reporting.py`: resumen y panel de gastos.
- `cobranzas/services/cuenta_service.py`: resumen de cuentas por cobrar.
- Servicios de control de empleados para pagos, ausencias y vacaciones.

No conviene meter la lógica del asistente backoffice dentro del bot de WhatsApp actual, porque ese bot está orientado a clientes finales.

## Flujo De Consulta

1. Usuario escribe una pregunta en el chat interno.
2. Backend valida sesión, permisos y estado de IA.
3. Se envía al modelo un prompt corto con contexto mínimo.
4. El modelo decide si llama una tool.
5. Backend ejecuta la tool permitida.
6. La tool devuelve JSON compacto.
7. El modelo redacta una respuesta humana, breve y accionable.
8. Se registra auditoría de la consulta y de las tools usadas.

## Control De Tokens

Reglas obligatorias:

- Historial máximo: últimas 8 a 12 interacciones, resumidas si crece.
- Respuestas de tools con `top_n` limitado, por defecto 5.
- No enviar listas completas de ventas, clientes, productos o cuotas.
- No enviar HTML ni templates al modelo.
- No enviar objetos ORM serializados completos.
- Los montos, cantidades, variaciones y rankings se calculan en backend.
- La IA redacta el análisis, no calcula desde datos crudos.

## Modelos

Proveedor recomendado inicial:

```text
AI_PROVIDER=deepseek
AI_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Debe mantenerse compatibilidad OpenAI-compatible para cambiar modelo sin reescribir tools.

La configuración actual del sistema debe revisarse porque el código existente puede usar `https://api.deepseek.com/v1` y `deepseek-chat` como fallback. Para el asistente interno, la configuración objetivo es:

- `base_url`: `https://api.deepseek.com`
- modelo rápido/principal: `deepseek-v4-flash`
- modelo avanzado opcional: `deepseek-v4-pro`

Los nombres `deepseek-chat` y `deepseek-reasoner` solo deben mantenerse como compatibilidad temporal. No deben ser defaults nuevos porque están marcados para deprecación el 2026-07-24.

## Configuración DeepSeek OpenAI-Compatible

Ejemplo base para el cliente:

```python
from openai import OpenAI

client = OpenAI(
    api_key=deepseek_api_key,
    base_url="https://api.deepseek.com",
)

response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=messages,
    stream=False,
)
```

Para análisis más profundo se puede usar `deepseek-v4-pro` con parámetros de razonamiento solo cuando el usuario active una consulta compleja o root habilite un modo avanzado:

```python
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=messages,
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
```

Regla de costo: no usar `deepseek-v4-pro` por defecto.

## Respuesta Humana

El asistente debe sonar como ayudante de negocio, no como reporte seco.

Formato ideal:

- Resumen corto.
- Dato clave.
- Interpretación.
- Siguiente acción sugerida.

Ejemplo:

```text
Este mes venís mejor: las ventas subieron 18% contra el mes anterior. Lo que más empuja es celulares, pero el ticket promedio bajó un poco. Yo revisaría descuentos o combos para no vender más con menos margen.
```

## No Alcance Inicial

No incluir en el MVP:

- Crear ventas.
- Anular ventas.
- Registrar cobros.
- Cerrar caja.
- Borrar registros.
- Cambiar salarios.
- Modificar stock.
- Enviar WhatsApp automáticamente.

Estas acciones pueden planificarse después con confirmación explícita, doble validación y auditoría.
