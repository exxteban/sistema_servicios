from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models import (
    Categoria,
    Compra,
    Configuracion,
    DetalleCompra,
    MetodoPago,
    MovimientoCaja,
    MovimientoStock,
    PagoCompra,
    Producto,
    Proveedor,
    RecepcionCompraUsado,
    SesionCaja,
    VendedorUsado,
)
from app.utils.auditoria_utils import registrar_auditoria

recepcion_usados_bp = Blueprint('recepcion_usados', __name__)

PROVEEDOR_USADOS_NOMBRE = 'COMPRA DE USADOS'


def _parse_decimal(value) -> Decimal:
    raw = str(value or '').strip()
    if not raw:
        return Decimal('0')
    raw = raw.replace('₲', '').replace('Gs.', '').replace('Gs', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    elif raw.count('.') > 1:
        raw = raw.replace('.', '')
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _parse_date(value: str | None) -> date | None:
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _normalize_document_number(value: str | None) -> str:
    return ''.join(ch for ch in (value or '').upper() if ch.isalnum())


def _normalize_name(value: str | None) -> str:
    return ' '.join((value or '').strip().split())


def _preview_next_form_number() -> int:
    ultimo = db.session.query(func.max(RecepcionCompraUsado.numero_formulario)).scalar() or 0
    return int(ultimo) + 1


def _buscar_metodo_pago(id_metodo_pago: int | None) -> MetodoPago | None:
    if not id_metodo_pago:
        return None
    return MetodoPago.query.filter_by(id_metodo_pago=id_metodo_pago, activo=True).first()


def _es_metodo_efectivo(metodo: MetodoPago | None) -> bool:
    if not metodo:
        return False
    from app.services.caja_metodos import es_metodo_efectivo as _svc_es_efectivo
    return _svc_es_efectivo(metodo)


def _obtener_o_crear_proveedor_usados() -> Proveedor:
    proveedor = Proveedor.query.filter_by(nombre=PROVEEDOR_USADOS_NOMBRE).first()
    if proveedor:
        if not bool(proveedor.activo):
            proveedor.activo = True
        return proveedor

    proveedor = Proveedor(
        nombre=PROVEEDOR_USADOS_NOMBRE,
        ruc=None,
        telefono='',
        email='',
        direccion='Compras de equipos usados a particulares',
        contacto_nombre='',
        contacto_telefono='',
        dias_credito=0,
        notas='Proveedor interno para registrar compras de equipos usados.',
        activo=True,
    )
    db.session.add(proveedor)
    db.session.flush()
    return proveedor


def _build_product_name(data: dict) -> str:
    partes = [
        (data.get('descripcion_producto') or '').strip(),
        (data.get('marca') or '').strip(),
        (data.get('modelo') or '').strip(),
    ]
    nombre = ' - '.join([p for p in partes if p])
    return nombre[:200] if nombre else 'Equipo usado'


def _build_product_description(data: dict, vendedor: VendedorUsado, numero_formulario: str) -> str:
    lineas = [
        f'Formulario de compra de usados N. {numero_formulario}',
        f'Vendedor: {vendedor.nombres_apellidos}',
        f'Documento: {vendedor.tipo_documento} {vendedor.numero_documento}',
        f'Descripcion: {(data.get("descripcion_producto") or "").strip()}',
    ]
    extras = [
        ('Marca', data.get('marca')),
        ('Modelo', data.get('modelo')),
        ('Color', data.get('color')),
        ('Capacidad', data.get('capacidad')),
        ('IMEI/Serie', data.get('imei_serie')),
        ('Accesorios', data.get('accesorios')),
        ('Estado', data.get('estado_equipo')),
        ('Observaciones', data.get('observaciones')),
    ]
    for etiqueta, valor in extras:
        valor = (valor or '').strip()
        if valor:
            lineas.append(f'{etiqueta}: {valor}')
    return '\n'.join(lineas)


def _get_empresa() -> dict:
    return {
        'nombre': Configuracion.obtener('nombre_empresa', 'RYJCELL') or 'RYJCELL',
        'direccion': Configuracion.obtener('direccion_empresa', ''),
        'telefono': Configuracion.obtener('telefono_empresa', ''),
        'ruc': Configuracion.obtener('ruc_empresa', ''),
    }


def _vendedor_payload(vendedor: VendedorUsado) -> dict:
    ultima = vendedor.recepciones.order_by(RecepcionCompraUsado.fecha_formulario.desc()).first()
    return {
        'id_vendedor_usado': vendedor.id_vendedor_usado,
        'nombres_apellidos': vendedor.nombres_apellidos,
        'fecha_nacimiento': vendedor.fecha_nacimiento.isoformat() if vendedor.fecha_nacimiento else '',
        'nacionalidad': vendedor.nacionalidad or '',
        'tipo_documento': vendedor.tipo_documento or '',
        'numero_documento': vendedor.numero_documento or '',
        'estado_civil': vendedor.estado_civil or '',
        'domicilio': vendedor.domicilio or '',
        'referencia_domicilio': vendedor.referencia_domicilio or '',
        'barrio': vendedor.barrio or '',
        'ciudad': vendedor.ciudad or '',
        'departamento': vendedor.departamento or '',
        'telefono': vendedor.telefono or '',
        'veces_vendio': vendedor.total_ventas_usados,
        'ultima_recepcion': ultima.numero_formulario_display if ultima else None,
    }


@recepcion_usados_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('ver_recepcion_usados'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver recepciones de usados.', 'danger')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()

    query = RecepcionCompraUsado.query.join(VendedorUsado).outerjoin(
        Producto,
        RecepcionCompraUsado.id_producto == Producto.id_producto,
    )
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                RecepcionCompraUsado.numero_formulario.cast(db.String).ilike(like),
                RecepcionCompraUsado.descripcion_producto.ilike(like),
                VendedorUsado.nombres_apellidos.ilike(like),
                VendedorUsado.numero_documento.ilike(like),
                Producto.codigo.ilike(like),
            )
        )

    recepciones = query.order_by(
        RecepcionCompraUsado.fecha_formulario.desc(),
        RecepcionCompraUsado.id_recepcion_compra_usado.desc(),
    ).paginate(page=page, per_page=12, error_out=False)

    return render_template('recepcion_usados/listar.html', recepciones=recepciones, q=q)


@recepcion_usados_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    if not current_user.tiene_permiso('crear_recepcion_usados'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para registrar compras de usados.', 'danger')
        return redirect(url_for('recepcion_usados.listar'))

    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre.asc()).all()
    metodos_pago = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display.asc()).all()
    sesion_activa = SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()
    saldo_caja = sesion_activa.calcular_total_efectivo() if sesion_activa else 0

    if request.method == 'POST':
        fecha_formulario = _parse_date(request.form.get('fecha_formulario')) or date.today()
        fecha_nacimiento = _parse_date(request.form.get('fecha_nacimiento'))
        monto_compra = _parse_decimal(request.form.get('monto_compra'))
        tipo_documento = (request.form.get('tipo_documento') or '').strip()
        numero_documento = (request.form.get('numero_documento') or '').strip()
        documento_normalizado = _normalize_document_number(numero_documento)
        id_categoria = request.form.get('id_categoria', type=int)
        id_metodo_pago = request.form.get('id_metodo_pago', type=int)
        metodo_pago = _buscar_metodo_pago(id_metodo_pago)

        data = {
            'nombres_apellidos': _normalize_name(request.form.get('nombres_apellidos')),
            'fecha_nacimiento': fecha_nacimiento,
            'nacionalidad': _normalize_name(request.form.get('nacionalidad')),
            'tipo_documento': tipo_documento,
            'numero_documento': numero_documento,
            'estado_civil': _normalize_name(request.form.get('estado_civil')),
            'domicilio': (request.form.get('domicilio') or '').strip(),
            'referencia_domicilio': (request.form.get('referencia_domicilio') or '').strip(),
            'barrio': _normalize_name(request.form.get('barrio')),
            'ciudad': _normalize_name(request.form.get('ciudad')),
            'departamento': _normalize_name(request.form.get('departamento')),
            'telefono': (request.form.get('telefono') or '').strip(),
            'descripcion_producto': (request.form.get('descripcion_producto') or '').strip(),
            'marca': _normalize_name(request.form.get('marca')),
            'modelo': _normalize_name(request.form.get('modelo')),
            'color': _normalize_name(request.form.get('color')),
            'capacidad': _normalize_name(request.form.get('capacidad')),
            'imei_serie': (request.form.get('imei_serie') or '').strip(),
            'accesorios': (request.form.get('accesorios') or '').strip(),
            'estado_equipo': (request.form.get('estado_equipo') or '').strip(),
            'referencia_pago': (request.form.get('referencia_pago') or '').strip(),
            'observaciones': (request.form.get('observaciones') or '').strip(),
            'lugar_firma': _normalize_name(request.form.get('lugar_firma')),
            'domicilio_especial_vendedor': (request.form.get('domicilio_especial_vendedor') or '').strip(),
        }

        errores = []
        campos_obligatorios = {
            'nombres_apellidos': 'Los nombres y apellidos del vendedor son obligatorios.',
            'nacionalidad': 'La nacionalidad es obligatoria.',
            'tipo_documento': 'Debe indicar el tipo de documento.',
            'numero_documento': 'Debe indicar el número de documento.',
            'estado_civil': 'El estado civil es obligatorio.',
            'domicilio': 'El domicilio es obligatorio.',
            'barrio': 'El barrio es obligatorio.',
            'ciudad': 'La ciudad es obligatoria.',
            'departamento': 'El departamento es obligatorio.',
            'telefono': 'El celular del vendedor es obligatorio.',
            'descripcion_producto': 'Debe describir el equipo comprado.',
        }
        for campo, mensaje in campos_obligatorios.items():
            if not data.get(campo):
                errores.append(mensaje)

        if not fecha_nacimiento:
            errores.append('La fecha de nacimiento es obligatoria.')
        if not documento_normalizado:
            errores.append('El número de documento no es válido.')
        if monto_compra <= 0:
            errores.append('El monto de compra debe ser mayor a cero.')
        if not id_categoria or not Categoria.query.filter_by(id_categoria=id_categoria, activo=True).first():
            errores.append('Debe seleccionar una categoría válida para inventario.')
        if not metodo_pago:
            errores.append('Debe seleccionar un método de pago válido.')
        elif getattr(metodo_pago, 'requiere_referencia', False) and not data['referencia_pago']:
            errores.append(f'El método de pago {metodo_pago.nombre} requiere referencia.')

        es_efectivo = _es_metodo_efectivo(metodo_pago)
        if es_efectivo and not sesion_activa:
            errores.append('Debe tener una caja abierta para registrar pagos en efectivo.')
        if es_efectivo and sesion_activa and monto_compra > Decimal(str(saldo_caja or 0)):
            errores.append(f'No hay suficiente efectivo en caja. Disponible: ₲ {saldo_caja:,.0f}.')

        if errores:
            for error in errores:
                flash(error, 'warning')
            return render_template(
                'recepcion_usados/form.html',
                categorias=categorias,
                metodos_pago=metodos_pago,
                saldo_caja=saldo_caja,
                numero_preview=_preview_next_form_number(),
            )

        try:
            with db.session.begin_nested():
                vendedor = VendedorUsado.query.filter_by(
                    tipo_documento=tipo_documento,
                    numero_documento_normalizado=documento_normalizado,
                ).first()

                if vendedor is None:
                    vendedor = VendedorUsado(
                        nombres_apellidos=data['nombres_apellidos'],
                        fecha_nacimiento=fecha_nacimiento,
                        nacionalidad=data['nacionalidad'],
                        tipo_documento=tipo_documento,
                        numero_documento=numero_documento,
                        numero_documento_normalizado=documento_normalizado,
                        estado_civil=data['estado_civil'],
                        domicilio=data['domicilio'],
                        referencia_domicilio=data['referencia_domicilio'],
                        barrio=data['barrio'],
                        ciudad=data['ciudad'],
                        departamento=data['departamento'],
                        telefono=data['telefono'],
                        activo=True,
                    )
                    db.session.add(vendedor)
                    db.session.flush()
                else:
                    vendedor.nombres_apellidos = data['nombres_apellidos']
                    vendedor.fecha_nacimiento = fecha_nacimiento
                    vendedor.nacionalidad = data['nacionalidad']
                    vendedor.numero_documento = numero_documento
                    vendedor.estado_civil = data['estado_civil']
                    vendedor.domicilio = data['domicilio']
                    vendedor.referencia_domicilio = data['referencia_domicilio']
                    vendedor.barrio = data['barrio']
                    vendedor.ciudad = data['ciudad']
                    vendedor.departamento = data['departamento']
                    vendedor.telefono = data['telefono']
                    vendedor.activo = True

                recepcion = RecepcionCompraUsado(
                    fecha_formulario=fecha_formulario,
                    id_vendedor_usado=vendedor.id_vendedor_usado,
                    id_usuario=current_user.id_usuario,
                    id_producto=None,
                    id_compra=None,
                    descripcion_producto=data['descripcion_producto'],
                    marca=data['marca'],
                    modelo=data['modelo'],
                    color=data['color'],
                    capacidad=data['capacidad'],
                    imei_serie=data['imei_serie'],
                    accesorios=data['accesorios'],
                    estado_equipo=data['estado_equipo'],
                    monto_compra=monto_compra,
                    metodo_pago=metodo_pago.nombre,
                    referencia_pago=data['referencia_pago'],
                    observaciones=data['observaciones'],
                    lugar_firma=data['lugar_firma'] or data['ciudad'],
                    domicilio_especial_vendedor=data['domicilio_especial_vendedor'] or data['domicilio'],
                    vendedor_nombres_apellidos=data['nombres_apellidos'],
                    vendedor_fecha_nacimiento=fecha_nacimiento,
                    vendedor_nacionalidad=data['nacionalidad'],
                    vendedor_tipo_documento=tipo_documento,
                    vendedor_numero_documento=numero_documento,
                    vendedor_estado_civil=data['estado_civil'],
                    vendedor_domicilio=data['domicilio'],
                    vendedor_referencia_domicilio=data['referencia_domicilio'],
                    vendedor_barrio=data['barrio'],
                    vendedor_ciudad=data['ciudad'],
                    vendedor_departamento=data['departamento'],
                    vendedor_telefono=data['telefono'],
                )
                db.session.add(recepcion)
                db.session.flush()
                recepcion.numero_formulario = recepcion.id_recepcion_compra_usado

                numero_referencia = f'US-{recepcion.numero_formulario_display}'
                proveedor = _obtener_o_crear_proveedor_usados()

                producto = Producto(
                    codigo=numero_referencia,
                    nombre=_build_product_name(data),
                    descripcion=_build_product_description(data, vendedor, recepcion.numero_formulario_display),
                    id_categoria=id_categoria,
                    id_proveedor_principal=proveedor.id_proveedor,
                    marca=data['marca'] or None,
                    modelo=data['modelo'] or None,
                    color=data['color'] or None,
                    capacidad=data['capacidad'] or None,
                    precio_compra=monto_compra,
                    precio_venta=monto_compra,
                    precio_mayorista=monto_compra,
                    porcentaje_iva=10,
                    stock_actual=0,
                    stock_minimo=0,
                    activo=True,
                    id_usuario_modificacion=current_user.id_usuario,
                )
                db.session.add(producto)
                db.session.flush()

                compra = Compra(
                    numero_factura=numero_referencia,
                    id_proveedor=proveedor.id_proveedor,
                    id_usuario=current_user.id_usuario,
                    fecha_compra=fecha_formulario,
                    subtotal=monto_compra,
                    total_iva_10=Decimal('0'),
                    total_iva_5=Decimal('0'),
                    total=monto_compra,
                    estado='completada',
                    tipo_compra='contado',
                    pagada=True,
                    observaciones=f'Compra de usado {numero_referencia} - {vendedor.nombres_apellidos}',
                )
                db.session.add(compra)
                db.session.flush()

                detalle = DetalleCompra(
                    id_compra=compra.id_compra,
                    id_producto=producto.id_producto,
                    cantidad=1,
                    precio_unitario=monto_compra,
                    porcentaje_iva=10,
                    subtotal=monto_compra,
                )
                db.session.add(detalle)

                producto.stock_actual = 1
                movimiento_stock = MovimientoStock(
                    id_producto=producto.id_producto,
                    id_usuario=current_user.id_usuario,
                    tipo_movimiento='entrada',
                    cantidad=1,
                    stock_anterior=0,
                    stock_nuevo=1,
                    referencia_tipo='recepcion_compra_usado',
                    referencia_id=recepcion.id_recepcion_compra_usado,
                )
                db.session.add(movimiento_stock)

                movimiento_caja = None
                if es_efectivo and sesion_activa:
                    movimiento_caja = MovimientoCaja(
                        id_sesion_caja=sesion_activa.id_sesion,
                        id_usuario=current_user.id_usuario,
                        tipo='egreso',
                        monto=monto_compra,
                        motivo=f'Compra usado {numero_referencia}',
                        referencia_tipo='recepcion_compra_usado',
                        referencia_id=recepcion.id_recepcion_compra_usado,
                    )
                    db.session.add(movimiento_caja)
                    db.session.flush()

                pago = PagoCompra(
                    id_compra=compra.id_compra,
                    id_metodo_pago=metodo_pago.id_metodo_pago,
                    id_sesion_caja=sesion_activa.id_sesion if es_efectivo and sesion_activa else None,
                    id_usuario=current_user.id_usuario,
                    monto=monto_compra,
                    referencia=data['referencia_pago'] or numero_referencia,
                    observaciones=f'Pago de compra usado {numero_referencia}',
                )
                db.session.add(pago)

                recepcion.id_producto = producto.id_producto
                recepcion.id_compra = compra.id_compra
                recepcion.id_movimiento_caja = movimiento_caja.id_movimiento_caja if movimiento_caja else None

                registrar_auditoria(
                    accion='crear_recepcion_usado',
                    modulo='recepcion_usados',
                    descripcion=f'Registró recepción de usado {numero_referencia}',
                    referencia_tipo='recepcion_compra_usado',
                    referencia_id=recepcion.id_recepcion_compra_usado,
                    datos_nuevos={
                        'numero_formulario': recepcion.numero_formulario,
                        'vendedor': vendedor.nombres_apellidos,
                        'documento': f'{tipo_documento} {numero_documento}',
                        'producto_codigo': producto.codigo,
                        'producto_nombre': producto.nombre,
                        'monto_compra': float(monto_compra),
                        'metodo_pago': metodo_pago.nombre,
                        'id_compra': compra.id_compra,
                    },
                    commit=False,
                )

            db.session.commit()
            flash(f'Formulario Nº {recepcion.numero_formulario_display} registrado correctamente.', 'success')
            return redirect(url_for('recepcion_usados.detalle', id_recepcion=recepcion.id_recepcion_compra_usado))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al registrar recepción de compra de usado')
            flash('Ocurrió un error al registrar la compra de usado. Intente nuevamente.', 'danger')

    return render_template(
        'recepcion_usados/form.html',
        categorias=categorias,
        metodos_pago=metodos_pago,
        saldo_caja=saldo_caja,
        numero_preview=_preview_next_form_number(),
    )


@recepcion_usados_bp.route('/<int:id_recepcion>')
@login_required
def detalle(id_recepcion):
    if not current_user.tiene_permiso('ver_recepcion_usados'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver recepciones de usados.', 'danger')
        return redirect(url_for('main.dashboard'))

    recepcion = RecepcionCompraUsado.query.get_or_404(id_recepcion)
    return render_template('recepcion_usados/detalle.html', recepcion=recepcion)


@recepcion_usados_bp.route('/<int:id_recepcion>/imprimir')
@login_required
def imprimir(id_recepcion):
    if not current_user.tiene_permiso('ver_recepcion_usados'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para imprimir recepciones de usados.', 'danger')
        return redirect(url_for('main.dashboard'))

    recepcion = RecepcionCompraUsado.query.get_or_404(id_recepcion)
    recepcion.cantidad_impresiones = int(recepcion.cantidad_impresiones or 0) + 1
    recepcion.fecha_ultima_impresion = datetime.utcnow()
    db.session.commit()

    return render_template('recepcion_usados/imprimir.html', recepcion=recepcion, empresa=_get_empresa())


@recepcion_usados_bp.route('/api/vendedor')
@login_required
def api_vendedor():
    if not (current_user.tiene_permiso('ver_recepcion_usados') or current_user.tiene_permiso('crear_recepcion_usados')):
        modo_demo = bool(getattr(current_user, 'modo_demo', False))
        return jsonify({'success': False, 'mensaje': 'Sin permisos', 'modo_demo': modo_demo}), 403

    tipo_documento = (request.args.get('tipo_documento') or '').strip()
    numero_documento = _normalize_document_number(request.args.get('numero_documento'))
    if not tipo_documento or not numero_documento:
        return jsonify({'success': False, 'mensaje': 'Documento incompleto'}), 400

    vendedor = VendedorUsado.query.filter_by(
        tipo_documento=tipo_documento,
        numero_documento_normalizado=numero_documento,
    ).first()
    if not vendedor:
        return jsonify({'success': True, 'found': False})

    return jsonify({'success': True, 'found': True, 'vendedor': _vendedor_payload(vendedor)})
