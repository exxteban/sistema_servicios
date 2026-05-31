# Gastronomia: salida a produccion

## Migracion y backup

1. Verificar `DATABASE_URL` y `ENV_FILE_PATH` del servidor.
2. Ejecutar `ENV_FILE_PATH=/etc/instancia.env SERVICE_NAME=nombre-servicio bash deploy/update_min.sh`; por defecto corre `migrations/gastronomia_base.py`.
3. Confirmar en la salida la ruta `Backup pre-migracion OK`.
4. Si ya existe un backup externo validado, se puede omitir el backup local con `SKIP_GASTRONOMIA_BACKUP=1`, pero no es recomendado.

El script crea un backup antes de tocar la base y asegura las tablas/columnas actuales de Gastronomia. Siempre debe recibir `ENV_FILE_PATH` y `SERVICE_NAME` de la instancia desplegada. Si se necesita correr la migracion manualmente, primero se debe cargar el env correcto y luego ejecutar `python migrations/gastronomia_base.py`. Para desactivar solo esta migracion en un update: `RUN_GASTRONOMIA_MIGRATIONS=0 ENV_FILE_PATH=/etc/instancia.env SERVICE_NAME=nombre-servicio bash deploy/update_min.sh`. Para omitir el backup local cuando ya existe un backup externo validado: `SKIP_GASTRONOMIA_BACKUP=1`.

## Reglas de caja

1. IVA gastronomico: por defecto usa `10`.
2. Para cambiarlo, configurar `gastronomia_iva_porcentaje` en `configuraciones` con valor `10`, `5` o `0`.
3. Los metodos de pago con `requiere_referencia=True` rechazan cobros sin referencia.
4. La anulacion de una venta central asociada a Gastronomia cancela el pedido, elimina el cobro gastronomico y restaura stock controlado.

## Prueba manual obligatoria

1. Cargar categoria, producto con precio, producto agotado y producto con modificadores.
2. Crear pedido de mostrador desde POS y guardarlo sin enviar.
3. Editar el pedido abierto y confirmar que mantiene items/modificadores.
4. Enviar pedido a cocina y validar que aparece en KDS.
5. Pasar pedido por `preparando`, `listo` y `entregado`.
6. Crear pedido de mesa desde Salon y moverlo a otra mesa.
7. Cobrar desde Caja con efectivo y validar ticket impreso.
8. Cobrar con metodo que requiere referencia y validar rechazo sin referencia.
9. Anular la venta central y validar que el pedido queda cancelado.
10. Verificar Entregas y Reportes del dia.
11. Abrir el menu TV publico y validar productos visibles/precios/agotados.

## Piloto controlado

1. Usar 1 caja, 1 usuario POS y 1 pantalla cocina durante el primer turno.
2. Registrar manualmente cantidad de pedidos, cobros, anulaciones y diferencias de caja.
3. Revisar logs al cierre del turno.
4. Comparar total de Caja Gastronomia contra ventas centrales y movimientos de caja.
5. Si no hay diferencias ni errores repetidos, habilitar al resto del equipo.

## Criterio de aprobacion

1. Suite `test_gastronomia_*.py` pasando.
2. Backup recuperable confirmado.
3. Ticket real impreso correctamente.
4. Cierre de caja sin diferencias no explicadas.
5. Flujo de anulacion validado por el responsable operativo.
