from flask import jsonify, request
from flask_login import current_user, login_required

from app import db
from app.models import Categoria, Cliente, Producto, ProductoPrecioOpcion, Servicio, ServicioPrecioOpcion
from app.routes.ventas.parte1 import ventas_bp


def _id_cliente_servicios():
    id_cliente = getattr(current_user, 'id_cliente', None)
    if id_cliente:
        return int(id_cliente)
    if current_user.es_admin():
        clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.id_cliente.asc()).limit(2).all()
        if len(clientes) == 1:
            return int(clientes[0].id_cliente)
    return None


def _puede_buscar_catalogo():
    return current_user.tiene_permiso('crear_venta') or current_user.tiene_permiso('ver_inventario')


@ventas_bp.route('/catalogo/buscar')
@login_required
def buscar_catalogo_pos():
    if not _puede_buscar_catalogo():
        return jsonify({'error': 'Sin permisos'}), 403
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])

    productos = _buscar_productos(q)
    servicios = _buscar_servicios(q)
    return jsonify(productos + servicios)


@ventas_bp.route('/catalogo/buscar_exacto')
@login_required
def buscar_catalogo_exacto_pos():
    if not _puede_buscar_catalogo():
        return jsonify({'error': 'Sin permisos'}), 403
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({})

    producto = _buscar_producto_exacto(q)
    if producto:
        return jsonify(producto)
    servicio = _buscar_servicio_exacto(q)
    return jsonify(servicio or {})


def _buscar_productos(q):
    like = f'%{q}%'
    productos = (
        Producto.query.join(Categoria, Producto.id_categoria == Categoria.id_categoria)
        .filter(
            Producto.activo.is_(True),
            db.or_(
                Producto.nombre.ilike(like),
                Producto.codigo.ilike(like),
                Producto.codigo_barras.ilike(like),
                Producto.codigo_proveedor.ilike(like),
                Categoria.nombre.ilike(like),
            ),
        )
        .limit(10)
        .all()
    )
    opciones = _producto_opciones([p.id_producto for p in productos])
    return [_producto_dict(p, opciones.get(int(p.id_producto), [])) for p in productos]


def _buscar_producto_exacto(q):
    q_lower = q.lower()
    producto = Producto.query.filter(
        Producto.activo.is_(True),
        db.or_(
            db.func.lower(Producto.codigo) == q_lower,
            db.func.lower(Producto.codigo_barras) == q_lower,
            db.func.lower(Producto.codigo_proveedor) == q_lower,
        ),
    ).first()
    if not producto:
        return None
    return _producto_dict(producto, _producto_opciones([producto.id_producto]).get(int(producto.id_producto), []))


def _buscar_servicios(q):
    id_cliente = _id_cliente_servicios()
    if not id_cliente:
        return []
    like = f'%{q}%'
    servicios = Servicio.query.filter(
        Servicio.id_cliente == id_cliente,
        Servicio.activo.is_(True),
        db.or_(Servicio.nombre.ilike(like), Servicio.codigo.ilike(like), Servicio.categoria.ilike(like)),
    ).order_by(Servicio.nombre.asc()).limit(10).all()
    opciones = _servicio_opciones([s.id_servicio for s in servicios])
    return [_servicio_dict(s, opciones.get(int(s.id_servicio), [])) for s in servicios]


def _buscar_servicio_exacto(q):
    id_cliente = _id_cliente_servicios()
    if not id_cliente:
        return None
    q_lower = q.lower()
    servicio = Servicio.query.filter(
        Servicio.id_cliente == id_cliente,
        Servicio.activo.is_(True),
        db.func.lower(Servicio.codigo) == q_lower,
    ).first()
    if not servicio:
        return None
    return _servicio_dict(servicio, _servicio_opciones([servicio.id_servicio]).get(int(servicio.id_servicio), []))


def _producto_opciones(producto_ids):
    if not producto_ids:
        return {}
    rows = ProductoPrecioOpcion.query.filter(
        ProductoPrecioOpcion.activo.is_(True),
        ProductoPrecioOpcion.id_producto.in_(producto_ids),
    ).order_by(ProductoPrecioOpcion.id_producto.asc(), ProductoPrecioOpcion.orden.asc()).all()
    opciones = {}
    for row in rows:
        opciones.setdefault(int(row.id_producto), []).append(row)
    return opciones


def _servicio_opciones(servicio_ids):
    if not servicio_ids:
        return {}
    rows = ServicioPrecioOpcion.query.filter(
        ServicioPrecioOpcion.activo.is_(True),
        ServicioPrecioOpcion.id_servicio.in_(servicio_ids),
    ).order_by(ServicioPrecioOpcion.id_servicio.asc(), ServicioPrecioOpcion.orden.asc()).all()
    opciones = {}
    for row in rows:
        opciones.setdefault(int(row.id_servicio), []).append(row)
    return opciones


def _producto_dict(producto, opciones):
    return {
        'tipo': 'producto',
        'id': int(producto.id_producto),
        'codigo': producto.codigo,
        'nombre': producto.nombre,
        'precio': float(producto.precio_venta or 0),
        'precio_mayorista': float(producto.precio_mayorista) if producto.precio_mayorista else None,
        'precios_opciones': [{'id': int(o.id_opcion_precio), 'etiqueta': (o.etiqueta or '').strip() or None, 'precio': float(o.precio or 0)} for o in opciones],
        'stock': int(producto.stock_actual or 0),
        'stock_minimo': int(producto.stock_minimo or 0),
        'es_servicio': bool(producto.es_servicio),
        'iva': int(producto.porcentaje_iva or 0),
    }


def _servicio_dict(servicio, opciones):
    return {
        'tipo': 'servicio',
        'id': int(servicio.id_servicio),
        'codigo': servicio.codigo or f'SRV-{servicio.id_servicio}',
        'nombre': servicio.nombre,
        'precio': float(servicio.precio or 0),
        'precio_mayorista': None,
        'precios_opciones': [{'id': int(o.id_opcion_precio), 'etiqueta': o.etiqueta, 'precio': float(o.precio or 0)} for o in opciones],
        'stock': 0,
        'stock_minimo': 0,
        'es_servicio': True,
        'iva': int(servicio.porcentaje_iva or 0),
    }
