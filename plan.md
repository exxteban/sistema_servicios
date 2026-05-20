# Plan de correccion para ventas a credito

## Problema actual

Hoy el sistema ya separa varias piezas importantes de una venta a credito:

- `Venta`: registra la operacion comercial.
- `PagoVenta`: registra solo lo cobrado en el momento de la venta.
- `CuentaPorCobrar`: registra la deuda pendiente.
- `PlanCreditoVenta` y `CuotaCreditoVenta`: registran el plan financiado y sus cuotas.
- `PagoCuentaCobrar`: registra los cobros posteriores del credito.
- `MovimientoCaja`: registra entradas y salidas reales de caja.

El problema no parece estar en `cobranzas`, sino en que distintos modulos interpretan "venta" de formas diferentes:

- algunos usan `Venta.total` para medir ventas/facturacion;
- otros usan `PagoVenta` para mostrar ventas del dia;
- otros mezclan cobro inmediato con venta emitida;
- en UI el historial puede mostrar una venta a credito como si fuera contado, o al menos dejar esa impresion.

Resultado:

- una venta a credito puede verse "completada" pero seguir impaga;
- el historial puede parecer de contado si solo mira total o pagos sin aclarar `tipo_venta`;
- contabilidad, caja, dashboard e inteligencia comercial pueden contar cosas distintas con el mismo nombre.

## Objetivo

Lograr que una venta a credito se registre y se muestre correctamente en todo el sistema, separando claramente:

1. venta emitida
2. cobro inmediato
3. saldo financiado
4. cobros posteriores del credito
5. interes financiero

## Regla de negocio correcta

### 1. Venta contado

- `Venta.total` = total comercial de la venta
- `Venta.tipo_venta` = `contado`
- `Venta.saldo_pendiente` = `0`
- `PagoVenta` = total cobrado al momento
- `MovimientoCaja` = solo por medios que afecten caja real

### 2. Venta credito sin anticipo

- `Venta.total` = total comercial de la mercaderia/servicio
- `Venta.tipo_venta` = `credito`
- `PagoVenta` = no debe existir si no hubo cobro inmediato
- `CuentaPorCobrar` = se crea por el saldo financiado
- `MovimientoCaja` = no debe existir por el saldo financiado

### 3. Venta credito con anticipo

- `Venta.total` = total comercial de la venta
- `Venta.tipo_venta` = `credito`
- `PagoVenta` = solo por el anticipo
- `CuentaPorCobrar` = solo por el saldo pendiente
- `MovimientoCaja` = solo por lo cobrado al momento en medios que correspondan

### 4. Venta credito en cuotas con interes

- `Venta.total` = valor comercial base de la venta
- `PlanCreditoVenta.monto_total_financiado` = capital financiado
- `PlanCreditoVenta.monto_total_interes` = interes total
- `PlanCreditoVenta.monto_total_con_interes` = total final a cobrar
- `CuentaPorCobrar.saldo_pendiente` = deuda real vigente del plan

Importante:

- el interes no debe reemplazar el valor de `Venta.total`;
- el interes debe vivir en el plan financiero y en las cobranzas;
- caja no debe tomar deuda futura como si fuera ingreso del dia.

## Definiciones oficiales que deben usarse en todo el sistema

Para evitar ambiguedad, normalizar estas definiciones:

### Venta emitida

Monto de la operacion comercial registrada.

- fuente principal: `Venta.total`
- incluye contado y credito
- no implica que el dinero haya ingresado

### Cobro inmediato

Monto cobrado en el momento de registrar la venta.

- fuente principal: `PagoVenta`
- puede ser `0` en ventas a credito

### Cobro de credito

Monto cobrado despues de haberse creado la cuenta por cobrar.

- fuente principal: `PagoCuentaCobrar`

### Saldo financiado

Monto pendiente de pago de una venta a credito.

- fuente principal: `CuentaPorCobrar.saldo_pendiente`

### Interes financiero

Costo financiero agregado al plan en cuotas.

- fuente principal: `PlanCreditoVenta.monto_total_interes`

## Problemas observados a corregir

### A. Historial y detalle de ventas

Sintoma:

- una venta a credito parece contado o no queda claramente identificada.

Correccion:

- mostrar siempre `tipo_venta`;
- mostrar `cobrado_al_momento`;
- mostrar `saldo_pendiente`;
- si hay plan en cuotas, mostrar `modo_credito`, `interes_total` y `total_financiado`;
- no usar solo estado `completada` como indicador de cobro.

Texto sugerido:

- `Estado de venta`: completada / anulada
- `Estado de cobro`: pendiente / parcial / pagada
- `Tipo de venta`: contado / credito

### B. Caja y cierre de caja

Sintoma:

- riesgo de mezclar venta emitida con dinero efectivamente cobrado.

Correccion:

- caja y cierre deben trabajar con:
  - `PagoVenta` para cobros inmediatos;
  - `PagoCuentaCobrar` para cobros posteriores;
  - `MovimientoCaja` para efectivo real.
- nunca usar `Venta.total` como dinero ingresado en caja.

### C. Contabilidad del rango

Sintoma:

- el reporte puede mezclar ventas cobradas, ventas emitidas y cobros de credito.

Correccion:

- separar secciones:
  - `Ventas emitidas`
  - `Cobrado en ventas`
  - `Cobros de creditos`
  - `Cuentas por cobrar generadas`
  - `Interes financiero generado`
- renombrar etiquetas donde hoy "ventas" en realidad significa "cobrado".

### D. Dashboard e inteligencia comercial

Sintoma:

- algunas metricas usan `Venta.total`, lo cual puede ser correcto para facturacion, pero incorrecto para caja.

Correccion:

- si la card dice "Facturacion" o "Ventas emitidas", puede usar `Venta.total`;
- si la card dice "Ingresos" o "Cobrado", debe usar pagos/cobros reales;
- separar metrica comercial de metrica de caja.

### E. Perfil e historial del cliente

Sintoma:

- el cliente puede aparecer con compras correctas, pero sin distinguir si fueron al contado o a credito.

Correccion:

- en historial del cliente mostrar:
  - tipo de venta
  - total venta
  - cobrado al momento
  - saldo pendiente
- agregar acceso al detalle de cuenta por cobrar si aplica.

## Cambios concretos por modulo

## Fase 1. UI de historial y detalle de venta

Archivos a revisar:

- `app/templates/ventas/detalle.html`
- `app/routes/ventas/parte4.py`
- cualquier listado/historial que muestre ventas sin `tipo_venta`

Acciones:

1. Mostrar `tipo_venta` de forma visible.
2. Mostrar `estado de cobro` separado del `estado de venta`.
3. Si `tipo_venta == credito`, mostrar:
   - anticipo/cobrado al momento
   - saldo pendiente
   - cuenta por cobrar asociada
   - plan de cuotas si existe
4. Si hay interes, mostrarlo separado del total base.

## Fase 2. Normalizacion de metricas

Crear una capa comun de metricas o helpers para no repetir logica contradictoria.

Objetivo:

- un helper para `ventas emitidas`
- un helper para `cobros inmediatos`
- un helper para `cobros de creditos`
- un helper para `saldo de cuentas por cobrar`

Beneficio:

- dashboard, reportes, historial vendedor, contabilidad e inteligencia usan la misma definicion.

## Fase 3. Corregir contabilidad y caja

Archivos a revisar:

- `app/routes/caja/common.py`
- `app/routes/caja/contabilidad_report.py`
- `app/models/caja.py`

Acciones:

1. Revisar nombres de conceptos para que no confundan venta con cobro.
2. Mantener `cierre de caja` basado en dinero real.
3. En `contabilidad`, separar claramente:
   - facturacion
   - cobros inmediatos
   - cobros de credito
   - egresos
4. Evitar que `total_ventas` signifique una cosa en una pantalla y otra en otra.

## Fase 4. Corregir dashboard, clientes e inteligencia

Archivos a revisar:

- `app/routes/main.py`
- `app/routes/clientes.py`
- `app/routes/reportes.py`
- `app/services/inteligencia/comercial.py`
- `app/services/inteligencia/ventas.py`
- `app/services/inteligencia/clientes.py`

Acciones:

1. Donde se quiera medir actividad comercial, usar `Venta.total`.
2. Donde se quiera medir ingresos reales, usar pagos y cobros.
3. En cliente, agregar visibilidad de credito vs contado.
4. Ajustar labels para que no digan "ventas" si en realidad son "cobros".

## Fase 5. Validaciones y pruebas

Agregar o actualizar tests para cubrir estos casos:

1. venta contado total
2. venta credito sin anticipo
3. venta credito con anticipo
4. venta credito en cuotas sin interes
5. venta credito en cuotas con interes
6. cobro posterior parcial
7. cobro posterior total
8. anulacion de venta contado
9. anulacion de venta credito
10. cierre de caja con mezcla de contado y credito
11. reporte contable que diferencie:
    - ventas emitidas
    - cobrado en ventas
    - cobros de creditos

## Criterios de aceptacion

Se considera corregido cuando:

1. una venta a credito ya no se ve como contado en historial ni en detalle;
2. el detalle de venta muestra claramente:
   - tipo de venta
   - cobrado al momento
   - saldo pendiente
   - interes financiero si aplica;
3. el cierre de caja no suma deuda futura como ingreso;
4. contabilidad separa facturacion de cobros;
5. dashboard y reportes usan nombres coherentes con la metrica mostrada;
6. el historial del cliente permite distinguir compras contado y credito;
7. las pruebas cubren contado, credito simple, credito mixto y cuotas con interes.

## Orden recomendado de implementacion

1. Corregir primero UI de historial/detalle de venta.
2. Crear helpers comunes de metricas.
3. Corregir caja y contabilidad.
4. Corregir dashboard, clientes, reportes e inteligencia.
5. Agregar pruebas de regresion.

## Nota importante de negocio

No cambiar esta regla:

- `Venta.total` debe seguir representando la venta comercial.

Y respetar esta separacion:

- venta comercial != dinero cobrado hoy
- saldo financiado != ingreso de caja
- interes financiero != precio base del producto

Si se mantiene esta separacion en todas las pantallas y reportes, la venta a credito va a quedar correctamente registrada y ya no va a parecer una venta contado.
