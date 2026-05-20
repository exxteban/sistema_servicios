from .base_y_listado import *

def _render_pos_interface(sesion=None, solo_registro_vendedor=False):
    if not current_user.tiene_permiso('crear_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para acceder al POS.', 'danger')
        return redirect(url_for('main.dashboard'))

    clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    metodos_pago = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display).all()
    metodos_pago = [m for m in metodos_pago if not _es_metodo_credito_tienda(m.nombre)]
    ocultar_selector_vendedor_pos = _ocultar_selector_vendedor_pos()
    current_app.logger.info(
        "POS config vendedor/cajero: raw=%s ocultar_selector=%s",
        Configuracion.obtener(CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS, None),
        ocultar_selector_vendedor_pos,
    )
    vendedores_cajeros = _usuarios_vendedores_cajeros_activos()
    vendedor_default_id = None
    if ocultar_selector_vendedor_pos:
        vendedor_default_id = int(current_user.id_usuario)
    elif any(int(u.id_usuario) == int(current_user.id_usuario) for u in vendedores_cajeros):
        vendedor_default_id = int(current_user.id_usuario)
    vendedores_cajeros_data = [
        {
            'id_usuario': int(u.id_usuario),
            'nombre_completo': (u.nombre_completo or '').strip(),
            'rol': ((u.rol.nombre if u.rol else '') or '').strip(),
        }
        for u in vendedores_cajeros
    ]
    if not vendedores_cajeros_data:
        vendedores_cajeros_data = [{
            'id_usuario': int(current_user.id_usuario),
            'nombre_completo': (current_user.nombre_completo or '').strip(),
            'rol': ((current_user.rol.nombre if getattr(current_user, 'rol', None) else '') or '').strip(),
        }]
        vendedor_default_id = int(current_user.id_usuario)

    efectivo = next(
        (
            m for m in metodos_pago
            if (m.nombre or '').strip().lower() == 'efectivo'
        ),
        None
    )
    fallback_metodo = metodos_pago[0] if metodos_pago else None
    efectivo_id = int(getattr((efectivo or fallback_metodo), 'id_metodo_pago', 1) or 1)
    efectivo_nombre = str(getattr((efectivo or fallback_metodo), 'nombre', 'Efectivo') or 'Efectivo')

    empresa = {
        'nombre': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or ''
    }

    caja_flujo_enviado_activo = Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
    caja_exigir_cajero_para_cobro = Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
    modo_cobro_exclusivo_cajero = _modo_cobro_exclusivo_cajero_activo()
    puede_enviar_caja_venta = current_user.es_admin() or current_user.tiene_permiso('enviar_caja_venta')
    puede_tomar_cola_cobro = _usuario_puede_tomar_cola_cobro()
    puede_cobrar_pos_directo = (not modo_cobro_exclusivo_cajero) or puede_tomar_cola_cobro
    if solo_registro_vendedor:
        puede_cobrar_pos_directo = False

    cola_cobro_data = None

    # Lógica para precargar reparación
    reparacion_id = None if solo_registro_vendedor else request.args.get('reparacion_id', type=int)
    reparacion_token = request.args.get('rt')
    reparacion_data = None
    if reparacion_id:
        reparacion = db.session.get(Reparacion, reparacion_id)
        if reparacion:
            detalles_cobrables = reparacion.detalles.filter_by(incluye_costo_final=True).all()
            items = []

            costo_final_base = float(reparacion.costo_final or 0)
            if costo_final_base > 0:
                producto_base = _get_or_create_producto_costo_final_reparacion()
                solucion_txt = (reparacion.solucion or '').strip()
                nombre_base = f"Solución: {solucion_txt}" if solucion_txt else producto_base.nombre
                items.append({
                    'id': producto_base.id_producto,
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
                })

            for det in detalles_cobrables:
                items.append({
                    'id': det.id_producto,
                    'codigo': det.producto.codigo if det.producto else '',
                    'nombre': det.nombre_producto,
                    'precio': float(det.precio_unitario),
                    'precio_base': float(det.producto.precio_venta) if det.producto else float(det.precio_unitario),
                    'precio_mayorista': float(det.producto.precio_mayorista) if det.producto and det.producto.precio_mayorista else None,
                    'cantidad': det.cantidad,
                    'es_servicio': det.es_servicio,
                    'stock': det.producto.stock_actual if det.producto else 0,
                    'stock_minimo': det.producto.stock_minimo if det.producto else 0,
                    'iva': det.producto.porcentaje_iva if det.producto else 10,
                    'precio_manual': True,
                })

            reparacion_data = {
                'id': reparacion.id_reparacion,
                'cliente_id': reparacion.cliente_id,
                'id_usuario_vendedor': reparacion.id_usuario_vendedor,
                'abono': float(reparacion.abono or 0),
                'items': items
            }

            if (not vendedor_default_id) and (not ocultar_selector_vendedor_pos) and reparacion.id_usuario_vendedor and any(
                int(v['id_usuario']) == int(reparacion.id_usuario_vendedor) for v in vendedores_cajeros_data
            ):
                vendedor_default_id = int(reparacion.id_usuario_vendedor)

    cola_id = None if solo_registro_vendedor else request.args.get('cola_id', type=int)
    if cola_id:
        if not (current_user.es_admin() or current_user.tiene_permiso('tomar_cola_cobro')):
            flash('No tiene permisos para tomar pendientes de cobro.', 'warning')
        else:
            from app.routes.caja.api import _asegurar_en_proceso

            item_cola, error, _status = _asegurar_en_proceso(cola_id, commit=True)
            if error:
                mensaje_error = (error.get('error') or '').strip()
                if mensaje_error != 'Este pendiente ya no está disponible':
                    flash(mensaje_error or 'No se pudo abrir el pendiente de cobro.', 'warning')
            else:
                cola_cobro_data = _build_pos_data_from_cola_cobro(item_cola)

    template_name = 'ventas/registro_vendedor.html' if solo_registro_vendedor else 'ventas/pos.html'
    return render_template(template_name,
        sesion=sesion,
        clientes=clientes,
        metodos_pago=metodos_pago,
        efectivo_id=efectivo_id,
        efectivo_nombre=efectivo_nombre,
        empresa=empresa,
        reparacion_data=reparacion_data,
        reparacion_token=reparacion_token,
        cola_cobro_data=cola_cobro_data,
        vendedores_cajeros=vendedores_cajeros_data,
        vendedor_default_id=vendedor_default_id,
        ocultar_selector_vendedor_pos=ocultar_selector_vendedor_pos,
        caja_flujo_enviado_activo=caja_flujo_enviado_activo,
        caja_exigir_cajero_para_cobro=caja_exigir_cajero_para_cobro,
        modo_cobro_exclusivo_cajero=modo_cobro_exclusivo_cajero,
        puede_enviar_caja_venta=puede_enviar_caja_venta,
        puede_cobrar_pos_directo=puede_cobrar_pos_directo,
        solo_registro_vendedor=solo_registro_vendedor,
    )


@ventas_bp.route('/pos')
@login_required
def pos():
    """Pantalla del Punto de Venta (cobro)."""
    if not current_user.tiene_permiso('crear_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para acceder al POS.', 'danger')
        return redirect(url_for('main.dashboard'))

    modo_cobro_exclusivo_cajero = _modo_cobro_exclusivo_cajero_activo()

    # En modo exclusivo, vendedor sin permiso de caja entra al módulo de registro.
    if modo_cobro_exclusivo_cajero and not _usuario_puede_tomar_cola_cobro():
        return redirect(url_for('ventas.registro_vendedor'))

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()
    if not sesion:
        flash('Debe abrir una caja antes de realizar esta operación.', 'warning')
        return redirect(url_for('caja.abrir'))

    return _render_pos_interface(sesion=sesion, solo_registro_vendedor=False)


@ventas_bp.route('/registro-vendedor')
@login_required
def registro_vendedor():
    """Módulo simplificado de vendedor: registra y envía al cajero."""
    if not current_user.tiene_permiso('crear_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para registrar ventas.', 'danger')
        return redirect(url_for('main.dashboard'))

    modo_cobro_exclusivo_cajero = _modo_cobro_exclusivo_cajero_activo()

    if not modo_cobro_exclusivo_cajero:
        return redirect(url_for('ventas.pos'))

    if _usuario_puede_tomar_cola_cobro():
        return redirect(url_for('ventas.pos'))

    return _render_pos_interface(sesion=None, solo_registro_vendedor=True)


@ventas_bp.route('/registro-vendedor/enviadas')
@login_required
def registro_vendedor_enviadas():
    if not current_user.tiene_permiso('crear_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver tus ventas enviadas.', 'danger')
        return redirect(url_for('main.dashboard'))

    modo_cobro_exclusivo_cajero = _modo_cobro_exclusivo_cajero_activo()
    if not modo_cobro_exclusivo_cajero:
        flash('El modo vendedor -> cajero no está activo.', 'info')
        return redirect(url_for('ventas.pos'))

    estado_filtro = (request.args.get('estado') or '').strip().lower()
    estados_validos = {'pendiente', 'en_proceso', 'cobrado', 'cancelado'}
    if estado_filtro not in estados_validos:
        estado_filtro = ''
    cliente_filtro = (request.args.get('cliente') or '').strip()
    fecha_desde = parse_iso_date(request.args.get('fecha_desde'))
    fecha_hasta = parse_iso_date(request.args.get('fecha_hasta'))
    if fecha_desde and not fecha_hasta:
        fecha_hasta = fecha_desde
    if fecha_hasta and not fecha_desde:
        fecha_desde = fecha_hasta
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    page = request.args.get('page', 1, type=int)
    query_base = (
        ColaCobro.query
        .filter(
            ColaCobro.tipo_origen == 'venta',
            ColaCobro.id_usuario_origen == current_user.id_usuario,
        )
    )

    start_utc = None
    end_utc = None
    if fecha_desde and fecha_hasta:
        start_utc, end_utc = utc_bounds_for_local_dates(fecha_desde, fecha_hasta)
        query_base = query_base.filter(
            ColaCobro.fecha_envio >= start_utc,
            ColaCobro.fecha_envio < end_utc,
        )

    cliente_query_filter = None
    if cliente_filtro:
        cliente_term = cliente_filtro.lower()
        cliente_query_filter = [func.lower(Cliente.nombre).like(f'%{cliente_term}%')]
        if cliente_filtro.isdigit():
            cliente_query_filter.append(Cliente.id_cliente == int(cliente_filtro))
        query_base = query_base.outerjoin(ColaCobro.cliente).filter(or_(*cliente_query_filter))

    query = query_base
    if estado_filtro:
        query = query.filter(ColaCobro.estado == estado_filtro)

    query = query.options(
        joinedload(ColaCobro.cliente),
        joinedload(ColaCobro.usuario_destino),
    )

    enviados = query.order_by(ColaCobro.fecha_envio.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    resumen_estado = {k: 0 for k in estados_validos}
    resumen_rows = (
        query_base.with_entities(ColaCobro.estado, func.count(ColaCobro.id))
        .group_by(ColaCobro.estado)
        .all()
    )
    for estado, total in resumen_rows:
        key = (estado or '').strip().lower()
        if key in resumen_estado:
            resumen_estado[key] = int(total or 0)

    metricas_enviadas = int(
        query_base.with_entities(func.count(ColaCobro.id)).scalar() or 0
    )
    metricas_pendientes = int(
        query_base.filter(ColaCobro.estado.in_(['pendiente', 'en_proceso']))
        .with_entities(func.count(ColaCobro.id))
        .scalar() or 0
    )

    query_cobradas = Venta.query.filter(
        Venta.id_usuario_vendedor == current_user.id_usuario,
        Venta.estado == 'completada',
    )
    if start_utc and end_utc:
        query_cobradas = query_cobradas.filter(
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
    if cliente_query_filter:
        query_cobradas = query_cobradas.outerjoin(Cliente, Venta.id_cliente == Cliente.id_cliente)
        query_cobradas = query_cobradas.filter(or_(*cliente_query_filter))

    metricas_cobradas = int(
        query_cobradas.with_entities(func.count(Venta.id_venta)).scalar() or 0
    )
    tasa_cobro = round((metricas_cobradas / metricas_enviadas) * 100, 1) if metricas_enviadas > 0 else 0.0

    def _estado_ui(estado):
        estado = (estado or '').strip().lower()
        if estado == 'pendiente':
            return 'Pendiente', 'bg-amber-100 text-amber-800'
        if estado == 'en_proceso':
            return 'En proceso', 'bg-blue-100 text-blue-800'
        if estado == 'cobrado':
            return 'Cobrado', 'bg-green-100 text-green-800'
        if estado == 'cancelado':
            return 'Cancelado', 'bg-red-100 text-red-800'
        return (estado or 'Desconocido').replace('_', ' ').title(), 'bg-gray-100 text-gray-700'

    enviados_rows = []
    for item in enviados.items:
        metadata = item.get_metadata() or {}
        estado_label, estado_badge_class = _estado_ui(item.estado)
        cliente_nombre = ((item.cliente.nombre if item.cliente else '') or '').strip() or 'Consumidor Final'
        cajero_nombre = ((item.usuario_destino.nombre_completo if item.usuario_destino else '') or '').strip() or '-'
        items_meta = metadata.get('items') if isinstance(metadata.get('items'), list) else []
        cantidad_items = 0
        for it in items_meta:
            try:
                cantidad_items += int(it.get('cantidad') or 0)
            except Exception:
                continue
        enviados_rows.append({
            'id': int(item.id),
            'estado': item.estado,
            'estado_label': estado_label,
            'estado_badge_class': estado_badge_class,
            'monto_total': float(item.monto_total or 0),
            'cliente_nombre': cliente_nombre,
            'cantidad_items': int(cantidad_items),
            'fecha_envio_label': local_strftime(item.fecha_envio),
            'fecha_toma_label': local_strftime(item.fecha_toma),
            'fecha_cobro_label': local_strftime(item.fecha_cobro),
            'venta_id': metadata.get('venta_id'),
            'observaciones': (metadata.get('observaciones') or '').strip(),
            'cancelacion_motivo': (metadata.get('cancelacion_motivo') or '').strip(),
            'cajero_nombre': cajero_nombre,
        })

    return render_template(
        'ventas/registro_vendedor_enviadas.html',
        enviados=enviados,
        enviados_rows=enviados_rows,
        estado_filtro=estado_filtro,
        cliente_filtro=cliente_filtro,
        fecha_desde_filtro=fecha_desde.isoformat() if fecha_desde else '',
        fecha_hasta_filtro=fecha_hasta.isoformat() if fecha_hasta else '',
        resumen_estado=resumen_estado,
        metricas_vendedor={
            'enviadas': metricas_enviadas,
            'cobradas': metricas_cobradas,
            'pendientes': metricas_pendientes,
            'tasa_cobro': tasa_cobro,
        },
    )


@ventas_bp.route('/validar-carrito', methods=['POST'])
@login_required
def validar_carrito():
    """Validar productos del carrito guardado - retorna datos actualizados"""
    try:
        data = request.get_json()
        ids_productos = data.get('ids', [])
        
        if not ids_productos:
            return jsonify({'productos': {}})
        
        productos_validados = {}
        for id_producto in ids_productos:
            producto = db.session.get(Producto, id_producto)
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
                        for o in (
                            producto.precios_opciones.filter_by(activo=True)
                            .order_by(ProductoPrecioOpcion.orden.asc(), ProductoPrecioOpcion.id_opcion_precio.asc())
                            .all()
                        )
                    ],
                    'stock': producto.stock_actual,
                    'stock_minimo': producto.stock_minimo,
                    'es_servicio': producto.es_servicio,
                    'iva': producto.porcentaje_iva
                }
            else:
                productos_validados[str(id_producto)] = {
                    'existe': False
                }
        
        return jsonify({'productos': productos_validados})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ventas_bp.route('/enviar-a-caja', methods=['POST'])
@login_required
def enviar_a_caja():
    """Guarda un borrador de venta en la cola de cobro para que lo procese caja."""
    try:
        if not Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False):
            return jsonify({'error': 'El flujo de envío a caja no está habilitado'}), 403

        if not current_user.es_admin() and not current_user.tiene_permiso('enviar_caja_venta'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403
        if not current_user.es_admin() and not current_user.tiene_permiso('crear_venta'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

        data = request.get_json() or {}
        items = data.get('items', [])
        id_cliente = data.get('id_cliente', 1)
        id_usuario_vendedor_raw = data.get('id_usuario_vendedor')
        descuento_monto = Decimal(str(data.get('descuento', 0) or 0))
        forzar_precio_mayorista_raw = data.get('forzar_precio_mayorista', False)
        client_request_id = (data.get('client_request_id') or '').strip()
        reparacion_id = data.get('reparacion_id')
        observaciones = (data.get('observaciones') or '').strip()

        if reparacion_id not in (None, ''):
            return jsonify({'error': 'El envío a caja para reparaciones se implementa en el siguiente bloque'}), 400

        if client_request_id and len(client_request_id) > 64:
            return jsonify({'error': 'client_request_id inválido'}), 400

        try:
            id_cliente = int(id_cliente)
        except Exception:
            return jsonify({'error': 'Cliente inválido'}), 400

        cliente = db.session.get(Cliente, id_cliente)
        if not cliente or not bool(cliente.activo):
            return jsonify({'error': 'Cliente no encontrado o inactivo'}), 400

        ocultar_selector_vendedor_pos = _ocultar_selector_vendedor_pos()
        vendedores_cajeros = _usuarios_vendedores_cajeros_activos()
        ids_vendedores = {int(u.id_usuario) for u in vendedores_cajeros}
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
                return jsonify({'error': 'Vendedor/Cajero inválido'}), 400
        if (not ocultar_selector_vendedor_pos) and ids_vendedores and id_usuario_vendedor not in ids_vendedores:
            return jsonify({'error': 'Debe seleccionar un vendedor/cajero válido'}), 400

        cliente_tipo = (cliente.tipo or '').strip().lower()
        usar_precio_mayorista = _is_truthy(forzar_precio_mayorista_raw) or (cliente_tipo in ('mayorista', 'empresa'))
        try:
            items_normalizados, subtotal = _normalizar_items_para_cola_cobro(items, usar_precio_mayorista=usar_precio_mayorista)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        total = subtotal - descuento_monto
        if total < 0:
            return jsonify({'error': 'El descuento no puede ser mayor al total'}), 400

        pendiente_existente = _buscar_cola_cobro_venta_activa_por_request_id(client_request_id)
        if pendiente_existente:
            return jsonify({
                'success': True,
                'cola_id': int(pendiente_existente.id),
                'mensaje': f'La venta ya estaba enviada a caja como pendiente #{pendiente_existente.id}'
            })

        metadata = {
            'client_request_id': client_request_id or None,
            'id_usuario_vendedor': int(id_usuario_vendedor),
            'descuento': float(descuento_monto or 0),
            'forzar_precio_mayorista': bool(usar_precio_mayorista),
            'observaciones': observaciones,
            'items': items_normalizados,
        }

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=id_cliente,
            monto_total=total,
            id_usuario_origen=id_usuario_vendedor,
            estado='pendiente',
        )
        pendiente.set_metadata(metadata)
        db.session.add(pendiente)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='enviar_a_caja',
                    modulo='ventas',
                    descripcion=f'Envió venta a caja como pendiente #{pendiente.id}',
                    referencia_tipo='cola_cobro',
                    referencia_id=pendiente.id,
                    datos_nuevos={
                        'tipo_origen': 'venta',
                        'cliente_id': id_cliente,
                        'id_usuario_vendedor': id_usuario_vendedor,
                        'monto_total': float(total or 0),
                        'client_request_id': client_request_id or None,
                    },
                    commit=False
                )
        except Exception:
            pass
        
        db.session.commit()
        return jsonify({
            'success': True,
            'cola_id': int(pendiente.id),
            'mensaje': f'Venta enviada a caja como pendiente #{pendiente.id}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

