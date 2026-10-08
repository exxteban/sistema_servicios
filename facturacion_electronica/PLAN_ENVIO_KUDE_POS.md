# Plan — Envío a SIFEN, KuDE y flujo POS

Plan de las fases que faltan para emitir facturas electrónicas **de verdad**,
una vez que se cuente con el certificado digital real y la habilitación de la
DNIT. El motor (generar, firmar, guardar) ya está hecho y probado.

> Regla base (AGENTS.md): instalación por negocio, **no multi-tenant**. El
> módulo es aislado y apagado por defecto. El flujo de venta actual **no se
> toca** salvo agregar la opción de facturar.

---

## 1. Estado actual

> La foto completa y honesta está en la **sección 4 (CHECKLIST DE ESTADO)** al final.
> Resumen: el circuito interno (config → generar → firmar → QR → KuDE) y la
> integración POS están hechos y probados; el **envío a SIFEN está cableado pero
> sin probar** (necesita cert real); falta correo, NC/ND y cuotas.

- **Configuración del emisor** (RUC, timbrado, establecimiento/punto, actividad,
  geo con selector en cascada de la tabla oficial SIFEN).
- **Certificado .p12** con contraseña **cifrada** (Fernet, derivada del SECRET_KEY).
- **Generación del XML** vía microservicio Node (TIPS `xmlgen`), con datos reales:
  cliente contribuyente/consumidor final, IVA 10/5/exento, unidades de medida,
  métodos de pago.
- **CDC** calculado y persistido (modelo `DocumentoElectronico`, un DE por venta).
- **Firma** vía TIPS `xmlsign` (endpoint `/firmar` en el servicio Node).
- **QR + KuDE** imprimible (Fase 6) e **integración con el POS** (Fase 5, checkbox
  opt-in que no toca el flujo de venta actual).
- **Envío a SIFEN** (Fase 4) y consulta de estado: **código escrito, sin probar**.
- Accesible de forma **manual** desde la pantalla "Vista previa" y, para el cajero,
  desde el checkbox del cobro.

Servicio Node: `sifen_service/` (systemd `sifen-service`, puerto 3010). Endpoints:
`/generar`, `/firmar`, `/qr`, `/enviar`, `/consultar`, `/cancelar`.
Estados del documento: `generado → firmado → enviado → aprobado/rechazado`
(`cancelado`, `error`).

**Numeración correlativa (clave SIFEN):** el número del DE lo lleva el emisor,
correlativo por establecimiento+punto dentro del rango del timbrado (SIFEN NO lo
genera). Tabla `facturacion_electronica_secuencia` (`SecuenciaNumeracionDE`,
clave única establecimiento+punto) + `services/numeracion_service.py`
(`reservar_numero` atómico, `peek_proximo_numero` para la vista previa). El número
se reserva una vez por DE y es estable entre regeneraciones. **NO** deriva de
`venta.numero_factura` (eso es una factura externa que el cajero registra, sin
relación con el DE). OJO al ir a producción: si ya se emitió con ese timbrado por
otro medio, setear el `ultimo_numero` inicial de la secuencia.

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

## 2.b Decisión estratégica (caminos y costos)

Dos formas de emitir, **una por RUC** (no se usan las dos a la vez):

- **e-Kuatia'i** (portal web gratis de la DNIT): para pequeños contribuyentes
  (1 establecimiento, 1 punto). Emitís en la web de la DNIT, **a mano**, no desde
  un sistema propio. La DNIT da un certificado gratis, pero lo más probable es
  que sea **solo para su portal** (a confirmar con la DNIT).
- **e-Kuatia** (sistema propio, lo que construimos): emitís desde tu POS.
  Requiere **certificado real de un PSC** (tipo F1). **No hay "certificado de
  prueba" barato**: es **uno solo**, sirve para test y producción, ~1 año de
  validez. El autofirmado **no** conecta a SIFEN (sólo sirvió para probar el
  circuito interno).

**Decisión tomada:**
- **Negocio propio (py systems, contribuyente chico):** usar **e-Kuatia'i** (gratis).
- **El sistema integrado:** es el **producto para clientes** que quieran FE en su
  POS. Cada cliente trae **su** certificado.
- **Prueba real contra SIFEN:** se hace con el **primer cliente real** que tenga
  certificado (o si el dueño decide usar su propio sistema en producción). No se
  compra un certificado sólo para "probar".

## 2.c Prerrequisitos del contribuyente (Paso 0, lado DNIT)

Para cada negocio que vaya a emitir desde el sistema (camino e-Kuatia):
1. **RUC activo** (reactivar si está en suspensión — con el contador).
2. **Habilitación como facturador electrónico** (no se registra el software; se
   habilita el RUC). Guía "Habilitación como Facturador Electrónico".
3. **Certificado** F1 de un PSC (a nombre del RUC; persona física es válido).
4. **Timbrado electrónico** (8 dígitos). Guía "Generar Timbrado".
5. **Establecimiento/punto** (001/001). Guía correspondiente.
6. **CSC + IdCSC**. Guía "Solicitud de CSC".
7. **Etapa de pruebas**: emitir el set de documentos de la "Guía de Pruebas" en
   el ambiente test; al pasar, la DNIT habilita producción.

## 2.d Qué se puede avanzar YA (sin certificado real)

Lo único bloqueado por el certificado es el **envío real a SIFEN** (Fase 4).
Todo lo demás se puede construir y probar ahora:
- **Fase 6 (KuDE + QR)** con un CSC de prueba — el comprobante imprimible. Es lo
  que hace al sistema **demoable/vendible** a un cliente. ← siguiente paso sugerido.
- **Fase 5 (POS)** hasta generar + firmar (el envío queda stub hasta el cert).
- Más **tipos de documento** (NC/ND) y **cuotas de crédito**.
- El **código del envío** (Fase 4) se puede dejar escrito; sólo no se puede
  *probar* contra SIFEN hasta tener el certificado.

---

## 3. Fases pendientes

### Fase 4 — Envío a SIFEN (`setapi`) — ✅ CABLEADA (no probada: requiere cert real)
- `facturacionelectronicapy-setapi` agregado al servicio Node: `POST /enviar`
  (`recibe`/siRecepDE síncrono) y `POST /consultar` (`consulta`/siConsDE por CDC).
- Cliente `sifen_client.enviar_de()` / `consultar_de()` (`_post_json`, timeout 100s).
- `emision_service.enviar_documento(doc)`: chequea la ventana de **72 h** (avisa,
  no envía si el DE es viejo), envía `xml_qr or xml_firmado`, interpreta la
  respuesta (`_interpretar_respuesta` busca `dCodRes`/`dMsgRes`/`dProtAut`/`dEstRes`
  de forma defensiva) y guarda `estado` (enviado/aprobado/rechazado/error),
  `respuesta_codigo`, `respuesta_mensaje`, `protocolo_autorizacion`, `fecha_envio`.
  `consultar_documento(doc)` consulta por CDC.
- Rutas `POST /enviar/<id>` y `POST /consultar/<id>` + botones en la vista previa.
- Ambiente: `config.ambiente` ('produccion'→'prod', resto→'test'). Empezar SIEMPRE
  en **test** antes de producción.
- **No probado end-to-end**: el TLS mutuo necesita el certificado real habilitado.
  La estructura exacta del SOAP de respuesta se confirma recién contra el ambiente
  real (por eso `_interpretar_respuesta` es defensivo).
- Lote async (`recibeLote`/`consultaLote`): HECHO el 2026-10-03 como opción
  "Modo de envío" de la configuración (síncrono por defecto). Un DE por lote;
  el job consulta el lote en cada pasada. Ver `services/envio_lote.py`.

### Fase 5 — Integración con el POS — ✅ HECHA (hasta KuDE; el envío a SIFEN queda para Fase 4)
- Checkbox **"Emitir factura electrónica"** en el modal de vista previa del cobro,
  **default OFF**, opt-in por venta. Solo visible si el módulo está activo Y la
  config está COMPLETA (`facturacion_electronica_lista` en `_render_pos_interface`).
- Al confirmar con el check marcado: `emitir_para_pos(venta)` (generar→firmar→qr)
  vía `POST /facturacion-electronica/emitir-pos/<id>` y abre el KuDE. Sin marcar →
  `imprimirTicketVenta()` (ticket de siempre, sin cambios).
- **No rompe la venta**: la FE corre DESPUÉS de registrar la venta; si falla, avisa
  y cae al ticket normal. Tres candados: feature-flag OFF + módulo aislado + paso
  posterior a la venta. "No quiero factura"/"así no más" = no marcar el checkbox.
- PENDIENTE: el envío real a SIFEN (Fase 4) — hoy llega hasta firmar+QR+KuDE.

### Fase 6 — KuDE (representación gráfica) + QR — ✅ HECHA (con CSC de maqueta)
- `facturacionelectronicapy-qrgen` en el servicio Node (`POST /qr`): el QR necesita
  el **XML firmado** + el **CSC** (real, de la DNIT) + IdCSC. Sin CSC real el QR no
  es válido; se usa `CSC_DEMO`/`CSC_DEMO_ID` para la maqueta.
- Plantilla **propia** (no se usó `facturacionelectronicapy-kude`): template térmico
  80 mm `templates/facturacion_electronica/kude.html`, con los datos del DE, CDC en
  grupos de 4 y el QR (renderizado con `segno`).
- Servicios: `services/qr.py` (extrae la URL del QR + PNG data-uri) y
  `services/kude_service.py` (contexto + liquidación de IVA IVA-incluido).
- Columnas nuevas en `DocumentoElectronico`: `xml_qr`, `qr_url` (migración en
  `app/bootstrap/schema.py`). Rutas `POST /qr/<venta_id>` y `GET /kude/<venta_id>`.
- Formato cinta (80/58 mm); reemplaza/amplía el ticket cuando la venta es facturada.
- Integrado al POS en la Fase 5. PENDIENTE: formato carta (A4) opcional.

### Fase 7 — Envío por correo (opcional)
- Adjuntar XML firmado (DTE) + KuDE (PDF) y enviar al email del cliente.
- Solo si el cliente lo pide y tiene email cargado.

### Fase 8 — Cancelación + re-facturación — ✅ CABLEADA (no probada: requiere cert real)
- **Cancelación = evento SIFEN** (siRecepEvento, `tipoEvento=1`), NO es lo mismo que
  anular la venta interna. Servicio Node `POST /cancelar`
  (`generateXMLEventoCancelacion` + `signXMLEvento` + `setapi.evento`). Cliente
  `sifen_client.cancelar_de()` (devuelve respuesta + xml firmado del evento).
- `emision_service.cancelar_documento(doc, motivo)`: exige estado **aprobado**,
  motivo **5-500 chars**, plazo **48 h** (`HORAS_LIMITE_CANCELACION`; pasado eso
  avisa que corresponde nota de crédito). Guarda `estado='cancelado'`,
  `motivo_cancelacion`, `xml_cancelacion`, `fecha_cancelado` (columnas nuevas +
  migración). Ruta `POST /cancelar/<venta_id>` + form con motivo en la vista previa.
- **Re-facturación:** el DE dejó de ser único por venta. `id_venta` ya **no es
  unique** (migración convierte el índice UNIQUE histórico en común, idempotente,
  sqlite+mysql, validada simulando BD vieja). El **DE vigente = el de mayor id**
  (`obtener_documento` ordena desc). Tras cancelar, `generar_documento` crea un DE
  **nuevo** (número correlativo nuevo) conservando el cancelado para auditoría.
- **Orquestación anular venta** (`app/routes/ventas/parte4.py`): guarda mínima y
  aditiva — bloquea anular una venta con DE vigente (`aprobado`/`enviado`) pidiendo
  cancelar la factura primero, para no dejar un ingreso declarado inexistente. No
  toca la lógica de reversa (stock/caja/cuentas).
- Tests: `test_facturacion_electronica_cancelacion.py` (validaciones),
  `test_facturacion_electronica_refacturacion.py` (multi-DE en BD real),
  `test_facturacion_electronica_numeracion.py` (secuencia correlativa).
- **Sin probar contra SIFEN**: la interpretación de la respuesta del evento usa el
  mismo `_interpretar_respuesta` defensivo; se afina con el SOAP real.

---

## 4. CHECKLIST DE ESTADO (la foto honesta)

### ✅ Hecho y probado (corrió end-to-end + tests, 39 verdes)
- [x] Configuración del emisor (RUC, timbrado, geo en cascada, actividad).
- [x] Certificado `.p12` con contraseña cifrada (Fernet derivada del SECRET_KEY).
- [x] Generar XML del DE + cálculo del CDC (modelo `DocumentoElectronico`).
- [x] Firmar XML (`xmlsign`, probado con `.p12` autofirmado).
- [x] QR (`qrgen`) + KuDE imprimible (template térmico 80/58 mm, QR con `segno`).
- [x] Integración POS: checkbox opt-in, default OFF, no rompe el flujo de venta.
- [x] Liquidación de IVA del KuDE (IVA-incluido: /11 y /21).

### ⚠️ Construido pero SIN PROBAR contra SIFEN (puede requerir ajustes reales, no solo typos)
- [ ] **Envío a SIFEN** (`/enviar`, siRecepDE) — nunca tocó SIFEN. Riesgos concretos:
  - [ ] **Lectura de la respuesta**: `_interpretar_respuesta` busca los campos por
        nombre (`dCodRes`/`dMsgRes`/`dProtAut`/`dEstRes`) sin asumir el árbol del
        SOAP. Hay que afinar contra una respuesta real.
  - [ ] **QR vs firma**: `qrgen` rearma el XML y eso PUEDE invalidar la firma. Hoy
        se envía `xml_qr or xml_firmado`; con el cert real hay que confirmar cuál
        acepta SIFEN. **Punto más delicado.**
  - [ ] **TLS mutuo**: confirmar que el `.p12` real conecta.
- [ ] **Consulta de estado** (`/consultar`, siConsDE) — mismo caso, sin probar.
      Ya actualiza el estado del documento (aprobado/rechazado) con la respuesta.
- [ ] **Cancelación** (`/cancelar`, evento siRecepEvento) — Fase 8, cableada sin
      probar. Re-facturación (multi-DE por venta) sí probada en BD.
- [ ] **Encadenar el envío al POS**: hoy `emitir_para_pos` llega hasta QR+KuDE; el
      envío es un paso aparte (botón en vista previa) hasta validar la Fase 4.

### ❌ Falta construir (pospuesto a propósito)
- [ ] **Correo (Fase 7)**: adjuntar XML firmado + KuDE (PDF) y enviar al cliente.
      No empezado.
- [ ] **Nota de Crédito / Débito** y **autofactura**: hoy solo emite Factura
      (`tipoDocumento=1`).
- [ ] **Detalle de cuotas** en venta a crédito: hoy va como "plazo 30 días" fijo.
- [ ] **KuDE formato carta** (A4) opcional, además del térmico.
- [x] Lote async (`recibeLote`/`consultaLote`) e **inutilización** de números
      reservados nunca emitidos (huecos de numeración). La **cancelación** ya está
      cableada (Fase 8); inutilización sigue pendiente.
- [ ] `unidadMedida` para bolsa/caja/rollo cae a Unidad (SIFEN no las tipifica) —
      aceptable, anotado.

### 🔑 Formato del certificado
- El sistema usa **PKCS#12**: `.p12` y `.pfx` (son el MISMO formato, distinta
  extensión — un archivo con cert + clave privada + contraseña). **Ambos aceptados**
  (`EXTENSIONES_CERT` en `config_service.py`); firma y envío usan ese archivo.
- **PEM** (cert y clave en archivos separados `.cer`/`.crt` + `.key`) **NO está
  soportado** hoy. Los PSC de Paraguay casi siempre entregan `.p12`. Si aparece PEM:
  - Conversión rápida: `openssl pkcs12 -export -inkey clave.key -in cert.cer -out cert.p12`
  - O agregar soporte directo (cambio chico en el servicio de firma).

### 📋 Trámite (lado DNIT, no es código)
- [ ] RUC activo y habilitado como **facturador electrónico**.
- [ ] **Certificado** F1 de un PSC (a nombre del RUC).
- [ ] **Timbrado electrónico** (8 dígitos) + establecimiento/punto (001/001).
- [ ] **CSC + IdCSC** (sin esto el QR no es válido; hoy usa CSC de maqueta).
- [ ] **Etapa de pruebas DNIT**: emitir el set de la "Guía de Pruebas" en ambiente
      test; al pasar, la DNIT habilita producción.

---

## 5. Qué desbloquea el certificado real
- Firma válida para SIFEN (hoy solo probada con `.p12` autofirmado).
- Envío (TLS mutuo) — Fase 4, hoy a ciegas.
- QR válido (con el CSC real de la DNIT) — hoy con CSC de maqueta.

**Resumen honesto:** el camino feliz de una **factura de contado** está completo y,
con el cert, debería andar con ajustes menores. Pero NO es "solo falta el cert": la
Fase 4 (envío) tiene dos puntos que recién se validan contra SIFEN real (lectura de
respuesta y QR-vs-firma), y quedan features sin hacer (correo, NC/ND, cuotas). Si los
clientes solo necesitan factura de contado al inicio, está muy cerca; NC/ND o cuotas
son trabajo nuevo.
