from .parte1 import *
from app.models import ClienteServicio
from .parte3_helpers import (
    _construir_detalles_venta,
    _normalizar_pagos_venta,
    _prefetch_catalogo_venta,
    _registrar_pagos_y_movimientos_venta,
    _validar_credito_cliente,
    _validar_stock_para_venta,
)
from cobranzas.services.credito_service import (
    calcular_compromiso_credito,
    crear_venta_credito,
    resolver_credito_desde_pagos,
    resolver_credito_plan_payload,
)
from app.services.clientes_fidelizacion import (
    beneficio_resumen_config,
    fidelizacion_config,
    registrar_canje_beneficio_en_venta,
    registrar_compra_fidelizacion_por_venta,
    resolver_descuento_beneficio_pos,
)
from app.services.clientes_servicios import get_cliente_servicios_cobrables, parse_cliente_servicio_ids


def _procesar_venta_payload(data):
    perf_enabled = bool((data or {}).get('debug_perf') is True)
    perf_t0 = perf_counter()
    perf_last = perf_t0
    perf_stages = []
    def _perf_stage(nombre):
        nonlocal perf_last
        if not perf_enabled:
            return
        ahora = perf_counter()
        perf_stages.append({'etapa': nombre, 'ms': round((ahora - perf_last) * 1000, 2)})
        perf_last = ahora

    if not current_user.es_admin() and not current_user.tiene_permiso('crear_venta'):
        if getattr(current_user, 'modo_demo', False):
            return {'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acci?n est? deshabilitada', 'modo_demo': True}, 403
        return {'error': 'Sin permisos', 'modo_demo': False}, 403

    data = data or {}
    client_request_id = data.get('client_request_id')
    if client_request_id:
        client_request_id = str(client_request_id).strip()
        if len(client_request_id) > 64:
            return {'error': 'client_request_id inv?lido'}, 400
        existente = Venta.query.filter_by(client_request_id=client_request_id).first()
        if existente:
            return _venta_existente_response(existente), 200

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()
    if not sesion:
        return {'error': 'No hay caja abierta'}, 400

    items = data.get('items', [])
    pagos = data.get('pagos', [])
    id_cliente = data.get('id_cliente', 1)
    id_usuario_vendedor_raw = data.get('id_usuario_vendedor')
    reparacion_id = data.get('reparacion_id')
    cliente_servicio_id = data.get('cliente_servicio_id')
    cliente_servicio_ids = parse_cliente_servicio_ids([
        data.get('cliente_servicio_ids'),
        cliente_servicio_id,
    ])
    cola_cobro_id = data.get('cola_cobro_id')
    beneficio_fidelizacion_id = data.get('beneficio_fidelizacion_id')
    usar_precio_mayorista_raw = data.get('usar_precio_mayorista', None)
    forzar_precio_mayorista_raw = data.get('forzar_precio_mayorista', False)
    _descuento_raw = data.get('descuento', 0)
    try:
        # Normalizar: string vacío o None se trata como 0
        _descuento_str = str(_descuento_raw).strip() if _descuento_raw not in (None, '') else '0'
        if _descuento_str == '':
            _descuento_str = '0'
        descuento_monto = Decimal(_descuento_str)
    except Exception:
        return {
            'error': f'El campo descuento tiene un valor inválido: "{_descuento_raw}". '
                     'Debe ser un número (ej: 0, 5000, 10000). '
                     'Si no hay descuento, envíe 0.'
        }, 400
    observaciones = data.get('observaciones', '')
    id_autorizacion = data.get('id_autorizacion')
    if id_autorizacion in (None, ''):
        id_autorizacion = None
    else:
        try:
            id_autorizacion = int(id_autorizacion)
        except Exception:
            return {'error': 'id_autorizacion invalido'}, 400

    cola_cobro = None
    cola_metadata = {}
    cola_cobro_data = None
    if cola_cobro_id not in (None, ''):
        try:
            cola_cobro_id = int(cola_cobro_id)
        except Exception:
            return {'error': 'cola_cobro_id inv?lido'}, 400
        cola_cobro = db.session.get(ColaCobro, cola_cobro_id)
        if not cola_cobro:
            return {'error': 'Pendiente de cobro no encontrado'}, 404
        if cola_cobro.tipo_origen not in ('venta', 'reparacion'):
            return {'error': 'El pendiente indicado no corresponde a un origen soportado'}, 400
        if cola_cobro.estado in ('cobrado', 'cancelado'):
            return {'error': 'Este pendiente ya no est? disponible'}, 400
        if cola_cobro.id_usuario_destino and int(cola_cobro.id_usuario_destino) != int(current_user.id_usuario):
            return {'error': 'Este pendiente est? asignado a otro cajero'}, 403
        if not current_user.es_admin() and not current_user.tiene_permiso('tomar_cola_cobro'):
            return {'error': 'Sin permisos para cobrar pendientes enviados a caja'}, 403
        if cola_cobro.estado != 'en_proceso':
            return {'error': 'Debe tomar el pendiente antes de cobrarlo'}, 409
        cola_metadata = cola_cobro.get_metadata()
        cola_cobro_data = _build_pos_data_from_cola_cobro(cola_cobro)
        items = _build_venta_items_payload_from_pos_items(cola_cobro_data.get('items'))
        id_cliente = int(cola_cobro_data.get('cliente_id') or 1)
        id_usuario_vendedor_raw = cola_cobro_data.get('id_usuario_vendedor')
        descuento_monto = Decimal(str(cola_cobro_data.get('descuento') or 0))
        beneficio_fidelizacion_id = cola_cobro_data.get('beneficio_fidelizacion_id')
        cliente_servicio_ids = parse_cliente_servicio_ids([
            cola_cobro_data.get('cliente_servicio_ids'),
            cola_cobro_data.get('cliente_servicio_id'),
        ])
        cliente_servicio_id = cliente_servicio_ids[0] if cliente_servicio_ids else None
        usar_precio_mayorista_raw = cola_metadata.get('usar_precio_mayorista', None)
        forzar_precio_mayorista_raw = cola_metadata.get('forzar_precio_mayorista', False)
        if not (observaciones or '').strip():
            observaciones = cola_cobro_data.get('observaciones') or ''
        if cola_cobro.tipo_origen == 'reparacion':
            reparacion_id_cola = cola_metadata.get('reparacion_id') or cola_cobro.id_origen
            if reparacion_id_cola not in (None, ''):
                if reparacion_id not in (None, ''):
                    try:
                        reparacion_id = int(reparacion_id)
                    except Exception:
                        return {'error': 'reparacion_id inv?lido'}, 400
                    if int(reparacion_id) != int(reparacion_id_cola):
                        return {'error': 'El pendiente no corresponde a la reparaci?n indicada'}, 400
                reparacion_id = reparacion_id_cola

    modo_cobro_exclusivo_cajero = _modo_cobro_exclusivo_cajero_activo()
    if modo_cobro_exclusivo_cajero and not current_user.es_admin():
        puede_cobrar_pendientes = current_user.tiene_permiso('tomar_cola_cobro')
        if cola_cobro is None and not puede_cobrar_pendientes:
            return {'error': 'Debe enviar la venta a caja para que un cajero complete el cobro'}, 403

    pagos_ctx, error_response = _normalizar_pagos_venta(pagos, id_autorizacion)
    if error_response:
        return error_response
    autorizacion_venta_credito = pagos_ctx['autorizacion_venta_credito']
    ids_metodo_efectivo = pagos_ctx['ids_metodo_efectivo']
    ids_metodo_credito = pagos_ctx['ids_metodo_credito']
    pagos_normalizados = pagos_ctx['pagos_normalizados']

    _perf_stage('validaciones_iniciales')

    if not items:
        return {'error': 'No hay productos en la venta'}, 400
    if descuento_monto < 0:
        return {'error': 'El descuento no puede ser negativo'}, 400

    try:
        id_cliente = int(id_cliente)
    except Exception:
        return {'error': 'Cliente inv?lido'}, 400

    cliente = db.session.get(Cliente, id_cliente)
    if not cliente or not bool(cliente.activo):
        return {'error': 'Cliente no encontrado o inactivo'}, 400

    ocultar_selector_vendedor_pos = _ocultar_selector_vendedor_pos()
    vendedores_cajeros = _usuarios_vendedores_cajeros_activos()
    ids_vendedores = {int(u.id_usuario) for u in vendedores_cajeros}
    if cola_cobro is not None:
        vendedor_origen = id_usuario_vendedor_raw or cola_cobro.id_usuario_origen or current_user.id_usuario
        try:
            id_usuario_vendedor = int(vendedor_origen)
        except Exception:
            return {'error': 'Vendedor original inv?lido en el pendiente enviado a caja'}, 400
        vendedor_obj = db.session.get(Usuario, id_usuario_vendedor)
        if not vendedor_obj:
            return {'error': 'El vendedor original del pendiente ya no existe'}, 400
    else:
        if ocultar_selector_vendedor_pos:
            id_usuario_vendedor = int(current_user.id_usuario)
        elif id_usuario_vendedor_raw in (None, ''):
            if int(current_user.id_usuario) in ids_vendedores or not vendedores_cajeros:
                id_usuario_vendedor = int(current_user.id_usuario)
            else:
                id_usuario_vendedor = int(vendedores_cajeros[0].id_usuario)
        else:
            try:
                id_usuario_vendedor = int(id_usuario_vendedor_raw)
            except Exception:
                return {'error': 'Vendedor/Cajero inv?lido'}, 400
        if (not ocultar_selector_vendedor_pos) and ids_vendedores and id_usuario_vendedor not in ids_vendedores:
            return {'error': 'Debe seleccionar un vendedor/cajero v?lido'}, 400

    reparacion_obj = None
    cliente_servicio_objs = []
    if reparacion_id not in (None, ''):
        try:
            reparacion_id = int(reparacion_id)
        except Exception:
            return {'error': 'reparacion_id inv?lido'}, 400
        reparacion_obj = db.session.get(Reparacion, reparacion_id)
        if not reparacion_obj:
            return {'error': 'Reparaci?n no encontrada'}, 400
        if int(reparacion_obj.cliente_id) != int(id_cliente):
            return {'error': 'La reparaci?n no corresponde al cliente seleccionado'}, 400
        existente = (
            Venta.query
            .filter(Venta.id_reparacion == reparacion_obj.id_reparacion, Venta.estado != 'anulada')
            .first()
        )
        if existente:
            return {'error': f'La reparaci?n ya fue cobrada en la venta #{existente.id_venta}'}, 400

    if cliente_servicio_ids:
        try:
            cliente_servicio_objs = get_cliente_servicios_cobrables(cliente_servicio_ids, id_cliente=id_cliente)
        except ValueError as exc:
            mensaje = str(exc)
            status_code = 404 if 'no encontrado' in mensaje.lower() else 400
            return {'error': mensaje}, status_code

        requerido_por_servicio = {}
        for asignacion in cliente_servicio_objs:
            servicio_id = int(asignacion.id_servicio or 0)
            requerido_por_servicio[servicio_id] = requerido_por_servicio.get(servicio_id, 0) + max(int(asignacion.cantidad or 1), 1)

        cantidad_en_venta_por_servicio = {}
        for item in items or []:
            try:
                id_servicio_item = int(item.get('id_servicio') or item.get('id') or 0)
                cantidad_item = max(int(item.get('cantidad') or 0), 0)
            except Exception:
                id_servicio_item = 0
                cantidad_item = 0
            if id_servicio_item > 0 and cantidad_item > 0:
                cantidad_en_venta_por_servicio[id_servicio_item] = cantidad_en_venta_por_servicio.get(id_servicio_item, 0) + cantidad_item

        for asignacion in cliente_servicio_objs:
            servicio_id = int(asignacion.id_servicio or 0)
            cantidad_requerida = requerido_por_servicio.get(servicio_id, 0)
            cantidad_en_venta = cantidad_en_venta_por_servicio.get(servicio_id, 0)
            if cantidad_en_venta < cantidad_requerida:
                return {'error': f'La venta no incluye la cantidad suficiente del servicio asignado para #{asignacion.id_cliente_servicio}'}, 400

    cliente_tipo = (cliente.tipo or '').strip().lower()
    if usar_precio_mayorista_raw is None:
        usar_precio_mayorista = _is_truthy(forzar_precio_mayorista_raw) or (cliente_tipo in ('mayorista', 'empresa'))
    else:
        usar_precio_mayorista = _is_truthy(usar_precio_mayorista_raw)

    catalogo_ctx, error_response = _prefetch_catalogo_venta(items)
    if error_response:
        return error_response
    productos_prefetch_por_id = catalogo_ctx['productos_prefetch_por_id']
    servicios_prefetch_por_id = catalogo_ctx['servicios_prefetch_por_id']
    opciones_precio_por_clave = catalogo_ctx['opciones_precio_por_clave']
    servicio_opciones_precio_por_clave = catalogo_ctx['servicio_opciones_precio_por_clave']

    _perf_stage('prefetch_catalogo')

    detalles_ctx, error_response = _construir_detalles_venta(
        items,
        productos_prefetch_por_id,
        servicios_prefetch_por_id,
        opciones_precio_por_clave,
        servicio_opciones_precio_por_clave,
        cola_cobro,
        reparacion_obj,
        usar_precio_mayorista,
    )
    if error_response:
        return error_response
    subtotal = detalles_ctx['subtotal']
    total_iva_10 = detalles_ctx['total_iva_10']
    total_iva_5 = detalles_ctx['total_iva_5']
    total_exenta = detalles_ctx['total_exenta']
    detalles = detalles_ctx['detalles']
    productos_por_id = detalles_ctx['productos_por_id']
    cantidades_por_producto = detalles_ctx['cantidades_por_producto']

    _perf_stage('calculo_items')

    stock_ctx, error_response = _validar_stock_para_venta(productos_por_id, cantidades_por_producto, id_autorizacion)
    if error_response:
        return error_response
    stock_warnings = stock_ctx['stock_warnings']
    autorizacion_stock_negativo = stock_ctx['autorizacion_stock_negativo']

    _perf_stage('validacion_stock')

    if subtotal <= 0:
        return {'error': 'El subtotal de la venta debe ser mayor a cero'}, 400
    if descuento_monto >= subtotal:
        return {'error': 'El descuento debe ser menor al subtotal'}, 400

    try:
        beneficio_descuento_ctx = resolver_descuento_beneficio_pos(
            id_cliente,
            beneficio_fidelizacion_id,
            subtotal,
            descuento_monto,
        )
    except ValueError as exc:
        return {'error': str(exc)}, 400
    descuento_beneficio_monto = Decimal(str(beneficio_descuento_ctx['descuento_adicional'] or 0))

    stock_inicial = {pid: p.stock_actual for pid, p in productos_por_id.items()}
    total = subtotal - descuento_monto - descuento_beneficio_monto
    if total <= 0:
        return {'error': 'El total de la venta debe ser mayor a cero'}, 400
    credito_ctx, error_response = resolver_credito_desde_pagos(
        pagos_normalizados,
        ids_metodo_credito,
        total,
    )
    if error_response:
        return error_response
    monto_financiado = credito_ctx['monto_financiado']
    monto_inmediato_exigido = credito_ctx['monto_inmediato_exigido']
    total_pagado = credito_ctx['total_pagado_inmediato']
    pagos_inmediatos = credito_ctx['pagos_inmediatos']
    plan_credito_ctx = {'modo': 'cuenta_corriente'}
    if monto_financiado > 0:
        if reparacion_obj is not None:
            return {'error': 'La venta a credito no esta habilitada para reparaciones desde POS'}, 400
        if cola_cobro is not None:
            return {'error': 'La venta a credito no esta habilitada para pendientes enviados a caja'}, 400
        plan_credito_ctx, error_response = resolver_credito_plan_payload(
            data,
            fecha_base=today_local(),
        )
        if error_response:
            return error_response
        compromiso_credito = calcular_compromiso_credito(
            monto_financiado,
            credito_plan=plan_credito_ctx,
        )
        error_response = _validar_credito_cliente(id_cliente, compromiso_credito)
        if error_response:
            return error_response
    precision_tolerancia = Decimal('0.0001')
    if total_pagado + precision_tolerancia < monto_inmediato_exigido:
        return {'error': f'Pago insuficiente. Faltan ? {monto_inmediato_exigido - total_pagado:,.0f}'}, 400

    venta = Venta(
        id_cliente=id_cliente,
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=id_usuario_vendedor,
        subtotal=subtotal,
        descuento_monto=(descuento_monto + descuento_beneficio_monto),
        descuento_manual_monto=descuento_monto,
        descuento_fidelizacion_monto=descuento_beneficio_monto,
        total_iva_10=total_iva_10,
        total_iva_5=total_iva_5,
        total_exenta=total_exenta,
        total=total,
        observaciones=observaciones
    )
    if monto_financiado > 0:
        venta.tipo_venta = 'credito'
        venta.saldo_pendiente = monto_financiado
    if reparacion_obj:
        venta.id_reparacion = reparacion_obj.id_reparacion
    if client_request_id:
        venta.client_request_id = client_request_id
    if beneficio_descuento_ctx['beneficio_resumen']:
        beneficio_texto = f'Beneficio POS aplicado: {beneficio_descuento_ctx["beneficio_resumen"]}'
        observaciones_actuales = (observaciones or '').strip()
        venta.observaciones = f'{observaciones_actuales} | {beneficio_texto}'.strip(' |')
    db.session.add(venta)
    db.session.flush()

    beneficio_aplicado_snapshot = registrar_canje_beneficio_en_venta(
        id_cliente,
        beneficio_fidelizacion_id,
        venta.id_venta,
        id_usuario=getattr(current_user, 'id_usuario', None),
    )
    if beneficio_aplicado_snapshot:
        venta.beneficio_fidelizacion_tipo = beneficio_aplicado_snapshot.get('tipo')
        venta.beneficio_fidelizacion_descripcion = (beneficio_descuento_ctx['beneficio_resumen'] or '').strip()[:255] or None

    if autorizacion_venta_credito:
        autorizacion_venta_credito.referencia_tipo = 'venta'
        autorizacion_venta_credito.referencia_id = venta.id_venta
        db.session.add(autorizacion_venta_credito)

    if autorizacion_stock_negativo:
        autorizacion_stock_negativo.referencia_tipo = 'venta'
        autorizacion_stock_negativo.referencia_id = venta.id_venta
        db.session.add(autorizacion_stock_negativo)

    cuenta_por_cobrar = None
    if monto_financiado > 0:
        cuenta_por_cobrar = crear_venta_credito(
            venta,
            id_cliente,
            monto_financiado,
            observaciones=observaciones,
            monto_anticipo=total_pagado,
            credito_plan=plan_credito_ctx,
        )

    for detalle, producto, cantidad, servicio in detalles:
        detalle.id_venta = venta.id_venta
        db.session.add(detalle)
        if not producto or producto.es_servicio:
            continue

        stock_anterior = producto.stock_actual
        producto.stock_actual -= cantidad
        db.session.add(MovimientoStock(
            id_producto=producto.id_producto,
            id_usuario=current_user.id_usuario,
            tipo_movimiento='salida',
            cantidad=cantidad,
            stock_anterior=stock_anterior,
            stock_nuevo=producto.stock_actual,
            referencia_tipo='venta',
            referencia_id=venta.id_venta
        ))

    low_stock_warnings = []
    for id_producto, producto in productos_por_id.items():
        if producto.stock_actual <= producto.stock_minimo:
            low_stock_warnings.append({
                'producto': producto.nombre,
                'codigo': producto.codigo,
                'stock_anterior': stock_inicial.get(id_producto, producto.stock_actual),
                'stock_nuevo': producto.stock_actual,
                'stock_minimo': producto.stock_minimo
            })

    pagos_registrados_ctx, error_response = _registrar_pagos_y_movimientos_venta(
        venta,
        sesion,
        pagos_inmediatos,
        pagos_inmediatos,
        ids_metodo_efectivo,
        monto_inmediato_exigido,
        total_pagado,
    )
    if error_response:
        db.session.rollback()
        return error_response
    vuelto = pagos_registrados_ctx['vuelto']

    if autorizacion_stock_negativo:
        registrar_auditoria(
            accion='venta_sin_stock',
            modulo='ventas',
            descripcion=f'Venta #{venta.id_venta} procesada con stock insuficiente',
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
            datos_nuevos={'stock_warnings': stock_warnings},
            id_autorizacion=autorizacion_stock_negativo.id_autorizacion,
            commit=False
        )

    numero_ticket = f"TK-{venta.id_venta:06d}"
    db.session.add(Ticket(
        id_venta=venta.id_venta,
        numero_ticket=numero_ticket,
        id_usuario_emision=current_user.id_usuario
    ))

    items_auditoria = []
    for detalle, producto, cantidad, servicio in detalles:
        item_id = producto.id_producto if producto else servicio.id_servicio
        items_auditoria.append({
            'tipo': 'producto' if producto else 'servicio',
            'id_producto': producto.id_producto if producto else None,
            'id_servicio': servicio.id_servicio if servicio else None,
            'id_item': item_id,
            'codigo': ((producto.codigo if producto else servicio.codigo) or '').strip(),
            'nombre': ((producto.nombre if producto else servicio.nombre) or '').strip(),
            'cantidad': int(cantidad),
            'precio_unitario': float(detalle.precio_unitario or 0),
            'subtotal': float(detalle.subtotal or 0),
            'es_servicio': bool(servicio or producto.es_servicio),
            'es_kit': bool(producto.es_kit) if producto else False,
        })

    pagos_auditoria = []
    for pago in pagos_normalizados:
        try:
            pagos_auditoria.append({
                'id_metodo_pago': int(pago.get('id_metodo_pago')),
                'monto': float(pago.get('monto', 0)),
                'referencia': (pago.get('referencia') or '').strip() or None,
            })
        except Exception:
            pass

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='crear_venta',
                modulo='ventas',
                descripcion=f'Cre? venta #{venta.id_venta}',
                referencia_tipo='venta',
                referencia_id=venta.id_venta,
                datos_nuevos={
                    'id_cliente': int(id_cliente),
                    'cliente_servicio_id': int(cliente_servicio_objs[0].id_cliente_servicio) if len(cliente_servicio_objs) == 1 else None,
                    'cliente_servicio_ids': [int(asignacion.id_cliente_servicio) for asignacion in cliente_servicio_objs],
                    'id_sesion_caja': int(sesion.id_sesion),
                    'subtotal': float(subtotal or 0),
                    'descuento_monto': float(descuento_monto or 0),
                    'descuento_beneficio_monto': float(descuento_beneficio_monto or 0),
                    'total': float(total or 0),
                    'tipo_venta': venta.tipo_venta,
                    'saldo_pendiente': float(venta.saldo_pendiente or 0),
                    'total_iva_10': float(total_iva_10 or 0),
                    'total_iva_5': float(total_iva_5 or 0),
                    'total_exenta': float(total_exenta or 0),
                    'total_pagado': float(total_pagado or 0),
                    'vuelto': float(vuelto or 0),
                    'observaciones': observaciones,
                    'numero_ticket': numero_ticket,
                    'items': items_auditoria,
                    'pagos': pagos_auditoria,
                    'cuenta_por_cobrar_id': int(cuenta_por_cobrar.id_cuenta_cobrar) if cuenta_por_cobrar else None,
                    'plan_credito_id': int(cuenta_por_cobrar.plan_credito_creado.id_plan_credito_venta) if getattr(cuenta_por_cobrar, 'plan_credito_creado', None) else None,
                    'stock_warnings': stock_warnings,
                    'low_stock_warnings': low_stock_warnings,
                },
                id_autorizacion=autorizacion_stock_negativo.id_autorizacion if autorizacion_stock_negativo else None,
                commit=False
            )
    except Exception:
        pass

    if reparacion_obj:
        estado_anterior_reparacion = reparacion_obj.estado
        reparacion_obj.estado = 'entregado'
        if not reparacion_obj.fecha_entrega:
            reparacion_obj.fecha_entrega = datetime.utcnow()
        db.session.add(ReparacionHistorialEstado(
            id_reparacion=reparacion_obj.id_reparacion,
            estado_anterior=estado_anterior_reparacion,
            estado_nuevo='entregado',
            nota=f'Entrega por venta #{venta.id_venta}'
        ))
        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='entregar_reparacion',
                    modulo='reparaciones',
                    descripcion=f'Entrega de reparaci?n #{reparacion_obj.id_reparacion} por venta #{venta.id_venta}',
                    referencia_tipo='reparacion',
                    referencia_id=reparacion_obj.id_reparacion,
                    datos_anteriores={'estado': estado_anterior_reparacion},
                    datos_nuevos={
                        'estado': 'entregado',
                        'fecha_entrega': reparacion_obj.fecha_entrega.isoformat() if reparacion_obj.fecha_entrega else None,
                        'venta_id': int(venta.id_venta),
                    },
                    commit=False
                )
        except Exception:
            pass

    for cliente_servicio_obj in cliente_servicio_objs:
        estado_anterior_servicio = cliente_servicio_obj.estado
        estado_normalizado = (cliente_servicio_obj.estado or '').strip().lower()
        cobro_anticipado = estado_normalizado in {'agendado', 'presupuestado'} and cliente_servicio_obj.fecha_programada is not None
        cliente_servicio_obj.estado = estado_anterior_servicio if cobro_anticipado else 'completado'
        cliente_servicio_obj.id_venta = venta.id_venta
        if cliente_servicio_obj.estado == 'completado' and not cliente_servicio_obj.fecha_cierre:
            cliente_servicio_obj.fecha_cierre = datetime.utcnow()
        elif cliente_servicio_obj.estado != 'completado':
            cliente_servicio_obj.fecha_cierre = None
        observaciones_servicio = (cliente_servicio_obj.observaciones or '').strip()
        cierre_texto = (
            f'Cobrado por anticipado en venta #{venta.id_venta}'
            if cobro_anticipado else
            f'Cobrado en venta #{venta.id_venta}'
        )
        if cierre_texto not in observaciones_servicio:
            cliente_servicio_obj.observaciones = f'{observaciones_servicio} | {cierre_texto}'.strip(' |')
        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='cobrar_servicio_cliente',
                    modulo='clientes',
                    descripcion=f'Servicio del cliente #{cliente_servicio_obj.id_cliente_servicio} cobrado en venta #{venta.id_venta}',
                    referencia_tipo='cliente_servicio',
                    referencia_id=cliente_servicio_obj.id_cliente_servicio,
                    datos_anteriores={'estado': estado_anterior_servicio},
                    datos_nuevos={
                        'estado': cliente_servicio_obj.estado,
                        'venta_id': int(venta.id_venta),
                        'fecha_cierre': cliente_servicio_obj.fecha_cierre.isoformat() if cliente_servicio_obj.fecha_cierre else None,
                    },
                    commit=False
                )
        except Exception:
            pass

    if cola_cobro is not None:
        estado_anterior_cola = cola_cobro.estado
        metadata_cola = cola_metadata or cola_cobro.get_metadata()
        metadata_cola['venta_id'] = int(venta.id_venta)
        metadata_cola['cerrado_por_usuario'] = int(current_user.id_usuario)
        id_origen_cola = cola_cobro.id_origen
        if cola_cobro.tipo_origen == 'venta':
            id_origen_cola = venta.id_venta
        elif reparacion_obj:
            id_origen_cola = int(reparacion_obj.id_reparacion)
            metadata_cola['reparacion_id'] = int(reparacion_obj.id_reparacion)
        fecha_cobro_cola = datetime.utcnow()
        filas_actualizadas = (
            db.session.query(ColaCobro)
            .filter(
                ColaCobro.id == cola_cobro.id,
                ColaCobro.estado.in_(('pendiente', 'en_proceso')),
                or_(ColaCobro.id_usuario_destino.is_(None), ColaCobro.id_usuario_destino == int(current_user.id_usuario))
            )
            .update(
                {
                    ColaCobro.id_usuario_destino: int(current_user.id_usuario),
                    ColaCobro.id_origen: int(id_origen_cola) if id_origen_cola is not None else None,
                    ColaCobro.estado: 'cobrado',
                    ColaCobro.fecha_cobro: fecha_cobro_cola,
                    ColaCobro.fecha_toma: func.coalesce(ColaCobro.fecha_toma, fecha_cobro_cola),
                },
                synchronize_session=False
            )
        )
        if not filas_actualizadas:
            db.session.rollback()
            return {'error': 'Este pendiente ya fue procesado por otro usuario'}, 409

        db.session.expire_all()
        cola_cobro = db.session.get(ColaCobro, cola_cobro.id)
        cola_cobro.set_metadata(metadata_cola)

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='cobrar_pendiente_caja',
                    modulo='caja',
                    descripcion=f'Cobr? pendiente de caja #{cola_cobro.id} con venta #{venta.id_venta}',
                    referencia_tipo='cola_cobro',
                    referencia_id=cola_cobro.id,
                    datos_anteriores={'estado': estado_anterior_cola},
                    datos_nuevos={
                        'estado': 'cobrado',
                        'venta_id': int(venta.id_venta),
                        'tipo_origen': cola_cobro.tipo_origen,
                        'reparacion_id': int(reparacion_obj.id_reparacion) if reparacion_obj else None,
                    },
                    commit=False
                )
        except Exception:
            pass

    fidelizacion_resultado = registrar_compra_fidelizacion_por_venta(
        venta,
        id_usuario=getattr(current_user, 'id_usuario', None),
    )

    _perf_stage('persistencia_pre_commit')
    db.session.commit()
    _perf_stage('commit')

    mensaje = f'Venta #{venta.id_venta} procesada correctamente'
    if fidelizacion_resultado.get('beneficios_generados'):
        beneficio_texto = beneficio_resumen_config(fidelizacion_config())
        mensaje += (
            f' | Fidelizacion: +{int(fidelizacion_resultado["beneficios_generados"])} '
            f'beneficio(s) ({beneficio_texto})'
        )
    if beneficio_descuento_ctx['beneficio_resumen']:
        mensaje += f' | Beneficio aplicado: {beneficio_descuento_ctx["beneficio_resumen"]}'

    response_data = {
        'success': True,
        'id_venta': venta.id_venta,
        'tipo_venta': venta.tipo_venta,
        'credito_modo': plan_credito_ctx.get('modo') if monto_financiado > 0 else None,
        'credito_tasa_interes_pct': float(plan_credito_ctx.get('tasa_interes_pct') or 0) if monto_financiado > 0 else 0,
        'id_plan_credito_venta': int(cuenta_por_cobrar.plan_credito_creado.id_plan_credito_venta) if getattr(cuenta_por_cobrar, 'plan_credito_creado', None) else None,
        'saldo_pendiente': float(venta.saldo_pendiente or 0),
        'total': float(total),
        'pagado': float(total_pagado),
        'vuelto': float(vuelto),
        'mensaje': mensaje,
        'fidelizacion': fidelizacion_resultado,
        'beneficio_aplicado': {
            'resumen': beneficio_descuento_ctx['beneficio_resumen'],
            'descuento_monto': float(descuento_beneficio_monto or 0),
            'tipo': beneficio_aplicado_snapshot['tipo'] if beneficio_aplicado_snapshot else None,
        },
    }
    if stock_warnings:
        response_data['stock_warnings'] = stock_warnings
    if low_stock_warnings:
        response_data['low_stock_warnings'] = low_stock_warnings
    if autorizacion_stock_negativo:
        response_data['id_autorizacion'] = autorizacion_stock_negativo.id_autorizacion
    if perf_enabled:
        response_data['perf'] = {
            'total_ms': round((perf_counter() - perf_t0) * 1000, 2),
            'stages': perf_stages,
        }
    return response_data, 200
