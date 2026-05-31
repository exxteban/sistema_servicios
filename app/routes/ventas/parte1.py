"""
Rutas de Punto de Venta (POS)
"""
import re
from datetime import datetime
from time import perf_counter
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, render_template_string, current_app, abort
from flask_login import login_required, current_user
from decimal import Decimal
from jinja2 import TemplateSyntaxError
from app import db
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from app.models import (
    Producto, Categoria, ProductoPrecioOpcion, Servicio, ServicioPrecioOpcion, Cliente, Venta, DetalleVenta, PagoVenta, Ticket,
    CuentaPorCobrar,
    MetodoPago, SesionCaja, MovimientoCaja, MovimientoStock, Configuracion, Permiso, Autorizacion, ColaCobro,
    Devolucion, DetalleDevolucion, Reparacion, Usuario, Rol
)
from app.models.reparacion_seguimiento import ReparacionHistorialEstado
from app.utils.helpers import caja_abierta_required, local_strftime, parse_iso_date, today_local, utc_bounds_for_local_dates
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.permisos import validar_autorizacion
from cobranzas import CLAVE_VENTAS_CREDITO_METODO_PAGO_ID

ventas_bp = Blueprint('ventas', __name__)

REPARACION_COSTO_BASE_CODIGO = 'SRV-REP-COSTO-BASE'
REPARACION_COSTO_BASE_NOMBRE = 'Costo final reparación (base)'
REPARACION_SERVICIOS_CATEGORIA = 'Servicios de Reparación'
ROLES_VENDEDOR_CAJERO = {'vendedor', 'cajero'}
CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS = 'pos_ocultar_selector_vendedor_cajero'
CLAVE_CAJA_FLUJO_ENVIADO = 'caja_flujo_enviado_desde_vendedor'
CLAVE_CAJA_EXIGIR_CAJERO = 'caja_exigir_cajero_para_cobro'


def _is_truthy(v):
    if v is True:
        return True
    if v in (None, False, 0, 0.0, ''):
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ('1', 'true', 't', 'yes', 'y', 'si', 'sí', 'on')

def _usuarios_vendedores_cajeros_activos():
    return (
        Usuario.query
        .options(joinedload(Usuario.rol))
        .join(Rol, Usuario.id_rol == Rol.id_rol)
        .filter(
            Usuario.activo == True,
            Rol.activo == True,
            func.lower(Rol.nombre).in_(ROLES_VENDEDOR_CAJERO)
        )
        .order_by(Usuario.nombre_completo.asc())
        .all()
    )

def _ocultar_selector_vendedor_pos():
    # Compatibilidad: clave histórica usada como "mostrar selector".
    # Desactivado => no mostrar selector y usar usuario actual.
    mostrar_selector = Configuracion.obtener_bool(CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS, default=False)
    return not mostrar_selector

def _norm_nombre_metodo(nombre):
    s = (nombre or '').strip().lower()
    s = s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    return ' '.join(s.split())

def _es_metodo_credito_tienda(nombre):
    n = _norm_nombre_metodo(nombre)
    return n in {'credito tienda', 'venta a credito'}

def _es_metodo_efectivo(nombre):
    """Compatibilidad: delega en el servicio canonico de metodos de caja.

    Para identificar el metodo efectivo en colecciones preferir
    `app.services.caja_metodos.obtener_metodo_efectivo_id()` y comparar por id.
    Este wrapper se mantiene para callers que solo tienen el nombre.
    """
    from app.services.caja_metodos import es_metodo_efectivo as _svc_es_efectivo
    return _svc_es_efectivo(nombre)

def _resolver_metodo_credito_tienda(metodos=None, *, solo_activos=False):
    metodos_disponibles = list(metodos) if metodos is not None else list(MetodoPago.query.all())
    if solo_activos:
        metodos_disponibles = [metodo for metodo in metodos_disponibles if bool(getattr(metodo, 'activo', False))]

    metodo_configurado_id = Configuracion.obtener_int(CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, default=0)
    if metodo_configurado_id > 0:
        for metodo in metodos_disponibles:
            if int(getattr(metodo, 'id_metodo_pago', 0) or 0) == metodo_configurado_id:
                return metodo
        metodo_configurado = db.session.get(MetodoPago, metodo_configurado_id)
        if metodo_configurado and (not solo_activos or bool(getattr(metodo_configurado, 'activo', False))):
            return metodo_configurado

    candidatos_legacy = [
        metodo for metodo in metodos_disponibles
        if _es_metodo_credito_tienda(getattr(metodo, 'nombre', ''))
    ]
    if candidatos_legacy:
        candidatos_legacy.sort(key=lambda metodo: (int(getattr(metodo, 'orden_display', 0) or 0), int(getattr(metodo, 'id_metodo_pago', 0) or 0)))
        return candidatos_legacy[0]

    candidatos_fuzzy = []
    for metodo in metodos_disponibles:
        nombre_normalizado = _norm_nombre_metodo(getattr(metodo, 'nombre', ''))
        if 'credito' in nombre_normalizado and 'tienda' in nombre_normalizado:
            candidatos_fuzzy.append(metodo)
    if len(candidatos_fuzzy) == 1:
        return candidatos_fuzzy[0]
    return None

def _metodo_pago_es_credito_tienda(metodo, metodo_credito_tienda=None):
    if metodo is None:
        return False
    metodo_credito_tienda = metodo_credito_tienda or _resolver_metodo_credito_tienda()
    if metodo_credito_tienda is not None:
        try:
            return int(getattr(metodo, 'id_metodo_pago', 0) or 0) == int(getattr(metodo_credito_tienda, 'id_metodo_pago', 0) or 0)
        except Exception:
            return False
    return _es_metodo_credito_tienda(getattr(metodo, 'nombre', ''))

def _buscar_cola_cobro_venta_activa_por_request_id(client_request_id):
    client_request_id = (client_request_id or '').strip()
    if not client_request_id:
        return None

    pendientes = (
        ColaCobro.query
        .filter(
            ColaCobro.tipo_origen == 'venta',
            ColaCobro.estado.in_(['pendiente', 'en_proceso'])
        )
        .order_by(ColaCobro.fecha_envio.desc())
        .all()
    )
    for pendiente in pendientes:
        metadata = pendiente.get_metadata()
        if (metadata.get('client_request_id') or '').strip() == client_request_id:
            return pendiente
    return None

def _normalizar_items_para_cola_cobro(items, usar_precio_mayorista=False):
    if not items:
        raise ValueError('No hay productos en la venta')

    from app.services.ventas_promociones import (
        calculate_queue_product_subtotal,
        get_queue_product_promotions,
    )
    promociones_por_producto = get_queue_product_promotions(items)

    subtotal = Decimal('0')
    items_normalizados = []

    for item in items:
        tipo_item = (item.get('tipo') or 'producto').strip().lower()
        if tipo_item == 'servicio' or item.get('id_servicio') not in (None, ''):
            try:
                id_servicio = int(item.get('id_servicio') or item.get('id'))
            except Exception:
                raise ValueError('Servicio inválido')
            servicio = db.session.get(Servicio, id_servicio)
            if not servicio or not servicio.activo:
                raise ValueError(f'Servicio no encontrado: {id_servicio}')
            producto = None
        else:
            try:
                id_producto = int(item.get('id_producto'))
            except Exception:
                raise ValueError('Producto inválido')
            producto = db.session.get(Producto, id_producto)
            if not producto:
                raise ValueError(f'Producto no encontrado: {id_producto}')
            servicio = None

        try:
            cantidad = int(item.get('cantidad', 0))
        except Exception:
                raise ValueError('Cantidad inválida')
        if cantidad <= 0:
            raise ValueError('Cantidad inválida')

        precio_original = Decimal(str((servicio.precio if servicio else producto.precio_venta) or 0))
        precio = precio_original
        precio_opcion_id = item.get('precio_opcion_id')

        if servicio and precio_opcion_id not in (None, ''):
            try:
                precio_opcion_id = int(precio_opcion_id)
            except Exception:
                raise ValueError('precio_opcion_id inválido')
            opcion = ServicioPrecioOpcion.query.filter_by(
                id_opcion_precio=precio_opcion_id,
                id_servicio=servicio.id_servicio,
                activo=True
            ).first()
            if not opcion:
                raise ValueError('Opción de precio inválida para el servicio')
            precio = Decimal(str(opcion.precio or 0))
        elif servicio and item.get('precio_manual') and item.get('precio') is not None:
            try:
                precio = Decimal(str(item.get('precio')))
            except Exception:
                raise ValueError('Precio inválido para el servicio')
            if precio <= 0:
                raise ValueError('Precio inválido para el servicio')
        elif precio_opcion_id not in (None, ''):
            try:
                precio_opcion_id = int(precio_opcion_id)
            except Exception:
                raise ValueError('precio_opcion_id inválido')
            opcion = ProductoPrecioOpcion.query.filter_by(
                id_opcion_precio=precio_opcion_id,
                id_producto=producto.id_producto,
                activo=True
            ).first()
            if not opcion:
                raise ValueError('Opción de precio inválida para el producto')
            try:
                precio = Decimal(str(opcion.precio))
            except Exception:
                raise ValueError('Precio inválido en opción de precio')
            if precio <= 0:
                raise ValueError('Precio inválido en opción de precio')
        elif producto and (
            producto.codigo == REPARACION_COSTO_BASE_CODIGO
            and item.get('precio_manual')
            and item.get('precio') is not None
        ):
            try:
                precio = Decimal(str(item.get('precio')))
            except Exception:
                raise ValueError('Precio inválido para costo final de reparación')
            if precio < 0:
                raise ValueError('Precio inválido para costo final de reparación')
        elif producto and usar_precio_mayorista:
            try:
                if producto.precio_mayorista is not None:
                    precio_may = Decimal(str(producto.precio_mayorista))
                    if precio_may > 0:
                        precio = precio_may
            except Exception:
                precio = precio_original

        if producto:
            item_subtotal, promocion_activa = calculate_queue_product_subtotal(
                producto=producto,
                precio=precio,
                cantidad=cantidad,
                precio_opcion_id=precio_opcion_id,
                precio_manual=item.get('precio_manual'),
                usar_precio_mayorista=usar_precio_mayorista,
                promotions=promociones_por_producto,
            )
        else:
            item_subtotal = precio * cantidad
            promocion_activa = None
        subtotal += item_subtotal

        try:
            precio_mayorista = float(producto.precio_mayorista) if producto and producto.precio_mayorista is not None else None
        except Exception:
            precio_mayorista = None

        items_normalizados.append({
            'tipo': 'servicio' if servicio else 'producto',
            'id': int(servicio.id_servicio if servicio else producto.id_producto),
            'id_producto': int(producto.id_producto) if producto else None,
            'id_servicio': int(servicio.id_servicio) if servicio else None,
            'codigo': ((servicio.codigo if servicio else producto.codigo) or '').strip(),
            'nombre': ((servicio.nombre if servicio else producto.nombre) or '').strip(),
            'precio': float(precio),
            'precio_base': float(precio_original),
            'precio_mayorista': precio_mayorista,
            'cantidad': int(cantidad),
            'subtotal': float(item_subtotal),
            'subtotal_cantidad': int(cantidad),
            'promocion_activa': promocion_activa,
            'es_servicio': bool(servicio or producto.es_servicio),
            'stock': int(producto.stock_actual or 0) if producto else 0,
            'stock_minimo': int(producto.stock_minimo or 0) if producto else 0,
            'iva': int((servicio.porcentaje_iva if servicio else producto.porcentaje_iva) or 0),
            'precio_manual': bool(item.get('precio_manual') is True),
            'precio_opcion_id': int(precio_opcion_id) if precio_opcion_id not in (None, '') else None,
        })

    return items_normalizados, subtotal

def _build_pos_data_from_cola_cobro(item_cola):
    metadata = item_cola.get_metadata()
    items_metadata = metadata.get('items') if isinstance(metadata.get('items'), list) else []
    ids_productos = []
    ids_servicios = []
    for item in items_metadata:
        if (item.get('tipo') or '').strip().lower() == 'servicio' or item.get('id_servicio') not in (None, ''):
            try:
                ids_servicios.append(int(item.get('id_servicio') or item.get('id')))
            except Exception:
                continue
        else:
            try:
                ids_productos.append(int(item.get('id_producto') or item.get('id')))
            except Exception:
                continue

    productos = {}
    if ids_productos:
        productos = {
            int(p.id_producto): p
            for p in Producto.query.filter(Producto.id_producto.in_(ids_productos)).all()
        }
    servicios = {}
    if ids_servicios:
        servicios = {
            int(s.id_servicio): s
            for s in Servicio.query.filter(Servicio.id_servicio.in_(ids_servicios)).all()
        }

    items = []
    for item in items_metadata:
        tipo_item = (item.get('tipo') or 'producto').strip().lower()
        try:
            id_item = int(item.get('id_servicio') or item.get('id_producto') or item.get('id'))
        except Exception:
            continue
        producto = None if tipo_item == 'servicio' else productos.get(id_item)
        servicio = servicios.get(id_item) if tipo_item == 'servicio' else None
        stock_actual = int(getattr(producto, 'stock_actual', item.get('stock', 0)) or 0) if producto else 0
        stock_minimo = int(getattr(producto, 'stock_minimo', item.get('stock_minimo', 0)) or 0) if producto else 0
        es_servicio = bool(servicio or getattr(producto, 'es_servicio', item.get('es_servicio', False)))
        iva = int(getattr(servicio or producto, 'porcentaje_iva', item.get('iva', 0)) or 0)

        try:
            precio_mayorista = float(getattr(producto, 'precio_mayorista', item.get('precio_mayorista'))) if producto else None
        except Exception:
            precio_mayorista = item.get('precio_mayorista')

        items.append({
            'tipo': tipo_item,
            'id_item': id_item,
            'id_servicio': id_item if tipo_item == 'servicio' else None,
            'id_producto': id_item if tipo_item != 'servicio' else None,
            'id': id_item,
            'codigo': (item.get('codigo') or getattr(servicio or producto, 'codigo', '') or '').strip(),
            'nombre': (item.get('nombre') or getattr(servicio or producto, 'nombre', '') or f'Item #{id_item}').strip(),
            'precio': float(item.get('precio') or 0),
            'precio_base': float(item.get('precio_base') or getattr(servicio or producto, 'precio', getattr(producto, 'precio_venta', 0)) or 0),
            'precio_mayorista': precio_mayorista,
            'cantidad': int(item.get('cantidad') or 0),
            'subtotal': item.get('subtotal'),
            'subtotal_cantidad': item.get('subtotal_cantidad'),
            'promocion_activa': item.get('promocion_activa'),
            'es_servicio': es_servicio,
            'stock': stock_actual,
            'stock_minimo': stock_minimo,
            'iva': iva,
            'precio_manual': bool(item.get('precio_manual') is True),
            'precio_opcion_id': item.get('precio_opcion_id'),
        })

    reparacion_id = None
    if item_cola.tipo_origen == 'reparacion':
        try:
            reparacion_id = int(metadata.get('reparacion_id') or item_cola.id_origen or 0) or None
        except Exception:
            reparacion_id = None

    return {
        'id': int(item_cola.id),
        'tipo_origen': item_cola.tipo_origen,
        'cliente_id': int(item_cola.id_cliente or 1),
        'cliente_servicio_id': metadata.get('cliente_servicio_id'),
        'cliente_servicio_ids': metadata.get('cliente_servicio_ids') if isinstance(metadata.get('cliente_servicio_ids'), list) else [],
        'agenda_actividad_id': metadata.get('agenda_actividad_id'),
        'reparacion_id': reparacion_id,
        'id_usuario_vendedor': int(metadata.get('id_usuario_vendedor') or item_cola.id_usuario_origen),
        'descuento': float(metadata.get('descuento') or 0),
        'beneficio_fidelizacion_id': metadata.get('beneficio_fidelizacion_id'),
        'observaciones': (metadata.get('observaciones') or '').strip(),
        'gastronomia_pedido_id': metadata.get('gastronomia_pedido_id'),
        'gastronomia_codigo_entrega': (metadata.get('gastronomia_codigo_entrega') or '').strip(),
        'gastronomia_referencia_entrega': (metadata.get('gastronomia_referencia_entrega') or '').strip(),
        'gastronomia_tipo_pedido': (metadata.get('gastronomia_tipo_pedido') or '').strip(),
        'gastronomia_mesa': (metadata.get('gastronomia_mesa') or '').strip(),
        'items': items,
    }

def _build_venta_items_payload_from_pos_items(items_pos):
    items_payload = []
    for item_pos in items_pos or []:
        tipo_item = (item_pos.get('tipo') or 'producto').strip().lower()
        try:
            id_item = int(item_pos.get('id_servicio') or item_pos.get('id_producto') or item_pos.get('id'))
            cantidad = int(item_pos.get('cantidad') or 0)
        except Exception:
            continue

        items_payload.append({
            'tipo': tipo_item,
            'id_producto': id_item if tipo_item != 'servicio' else None,
            'id_servicio': id_item if tipo_item == 'servicio' else None,
            'cantidad': cantidad,
            'subtotal': item_pos.get('subtotal'),
            'subtotal_cantidad': item_pos.get('subtotal_cantidad'),
            'precio': float(item_pos.get('precio') or 0),
            'precio_base': item_pos.get('precio_base'),
            'precio_manual': bool(item_pos.get('precio_manual') is True),
            'precio_opcion_id': item_pos.get('precio_opcion_id'),
            'nombre': item_pos.get('nombre'),
            'codigo': item_pos.get('codigo'),
        })
    return items_payload

def _get_or_create_producto_costo_final_reparacion():
    producto = Producto.query.filter_by(codigo=REPARACION_COSTO_BASE_CODIGO).first()
    if producto:
        return producto

    categoria = Categoria.query.filter_by(nombre=REPARACION_SERVICIOS_CATEGORIA).first()
    if not categoria:
        categoria = Categoria(nombre=REPARACION_SERVICIOS_CATEGORIA, activo=True)
        db.session.add(categoria)
        db.session.flush()

    producto = Producto(
        codigo=REPARACION_COSTO_BASE_CODIGO,
        nombre=REPARACION_COSTO_BASE_NOMBRE,
        id_categoria=categoria.id_categoria,
        precio_compra=0,
        precio_venta=0,
        porcentaje_iva=10,
        stock_actual=0,
        stock_minimo=0,
        es_servicio=True,
        activo=True,
    )
    db.session.add(producto)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        producto = Producto.query.filter_by(codigo=REPARACION_COSTO_BASE_CODIGO).first()
        if producto:
            return producto
        raise
    return producto

def _enforce_ticket_light_background(html: str) -> str:
    """
    Sanitiza el HTML del ticket para asegurar compatibilidad con impresoras térmicas.
    - Elimina display:flex que causa fragmentación del texto
    - Fuerza fondo blanco y texto negro
    - Aplica estilos compatibles con impresoras POS
    """
    css = (
        "<style>"
        "@page{size:58mm auto !important;margin:0 !important;}"
        "html,body{background:#fff !important;color:#000 !important;margin:0 !important;padding:0 !important;}"
        "body{width:58mm !important;max-width:58mm !important;padding:2mm !important;"
        "font-family:'Courier New',Courier,monospace !important;font-size:11px !important;line-height:1.3 !important;}"
        "*,*:before,*:after{box-sizing:border-box !important;}"
        "div,span,td,th,p{word-break:normal !important;overflow-wrap:break-word !important;}"
        # IMPORTANTE: Sobrescribir flexbox que causa problemas en impresoras térmicas
        "[style*='flex'],[style*='display:flex'],[style*='display: flex']{display:block !important;}"
        ".flex,.d-flex{display:block !important;}"
        "</style>"
    )
    try:
        if not html:
            return html
        
        # Eliminar display:flex inline que causa problemas en impresoras térmicas
        html = re.sub(r'display\s*:\s*flex\s*;?', 'display:block;', html, flags=re.IGNORECASE)
        html = re.sub(r'justify-content\s*:\s*[^;]+;?', '', html, flags=re.IGNORECASE)
        html = re.sub(r'gap\s*:\s*[^;]+;?', '', html, flags=re.IGNORECASE)
        
        if re.search(r"<head[^>]*>", html, flags=re.IGNORECASE):
            return re.sub(r"(<head[^>]*>)", r"\1" + css, html, count=1, flags=re.IGNORECASE)
        if re.search(r"<html[^>]*>", html, flags=re.IGNORECASE):
            return re.sub(r"(<html[^>]*>)", r"\1<head>" + css + "</head>", html, count=1, flags=re.IGNORECASE)
        return "<!doctype html><html><head>" + css + "</head><body>" + html + "</body></html>"
    except Exception:
        return html

def _normalize_ticket_template_signature(template_html: str) -> str:
    return re.sub(r'\s+', '', (template_html or '').strip()).lower()

def _should_use_builtin_sales_ticket_template(template_html: str) -> bool:
    """
    Detecta copias guardadas de la plantilla estándar de ventas para que
    las mejoras del template oficial apliquen también a configuraciones ya guardadas.
    """
    normalized = _normalize_ticket_template_signature(template_html)
    if not normalized:
        return False

    markers = (
        '<title>ticketventa#{{venta.id_venta}}</title>',
        '<table><trclass="info-row"><tdclass="info-label">venta:</td>',
        '<thclass="leftcol-prod">producto</th>',
        "{{footer_text|default('graciasporsucompra')|thermal_safe}}",
        'window.print();',
    )
    return all(marker in normalized for marker in markers)

def _build_pagos_resumen(pagos):
    resumen = {}

    def _sort_key_for_pago(p):
        try:
            orden = int(p.metodo.orden_display) if getattr(p, 'metodo', None) and p.metodo.orden_display is not None else 999
        except Exception:
            orden = 999
        try:
            nombre = (p.metodo.nombre or '').strip().lower() if getattr(p, 'metodo', None) else ''
        except Exception:
            nombre = ''
        return (orden, nombre)

    pagos_ordenados = sorted(list(pagos or []), key=_sort_key_for_pago)
    for pago in pagos_ordenados:
        try:
            nombre = (pago.metodo.nombre if pago.metodo else '') or 'Pago'
            nombre = str(nombre).strip() or 'Pago'
        except Exception:
            nombre = 'Pago'
        try:
            monto = float(pago.monto or 0)
        except Exception:
            monto = 0.0
        ref = None
        try:
            ref = (pago.referencia or '').strip() or None
        except Exception:
            ref = None

        entry = resumen.get(nombre)
        if not entry:
            entry = {
                'nombre': nombre,
                'monto': 0.0,
                'referencias': set(),
                'orden': _sort_key_for_pago(pago)[0],
            }
            resumen[nombre] = entry
        entry['monto'] += monto
        if ref:
            entry['referencias'].add(ref)

    items = []
    for entry in resumen.values():
        refs = sorted(entry['referencias'])
        items.append({
            'nombre': entry['nombre'],
            'monto': float(entry['monto']),
            'referencias': refs,
            'orden': entry['orden'],
        })
    items.sort(key=lambda x: (x['orden'], str(x['nombre']).lower()))
    return items

@ventas_bp.route('/')
@login_required
def listar():
    """Lista de ventas"""
    if not current_user.tiene_permiso('ver_ventas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver ventas.', 'danger')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    
    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')
    desde = parse_iso_date(raw_desde)
    hasta = parse_iso_date(raw_hasta)
    
    query = Venta.query

    # Si el usuario no puede ver otras cajas, filtrar solo sus propias ventas
    puede_ver_otras_cajas = current_user.es_admin() or current_user.tiene_permiso('ver_otras_cajas')
    if not puede_ver_otras_cajas:
        mis_sesiones = (
            db.session.query(SesionCaja.id_sesion)
            .filter(SesionCaja.id_usuario == current_user.id_usuario)
            .subquery()
        )
        query = query.filter(Venta.id_sesion_caja.in_(mis_sesiones))

    if desde or hasta:
        if not desde:
            desde = hasta
        if not hasta:
            hasta = desde
        if desde and hasta and desde > hasta:
            desde, hasta = hasta, desde
        start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
        query = query.filter(
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc
        )
        
    ventas = query.options(
        joinedload(Venta.cliente),
        joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
        joinedload(Venta.vendedor),
        joinedload(Venta.reparacion)
    ).order_by(Venta.fecha_venta.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    detalles_por_venta = {}
    venta_ids = [v.id_venta for v in ventas.items]
    if venta_ids:
        obs_by_id = {v.id_venta: (v.observaciones or '').strip() for v in ventas.items}
        for v in ventas.items:
            txt = ''
            rep = getattr(v, 'reparacion', None)
            if rep is not None:
                txt = (rep.solucion or rep.diagnostico_tecnico or rep.falla_reportada or '').strip()
                txt = f"Reparación: {txt}" if txt else "Reparación"
            detalles_por_venta[v.id_venta] = txt

        rows = (
            db.session.query(
                DetalleVenta.id_venta,
                Producto.nombre,
                db.func.sum(DetalleVenta.cantidad).label('cantidad')
            )
            .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
            .filter(DetalleVenta.id_venta.in_(venta_ids))
            .group_by(DetalleVenta.id_venta, Producto.nombre)
            .order_by(DetalleVenta.id_venta.asc(), Producto.nombre.asc())
            .all()
        )

        agrupado = {}
        for id_venta, nombre, cantidad in rows:
            if int(id_venta) not in agrupado:
                agrupado[int(id_venta)] = []
            try:
                cant_int = int(cantidad or 0)
            except Exception:
                cant_int = 0
            agrupado[int(id_venta)].append((nombre, cant_int))

        for id_venta in venta_ids:
            if detalles_por_venta.get(id_venta):
                continue
            partes = []
            for nombre, cant_int in agrupado.get(int(id_venta), []):
                if cant_int and cant_int != 1:
                    partes.append(f"{nombre} x{cant_int}")
                else:
                    partes.append(f"{nombre}")
            texto = ", ".join([p for p in partes if p]) or obs_by_id.get(id_venta, '')
            detalles_por_venta[id_venta] = texto
    
    return render_template(
        'ventas/listar.html',
        ventas=ventas,
        detalles_por_venta=detalles_por_venta,
        desde=(desde.isoformat() if desde else (raw_desde or '')),
        hasta=(hasta.isoformat() if hasta else (raw_hasta or ''))
    )

def _usuario_puede_tomar_cola_cobro():
    return current_user.es_admin() or current_user.tiene_permiso('tomar_cola_cobro')

def _modo_cobro_exclusivo_cajero_activo():
    return (
        Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
        and Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
    )

@ventas_bp.app_context_processor
def _inject_sidebar_ventas_flags():
    if not getattr(current_user, 'is_authenticated', False):
        return {
            'sidebar_modo_cobro_exclusivo_cajero': False,
            'sidebar_mostrar_pos': False,
            'sidebar_mostrar_registro_vendedor': False,
        }

    puede_crear_venta = current_user.tiene_permiso('crear_venta')
    modo_exclusivo = _modo_cobro_exclusivo_cajero_activo() if puede_crear_venta else False
    puede_tomar_cola = _usuario_puede_tomar_cola_cobro() if puede_crear_venta else False

    mostrar_registro_vendedor = bool(puede_crear_venta and modo_exclusivo and not puede_tomar_cola)
    mostrar_pos = bool(puede_crear_venta and not mostrar_registro_vendedor)
    return {
        'sidebar_modo_cobro_exclusivo_cajero': bool(modo_exclusivo),
        'sidebar_mostrar_pos': mostrar_pos,
        'sidebar_mostrar_registro_vendedor': mostrar_registro_vendedor,
    }

@ventas_bp.route('/validar-carrito', methods=['POST'])
@login_required
def validar_carrito():
    """Validar productos del carrito guardado - retorna datos actualizados"""
    try:
        data = request.get_json()
        ids_productos = data.get('ids', [])
        
        if not ids_productos:
            return jsonify({'productos': {}})
        
        ids_normalizados = []
        for id_producto in ids_productos:
            try:
                id_int = int(id_producto)
            except (TypeError, ValueError):
                continue
            if id_int not in ids_normalizados:
                ids_normalizados.append(id_int)

        if not ids_normalizados:
            return jsonify({'productos': {}})

        productos = (
            Producto.query
            .filter(Producto.id_producto.in_(ids_normalizados))
            .all()
        )
        productos_map = {int(producto.id_producto): producto for producto in productos}
        from app.services.ventas_promociones import get_serialized_active_product_promotions
        promociones_por_producto = get_serialized_active_product_promotions(ids_normalizados)

        opciones_por_producto = {}
        opciones = (
            ProductoPrecioOpcion.query
            .filter(
                ProductoPrecioOpcion.activo.is_(True),
                ProductoPrecioOpcion.id_producto.in_(ids_normalizados),
            )
            .order_by(
                ProductoPrecioOpcion.id_producto.asc(),
                ProductoPrecioOpcion.orden.asc(),
                ProductoPrecioOpcion.id_opcion_precio.asc(),
            )
            .all()
        )
        for opcion in opciones:
            opciones_por_producto.setdefault(int(opcion.id_producto), []).append(opcion)

        productos_validados = {}
        for id_producto in ids_normalizados:
            producto = productos_map.get(id_producto)
            if producto and producto.activo:
                productos_validados[str(id_producto)] = {
                    'existe': True,
                    'codigo': producto.codigo,
                    'nombre': producto.nombre,
                    'precio': float(producto.precio_venta),
                    'precio_mayorista': float(producto.precio_mayorista) if producto.precio_mayorista else None,
                    'precios_opciones': [
                        {
                            'id': int(o.id_opcion_precio),
                            'etiqueta': (o.etiqueta or '').strip() or None,
                            'precio': float(o.precio or 0),
                        }
                        for o in opciones_por_producto.get(id_producto, [])
                    ],
                    'stock': producto.stock_actual,
                    'stock_minimo': producto.stock_minimo,
                    'es_servicio': producto.es_servicio,
                    'iva': producto.porcentaje_iva,
                    'promocion_activa': promociones_por_producto.get(id_producto)
                }
            else:
                productos_validados[str(id_producto)] = {
                    'existe': False
                }
        
        return jsonify({'productos': productos_validados})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



__all__ = [name for name in globals() if not name.startswith('__')]
