"""Envio de borradores de venta a la cola de cobro."""
from .parte1 import *
from app.services.clientes_fidelizacion import resolver_descuento_beneficio_pos
from app.services.clientes_servicios import get_cliente_servicios_cobrables, parse_cliente_servicio_ids


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

        if _modo_cobro_exclusivo_cajero_activo() or _usuario_puede_tomar_cola_cobro():
            sesion = SesionCaja.query.filter_by(
                id_usuario=current_user.id_usuario,
                estado='abierta',
            ).first()
            if not sesion:
                return jsonify({
                    'success': False,
                    'error': 'Debe abrir una caja antes de enviar o cobrar la venta.',
                    'redirect_url': url_for('caja.abrir'),
                }), 400

        data = request.get_json() or {}
        items = data.get('items', [])
        id_cliente = data.get('id_cliente', 1)
        id_usuario_vendedor_raw = data.get('id_usuario_vendedor')
        cliente_servicio_ids = parse_cliente_servicio_ids([
            data.get('cliente_servicio_ids'),
            data.get('cliente_servicio_id'),
        ])
        agenda_actividad_id = data.get('agenda_actividad_id')
        descuento_monto = Decimal(str(data.get('descuento', 0) or 0))
        beneficio_fidelizacion_id = data.get('beneficio_fidelizacion_id')
        usar_precio_mayorista_raw = data.get('usar_precio_mayorista', None)
        forzar_precio_mayorista_raw = data.get('forzar_precio_mayorista', False)
        client_request_id = (data.get('client_request_id') or '').strip()
        reparacion_id = data.get('reparacion_id')
        observaciones = (data.get('observaciones') or '').strip()

        if reparacion_id not in (None, ''):
            return jsonify({'error': 'El envío a caja para reparaciones se implementa en el siguiente bloque'}), 400

        if client_request_id and len(client_request_id) > 64:
            return jsonify({'error': 'client_request_id inválido'}), 400

        if beneficio_fidelizacion_id not in (None, '', 0, '0'):
            try:
                beneficio_fidelizacion_id = int(beneficio_fidelizacion_id)
            except Exception:
                return jsonify({'error': 'Beneficio de fidelización inválido'}), 400

        try:
            id_cliente = int(id_cliente)
        except Exception:
            return jsonify({'error': 'Cliente inválido'}), 400

        cliente = db.session.get(Cliente, id_cliente)
        if not cliente or not bool(cliente.activo):
            return jsonify({'error': 'Cliente no encontrado o inactivo'}), 400

        if cliente_servicio_ids:
            try:
                get_cliente_servicios_cobrables(cliente_servicio_ids, id_cliente=id_cliente)
            except ValueError as exc:
                mensaje = str(exc)
                status_code = 404 if 'no encontrado' in mensaje.lower() else 400
                return jsonify({'error': mensaje}), status_code

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
        if usar_precio_mayorista_raw is None:
            usar_precio_mayorista = _is_truthy(forzar_precio_mayorista_raw) or (cliente_tipo in ('mayorista', 'empresa'))
        else:
            usar_precio_mayorista = _is_truthy(usar_precio_mayorista_raw)
        try:
            items_normalizados, subtotal = _normalizar_items_para_cola_cobro(items, usar_precio_mayorista=usar_precio_mayorista)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        try:
            beneficio_descuento_ctx = resolver_descuento_beneficio_pos(
                id_cliente,
                beneficio_fidelizacion_id,
                subtotal,
                descuento_monto,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        descuento_beneficio_monto = Decimal(str(beneficio_descuento_ctx['descuento_adicional'] or 0))

        total = subtotal - descuento_monto - descuento_beneficio_monto
        if total <= 0:
            return jsonify({'error': 'El total de la venta debe ser mayor a cero'}), 400

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
            'descuento_beneficio': float(descuento_beneficio_monto or 0),
            'beneficio_fidelizacion_id': beneficio_fidelizacion_id if beneficio_fidelizacion_id not in (None, '', 0, '0') else None,
            'beneficio_fidelizacion_resumen': beneficio_descuento_ctx['beneficio_resumen'] or '',
            'cliente_servicio_id': cliente_servicio_ids[0] if len(cliente_servicio_ids) == 1 else None,
            'cliente_servicio_ids': cliente_servicio_ids,
            'agenda_actividad_id': agenda_actividad_id,
            'usar_precio_mayorista': bool(usar_precio_mayorista),
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
