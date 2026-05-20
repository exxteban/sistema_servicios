from .base_y_listado import *

def _venta_existente_response(venta):
    total_pagado = sum(float(p.monto) for p in venta.pagos.all())
    total = float(venta.total or 0)
    vuelto = max(0, total_pagado - total)
    return {
        'success': True,
        'id_venta': venta.id_venta,
        'total': total,
        'pagado': total_pagado,
        'vuelto': float(vuelto),
        'mensaje': f'Venta #{venta.id_venta} ya estaba registrada'
    }


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
    cola_cobro_id = data.get('cola_cobro_id')
    forzar_precio_mayorista_raw = data.get('forzar_precio_mayorista', False)
    descuento_monto = Decimal(str(data.get('descuento', 0)))
    observaciones = data.get('observaciones', '')
    id_autorizacion = data.get('id_autorizacion')
    if id_autorizacion in (None, ''):
        id_autorizacion = None
    else:
        id_autorizacion = int(id_autorizacion)

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

    autorizacion_venta_credito = None
    ids_metodo_efectivo = set()
    if pagos:
        metodo_ids = set()
        for pago in pagos:
            try:
                metodo_ids.add(int(pago.get('id_metodo_pago')))
            except Exception:
                continue

        if metodo_ids:
            metodos = MetodoPago.query.filter(MetodoPago.id_metodo_pago.in_(list(metodo_ids))).all()
            usa_credito = any(_es_metodo_credito_tienda(m.nombre) for m in metodos)
            ids_metodo_efectivo = {
                int(m.id_metodo_pago) for m in metodos
                if _es_metodo_efectivo(m.nombre)
            }
            if usa_credito:
                return {'error': 'Venta a cr?dito deshabilitada'}, 403
            if usa_credito and not current_user.es_admin():
                if not current_user.tiene_permiso('venta_credito'):
                    return {'error': 'Sin permiso para venta a cr?dito'}, 403
                ok, autorizacion_venta_credito = validar_autorizacion(id_autorizacion, 'venta_credito')
                if not ok:
                    return {'error': autorizacion_venta_credito, 'codigo_permiso': 'venta_credito'}, 403

    _perf_stage('validaciones_iniciales')

    if not items:
        return {'error': 'No hay productos en la venta'}, 400

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

    cliente_tipo = (cliente.tipo or '').strip().lower()
    usar_precio_mayorista = _is_truthy(forzar_precio_mayorista_raw) or (cliente_tipo in ('mayorista', 'empresa'))

    producto_ids_requeridos = set()
    precio_opcion_ids_requeridos = set()
    for item in items:
        try:
            id_producto_item = int(item.get('id_producto'))
        except Exception:
            return {'error': 'Producto inválido'}, 400
        producto_ids_requeridos.add(id_producto_item)
        precio_opcion_id_item = item.get('precio_opcion_id')
        if precio_opcion_id_item not in (None, ''):
            try:
                precio_opcion_ids_requeridos.add(int(precio_opcion_id_item))
            except Exception:
                return {'error': 'precio_opcion_id inv?lido'}, 400

    productos_prefetch = (
        Producto.query
        .filter(Producto.id_producto.in_(list(producto_ids_requeridos)))
        .all()
    )
    productos_prefetch_por_id = {int(p.id_producto): p for p in productos_prefetch}
    for id_producto_item in sorted(producto_ids_requeridos):
        if id_producto_item not in productos_prefetch_por_id:
            return {'error': f'Producto no encontrado: {id_producto_item}'}, 400

    opciones_precio_por_clave = {}
    if precio_opcion_ids_requeridos:
        opciones_precio = (
            ProductoPrecioOpcion.query
            .filter(
                ProductoPrecioOpcion.id_opcion_precio.in_(list(precio_opcion_ids_requeridos)),
                ProductoPrecioOpcion.id_producto.in_(list(producto_ids_requeridos)),
                ProductoPrecioOpcion.activo == True
            )
            .all()
        )
        opciones_precio_por_clave = {
            (int(op.id_producto), int(op.id_opcion_precio)): op
            for op in opciones_precio
        }

    _perf_stage('prefetch_catalogo')

    subtotal = Decimal('0')
    total_iva_10 = Decimal('0')
    total_iva_5 = Decimal('0')
    total_exenta = Decimal('0')
    detalles = []
    productos_por_id = {}
    cantidades_por_producto = {}

    for item in items:
        try:
            id_producto_item = int(item.get('id_producto'))
        except Exception:
            return {'error': 'Producto inválido'}, 400
        producto = productos_prefetch_por_id.get(id_producto_item)
        if not producto:
            return {'error': f'Producto no encontrado: {id_producto_item}'}, 400

        cantidad = int(item['cantidad'])
        if cola_cobro is not None:
            try:
                precio_original = Decimal(str(item.get('precio_base', producto.precio_venta or 0) or 0))
            except Exception:
                return {'error': 'Precio base invalido en el pendiente enviado a caja'}, 400
            try:
                precio = Decimal(str(item.get('precio')))
            except Exception:
                return {'error': 'Precio invalido en el pendiente enviado a caja'}, 400
        else:
            precio_original = Decimal(str(producto.precio_venta or 0))
            precio = precio_original
        precio_opcion_id = item.get('precio_opcion_id')
        if precio_opcion_id not in (None, ''):
            try:
                precio_opcion_id = int(precio_opcion_id)
            except Exception:
                return {'error': 'precio_opcion_id inv?lido'}, 400
            opcion = opciones_precio_por_clave.get((int(producto.id_producto), int(precio_opcion_id)))
            if not opcion:
                return {'error': 'Opci?n de precio inv?lida para el producto'}, 400
            if cola_cobro is None:
                try:
                    precio = Decimal(str(opcion.precio))
                except Exception:
                    return {'error': 'Precio inv?lido en opci?n de precio'}, 400
                if precio <= 0:
                    return {'error': 'Precio inv?lido en opci?n de precio'}, 400
        if (
            cola_cobro is None
            and item.get('precio_manual')
            and (
                producto.codigo == REPARACION_COSTO_BASE_CODIGO
                or reparacion_obj is not None
            )
        ):
            if cola_cobro is None and item.get('precio') is not None:
                try:
                    precio = Decimal(str(item.get('precio')))
                except Exception:
                    return {'error': 'Precio inv?lido para costo final de reparaci?n'}, 400
            if precio < 0:
                return {'error': 'Precio inv?lido para costo final de reparaci?n'}, 400
        elif cola_cobro is None and usar_precio_mayorista and precio_opcion_id in (None, ''):
            try:
                if producto.precio_mayorista is not None:
                    precio_may = Decimal(str(producto.precio_mayorista))
                    if precio_may > 0:
                        precio = precio_may
            except Exception:
                precio = precio_original
        elif cola_cobro is not None and precio <= 0:
            return {'error': 'Precio invalido en el pendiente enviado a caja'}, 400

        item_subtotal = precio * cantidad
        if not producto.es_servicio:
            productos_por_id[producto.id_producto] = producto
            cantidades_por_producto[producto.id_producto] = cantidades_por_producto.get(producto.id_producto, 0) + cantidad

        if producto.porcentaje_iva == 10:
            item_iva = item_subtotal / 11
            total_iva_10 += item_iva
        elif producto.porcentaje_iva == 5:
            item_iva = item_subtotal / 21
            total_iva_5 += item_iva
        else:
            item_iva = Decimal('0')
            total_exenta += item_subtotal

        subtotal += item_subtotal
        detalle = DetalleVenta(
            id_producto=producto.id_producto,
            cantidad=cantidad,
            precio_unitario=precio,
            precio_original=precio_original,
            porcentaje_iva=producto.porcentaje_iva,
            monto_iva=item_iva,
            subtotal=item_subtotal,
            es_kit=producto.es_kit
        )
        detalles.append((detalle, producto, cantidad))

    _perf_stage('calculo_items')

    stock_warnings = []
    for id_producto, cantidad_solicitada in cantidades_por_producto.items():
        producto = productos_por_id[id_producto]
        if producto.stock_actual <= 0:
            stock_warnings.append({
                'producto': producto.nombre,
                'codigo': producto.codigo,
                'cantidad_solicitada': cantidad_solicitada,
                'stock_disponible': producto.stock_actual,
                'tipo': 'sin_stock'
            })
        elif cantidad_solicitada > producto.stock_actual:
            stock_warnings.append({
                'producto': producto.nombre,
                'codigo': producto.codigo,
                'cantidad_solicitada': cantidad_solicitada,
                'stock_disponible': producto.stock_actual,
                'tipo': 'stock_insuficiente'
            })

    stock_negativo_permitido = Configuracion.obtener_bool('stock_negativo_permitido', default=False)
    autorizacion_stock_negativo = None
    if stock_warnings and not stock_negativo_permitido:
        if not (current_user.es_admin() or current_user.tiene_permiso('vender_sin_stock')):
            return {'error': 'Sin permiso para vender sin stock', 'stock_warnings': stock_warnings}, 403

        if current_user.es_admin():
            autorizacion_stock_negativo = None
        elif not id_autorizacion:
            return {'error': 'Se requiere autorizaci?n de administrador para vender sin stock', 'stock_warnings': stock_warnings}, 403
        else:
            autorizacion_stock_negativo = db.session.get(Autorizacion, id_autorizacion)
            if not autorizacion_stock_negativo:
                return {'error': 'Autorizaci?n no encontrada', 'stock_warnings': stock_warnings}, 403
            if autorizacion_stock_negativo.estado != 'aprobada':
                return {'error': 'Autorizaci?n no aprobada', 'stock_warnings': stock_warnings}, 403
            if autorizacion_stock_negativo.id_usuario_solicitante != current_user.id_usuario:
                return {'error': 'Autorizaci?n no corresponde al usuario solicitante', 'stock_warnings': stock_warnings}, 403
            permiso_autorizado = db.session.get(Permiso, autorizacion_stock_negativo.id_permiso)
            if not permiso_autorizado or permiso_autorizado.codigo != 'vender_sin_stock':
                return {'error': 'Autorizaci?n inv?lida para esta operaci?n', 'stock_warnings': stock_warnings}, 403

    _perf_stage('validacion_stock')

    stock_inicial = {pid: p.stock_actual for pid, p in productos_por_id.items()}
    total = subtotal - descuento_monto
    total_pagado = sum(Decimal(str(p['monto'])) for p in pagos)
    if total_pagado < total:
        return {'error': f'Pago insuficiente. Faltan ? {total - total_pagado:,.0f}'}, 400

    venta = Venta(
        id_cliente=id_cliente,
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=id_usuario_vendedor,
        subtotal=subtotal,
        descuento_monto=descuento_monto,
        total_iva_10=total_iva_10,
        total_iva_5=total_iva_5,
        total_exenta=total_exenta,
        total=total,
        observaciones=observaciones
    )
    if reparacion_obj:
        venta.id_reparacion = reparacion_obj.id_reparacion
    if client_request_id:
        venta.client_request_id = client_request_id
    db.session.add(venta)
    db.session.flush()

    if autorizacion_venta_credito:
        autorizacion_venta_credito.referencia_tipo = 'venta'
        autorizacion_venta_credito.referencia_id = venta.id_venta
        db.session.add(autorizacion_venta_credito)

    if autorizacion_stock_negativo:
        autorizacion_stock_negativo.referencia_tipo = 'venta'
        autorizacion_stock_negativo.referencia_id = venta.id_venta
        db.session.add(autorizacion_stock_negativo)

    for detalle, producto, cantidad in detalles:
        detalle.id_venta = venta.id_venta
        db.session.add(detalle)
        if producto.es_servicio:
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

    if pagos and not ids_metodo_efectivo:
        metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        if metodo_efectivo:
            ids_metodo_efectivo.add(int(metodo_efectivo.id_metodo_pago))
    vuelto = total_pagado - total
    if vuelto > 0:
        efectivo_pagado = Decimal('0')
        for pago in pagos:
            try:
                if int(pago.get('id_metodo_pago')) in ids_metodo_efectivo:
                    efectivo_pagado += Decimal(str(pago.get('monto', 0)))
            except Exception:
                continue
        if efectivo_pagado <= 0:
            return {'error': 'El vuelto solo es v?lido con pago en efectivo'}, 400
        if efectivo_pagado < vuelto:
            return {'error': 'El vuelto supera el efectivo recibido'}, 400

    for pago in pagos:
        id_metodo = int(pago['id_metodo_pago'])
        monto_pago = Decimal(str(pago['monto']))
        db.session.add(PagoVenta(
            id_venta=venta.id_venta,
            id_metodo_pago=id_metodo,
            monto=monto_pago,
            referencia=pago.get('referencia', '')
        ))
        if id_metodo in ids_metodo_efectivo:
            db.session.add(MovimientoCaja(
                id_sesion_caja=sesion.id_sesion,
                id_usuario=current_user.id_usuario,
                tipo='ingreso',
                monto=monto_pago,
                motivo=f'Cobro Efectivo Venta #{venta.id_venta}',
                referencia_tipo='venta',
                referencia_id=venta.id_venta,
                fecha_movimiento=venta.fecha_venta
            ))

    if vuelto > 0:
        db.session.add(MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=current_user.id_usuario,
            tipo='egreso',
            monto=vuelto,
            motivo=f'Vuelto Venta #{venta.id_venta}',
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
            fecha_movimiento=venta.fecha_venta
        ))

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
    for detalle, producto, cantidad in detalles:
        items_auditoria.append({
            'id_producto': producto.id_producto,
            'codigo': (producto.codigo or '').strip(),
            'nombre': (producto.nombre or '').strip(),
            'cantidad': int(cantidad),
            'precio_unitario': float(detalle.precio_unitario or 0),
            'subtotal': float(detalle.subtotal or 0),
            'es_servicio': bool(producto.es_servicio),
            'es_kit': bool(producto.es_kit),
        })

    pagos_auditoria = []
    for pago in pagos:
        try:
            pagos_auditoria.append({
                'id_metodo_pago': int(pago.get('id_metodo_pago')),
                'monto': float(Decimal(str(pago.get('monto', 0)))),
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
                    'id_sesion_caja': int(sesion.id_sesion),
                    'subtotal': float(subtotal or 0),
                    'descuento_monto': float(descuento_monto or 0),
                    'total': float(total or 0),
                    'total_iva_10': float(total_iva_10 or 0),
                    'total_iva_5': float(total_iva_5 or 0),
                    'total_exenta': float(total_exenta or 0),
                    'total_pagado': float(total_pagado or 0),
                    'vuelto': float((total_pagado - total) or 0),
                    'observaciones': observaciones,
                    'numero_ticket': numero_ticket,
                    'items': items_auditoria,
                    'pagos': pagos_auditoria,
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

    _perf_stage('persistencia_pre_commit')
    db.session.commit()
    _perf_stage('commit')

    response_data = {
        'success': True,
        'id_venta': venta.id_venta,
        'total': float(total),
        'pagado': float(total_pagado),
        'vuelto': float(vuelto),
        'mensaje': f'Venta #{venta.id_venta} procesada correctamente'
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


