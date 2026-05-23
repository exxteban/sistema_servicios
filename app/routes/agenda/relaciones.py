from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import joinedload, load_only

from app import db
from app.models import Cliente, ClienteServicio, CrmContacto, Reparacion, Servicio, ServicioPrecioOpcion, Usuario, Venta
from app.routes.agenda import agenda_bp
from app.routes.agenda.actividades import _parse_optional_int, _parse_positive_int, _puede_ver_todo
from app.routes.agenda.visibilidad import usuarios_agenda_visibles_para
from app.utils.helpers import local_strftime


def _serializar_cliente(cliente: Cliente | None):
    if not cliente:
        return None
    return {
        'id_cliente': cliente.id_cliente,
        'nombre': cliente.nombre or '',
        'ruc_ci': cliente.ruc_ci or '',
        'telefono': cliente.telefono or '',
        'email': cliente.email or '',
    }


def _serializar_venta(venta: Venta | None):
    if not venta:
        return None
    return {
        'id_venta': venta.id_venta,
        'id_cliente': venta.id_cliente,
        'numero_comprobante': venta.numero_comprobante or '',
        'fecha_venta': local_strftime(venta.fecha_venta, '%d/%m/%Y %H:%M'),
        'total': float(venta.total or 0),
        'estado': venta.estado or '',
        'cliente': _serializar_cliente(getattr(venta, 'cliente', None)),
    }


def _serializar_reparacion(reparacion: Reparacion | None):
    if not reparacion:
        return None
    equipo = ' '.join(filter(None, [reparacion.tipo_equipo, reparacion.marca_modelo])).strip()
    return {
        'id_reparacion': reparacion.id_reparacion,
        'cliente_id': reparacion.cliente_id,
        'equipo': equipo,
        'tipo_equipo': reparacion.tipo_equipo or '',
        'marca_modelo': reparacion.marca_modelo or '',
        'estado': reparacion.estado or '',
        'fecha_ingreso': local_strftime(reparacion.fecha_ingreso, '%d/%m/%Y %H:%M'),
        'cliente': _serializar_cliente(getattr(reparacion, 'cliente', None)),
    }


def _serializar_servicio(servicio: Servicio | None):
    if not servicio:
        return None
    opciones = (
        servicio.opciones.filter_by(activo=True)
        .order_by(ServicioPrecioOpcion.orden.asc(), ServicioPrecioOpcion.id_opcion_precio.asc())
        .all()
    )
    return {
        'id_servicio': servicio.id_servicio,
        'nombre': servicio.nombre or '',
        'categoria': servicio.categoria or '',
        'precio': float(servicio.precio or 0),
        'costo': float(servicio.costo or 0),
        'duracion_minutos': int(servicio.duracion_minutos or 30),
        'opciones': [
            {
                'id_opcion_precio': opcion.id_opcion_precio,
                'etiqueta': opcion.etiqueta or '',
                'precio': float(opcion.precio or 0),
                'costo': float(opcion.costo or 0),
            }
            for opcion in opciones
        ],
    }


def _serializar_cliente_servicio(asignacion: ClienteServicio | None):
    if not asignacion:
        return None
    return {
        'id_cliente_servicio': asignacion.id_cliente_servicio,
        'id_cliente': asignacion.id_cliente,
        'id_servicio': asignacion.id_servicio,
        'cantidad': int(asignacion.cantidad or 1),
        'estado': asignacion.estado or '',
        'precio_pactado': float(asignacion.precio_pactado or 0),
        'costo_pactado': float(asignacion.costo_pactado or 0),
        'fecha_programada': local_strftime(asignacion.fecha_programada, '%Y-%m-%dT%H:%M') if asignacion.fecha_programada else '',
        'observaciones': asignacion.observaciones or '',
        'cliente': _serializar_cliente(getattr(asignacion, 'cliente', None)),
        'servicio': _serializar_servicio(getattr(asignacion, 'servicio', None)),
    }


def _obtener_relaciones_iniciales(data=None, actividad=None):
    cliente_id = _parse_optional_int(data.get('cliente_id') if data else None)
    cliente_servicio_id = _parse_optional_int(data.get('cliente_servicio_id') if data else None)
    servicio_id = _parse_optional_int(data.get('servicio_catalogo_id') if data else None)
    reparacion_id = _parse_optional_int(data.get('reparacion_id') if data else None)
    venta_id = _parse_optional_int(data.get('venta_id') if data else None)

    if cliente_id is None and actividad:
        cliente_id = actividad.cliente_id
    if cliente_servicio_id is None and actividad:
        cliente_servicio_id = actividad.cliente_servicio_id
    if reparacion_id is None and actividad:
        reparacion_id = actividad.reparacion_id
    if venta_id is None and actividad:
        venta_id = actividad.venta_id

    cliente = cliente_servicio = servicio = reparacion = venta = None
    if cliente_servicio_id:
        cliente_servicio = (
            ClienteServicio.query.options(
                joinedload(ClienteServicio.cliente).load_only(
                    Cliente.id_cliente,
                    Cliente.nombre,
                    Cliente.ruc_ci,
                    Cliente.telefono,
                    Cliente.email,
                ),
                joinedload(ClienteServicio.servicio),
            )
            .filter(ClienteServicio.id_cliente_servicio == cliente_servicio_id)
            .first()
        )
        if cliente_servicio:
            cliente_id = cliente_id or cliente_servicio.id_cliente
            servicio_id = servicio_id or cliente_servicio.id_servicio
    if cliente_id:
        cliente = (
            Cliente.query.options(
                load_only(Cliente.id_cliente, Cliente.nombre, Cliente.ruc_ci, Cliente.telefono, Cliente.email)
            )
            .filter(Cliente.id_cliente == cliente_id)
            .first()
        )
    if servicio_id:
        servicio = Servicio.query.filter_by(id_servicio=servicio_id, activo=True).first()
    if reparacion_id:
        reparacion = (
            Reparacion.query.options(
                joinedload(Reparacion.cliente).load_only(
                    Cliente.id_cliente,
                    Cliente.nombre,
                    Cliente.ruc_ci,
                    Cliente.telefono,
                    Cliente.email,
                )
            )
            .filter(Reparacion.id_reparacion == reparacion_id)
            .first()
        )
    if venta_id:
        venta = (
            Venta.query.options(
                joinedload(Venta.cliente).load_only(
                    Cliente.id_cliente,
                    Cliente.nombre,
                    Cliente.ruc_ci,
                    Cliente.telefono,
                    Cliente.email,
                )
            )
            .filter(Venta.id_venta == venta_id)
            .first()
        )
    return (
        _serializar_cliente(cliente),
        _serializar_cliente_servicio(cliente_servicio),
        _serializar_servicio(servicio),
        _serializar_reparacion(reparacion),
        _serializar_venta(venta),
    )


def _obtener_opciones_formulario():
    usuarios = usuarios_agenda_visibles_para(current_user, _puede_ver_todo())
    contactos = CrmContacto.query.order_by(CrmContacto.id.desc()).limit(120).all()
    return usuarios, contactos


def _servicio_catalogo_desde_form(data):
    servicio_id = _parse_positive_int(data.get('servicio_catalogo_id'))
    if not servicio_id:
        return None
    return Servicio.query.filter_by(id_servicio=servicio_id, activo=True).first()


def _opcion_precio_desde_form(servicio, data):
    opcion_id = _parse_positive_int(data.get('servicio_precio_opcion_id'))
    if not servicio or not opcion_id:
        return None
    return ServicioPrecioOpcion.query.filter_by(
        id_opcion_precio=opcion_id,
        id_servicio=servicio.id_servicio,
        activo=True,
    ).first()


def _resolver_cliente_servicio_agenda(data, fecha_inicio):
    cliente_servicio_id = _parse_positive_int(data.get('cliente_servicio_id'))
    if cliente_servicio_id:
        asignacion = db.session.get(ClienteServicio, cliente_servicio_id)
        if asignacion:
            asignacion.fecha_programada = fecha_inicio
            if (asignacion.estado or '').strip().lower() in {'solicitado', 'presupuestado'}:
                asignacion.estado = 'agendado'
        return asignacion

    cliente_id = _parse_positive_int(data.get('cliente_id'))
    servicio = _servicio_catalogo_desde_form(data)
    if not cliente_id or not servicio:
        return None

    opcion = _opcion_precio_desde_form(servicio, data)
    costo = opcion.costo if opcion is not None else (servicio.costo or 0)
    precio = opcion.precio if opcion is not None else (servicio.precio or 0)
    observaciones = (data.get('observaciones') or '').strip()
    if opcion is not None:
        tipo_label = (opcion.etiqueta or '').strip()
        observaciones = f'Tipo: {tipo_label}' + (f'\n{observaciones}' if observaciones else '')

    asignacion = ClienteServicio(
        id_cliente=cliente_id,
        id_servicio=servicio.id_servicio,
        cantidad=1,
        costo_pactado=costo,
        precio_pactado=precio,
        estado='agendado',
        fecha_programada=fecha_inicio,
        observaciones=observaciones or None,
        id_usuario_registro=current_user.id_usuario,
    )
    db.session.add(asignacion)
    db.session.flush()
    return asignacion


@agenda_bp.route('/api/clientes/buscar', methods=['GET'])
@login_required
def buscar_clientes_relacion():
    q = (request.args.get('q') or '').strip()
    query = Cliente.query.filter(Cliente.activo.is_(True))
    if q:
        like = f'%{q}%'
        query = query.filter(or_(Cliente.nombre.ilike(like), Cliente.ruc_ci.ilike(like), Cliente.telefono.ilike(like)))
    clientes = query.order_by(Cliente.nombre.asc()).limit(12).all()
    return jsonify({'items': [_serializar_cliente(cliente) for cliente in clientes]})


@agenda_bp.route('/api/ventas/buscar', methods=['GET'])
@login_required
def buscar_ventas_relacion():
    q = (request.args.get('q') or '').strip()
    cliente_id = _parse_optional_int(request.args.get('cliente_id'))
    query = Venta.query.options(joinedload(Venta.cliente))
    if cliente_id:
        query = query.filter(Venta.id_cliente == cliente_id)
    if q:
        query = query.filter(or_(cast(Venta.id_venta, String).ilike(f'%{q}%'), Venta.numero_comprobante.ilike(f'%{q}%')))
    ventas = query.order_by(Venta.fecha_venta.desc()).limit(12).all()
    return jsonify({'items': [_serializar_venta(venta) for venta in ventas]})


@agenda_bp.route('/api/reparaciones/buscar', methods=['GET'])
@login_required
def buscar_reparaciones_relacion():
    q = (request.args.get('q') or '').strip()
    cliente_id = _parse_optional_int(request.args.get('cliente_id'))
    query = Reparacion.query.options(joinedload(Reparacion.cliente))
    if cliente_id:
        query = query.filter(Reparacion.cliente_id == cliente_id)
    if q:
        like = f'%{q}%'
        query = query.filter(or_(cast(Reparacion.id_reparacion, String).ilike(like), Reparacion.tipo_equipo.ilike(like), Reparacion.marca_modelo.ilike(like)))
    reparaciones = query.order_by(Reparacion.fecha_ingreso.desc()).limit(12).all()
    return jsonify({'items': [_serializar_reparacion(reparacion) for reparacion in reparaciones]})


@agenda_bp.route('/api/servicios/buscar', methods=['GET'])
@login_required
def buscar_servicios_relacion():
    q = (request.args.get('q') or '').strip()
    query = Servicio.query.filter(Servicio.activo.is_(True))
    if q:
        query = query.filter(or_(Servicio.nombre.ilike(f'%{q}%'), Servicio.codigo.ilike(f'%{q}%'), Servicio.categoria.ilike(f'%{q}%')))
    servicios = query.order_by(Servicio.categoria.asc(), Servicio.nombre.asc()).limit(12).all()
    return jsonify({'items': [_serializar_servicio(servicio) for servicio in servicios]})


@agenda_bp.route('/api/cliente-servicios/buscar', methods=['GET'])
@login_required
def buscar_cliente_servicios_relacion():
    cliente_id = _parse_positive_int(request.args.get('cliente_id'))
    if not cliente_id:
        return jsonify({'items': []})
    asignaciones = (
        ClienteServicio.query.options(joinedload(ClienteServicio.cliente), joinedload(ClienteServicio.servicio))
        .filter(
            ClienteServicio.id_cliente == cliente_id,
            ClienteServicio.estado.in_({'solicitado', 'presupuestado', 'agendado', 'en_proceso'}),
        )
        .order_by(ClienteServicio.fecha_solicitud.desc(), ClienteServicio.id_cliente_servicio.desc())
        .limit(10)
        .all()
    )
    return jsonify({'items': [_serializar_cliente_servicio(asignacion) for asignacion in asignaciones]})
