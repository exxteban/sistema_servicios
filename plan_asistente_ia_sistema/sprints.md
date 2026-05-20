# Plan Por Sprints

## Sprint 0 - Diseño Base Y Seguridad

Objetivo: dejar preparada la base sin exponer datos ni gastar tokens de más.

Entregables:

- Crear módulo `app/services/ia_backoffice/`.
- Crear prompt separado del bot de WhatsApp.
- Crear configuración separada `ia_backoffice_*`.
- Definir DeepSeek como proveedor principal del asistente interno.
- Usar `https://api.deepseek.com` como base URL por defecto.
- Usar `deepseek-v4-flash` como modelo por defecto.
- Dejar `deepseek-v4-pro` como modelo avanzado opcional controlado por root.
- Evitar `deepseek-chat` y `deepseek-reasoner` como defaults nuevos.
- Agregar validación root-only para habilitar/deshabilitar.
- Agregar permisos `usar_asistente_ia` y `gestionar_asistente_ia`.
- Diseñar tabla o modelo de auditoría.
- Definir límites de tokens por request, día y mes.
- Tests de permisos root y usuario no root.

Criterio de aceptación:

- Solo root puede cambiar el estado global.
- Un usuario sin permiso no puede usar el chat.
- El asistente no ejecuta ninguna tool todavía.

## Sprint 1 - Chat Interno Solo Lectura

Objetivo: tener el primer chat funcional en backoffice.

Entregables:

- Ruta `GET /asistente-ia`.
- Endpoint `POST /asistente-ia/api/chat`.
- UI básica de chat dentro del layout actual.
- Engine IA reutilizando cliente OpenAI-compatible.
- Historial corto por sesión.
- Respuesta fallback si IA está apagada.
- Auditoría básica de pregunta/respuesta.

Criterio de aceptación:

- Root habilita la IA.
- Usuario con permiso puede preguntar.
- Usuario sin permiso recibe bloqueo.
- El chat responde sin tools, usando contexto mínimo.

## Sprint 2 - Tools De Ventas

Objetivo: que la IA responda preguntas reales de ventas.

Entregables:

- `ventas_resumen_periodo`.
- `ventas_top_productos`.
- `ventas_por_categoria`.
- `ventas_tendencia`.
- `ventas_por_vendedor`.
- Tests de cada handler.
- Respuestas compactas con comparaciones.

Criterio de aceptación:

- Preguntas sobre ventas no mandan ventas crudas al modelo.
- Las tools devuelven máximo top 5 por defecto.
- La IA explica variaciones y sugiere una acción.

## Sprint 3 - Cobranzas E Inventario

Objetivo: cubrir dinero pendiente y stock.

Entregables:

- `cobranzas_resumen`.
- `cobranzas_clientes_morosos`.
- `cobranzas_proximos_vencimientos`.
- `inventario_resumen`.
- `inventario_productos_reponer`.
- `inventario_productos_inmovilizados`.
- Validación de permisos por módulo.

Criterio de aceptación:

- La IA puede responder quién debe, cuánto falta cobrar y qué productos revisar.
- No expone datos de clientes si el usuario no tiene permiso.
- Los rankings se limitan por `top_n`.

## Sprint 4 - Gastos Corrientes Y Caja

Objetivo: explicar salida de dinero y situación diaria.

Entregables:

- `gastos_resumen_periodo`.
- `gastos_por_categoria`.
- `gastos_vencidos`.
- `caja_resumen_periodo`.
- `caja_estado_actual`.
- `caja_anulaciones_periodo`.

Criterio de aceptación:

- La IA puede responder cuánto falta pagar y qué está vencido.
- La IA puede resumir caja sin cerrar, abrir ni modificar nada.
- Cualquier consulta de caja queda auditada.

## Sprint 5 - Clientes Y CRM

Objetivo: convertir inteligencia en acciones comerciales.

Entregables:

- `clientes_resumen_inteligencia`.
- `clientes_top_valor`.
- `clientes_para_contactar`.
- `crm_sugerir_mensaje`.
- Borradores de mensajes sin envío automático.

Criterio de aceptación:

- La IA sugiere clientes a contactar con motivo.
- Puede redactar un mensaje, pero no enviarlo.
- Reutiliza plantillas CRM cuando existan.

## Sprint 6 - Empleados Y Reparaciones

Objetivo: ampliar el asistente a operación interna.

Entregables:

- `empleados_resumen`.
- `empleados_ausencias_periodo`.
- `empleados_pagos_periodo`.
- `empleados_aguinaldo_resumen`.
- `reparaciones_resumen`.
- `reparaciones_atrasadas`.
- `reparaciones_por_tecnico`.
- `reparaciones_fallas_frecuentes`.

Criterio de aceptación:

- La IA puede explicar ausencias, pagos y cargas operativas.
- No modifica salarios, pagos ni reparaciones.

## Sprint 7 - Tienda Online Analytics Y Pedidos

Objetivo: sumar análisis del catálogo web y pedidos.

Entregables:

- `tienda_resumen_analytics`.
- `tienda_productos_mucha_vista_poca_consulta`.
- `tienda_ofertas_rendimiento`.
- `pedidos_resumen`.
- `pedidos_pagos_pendientes`.

Criterio de aceptación:

- La IA identifica productos vistos que no convierten.
- La IA resume pedidos sin cambiar estados.
- No se toca el frontend `tienda_online` salvo APIs ya autorizadas.

## Sprint 8 - Optimización De Costos Y Calidad

Objetivo: bajar consumo y mejorar utilidad.

Entregables:

- Cache de resultados de tools frecuentes.
- Resumen automático de historial.
- Métricas de tokens por usuario.
- Dashboard root de consumo IA.
- Evaluaciones con preguntas frecuentes.
- Ajuste de prompts para respuestas más humanas.

Criterio de aceptación:

- Root puede ver consumo diario/mensual.
- El sistema bloquea uso al superar presupuesto.
- Las respuestas mantienen tono humano y útil.

## Sprint 9 - Acciones Asistidas Con Confirmación

Objetivo: planificar futuras acciones, sin meter riesgo en el MVP.

Posibles acciones:

- Preparar borrador de campaña.
- Preparar lista de clientes para contactar.
- Crear tarea o recordatorio interno.
- Generar reporte descargable.

No incluir todavía:

- Anular ventas.
- Registrar cobros.
- Cerrar caja.
- Cambiar stock.
- Cambiar salario.
- Enviar WhatsApp automáticamente.

Criterio de aceptación:

- Toda acción requiere confirmación explícita.
- Toda acción deja auditoría.
- Root puede desactivar acciones asistidas.

Avance inicial implementado:

- Switch root `ia_backoffice_assisted_actions_enabled`, apagado por defecto.
- Endpoints de preparacion y confirmacion de acciones asistidas.
- Deteccion conservadora de pedidos explicitos desde el chat.
- Tarjeta de confirmacion en UI del chat para acciones preparadas.
- Preparacion auditada para borrador de campana, lista de clientes, recordatorio interno y reporte descargable.
- Confirmacion auditada sin ejecucion automatica de cambios de negocio.
