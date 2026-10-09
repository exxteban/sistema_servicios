# Porte del módulo desde `sistema_silvio_cel`

El módulo `facturacion_electronica/` de este repo es una **copia del sistema
padre** (`sistema_con_whats/sistema_silvio_cel`). Se mantiene lo más idéntico
posible para poder resincronizarlo copiando la carpeta.

## Snapshot

| Parte | Commit del padre | Fecha |
|---|---|---|
| `facturacion_electronica/` completo (núcleo, motor propio, KuDE, NC, guardas, envío automático, capa API) | `62a78acc` | 2026-10-08 |
| `sifen_service/` (index.js, package.json, README, deploy, test_bases_gravadas.js) | `62a78acc` | 2026-10-08 |
| `app/utils/unidades_venta.py`, `app/services/caja_transacciones.py` | `d70e957b` | 2026-10-01 |
| `app/templates/ventas/_facturacion_electronica.html` | `d70e957b` | 2026-10-01 |
| Tests `test_facturacion_electronica_*.py` | `62a78acc` | 2026-10-08 |

Resincronizado el 2026-10-08 (antes: `d70e957b`). Trajo: envío por lotes del
motor propio (siRecepLoteDE + consulta a los 10 min, respaldo por CDC; en
producción siempre por lote; el modo vive en la tabla `configuracion`, sin
columnas nuevas), cada documento lo sigue sólo el proveedor que lo transmitió
(`proveedores/pertenencia.py`), reintentar emisión no le pasa a la API una
factura del motor propio, certificado/CSC/timbrado de la API por ambiente y
KuDE al ancho de papel del ticket (`ticket_paper_width_mm`). Ninguna divergencia
local se tocó.

Resincronización anterior el 2026-10-02 (antes: `c807628a`). Trajo: refactor de
`emision_service` (envío, eventos, generación, NC y respuesta SIFEN en archivos
propios), corregir y reenviar rechazadas, reintentar emisión, retransmisión,
NC por API (con el receptor que declaró la factura y el descuento global
prorrateado), redondeo SEDECO en la API, datos fiscales del emisor y
`emission_readiness`, 409 `fiscal_number_conflict`, tabla geográfica de la SET
renovada sola y la pantalla "Facturas electrónicas". El proveedor por defecto
sigue siendo `propio`.

`routes.py` viene del padre con 623 líneas (pasa el límite de 600 de AGENTS.md);
se deja igual para no abrir una divergencia: partirlo primero en el padre.

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
- `app/services/fe_venta_contexto.py` — panel de FE en el detalle de venta y
  `datos_fe_modal` (número, estado, rechazo y reimprimir KuDE en el modal del
  Historial y del reporte del día; en el padre está en `reportes.detalle_venta`).
- `app/utils/modulos.py` — adaptador `_modulo_activo` que importan
  `routes_documentos` y `acciones` (en el padre tiene además los guards de
  módulos).
- `app/bootstrap/fe_scheduler.py` corre `tareas_periodicas.ejecutar`;
  `app/__init__.py` importa `routes_api`, `routes_documentos` y `routes_geo`.
- `app/templates/layout/_fe_menu_links.html` — Configuración y "Facturas
  electrónicas" (esta última también con `ver_reportes`).
- `gastronomia/services/factura_electronica_service.py`,
  `gastronomia/static/js/caja_factura.js`,
  `gastronomia/templates/gastronomia/_caja_factura_electronica.html` —
  checkbox, cliente de la factura y emisión desde la caja gastronómica. En modo
  API el pre-chequeo antes de cobrar corre también `validar_receptor_api`.

## Cómo resincronizar

```bash
# en el padre: qué cambió desde el snapshot
git -C ../sistema_con_whats/sistema_silvio_cel diff 62a78acc..HEAD --stat -- facturacion_electronica sifen_service
```

1. Copiar la carpeta del padre encima (sin `CLIENTE_*.md`, `DIAGNOSTICO_*.md`,
   `REVISION_*.md` ni certificados/claves de `sifen_service`). Para no perder
   las divergencias, `git merge-file` local / snapshot / HEAD del padre.
2. Re-aplicar las tres divergencias de arriba. Revisar si el padre importa
   algo nuevo de `app.*` que acá no exista (así apareció `app/utils/modulos.py`).
3. Si el padre agregó columnas, sumarlas a `_FE_COLUMNAS` en
   `app/bootstrap/fe_schema.py`.
4. Copiar los tests nuevos y correr `pytest test_facturacion_electronica_*.py
   test_gastronomia_factura_electronica.py`.
5. Actualizar la tabla de snapshot con el commit nuevo.
6. En el servidor: `cd sifen_service && npm install` si cambió `package.json`.
