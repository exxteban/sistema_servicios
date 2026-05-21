import re
from decimal import Decimal

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import DataError, IntegrityError

from app import db
from app.models import Cliente, Servicio, ServicioPrecioOpcion

servicios_bp = Blueprint('servicios', __name__)


def _clientes_disponibles():
    if not current_user.es_admin():
        return []
    return Cliente.query.filter_by(activo=True).order_by(Cliente.nombre.asc(), Cliente.id_cliente.asc()).all()


def _id_cliente_actual():
    id_cliente = getattr(current_user, 'id_cliente', None)
    if id_cliente:
        return int(id_cliente)
    if current_user.es_admin():
        raw = request.form.get('id_cliente') if request.method == 'POST' else request.args.get('id_cliente')
        try:
            if raw:
                return int(raw)
        except (TypeError, ValueError):
            return None
    if current_user.es_admin():
        clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.id_cliente.asc()).limit(2).all()
        if len(clientes) == 1:
            return int(clientes[0].id_cliente)
    return None


def _redirect_sin_cliente():
    flash('No se pudo determinar el cliente para cargar servicios.', 'danger')
    return redirect(url_for('main.dashboard'))


def _decimal_form(name, default='0'):
    raw = (request.form.get(name, default) or default).strip()
    raw = raw.replace('₲', '').replace('.', '').replace(',', '.')
    try:
        return Decimal(raw)
    except Exception:
        return Decimal(default)


def _int_form(name, default=0):
    try:
        return int(request.form.get(name, default) or default)
    except Exception:
        return default


def _decimal_to_str(value) -> str:
    try:
        s = format(Decimal(str(value or 0)), 'f')
    except Exception:
        return str(value or '')
    return s.rstrip('0').rstrip('.') if '.' in s else s


def _parsear_variantes(raw: str):
    variantes = []
    for line in (raw or '').splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [p.strip() for p in re.split(r'[|;]', text) if p.strip()]
        if len(parts) < 3:
            parts = [p.strip() for p in text.split(',') if p.strip()]
        if len(parts) < 3:
            continue
        etiqueta = parts[0][:100]
        try:
            costo = Decimal(parts[1].replace('₲', '').replace('.', '').replace(',', '.'))
            precio = Decimal(parts[2].replace('₲', '').replace('.', '').replace(',', '.'))
        except Exception:
            continue
        if precio <= 0 or costo < 0:
            continue
        variantes.append({'etiqueta': etiqueta, 'costo': costo, 'precio': precio})
    return variantes


def _variantes_text(servicio):
    opciones = (
        servicio.opciones.filter_by(activo=True)
        .order_by(ServicioPrecioOpcion.orden.asc(), ServicioPrecioOpcion.id_opcion_precio.asc())
        .all()
    )
    return '\n'.join(
        f'{op.etiqueta} | {_decimal_to_str(op.costo)} | {_decimal_to_str(op.precio)}'
        for op in opciones
    )


def _actualizar_variantes(servicio, raw):
    for opcion in servicio.opciones.all():
        db.session.delete(opcion)
    for idx, item in enumerate(_parsear_variantes(raw)):
        db.session.add(ServicioPrecioOpcion(
            id_servicio=servicio.id_servicio,
            etiqueta=item['etiqueta'],
            costo=item['costo'],
            precio=item['precio'],
            orden=idx,
            activo=True,
        ))


def _query_servicios_cliente(id_cliente):
    return Servicio.query.filter(Servicio.id_cliente == id_cliente, Servicio.activo.is_(True))


def _query_servicios_visibles(id_cliente):
    if id_cliente:
        return _query_servicios_cliente(id_cliente)
    if current_user.es_admin():
        return Servicio.query.filter(Servicio.activo.is_(True))
    return Servicio.query.filter(db.false())


def _render_form(servicio=None, variantes_text=''):
    return render_template(
        'servicios/form.html',
        servicio=servicio,
        variantes_text=variantes_text,
        clientes=_clientes_disponibles(),
        cliente_id=_id_cliente_actual(),
    )


@servicios_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('ver_inventario'):
        flash('No tienes permisos para ver servicios.', 'danger')
        return redirect(url_for('main.dashboard'))
    id_cliente = _id_cliente_actual()

    buscar = (request.args.get('buscar') or '').strip()
    page = request.args.get('page', 1, type=int)
    query = _query_servicios_visibles(id_cliente)
    if buscar:
        like = f'%{buscar}%'
        query = query.filter(db.or_(Servicio.nombre.ilike(like), Servicio.codigo.ilike(like), Servicio.categoria.ilike(like)))
    servicios = query.order_by(Servicio.categoria.asc(), Servicio.nombre.asc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('servicios/listar.html', servicios=servicios, buscar=buscar, clientes=_clientes_disponibles(), cliente_id=id_cliente)


@servicios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not current_user.tiene_permiso('crear_producto'):
        flash('No tienes permisos para crear servicios.', 'danger')
        return redirect(url_for('servicios.listar'))
    id_cliente = _id_cliente_actual()

    if request.method == 'POST':
        if not id_cliente:
            flash('Selecciona el cliente al que pertenece el servicio.', 'danger')
            return _render_form(None, request.form.get('variantes', ''))
        servicio = Servicio(id_cliente=id_cliente)
        error = _guardar_desde_form(servicio)
        if error:
            flash(error, 'danger')
            return _render_form(None, request.form.get('variantes', ''))
        try:
            db.session.add(servicio)
            db.session.flush()
            _actualizar_variantes(servicio, request.form.get('variantes', ''))
            db.session.commit()
            flash(f'Servicio "{servicio.nombre}" creado correctamente.', 'success')
            return redirect(url_for('servicios.listar'))
        except (IntegrityError, DataError):
            db.session.rollback()
            flash('No se pudo guardar el servicio. Verifica el código y los importes.', 'danger')
    return _render_form(None, '')


@servicios_bp.route('/<int:id_servicio>/editar', methods=['GET', 'POST'])
@login_required
def editar(id_servicio):
    if not current_user.tiene_permiso('editar_producto'):
        flash('No tienes permisos para editar servicios.', 'danger')
        return redirect(url_for('servicios.listar'))
    id_cliente = _id_cliente_actual()
    servicio = _query_servicios_visibles(id_cliente).filter_by(id_servicio=id_servicio).first_or_404()

    if request.method == 'POST':
        error = _guardar_desde_form(servicio)
        if error:
            flash(error, 'danger')
            return _render_form(servicio, request.form.get('variantes', ''))
        try:
            _actualizar_variantes(servicio, request.form.get('variantes', ''))
            db.session.commit()
            flash(f'Servicio "{servicio.nombre}" actualizado.', 'success')
            return redirect(url_for('servicios.listar'))
        except (IntegrityError, DataError):
            db.session.rollback()
            flash('No se pudo actualizar el servicio. Verifica el código y los importes.', 'danger')
    return _render_form(servicio, _variantes_text(servicio))


@servicios_bp.route('/<int:id_servicio>/eliminar', methods=['POST'])
@login_required
def eliminar(id_servicio):
    if not current_user.tiene_permiso('eliminar_producto'):
        flash('No tienes permisos para eliminar servicios.', 'danger')
        return redirect(url_for('servicios.listar'))
    id_cliente = _id_cliente_actual()
    servicio = _query_servicios_visibles(id_cliente).filter_by(id_servicio=id_servicio).first_or_404()
    servicio.activo = False
    servicio.publicado_tienda = False
    db.session.commit()
    flash(f'Servicio "{servicio.nombre}" eliminado.', 'success')
    return redirect(url_for('servicios.listar'))


@servicios_bp.route('/buscar')
@login_required
def buscar_api():
    if not (current_user.tiene_permiso('crear_venta') or current_user.tiene_permiso('ver_inventario')):
        return jsonify({'error': 'Sin permisos'}), 403
    id_cliente = _id_cliente_actual()
    if not id_cliente:
        return jsonify([])
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    servicios = _query_servicios_cliente(id_cliente).filter(
        db.or_(Servicio.nombre.ilike(like), Servicio.codigo.ilike(like), Servicio.categoria.ilike(like))
    ).order_by(Servicio.nombre.asc()).limit(10).all()
    return jsonify([_servicio_pos_dict(servicio) for servicio in servicios])


def _guardar_desde_form(servicio):
    servicio.codigo = (request.form.get('codigo') or '').strip() or None
    servicio.nombre = (request.form.get('nombre') or '').strip()
    servicio.categoria = (request.form.get('categoria') or '').strip() or None
    servicio.descripcion = (request.form.get('descripcion') or '').strip() or None
    servicio.costo = _decimal_form('costo')
    servicio.precio = _decimal_form('precio')
    servicio.duracion_minutos = max(0, _int_form('duracion_minutos', 30))
    servicio.porcentaje_iva = _int_form('porcentaje_iva', 10)
    servicio.publicado_tienda = bool(request.form.get('publicado_tienda'))
    servicio.descripcion_tienda = (request.form.get('descripcion_tienda') or '').strip() or None
    servicio.id_usuario_modificacion = current_user.id_usuario
    if not servicio.nombre:
        return 'El nombre del servicio es obligatorio.'
    if servicio.precio <= 0:
        return 'El precio al cliente debe ser mayor a 0.'
    if servicio.costo < 0:
        return 'El costo interno no puede ser negativo.'
    if servicio.porcentaje_iva not in (0, 5, 10):
        servicio.porcentaje_iva = 10
    return None


def _servicio_pos_dict(servicio):
    opciones = servicio.opciones.filter_by(activo=True).order_by(ServicioPrecioOpcion.orden.asc()).all()
    return {
        'id': int(servicio.id_servicio),
        'tipo': 'servicio',
        'codigo': servicio.codigo or f'SRV-{servicio.id_servicio}',
        'nombre': servicio.nombre,
        'precio': float(servicio.precio or 0),
        'costo': float(servicio.costo or 0),
        'precios_opciones': [
            {'id': int(op.id_opcion_precio), 'etiqueta': op.etiqueta, 'precio': float(op.precio or 0), 'costo': float(op.costo or 0)}
            for op in opciones
        ],
        'stock': 0,
        'stock_minimo': 0,
        'es_servicio': True,
        'iva': int(servicio.porcentaje_iva or 0),
    }
