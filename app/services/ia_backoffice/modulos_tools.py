import re
import unicodedata

from app.models import Permiso


MODULE_REGISTRY = {
    'ventas': {
        'label': 'Ventas',
        'aliases': ('venta', 'ventas', 'pos'),
        'summary': 'Gestiona el registro de ventas, descuentos, credito y cierre comercial de cada operacion.',
        'flow': [
            'Se cargan productos, cantidades y condiciones de cobro.',
            'La venta puede pasar a caja o completarse segun el flujo habilitado.',
            'Queda historial para consulta, detalle y anulaciones autorizadas.',
        ],
    },
    'inventario': {
        'label': 'Inventario',
        'aliases': ('inventario', 'stock', 'productos', 'producto'),
        'summary': 'Centraliza productos, stock, precios, costos visibles y ajustes de mercaderia.',
        'flow': [
            'Se crean o editan productos y sus datos comerciales.',
            'El stock se mueve por compras, ventas, ajustes y otros procesos conectados.',
            'Desde ahi tambien se revisan faltantes, precios y disponibilidad.',
        ],
    },
    'compras': {
        'label': 'Compras',
        'aliases': ('compra', 'compras'),
        'summary': 'Sirve para registrar compras a proveedores, controlar costos y dejar trazabilidad de pagos.',
        'flow': [
            'Se carga la compra con proveedor, productos y montos.',
            'La recepcion impacta en stock y en la deuda con proveedor si corresponde.',
            'Luego se puede consultar, pagar o anular segun permisos.',
        ],
    },
    'caja': {
        'label': 'Caja',
        'aliases': ('caja', 'cierres', 'arqueo', 'cola de cobro'),
        'summary': 'Administra aperturas, cobros, movimientos, cola de cobro y cierres de caja.',
        'flow': [
            'Se abre una sesion de caja para operar.',
            'Ingresan ventas, reparaciones u otros movimientos segun el flujo del negocio.',
            'Al cierre se comparan sistema, declarado y diferencia.',
        ],
    },
    'clientes': {
        'label': 'Clientes',
        'aliases': ('cliente', 'clientes', 'directorio'),
        'summary': 'Reune la ficha comercial de cada cliente con datos de contacto, historial y relacion operativa.',
        'flow': [
            'Se da de alta o actualiza la ficha del cliente.',
            'La ficha se conecta con ventas, cobranzas, reparaciones y otros modulos relacionados.',
            'Desde ahi se consulta el estado general y antecedentes del cliente.',
        ],
    },
    'fidelizacion': {
        'label': 'Fidelizacion',
        'aliases': ('fidelizacion', 'fidelización', 'puntos', 'recompensas', 'canjes'),
        'summary': 'Automatiza beneficios por compras repetidas y mantiene el saldo de beneficios de cada cliente.',
        'flow': [
            'Las ventas validas acumulan compras para el cliente.',
            'Al cumplir la regla definida se liberan beneficios segun la configuracion activa.',
            'Los beneficios quedan disponibles para canje manual o uso en POS si aplica.',
        ],
    },
    'cobranzas': {
        'label': 'Cobranzas',
        'aliases': ('cobranza', 'cobranzas', 'cuentas por cobrar', 'morosos', 'creditos'),
        'summary': 'Controla cuentas por cobrar, vencimientos, cobros, promesas y seguimiento de deuda de clientes.',
        'flow': [
            'Se generan saldos pendientes desde ventas u operaciones a credito.',
            'El modulo muestra vencimientos, estados y clientes a seguir.',
            'Los cobros registrados actualizan el saldo y dejan historial.',
        ],
    },
    'gastos_corrientes': {
        'label': 'Gastos Corrientes',
        'aliases': ('gastos', 'gastos corrientes', 'egresos'),
        'summary': 'Organiza gastos operativos recurrentes, sus pagos y el seguimiento de vencimientos.',
        'flow': [
            'Se cargan gastos con categoria, monto y vencimiento.',
            'Luego se registran pagos o anulaciones segun permisos.',
            'El modulo ayuda a ver pendientes, vencidos y reportes.',
        ],
    },
    'reparaciones': {
        'label': 'Reparaciones',
        'aliases': ('reparacion', 'reparaciones', 'servicio tecnico', 'tecnico'),
        'summary': 'Administra la recepcion, seguimiento tecnico, costos y entrega de equipos en reparacion.',
        'flow': [
            'Se registra el ingreso del equipo y el problema reportado.',
            'Durante el proceso se actualizan estado, prioridad, costos y observaciones.',
            'Cuando corresponde, la reparacion puede pasar a cobro o vincularse con venta.',
        ],
    },
    'recepcion_usados': {
        'label': 'Compra de Usados',
        'aliases': ('usados', 'compra de usados', 'recepcion usados', 'recepcion de usados'),
        'summary': 'Sirve para registrar compras de equipos usados y dejar trazabilidad documental de la recepcion.',
        'flow': [
            'Se carga el equipo, su condicion y datos de la operacion.',
            'La recepcion queda asociada a la trazabilidad interna de usados.',
            'Luego puede conectarse con compras, stock o revision segun el flujo aplicado.',
        ],
    },
    'presupuestos_empresariales': {
        'label': 'Presupuestos Empresariales',
        'aliases': ('presupuestos', 'presupuestos empresariales', 'cotizaciones'),
        'summary': 'Permite armar cotizaciones formales para clientes empresa y seguir su estado comercial.',
        'flow': [
            'Se crea el presupuesto con items, condiciones y datos del cliente.',
            'Puede imprimirse o exportarse segun el flujo del area comercial.',
            'Despues se consulta para seguimiento, vigencia o conversion.',
        ],
    },
    'agenda': {
        'label': 'Agenda',
        'aliases': ('agenda', 'turnos', 'actividades'),
        'summary': 'Coordina actividades, turnos y seguimiento operativo de tareas agendadas.',
        'flow': [
            'Se crean actividades o turnos con fecha, responsable y estado.',
            'Cada item puede editarse, completarse o cancelarse segun permisos.',
            'La agenda ayuda a ordenar pendientes y proximos compromisos.',
        ],
    },
    'control_empleados': {
        'label': 'Control de Empleados',
        'aliases': ('empleados', 'control de empleados', 'salarios', 'ausencias'),
        'summary': 'Agrupa gestion de empleados, movimientos salariales, pagos y ausencias.',
        'flow': [
            'Se administra la ficha laboral y sus datos base.',
            'Se registran movimientos, pagos o ausencias segun el proceso habilitado.',
            'Luego se consulta el historial y los calculos asociados.',
        ],
    },
    'crm': {
        'label': 'CRM',
        'aliases': ('crm', 'crm whatsapp', 'asesor crm'),
        'summary': 'Centraliza seguimiento comercial y conversacional para atencion y reactivacion de clientes.',
        'flow': [
            'Se visualizan conversaciones o contactos pendientes.',
            'El asesor puede tomar casos y responder dentro del flujo permitido.',
            'Queda historial para seguimiento comercial posterior.',
        ],
    },
    'whatsapp': {
        'label': 'WhatsApp',
        'aliases': ('whatsapp', 'conversaciones whatsapp'),
        'summary': 'Ofrece un panel de conversaciones y monitoreo de interacciones por WhatsApp.',
        'flow': [
            'Se concentran conversaciones o eventos del canal.',
            'El equipo revisa estados, historial y derivaciones disponibles.',
            'Puede convivir con CRM segun el rol del usuario.',
        ],
    },
    'tienda': {
        'label': 'Mi Tienda Online',
        'aliases': ('tienda', 'tienda online', 'mi tienda online', 'catalogo web', 'catálogo web'),
        'summary': 'Administra el frente online del negocio para mostrar catalogo, contenido y conversion a consultas.',
        'flow': [
            'Se configura la presencia online y sus recursos visibles.',
            'Los productos y promociones publicados se apoyan en los datos del sistema principal.',
            'Luego se analizan visitas, consultas y rendimiento comercial.',
        ],
    },
    'reportes': {
        'label': 'Reportes',
        'aliases': ('reporte', 'reportes'),
        'summary': 'Concentra vistas analiticas para revisar ventas, inventario, finanzas y otras areas del negocio.',
        'flow': [
            'Se elige un reporte y un rango de analisis.',
            'El sistema agrupa la informacion del modulo correspondiente.',
            'Segun permisos, tambien puede exportarse.',
        ],
    },
    'configuracion': {
        'label': 'Configuracion',
        'aliases': ('configuracion', 'configuración', 'ajustes', 'usuarios', 'roles'),
        'summary': 'Reune ajustes generales del sistema, usuarios, roles y permisos administrativos.',
        'flow': [
            'Se revisan parametros generales o estructuras de acceso.',
            'Los cambios administrativos quedan controlados por permisos altos.',
            'Desde aqui tambien se ordena el acceso de usuarios y roles.',
        ],
    },
    'inteligencia': {
        'label': 'Inteligencia',
        'aliases': ('inteligencia', 'bi', 'analitica', 'analítica'),
        'summary': 'Resume senales del negocio para detectar oportunidades, alertas y foco operativo.',
        'flow': [
            'Se consolidan datos de varias areas en una vista de analisis.',
            'El usuario revisa alertas, comparaciones y oportunidades detectadas.',
            'Sirve como capa de lectura para apoyar decisiones.',
        ],
    },
    'proveedores': {
        'label': 'Proveedores',
        'aliases': ('proveedor', 'proveedores'),
        'summary': 'Gestiona la ficha de proveedores y su relacion operativa con compras y pagos.',
        'flow': [
            'Se da de alta o actualiza el proveedor.',
            'Su ficha se usa luego en compras, deudas y seguimiento comercial.',
            'Permite ordenar la base de abastecimiento del negocio.',
        ],
    },
    'asistente_ia': {
        'label': 'Asistente IA',
        'aliases': ('asistente ia', 'ia', 'panel ia'),
        'summary': 'Ayuda a consultar el sistema en modo de lectura y a resumir informacion operativa.',
        'flow': [
            'El usuario hace una consulta en lenguaje natural.',
            'El asistente elige la consulta interna adecuada y devuelve una respuesta resumida.',
            'No ejecuta cambios automaticos si no hay un flujo asistido explicitamente controlado.',
        ],
    },
    'auditoria': {
        'label': 'Auditoria',
        'aliases': ('auditoria', 'auditoría', 'logs'),
        'summary': 'Permite revisar trazabilidad de eventos y acciones registradas en el sistema.',
        'flow': [
            'Se consultan eventos o cambios registrados.',
            'El historial sirve para control, seguimiento y revision administrativa.',
            'Su uso suele estar limitado a perfiles autorizados.',
        ],
    },
}


def _normalizar(texto: str) -> str:
    texto = (texto or '').lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', texto).strip()


def _label_desde_codigo(modulo: str) -> str:
    base = MODULE_REGISTRY.get(modulo, {}).get('label')
    if base:
        return base
    return ' '.join((modulo or '').replace('_', ' ').split()).title() or 'Modulo'


def resolver_modulo_consulta(texto: str) -> str | None:
    consulta = _normalizar(texto)
    if not consulta:
        return None

    for codigo, meta in MODULE_REGISTRY.items():
        if consulta == codigo or consulta == _normalizar(meta.get('label') or ''):
            return codigo
        for alias in meta.get('aliases') or ():
            alias_norm = _normalizar(alias)
            if alias_norm and (consulta == alias_norm or f'modulo de {alias_norm}' in consulta or f'modulo {alias_norm}' in consulta or alias_norm in consulta):
                return codigo

    modulos_permiso = {
        item[0] for item in Permiso.query.with_entities(Permiso.modulo).filter(Permiso.activo.is_(True)).distinct().all()
    }
    for modulo in sorted(modulos_permiso):
        modulo_norm = _normalizar(modulo.replace('_', ' '))
        if modulo_norm and (consulta == modulo_norm or f'modulo de {modulo_norm}' in consulta or f'modulo {modulo_norm}' in consulta or modulo_norm in consulta):
            return modulo
    return None


def _sugerencias_modulo(texto: str) -> list[str]:
    consulta = _normalizar(texto)
    if not consulta:
        return []
    sugerencias = []
    for codigo, meta in MODULE_REGISTRY.items():
        label = meta.get('label') or codigo
        tokens = [_normalizar(label), _normalizar(codigo.replace('_', ' ')), *[_normalizar(x) for x in meta.get('aliases') or ()]]
        if any(token and (token in consulta or consulta in token) for token in tokens):
            sugerencias.append(label)
    return list(dict.fromkeys(sugerencias))[:5]


def _permisos_modulo(modulo: str):
    return Permiso.query.filter_by(modulo=modulo, activo=True).order_by(Permiso.nombre.asc()).all()


def _funciones_desde_permisos(permisos) -> list[str]:
    funciones = []
    for permiso in permisos:
        descripcion = (permiso.descripcion or permiso.nombre or '').strip()
        if descripcion and descripcion not in funciones:
            funciones.append(descripcion)
    return funciones[:6]


def _acciones_sensibles_desde_permisos(permisos) -> list[str]:
    sensibles = []
    for permiso in permisos:
        if not bool(getattr(permiso, 'requiere_autorizacion', False)):
            continue
        texto = (permiso.descripcion or permiso.nombre or '').strip()
        if texto and texto not in sensibles:
            sensibles.append(texto)
    return sensibles[:4]


def _flujo_generico(label: str, funciones: list[str]) -> list[str]:
    flujo = [f'Se usa para operar y consultar {label.lower()} dentro del sistema.']
    if funciones:
        flujo.append(f'Las tareas mas comunes incluyen: {funciones[0].rstrip(".")}.')
    if len(funciones) > 1:
        flujo.append(f'Tambien puede cubrir: {funciones[1].rstrip(".")}.')
    return flujo[:3]


def modulo_funcionamiento(args: dict | None = None, usuario=None) -> dict:
    del usuario
    payload = dict(args or {})
    consulta = (payload.get('modulo') or payload.get('busqueda') or payload.get('referencia') or '').strip()
    modulo = resolver_modulo_consulta(consulta)
    if not modulo:
        return {
            'encontrado': False,
            'error': 'modulo_no_encontrado',
            'consulta': consulta,
            'sugerencias': _sugerencias_modulo(consulta),
        }

    permisos = _permisos_modulo(modulo)
    meta = MODULE_REGISTRY.get(modulo, {})
    label = _label_desde_codigo(modulo)
    funciones = _funciones_desde_permisos(permisos)
    flujo = (meta.get('flow') or [])[:4] or _flujo_generico(label, funciones)

    return {
        'encontrado': True,
        'modulo': modulo,
        'label': label,
        'summary': meta.get('summary') or f'Es el modulo funcional de {label.lower()} dentro del sistema.',
        'funciones_clave': funciones,
        'flujo_resumen': flujo,
        'acciones_sensibles': _acciones_sensibles_desde_permisos(permisos),
        'nota_seguridad': 'Explicacion funcional de alto nivel, sin exponer codigo, claves ni configuraciones sensibles.',
    }
