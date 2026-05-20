from .base_y_listado import *
from .procesamiento import _procesar_venta_payload, _venta_existente_response

@ventas_bp.route('/procesar', methods=['POST'])
@login_required
@caja_abierta_required
def procesar():
    """Procesar una venta"""
    try:
        data = request.get_json(silent=True) or {}
        payload, status = _procesar_venta_payload(data)
        return jsonify(payload), status
    except IntegrityError:
        db.session.rollback()
        try:
            data = request.get_json(silent=True) or {}
            client_request_id = (data.get('client_request_id') or '').strip()
            if client_request_id:
                existente = Venta.query.filter_by(client_request_id=client_request_id).first()
                if existente:
                    return jsonify(_venta_existente_response(existente))
        except Exception:
            pass
        return jsonify({'error': 'Conflicto al registrar la venta'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
@ventas_bp.route('/<int:id>')
@login_required
def detalle(id):
    """Ver detalle de una venta"""
    if not current_user.tiene_permiso('ver_detalle_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver el detalle de ventas.', 'danger')
        return redirect(url_for('ventas.listar'))

    venta = Venta.query.options(
        joinedload(Venta.cliente),
        joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
        joinedload(Venta.vendedor)
    ).filter(Venta.id_venta == id).first()
    if venta is None:
        abort(404)
    return render_template('ventas/detalle.html', venta=venta)


@ventas_bp.route('/<int:id>/ticket')
@login_required
def ticket(id):
    """Imprimir ticket de una venta"""
    if not (current_user.es_admin() or current_user.tiene_permiso('ver_detalle_venta') or current_user.tiene_permiso('crear_venta')):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para imprimir tickets.', 'danger')
        return redirect(url_for('ventas.listar'))

    preview = request.args.get('preview') == '1'
    embedded = request.args.get('embedded') == '1'
    venta = Venta.query.options(
        joinedload(Venta.cliente),
        joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
        joinedload(Venta.vendedor)
    ).filter(Venta.id_venta == id).first()
    if venta is None:
        abort(404)
    detalles = venta.detalles.all()
    pagos = venta.pagos.all()
    
    # Actualizar contador de impresiones si no es preview
    if not preview and venta.ticket:
        from datetime import datetime
        venta.ticket.cantidad_impresiones += 1
        venta.ticket.fecha_ultima_impresion = datetime.utcnow()
        db.session.commit()

    empresa = {
        'nombre': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or ''
    }

    total_pagado = sum(float(p.monto) for p in pagos)
    total = float(venta.total or 0)
    vuelto = max(0, total_pagado - total)
    moneda_simbolo = '₲' if preview else 'Gs'
    footer_text = Configuracion.obtener('ticket_footer_text', 'Gracias por su compra') or 'Gracias por su compra'
    template_html = (Configuracion.obtener('ticket_template_html', '') or '').strip()

    try:
        subtotal = float(getattr(venta, 'subtotal', venta.total) or 0)
    except Exception:
        subtotal = float(total or 0)
    try:
        descuento = float(getattr(venta, 'descuento_monto', 0) or 0)
    except Exception:
        descuento = 0.0
    pagos_resumen = _build_pagos_resumen(pagos)

    ctx = dict(
        venta=venta,
        detalles=detalles,
        pagos=pagos,
        pagos_resumen=pagos_resumen,
        empresa=empresa,
        subtotal=subtotal,
        descuento=descuento,
        total_pagado=total_pagado,
        vuelto=vuelto,
        preview=preview,
        embedded=embedded,
        moneda_simbolo=moneda_simbolo,
        footer_text=footer_text,
    )

    if template_html:
        try:
            html = render_template_string(template_html, **ctx)
            return _enforce_ticket_light_background(html)
        except TemplateSyntaxError as e:
            pos = None
            m = re.search(r'at (\d+)\s*$', str(e))
            if m:
                try:
                    pos = int(m.group(1))
                except Exception:
                    pos = None
            if pos is not None:
                snippet = template_html[max(0, pos - 120):pos + 120]
                current_app.logger.error('Error en ticket_template_html cerca de: %r', snippet)
            current_app.logger.exception('Error de sintaxis en ticket_template_html; usando plantilla por defecto')

    return render_template('ventas/ticket.html', **ctx)


@ventas_bp.route('/config/ticket', methods=['GET', 'POST'])
@login_required
def config_ticket():
    if not (current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar el ticket.', 'danger')
        return redirect(url_for('main.dashboard'))

    from pathlib import Path
    ticket_path = Path(current_app.root_path) / 'templates' / 'ventas' / 'ticket.html'
    try:
        default_template_html = ticket_path.read_text(encoding='utf-8')
    except Exception:
        default_template_html = ''

    if request.method == 'POST':
        nombre = (request.form.get('nombre_empresa') or '').strip()
        ruc = (request.form.get('ruc_empresa') or '').strip()
        direccion = (request.form.get('direccion_empresa') or '').strip()
        telefono = (request.form.get('telefono_empresa') or '').strip()
        footer_text = (request.form.get('ticket_footer_text') or '').strip()
        template_html = request.form.get('ticket_template_html') or ''

        Configuracion.establecer('nombre_empresa', nombre, 'Nombre de la empresa')
        Configuracion.establecer('ruc_empresa', ruc, 'RUC de la empresa')
        Configuracion.establecer('direccion_empresa', direccion, 'Dirección fiscal')
        Configuracion.establecer('telefono_empresa', telefono, 'Teléfono de contacto')
        Configuracion.establecer('ticket_footer_text', footer_text, 'Texto del pie del ticket')
        Configuracion.establecer('ticket_template_html', template_html, 'Plantilla HTML del ticket')

        flash('Ticket actualizado correctamente.', 'success')
        return redirect(url_for('ventas.config_ticket'))

    last_sale = Venta.query.order_by(Venta.id_venta.desc()).first()
    id_venta_preview = last_sale.id_venta if last_sale else ''

    data = {
        'nombre_empresa': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc_empresa': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion_empresa': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono_empresa': Configuracion.obtener('telefono_empresa', '') or '',
        'ticket_footer_text': Configuracion.obtener('ticket_footer_text', 'Gracias por su compra') or 'Gracias por su compra',
        'ticket_template_html': Configuracion.obtener('ticket_template_html', '') or '',
    }

    return render_template(
        'ventas/ticket_config.html',
        data=data,
        default_template_html=default_template_html,
        id_venta_preview=id_venta_preview,
    )


@ventas_bp.route('/config/ticket/preview', methods=['POST'])
@login_required
def config_ticket_preview():
    if not (current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'success': False, 'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'success': False, 'error': 'Sin permisos', 'modo_demo': False}), 403

    payload = request.get_json(silent=True) or {}
    id_venta = payload.get('id_venta')
    template_html = payload.get('ticket_template_html') or ''
    footer_text = (payload.get('ticket_footer_text') or 'Gracias por su compra').strip() or 'Gracias por su compra'

    empresa = {
        'nombre': (payload.get('nombre_empresa') or '').strip(),
        'ruc': (payload.get('ruc_empresa') or '').strip(),
        'direccion': (payload.get('direccion_empresa') or '').strip(),
        'telefono': (payload.get('telefono_empresa') or '').strip(),
    }

    venta = None
    if id_venta not in (None, '', 0, '0'):
        try:
            venta = db.session.get(Venta, int(id_venta))
        except Exception:
            venta = None

    if not venta:
        venta = Venta.query.order_by(Venta.id_venta.desc()).first()

    if venta:
        detalles = venta.detalles.all()
        pagos = venta.pagos.all()
        total_pagado = sum(float(p.monto) for p in pagos)
        total = float(venta.total or 0)
        vuelto = max(0, total_pagado - total)
        try:
            subtotal = float(getattr(venta, 'subtotal', venta.total) or 0)
        except Exception:
            subtotal = float(total or 0)
        try:
            descuento = float(getattr(venta, 'descuento_monto', 0) or 0)
        except Exception:
            descuento = 0.0
    else:
        from types import SimpleNamespace
        from datetime import datetime
        venta = SimpleNamespace(
            id_venta=1,
            fecha_venta=datetime.utcnow(),
            total=28000,
            subtotal=30000,
            descuento_monto=2000,
            cliente=SimpleNamespace(nombre='CONSUMIDOR FINAL')
        )
        producto = SimpleNamespace(nombre='Producto de ejemplo')
        detalles = [SimpleNamespace(producto=producto, precio_unitario=28000, subtotal=28000, cantidad=1)]
        pagos = [SimpleNamespace(metodo=SimpleNamespace(nombre='Efectivo'), monto=28000)]
        total_pagado = 28000
        vuelto = 0
        subtotal = 30000
        descuento = 2000

    moneda_simbolo = '₲'
    preview = True
    pagos_resumen = _build_pagos_resumen(pagos)

    ctx = dict(
        venta=venta,
        detalles=detalles,
        pagos=pagos,
        pagos_resumen=pagos_resumen,
        empresa=empresa,
        subtotal=subtotal,
        descuento=descuento,
        total_pagado=total_pagado,
        vuelto=vuelto,
        preview=preview,
        moneda_simbolo=moneda_simbolo,
        footer_text=footer_text,
    )

    try:
        if template_html.strip():
            html = render_template_string(template_html, **ctx)
        else:
            html = render_template('ventas/ticket.html', **ctx)
        return jsonify({'success': True, 'html': _enforce_ticket_light_background(html)})
    except TemplateSyntaxError as e:
        pos = None
        m = re.search(r'at (\d+)\s*$', str(e))
        if m:
            try:
                pos = int(m.group(1))
            except Exception:
                pos = None
        if pos is not None:
            snippet = template_html[max(0, pos - 120):pos + 120]
            return jsonify({'success': False, 'error': f'{e} | cerca de: {snippet}'}), 400
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@ventas_bp.route('/<int:id>/anular', methods=['POST'])
@login_required
def anular(id):
    """Anular una venta"""
    venta = db.session.get(Venta, id)
    if venta is None:
        abort(404)

    if not current_user.es_admin() and not current_user.tiene_permiso('anular_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para anular ventas.', 'danger')
        return redirect(url_for('ventas.detalle', id=id))
    
    if venta.estado == 'anulada':
        flash('Esta venta ya está anulada.', 'warning')
        return redirect(url_for('ventas.detalle', id=id))

    id_autorizacion = request.form.get('id_autorizacion', type=int)
    ok, autorizacion = validar_autorizacion(id_autorizacion, 'anular_venta')
    if not ok:
        flash(str(autorizacion), 'danger')
        return redirect(url_for('ventas.detalle', id=id))
    
    devueltos_rows = (
        db.session.query(
            DetalleDevolucion.id_detalle_venta_original,
            func.coalesce(func.sum(DetalleDevolucion.cantidad), 0),
        )
        .join(Devolucion, DetalleDevolucion.id_devolucion == Devolucion.id_devolucion)
        .filter(
            Devolucion.id_venta == venta.id_venta,
            Devolucion.estado != 'anulada',
            Devolucion.accion_stock == 'retorno_stock',
        )
        .group_by(DetalleDevolucion.id_detalle_venta_original)
        .all()
    )
    devuelto_por_detalle = {
        int(r[0]): int(r[1] or 0) for r in devueltos_rows if r and r[0] is not None
    }

    reparacion_reabierta_id = None
    if getattr(venta, 'id_reparacion', None):
        try:
            rid = int(venta.id_reparacion)
        except Exception:
            rid = None
        if rid:
            reparacion_obj = db.session.get(Reparacion, rid)
            if reparacion_obj:
                estado_anterior = (reparacion_obj.estado or '').strip()
                if estado_anterior.lower() == 'entregado':
                    reparacion_obj.estado = 'listo'
                    reparacion_obj.fecha_entrega = None
                    db.session.add(
                        ReparacionHistorialEstado(
                            id_reparacion=reparacion_obj.id_reparacion,
                            estado_anterior=estado_anterior or None,
                            estado_nuevo='listo',
                            nota=f'Reapertura por anulación de venta #{venta.id_venta}'
                        )
                    )
                    reparacion_reabierta_id = reparacion_obj.id_reparacion
            venta.id_reparacion = None

    # Restaurar stock
    for detalle in venta.detalles.all():
        producto = detalle.producto
        if not producto or bool(getattr(producto, 'es_servicio', False)):
            continue
        cantidad_devuelta = int(devuelto_por_detalle.get(int(detalle.id_detalle_venta), 0) or 0)
        cantidad_a_restaurar = int(detalle.cantidad or 0) - cantidad_devuelta
        if cantidad_a_restaurar <= 0:
            continue
        stock_anterior = producto.stock_actual
        producto.stock_actual += cantidad_a_restaurar
        
        movimiento = MovimientoStock(
            id_producto=producto.id_producto,
            id_usuario=current_user.id_usuario,
            tipo_movimiento='entrada',
            cantidad=cantidad_a_restaurar,
            stock_anterior=stock_anterior,
            stock_nuevo=producto.stock_actual,
            referencia_tipo='anulacion_venta',
            referencia_id=venta.id_venta,
            motivo=f'Anulación de venta #{venta.id_venta}'
        )
        db.session.add(movimiento)

    movimientos_caja_venta = (
        MovimientoCaja.query.filter_by(
            id_sesion_caja=venta.id_sesion_caja,
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
        )
        .order_by(MovimientoCaja.id_movimiento_caja.asc())
        .all()
    )
    from datetime import datetime

    if movimientos_caja_venta:
        for mov in movimientos_caja_venta:
            tipo_original = (mov.tipo or '').strip().lower()
            if tipo_original not in {'ingreso', 'egreso'}:
                continue
            tipo_reverso = 'egreso' if tipo_original == 'ingreso' else 'ingreso'
            motivo_base = (mov.motivo or '').strip()
            motivo_reverso = f'Anulación venta #{venta.id_venta}: {motivo_base}'.strip()
            if len(motivo_reverso) > 200:
                motivo_reverso = motivo_reverso[:200]
            db.session.add(
                MovimientoCaja(
                    id_sesion_caja=mov.id_sesion_caja,
                    id_usuario=current_user.id_usuario,
                    tipo=tipo_reverso,
                    monto=mov.monto,
                    motivo=motivo_reverso or f'Anulación venta #{venta.id_venta}',
                    referencia_tipo='anulacion_venta',
                    referencia_id=venta.id_venta,
                    fecha_movimiento=datetime.utcnow(),
                )
            )
    else:
        def _norm_metodo_pago_nombre(nombre: str) -> str:
            s = (nombre or '').strip().lower()
            s = s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
            return ' '.join(s.split())

        metodos = MetodoPago.query.all()
        metodo_efectivo = None
        for m in metodos:
            if _norm_metodo_pago_nombre(getattr(m, 'nombre', '') or '') == 'efectivo':
                metodo_efectivo = m
                break
        if metodo_efectivo is None:
            candidatos = [m for m in metodos if 'efectivo' in _norm_metodo_pago_nombre(getattr(m, 'nombre', '') or '')]
            if candidatos:
                candidatos.sort(key=lambda x: (int(getattr(x, 'orden_display', 0) or 0), int(getattr(x, 'id_metodo_pago', 0) or 0)))
                metodo_efectivo = candidatos[0]

        efectivo_id = int(getattr(metodo_efectivo, 'id_metodo_pago', 1) or 1)
        total_efectivo_pagado = (
            db.session.query(func.sum(PagoVenta.monto))
            .filter(PagoVenta.id_venta == venta.id_venta, PagoVenta.id_metodo_pago == efectivo_id)
            .scalar()
        )
        if total_efectivo_pagado and Decimal(str(total_efectivo_pagado)) > 0:
            motivo_reverso = f'Anulación venta #{venta.id_venta}: ajuste efectivo'.strip()
            if len(motivo_reverso) > 200:
                motivo_reverso = motivo_reverso[:200]
            db.session.add(
                MovimientoCaja(
                    id_sesion_caja=venta.id_sesion_caja,
                    id_usuario=current_user.id_usuario,
                    tipo='egreso',
                    monto=total_efectivo_pagado,
                    motivo=motivo_reverso,
                    referencia_tipo='anulacion_venta',
                    referencia_id=venta.id_venta,
                    fecha_movimiento=datetime.utcnow(),
                )
            )
    
    venta.estado = 'anulada'
    db.session.commit()

    try:
        id_aut = int(getattr(autorizacion, 'id_autorizacion', 0) or 0) if autorizacion else None
        if not id_aut:
            id_aut = None
        registrar_auditoria(
            accion='anular_venta',
            modulo='ventas',
            descripcion=f'Anulación de venta #{venta.id_venta}',
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
            id_autorizacion=id_aut
        )
    except Exception:
        pass
    
    if reparacion_reabierta_id:
        flash(
            f'Venta #{id} anulada. Stock restaurado. Reparación #{reparacion_reabierta_id} reabierta para cobrar nuevamente.',
            'success'
        )
    else:
        flash(f'Venta #{id} anulada. Stock restaurado.', 'success')
    return redirect(url_for('ventas.detalle', id=id))


@ventas_bp.route('/<int:id>/devolucion', methods=['POST'])
@login_required
@caja_abierta_required
def crear_devolucion(id):
    """Registrar devolución parcial/total de una venta"""
    try:
        if not current_user.es_admin() and not current_user.tiene_permiso('anular_venta'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

        venta = db.session.get(Venta, id)
        if venta is None:
            abort(404)
        if venta.estado != 'completada':
            return jsonify({'error': 'La venta no está en estado válido para devolución'}), 400

        sesion = SesionCaja.query.filter_by(
            id_usuario=current_user.id_usuario,
            estado='abierta'
        ).first()
        if not sesion:
            return jsonify({'error': 'No hay caja abierta'}), 400

        data = request.get_json() or {}
        items = data.get('items', [])
        motivo = (data.get('motivo') or '').strip()
        accion_stock = (data.get('accion_stock') or 'retorno_stock').strip()
        metodo_reembolso = (data.get('metodo_reembolso') or 'efectivo').strip()
        observaciones = data.get('observaciones', '')
        id_autorizacion = data.get('id_autorizacion')
        if id_autorizacion in (None, ''):
            id_autorizacion = None
        else:
            id_autorizacion = int(id_autorizacion)

        if not items:
            return jsonify({'error': 'Debe indicar al menos un ítem para devolver'}), 400
        if not motivo:
            return jsonify({'error': 'Debe indicar el motivo de la devolución'}), 400
        if accion_stock not in ['retorno_stock', 'descarte', 'ninguna']:
            return jsonify({'error': 'accion_stock inválido'}), 400

        cantidades_por_detalle = {}
        for item in items:
            try:
                id_detalle_venta = int(item.get('id_detalle_venta'))
                cantidad = int(item.get('cantidad'))
            except Exception:
                return jsonify({'error': 'Ítem inválido'}), 400
            if cantidad <= 0:
                return jsonify({'error': f'Cantidad inválida para detalle {id_detalle_venta}'}), 400
            cantidades_por_detalle[id_detalle_venta] = cantidades_por_detalle.get(id_detalle_venta, 0) + cantidad

        if not cantidades_por_detalle:
            return jsonify({'error': 'Debe indicar al menos un ítem para devolver'}), 400

        ok, autorizacion = validar_autorizacion(id_autorizacion, 'anular_venta')
        if not ok:
            return jsonify({'error': str(autorizacion), 'codigo_permiso': 'anular_venta'}), 403

        detalles_venta_por_id = {int(d.id_detalle_venta): d for d in venta.detalles.all()}
        detalle_ids = sorted(int(x) for x in cantidades_por_detalle.keys())
        devueltos_rows = (
            db.session.query(
                DetalleDevolucion.id_detalle_venta_original,
                func.coalesce(func.sum(DetalleDevolucion.cantidad), 0),
            )
            .join(Devolucion, DetalleDevolucion.id_devolucion == Devolucion.id_devolucion)
            .filter(
                Devolucion.id_venta == venta.id_venta,
                Devolucion.estado != 'anulada',
                DetalleDevolucion.id_detalle_venta_original.in_(detalle_ids),
            )
            .group_by(DetalleDevolucion.id_detalle_venta_original)
            .all()
        )
        devueltos_por_detalle = {int(r[0]): int(r[1] or 0) for r in devueltos_rows if r and r[0] is not None}

        monto_total = Decimal('0')
        items_auditoria = []
        items_normalizados = []

        for id_detalle_venta in detalle_ids:
            cantidad = int(cantidades_por_detalle.get(id_detalle_venta) or 0)
            detalle_venta = detalles_venta_por_id.get(id_detalle_venta)
            if not detalle_venta:
                return jsonify({'error': f'Detalle de venta no encontrado: {id_detalle_venta}'}), 400

            cantidad_original = int(detalle_venta.cantidad)
            cantidad_devuelta = int(devueltos_por_detalle.get(id_detalle_venta) or 0)
            disponible = cantidad_original - cantidad_devuelta
            if disponible <= 0:
                return jsonify({'error': f'No hay cantidad disponible para devolver en detalle {id_detalle_venta}'}), 400
            if cantidad > disponible:
                return jsonify({'error': f'Cantidad inválida para detalle {id_detalle_venta}. Disponible: {disponible}'}), 400

            precio_unitario = Decimal(str(detalle_venta.precio_unitario))
            subtotal = precio_unitario * Decimal(str(cantidad))
            monto_total += subtotal
            items_normalizados.append((detalle_venta, cantidad, subtotal))

            items_auditoria.append({
                'id_detalle_venta': id_detalle_venta,
                'id_producto': detalle_venta.id_producto,
                'cantidad': cantidad,
                'precio_unitario': float(detalle_venta.precio_unitario or 0),
                'subtotal': float(subtotal or 0),
            })

        devolucion = Devolucion(
            id_venta=venta.id_venta,
            id_usuario=current_user.id_usuario,
            id_sesion_caja=sesion.id_sesion,
            motivo=motivo,
            accion_stock=accion_stock,
            monto_total=monto_total,
            metodo_reembolso=metodo_reembolso,
            observaciones=observaciones
        )
        db.session.add(devolucion)
        db.session.flush()

        for detalle_venta, cantidad, subtotal in items_normalizados:
            detalle_dev = DetalleDevolucion(
                id_devolucion=devolucion.id_devolucion,
                id_producto=detalle_venta.id_producto,
                id_detalle_venta_original=detalle_venta.id_detalle_venta,
                cantidad=cantidad,
                precio_unitario=detalle_venta.precio_unitario,
                subtotal=subtotal
            )
            db.session.add(detalle_dev)

            if accion_stock == 'retorno_stock' and not detalle_venta.producto.es_servicio:
                producto = detalle_venta.producto
                stock_anterior = int(producto.stock_actual or 0)
                producto.stock_actual = stock_anterior + cantidad

                movimiento_stock = MovimientoStock(
                    id_producto=producto.id_producto,
                    id_usuario=current_user.id_usuario,
                    tipo_movimiento='entrada',
                    cantidad=cantidad,
                    stock_anterior=stock_anterior,
                    stock_nuevo=int(producto.stock_actual),
                    referencia_tipo='devolucion',
                    referencia_id=devolucion.id_devolucion,
                    motivo=f'Devolución #{devolucion.id_devolucion} de venta #{venta.id_venta}'
                )
                db.session.add(movimiento_stock)

        if metodo_reembolso.lower() == 'efectivo' and monto_total > 0:
            movimiento_caja = MovimientoCaja(
                id_sesion_caja=sesion.id_sesion,
                id_usuario=current_user.id_usuario,
                tipo='egreso',
                monto=monto_total,
                motivo=f'Reembolso devolución #{devolucion.id_devolucion} venta #{venta.id_venta}',
                referencia_tipo='devolucion',
                referencia_id=devolucion.id_devolucion
            )
            db.session.add(movimiento_caja)

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_devolucion',
                    modulo='ventas',
                    descripcion=f'Devolución registrada para venta #{venta.id_venta}',
                    referencia_tipo='devolucion',
                    referencia_id=devolucion.id_devolucion,
                    datos_nuevos={
                        'id_venta': venta.id_venta,
                        'id_sesion_caja': sesion.id_sesion,
                        'motivo': motivo,
                        'accion_stock': accion_stock,
                        'metodo_reembolso': metodo_reembolso,
                        'monto_total': float(monto_total or 0),
                        'items': items_auditoria,
                    },
                    id_autorizacion=autorizacion.id_autorizacion if autorizacion else None,
                    commit=False
                )
        except Exception:
            pass

        db.session.commit()
        return jsonify({
            'success': True,
            'id_devolucion': devolucion.id_devolucion,
            'monto_total': float(monto_total)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
