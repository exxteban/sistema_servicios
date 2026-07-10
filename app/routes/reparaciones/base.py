"""
Rutas de gestión de reparaciones (Servicio Técnico)
"""
import re

from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (
    Categoria,
    Cliente,
    ColaCobro,
    Configuracion,
    DetalleReparacion,
    Producto,
    Reparacion,
    Rol,
    Usuario,
    Venta,
)
from app.services.system_modules import CLAVE_MODULO_SERVICIO_TECNICO, system_module_enabled


reparaciones_bp = Blueprint('reparaciones', __name__)
_normalizacion_numericos_ejecutada = False
_normalizacion_horas_ejecutada = False
ROLES_VENDEDOR_CAJERO = {'vendedor', 'cajero', 'administrador'}
CLAVE_CAJA_FLUJO_ENVIADO = 'caja_flujo_enviado_desde_vendedor'
CLAVE_CAJA_EXIGIR_CAJERO = 'caja_exigir_cajero_para_cobro'
CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO = 'reparacion_whatsapp_mensaje_link'
MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT = 'Hola! Este es su link de {empresa} para ver el estado de reparación de su equipo:\n\n{link}'
REPARACION_COSTO_BASE_CODIGO = 'SRV-REP-COSTO-BASE'
REPARACION_COSTO_BASE_NOMBRE = 'Costo final reparación (base)'
REPARACION_SERVICIOS_CATEGORIA = 'Servicios de Reparación'
REPARACION_TICKET_FOOTER_DEFAULT = (
    'Este documento es el único comprobante para el retiro del equipo. '
    'Una vez aceptado el presupuesto, los equipos deben ser retirados dentro de los 30 días; '
    'en caso contrario, el equipo será considerado como abandono y la empresa se hará cargo del mismo.'
)

# El flujo no es lineal: una reparación entregada puede reabrirse tras una
# anulación, pero no debe poder saltar arbitrariamente entre estados.
TRANSICIONES_ESTADO_REPARACION = {
    'pendiente': {'diagnostico', 'espera_presupuesto', 'en_proceso', 'cancelado'},
    'diagnostico': {'espera_presupuesto', 'espera_repuesto', 'espera_cliente', 'en_proceso', 'listo', 'no_se_pudo', 'cancelado'},
    'espera_presupuesto': {'diagnostico', 'espera_repuesto', 'espera_cliente', 'en_proceso', 'cancelado'},
    'espera_repuesto': {'diagnostico', 'espera_presupuesto', 'espera_cliente', 'en_proceso', 'cancelado'},
    'espera_cliente': {'diagnostico', 'espera_presupuesto', 'espera_repuesto', 'en_proceso', 'listo', 'no_se_pudo', 'cancelado'},
    'en_proceso': {'espera_repuesto', 'espera_cliente', 'listo', 'no_se_pudo', 'cancelado'},
    'listo': {'en_proceso', 'espera_cliente', 'entregado', 'cancelado'},
    'no_se_pudo': {'diagnostico', 'en_proceso', 'cancelado'},
    'entregado': {'listo', 'en_proceso'},
    'cancelado': {'pendiente'},
    'antiguos': {'pendiente'},
}


def _modulo_servicio_tecnico_activo() -> bool:
    return system_module_enabled(CLAVE_MODULO_SERVICIO_TECNICO, default=True)


@reparaciones_bp.before_request
def _require_modulo_servicio_tecnico_activo():
    if _modulo_servicio_tecnico_activo():
        return None

    mensaje = 'El modulo de servicio tecnico esta desactivado.'
    wants_json = (
        request.is_json
        or '/items/' in request.path
        or request.path.endswith('/costos')
        or request.path.endswith('/preview')
        or request.path.endswith('/generar_venta')
        or request.path.endswith('/enviar_a_caja')
        or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
    )
    if wants_json:
        return jsonify({'error': 'Modulo desactivado', 'mensaje': mensaje, 'modulo': 'servicio_tecnico'}), 403

    flash(mensaje, 'warning')
    return redirect(url_for('main.dashboard'))


def _usuarios_vendedores_cajeros_activos():
    return (
        Usuario.query
        .join(Rol, Usuario.id_rol == Rol.id_rol)
        .filter(
            Usuario.activo == True,
            Rol.activo == True,
            func.lower(Rol.nombre).in_(ROLES_VENDEDOR_CAJERO)
        )
        .order_by(Usuario.nombre_completo.asc())
        .all()
    )


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
    db.session.flush()
    return producto


def _buscar_pendiente_cobro_reparacion_activa(id_reparacion):
    return (
        ColaCobro.query
        .filter(
            ColaCobro.tipo_origen == 'reparacion',
            ColaCobro.id_origen == id_reparacion,
            ColaCobro.estado.in_(['pendiente', 'en_proceso'])
        )
        .order_by(ColaCobro.fecha_envio.desc(), ColaCobro.id.desc())
        .first()
    )


def _reparacion_tiene_conceptos_cobrables(reparacion):
    try:
        if float(reparacion.costo_final or 0) > 0:
            return True
    except Exception:
        pass
    try:
        return reparacion.detalles.filter_by(incluye_costo_final=True).count() > 0
    except Exception:
        return False


def _reparacion_tiene_saldo_pendiente(reparacion):
    try:
        return float(reparacion.saldo_pendiente or 0) > 0
    except Exception:
        return False


def _reparacion_tiene_venta_cobrada(reparacion):
    """Una venta vigente convierte la orden en un comprobante inmutable."""
    return db.session.query(Venta.id_venta).filter(
        Venta.id_reparacion == reparacion.id_reparacion,
        Venta.estado != 'anulada',
    ).first() is not None


def _reparacion_tiene_cobro_en_proceso(reparacion):
    return _buscar_pendiente_cobro_reparacion_activa(reparacion.id_reparacion) is not None


def _motivo_bloqueo_financiero_reparacion(reparacion):
    if _reparacion_tiene_venta_cobrada(reparacion):
        return 'La reparación ya fue cobrada y no se pueden modificar sus importes ni sus items.'
    if _reparacion_tiene_cobro_en_proceso(reparacion):
        return 'La reparación ya está enviada a caja; cancele el pendiente antes de modificar importes o items.'
    return None


def _transicion_estado_reparacion_permitida(estado_anterior, estado_nuevo):
    anterior = (estado_anterior or '').strip().lower()
    nuevo = (estado_nuevo or '').strip().lower()
    return anterior == nuevo or nuevo in TRANSICIONES_ESTADO_REPARACION.get(anterior, set())


def _importes_reparacion_validos(*importes):
    """Los costos y abonos nunca pueden ser negativos."""
    try:
        return all(float(importe or 0) >= 0 for importe in importes)
    except (TypeError, ValueError):
        return False


def _abono_reparacion_valido(costo_estimado, costo_final, abono):
    """El abono se aplica al importe efectivo que se cobrará."""
    if not _importes_reparacion_validos(costo_estimado, costo_final, abono):
        return False
    final = float(costo_final or 0)
    estimado = float(costo_estimado or 0)
    total = final if final > 0 else estimado
    return float(abono or 0) <= total


def _mensaje_importes_reparacion(costo_estimado, costo_final, abono):
    if not _importes_reparacion_validos(costo_estimado, costo_final, abono):
        return 'Los importes no pueden ser negativos.'
    if not _abono_reparacion_valido(costo_estimado, costo_final, abono):
        return 'El abono no puede superar el importe efectivo de la reparación.'
    return None


def _puede_cobrar_reparacion_pos(usuario):
    if usuario.es_admin():
        return True
    return (
        usuario.tiene_permiso('cobrar_reparacion')
        or usuario.tiene_permiso('cobrar_reparaciones')
    )


def _puede_cambiar_estado_reparacion(usuario):
    if usuario.es_admin():
        return True
    return (
        usuario.tiene_permiso('cambiar_estado_reparacion')
        or usuario.tiene_permiso('editar_reparacion')
    )


def _construir_items_cola_cobro_reparacion(reparacion):
    items = []
    costo_final_base = float(reparacion.costo_final or 0)
    detalles_cobrables = reparacion.detalles.filter_by(incluye_costo_final=True).all()

    if costo_final_base > 0:
        producto_base = _get_or_create_producto_costo_final_reparacion()
        solucion_txt = (reparacion.solucion or '').strip()
        nombre_base = f"Solución: {solucion_txt}" if solucion_txt else producto_base.nombre
        items.append({
            'id': int(producto_base.id_producto),
            'codigo': '',
            'nombre': nombre_base,
            'precio': costo_final_base,
            'precio_base': costo_final_base,
            'precio_mayorista': None,
            'cantidad': 1,
            'es_servicio': True,
            'stock': 0,
            'stock_minimo': 0,
            'iva': int(producto_base.porcentaje_iva or 10),
            'precio_manual': True,
            'precio_opcion_id': None,
        })

    for det in detalles_cobrables:
        producto = det.producto or db.session.get(Producto, det.id_producto)
        if not producto:
            raise ValueError(f'Producto no encontrado para detalle #{det.id_detalle}')

        try:
            precio_mayorista = float(producto.precio_mayorista) if producto.precio_mayorista is not None else None
        except Exception:
            precio_mayorista = None

        items.append({
            'id': int(det.id_producto),
            'codigo': (producto.codigo or '').strip(),
            'nombre': (det.nombre_producto or producto.nombre or '').strip() or f'Producto #{det.id_producto}',
            'precio': float(det.precio_unitario or 0),
            'precio_base': float(producto.precio_venta or det.precio_unitario or 0),
            'precio_mayorista': precio_mayorista,
            'cantidad': int(det.cantidad or 0),
            'es_servicio': bool(det.es_servicio),
            'stock': int(producto.stock_actual or 0),
            'stock_minimo': int(producto.stock_minimo or 0),
            'iva': int(producto.porcentaje_iva or 0),
            'precio_manual': False,
            'precio_opcion_id': None,
        })

    if not items:
        raise ValueError('No hay costo final ni items marcados para cobrar')

    total = float(reparacion.costo_final_calculado or 0)
    if total <= 0:
        total = sum(float(item.get('precio') or 0) * int(item.get('cantidad') or 0) for item in items)
    if total <= 0:
        raise ValueError('El total de la reparación debe ser mayor a cero')

    return items, total


def _build_pendiente_cobro_reparacion(reparacion, usuario_actual):
    items, total_bruto = _construir_items_cola_cobro_reparacion(reparacion)
    descuento = float(reparacion.abono or 0)
    total = float(total_bruto or 0) - descuento
    if total <= 0:
        raise ValueError('La reparación no tiene saldo pendiente para enviar a caja')

    id_usuario_origen = int(reparacion.id_usuario_vendedor or usuario_actual.id_usuario)
    observaciones = (reparacion.solucion or reparacion.diagnostico_tecnico or reparacion.falla_reportada or '').strip()
    metadata = {
        'reparacion_id': int(reparacion.id_reparacion),
        'id_usuario_vendedor': id_usuario_origen,
        'descuento': descuento,
        'abono': descuento,
        'observaciones': observaciones,
        'items': items,
    }

    pendiente = ColaCobro(
        tipo_origen='reparacion',
        id_origen=reparacion.id_reparacion,
        id_cliente=reparacion.cliente_id,
        monto_total=total,
        id_usuario_origen=id_usuario_origen,
        estado='pendiente',
    )
    pendiente.set_metadata(metadata)
    return pendiente


def _obtener_o_crear_pendiente_cobro_reparacion(reparacion, usuario_actual):
    pendiente_existente = _buscar_pendiente_cobro_reparacion_activa(reparacion.id_reparacion)
    if pendiente_existente:
        return pendiente_existente, False

    pendiente = _build_pendiente_cobro_reparacion(reparacion, usuario_actual)
    db.session.add(pendiente)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        pendiente_existente = _buscar_pendiente_cobro_reparacion_activa(reparacion.id_reparacion)
        if pendiente_existente:
            return pendiente_existente, False
        raise

    return pendiente, True


def _a_float_seguro(valor, default=0.0):
    if valor is None:
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return default
    texto = re.sub(r'[^0-9,\.\-]', '', texto)
    if not texto or texto in {'-', '.', ',', '-.', '-,'}:
        return default
    negativo = texto.startswith('-')
    texto = texto.lstrip('-')
    if not texto:
        return default

    if ',' in texto and '.' in texto:
        decimal_sep = ',' if texto.rfind(',') > texto.rfind('.') else '.'
        miles_sep = '.' if decimal_sep == ',' else ','
        texto = texto.replace(miles_sep, '')
        if decimal_sep == ',':
            texto = texto.replace(',', '.')
    elif ',' in texto:
        partes = [parte for parte in texto.split(',') if parte != '']
        if not partes:
            return default
        if len(partes) > 1 and len(partes[-1]) == 3:
            texto = ''.join(partes)
        elif len(partes) > 1:
            texto = ''.join(partes[:-1]) + '.' + partes[-1]
        else:
            texto = partes[0]
    elif '.' in texto:
        partes = [parte for parte in texto.split('.') if parte != '']
        if not partes:
            return default
        if len(partes) > 1 and len(partes[-1]) == 3:
            texto = ''.join(partes)
        elif len(partes) > 1:
            texto = ''.join(partes[:-1]) + '.' + partes[-1]
        else:
            texto = partes[0]

    if negativo:
        texto = f'-{texto}'
    try:
        return float(texto)
    except Exception:
        return default


def _normalizar_numericos_reparacion(id_reparacion):
    raw = db.session.query(
        Reparacion.id_reparacion,
        db.cast(Reparacion.costo_estimado, db.String).label('costo_estimado_raw'),
        db.cast(Reparacion.costo_final, db.String).label('costo_final_raw'),
        db.cast(Reparacion.abono, db.String).label('abono_raw'),
    ).filter_by(id_reparacion=id_reparacion).first()
    if not raw:
        return

    db.session.query(Reparacion).filter_by(id_reparacion=id_reparacion).update({
        Reparacion.costo_estimado: _a_float_seguro(raw.costo_estimado_raw),
        Reparacion.costo_final: _a_float_seguro(raw.costo_final_raw),
        Reparacion.abono: _a_float_seguro(raw.abono_raw),
    }, synchronize_session=False)

    detalle_rows = db.session.query(
        DetalleReparacion.id_detalle,
        db.cast(DetalleReparacion.precio_unitario, db.String).label('precio_unitario_raw'),
        db.cast(DetalleReparacion.subtotal, db.String).label('subtotal_raw'),
    ).filter_by(id_reparacion=id_reparacion).all()

    for det in detalle_rows:
        db.session.query(DetalleReparacion).filter_by(id_detalle=det.id_detalle).update({
            DetalleReparacion.precio_unitario: _a_float_seguro(det.precio_unitario_raw),
            DetalleReparacion.subtotal: _a_float_seguro(det.subtotal_raw),
        }, synchronize_session=False)

    db.session.commit()


def _normalizar_numericos_reparaciones_global():
    global _normalizacion_numericos_ejecutada
    if _normalizacion_numericos_ejecutada:
        return
    _normalizacion_numericos_ejecutada = True
    try:
        reparaciones_rows = db.session.query(
            Reparacion.id_reparacion,
            db.cast(Reparacion.costo_estimado, db.String).label('costo_estimado_raw'),
            db.cast(Reparacion.costo_final, db.String).label('costo_final_raw'),
            db.cast(Reparacion.abono, db.String).label('abono_raw'),
        ).all()
        for row in reparaciones_rows:
            db.session.query(Reparacion).filter_by(id_reparacion=row.id_reparacion).update({
                Reparacion.costo_estimado: _a_float_seguro(row.costo_estimado_raw),
                Reparacion.costo_final: _a_float_seguro(row.costo_final_raw),
                Reparacion.abono: _a_float_seguro(row.abono_raw),
            }, synchronize_session=False)

        detalle_rows = db.session.query(
            DetalleReparacion.id_detalle,
            db.cast(DetalleReparacion.precio_unitario, db.String).label('precio_unitario_raw'),
            db.cast(DetalleReparacion.subtotal, db.String).label('subtotal_raw'),
        ).all()
        for det in detalle_rows:
            db.session.query(DetalleReparacion).filter_by(id_detalle=det.id_detalle).update({
                DetalleReparacion.precio_unitario: _a_float_seguro(det.precio_unitario_raw),
                DetalleReparacion.subtotal: _a_float_seguro(det.subtotal_raw),
            }, synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        _normalizacion_numericos_ejecutada = False


def _normalizar_hora_estimada_invalida(id_reparacion):
    db.session.execute(text(
        """
        UPDATE reparaciones
        SET fecha_estimada_hora = NULL
        WHERE id_reparacion = :id_reparacion
          AND fecha_estimada_hora IS NOT NULL
          AND TRIM(fecha_estimada_hora) = ''
        """
    ), {'id_reparacion': id_reparacion})
    db.session.commit()


def _normalizar_horas_estimadas_invalidas_global():
    global _normalizacion_horas_ejecutada
    if _normalizacion_horas_ejecutada:
        return
    _normalizacion_horas_ejecutada = True
    try:
        db.session.execute(text(
            """
            UPDATE reparaciones
            SET fecha_estimada_hora = NULL
            WHERE fecha_estimada_hora IS NOT NULL
              AND TRIM(fecha_estimada_hora) = ''
            """
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        _normalizacion_horas_ejecutada = False


def _get_reparacion_or_404_safe(id_reparacion):
    try:
        reparacion = db.session.get(Reparacion, id_reparacion)
        if not reparacion:
            abort(404)
        return reparacion
    except Exception as exc:
        err = str(exc)
        if 'must be real number, not str' in err:
            db.session.rollback()
            _normalizar_numericos_reparacion(id_reparacion)
            db.session.expire_all()
            reparacion = db.session.get(Reparacion, id_reparacion)
            if not reparacion:
                abort(404)
            return reparacion
        if 'Invalid isoformat string' in err:
            db.session.rollback()
            _normalizar_hora_estimada_invalida(id_reparacion)
            db.session.expire_all()
            reparacion = db.session.get(Reparacion, id_reparacion)
            if not reparacion:
                abort(404)
            return reparacion
        raise


def _get_detalle_reparacion_or_404_safe(id_detalle):
    try:
        detalle = db.session.get(DetalleReparacion, id_detalle)
        if not detalle:
            abort(404)
        return detalle
    except Exception as exc:
        if 'must be real number, not str' not in str(exc):
            raise
        db.session.rollback()
        raw = db.session.query(
            DetalleReparacion.id_reparacion
        ).filter_by(id_detalle=id_detalle).first()
        if raw and raw.id_reparacion:
            _normalizar_numericos_reparacion(raw.id_reparacion)
            db.session.expire_all()
        detalle = db.session.get(DetalleReparacion, id_detalle)
        if not detalle:
            abort(404)
        return detalle
