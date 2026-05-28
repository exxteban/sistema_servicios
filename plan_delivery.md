# Plan Modulo Delivery Para Gastronomia

## Objetivo

Crear un modulo de delivery orientado a gastronomia, integrado al POS, que permita tomar pedidos, imprimir tickets con datos de entrega y ofrecer al cliente una vista publica para consultar el estado del pedido.

El modulo debe reutilizar la idea funcional del seguimiento de reparaciones, donde el cliente puede consultar el estado de su equipo, pero adaptada a pedidos gastronomicos. No debe acoplarse directamente al modelo de reparaciones si eso mezcla responsabilidades.

## Contexto De Instalacion

El sistema no se debe pensar como multi-tenant real para este modulo.

El escenario esperado es:

- Una instalacion por cliente.
- Como maximo algunos clientes por servidor.
- Bases de datos separadas.
- Servicios separados.

Por lo tanto:

- No hace falta sobredisenar el modulo alrededor de separacion multi-tenant compleja.
- Si el sistema actual ya usa `cliente_id` en ciertas tablas, se puede respetar donde sea necesario por compatibilidad interna.
- No se debe hacer que el modulo dependa semanticamente de un tenant global.
- La separacion fuerte entre clientes viene dada por la base de datos y los servicios separados.

## Alcance Inicial

El modulo debe cubrir:

- Nueva seccion `Delivery` dentro del POS.
- Creacion de pedidos delivery.
- Carga de datos del cliente.
- Carga de celular para contacto.
- Carga de direccion y referencias.
- Asociacion de productos al pedido.
- Estado actual del pedido.
- Tiempo estimado.
- Impresion de ticket.
- Vista publica de seguimiento por codigo o link.
- Panel de pedidos activos.
- Cambio rapido de estados.

## Flujo Principal

1. El operador entra al POS y selecciona `Delivery`.
2. Carga los productos del pedido igual que en una venta normal.
3. Carga los datos del cliente.
4. Define si es envio a domicilio o retiro en local.
5. Si es envio, carga direccion y referencia.
6. Carga celular obligatorio o recomendado.
7. Define metodo de pago.
8. Define tiempo estimado, si corresponde.
9. Confirma el pedido.
10. El sistema genera un codigo publico de seguimiento.
11. Se imprime el ticket.
12. El pedido queda visible en el panel de delivery.
13. El operador o cocina cambia el estado a medida que avanza.
14. El cliente puede consultar el estado desde un link publico.

## Estados Del Pedido

Estados base recomendados:

- `recibido`: el pedido fue tomado.
- `confirmado`: el comercio confirmo que lo va a preparar.
- `en_preparacion`: cocina esta preparando el pedido.
- `listo`: el pedido esta listo.
- `en_camino`: el pedido salio con delivery.
- `entregado`: el pedido fue entregado.
- `cancelado`: el pedido fue cancelado.

Estados o flags opcionales:

- `demorado`: puede ser un estado o una marca auxiliar.
- `pago_pendiente`: indica que el pedido todavia no fue cobrado.
- `pagado`: indica que el pedido ya fue cobrado.

Recomendacion: mantener estados simples al principio y manejar demora/pago como campos separados para no complicar el flujo principal.

## Datos Del Pedido

Campos principales del pedido:

- ID interno.
- Codigo publico de seguimiento.
- Fecha y hora de creacion.
- Estado actual.
- Tipo de entrega: `delivery` o `retiro_en_local`.
- Nombre del cliente.
- Celular del cliente.
- Direccion de entrega.
- Referencia de domicilio.
- Notas del cliente.
- Notas internas.
- Metodo de pago.
- Estado de pago.
- Costo de envio.
- Subtotal.
- Descuento, si aplica.
- Total.
- Tiempo estimado en minutos.
- Fecha/hora estimada de entrega, si aplica.
- Repartidor asignado, si aplica en una etapa posterior.
- Venta asociada, si el pedido se registra tambien como venta POS.
- Usuario que creo el pedido.
- Usuario que hizo la ultima modificacion.

## Datos Del Cliente

Para delivery gastronomico, el celular debe tener mucha importancia.

Campos recomendados:

- Nombre.
- Celular.
- Direccion.
- Piso/departamento, si aplica.
- Referencia.
- Observaciones.

Reglas sugeridas:

- Para pedidos `delivery`, el celular deberia ser obligatorio.
- Para pedidos `delivery`, la direccion deberia ser obligatoria.
- Para `retiro_en_local`, el celular puede ser obligatorio o recomendado segun configuracion.
- El celular debe imprimirse en el ticket.
- El celular debe estar disponible con boton de copiar o abrir WhatsApp en una etapa posterior.

## Productos Del Pedido

El pedido debe reutilizar la logica de seleccion de productos del POS siempre que sea posible.

Cada item deberia guardar:

- Producto.
- Cantidad.
- Precio unitario.
- Subtotal.
- Notas por item.
- Modificadores o variantes, si el sistema los soporta en el futuro.

Ejemplos de notas por item:

- Sin cebolla.
- Extra queso.
- Punto de coccion.
- Bebida fria.

## Ticket Impreso

El ticket debe identificar claramente que se trata de un pedido delivery.

Contenido recomendado:

- Encabezado del comercio.
- Texto visible `DELIVERY` o `RETIRO EN LOCAL`.
- Numero o codigo del pedido.
- Fecha y hora.
- Nombre del cliente.
- Celular del cliente.
- Direccion de entrega.
- Referencia.
- Metodo de pago.
- Estado de pago.
- Productos.
- Cantidades.
- Notas por item.
- Notas generales.
- Costo de envio.
- Total.
- Tiempo estimado.
- Link o codigo de seguimiento, si entra en el formato de impresion.

Versiones posibles de ticket:

- Ticket para cocina: productos, cantidades y notas de preparacion.
- Ticket para delivery: cliente, celular, direccion, pago, total y productos resumidos.
- Ticket para cliente: comprobante del pedido.

Para el MVP puede imprimirse un solo ticket completo.

## Vista Publica Para El Cliente

El cliente debe poder consultar el estado de su pedido sin iniciar sesion.

Ejemplo de ruta:

`/pedido/<codigo>`

Informacion visible:

- Nombre del comercio.
- Codigo del pedido.
- Estado actual.
- Mensaje claro segun estado.
- Tiempo estimado.
- Ultima actualizacion.
- Timeline simple de estados.
- Datos basicos del pedido.

No deberia mostrar informacion sensible innecesaria.

Mensajes sugeridos:

- `recibido`: Recibimos tu pedido.
- `confirmado`: Tu pedido fue confirmado.
- `en_preparacion`: Estamos preparando tu pedido.
- `listo`: Tu pedido esta listo.
- `en_camino`: Tu pedido ya salio con el delivery.
- `entregado`: Tu pedido fue entregado.
- `cancelado`: Tu pedido fue cancelado.

## Panel Delivery En POS

La seccion `Delivery` del POS deberia permitir:

- Crear pedido.
- Ver pedidos activos.
- Buscar pedidos.
- Filtrar por estado.
- Cambiar estado rapidamente.
- Ver datos del cliente.
- Ver celular.
- Ver direccion.
- Reimprimir ticket.
- Cancelar pedido con motivo.
- Marcar como pagado.
- Modificar tiempo estimado.

Vista recomendada para pedidos activos:

- Lista compacta o tablero por columnas.
- Prioridad visual para pedidos demorados.
- Hora de ingreso visible.
- Minutos transcurridos visibles.
- Estado actual bien destacado.

Columnas posibles:

- Recibidos.
- En preparacion.
- Listos.
- En camino.

## Historial De Estados

Cada cambio de estado deberia registrar:

- Pedido.
- Estado anterior.
- Estado nuevo.
- Usuario que realizo el cambio.
- Fecha y hora.
- Comentario opcional.
- Si el cambio es visible para el cliente.

Este historial permite:

- Mostrar timeline al cliente.
- Auditar demoras.
- Saber quien cambio un estado.
- Resolver reclamos.

## Reutilizacion De Reparaciones

Se puede reutilizar el concepto de reparaciones, pero no necesariamente sus modelos.

Partes reutilizables como patron:

- Codigo publico de consulta.
- Vista publica de estado.
- Historial de cambios.
- Mensajes segun estado.
- Consulta sin login.

Partes que no conviene reutilizar directamente:

- Modelo de equipo.
- Campos especificos de reparacion.
- Estados tecnicos de reparacion.
- Logica de diagnostico o presupuesto.

La recomendacion es crear modelos propios para delivery y, si existe codigo util de seguimiento publico, extraer una utilidad o servicio comun solo si encaja limpio.

## Modelo De Datos Sugerido

Tabla `delivery_pedidos`:

- `id`
- `codigo_publico`
- `estado`
- `tipo_entrega`
- `nombre_cliente`
- `celular_cliente`
- `direccion_entrega`
- `referencia_entrega`
- `notas_cliente`
- `notas_internas`
- `metodo_pago`
- `estado_pago`
- `costo_envio`
- `subtotal`
- `descuento`
- `total`
- `tiempo_estimado_minutos`
- `fecha_estimada_entrega`
- `venta_id`
- `usuario_creacion_id`
- `usuario_actualizacion_id`
- `created_at`
- `updated_at`

Tabla `delivery_pedido_items`:

- `id`
- `pedido_id`
- `producto_id`
- `descripcion`
- `cantidad`
- `precio_unitario`
- `subtotal`
- `notas`
- `created_at`

Tabla `delivery_estado_historial`:

- `id`
- `pedido_id`
- `estado_anterior`
- `estado_nuevo`
- `usuario_id`
- `comentario`
- `visible_cliente`
- `created_at`

Tabla opcional `delivery_repartidores`:

- `id`
- `nombre`
- `celular`
- `activo`
- `created_at`
- `updated_at`

Campo opcional futuro en `delivery_pedidos`:

- `repartidor_id`

## API Sugerida

Endpoints internos para POS:

- `GET /api/delivery/pedidos`
- `POST /api/delivery/pedidos`
- `GET /api/delivery/pedidos/<id>`
- `PUT /api/delivery/pedidos/<id>`
- `POST /api/delivery/pedidos/<id>/estado`
- `POST /api/delivery/pedidos/<id>/cancelar`
- `POST /api/delivery/pedidos/<id>/marcar-pagado`
- `POST /api/delivery/pedidos/<id>/reimprimir-ticket`

Endpoint publico:

- `GET /api/delivery/publico/<codigo>`

Vista publica:

- `GET /pedido/<codigo>`

## Validaciones

Validaciones recomendadas:

- El pedido debe tener al menos un producto.
- Si `tipo_entrega = delivery`, debe tener direccion.
- Si `tipo_entrega = delivery`, debe tener celular.
- El total no puede ser negativo.
- El costo de envio no puede ser negativo.
- El estado debe pertenecer a los estados permitidos.
- No se deberia permitir cambiar un pedido `entregado` o `cancelado` sin una accion explicita de reapertura.
- El codigo publico debe ser unico.

## Seguridad

Para la vista publica:

- Usar codigos publicos dificiles de adivinar.
- No exponer IDs incrementales.
- No mostrar datos internos.
- No permitir modificar pedidos desde endpoints publicos.
- No mostrar notas internas.

Para el POS:

- Requerir login.
- Respetar permisos existentes si el sistema ya los tiene.
- Registrar usuario en cambios importantes.

## Configuraciones Utiles

Configuraciones futuras o iniciales segun complejidad:

- Tiempo estimado por defecto.
- Costo de envio por defecto.
- Requerir celular siempre.
- Requerir direccion solo en delivery.
- Imprimir automaticamente al confirmar.
- Cantidad de copias del ticket.
- Mostrar link publico en ticket.
- Estados visibles para cliente.
- Mensajes personalizados por estado.

## Reportes Futuros

Reportes utiles:

- Cantidad de pedidos por dia.
- Ventas por delivery.
- Promedio de tiempo de entrega.
- Pedidos cancelados.
- Motivos de cancelacion.
- Pedidos demorados.
- Productos mas vendidos por delivery.
- Pedidos por metodo de pago.

## Integraciones Futuras

Posibles mejoras:

- Enviar link por WhatsApp.
- Boton para abrir WhatsApp al cliente.
- Notificaciones automaticas por cambio de estado.
- Asignacion de repartidor.
- Mapa o link a Google Maps.
- Calculo automatico de costo de envio.
- Comandas separadas por cocina y delivery.
- Impresion automatica en cocina.
- Pantalla tipo KDS para cocina.

## MVP Recomendado

Primera version minima:

1. Nueva seccion `Delivery` en POS.
2. Crear pedido con productos, nombre, celular, direccion, notas y metodo de pago.
3. Estados basicos: recibido, en preparacion, listo, en camino, entregado y cancelado.
4. Ticket impreso con tipo de pedido, celular, direccion, productos y total.
5. Panel de pedidos activos.
6. Cambio rapido de estado.
7. Codigo publico de seguimiento.
8. Vista publica simple para el cliente.

## Segunda Etapa

Mejoras despues del MVP:

- Historial visual completo.
- Reimpresion avanzada.
- Motivo de cancelacion.
- Pago pendiente/pagado.
- Boton WhatsApp.
- Repartidores.
- Reportes.
- Demoras destacadas.
- Configuracion de mensajes por estado.

## Criterios De Aceptacion

El modulo puede considerarse funcional cuando:

- Se puede crear un pedido delivery desde POS.
- El pedido guarda celular y direccion.
- El ticket impreso incluye celular y direccion.
- El pedido tiene estados modificables.
- El cliente puede consultar el estado con un codigo publico.
- Los pedidos activos se pueden ver desde POS.
- Se puede marcar un pedido como entregado o cancelado.
- No se mezclan responsabilidades con reparaciones.
- No se rompe el flujo de ventas actual.

## Riesgos A Tener En Cuenta

- Acoplar demasiado delivery con reparaciones.
- Crear un flujo demasiado complejo para el MVP.
- No imprimir datos suficientes para el repartidor.
- No registrar historial de estados desde el inicio.
- Usar IDs internos en links publicos.
- No diferenciar bien delivery de retiro en local.
- No contemplar pedidos demorados.

## Recomendacion Final

El modulo deberia construirse como una extension natural del POS, con modelos propios de delivery y una vista publica de seguimiento inspirada en reparaciones.

La prioridad inicial debe ser resolver bien el flujo operativo diario: tomar pedido, imprimir ticket, preparar, enviar y permitir que el cliente vea el estado.

Las integraciones como WhatsApp, repartidores y reportes pueden agregarse despues, una vez que el MVP este estable.
