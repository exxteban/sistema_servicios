# Plan de Implementacion: Modo Gastronomia

## Objetivo

Agregar un nuevo modo operativo de Gastronomia dentro del mismo SaaS, reutilizando la base existente de clientes, usuarios, autenticacion y configuracion general, pero manteniendo el nuevo dominio lo mas aislado posible del flujo actual de servicios.

El sistema debe permitir que el usuario root active para cada cliente un modo principal desde la seccion de modulos del sistema:

- `servicios`: experiencia actual del sistema.
- `gastronomia`: nueva experiencia orientada a restaurante, pedidos touch, cocina y caja.

El cliente final no debe poder activar ni desactivar este modo por su cuenta. La habilitacion corresponde solamente al usuario root, que es invisible para los clientes y tiene control total del SaaS.

La prioridad tecnica es evitar mezclar responsabilidades. Gastronomia debe crecer como modulo propio, con rutas, modelos, servicios, templates y archivos estaticos separados.

## Principios de Arquitectura

1. **Mismo repositorio, modulo aislado**
   - No crear otro repo inicialmente.
   - Crear una zona propia para Gastronomia dentro del backend actual.
   - Evitar modificar pantallas actuales salvo para agregar la redireccion segun modo activo.

2. **Separacion por dominio**
   - Todo lo gastronomico debe vivir en carpetas, blueprints, modelos y servicios con nombre claro: `gastronomia`.
   - No meter logica de pedidos de restaurante dentro de funciones existentes de reparaciones/servicios.

3. **Multi-tenant estricto**
   - Todo dato de Gastronomia debe estar atado a `cliente_id`.
   - No debe existir consulta gastronomica sin filtro por `cliente_id`.
   - WebSocket tambien debe respetar salas/canales por cliente.

4. **Base de datos como fuente de verdad**
   - WebSocket se usa para notificar en tiempo real.
   - Los pedidos, estados e items siempre se persisten primero en base de datos.
   - Si una pantalla se desconecta, al reconectar debe recuperar el estado actual por API.

5. **Touch first**
   - El POS debe estar pensado para tablet o pantalla tactil.
   - Botones grandes, pocos campos escritos, flujos rapidos.
   - La edicion de productos debe ser visual: extras, quitar ingredientes, notas y cantidades.

6. **Configurabilidad**
   - El restaurante debe poder cargar categorias, productos, variantes, extras, combos y disponibilidad.
   - No hardcodear productos ni reglas de menu en el frontend.

7. **Limite de archivos**
   - Ningun archivo debe superar 600 lineas.
   - Si una vista o servicio crece demasiado, dividir en componentes, servicios o utilidades.

## Estructura Recomendada

La estructura exacta debe adaptarse al proyecto actual, pero la separacion deberia parecerse a esto:

```text
sistema_silvio_cel/
  gastronomia/
    __init__.py
    routes/
      dashboard_routes.py
      menu_routes.py
      pedido_routes.py
      cocina_routes.py
      caja_routes.py
    services/
      menu_service.py
      pedido_service.py
      cocina_service.py
      caja_service.py
    models/
      menu_models.py
      pedido_models.py
      mesa_models.py
    sockets/
      cocina_socket.py
    templates/
      gastronomia/
        dashboard.html
        pos.html
        cocina.html
        menu_config.html
        caja.html
    static/
      gastronomia/
        css/
        js/
```

Si el proyecto ya tiene convenciones distintas, respetarlas, pero manteniendo el aislamiento por modulo.

## Modelo Funcional

### Modo por Cliente Administrado por Root

Cada cliente debe tener una configuracion que indique el modo activo, pero esa configuracion solo puede ser modificada por el usuario root desde la seccion de modulos del sistema.

Campos sugeridos:

- `modo_operacion`: `servicios` o `gastronomia`.
- `gastronomia_activo`: booleano opcional si conviene.
- Configuracion adicional gastronomica en una tabla separada para no ensuciar el modelo principal.

Reglas:

- El cliente no ve un boton para activar o desactivar Gastronomia.
- Solo el root puede habilitar o deshabilitar el modulo.
- La seccion de modulos debe permitir seleccionar el cliente y activar/desactivar Gastronomia.
- Si el modo activo es `servicios`, se muestra el dashboard actual.
- Si el modo activo es `gastronomia`, se redirige al dashboard gastronomico.
- El cambio de modo no borra datos del otro modo.

### Menu

Entidades sugeridas:

- Categoria.
- Producto.
- Variante.
- Extra.
- Ingrediente removible.
- Combo.
- Grupo de opciones.
- Disponibilidad.

Ejemplos:

- Hamburguesa clasica.
- Extra queso.
- Sin lechuga.
- Combo hamburguesa + papas + gaseosa.
- Pizza grande / mediana.
- Producto agotado temporalmente.

### Pedidos

Tipos de pedido:

- Mesa.
- Mostrador.
- Retiro.
- Delivery, si se decide incluirlo en una fase posterior.

Estados sugeridos:

- `abierto`
- `enviado_cocina`
- `preparando`
- `listo`
- `entregado`
- `cobrado`
- `cancelado`

Cada pedido debe guardar:

- Cliente.
- Usuario que lo creo.
- Mesa o tipo de pedido.
- Items.
- Modificadores por item.
- Notas por item.
- Estado.
- Totales.
- Tiempos de creacion y actualizacion.

### Cocina

La cocina debe tener una pantalla tipo KDS.

Debe mostrar:

- Pedidos pendientes.
- Tiempo transcurrido.
- Items agrupados.
- Notas visibles.
- Modificadores importantes.
- Botones grandes para cambiar estado.

Estados operativos:

- Nuevo.
- En preparacion.
- Listo.

Opcional por fases:

- Estaciones: cocina, barra, parrilla.
- Prioridad.
- Sonido al recibir pedido.
- Vista por pantalla separada.

### Caja

Funciones iniciales:

- Ver pedido listo o entregado.
- Cobrar.
- Registrar metodo de pago.
- Aplicar descuento simple.
- Marcar como cobrado.

Funciones posteriores:

- Dividir cuenta.
- Propina.
- Facturacion integrada.
- Cierre de caja.
- Reporte por turno.

## WebSocket

WebSocket debe usarse para eventos en tiempo real, especialmente entre POS y cocina.

Eventos sugeridos:

- `pedido_creado`
- `pedido_enviado_cocina`
- `pedido_actualizado`
- `pedido_estado_cambiado`
- `pedido_listo`
- `item_actualizado`

Reglas:

- Cada cliente debe usar una sala/canal separado: por ejemplo `cliente:{cliente_id}:gastronomia`.
- No enviar datos de un cliente a otro.
- El evento WebSocket no reemplaza la persistencia.
- Cada pantalla debe poder reconstruir su estado haciendo una llamada API.

## APIs Sugeridas

Endpoints internos sugeridos:

```text
GET    /api/gastronomia/config
PUT    /api/gastronomia/config

GET    /api/gastronomia/categorias
POST   /api/gastronomia/categorias
PUT    /api/gastronomia/categorias/<id>
DELETE /api/gastronomia/categorias/<id>

GET    /api/gastronomia/productos
POST   /api/gastronomia/productos
PUT    /api/gastronomia/productos/<id>
DELETE /api/gastronomia/productos/<id>

GET    /api/gastronomia/pedidos
POST   /api/gastronomia/pedidos
GET    /api/gastronomia/pedidos/<id>
PUT    /api/gastronomia/pedidos/<id>
POST   /api/gastronomia/pedidos/<id>/enviar-cocina
POST   /api/gastronomia/pedidos/<id>/estado

GET    /api/gastronomia/cocina/pedidos
POST   /api/gastronomia/cocina/pedidos/<id>/tomar
POST   /api/gastronomia/cocina/pedidos/<id>/listo

POST   /api/gastronomia/caja/pedidos/<id>/cobrar
```

## Sprints

Estado de avance al 2026-05-24:

- Sprint 0 completado: estructura aislada, blueprint y documento tecnico de integracion.
- Sprint 1 completado: modo `gastronomia` activable por root y redireccion por cliente.
- Sprint 2 completado: CRUD inicial de categorias/productos y API de menu por `cliente_id`.
- Sprint 3 completado: variantes, extras, ingredientes removibles y combos simples.
- Sprint 4 completado: POS touch inicial con carrito, modificadores, persistencia y envio a cocina.
- Sprint 5 completado: KDS inicial con pedidos pendientes, estados de cocina y eventos por cliente.
- Sprint 6 completado: caja inicial con cobro, descuento simple, metodo de pago y estado `cobrado`.
- Sprint 7 completado: mesas y salon inicial con estados por pedidos activos y movimiento entre mesas.
- Sprint 8 completado: reportes iniciales con ventas, productos mas vendidos, metodos de pago, cancelados y tiempos de preparacion.
- Sprint 9 en avance: permisos operativos por rol completados con roles `Cocina`, `Mozo` y `Caja Gastronomia`.
- Proximo foco: pulido visual en tablet, sonidos configurables y exportacion simple de reportes.

### Sprint 0: Analisis y Preparacion

Objetivo: entender el sistema actual y definir el punto exacto de integracion sin tocar flujos sensibles.

Tareas:

- Revisar estructura actual del backend, rutas, templates, autenticacion y modelo de cliente.
- Identificar como se resuelve actualmente el dashboard inicial.
- Identificar sistema de permisos/roles si existe.
- Definir ubicacion exacta del modulo `gastronomia`.
- Definir estrategia de migraciones.
- Documentar dependencias actuales antes de agregar WebSocket.

Entregables:

- Documento tecnico corto con puntos de integracion.
- Estructura inicial de carpetas.
- Blueprint o modulo vacio registrado sin romper nada.

Criterios de aceptacion:

- El sistema actual sigue funcionando igual.
- Existe una ruta base de Gastronomia protegida por login.
- No hay cambios visuales fuertes todavia.

### Sprint 1: Modo Gastronomia Controlado por Root

Objetivo: permitir que el usuario root active Gastronomia para un cliente desde la seccion de modulos, sin eliminar el modo actual ni exponer esta decision al cliente.

Tareas:

- Agregar campo o tabla de configuracion para modo activo.
- Crear migracion con defaults seguros.
- Crear servicio para leer el modo activo del cliente.
- Ajustar redireccion del dashboard segun modo.
- Crear pantalla base de dashboard gastronomico.
- Agregar control en la seccion de modulos del sistema, visible solo para root.
- Bloquear cualquier intento de cambio de modo desde usuarios normales o administradores del cliente.

Entregables:

- `modo_operacion` funcional.
- Dashboard gastronomico inicial.
- Redireccion segura segun cliente.
- Control root para activar/desactivar Gastronomia por cliente.

Criterios de aceptacion:

- Clientes existentes quedan en modo `servicios` por defecto.
- El root puede activar Gastronomia desde la seccion de modulos.
- El root puede desactivar Gastronomia y volver al dashboard actual.
- El cliente no puede activar ni desactivar Gastronomia por su cuenta.
- No se pierden datos al cambiar de modo.

### Sprint 2: Configuracion de Menu

Objetivo: permitir cargar lo que ofrece el restaurante.

Tareas:

- Crear modelos de categorias y productos.
- Crear CRUD de categorias.
- Crear CRUD de productos.
- Agregar precio, descripcion, imagen opcional, disponibilidad y orden.
- Agregar filtros por `cliente_id` en todas las consultas.
- Crear vista de configuracion de menu.

Entregables:

- Panel para cargar categorias.
- Panel para cargar productos.
- API de menu.

Criterios de aceptacion:

- Un cliente solo ve sus productos.
- Se puede marcar un producto como agotado u oculto.
- El POS puede consumir el menu por API.

### Sprint 3: Variantes, Extras, Ingredientes y Combos

Objetivo: hacer que el menu sea realmente configurable para gastronomia.

Tareas:

- Agregar variantes de producto: tamanos, sabores, puntos de coccion.
- Agregar extras con precio adicional.
- Agregar ingredientes removibles.
- Agregar grupos de opciones obligatorios u opcionales.
- Agregar estructura inicial para combos.
- Validar reglas de seleccion desde backend.

Entregables:

- Configuracion completa de modificadores.
- Soporte para combos simples.
- API que devuelva productos listos para POS.

Criterios de aceptacion:

- Se puede pedir un producto con extras.
- Se puede pedir un producto sin ingredientes especificos.
- Se puede armar un combo desde opciones configuradas.
- El total se calcula correctamente en backend.

### Sprint 4: POS Touch para Toma de Pedidos

Objetivo: crear una pantalla tactil para tomar pedidos rapido.

Tareas:

- Crear vista POS.
- Mostrar categorias como botones grandes.
- Mostrar productos como botones grandes.
- Crear carrito/pedido actual.
- Permitir editar item: cantidad, extras, quitar ingredientes, notas.
- Crear pedidos de mesa y mostrador.
- Guardar pedidos en estado `abierto`.
- Enviar pedido a cocina.

Entregables:

- POS funcional para crear pedidos.
- Edicion visual de items.
- Envio a cocina.

Criterios de aceptacion:

- Un pedido puede armarse sin usar teclado en el flujo principal.
- Las notas manuales son opcionales.
- El total se recalcula al cambiar extras o cantidades.
- El pedido queda persistido antes de enviarse a cocina.

### Sprint 5: Pantalla de Cocina en Tiempo Real

Objetivo: implementar el mostrador de cocina con actualizacion en vivo.

Tareas:

- Agregar soporte WebSocket.
- Crear canal/sala por cliente.
- Emitir evento al enviar pedido a cocina.
- Crear vista KDS para cocina.
- Mostrar pedidos pendientes.
- Permitir cambiar estados: nuevo, preparando, listo.
- Sincronizar cambios con WebSocket.
- Agregar recuperacion inicial por API.

Entregables:

- Pantalla de cocina.
- Eventos en tiempo real.
- Estados de preparacion.

Criterios de aceptacion:

- Al enviar un pedido desde POS aparece en cocina sin refrescar.
- Si cocina marca como listo, POS/caja lo ven actualizado.
- Si se recarga cocina, recupera pedidos pendientes por API.
- No se filtran pedidos entre clientes.

### Sprint 6: Caja y Cobro

Objetivo: cerrar el flujo operativo basico del restaurante.

Tareas:

- Crear vista de caja.
- Listar pedidos listos, entregados o abiertos para cobrar.
- Registrar metodo de pago.
- Aplicar descuento simple si se permite.
- Marcar pedido como cobrado.
- Evitar editar pedidos ya cobrados salvo permisos especiales.

Entregables:

- Caja basica.
- Registro de cobros.
- Estado `cobrado`.

Criterios de aceptacion:

- Un pedido puede pasar desde POS hasta cocina y caja.
- El cobro queda registrado.
- Un pedido cobrado no se modifica accidentalmente.

### Sprint 7: Mesas y Salon

Objetivo: agregar manejo visual de mesas si el restaurante lo necesita.

Tareas:

- Crear modelo de mesas.
- Crear estados: libre, ocupada, esperando cocina, listo, cobrando.
- Permitir abrir pedido desde una mesa.
- Ver resumen de mesa.
- Mover pedido de mesa si hace falta.

Entregables:

- Vista de salon.
- Gestion basica de mesas.

Criterios de aceptacion:

- Se puede abrir una mesa.
- Se puede agregar productos a una mesa abierta.
- Se puede cerrar/cobrar una mesa.

### Sprint 8: Reportes y Control

Objetivo: dar visibilidad del negocio gastronomico.

Tareas:

- Reporte de ventas por dia.
- Productos mas vendidos.
- Ventas por metodo de pago.
- Tiempo promedio de preparacion.
- Pedidos cancelados.
- Exportacion simple si el sistema ya soporta reportes.

Entregables:

- Dashboard de metricas gastronomicas.
- Reportes basicos.

Criterios de aceptacion:

- El cliente puede ver ventas del dia.
- El cliente puede identificar productos mas vendidos.
- Los reportes respetan `cliente_id`.

### Sprint 9: Pulido Operativo

Objetivo: mejorar usabilidad y robustez antes de considerarlo modulo vendible.

Tareas:

- Agregar permisos por rol: caja, cocina, administrador.
- Agregar sonidos configurables en cocina.
- Mejorar estados vacios y errores.
- Agregar validaciones de stock/disponibilidad.
- Optimizar flujo tactil.
- Pruebas en tablet o viewport chico.
- Revisar archivos mayores a 600 lineas y dividir.

Entregables:

- Experiencia mas estable.
- Permisos basicos.
- UI mas lista para uso real.

Criterios de aceptacion:

- Cocina puede operar sin acceso a configuracion.
- Caja puede cobrar sin editar menu.
- Administrador puede configurar menu.
- La experiencia touch es fluida.

## Riesgos y Cuidados

### Riesgo: mezclar Gastronomia con Servicios

Mitigacion:

- Crear servicios y rutas nuevas.
- Solo tocar el dashboard/router principal para decidir a donde enviar al usuario.
- No modificar logica de ordenes de servicio para adaptarla a pedidos de comida.

### Riesgo: WebSocket sin persistencia confiable

Mitigacion:

- Guardar en base de datos antes de emitir eventos.
- Al cargar pantalla, consultar API.
- Usar WebSocket solo como notificador.

### Riesgo: consultas sin `cliente_id`

Mitigacion:

- Servicios centralizados para consultas.
- Tests o revisiones manuales de endpoints.
- Nunca confiar el `cliente_id` enviado por frontend si ya existe en sesion.

### Riesgo: POS lento o dificil de usar

Mitigacion:

- Disenar touch first.
- Priorizar botones grandes y flujos cortos.
- Reducir campos escritos.
- Probar en resoluciones tipo tablet.

### Riesgo: archivos grandes

Mitigacion:

- Dividir por responsabilidades desde el inicio.
- Componentes pequenos.
- Servicios separados para calculo de totales, validacion y estados.

## Orden de Prioridad Realista

Para una primera version usable, el orden recomendado es:

1. Modo por cliente.
2. Menu configurable.
3. POS touch.
4. Cocina en tiempo real.
5. Caja.
6. Mesas.
7. Reportes.

La version minima vendible podria salir al terminar Sprint 6 si el restaurante opera principalmente por mostrador o pedidos simples. Para restaurantes con salon, conviene llegar al Sprint 7 antes de ofrecerlo como producto formal.

## Definicion de MVP

El MVP de Gastronomia debe permitir:

- Activar modo Gastronomia para un cliente desde la seccion de modulos, solo con usuario root.
- Cargar categorias y productos.
- Configurar extras y opciones simples.
- Tomar un pedido desde pantalla touch.
- Enviar pedido a cocina.
- Ver pedido en cocina en tiempo real.
- Marcar pedido como listo.
- Cobrar pedido.

Lo que puede quedar para despues:

- Delivery avanzado.
- Dividir cuenta.
- Propinas.
- Integracion fiscal compleja.
- Stock avanzado por ingredientes.
- Mapa de mesas visual avanzado.
- Multi-estacion de cocina.

## Notas de Implementacion

- Cada sprint debe mantener el sistema actual funcionando.
- Las migraciones deben tener defaults seguros.
- Los endpoints deben validar permisos y cliente.
- Los calculos de precio deben hacerse en backend.
- El frontend puede mostrar totales estimados, pero el total final confiable viene del backend.
- No se deben crear dependencias innecesarias con `tienda_online`.
- Si se reutiliza caja/facturacion actual, hacerlo mediante adaptadores claros, no mezclando modelos gastronomicos con servicios tecnicos.
