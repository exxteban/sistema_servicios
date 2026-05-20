"""
Base de conocimiento de ayuda funcional del sistema.
Responde preguntas sobre como usar el sistema, donde esta cada opcion y como hacer tareas comunes.
Sin llamadas a la API: cero tokens extra.
"""

AYUDA_KB = [
    {
        "claves": ["agregar usuario", "nuevo usuario", "crear usuario", "alta usuario", "como agrego un usuario", "como creo un usuario"],
        "respuesta": (
            "Para agregar un usuario nuevo:\n"
            "1. Ir al menu Directorio > Usuarios.\n"
            "2. Hacer clic en el boton Nuevo usuario.\n"
            "3. Completar nombre, email, contrasena y asignar un rol.\n"
            "4. Guardar.\n"
            "Requiere el permiso gestionar_usuarios. Solo admin o root pueden hacerlo."
        ),
    },
    {
        "claves": ["cambiar permiso", "modificar permiso", "editar permiso", "asignar permiso", "quitar permiso", "como cambio permisos", "como asigno permisos"],
        "respuesta": (
            "Para cambiar permisos de un usuario:\n"
            "1. Ir al menu Directorio > Usuarios.\n"
            "2. Abrir el usuario que queres modificar.\n"
            "3. Cambiar el rol asignado o editar los permisos individuales.\n"
            "Para gestionar roles y sus permisos: menu Sistema > Roles.\n"
            "Requiere ser admin o tener el permiso gestionar_roles."
        ),
    },
    {
        "claves": ["ver ventas", "donde estan las ventas", "donde veo las ventas", "historial de ventas", "listado de ventas", "como veo las ventas"],
        "respuesta": (
            "Para ver las ventas:\n"
            "- Ventas del dia y listado general: menu Operaciones > Punto de Venta, o desde el dashboard.\n"
            "- Historial completo: menu Sistema > Reportes > Ventas diarias.\n"
            "- Analisis por periodo, categoria o vendedor: menu Sistema > Inteligencia.\n"
            "Requiere el permiso ver_ventas o ver_reportes segun la vista."
        ),
    },
    {
        "claves": ["abrir caja", "como abro la caja", "iniciar caja", "apertura de caja"],
        "respuesta": (
            "Para abrir la caja:\n"
            "1. Ir al menu Operaciones > Caja Actual.\n"
            "2. Si no hay sesion activa, aparece el boton Abrir caja.\n"
            "3. Ingresar el monto inicial y confirmar.\n"
            "Requiere el permiso ver_caja. Solo puede haber una sesion activa por caja."
        ),
    },
    {
        "claves": ["cerrar caja", "como cierro la caja", "cierre de caja", "hacer cierre"],
        "respuesta": (
            "Para cerrar la caja:\n"
            "1. Ir al menu Operaciones > Caja Actual.\n"
            "2. Revisar los movimientos del dia.\n"
            "3. Hacer clic en Cerrar caja.\n"
            "4. Ingresar el monto declarado y confirmar.\n"
            "El sistema calcula la diferencia entre lo esperado y lo declarado.\n"
            "Requiere el permiso ver_caja."
        ),
    },
    {
        "claves": ["ver cierres", "historial de cierres", "cierres anteriores", "donde veo los cierres"],
        "respuesta": (
            "Para ver cierres anteriores:\n"
            "- Ir al menu Operaciones > Cierres.\n"
            "- Ahi se listan todos los cierres con fecha, diferencia y estado.\n"
            "- Hacer clic en un cierre para ver el detalle completo.\n"
            "Requiere el permiso ver_caja."
        ),
    },
    {
        "claves": ["agregar producto", "nuevo producto", "crear producto", "alta de producto", "como agrego un producto"],
        "respuesta": (
            "Para agregar un producto:\n"
            "1. Ir al menu Logistica > Productos.\n"
            "2. Hacer clic en Nuevo producto.\n"
            "3. Completar nombre, precio, costo, stock inicial y categoria.\n"
            "4. Guardar.\n"
            "Requiere el permiso crear_producto."
        ),
    },
    {
        "claves": ["ver stock", "consultar stock", "donde veo el stock", "stock de productos", "inventario de productos"],
        "respuesta": (
            "Para ver el stock:\n"
            "- Ir al menu Logistica > Productos.\n"
            "- La columna Stock muestra la cantidad disponible de cada producto.\n"
            "- Para un resumen de productos con stock bajo: menu Sistema > Reportes > Stock bajo.\n"
            "Requiere el permiso ver_inventario."
        ),
    },
    {
        "claves": ["registrar compra", "nueva compra", "cargar compra", "como registro una compra", "como cargo una compra"],
        "respuesta": (
            "Para registrar una compra a proveedor:\n"
            "1. Ir al menu Sistema > Compras.\n"
            "2. Hacer clic en Nueva compra.\n"
            "3. Seleccionar el proveedor, agregar los productos y montos.\n"
            "4. Guardar.\n"
            "El stock se actualiza automaticamente al confirmar la compra.\n"
            "Requiere el permiso crear_compra."
        ),
    },
    {
        "claves": ["agregar cliente", "nuevo cliente", "crear cliente", "alta de cliente", "como agrego un cliente"],
        "respuesta": (
            "Para agregar un cliente:\n"
            "1. Ir al menu Directorio > Clientes.\n"
            "2. Hacer clic en Nuevo cliente.\n"
            "3. Completar los datos de contacto y guardar.\n"
            "Requiere el permiso crear_cliente."
        ),
    },
    {
        "claves": ["ver clientes", "listado de clientes", "donde veo los clientes", "buscar cliente"],
        "respuesta": (
            "Para ver o buscar clientes:\n"
            "- Ir al menu Directorio > Clientes.\n"
            "- Usar el buscador para filtrar por nombre, telefono o email.\n"
            "- Hacer clic en un cliente para ver su ficha completa con historial.\n"
            "Requiere el permiso ver_clientes."
        ),
    },
    {
        "claves": ["registrar gasto", "nuevo gasto", "cargar gasto", "como registro un gasto", "como cargo un gasto"],
        "respuesta": (
            "Para registrar un gasto corriente:\n"
            "1. Ir al menu Operaciones > Gastos corrientes.\n"
            "2. Hacer clic en Nuevo gasto.\n"
            "3. Completar categoria, monto, fecha y descripcion.\n"
            "4. Guardar.\n"
            "Requiere el permiso crear_gasto_corriente."
        ),
    },
    {
        "claves": ["ver gastos", "listado de gastos", "donde veo los gastos", "gastos del mes"],
        "respuesta": (
            "Para ver los gastos corrientes:\n"
            "- Ir al menu Operaciones > Gastos corrientes.\n"
            "- Se listan con fecha, categoria y estado de pago.\n"
            "- Para reportes por periodo: menu Sistema > Reportes.\n"
            "Requiere el permiso ver_gastos_corrientes."
        ),
    },
    {
        "claves": ["registrar reparacion", "nueva reparacion", "ingresar equipo", "como registro una reparacion"],
        "respuesta": (
            "Para registrar una reparacion:\n"
            "1. Ir al menu Servicio Tecnico.\n"
            "2. Hacer clic en Nueva reparacion.\n"
            "3. Completar datos del equipo, problema reportado y cliente.\n"
            "4. Guardar.\n"
            "Requiere el permiso ver_reparaciones o crear_reparacion."
        ),
    },
    {
        "claves": ["ver reparaciones", "listado de reparaciones", "donde veo las reparaciones", "estado de reparaciones"],
        "respuesta": (
            "Para ver las reparaciones:\n"
            "- Ir al menu Servicio Tecnico.\n"
            "- Se listan con estado, tecnico asignado y fecha de ingreso.\n"
            "- Hacer clic en una reparacion para ver el detalle y actualizar el estado.\n"
            "Requiere el permiso ver_reparaciones."
        ),
    },
    {
        "claves": ["ver empleados", "listado de empleados", "donde veo los empleados", "control de empleados"],
        "respuesta": (
            "Para ver el control de empleados:\n"
            "- Ir al menu Control de Empleados (aparece si el modulo esta activado).\n"
            "- Ahi se gestionan fichas, ausencias, pagos y movimientos salariales.\n"
            "Si no aparece en el menu, el modulo puede estar desactivado.\n"
            "Activarlo: menu Directorio > Usuarios > Configuracion > Modulos.\n"
            "Requiere el permiso ver_control_empleados."
        ),
    },
    {
        "claves": ["registrar ausencia", "cargar ausencia", "como registro una ausencia", "ausencia de empleado"],
        "respuesta": (
            "Para registrar una ausencia:\n"
            "1. Ir al menu Control de Empleados.\n"
            "2. Abrir la ficha del empleado o ir a la seccion Ausencias.\n"
            "3. Registrar la ausencia con fecha, tipo y motivo.\n"
            "Requiere el permiso gestionar_ausencias o similar."
        ),
    },
    {
        "claves": ["ver cobranzas", "cuentas por cobrar", "donde veo las cobranzas", "clientes con deuda", "saldos pendientes"],
        "respuesta": (
            "Para ver cobranzas:\n"
            "- Ir al menu Cobranzas (aparece si el modulo esta activado).\n"
            "- Ahi se ven saldos pendientes, vencimientos y clientes morosos.\n"
            "Si no aparece, el modulo puede estar desactivado.\n"
            "Activarlo: menu Directorio > Usuarios > Configuracion > Modulos.\n"
            "Requiere el permiso ver_cobranzas."
        ),
    },
    {
        "claves": ["ver reportes", "donde estan los reportes", "como veo los reportes", "acceder a reportes"],
        "respuesta": (
            "Para ver los reportes:\n"
            "- Ir al menu Sistema > Reportes.\n"
            "- Desde ahi se accede a ventas diarias, historial de vendedores, stock bajo e inventario.\n"
            "- Para analisis mas avanzados: menu Sistema > Inteligencia.\n"
            "Requiere el permiso ver_reportes."
        ),
    },
    {
        "claves": ["configurar sistema", "configuracion del sistema", "donde esta la configuracion", "ajustes del sistema", "como configuro el sistema"],
        "respuesta": (
            "Para acceder a la configuracion del sistema:\n"
            "- Ir al menu Directorio > Usuarios > Configuracion.\n"
            "- Desde ahi se gestionan: datos del negocio, modulos activos, configuracion de IA, ticket de venta y mas.\n"
            "Solo el usuario root o admin puede modificar la mayoria de estos ajustes."
        ),
    },
    {
        "claves": ["activar modulo", "habilitar modulo", "como activo un modulo", "como habilito un modulo"],
        "respuesta": (
            "Para activar un modulo:\n"
            "1. Ir al menu Directorio > Usuarios > Configuracion.\n"
            "2. Buscar la seccion Modulos.\n"
            "3. Activar el modulo deseado (por ejemplo: Control de empleados, Cobranzas).\n"
            "4. Guardar.\n"
            "Solo el usuario root puede cambiar la activacion de modulos."
        ),
    },
    {
        "claves": ["ver agenda", "donde esta la agenda", "como uso la agenda", "actividades pendientes"],
        "respuesta": (
            "Para ver la agenda:\n"
            "- Hacer clic en el icono de Agenda en la barra superior, o ir al menu Agenda.\n"
            "- Ahi se ven actividades, turnos y compromisos pendientes.\n"
            "- Para agregar una actividad: boton Nueva actividad dentro de la agenda.\n"
            "Requiere el permiso agenda_acceso."
        ),
    },
    {
        "claves": ["ver pedidos", "listado de pedidos", "donde veo los pedidos", "como veo los pedidos"],
        "respuesta": (
            "Para ver los pedidos:\n"
            "- Ir al menu Operaciones > Pedidos.\n"
            "- Se listan con estado, cliente y fecha.\n"
            "- Hacer clic en un pedido para ver el detalle y gestionar el cobro.\n"
            "Requiere permisos de clientes o admin."
        ),
    },
    {
        "claves": ["ver proveedores", "listado de proveedores", "donde veo los proveedores", "agregar proveedor"],
        "respuesta": (
            "Para ver o agregar proveedores:\n"
            "- Ir al menu Logistica > Proveedores.\n"
            "- Para agregar uno nuevo: boton Nuevo proveedor.\n"
            "Requiere el permiso ver_proveedores o crear_proveedor."
        ),
    },
    {
        "claves": ["tienda online", "mi tienda", "como configuro la tienda", "donde esta la tienda", "catalogo web"],
        "respuesta": (
            "Para gestionar la tienda online:\n"
            "- Ir al menu Logistica > Mi Tienda Online.\n"
            "- Desde ahi se configura el catalogo, productos publicados, promociones y el bot web.\n"
            "- Los cambios en productos del sistema se reflejan en la tienda segun la configuracion de publicacion."
        ),
    },
    {
        "claves": ["whatsapp", "conversaciones whatsapp", "panel whatsapp", "mis conversaciones", "como veo whatsapp"],
        "respuesta": (
            "Para ver las conversaciones de WhatsApp:\n"
            "- Ir al menu WhatsApp > Mis Conversaciones.\n"
            "- Ahi se gestionan las conversaciones asignadas al usuario.\n"
            "- Para el monitor general y derivaciones: menu CRM WhatsApp.\n"
            "Requiere el permiso whatsapp_conversaciones."
        ),
    },
    {
        "claves": ["ver auditoria", "logs del sistema", "historial de cambios", "donde veo la auditoria"],
        "respuesta": (
            "Para ver la auditoria del sistema:\n"
            "- Ir al menu Sistema > Auditoria.\n"
            "- Se listan eventos y cambios registrados con usuario, fecha y detalle.\n"
            "Requiere el permiso ver_auditoria."
        ),
    },
    {
        "claves": ["cambiar contrasena", "cambiar password", "como cambio mi contrasena", "olvide mi contrasena"],
        "respuesta": (
            "Para cambiar la contrasena:\n"
            "- El propio usuario: ir al menu de perfil (icono de usuario arriba a la derecha) > Cambiar contrasena.\n"
            "- Un admin puede resetear la contrasena de otro usuario desde Directorio > Usuarios > editar usuario.\n"
            "No se puede recuperar una contrasena olvidada sin acceso de admin."
        ),
    },
    {
        "claves": ["hacer una venta", "registrar venta", "como vendo", "como hago una venta", "punto de venta", "pos"],
        "respuesta": (
            "Para registrar una venta:\n"
            "1. Ir al menu Operaciones > Punto de Venta.\n"
            "2. Buscar y agregar los productos.\n"
            "3. Seleccionar el metodo de pago.\n"
            "4. Confirmar la venta.\n"
            "El ticket se genera automaticamente. Requiere el permiso crear_venta y caja abierta."
        ),
    },
    {
        "claves": ["presupuesto empresarial", "cotizacion empresarial", "como hago un presupuesto", "donde estan los presupuestos"],
        "respuesta": (
            "Para gestionar presupuestos empresariales:\n"
            "- Ir al menu Logistica > Presupuestos empresariales.\n"
            "- Para crear uno nuevo: boton Nuevo presupuesto.\n"
            "- Desde ahi se arman cotizaciones formales, se imprimen y se hace seguimiento.\n"
            "Requiere permisos de presupuestos."
        ),
    },
    {
        "claves": ["compra de usados", "recepcion de usados", "como registro un usado", "donde estan los usados"],
        "respuesta": (
            "Para registrar la compra de un equipo usado:\n"
            "- Ir al menu Logistica > Compra de usados.\n"
            "- Hacer clic en Nueva recepcion.\n"
            "- Completar datos del equipo, condicion y operacion.\n"
            "Requiere el permiso ver_recepcion_usados o crear_recepcion_usados."
        ),
    },
    {
        "claves": ["inteligencia", "panel de inteligencia", "donde esta inteligencia", "bi", "analitica"],
        "respuesta": (
            "Para acceder al panel de Inteligencia:\n"
            "- Ir al menu Sistema > Inteligencia.\n"
            "- Ahi se ven alertas, comparaciones de periodos, oportunidades y resumen ejecutivo del negocio.\n"
            "Requiere el permiso ver_reportes."
        ),
    },
    {
        "claves": ["no aparece opcion", "no veo el menu", "no encuentro la opcion", "opcion desaparecio", "no tengo acceso"],
        "respuesta": (
            "Si una opcion del menu no aparece, revisar en este orden:\n"
            "1. Permisos del usuario: Directorio > Usuarios > editar usuario > revisar rol y permisos.\n"
            "2. Modulo activo: Directorio > Usuarios > Configuracion > Modulos.\n"
            "3. Rol asignado: el rol puede no incluir ese permiso. Revisar en Sistema > Roles.\n"
            "Si el problema persiste, contactar al usuario root o admin del sistema."
        ),
    },
    {
        "claves": ["que es el asistente ia", "para que sirve el asistente", "como uso el asistente", "ayuda del asistente"],
        "respuesta": (
            "El Asistente IA interno sirve para dos cosas:\n"
            "1. Consultar datos del negocio en lenguaje natural: ventas, caja, empleados, cobranzas, etc.\n"
            "2. Obtener ayuda sobre como usar el sistema: donde esta cada opcion, como hacer tareas comunes.\n"
            "Solo lectura: no modifica datos salvo que uses una accion asistida confirmada.\n"
            "Acceso: boton Asistente IA en la barra superior del sistema."
        ),
    },
]
