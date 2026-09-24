# Porte del módulo desde `sistema_silvio_cel`

El módulo `facturacion_electronica/` de este repo es una **copia del sistema
padre** (`sistema_con_whats/sistema_silvio_cel`). Se mantiene lo más idéntico
posible para poder resincronizarlo copiando la carpeta.

## Snapshot

| Parte | Commit del padre | Fecha |
|---|---|---|
| `facturacion_electronica/` completo (núcleo, motor propio, KuDE, NC, guardas, envío automático, capa API) | `c807628a` | 2026-09-24 |
| `sifen_service/` (index.js, package.json, README, deploy, test_bases_gravadas.js) | `c807628a` | 2026-09-24 |
| `app/utils/unidades_venta.py`, `app/services/caja_transacciones.py` | `c807628a` | 2026-09-24 |
| `app/templates/ventas/_facturacion_electronica.html` | `c807628a` | 2026-09-24 |
| Tests `test_facturacion_electronica_*.py` | `c807628a` | 2026-09-24 |

La capa API (`services/proveedores/api*.py`, `routes_api.py`) se copió como
está, pero **en el padre todavía está en pruebas**. El proveedor por defecto es
`propio`; no seleccionar "API externa" en producción hasta resincronizar.

## Divergencias locales (re-aplicar después de cada resincronización)

1. `services/data_builder.py` — `_codigo_y_descripcion()`: los platos de
   gastronomía y los servicios son `DetalleVenta` con `id_servicio` y sin
   producto; el ítem toma código (`SRV-<id>` si no tiene) y nombre del servicio.
2. `services/nota_credito.py` — las líneas de NC llevan
   `servicio=getattr(detalle, 'servicio', None)` para que el punto anterior
   funcione también en la nota de crédito.
3. `services/data_builder.py` — `_descuento_unitario()`: cada línea declara
   exactamente su `subtotal`. El POS y la caja gastronómica de servicios
   aplican promociones guardando `precio_unitario` ya rebajado **y** el
   descuento en `descuento_linea` (informativo); el padre restaba ese descuento
   otra vez y el DE salía por menos de lo cobrado. En el padre no pasa porque su
   POS no carga `descuento_linea`. Tests en
   `test_facturacion_electronica_promociones_servicios.py`; además el helper
   `_detalle` de `test_facturacion_electronica_data_builder.py` arma
   `subtotal = cantidad × precio − descuento` (re-aplicar al copiar ese test).

Todo lo demás propio de servicios vive **fuera** del módulo:

- `app/bootstrap/fe_schema.py` — migraciones de esquema de FE (en el padre
  están en `schema.py` / `schema_migrations.py`).
- `app/bootstrap/fe_scheduler.py` — job de envío automático (en el padre está
  en `runtime.py`).
- `app/services/fe_anulacion.py` — guarda que impide anular una venta con DE
  vigente (ventas y gastronomía).
- `app/services/fe_venta_contexto.py` — panel de FE en el detalle de venta.
- `gastronomia/services/factura_electronica_service.py`,
  `gastronomia/static/js/caja_factura.js`,
  `gastronomia/templates/gastronomia/_caja_factura_electronica.html` —
  checkbox, cliente de la factura y emisión desde la caja gastronómica.

## Cómo resincronizar

```bash
# en el padre: qué cambió desde el snapshot
git -C ../sistema_con_whats/sistema_silvio_cel diff c807628a..HEAD --stat -- facturacion_electronica sifen_service
```

1. Copiar la carpeta del padre encima (sin `CLIENTE_*.md` ni certificados/claves
   de `sifen_service`).
2. Re-aplicar las tres divergencias de arriba.
3. Si el padre agregó columnas, sumarlas a `_FE_COLUMNAS` en
   `app/bootstrap/fe_schema.py`.
4. Copiar los tests nuevos y correr `pytest test_facturacion_electronica_*.py
   test_gastronomia_factura_electronica.py`.
5. Actualizar la tabla de snapshot con el commit nuevo.
6. En el servidor: `cd sifen_service && npm install` si cambió `package.json`.
