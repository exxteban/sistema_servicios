# Plan — Envío a SIFEN, KuDE y flujo POS

Plan de las fases que faltan para emitir facturas electrónicas **de verdad**,
una vez que se cuente con el certificado digital real y la habilitación de la
DNIT. El motor (generar, firmar, guardar) ya está hecho y probado.

> Regla base (AGENTS.md): instalación por negocio, **no multi-tenant**. El
> módulo es aislado y apagado por defecto. El flujo de venta actual **no se
> toca** salvo agregar la opción de facturar.

---

## 1. Estado actual (hecho y probado)

- **Configuración del emisor** (RUC, timbrado, establecimiento/punto, actividad,
  geo con selector en cascada de la tabla oficial SIFEN).
- **Certificado .p12** con contraseña **cifrada** (Fernet, derivada del SECRET_KEY).
- **Generación del XML** vía microservicio Node (TIPS `xmlgen`), con datos reales:
  cliente contribuyente/consumidor final, IVA 10/5/exento, unidades de medida,
  métodos de pago.
- **CDC** calculado y persistido (modelo `DocumentoElectronico`, un DE por venta).
- **Firma** vía TIPS `xmlsign` (endpoint `/firmar` en el servicio Node).
- Todo accesible hoy de forma **manual** desde la pantalla "Vista previa".

Servicio Node: `sifen_service/` (systemd `sifen-service`, puerto 3010).
Estados del documento: `generado → firmado → enviado → aprobado/rechazado`
(`cancelado`, `error`).

---

## 2. Flujo de negocio acordado

La factura es **a elección del cliente**:

- **No quiere factura** → flujo **idéntico al actual** (ticket normal, sin cambios).
- **Sí quiere factura** → al cobrar se marca "Emitir factura electrónica":
  - Receptor: cliente con **RUC** → a su nombre; sin RUC → **Consumidor Final**.
  - Generar → firmar → **enviar a SIFEN**.
  - Imprimir el **KuDE con QR** (en lugar del ticket común).
  - **Enviar por correo** si el cliente lo pide y tiene email (opcional).

El **CDC se calcula antes de enviar**, así el KuDE se imprime al instante y el
envío/aprobación de SIFEN corre por detrás (POS no espera).

---

## 3. Fases pendientes

### Fase 4 — Envío a SIFEN (`setapi`) — requiere certificado real
- Agregar `facturacionelectronicapy-setapi` al servicio Node.
- Endpoints: `siRecepDE` (síncrono, 1 DE) y/o `siRecepLoteDE` (lote async).
- Mutual TLS con el certificado real (por eso no se puede probar antes).
- Guardar respuesta en `DocumentoElectronico`: `estado`, `respuesta_codigo`,
  `respuesta_mensaje`, `protocolo_autorizacion`, `fecha_envio`.
- **Alerta de fecha (regla ~72 h)**: bloquear/avisar al emitir documentos viejos
  (va acá, en el envío, no antes).
- Consulta de estado: `siConsDE` / `siResultLoteDE` para lotes.
- Empezar SIEMPRE en ambiente **test** (`sifen-test`) antes de producción.

### Fase 5 — Integración con el POS
- Opción **"Emitir factura electrónica"** en el cobro (default: off → ticket normal).
- Capturar/confirmar receptor: usar el cliente seleccionado (su `ruc_ci`) o
  Consumidor Final. Confirmar email si se va a enviar.
- Al confirmar cobro con la opción marcada: `generar_documento` → `firmar_documento`
  → enviar (Fase 4). El camino sin factura no llama a nada de esto.
- Manejo de errores amable: si SIFEN falla, no romper la venta (imprimir + reintentar).
- Decisión cosmética a definir: check del cajero vs botón "Facturar".

### Fase 6 — KuDE (representación gráfica) + QR
- `facturacionelectronicapy-qrgen`: el QR necesita el **XML firmado** + el **CSC**
  (real, de la DNIT) + IdCSC. Sin CSC real el QR no es válido (para maqueta sirve dummy).
- `facturacionelectronicapy-kude` (o plantilla propia): PDF/ticket con los datos
  del DE, CDC en grupos de 4, y el QR.
- Formato cinta (80 mm) para la impresora térmica actual; formato carta opcional.
- Reemplaza/ amplía el ticket actual cuando la venta es facturada.

### Fase 7 — Envío por correo (opcional)
- Adjuntar XML firmado (DTE) + KuDE (PDF) y enviar al email del cliente.
- Solo si el cliente lo pide y tiene email cargado.

---

## 4. Pendientes menores del motor (no bloquean)
- Detalle de **cuotas** en ventas a crédito (hoy va como "plazo 30 días").
- Más tipos de documento: **Nota de Crédito / Débito**, Autofactura.
- `unidadMedida` para bolsa/caja/rollo cae a Unidad (SIFEN no las tipifica).

---

## 5. Qué necesita el certificado real (resumen)
- Firmar válido para SIFEN (hoy probado con `.p12` autofirmado).
- Enviar (mutual TLS) — Fase 4.
- QR válido (junto con el CSC de la DNIT) — Fase 6.

Todo lo demás (motor, POS salvo el envío, layout del KuDE) se puede preparar
antes; se valida de punta a punta recién con el certificado y la habilitación.
