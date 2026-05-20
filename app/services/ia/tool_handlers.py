"""
Ejecución de tool calls de la IA.
Todos los handlers consolidados en un solo archivo.
"""
import json
import logging
from datetime import datetime

from app.utils.phone_utils import normalizar_telefono
from app.models.reparacion import Reparacion
from app.services.bot_context import build_bot_context_faq

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────

ESTADO_DISPLAY = {
    'pendiente':          ('Pendiente', '⏳'),
    'diagnostico':        ('En diagnóstico', '🔍'),
    'espera_presupuesto': ('Esperando aprobación de presupuesto', '💰'),
    'espera_repuesto':    ('Esperando repuesto', '📦'),
    'espera_cliente':     ('Esperando respuesta del cliente', '📞'),
    'en_proceso':         ('En reparación', '🔧'),
    'listo':              ('Listo para retirar', '✅'),
    'no_se_pudo':         ('No se pudo reparar', '❌'),
    'entregado':          ('Entregado', '📱'),
    'cancelado':          ('Cancelado', '🚫'),
    'antiguos':           ('Antiguos', '🗂️'),
}

ESTADOS_ACTIVOS = [
    'pendiente', 'diagnostico', 'espera_presupuesto',
    'espera_repuesto', 'espera_cliente', 'en_proceso', 'listo', 'no_se_pudo',
]


def _coerce_reparacion_id(raw_id) -> int | None:
    if raw_id in (None, '', 0, '0'):
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _serializar_historial_publico(rep: Reparacion) -> list[dict]:
    historial_rel = getattr(rep, 'historial_estados', None)
    if historial_rel is None:
        return []

    try:
        historial_items = historial_rel.all()
    except Exception:
        try:
            historial_items = list(historial_rel)
        except Exception:
            historial_items = []

    historial_items = sorted(
        historial_items,
        key=lambda item: getattr(item, 'fecha_cambio', None) or datetime.min,
        reverse=True,
    )

    serializado = []
    for item in historial_items:
        estado_codigo = getattr(item, 'estado_nuevo', '') or ''
        estado_texto, _estado_emoji = ESTADO_DISPLAY.get(estado_codigo, (estado_codigo, ''))
        serializado.append({
            'estado': estado_codigo,
            'estado_texto': estado_texto,
            'fecha': item.fecha_cambio.strftime('%d/%m/%Y %H:%M') if getattr(item, 'fecha_cambio', None) else None,
            'nota': (getattr(item, 'nota', None) or '').strip() or None,
        })
    return serializado


def _construir_seguimiento_publico(rep: Reparacion) -> dict:
    estado_texto, estado_emoji = ESTADO_DISPLAY.get(rep.estado, (rep.estado, ''))
    costo_visible = None
    tipo_costo_visible = None

    if rep.mostrar_costo:
        costo_final = float(rep.costo_final_calculado or 0)
        costo_estimado = float(rep.costo_estimado or 0)
        if costo_final > 0:
            costo_visible = costo_final
            tipo_costo_visible = 'final'
        elif costo_estimado > 0:
            costo_visible = costo_estimado
            tipo_costo_visible = 'estimado'

    seguimiento = {
        'id_reparacion': rep.id_reparacion,
        'equipo': f'{rep.tipo_equipo} {rep.marca_modelo}',
        'estado': rep.estado,
        'estado_texto': f'{estado_texto} {estado_emoji}'.strip(),
        'fecha_ingreso': rep.fecha_ingreso.strftime('%d/%m/%Y') if rep.fecha_ingreso else None,
        'fecha_ingreso_detalle': rep.fecha_ingreso.strftime('%d/%m/%Y %H:%M') if rep.fecha_ingreso else None,
        'fecha_estimada': rep.fecha_estimada.strftime('%d/%m/%Y') if rep.fecha_estimada else None,
        'hora_estimada': rep.fecha_estimada_hora.strftime('%H:%M') if rep.fecha_estimada_hora else None,
        'nota_del_local': (rep.nota_cliente or '').strip() or None,
        'historial': _serializar_historial_publico(rep),
    }
    if costo_visible is not None:
        seguimiento['costo_visible'] = costo_visible
        seguimiento['tipo_costo_visible'] = tipo_costo_visible

    return seguimiento


# ─── Contexto del cliente ────────────────────────────────────────────────────

def obtener_contexto_cliente(telefono: str) -> dict:
    """Obtiene reparaciones activas y datos del cliente por teléfono."""
    from app.models.cliente import Cliente
    from app.models.reparacion import Reparacion

    if not telefono:
        return {}

    tel_norm = normalizar_telefono(telefono)
    if not tel_norm:
        return {}

    clientes = Cliente.query.filter(Cliente.telefono.isnot(None)).all()
    cliente = None
    for c in clientes:
        if normalizar_telefono(c.telefono or '') == tel_norm:
            cliente = c
            break

    if not cliente:
        return {'cliente_registrado': False}

    resultado = {
        'cliente_registrado': True,
        'nombre_cliente': cliente.nombre,
    }

    reparaciones = Reparacion.query.filter(
        Reparacion.cliente_id == cliente.id_cliente,
        Reparacion.estado.in_(ESTADOS_ACTIVOS)
    ).order_by(Reparacion.fecha_ingreso.desc()).all()

    lista = []
    for rep in reparaciones:
        estado_texto, estado_emoji = ESTADO_DISPLAY.get(rep.estado, (rep.estado, ''))
        lista.append({
            'id_reparacion': rep.id_reparacion,
            'equipo': f'{rep.tipo_equipo} {rep.marca_modelo}',
            'estado': rep.estado,
            'estado_texto': f'{estado_texto} {estado_emoji}',
            'falla_reportada': rep.falla_reportada,
            'fecha_ingreso': rep.fecha_ingreso.strftime('%d/%m/%Y') if rep.fecha_ingreso else None,
            'fecha_estimada': rep.fecha_estimada.strftime('%d/%m/%Y') if rep.fecha_estimada else None,
            'hora_estimada': rep.fecha_estimada_hora.strftime('%H:%M') if rep.fecha_estimada_hora else None,
        })

    resultado['reparaciones_activas'] = lista
    resultado['total_reparaciones'] = len(lista)
    return resultado


# ─── Handlers de tools ───────────────────────────────────────────────────────

def _handle_listar_reparaciones(args: dict, contexto: dict) -> dict:
    from app.models.cliente import Cliente
    from app.models.reparacion import Reparacion

    telefono = args.get('telefono') or contexto.get('telefono', '')
    if not telefono:
        return {'error': 'Se requiere teléfono'}

    tel_norm = normalizar_telefono(telefono)
    if not tel_norm:
        return {'error': 'Teléfono inválido'}

    clientes = Cliente.query.filter(Cliente.telefono.isnot(None)).all()
    cliente = None
    for c in clientes:
        if normalizar_telefono(c.telefono or '') == tel_norm:
            cliente = c
            break

    if not cliente:
        return {
            'reparaciones': [],
            'mensaje': 'No encontramos reparaciones asociadas a este número de teléfono.',
        }

    reparaciones = Reparacion.query.filter(
        Reparacion.cliente_id == cliente.id_cliente,
        Reparacion.estado.in_(ESTADOS_ACTIVOS)
    ).order_by(Reparacion.fecha_ingreso.desc()).all()

    if not reparaciones:
        return {
            'reparaciones': [],
            'mensaje': 'No tenés reparaciones activas en este momento.',
        }

    lista = []
    for rep in reparaciones:
        estado_texto, estado_emoji = ESTADO_DISPLAY.get(rep.estado, (rep.estado, ''))
        lista.append({
            'id_reparacion': rep.id_reparacion,
            'equipo': f'{rep.tipo_equipo} {rep.marca_modelo}',
            'estado': rep.estado,
            'estado_texto': f'{estado_texto} {estado_emoji}',
            'falla_reportada': rep.falla_reportada,
            'fecha_ingreso': rep.fecha_ingreso.strftime('%d/%m/%Y') if rep.fecha_ingreso else None,
            'fecha_estimada': rep.fecha_estimada.strftime('%d/%m/%Y') if rep.fecha_estimada else None,
            'hora_estimada': rep.fecha_estimada_hora.strftime('%H:%M') if rep.fecha_estimada_hora else None,
        })

    return {
        'cliente': cliente.nombre,
        'total': len(lista),
        'reparaciones': lista,
    }


def _handle_consultar_estado(args: dict, contexto: dict) -> dict:
    id_rep = _coerce_reparacion_id(
        args.get('id_reparacion')
        or contexto.get('reparacion_verificada')
        or contexto.get('reparacion_seleccionada')
    )
    modo_consulta = str(args.get('modo_consulta') or 'detalle').strip().lower()
    if modo_consulta not in {'solo_fecha', 'estado', 'detalle'}:
        modo_consulta = 'detalle'

    if not id_rep:
        return {'error': 'Se requiere id_reparacion o una reparación previamente verificada/seleccionada'}

    rep = Reparacion.query.get(id_rep)
    if not rep:
        return {'error': f'No se encontró reparación #{id_rep}'}

    # Verificar que la reparación pertenece al teléfono de la conversación
    telefono_conv = contexto.get('telefono', '')
    if telefono_conv and rep.cliente:
        tel_cliente = normalizar_telefono(rep.cliente.telefono or '')
        tel_conv = normalizar_telefono(telefono_conv)
        if tel_cliente and tel_conv and tel_cliente != tel_conv:
            return {'error': 'Esta reparación no corresponde a tu número de teléfono'}

    estado_texto, estado_emoji = ESTADO_DISPLAY.get(rep.estado, (rep.estado, ''))
    verificado = contexto.get('verificado', False)
    seguimiento_publico = _construir_seguimiento_publico(rep)

    resultado = {
        'id_reparacion': rep.id_reparacion,
        'equipo': f'{rep.tipo_equipo} {rep.marca_modelo}',
        'modo_consulta': modo_consulta,
        'estado': rep.estado,
        'estado_texto': f'{estado_texto} {estado_emoji}',
        'falla_reportada': rep.falla_reportada,
        'fecha_ingreso': rep.fecha_ingreso.strftime('%d/%m/%Y') if rep.fecha_ingreso else None,
        'seguimiento_publico': seguimiento_publico,
    }

    if rep.fecha_estimada:
        resultado['fecha_estimada'] = rep.fecha_estimada.strftime('%d/%m/%Y')
    if rep.fecha_estimada_hora:
        resultado['hora_estimada'] = rep.fecha_estimada_hora.strftime('%H:%M')
    if rep.nota_cliente:
        resultado['nota_del_local'] = rep.nota_cliente
    if seguimiento_publico.get('historial'):
        resultado['historial'] = seguimiento_publico['historial']
    if seguimiento_publico.get('costo_visible') is not None:
        resultado['costo_visible'] = seguimiento_publico['costo_visible']
        resultado['tipo_costo_visible'] = seguimiento_publico.get('tipo_costo_visible')

    if modo_consulta == 'solo_fecha':
        salida = {
            'id_reparacion': resultado['id_reparacion'],
            'equipo': resultado['equipo'],
            'modo_consulta': modo_consulta,
            'fecha_estimada': resultado.get('fecha_estimada'),
            'hora_estimada': resultado.get('hora_estimada'),
        }
        if not salida.get('fecha_estimada'):
            salida['mensaje'] = 'Aún no hay fecha/hora estimada confirmada.'
        return salida

    if modo_consulta == 'estado':
        return {
            'id_reparacion': resultado['id_reparacion'],
            'equipo': resultado['equipo'],
            'modo_consulta': modo_consulta,
            'estado': resultado.get('estado'),
            'estado_texto': resultado.get('estado_texto'),
            'fecha_ingreso': resultado.get('fecha_ingreso'),
        }

    # Modo detalle
    if verificado:
        resultado['diagnostico'] = rep.diagnostico_tecnico
        resultado['solucion'] = rep.solucion
        if rep.mostrar_costo:
            resultado['costo_estimado'] = float(rep.costo_estimado or 0)
            resultado['costo_final'] = float(rep.costo_final_calculado or 0)
            resultado['abono'] = float(rep.abono or 0)
            resultado['saldo_pendiente'] = float(rep.saldo_pendiente or 0)
    else:
        resultado['nota_seguridad'] = (
            'Podés compartir el estado visible para clientes. Para ver diagnóstico técnico y datos internos, '
            'necesitás verificar tu identidad '
            'con el código de 6 dígitos que te dieron al dejar el equipo.'
        )

    return resultado


def _handle_verificar_codigo(args: dict, contexto: dict) -> dict:
    from app.services.whatsapp.verificacion_service import verificar_codigo

    codigo = args.get('codigo', '').strip()
    telefono = args.get('telefono') or contexto.get('telefono', '')

    if not codigo or not telefono:
        return {'error': 'Se requiere código y teléfono'}

    return verificar_codigo(telefono, codigo)


def _handle_obtener_faq(args: dict, contexto: dict) -> dict:
    from app.models.whatsapp import WhatsAppConfiguracion

    tema = args.get('tema', 'todos')

    faq_data = {}
    if tema == 'todos':
        configs = WhatsAppConfiguracion.query.filter_by(categoria='faq').all()
        for c in configs:
            faq_data[c.clave] = c.valor
    else:
        config = WhatsAppConfiguracion.query.filter_by(clave=f'faq_{tema}').first()
        if config:
            faq_data[tema] = config.valor

    defaults = {
        'horarios': 'Lunes a Sábados de 8:00 a 18:00',
        'ubicacion': 'Consultar con el local la dirección exacta.',
        'garantia': 'Ofrecemos garantía de 30 días en reparaciones. No cubre daños por agua ni golpes posteriores.',
        'requisitos': 'Para retirar tu equipo necesitás: cédula de identidad y el comprobante de ingreso.',
        'metodos_pago': 'Aceptamos efectivo, transferencia bancaria y pago con tarjeta.',
    }

    faq_contexto = build_bot_context_faq(extra_defaults={
        'horarios': 'Lunes a sabados de 8:00 a 18:00',
        'ubicacion': 'Consultar con el local la direccion exacta.',
        'garantia': 'Ofrecemos garantia de 30 dias en reparaciones. No cubre danos por agua ni golpes posteriores.',
        'requisitos': 'Para retirar tu equipo necesitas: cedula de identidad y el comprobante de ingreso.',
        'metodos_pago': 'Aceptamos efectivo, transferencia bancaria y pago con tarjeta.',
        'contacto': 'Podes consultar con el local para confirmar el numero disponible.',
        'zonas_de_entrega': 'Consulta con el local si llega a tu zona.',
        'politica_cambios': 'La politica de cambios debe confirmarse directamente con el local.',
    })
    if tema == 'todos':
        faq_data = {**faq_contexto, **faq_data}
    elif faq_contexto.get(tema):
        faq_data[tema] = faq_contexto[tema]

    if not faq_data:
        faq_data = defaults if tema == 'todos' else {tema: defaults.get(tema, 'Información no disponible.')}

    return {'faq': faq_data}


def _handle_estimar_precio_reparacion(args: dict, contexto: dict) -> dict:
    consulta = (args.get('consulta') or args.get('descripcion') or '').strip()
    tipo_equipo = (args.get('tipo_equipo') or '').strip().lower()
    marca_modelo = (args.get('marca_modelo') or '').strip().lower()
    if not consulta and not tipo_equipo and not marca_modelo:
        return {'error': 'Se requiere al menos consulta, tipo_equipo o marca_modelo'}

    texto_consulta = f'{consulta} {tipo_equipo} {marca_modelo}'.strip().lower()
    tokens = [t for t in texto_consulta.replace(',', ' ').replace('.', ' ').split() if len(t) >= 3]
    seen = set()
    tokens = [t for t in tokens if not (t in seen or seen.add(t))]

    referencias = []
    for rep in Reparacion.query.all():
        costo_final = float(getattr(rep, 'costo_final_calculado', 0) or 0)
        costo_estimado = float(getattr(rep, 'costo_estimado', 0) or 0)
        precio = costo_final if costo_final > 0 else costo_estimado
        if precio <= 0:
            continue

        texto_rep = f'{getattr(rep, "tipo_equipo", "")} {getattr(rep, "marca_modelo", "")} {getattr(rep, "falla_reportada", "")}'.lower()
        score = sum(1 for tok in tokens if tok in texto_rep)
        if tipo_equipo and tipo_equipo in (getattr(rep, 'tipo_equipo', '') or '').lower():
            score += 2
        if marca_modelo and marca_modelo in (getattr(rep, 'marca_modelo', '') or '').lower():
            score += 2
        referencias.append((score, precio))

    if not referencias:
        return {'error': 'No hay historial con costos para estimar'}

    score_minimo = 2 if len(tokens) >= 2 else 1
    similares = [item for item in referencias if item[0] >= score_minimo]
    criterio = 'similares'
    if not similares:
        similares = referencias
        criterio = 'historico_general'

    similares.sort(key=lambda item: item[0], reverse=True)
    muestra = similares[:20]
    precios = [int(round(item[1])) for item in muestra]
    minimo = min(precios)
    maximo = max(precios)
    confianza = 'alta' if criterio == 'similares' and len(precios) >= 3 else 'media' if criterio == 'similares' else 'baja'

    return {
        'consulta': consulta or marca_modelo or tipo_equipo,
        'rango_estimado': {'min': minimo, 'max': maximo, 'moneda': 'Gs'},
        'cantidad_referencias': len(precios),
        'criterio': criterio,
        'confianza': confianza,
        'mensaje': 'Rango orientativo basado en reparaciones similares del historial.',
    }


def _handle_buscar_productos(args: dict, contexto: dict) -> dict:
    from app import db
    from app.models.producto import Producto, Categoria

    busqueda = (args.get('busqueda') or '').strip()
    categoria_filtro = (args.get('categoria') or '').strip().lower()
    orden = (args.get('orden') or 'relevancia').strip().lower()

    # Base: productos activos (incluyendo sin stock para que la IA pueda
    # responder "no lo tenemos en este momento" en vez de ignorar el producto)
    def _base_query():
        q = Producto.query.filter(
            Producto.activo == True,
            Producto.es_servicio == False,
        )
        if categoria_filtro:
            q = q.join(Categoria).filter(
                db.func.lower(Categoria.nombre).contains(categoria_filtro)
            )
        return q

    terminos = busqueda.split()

    # 1. Búsqueda estricta: todos los términos deben coincidir (AND)
    query = _base_query()
    for termino in terminos:
        patron = f'%{termino}%'
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(patron),
                Producto.marca.ilike(patron),
                Producto.modelo.ilike(patron),
                Producto.descripcion.ilike(patron),
            )
        )

    if orden == 'precio_menor':
        query = query.order_by(db.asc(Producto.precio_venta))
    elif orden == 'precio_mayor':
        query = query.order_by(db.desc(Producto.precio_venta))
    else:
        query = query.order_by(Producto.nombre)

    productos = query.limit(10).all()

    # 2. Si no hay resultados exactos, hacer búsqueda amplia (OR) como fallback
    #    para que la IA pueda sugerir opciones similares al cliente
    sugerencias_modo = False
    if not productos and len(terminos) > 1:
        query_or = _base_query()
        condiciones = []
        for termino in terminos:
            patron = f'%{termino}%'
            condiciones.append(Producto.nombre.ilike(patron))
            condiciones.append(Producto.marca.ilike(patron))
            condiciones.append(Producto.modelo.ilike(patron))
        query_or = query_or.filter(db.or_(*condiciones))
        
        if orden == 'precio_menor':
            query_or = query_or.order_by(db.asc(Producto.precio_venta))
        elif orden == 'precio_mayor':
            query_or = query_or.order_by(db.desc(Producto.precio_venta))
        else:
            query_or = query_or.order_by(Producto.nombre)
            
        productos = query_or.limit(8).all()
        sugerencias_modo = True

    if not productos:
        mensaje_error = f'No encontramos productos que coincidan con "{busqueda}".' if busqueda else 'No encontramos productos con esas características.'
        return {
            'productos': [],
            'mensaje': f'{mensaje_error} Podés preguntar por otro nombre o te comunico con un asesor.',
        }

    lista = []
    for p in productos:
        disponible = (p.stock_actual or 0) > 0
        item = {
            'nombre': p.nombre,
            # Solo precio minorista. Nunca exponer stock_actual numérico.
            'precio': f'{int(p.precio_venta):,}'.replace(',', '.') + ' Gs' if p.precio_venta else 'Consultar',
            'disponible': disponible,
        }
        if not disponible:
            item['sin_stock'] = True  # Señal clara para la IA
        if p.marca:
            item['marca'] = p.marca
        if p.modelo:
            item['modelo'] = p.modelo
        if p.color:
            item['color'] = p.color
        if p.capacidad:
            item['capacidad'] = p.capacidad
        if p.categoria:
            item['categoria'] = p.categoria.nombre
        lista.append(item)

    resultado = {
        'total': len(lista),
        'productos': lista,
        'nota': 'Si el cliente quiere comprar, derivá a un asesor para concretar la venta.',
    }
    if sugerencias_modo:
        resultado['modo'] = 'sugerencias'
        resultado['aclaracion'] = (
            'No se encontró coincidencia exacta. Estos son productos similares. '
            'Preguntale al cliente si alguno es el que busca.'
        )
    return resultado


def _handle_derivar_asesor(args: dict, contexto: dict) -> dict:
    from app.services.whatsapp.asignacion_service import asignar_conversacion

    motivo = args.get('motivo', 'Solicitud del cliente')
    prioridad = args.get('prioridad', 'normal')
    id_conversacion = contexto.get('id_conversacion')

    if not id_conversacion:
        return {'error': 'No se pudo identificar la conversación'}

    return asignar_conversacion(id_conversacion, motivo, prioridad)


# ─── Dispatcher ──────────────────────────────────────────────────────────────

_HANDLERS = {
    'consultar_estado_reparacion': _handle_consultar_estado,
    'listar_reparaciones_cliente': _handle_listar_reparaciones,
    'verificar_codigo':            _handle_verificar_codigo,
    'obtener_faq':                 _handle_obtener_faq,
    'estimar_precio_reparacion':   _handle_estimar_precio_reparacion,
    'buscar_productos':            _handle_buscar_productos,
    'derivar_a_asesor':            _handle_derivar_asesor,
}


def ejecutar_tool(nombre: str, argumentos: dict, contexto: dict) -> str:
    """
    Ejecuta un tool call y retorna el resultado como JSON string.
    """
    handler = _HANDLERS.get(nombre)
    if not handler:
        logger.warning(f"Tool desconocido: {nombre}")
        return json.dumps({'error': f'Función {nombre} no existe'}, ensure_ascii=False)

    try:
        resultado = handler(argumentos, contexto)
        logger.info(f"Tool {nombre} OK: {str(resultado)[:200]}")
        return json.dumps(resultado, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"Error ejecutando tool {nombre}: {e}", exc_info=True)
        return json.dumps({'error': 'Error interno al procesar la consulta'}, ensure_ascii=False)
