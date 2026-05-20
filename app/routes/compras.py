"""
Rutas de gestión de compras
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import date, datetime, timedelta
from itertools import zip_longest
from app import db
from app.models import (
    Producto, Proveedor, Compra, DetalleCompra, MovimientoStock, Categoria,
    SesionCaja, MovimientoCaja, PagoCompra, CuentaPorPagar, MetodoPago
)
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.compra_facturas import extension_permitida, guardar_factura_compra

compras_bp = Blueprint('compras', __name__)


@compras_bp.route('/')
@login_required
def listar():
    """Lista de compras"""
    if not current_user.tiene_permiso('ver_compras'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver compras.', 'danger')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    sort_key = (request.args.get('sort') or 'fecha').strip().lower()
    sort_dir = (request.args.get('dir') or 'desc').strip().lower()
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'

    query = Compra.query.join(Proveedor, Compra.id_proveedor == Proveedor.id_proveedor)

    sort_columns = {
        'id': Compra.id_compra,
        'compra': Compra.id_compra,
        'fecha': Compra.fecha_compra,
        'proveedor': Proveedor.nombre,
        'factura': Compra.numero_factura,
        'condicion': Compra.tipo_compra,
        'total': Compra.total,
    }
    sort_column = sort_columns.get(sort_key, Compra.fecha_compra)

    primary_order = db.desc(sort_column) if sort_dir == 'desc' else db.asc(sort_column)
    secondary_order = db.desc(Compra.id_compra) if sort_dir == 'desc' else db.asc(Compra.id_compra)

    compras = query.order_by(primary_order, secondary_order).paginate(
        page=page, per_page=10, error_out=False
    )

    return render_template('compras/listar.html', compras=compras, sort=sort_key, dir=sort_dir)


@compras_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Registrar nueva compra"""
    if not current_user.tiene_permiso('crear_compra'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para registrar compras.', 'danger')
        return redirect(url_for('compras.listar'))

    def _parse_decimal(value):
        s = str(value or '').strip()
        if not s:
            return Decimal('0')
        s = s.replace('₲', '').replace('Gs.', '').replace('Gs', '').replace(' ', '')
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s and '.' not in s:
            s = s.replace(',', '.')
        elif s.count('.') > 1 and ',' not in s:
            s = s.replace('.', '')
        try:
            return Decimal(s)
        except Exception:
            return Decimal('0')

    if request.method == 'POST':
        id_proveedor = request.form.get('id_proveedor', type=int)
        numero_factura = request.form.get('numero_factura', '').strip()
        raw_fecha_compra = (request.form.get('fecha_compra') or '').strip()
        raw_hora_compra = (request.form.get('hora_compra') or '').strip()
        if raw_fecha_compra:
            try:
                fecha_compra = datetime.strptime(raw_fecha_compra, '%Y-%m-%d').date()
            except ValueError:
                fecha_compra = date.today()
        else:
            fecha_compra = date.today()
        if raw_hora_compra:
            try:
                hora_compra = datetime.strptime(raw_hora_compra, '%H:%M').time()
            except ValueError:
                hora_compra = datetime.now().replace(second=0, microsecond=0).time()
        else:
            hora_compra = datetime.now().replace(second=0, microsecond=0).time()
        tipo_compra = request.form.get('tipo_compra', 'contado')
        es_resumida = request.form.get('es_resumida') in ('1', 'true', 'on', 'si')
        observaciones = request.form.get('observaciones', '').strip()
        factura_imagen = request.files.get('factura_imagen')

        if factura_imagen and factura_imagen.filename and not extension_permitida(factura_imagen.filename):
            flash('La foto de factura debe ser PNG, JPG, JPEG, WEBP o GIF.', 'warning')
            proveedores = Proveedor.query.filter_by(activo=True).all()
            productos_query = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
            productos = [{
                'id_producto': p.id_producto,
                'codigo': p.codigo,
                'nombre': p.nombre,
                'precio_compra': float(p.precio_compra or 0)
            } for p in productos_query]
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            saldo_caja = 0
            sesion_activa = SesionCaja.query.filter_by(
                id_usuario=current_user.id_usuario,
                estado='abierta'
            ).first()
            if sesion_activa:
                saldo_caja = sesion_activa.calcular_total_efectivo()
            return render_template(
                'compras/form.html',
                proveedores=proveedores,
                productos=productos,
                categorias=categorias,
                saldo_caja=saldo_caja
            )

        if tipo_compra == 'contado':
            sesion_activa = SesionCaja.query.filter_by(
                id_usuario=current_user.id_usuario,
                estado='abierta'
            ).first()
            if not sesion_activa:
                flash('Debe tener una caja abierta para registrar compras al contado.', 'warning')
                proveedores = Proveedor.query.filter_by(activo=True).all()
                productos_query = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
                productos = [{
                    'id_producto': p.id_producto,
                    'codigo': p.codigo,
                    'nombre': p.nombre,
                    'precio_compra': float(p.precio_compra or 0)
                } for p in productos_query]
                categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
                return render_template('compras/form.html', proveedores=proveedores, productos=productos, categorias=categorias)
        
        productos_ids = request.form.getlist('producto_id[]')
        productos_texto = request.form.getlist('producto_texto[]')
        cantidades = request.form.getlist('cantidad[]')
        precios = request.form.getlist('precio[]')

        lineas = []
        for prod_id_raw, cant_raw, precio_raw in zip_longest(productos_ids, cantidades, precios, fillvalue=''):
            prod_id_raw = (prod_id_raw or '').strip()
            if not prod_id_raw:
                continue
            try:
                prod_id = int(prod_id_raw)
            except ValueError:
                continue

            try:
                cantidad = int(cant_raw) if str(cant_raw or '').strip() else 0
            except ValueError:
                continue
            precio = _parse_decimal(precio_raw)
            if cantidad <= 0 or precio <= 0:
                continue

            producto = Producto.query.get(prod_id)
            if not producto:
                continue

            lineas.append((producto, cantidad, precio))
        
        if not lineas:
            textos_invalidos = []
            for texto in productos_texto:
                t = (texto or '').strip()
                if t:
                    textos_invalidos.append(t)

            textos_invalidos = list(dict.fromkeys(textos_invalidos))
            if textos_invalidos:
                textos_mostrar = textos_invalidos[:3]
                extra = len(textos_invalidos) - len(textos_mostrar)
                listado = ', '.join(f'"{t}"' for t in textos_mostrar)
                if extra > 0:
                    listado = f'{listado} y {extra} más'
                flash(f'Producto no válido: {listado}. Seleccione un producto de la lista.', 'warning')
            else:
                flash('Debe agregar al menos un producto con cantidad y precio válidos.', 'warning')
            proveedores = Proveedor.query.filter_by(activo=True).all()
            productos_query = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
            productos = [{
                'id_producto': p.id_producto,
                'codigo': p.codigo,
                'nombre': p.nombre,
                'precio_compra': float(p.precio_compra or 0)
            } for p in productos_query]
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            return render_template('compras/form.html', proveedores=proveedores, productos=productos, categorias=categorias)
        
        try:
            with db.session.begin_nested():
                if not id_proveedor:
                    proveedor_generico = Proveedor.query.filter_by(nombre='SIN PROVEEDOR').first()
                    if proveedor_generico:
                        id_proveedor = proveedor_generico.id_proveedor
                    else:
                        proveedor_generico = Proveedor(nombre='SIN PROVEEDOR', ruc='00000000-0', activo=True)
                        db.session.add(proveedor_generico)
                        db.session.flush()
                        id_proveedor = proveedor_generico.id_proveedor

                compra = Compra(
                    id_proveedor=id_proveedor,
                    id_usuario=current_user.id_usuario,
                    numero_factura=numero_factura,
                    fecha_compra=fecha_compra,
                    hora_compra=hora_compra,
                    tipo_compra=tipo_compra,
                    pagada=(tipo_compra == 'contado'),
                    es_resumida=es_resumida,
                    observaciones=observaciones,
                    subtotal=0,
                    total=0
                )
                db.session.add(compra)
                db.session.flush()

                if factura_imagen and factura_imagen.filename:
                    compra.factura_imagen_url = guardar_factura_compra(
                        factura_imagen,
                        current_app.static_folder,
                        fecha_compra,
                        compra.id_compra
                    )
                
                total = Decimal('0')
                total_iva_10 = Decimal('0')
                total_iva_5 = Decimal('0')
                items_auditoria = []
                proveedor = Proveedor.query.get(id_proveedor) if id_proveedor else None
                
                for producto, cantidad, precio in lineas:
                    
                    subtotal_item = precio * cantidad
                    total += subtotal_item
                    
                    if producto.porcentaje_iva == 10:
                        total_iva_10 += subtotal_item / 11
                    elif producto.porcentaje_iva == 5:
                        total_iva_5 += subtotal_item / 21
                    
                    detalle = DetalleCompra(
                        id_compra=compra.id_compra,
                        id_producto=producto.id_producto,
                        cantidad=cantidad,
                        precio_unitario=precio,
                        porcentaje_iva=producto.porcentaje_iva,
                        subtotal=subtotal_item
                    )
                    db.session.add(detalle)
                    
                    stock_anterior = producto.stock_actual
                    producto.stock_actual += cantidad
                    
                    precio_compra_anterior = producto.precio_compra
                    producto.precio_compra = precio
                    
                    movimiento = MovimientoStock(
                        id_producto=producto.id_producto,
                        id_usuario=current_user.id_usuario,
                        tipo_movimiento='entrada',
                        cantidad=cantidad,
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.stock_actual,
                        referencia_tipo='compra',
                        referencia_id=compra.id_compra
                    )
                    db.session.add(movimiento)

                    items_auditoria.append({
                        'id_producto': producto.id_producto,
                        'codigo': producto.codigo,
                        'nombre': producto.nombre,
                        'cantidad': int(cantidad),
                        'precio_unitario': float(precio),
                        'subtotal': float(subtotal_item),
                        'porcentaje_iva': int(producto.porcentaje_iva or 0),
                        'stock_anterior': int(stock_anterior),
                        'stock_nuevo': int(producto.stock_actual),
                        'precio_compra_anterior': float(precio_compra_anterior or 0),
                        'precio_compra_nuevo': float(precio)
                    })
                
                compra.subtotal = total
                compra.total_iva_10 = total_iva_10
                compra.total_iva_5 = total_iva_5
                compra.total = total

                if tipo_compra == 'contado':
                    sesion_activa = SesionCaja.query.filter_by(
                        id_usuario=current_user.id_usuario,
                        estado='abierta'
                    ).first()
                    
                    if sesion_activa:
                        movimiento_caja = MovimientoCaja(
                            id_sesion_caja=sesion_activa.id_sesion,
                            id_usuario=current_user.id_usuario,
                            tipo='egreso',
                            monto=total,
                            motivo=f'Pago Compra #{compra.id_compra}',
                            referencia_tipo='compra',
                            referencia_id=compra.id_compra
                        )
                        db.session.add(movimiento_caja)
                        
                        metodo_pago = MetodoPago.query.filter(MetodoPago.nombre.ilike('efectivo')).first()
                        if not metodo_pago:
                            metodo_pago = MetodoPago.query.first()
                        
                        if total > 0:
                            pago = PagoCompra(
                                id_compra=compra.id_compra,
                                id_metodo_pago=metodo_pago.id_metodo_pago if metodo_pago else 1,
                                id_sesion_caja=sesion_activa.id_sesion,
                                id_usuario=current_user.id_usuario,
                                monto=total,
                                referencia='Pago Contado'
                            )
                            db.session.add(pago)
                        
                        compra.pagada = True
                        
                elif tipo_compra == 'credito':
                    compra.pagada = False
                    fecha_vencimiento = fecha_compra + timedelta(days=30)
                    compra.fecha_vencimiento = fecha_vencimiento
                    
                    cuenta = CuentaPorPagar(
                        id_compra=compra.id_compra,
                        id_proveedor=id_proveedor,
                        monto_total=total,
                        monto_pagado=0,
                        saldo_pendiente=total,
                        fecha_vencimiento=fecha_vencimiento,
                        estado='pendiente'
                    )
                    db.session.add(cuenta)

                registrar_auditoria(
                    accion='crear_compra',
                    modulo='compras',
                    descripcion=f'Registró compra #{compra.id_compra}',
                    referencia_tipo='compra',
                    referencia_id=compra.id_compra,
                    datos_nuevos={
                        'id_compra': compra.id_compra,
                        'id_proveedor': compra.id_proveedor,
                        'proveedor': proveedor.nombre if proveedor else None,
                        'numero_factura': compra.numero_factura,
                        'fecha_compra': compra.fecha_compra.isoformat() if compra.fecha_compra else None,
                        'hora_compra': compra.hora_compra.strftime('%H:%M') if compra.hora_compra else None,
                        'tipo_compra': compra.tipo_compra,
                        'pagada': bool(compra.pagada),
                        'es_resumida': bool(compra.es_resumida),
                        'subtotal': float(compra.subtotal or 0),
                        'total_iva_10': float(compra.total_iva_10 or 0),
                        'total_iva_5': float(compra.total_iva_5 or 0),
                        'total': float(compra.total or 0),
                        'factura_imagen_url': compra.factura_imagen_url,
                        'observaciones': compra.observaciones,
                        'items': items_auditoria
                    },
                    commit=False
                )
            
            db.session.commit()
            flash(f'Compra #{compra.id_compra} registrada correctamente.', 'success')
            return redirect(url_for('compras.listar'))
        except PermissionError:
            db.session.rollback()
            current_app.logger.exception('Sin permisos para guardar factura de compra')
            flash('No hay permisos para guardar la foto de la factura.', 'danger')
        except ValueError:
            db.session.rollback()
            current_app.logger.exception('Factura de compra inválida')
            flash('La foto de la factura no se pudo procesar.', 'warning')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al registrar compra')
            flash('Ocurrió un error al registrar la compra. Intente nuevamente.', 'danger')
    
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    productos_query = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    productos = [{
        'id_producto': p.id_producto,
        'codigo': p.codigo,
        'nombre': p.nombre,
        'precio_compra': float(p.precio_compra or 0)
    } for p in productos_query]
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    
    # Obtener saldo de caja actual
    sesion_activa = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()
    saldo_caja = sesion_activa.calcular_total_efectivo() if sesion_activa else 0
    
    return render_template('compras/form.html', proveedores=proveedores, productos=productos, categorias=categorias, saldo_caja=saldo_caja)


@compras_bp.route('/<int:id>')
@login_required
def detalle(id):
    """Ver detalle de una compra"""
    if not current_user.tiene_permiso('ver_compras'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver detalle de compras.', 'danger')
        return redirect(url_for('compras.listar'))

    compra = Compra.query.get_or_404(id)
    return render_template('compras/detalle.html', compra=compra)


@compras_bp.route('/<int:id>/pagar', methods=['GET', 'POST'])
@login_required
def pagar_deuda(id):
    """Registrar pago de una cuenta por pagar"""
    if not current_user.tiene_permiso('pagar_compra'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para pagar compras.', 'danger')
        return redirect(url_for('compras.listar'))

    compra = Compra.query.get_or_404(id)
    
    # Verificar si tiene cuenta por pagar
    if not compra.cuenta_por_pagar:
        flash('Esta compra no tiene una cuenta por pagar asociada.', 'warning')
        return redirect(url_for('compras.detalle', id=id))
        
    cuenta = compra.cuenta_por_pagar
    
    if cuenta.saldo_pendiente <= 0:
        flash('Esta cuenta ya está totalmente pagada.', 'info')
        return redirect(url_for('compras.detalle', id=id))

    # Obtener saldo de caja actual
    sesion_activa = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta'
    ).first()
    
    if not sesion_activa:
        flash('Debe tener una caja abierta para registrar pagos.', 'warning')
        return redirect(url_for('compras.detalle', id=id))

    if request.method == 'POST':
        monto_a_pagar = request.form.get('monto', 0, type=float)
        id_metodo_pago = request.form.get('id_metodo_pago', type=int)
        referencia = request.form.get('referencia', '').strip()
        observaciones = request.form.get('observaciones', '')
        
        if monto_a_pagar <= 0:
            flash('El monto debe ser mayor a cero.', 'warning')
        elif monto_a_pagar > float(cuenta.saldo_pendiente):
            flash(f'El monto no puede superar el saldo pendiente (₲ {cuenta.saldo_pendiente:,.0f}).', 'warning')
        else:
            saldo_caja = sesion_activa.calcular_total_efectivo()
            metodo = MetodoPago.query.get(id_metodo_pago)
            es_efectivo = metodo and metodo.nombre.lower() == 'efectivo'
            
            if es_efectivo and monto_a_pagar > saldo_caja:
                flash(f'No tiene suficiente efectivo en caja (Disponible: ₲ {saldo_caja:,.0f}).', 'danger')
            else:
                # 1. Registrar egreso de caja si es efectivo
                if es_efectivo:
                    movimiento_caja = MovimientoCaja(
                        id_sesion_caja=sesion_activa.id_sesion,
                        id_usuario=current_user.id_usuario,
                        tipo='egreso',
                        monto=monto_a_pagar,
                        motivo=f'Abono a Compra #{compra.id_compra} (Fac: {compra.numero_factura})',
                        referencia_tipo='compra',
                        referencia_id=compra.id_compra
                    )
                    db.session.add(movimiento_caja)
                
                # 2. Registrar pago
                pago = PagoCompra(
                    id_compra=compra.id_compra,
                    id_metodo_pago=id_metodo_pago,
                    id_sesion_caja=sesion_activa.id_sesion,
                    id_usuario=current_user.id_usuario,
                    monto=monto_a_pagar,
                    referencia=referencia,
                    observaciones=observaciones
                )
                db.session.add(pago)
                
                # 3. Actualizar cuenta por pagar
                cuenta.monto_pagado += Decimal(str(monto_a_pagar))
                cuenta.saldo_pendiente -= Decimal(str(monto_a_pagar))
                
                if cuenta.saldo_pendiente <= 0:
                    cuenta.estado = 'pagada'
                    compra.pagada = True
                else:
                    cuenta.estado = 'pendiente'
                
                # Auditoría
                registrar_auditoria(
                    accion='pagar_compra',
                    modulo='compras',
                    descripcion=f'Pago de ₲ {monto_a_pagar:,.0f} a compra #{compra.id_compra}',
                    referencia_tipo='compra',
                    referencia_id=compra.id_compra,
                    datos_nuevos={
                        'monto': monto_a_pagar,
                        'saldo_anterior': float(cuenta.saldo_pendiente + Decimal(str(monto_a_pagar))),
                        'saldo_nuevo': float(cuenta.saldo_pendiente),
                        'metodo_pago': metodo.nombre if metodo else id_metodo_pago
                    },
                    commit=False
                )
                
                db.session.commit()
                flash('Pago registrado correctamente.', 'success')
                return redirect(url_for('compras.detalle', id=id))

    metodos_pago = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display).all()
    saldo_caja = sesion_activa.calcular_total_efectivo()
    
    return render_template('compras/pagar_deuda.html', 
                           compra=compra, 
                           cuenta=cuenta, 
                           metodos_pago=metodos_pago,
                           saldo_caja=saldo_caja)
