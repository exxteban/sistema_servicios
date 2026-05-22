from datetime import datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.models import Cliente, ClienteServicio, Servicio
from app.models.servicio import CLIENTE_SERVICIO_ESTADOS
from app.services.clientes_servicios import get_cliente_servicios_cobrables, parse_cliente_servicio_ids

clientes_servicios_bp = Blueprint('clientes_servicios', __name__)


def _cliente_or_404(id_cliente: int):
    return Cliente.query.get_or_404(id_cliente)


def _redirect_target(id_cliente: int, fallback_endpoint: str):
    next_url = (request.form.get('next') or request.args.get('next') or '').strip()
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for(fallback_endpoint, id_cliente=id_cliente))


def _parse_decimal(raw, default):
    texto = str(raw or '').strip()
    if not texto:
        return Decimal(default)
    texto = texto.replace('₲', '').replace('.', '').replace(',', '.')
    try:
        return Decimal(texto)
    except Exception:
        return Decimal(default)


def _parse_datetime_local(raw):
    texto = (raw or '').strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _parse_cantidad(raw):
    try:
        cantidad = int(raw or 1)
    except (TypeError, ValueError):
        cantidad = 1
    return max(cantidad, 1)


def _require_ver_clientes():
    if current_user.tiene_permiso('ver_clientes'):
        return None
    flash('No tienes permisos para ver servicios del cliente.', 'danger')
    return redirect(url_for('main.dashboard'))


def _require_editar_cliente(id_cliente: int):
    if current_user.tiene_permiso('editar_cliente'):
        return None
    flash('No tienes permisos para gestionar servicios del cliente.', 'danger')
    return _redirect_target(id_cliente, 'clientes_servicios.detalle')


@clientes_servicios_bp.route('/<int:id_cliente>/servicios')
@login_required
def detalle(id_cliente):
    permiso_error = _require_ver_clientes()
    if permiso_error:
        return permiso_error

    cliente = _cliente_or_404(id_cliente)
    servicios_catalogo = (
        Servicio.query.filter(Servicio.activo.is_(True))
        .order_by(Servicio.categoria.asc(), Servicio.nombre.asc())
        .all()
    )
    asignaciones = (
        ClienteServicio.query.options(
            joinedload(ClienteServicio.servicio),
            joinedload(ClienteServicio.usuario_registro),
            joinedload(ClienteServicio.venta),
        )
        .filter(ClienteServicio.id_cliente == cliente.id_cliente)
        .order_by(ClienteServicio.fecha_solicitud.desc(), ClienteServicio.id_cliente_servicio.desc())
        .all()
    )
    return render_template(
        'clientes/servicios.html',
        cliente=cliente,
        servicios_catalogo=servicios_catalogo,
        asignaciones=asignaciones,
        estados=CLIENTE_SERVICIO_ESTADOS,
    )


@clientes_servicios_bp.route('/<int:id_cliente>/servicios/<int:id_cliente_servicio>/cobrar')
@login_required
def cobrar(id_cliente, id_cliente_servicio):
    permiso_error = _require_ver_clientes()
    if permiso_error:
        return permiso_error
    if not current_user.tiene_permiso('crear_venta'):
        flash('No tienes permisos para cobrar servicios del cliente.', 'danger')
        return _redirect_target(id_cliente, 'clientes_servicios.detalle')

    asignacion = ClienteServicio.query.filter_by(
        id_cliente_servicio=id_cliente_servicio,
        id_cliente=id_cliente,
    ).first_or_404()

    if asignacion.id_venta:
        flash(f'Este servicio ya fue cobrado en la venta #{asignacion.id_venta}.', 'info')
        return redirect(url_for('ventas.detalle', id=asignacion.id_venta))

    if (asignacion.estado or '').strip().lower() == 'cancelado':
        flash('No puedes cobrar un servicio cancelado.', 'warning')
        return _redirect_target(id_cliente, 'clientes_servicios.detalle')

    return redirect(url_for('ventas.pos', cliente_servicio_id=asignacion.id_cliente_servicio))


@clientes_servicios_bp.route('/<int:id_cliente>/servicios/cobrar-seleccionados', methods=['POST'])
@login_required
def cobrar_seleccionados(id_cliente):
    permiso_error = _require_ver_clientes()
    if permiso_error:
        return permiso_error
    if not current_user.tiene_permiso('crear_venta'):
        flash('No tienes permisos para cobrar servicios del cliente.', 'danger')
        return _redirect_target(id_cliente, 'clientes_servicios.detalle')

    cliente = _cliente_or_404(id_cliente)
    cliente_servicio_ids = parse_cliente_servicio_ids(request.form.getlist('cliente_servicio_ids'))
    if not cliente_servicio_ids:
        flash('Selecciona al menos un servicio del cliente para cobrar.', 'warning')
        return _redirect_target(id_cliente, 'clientes_servicios.detalle')

    try:
        asignaciones = get_cliente_servicios_cobrables(cliente_servicio_ids, id_cliente=cliente.id_cliente)
    except ValueError as exc:
        flash(str(exc), 'warning')
        return _redirect_target(id_cliente, 'clientes_servicios.detalle')

    if len(asignaciones) == 1:
        return redirect(url_for('ventas.pos', cliente_servicio_id=asignaciones[0].id_cliente_servicio))

    ids_query = ','.join(str(asignacion.id_cliente_servicio) for asignacion in asignaciones)
    return redirect(url_for('ventas.pos', cliente_servicio_ids=ids_query))


@clientes_servicios_bp.route('/<int:id_cliente>/servicios/asignar', methods=['POST'])
@login_required
def asignar(id_cliente):
    permiso_error = _require_editar_cliente(id_cliente)
    if permiso_error:
        return permiso_error

    cliente = _cliente_or_404(id_cliente)
    try:
        id_servicio = int(request.form.get('id_servicio') or 0)
    except (TypeError, ValueError):
        id_servicio = 0
    servicio = Servicio.query.filter_by(id_servicio=id_servicio, activo=True).first()
    if not servicio:
        flash('Selecciona un servicio válido del catálogo.', 'danger')
        return _redirect_target(cliente.id_cliente, 'clientes_servicios.detalle')

    precio_pactado = _parse_decimal(request.form.get('precio_pactado'), servicio.precio or 0)
    costo_pactado = _parse_decimal(request.form.get('costo_pactado'), servicio.costo or 0)
    estado = (request.form.get('estado') or 'solicitado').strip().lower()
    if estado not in CLIENTE_SERVICIO_ESTADOS:
        estado = 'solicitado'

    asignacion = ClienteServicio(
        id_cliente=cliente.id_cliente,
        id_servicio=servicio.id_servicio,
        cantidad=_parse_cantidad(request.form.get('cantidad')),
        costo_pactado=costo_pactado,
        precio_pactado=precio_pactado,
        estado=estado,
        fecha_programada=_parse_datetime_local(request.form.get('fecha_programada')),
        observaciones=(request.form.get('observaciones') or '').strip() or None,
        id_usuario_registro=current_user.id_usuario,
    )
    db.session.add(asignacion)
    db.session.commit()
    flash(f'Servicio "{servicio.nombre}" asignado a {cliente.nombre}.', 'success')
    return _redirect_target(cliente.id_cliente, 'clientes_servicios.detalle')


@clientes_servicios_bp.route('/<int:id_cliente>/servicios/<int:id_cliente_servicio>/actualizar', methods=['POST'])
@login_required
def actualizar(id_cliente, id_cliente_servicio):
    permiso_error = _require_editar_cliente(id_cliente)
    if permiso_error:
        return permiso_error

    asignacion = ClienteServicio.query.filter_by(
        id_cliente_servicio=id_cliente_servicio,
        id_cliente=id_cliente,
    ).first_or_404()

    asignacion.cantidad = _parse_cantidad(request.form.get('cantidad'))
    asignacion.precio_pactado = _parse_decimal(request.form.get('precio_pactado'), asignacion.precio_pactado or 0)
    asignacion.costo_pactado = _parse_decimal(request.form.get('costo_pactado'), asignacion.costo_pactado or 0)
    asignacion.observaciones = (request.form.get('observaciones') or '').strip() or None
    asignacion.fecha_programada = _parse_datetime_local(request.form.get('fecha_programada'))

    estado = (request.form.get('estado') or asignacion.estado or 'solicitado').strip().lower()
    if estado not in CLIENTE_SERVICIO_ESTADOS:
        estado = asignacion.estado or 'solicitado'
    asignacion.estado = estado
    if estado in ('completado', 'cancelado') and asignacion.fecha_cierre is None:
        asignacion.fecha_cierre = datetime.utcnow()
    elif estado not in ('completado', 'cancelado'):
        asignacion.fecha_cierre = None

    db.session.commit()
    flash('Servicio del cliente actualizado.', 'success')
    return _redirect_target(id_cliente, 'clientes_servicios.detalle')
