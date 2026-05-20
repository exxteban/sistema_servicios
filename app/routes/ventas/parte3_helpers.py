from .parte1 import *
from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO
from cobranzas.services.credito_service import calcular_compromiso_credito


def _normalizar_pagos_venta(pagos, id_autorizacion):
    autorizacion_venta_credito = None
    ids_metodo_efectivo = set()
    ids_metodo_credito = set()
    pagos_normalizados = []

    if not pagos:
        return {
            'autorizacion_venta_credito': autorizacion_venta_credito,
            'ids_metodo_efectivo': ids_metodo_efectivo,
            'ids_metodo_credito': ids_metodo_credito,
            'pagos_normalizados': pagos_normalizados,
        }, None

    metodo_ids = set()
    for pago in pagos:
        try:
            id_metodo_pago = int(pago.get('id_metodo_pago'))
        except Exception:
            return None, ({'error': 'Metodo de pago invalido'}, 400)
        try:
            monto_pago = Decimal(str(pago.get('monto', 0)))
        except Exception:
            return None, ({'error': 'Monto de pago invalido'}, 400)
        if monto_pago <= 0:
            return None, ({'error': 'El monto de cada pago debe ser mayor a cero'}, 400)
        referencia_pago = (pago.get('referencia') or '').strip()

        metodo_ids.add(id_metodo_pago)
        pagos_normalizados.append({
            'id_metodo_pago': id_metodo_pago,
            'monto': monto_pago,
            'referencia': referencia_pago,
        })

    if metodo_ids:
        metodos = MetodoPago.query.filter(MetodoPago.id_metodo_pago.in_(list(metodo_ids))).all()
        metodo_ids_encontrados = {int(m.id_metodo_pago) for m in metodos}
        metodos_por_id = {int(m.id_metodo_pago): m for m in metodos}
        ids_metodo_faltantes = sorted(metodo_ids - metodo_ids_encontrados)
        if ids_metodo_faltantes:
            return None, ({'error': f'Metodo de pago no encontrado: {ids_metodo_faltantes[0]}'}, 400)
        metodos_inactivos = [m for m in metodos if not bool(m.activo)]
        if metodos_inactivos:
            metodo_inactivo = sorted(
                metodos_inactivos,
                key=lambda metodo: (int(metodo.orden_display or 0), int(metodo.id_metodo_pago or 0))
            )[0]
            return None, ({'error': f'Metodo de pago inactivo: {metodo_inactivo.nombre}'}, 400)
        metodo_credito_tienda = _resolver_metodo_credito_tienda(metodos, solo_activos=True)
        from app.services.caja_metodos import obtener_metodo_efectivo_id as _get_efectivo_id
        efectivo_id_canonico = _get_efectivo_id(metodos)
        ids_metodo_efectivo = (
            {int(efectivo_id_canonico)} if efectivo_id_canonico is not None else set()
        )
        ids_metodo_credito = set()
        if metodo_credito_tienda is not None:
            metodo_credito_id = int(metodo_credito_tienda.id_metodo_pago)
            if metodo_credito_id in metodo_ids:
                ids_metodo_credito.add(metodo_credito_id)
        usa_credito = any(int(m.id_metodo_pago) in ids_metodo_credito for m in metodos)
        if usa_credito:
            for pago in pagos_normalizados:
                metodo = metodos_por_id.get(int(pago['id_metodo_pago']))
                if bool(getattr(metodo, 'requiere_referencia', False)) and not (pago.get('referencia') or '').strip():
                    return None, ({'error': f'El metodo de pago {metodo.nombre} requiere referencia'}, 400)
            if not Configuracion.obtener_bool(CLAVE_VENTAS_CREDITO_ACTIVO, default=False):
                return None, ({'error': 'Venta a cr?dito deshabilitada'}, 403)
            if not current_user.es_admin():
                ok, autorizacion_venta_credito = validar_autorizacion(id_autorizacion, 'venta_credito')
                if not ok:
                    return None, ({'error': autorizacion_venta_credito, 'codigo_permiso': 'venta_credito'}, 403)

    return {
        'autorizacion_venta_credito': autorizacion_venta_credito,
        'ids_metodo_efectivo': ids_metodo_efectivo,
        'ids_metodo_credito': ids_metodo_credito,
        'pagos_normalizados': pagos_normalizados,
    }, None


def _validar_credito_cliente(id_cliente, monto_comprometido_credito):
    monto_comprometido_credito = Decimal(str(monto_comprometido_credito or 0))
    if monto_comprometido_credito <= 0:
        return None

    cliente = (
        Cliente.query
        .filter(Cliente.id_cliente == int(id_cliente))
        .with_for_update()
        .first()
    )
    if not cliente or not bool(cliente.activo):
        return {'error': 'Cliente no encontrado o inactivo'}, 400
    if cliente.es_consumidor_final:
        return {'error': 'Debe seleccionar un cliente registrado para ventas a credito'}, 400

    saldo_vigente = (
        db.session.query(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0))
        .filter(
            CuentaPorCobrar.id_cliente == int(cliente.id_cliente),
            CuentaPorCobrar.estado != 'anulada',
        )
        .scalar()
    )
    saldo_vigente = Decimal(str(saldo_vigente or 0))
    limite_credito = Decimal(str(cliente.limite_credito or 0))
    credito_disponible = limite_credito - saldo_vigente
    cliente.saldo_pendiente = saldo_vigente

    if credito_disponible <= 0:
        return {'error': 'El cliente no tiene credito disponible'}, 400
    if monto_comprometido_credito > credito_disponible:
        return {
            'error': f'Credito insuficiente. Disponible: Gs. {credito_disponible:,.0f}'
        }, 400

    return None


def _prefetch_catalogo_venta(items):
    producto_ids_requeridos = set()
    precio_opcion_ids_requeridos = set()

    for item in items:
        try:
            id_producto_item = int(item.get('id_producto'))
        except Exception:
            return None, ({'error': 'Producto inválido'}, 400)
        producto_ids_requeridos.add(id_producto_item)
        precio_opcion_id_item = item.get('precio_opcion_id')
        if precio_opcion_id_item not in (None, ''):
            try:
                precio_opcion_ids_requeridos.add(int(precio_opcion_id_item))
            except Exception:
                return None, ({'error': 'precio_opcion_id inv?lido'}, 400)

    productos_prefetch = (
        Producto.query
        .filter(Producto.id_producto.in_(list(producto_ids_requeridos)))
        .all()
    )
    productos_prefetch_por_id = {int(p.id_producto): p for p in productos_prefetch}
    for id_producto_item in sorted(producto_ids_requeridos):
        if id_producto_item not in productos_prefetch_por_id:
            return None, ({'error': f'Producto no encontrado: {id_producto_item}'}, 400)

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

    return {
        'productos_prefetch_por_id': productos_prefetch_por_id,
        'opciones_precio_por_clave': opciones_precio_por_clave,
    }, None


def _construir_detalles_venta(
    items,
    productos_prefetch_por_id,
    opciones_precio_por_clave,
    cola_cobro,
    reparacion_obj,
    usar_precio_mayorista,
):
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
            return None, ({'error': 'Producto inválido'}, 400)
        producto = productos_prefetch_por_id.get(id_producto_item)
        if not producto:
            return None, ({'error': f'Producto no encontrado: {id_producto_item}'}, 400)

        try:
            cantidad = int(item.get('cantidad', 0))
        except Exception:
            return None, ({'error': f'Cantidad inválida para producto {id_producto_item}'}, 400)
        if cantidad <= 0:
            return None, ({'error': f'Cantidad inválida para producto {id_producto_item}'}, 400)

        if cola_cobro is not None:
            try:
                precio_original = Decimal(str(item.get('precio_base', producto.precio_venta or 0) or 0))
            except Exception:
                return None, ({'error': 'Precio base invalido en el pendiente enviado a caja'}, 400)
            try:
                precio = Decimal(str(item.get('precio')))
            except Exception:
                return None, ({'error': 'Precio invalido en el pendiente enviado a caja'}, 400)
        else:
            precio_original = Decimal(str(producto.precio_venta or 0))
            precio = precio_original

        precio_opcion_id = item.get('precio_opcion_id')
        if precio_opcion_id not in (None, ''):
            try:
                precio_opcion_id = int(precio_opcion_id)
            except Exception:
                return None, ({'error': 'precio_opcion_id inv?lido'}, 400)
            opcion = opciones_precio_por_clave.get((int(producto.id_producto), int(precio_opcion_id)))
            if not opcion:
                return None, ({'error': 'Opci?n de precio inv?lida para el producto'}, 400)
            if cola_cobro is None:
                try:
                    precio = Decimal(str(opcion.precio))
                except Exception:
                    return None, ({'error': 'Precio inv?lido en opci?n de precio'}, 400)
                if precio <= 0:
                    return None, ({'error': 'Precio inv?lido en opci?n de precio'}, 400)

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
                    return None, ({'error': 'Precio inv?lido para costo final de reparaci?n'}, 400)
            if precio < 0:
                return None, ({'error': 'Precio inv?lido para costo final de reparaci?n'}, 400)
        elif cola_cobro is None and usar_precio_mayorista and precio_opcion_id in (None, ''):
            try:
                if producto.precio_mayorista is not None:
                    precio_may = Decimal(str(producto.precio_mayorista))
                    if precio_may > 0:
                        precio = precio_may
            except Exception:
                precio = precio_original
        elif cola_cobro is not None and precio <= 0:
            return None, ({'error': 'Precio invalido en el pendiente enviado a caja'}, 400)

        item_subtotal = precio * cantidad
        if item_subtotal <= 0:
            return None, ({'error': f'Subtotal inválido para producto {id_producto_item}'}, 400)
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

    return {
        'subtotal': subtotal,
        'total_iva_10': total_iva_10,
        'total_iva_5': total_iva_5,
        'total_exenta': total_exenta,
        'detalles': detalles,
        'productos_por_id': productos_por_id,
        'cantidades_por_producto': cantidades_por_producto,
    }, None


def _validar_stock_para_venta(productos_por_id, cantidades_por_producto, id_autorizacion):
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
        if current_user.es_admin() or current_user.tiene_permiso('vender_sin_stock'):
            autorizacion_stock_negativo = None
        else:
            ok, autorizacion_stock_negativo = validar_autorizacion(id_autorizacion, 'vender_sin_stock')
            if not ok:
                if autorizacion_stock_negativo == 'Se requiere autorización de administrador':
                    return None, ({'error': 'Se requiere autorizaci?n de administrador para vender sin stock', 'stock_warnings': stock_warnings}, 403)
                return None, ({'error': 'Sin permiso para vender sin stock', 'stock_warnings': stock_warnings}, 403)

    return {
        'stock_warnings': stock_warnings,
        'autorizacion_stock_negativo': autorizacion_stock_negativo,
    }, None


def _registrar_pagos_y_movimientos_venta(venta, sesion, pagos, pagos_normalizados, ids_metodo_efectivo, total, total_pagado):
    if pagos and not ids_metodo_efectivo:
        metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        if metodo_efectivo:
            ids_metodo_efectivo.add(int(metodo_efectivo.id_metodo_pago))

    precision_tolerancia = Decimal('0.0001')
    vuelto = total_pagado - total
    if vuelto <= precision_tolerancia:
        vuelto = Decimal('0')
    if vuelto > 0:
        efectivo_pagado = Decimal('0')
        no_efectivo_pagado = Decimal('0')
        for pago in pagos_normalizados:
            try:
                if int(pago['id_metodo_pago']) in ids_metodo_efectivo:
                    efectivo_pagado += pago['monto']
                else:
                    no_efectivo_pagado += pago['monto']
            except Exception:
                continue
        if no_efectivo_pagado > precision_tolerancia:
            return None, ({'error': 'Con pagos mixtos no se admite vuelto. Ajuste los montos para que coincidan con el total'}, 400)
        if efectivo_pagado <= precision_tolerancia:
            return None, ({'error': 'El vuelto solo es v?lido con pago en efectivo'}, 400)
        if efectivo_pagado + precision_tolerancia < vuelto:
            return None, ({'error': 'El vuelto supera el efectivo recibido'}, 400)

    for pago in pagos_normalizados:
        id_metodo = int(pago['id_metodo_pago'])
        monto_pago = pago['monto']
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
            referencia_tipo='vuelto',
            referencia_id=venta.id_venta,
            fecha_movimiento=venta.fecha_venta
        ))

    return {'vuelto': vuelto}, None
