import re
from decimal import Decimal

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import DataError, IntegrityError

from app import db
from app.models import Servicio, ServicioPrecioOpcion
from app.services.agenda_turnos_peluqueria import TURNO_PELUQUERIA_TIPO_LABELS

servicios_bp = Blueprint('servicios', __name__)


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


def _query_servicios_activos():
    return Servicio.query.filter(Servicio.activo.is_(True))


def _render_form(servicio=None, variantes_text=''):
    return render_template(
        'servicios/form.html',
        servicio=servicio,
        variantes_text=variantes_text,
        turno_rapido_tipo_labels=TURNO_PELUQUERIA_TIPO_LABELS,
    )


@servicios_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('ver_inventario'):
        flash('No tienes permisos para ver servicios.', 'danger')
        return redirect(url_for('main.dashboard'))

    buscar = (request.args.get('buscar') or '').strip()
    page = request.args.get('page', 1, type=int)
    query = _query_servicios_activos()
    if buscar:
        like = f'%{buscar}%'
        query = query.filter(
            db.or_(
                Servicio.nombre.ilike(like),
                Servicio.codigo.ilike(like),
                Servicio.categoria.ilike(like),
            )
        )
    servicios = query.order_by(Servicio.categoria.asc(), Servicio.nombre.asc()).paginate(
        page=page,
        per_page=20,
        error_out=False,
    )
    return render_template(
        'servicios/listar.html',
        servicios=servicios,
        buscar=buscar,
        turno_rapido_tipo_labels=TURNO_PELUQUERIA_TIPO_LABELS,
    )


@servicios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not current_user.tiene_permiso('crear_producto'):
        flash('No tienes permisos para crear servicios.', 'danger')
        return redirect(url_for('servicios.listar'))

    if request.method == 'POST':
        servicio = Servicio()
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

    servicio = _query_servicios_activos().filter_by(id_servicio=id_servicio).first_or_404()

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

    servicio = _query_servicios_activos().filter_by(id_servicio=id_servicio).first_or_404()
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

    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])

    like = f'%{q}%'
    servicios = _query_servicios_activos().filter(
        db.or_(
            Servicio.nombre.ilike(like),
            Servicio.codigo.ilike(like),
            Servicio.categoria.ilike(like),
        )
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
    turno_rapido_tipo = (request.form.get('turno_rapido_tipo') or '').strip().lower()
    servicio.turno_rapido_tipo = turno_rapido_tipo or None
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
    if servicio.turno_rapido_tipo and servicio.turno_rapido_tipo not in TURNO_PELUQUERIA_TIPO_LABELS:
        return 'La opción de turno rápido seleccionada no es válida.'
    if servicio.turno_rapido_tipo:
        existente = (
            _query_servicios_activos()
            .filter(Servicio.turno_rapido_tipo == servicio.turno_rapido_tipo)
            .filter(Servicio.id_servicio != getattr(servicio, 'id_servicio', None))
            .first()
        )
        if existente:
            return (
                'La opción de turno rápido '
                f'"{TURNO_PELUQUERIA_TIPO_LABELS[servicio.turno_rapido_tipo]}" '
                f'ya está asignada a "{existente.nombre}".'
            )
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
            {
                'id': int(op.id_opcion_precio),
                'etiqueta': op.etiqueta,
                'precio': float(op.precio or 0),
                'costo': float(op.costo or 0),
            }
            for op in opciones
        ],
        'stock': 0,
        'stock_minimo': 0,
        'es_servicio': True,
        'iva': int(servicio.porcentaje_iva or 0),
    }
