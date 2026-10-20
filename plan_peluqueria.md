# Plan de Mejoras: Peluquería / Barbería

## Objetivo

Dejar el módulo de peluquería/barbería listo para el primer cliente real: que un dueño o recepcionista pueda dar turnos, atenderlos y cobrarlos sin capacitación, y que la caja cuadre.

Hoy la base funciona (turno → servicio del cliente → venta → caja, con tests verdes), pero:

- hay 4 errores que afectan dinero o datos,
- el alta de turno usa conceptos técnicos ("base cobrable", "vinculado", "variante", "precio manual"),
- falta una agenda visual por profesional y acciones básicas (empezar, terminar, cobrar).

Ningún cliente usa todavía este módulo. Todos los clientes actuales usan **modo gastronomía**, que no se puede romper.

---

## Reglas de protección del modo gastronomía

Valen para **todas** las fases. Si un cambio no puede cumplirlas, se frena y se replantea.

1. **Carpetas intocables:** no se modifica nada dentro de `gastronomia/` ni de `tienda_online/`.
2. **Zona de trabajo:** los cambios viven en
   - `app/routes/agenda/peluqueria*.py` y archivos nuevos `app/routes/agenda/peluqueria_*.py`,
   - `app/services/agenda_turnos_peluqueria*.py` y servicios nuevos `app/services/peluqueria_*.py`,
   - `app/templates/agenda/peluqueria_*.html` y `app/templates/dashboard/components/servicios_*.html`,
   - `app/services/dashboard_servicios.py`, `dashboard_agenda.py`, `dashboard_preferences.py` (solo los usa el dashboard de servicios; gastronomía redirige antes en `main.dashboard`).
3. **Archivos compartidos** (ventas, caja, POS, `layout.html`, `login.html`, modelos): solo se tocan si la fase lo indica explícitamente, con cambios **aditivos** (parámetros opcionales, ramas nuevas) y con el comportamiento actual intacto cuando el dato nuevo no viene.
4. **Base de datos:** columnas nuevas siempre `nullable=True` o con `default`. No se renombran ni se cambian valores existentes (por ejemplo, el estado `cancelada` de `AgendaActividad` sigue igual).
5. **Configuración:** claves nuevas en `Configuracion` con prefijo `peluqueria_` y un valor por defecto que reproduce el comportamiento actual.
6. **Límite de 600 líneas por archivo** (AGENTS.md). Si un archivo se acerca, se divide antes de seguir.
7. **Tests de protección** antes y después de cada fase (ver abajo). Si algo de gastronomía falla, la fase no se cierra.

### Batería de tests de protección

```bash
.venv/Scripts/python.exe -m pytest -q test_gastronomia_*.py test_pos_*.py test_caja_*.py test_ventas_*.py test_cobranzas_*.py test_tienda_*.py
```

### Batería de tests del módulo

```bash
.venv/Scripts/python.exe -m pytest -q test_agenda_*.py test_dashboard_servicios*.py test_dashboard_agenda_resumen.py test_cliente_servicios_ventas.py
```

---

## Fase 0 — Red de seguridad

**Objetivo:** tener una línea base medida antes de cambiar nada.

- Correr las dos baterías y guardar el resultado (cantidad de tests, tiempo).
- Agregar `test_peluqueria_no_afecta_gastronomia.py` con pruebas de humo:
  - con modo `gastronomia`, `/` sigue redirigiendo a `gastronomia.dashboard`;
  - las rutas de peluquería no cambian la configuración de gastronomía;
  - el título y el login en modo gastronomía siguen mostrando "Sistema de Gestión Gastronómica".
- Dejar una configuración `revision-peluqueria` en `.claude/launch.json` (ya existe) para probar con una copia de la base en modo `servicios` + dashboard `peluqueria_barberia`.

**Terminado cuando:** las dos baterías pasan y el test de humo existe y pasa.

---

## Fase 1 — Errores que afectan dinero o datos

**Objetivo:** que nada quede mal registrado.

### 1.1 Turnos sin cliente que quedan pendientes para siempre
- En `crear_turno_peluqueria`, incluir `agenda_turno_actividad_id` en los parámetros que van al POS (la actividad ya existe en ese momento).
- En `_build_turno_redirect_pos_params`, aceptar `actividad_id` como parámetro opcional.
- En `obtener_resumen_cobros_pendientes_dashboard` de `dashboard_servicios.py`, incluir citas con `cliente_id` nulo, mostrándolas como "Consumidor final" (hoy `int(actividad.cliente_id)` explotaría con nulo: armar los parámetros solo si existe).
- Tests: crear y cobrar sin cliente → la actividad queda `hecha` con `venta_id`; la cita sin cliente aparece en cobros pendientes.

### 1.2 Se pierde lo cargado cuando el horario está ocupado
- Cambiar los errores de validación de `crear_turno_peluqueria` para que **vuelvan a renderizar** el formulario con los valores enviados (profesional, servicio, variante, cliente, fecha, hora, observaciones) en lugar de `redirect`.
- Pasar esos valores iniciales al componente Alpine (`peluqueriaTurnoRapido(config)` acepta un objeto `inicial`).
- Tests: un turno que choca devuelve 200 con el mensaje y los valores cargados.

### 1.3 La seña no entra a la caja
- Reutilizar el patrón ya aprobado en reparaciones (`_registrar_movimiento_abono_reparacion` en `app/routes/reparaciones/base.py`): extraer la parte común a un servicio compartido (`app/services/caja_senas.py`) **sin cambiar** el comportamiento de reparaciones.
- Nueva columna `AgendaActividad.sena_monto` (`Numeric`, nullable).
- Registrar la seña: `MovimientoCaja` tipo `ingreso`, `referencia_tipo='turno_sena'`, en la sesión abierta del operador. Sin caja abierta → mensaje claro, no se registra.
- Al cobrar el turno en el POS, descontar la seña del total (mismo criterio que el abono de reparación: abono + saldo = total, sin doble conteo). Se pasa como dato opcional en `agenda_turno_*`; si no viene, el POS se comporta igual que hoy.
- Si el turno se cancela con seña, mostrar la opción de **devolver la seña** (egreso) o **dejarla como ingreso** (seña perdida), a elección del usuario.
- Usar el filtro `|moneda` / `formato_moneda_local()` en lugar de "Gs." fijo.
- Tests: seña → movimiento de caja; cobro descuenta la seña; cancelación con devolución genera egreso; reparaciones sigue pasando `test_reparaciones_pago_estado.py`.
- ⚠️ Fase con archivos compartidos (caja y POS): correr la batería de protección completa.

### 1.4 Comisiones inventadas en el dashboard
- Ocultar la tarjeta "Comisiones del día" (quitarla de `_SERVICE_CARD_DEFINITIONS`) hasta que exista el cálculo real (Fase 6).
- Tests: la tarjeta no aparece en el dashboard de servicios.

**Terminado cuando:** los 4 puntos tienen test, las dos baterías pasan y se probó en pantalla: turno sin cliente cobrado, choque de horario, seña con arqueo de caja.

---

## Fase 2 — Alta de turno simple

**Objetivo:** dar un turno en 3 toques: profesional → servicio → hora.

### 2.1 Botones con los servicios del catálogo
- Los botones del paso "Servicio" pasan a ser los **servicios activos del catálogo**, con su nombre, precio y `duracion_minutos`.
- `turno_rapido_tipo` queda solo para ícono y color (opcional). Los 7 botones fijos solo aparecen si el catálogo está vacío, con un aviso: "Cargá tus servicios para verlos acá" y un enlace a Servicios.
- Si el servicio tiene variantes (`ServicioPrecioOpcion`), se elige con un segundo toque en el mismo lugar (sin modal).
- El precio manual queda detrás de un enlace "Cambiar precio".
- Desaparecen de la pantalla los textos "Vinculado", "Sin vincular al catálogo", "Base cobrable".
- Dividir `_peluqueria_turno_rapido_js.html` (537 líneas): separar los estilos de color en un archivo aparte.

### 2.2 Horarios ocupados visibles
- Nuevo endpoint `GET /agenda/api/peluqueria/ocupados?profesional_id=&fecha=` que devuelve los rangos ocupados (reusa `_buscar_turno_solapado`).
- En la grilla de horas, mostrar ocupados en gris/tachados y no seleccionables; recalcular al cambiar profesional, fecha o duración.
- Ocultar horas pasadas cuando la fecha es hoy.

### 2.3 Horario del local configurable
- Claves `peluqueria_hora_apertura` (default `08:00`), `peluqueria_hora_cierre` (default `21:00`), `peluqueria_intervalo_minutos` (default `30`).
- Reemplazan la constante `HORARIOS_TURNO_PELUQUERIA`.
- Pantalla simple para editarlas dentro de la configuración del negocio.

### 2.4 Volver a un lugar útil
- Después de crear el turno, volver al dashboard de peluquería (o a la agenda del día de la Fase 3, cuando exista), no a "Actividades".

**Terminado cuando:** un usuario nuevo da un turno sin ver términos técnicos, no puede elegir una hora ocupada, y los tests del módulo pasan.

---

## Fase 3 — Agenda del día por profesional

**Objetivo:** una vista tipo "planilla de recepción".

- Nueva pantalla `/agenda/peluqueria/dia?fecha=`: una columna por profesional, horas hacia abajo según el horario configurado, turnos como bloques con cliente, servicio y estado.
- Tocar un hueco libre abre el alta de turno con profesional, fecha y hora ya cargados.
- Tocar un turno abre "Gestionar turno".
- Flechas día anterior / siguiente y botón "Hoy".
- Corregir el "Mapa del día" del dashboard: los turnos cobrados se muestran como "Finalizado / Cobrado" en lugar de desaparecer (quitar el filtro `venta_id IS NULL` del turnero y usar `actividad.venta_id` para `cobrado`).
- Los botones "Agenda" del dashboard de peluquería apuntan a esta vista.
- Dividir `app/templates/agenda/lista.html` (922 líneas) en parciales, sin cambiar su comportamiento, para cumplir el límite de 600.

**Terminado cuando:** desde la agenda del día se puede ver, crear y abrir cualquier turno, y la lista de actividades genérica sigue funcionando igual.

---

## Fase 4 — Gestión del turno de punta a punta

**Objetivo:** cada turno se mueve con botones claros: Agendado → En atención → Terminado → Cobrado.

- En "Gestionar turno" agregar **Empezar atención**, **Terminar** y **Cobrar** (abre el POS con el turno, la seña y el profesional como vendedor).
- Funciona también para turnos sin cliente (hoy "En atención" depende de tener `cliente_servicio`).
- No-show como dato real: nueva columna `AgendaActividad.cierre_motivo` (nullable: `cancelado` / `no_show`). El estado sigue siendo `cancelada`; el turnero lee `cierre_motivo` en lugar de buscar "no-show" en el texto de las notas.
- No permitir cancelar un turno ya cobrado (hoy se puede).
- Botón "Avisar por WhatsApp" que abre `wa.me` con un mensaje armado (confirmación o recordatorio); no envía nada automáticamente.

**Terminado cuando:** un turno se puede llevar de principio a fin solo con botones y el dashboard muestra los estados correctos.

---

## Fase 5 — Equipo y presentación

**Objetivo:** que el sistema "se vea" de peluquería y muestre a las personas correctas.

- Nueva columna `Usuario.atiende_clientes` (Boolean, nullable). Si nadie está marcado, se muestran todos (comportamiento actual). Si hay alguno marcado, solo esos aparecen como profesionales en turnos, agenda y dashboard.
- Checkbox "Atiende clientes" en el formulario de usuario.
- Marca según el modo: en `layout.html` y `login.html`, el texto por defecto depende del modo y del dashboard activo. Prioridad: `app_brand_name` → texto del rubro → texto actual. En modo gastronomía el resultado tiene que ser **exactamente** el de hoy (lo cubre el test de humo de la Fase 0).
- Dashboard de peluquería con 3 acciones principales (**Nuevo turno**, **Agenda de hoy**, **Cobrar**); "Cargar servicio", "Servicios y costos" y "Cliente nuevo" pasan a un menú "Más".

**Terminado cuando:** en una instalación de peluquería no aparece "Gastronómica" en ningún lado, solo figuran los profesionales marcados, y el test de humo de gastronomía sigue pasando.

---

## Fase 6 — Comisiones y recordatorios (valor agregado)

### 6.1 Comisiones reales por profesional
- Porcentaje de comisión por profesional (columna nullable en `Usuario` o tabla propia `peluqueria_comision`), con opción de porcentaje distinto por servicio más adelante.
- Cálculo sobre las líneas de servicio de ventas completadas donde `id_usuario_vendedor` es el profesional, excluyendo anuladas y devoluciones.
- Tarjeta "Comisiones del día" vuelve al dashboard con datos reales, y un reporte por rango de fechas para liquidar.

### 6.2 Recordatorios automáticos por WhatsApp
- Solo si el cliente tiene WhatsApp Cloud API configurado; si no, se mantiene el botón manual de la Fase 4.
- Clave `peluqueria_recordatorio_horas_antes` (default vacío = desactivado).
- Reutilizar los servicios de WhatsApp existentes; no crear un cliente nuevo de la API.

**Terminado cuando:** el dueño puede ver cuánto le corresponde a cada barbero en un rango de fechas y los recordatorios salen solos cuando están activados.

---

## Orden y tamaño estimado

| Fase | Contenido | Riesgo para gastronomía | Tamaño |
|------|-----------|-------------------------|--------|
| 0 | Red de seguridad | Ninguno | Chico |
| 1 | Errores de dinero/datos | **Medio** (1.3 toca caja y POS) | Mediano |
| 2 | Alta de turno simple | Bajo | Mediano |
| 3 | Agenda del día | Bajo | Mediano |
| 4 | Gestión del turno | Bajo | Mediano |
| 5 | Equipo y marca | **Medio** (layout y login compartidos) | Chico |
| 6 | Comisiones y recordatorios | Bajo | Grande |

Las fases 2, 3 y 4 son independientes entre sí una vez cerrada la Fase 1. Para el primer cliente de peluquería alcanza con las fases 0 a 4.

---

## Registro de avance

### Fase 0 — hecha (2026-10-19)
- Línea base: 405 tests de protección + módulo, todos verdes.
- `test_peluqueria_no_afecta_gastronomia.py`: redirección a gastronomía, marca en login y layout, crear turno no cambia el modo, migraciones sin claves duplicadas y columna nueva agregada a bases existentes.

### Fase 1 — hecha (2026-10-19)
- 1.1 Turnos sin cliente: el POS recibe el turno y lo marca cobrado; aparecen en Cobros pendientes con el profesional como vendedor. El POS ahora carga el turno aunque no traiga servicio ni cliente.
- 1.2 Choque de horario: el formulario vuelve con todo lo cargado (`_peluqueria_turno_rapido_inicial_js.html`).
- 1.3 Seña: entra a caja (`turno_sena`), se guarda en `AgendaActividad.sena_monto`, se descuenta sola en el POS, y al cancelar o marcar no-show se elige devolverla o retenerla. No se puede cancelar un turno cobrado. Lógica común con reparaciones en `app/services/caja_senas.py`.
- 1.4 Tarjeta "Comisiones del día" quitada hasta la Fase 6.
- Errores extra encontrados al probar en pantalla:
  - `schema.py` tenía la clave `agenda_actividades` duplicada: la segunda pisaba a la primera y sus columnas nunca se migraban. Unificada.
  - Los formularios de "Gestionar turno" no tenían `action`; dentro de las pestañas de la app se enviaban a `/` y fallaban.
  - Los campos de seña y precio manual tenían `step="1000"` con `min="1"`: el navegador rechazaba montos redondos (10.000, 20.000…).
- Resultado: 463 tests verdes (gastronomía, POS, caja, ventas, cobranzas, tienda, reparaciones, agenda, dashboard, peluquería).
- Pendiente fuera de alcance: el campo "precio de venta" del producto rápido del POS (`ventas/pos_html/ui_pos_principal.html`) tiene el mismo problema de `step="1000"`; es compartido con otros modos y no se tocó.

### Fase 2 — hecha (2026-10-19)
- 2.1 Los botones del paso "Servicio" son los servicios activos del catálogo (nombre, precio con `formato_moneda_local`, duración), armados en `app/services/peluqueria_turno_catalogo.py`. Las variantes se eligen en el mismo lugar, sin modal. El precio manual quedó detrás de "Cambiar precio". Con catálogo vacío aparecen los 7 botones fijos y el aviso "Cargá tus servicios para verlos acá". Se quitaron "Vinculado", "Sin vincular al catálogo", "Base cobrable" y el selector "Servicio base a cobrar".
- `_peluqueria_turno_rapido_js.html` bajó de 538 a 305 líneas: los colores y estilos pasaron a `_peluqueria_turno_rapido_estilos_js.html`.
- 2.2 `GET /agenda/api/peluqueria/ocupados` devuelve los rangos ocupados del profesional en el día. La consulta de solapamiento se movió a `query_turnos_solapados` (`app/services/peluqueria_horario.py`) y la usan tanto este endpoint como la validación del alta y la reprogramación. En la grilla, las horas ocupadas salen tachadas y no se pueden elegir según la duración elegida, las pasadas de hoy se ocultan, y se recalcula al cambiar de profesional, fecha o duración.
- 2.3 Claves `peluqueria_hora_apertura`, `peluqueria_hora_cierre` y `peluqueria_intervalo_minutos`. Por defecto reproducen el horario anterior (08:00 a 20:30, cada 30 min) y un valor inválido vuelve al default. Pantalla `/agenda/turnos/peluqueria/horario` (solo admin), con enlace "Horario del local" desde el alta de turno. No se agregó a "Módulos del sistema" porque esa pantalla es solo para root.
- 2.4 Después de crear el turno se vuelve al dashboard (`main.dashboard`) en lugar de "Actividades".
- Aviso de CSS: `style.css` está precompilado y su `tailwind.config.js` no escanea `gastronomia/templates`. Recompilarlo podría borrar clases de gastronomía, así que no se recompiló: las pantallas nuevas usan solo clases que ya existen, más un `<style>` propio para el selector de intervalo.
- Resultado: 76 tests del módulo (13 nuevos en `test_peluqueria_fase2.py`) y 356 de protección, todos verdes. Probado en pantalla: servicio con variantes, hora ocupada bloqueada, choque forzado que vuelve con servicio y variante cargados, y cambio de horario reflejado en la grilla.

### Fase 3 — hecha (2026-10-19)
- Nueva pantalla `/agenda/peluqueria/dia?fecha=` (`app/routes/agenda/peluqueria_agenda_dia.py`, `app/services/peluqueria_agenda_dia.py`, `agenda/peluqueria_agenda_dia.html`). Tiene una columna por profesional visible y filas según el horario del local; la grilla se amplía si hay turnos fuera de horario. Cada turno es un bloque del alto de su duración, con cliente, servicio y estado. Muestra una línea de "ahora" en el día actual y las flechas día anterior/siguiente, "Hoy" y selector de fecha.
- Al tocar un hueco libre se abre el alta con profesional, fecha y hora cargados (`/agenda/turnos/peluqueria/nuevo?profesional_id=&fecha=&hora=`). No se ofrecen huecos ya pasados ni días anteriores. Al tocar un turno se abre "Gestionar turno". Cancelados y no-show van en una lista aparte y dejan libre el hueco.
- Después de crear un turno se vuelve a la agenda de ese día (cierra el punto 2.4).
- Mapa del día: se quitó el filtro `venta_id IS NULL`. Ahora los turnos cobrados se muestran como "Cobrado" (usa `actividad.venta_id` o la venta del servicio del cliente). La serialización quedó en `serializar_turno_peluqueria` (`dashboard_agenda.py`) y la comparte con la agenda del día.
- Los botones "Agenda" y "Ver agenda completa" del dashboard de peluquería apuntan a la agenda del día; en el dashboard de servicios genérico siguen yendo a la agenda de siempre. El acceso "Agenda" del menú lateral no se tocó porque es compartido.
- `agenda/lista.html` pasó de 922 a 259 líneas. El JS se movió tal cual a `_lista_js.html` (523) y las funciones puras a `_lista_helpers_js.html` (`window.AgendaListaHelpers`). Probado en pantalla: alertas de vencida y sincronización por polling funcionan igual.
- Nota: para revisar si una clase de Tailwind está compilada hay que mirar también dentro de los `@media` (las clases `sm:`, `md:` y `lg:` viven ahí).

### Fase 4 — hecha (2026-10-19)
- Estados del turno en `app/services/peluqueria_turno_estado.py`: Agendado → En atención → Terminado → Cobrado, más Cancelado y No-show. "Gestionar turno" muestra la barra de pasos y los botones **Empezar atención**, **Terminar** y **Cobrar** (`_peluqueria_turno_estado.html`). La ruta pasó a `app/routes/agenda/peluqueria_gestion.py`, con acciones chicas en lugar de un solo bloque de if/elif.
- Columnas nuevas en `AgendaActividad`, todas nulables:
  - `atencion_inicio`: permite "En atención" sin servicio del cliente, o sea sin cliente.
  - `cierre_motivo` (`cancelado` / `no_show`): el no-show ya no se busca en el texto de las notas, salvo en turnos viejos sin motivo.
  - `servicio_id` y `servicio_precio_opcion_id`: guardan el servicio elegido para cobrar después un turno sin cliente.
- Cobrar (`/agenda/turnos/peluqueria/<id>/cobrar`):
  - Con servicio del cliente usa `cliente_servicio_id`. El POS ahora también recibe al profesional como vendedor (`profesional_para_cobro`, cambio aditivo en `clientes_servicios.py` y `pos_state_runtime.js`).
  - Sin cliente pasa turno, servicio y profesional. Los turnos viejos se resuelven por título, igual que Cobros pendientes.
  - En los dos casos la seña se descuenta sola.
- Terminado sin cobrar sigue en Cobros pendientes. No se puede reprogramar un turno en atención o atendido, ni cancelar uno terminado o cobrado.
- El contador "En atención" del dashboard cuenta también los turnos sin cliente, y su botón Cobrar en peluquería usa la ruta nueva. El "Iniciar" genérico de agenda también marca `atencion_inicio` en citas.
- `_sincronizar_cliente_servicio_desde_actividad` pasó de `routes/agenda/formularios.py` a `app/services/agenda_cliente_servicio_sync.py` sin cambiar su lógica.
- WhatsApp: botones "Confirmar turno" y "Recordar turno" que abren `wa.me` con el mensaje armado. El teléfono se normaliza con `app/utils/phone_utils.normalizar_telefono`. No se envía nada automáticamente; si el cliente no tiene teléfono, se pide cargarlo.
- Mapa del día y agenda del día muestran "Terminado" (ámbar) aparte de "Cobrado".

### Fase 5 — hecha (2026-10-19)
- `Usuario.atiende_clientes` (Boolean, nulable). Se marca con el checkbox "Atiende clientes" en alta y edición de usuario, que solo se muestra en instalaciones de servicios; si el formulario no trae el campo, el valor no se toca.
- `app/services/peluqueria_profesionales.py`: si nadie está marcado aparecen todos; si hay marcados activos, solo esos figuran en el alta de turno, la agenda del día, los horarios ocupados y la tarjeta de profesionales del dashboard de servicios. Quien solo maneja su propia agenda se sigue viendo a sí mismo.
- Marca según el rubro (`app/services/marca_rubro.py`, expuesta como `marca_rubro` en el contexto de las plantillas):
  - Gastronomía: las plantillas conservan su markup original en una rama `if`. Una comparación byte a byte de login, gastronomía, usuarios y agenda entre HEAD y el código nuevo dio idéntico, salvo tokens y relojes.
  - Servicios: el título usa el nombre de la empresa y, si no hay, el texto del rubro ("Sistema de Gestión para Peluquería y Barbería" o "Sistema de Gestión de Servicios"). La barra superior dice "Peluquería · Barbería" o "Servicios" y el login usa el texto del rubro.
  - También se cubrieron los títulos de respaldo en JS de las pestañas.
- La marca toma el modo y el dashboard del mapa de configuración que el runtime ya lee en una sola consulta (`modo_operacion_principal` y `dashboard_negocio_activo` se agregaron a esas claves), así que no suma consultas por página (`test_agenda_perf`).
- Dashboard de peluquería: 3 acciones a la vista (**Nuevo turno**, **Agenda de hoy**, **Cobrar**) y un menú "Más" con `<details>`: Cargar servicio, Servicios y costos, Cliente nuevo y Horario del local. Los botones se movieron a `dashboard/components/servicios_acciones.html`; el dashboard de servicios genérico conserva su bloque tal cual.
- Nota para tests: `g` se comparte entre requests cuando la clase deja el contexto de app abierto. Las cachés nuevas usan `request.environ`, y el test limpia `g._runtime_ui_config` después de cambiar la configuración.

### Fase 6 — hecha (2026-10-19)
- 6.1 Comisiones:
  - `Usuario.comision_porcentaje` (Numeric, nulable), editable en el formulario de usuario junto a "Atiende clientes".
  - Cálculo en `app/services/peluqueria_comisiones.py`: líneas de servicio de ventas completadas por vendedor (subtotal con descuento de línea), menos lo devuelto de cada línea (devoluciones no anuladas). Las anuladas no cuentan. Sin porcentaje la comisión es 0 y se avisa; no se inventa nada.
  - Reporte por rango `/agenda/peluqueria/comisiones` (admin o `ver_reporte_ventas`) con rangos rápidos: hoy, semana, mes y mes anterior.
  - La tarjeta "Comisiones del día" volvió al dashboard con datos reales (`servicios_comisiones.html`) y hay un acceso en el menú "Más".
  - El descuento global de la venta no se prorratea en la base; queda para cuando se pida.
  - Comisión distinta por servicio: todavía no.
- 6.2 Recordatorios automáticos por WhatsApp (`app/services/peluqueria_recordatorios.py`):
  - Claves `peluqueria_recordatorio_horas_antes` (vacío = desactivado) y `peluqueria_recordatorio_template`.
  - Solo actúa si WhatsApp Cloud API está configurado. Reutiliza `app/services/whatsapp/client.py` (`enviar_texto` / `enviar_template`) y el mismo texto que el botón manual (`texto_mensaje_turno`).
  - Un intento por turno (`AgendaActividad.recordatorio_whatsapp_at`, se limpia al reprogramar). Salta los turnos cancelados, en atención, cobrados o sin teléfono.
  - Job en segundo plano `app/bootstrap/peluqueria_recordatorios_scheduler.py`, igual que el de facturación electrónica: cada 5 min (`PELUQUERIA_RECORDATORIOS_INTERVAL_SECONDS`), se apaga con `PELUQUERIA_RECORDATORIOS_SCHEDULER=0` y no corre en tests.
  - Se configura en la pantalla "Horario del local", que avisa si WhatsApp no está configurado.
  - Importante: sin plantilla aprobada por Meta, WhatsApp solo entrega texto a quien escribió en las últimas 24 h. Para que llegue a todos hay que crear la plantilla con 4 variables (nombre, servicio, fecha y hora, profesional) y cargar su nombre.
- Arreglado aparte: `errores/403.html` no existía, así que Agenda, CRM y WhatsApp daban un error 500 en lugar de un 403 a quien no tenía permiso. Ahora existe la plantilla, recibe el `mensaje` de cada módulo y lo cubre `test_agenda_sin_permiso_403.py`.
