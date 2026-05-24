# Gastronomia - Integracion inicial

## Punto de integracion

- El modulo vive en `gastronomia/`, separado de rutas, servicios y modelos del backoffice existente.
- La aplicacion registra un blueprint propio en `/gastronomia`.
- El dashboard principal solo consulta el modo activo del cliente y redirige cuando corresponde.
- La activacion por cliente se administra desde `/usuarios/modulos-sistema`, visible solo para el usuario root real.

## Modelo inicial

- `gastronomia_cliente_config` guarda `cliente_id`, `modo_operacion`, `gastronomia_activo` y auditoria basica.
- Los clientes sin fila en esa tabla quedan en modo `servicios` por defecto.
- `Consumidor Final` no puede configurarse como cliente gastronomico.

## Reglas aplicadas

- Los usuarios comunes y administradores de cliente no pueden cambiar el modo.
- El cambio de modo no borra datos ni modifica modelos de ventas, reparaciones o tienda online.
- El dashboard gastronomico inicial esta protegido por login y verifica que el cliente tenga Gastronomia activa.

## Siguientes pasos

- Sprint 2: modelos y CRUD de menu inicial completados con categorias/productos por `cliente_id`.
- Sprint 3: modificadores iniciales completados con grupos `variante`, `extra`, `ingrediente_removible` y `combo`.
- Sprint 4: POS touch inicial completado con carrito, modificadores, persistencia de pedidos y envio a cocina.
- Sprint 5: KDS inicial completado con pedidos pendientes, estados de cocina y eventos persistidos por `cliente_id`.
- Sprint 6: caja inicial completada con listado de pedidos cobrables, descuento simple, metodo de pago, registro persistido y estado `cobrado`.
- Sprint 7: salon inicial completado con mesas por `cliente_id`, estado calculado desde pedidos activos, apertura hacia POS y movimiento de pedidos entre mesas.
- Sprint 8: reportes iniciales completados con ventas por periodo, productos mas vendidos, ventas por metodo de pago, pedidos cancelados y tiempo promedio de preparacion.
- Sprint 9: permisos operativos iniciales completados con permisos `gastronomia_*` y roles base `Cocina`, `Mozo` y `Caja Gastronomia`.
- Siguiente paso recomendado: pulido visual en tablet, sonidos configurables y exportacion de reportes.
