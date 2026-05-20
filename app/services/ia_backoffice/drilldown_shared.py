from sqlalchemy import case, func, or_
from sqlalchemy.orm import joinedload

from app.models import Cliente, Producto, Ticket, Venta
from app.services.ia_backoffice.periods import resolver_rango


ESTADOS_REPARACION_CERRADOS = {'entregado', 'cancelado', 'antiguos'}


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _pct(actual: float, anterior: float) -> float | None:
    actual = _money(actual)
    anterior = _money(anterior)
    if not anterior:
        return None
    return round(((actual - anterior) / anterior) * 100, 2)


def _comparacion(actual, anterior) -> dict:
    actual_val = _money(actual)
    anterior_val = _money(anterior)
    return {
        'actual': actual_val,
        'anterior': anterior_val,
        'variacion_abs': round(actual_val - anterior_val, 2),
        'variacion_pct': _pct(actual_val, anterior_val),
    }


def _iso(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _args_has_periodo(args: dict | None) -> bool:
    data = args or {}
    return bool(data.get('periodo') or data.get('desde') or data.get('hasta'))


def _rango_con_default(args: dict | None, periodo_default: str) -> dict:
    data = dict(args or {})
    if not _args_has_periodo(data):
        data['periodo'] = periodo_default
    return resolver_rango(data)


def _usuario_autenticado(usuario) -> bool:
    return bool(usuario and getattr(usuario, 'is_authenticated', False))


def _es_admin(usuario) -> bool:
    return bool(usuario and getattr(usuario, 'es_admin', lambda: False)())


def _tiene_permiso(usuario, codigo: str) -> bool:
    if not _usuario_autenticado(usuario):
        return False
    if _es_admin(usuario):
        return True
    return bool(getattr(usuario, 'tiene_permiso', lambda _codigo: False)(codigo))


def _puede_ver_ventas(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_ventas') or _tiene_permiso(usuario, 'ver_reporte_ventas')


def _puede_ver_clientes(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_clientes')


def _puede_ver_cobranzas(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_cobranzas') or _tiene_permiso(usuario, 'ver_reportes_cobranzas')


def _puede_ver_inventario(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_inventario') or _tiene_permiso(usuario, 'ver_reporte_inventario')


def _puede_ver_gastos(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_gastos_corrientes') or _tiene_permiso(usuario, 'ver_reportes_gastos_corrientes')


def _puede_ver_reparaciones(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_reparaciones')


def _puede_ver_caja(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_caja') or _tiene_permiso(usuario, 'ver_otras_cajas')


def _puede_ver_pedidos(usuario) -> bool:
    return _tiene_permiso(usuario, 'ver_clientes')


def _texto_busqueda(args: dict | None) -> str:
    data = args or {}
    for key in ('busqueda', 'referencia'):
        value = (data.get(key) or '').strip()
        if value:
            return value
    return ''


def _cliente_candidato_payload(cliente: Cliente) -> dict:
    return {
        'id_cliente': int(cliente.id_cliente),
        'nombre': cliente.nombre,
        'ruc_ci': cliente.ruc_ci or '',
        'telefono': cliente.telefono or '',
        'tipo': cliente.tipo or '',
        'activo': bool(cliente.activo),
    }


def _producto_candidato_payload(producto: Producto) -> dict:
    return {
        'id_producto': int(producto.id_producto),
        'codigo': producto.codigo,
        'nombre': producto.nombre,
        'marca': producto.marca or '',
        'modelo': producto.modelo or '',
        'stock_actual': int(producto.stock_actual or 0),
        'activo': bool(producto.activo),
    }


def _venta_candidata_payload(venta: Venta) -> dict:
    return {
        'id_venta': int(venta.id_venta),
        'numero_comprobante': venta.numero_comprobante or '',
        'tipo_comprobante': venta.tipo_comprobante or '',
        'fecha_venta': _iso(venta.fecha_venta),
        'cliente': venta.cliente.nombre if venta.cliente else '',
        'total': _money(venta.total),
        'estado': venta.estado or '',
    }


def _resolver_cliente(args: dict | None) -> tuple[Cliente | None, list[dict]]:
    data = args or {}
    cliente_id = data.get('id_cliente')
    if cliente_id:
        try:
            cliente = Cliente.query.get(int(cliente_id))
        except Exception:
            cliente = None
        return cliente, []

    termino = _texto_busqueda(data)
    if not termino:
        return None, []

    like = f'%{termino}%'
    filas = (
        Cliente.query
        .filter(
            or_(
                Cliente.nombre.ilike(like),
                Cliente.ruc_ci.ilike(like),
                Cliente.telefono.ilike(like),
                Cliente.email.ilike(like),
            )
        )
        .order_by(
            case(
                (func.lower(Cliente.nombre) == termino.lower(), 0),
                (Cliente.nombre.ilike(f'{termino}%'), 1),
                (Cliente.ruc_ci == termino, 2),
                (Cliente.telefono == termino, 3),
                else_=4,
            ),
            Cliente.nombre.asc(),
        )
        .limit(6)
        .all()
    )
    if not filas:
        return None, []
    exactos = [
        item for item in filas
        if (item.nombre or '').strip().lower() == termino.lower()
        or (item.ruc_ci or '').strip() == termino
        or (item.telefono or '').strip() == termino
    ]
    if len(filas) == 1:
        return filas[0], []
    if len(exactos) == 1:
        return exactos[0], []
    return None, [_cliente_candidato_payload(item) for item in filas]


def _resolver_producto(args: dict | None) -> tuple[Producto | None, list[dict]]:
    data = args or {}
    producto_id = data.get('id_producto')
    if producto_id:
        try:
            producto = Producto.query.get(int(producto_id))
        except Exception:
            producto = None
        return producto, []

    termino = _texto_busqueda(data)
    if not termino:
        return None, []

    like = f'%{termino}%'
    filas = (
        Producto.query
        .filter(
            or_(
                Producto.codigo.ilike(like),
                Producto.codigo_barras.ilike(like),
                Producto.nombre.ilike(like),
                Producto.marca.ilike(like),
                Producto.modelo.ilike(like),
            )
        )
        .order_by(
            case(
                (func.lower(Producto.codigo) == termino.lower(), 0),
                (func.lower(Producto.nombre) == termino.lower(), 1),
                (Producto.codigo.ilike(f'{termino}%'), 2),
                (Producto.nombre.ilike(f'{termino}%'), 3),
                else_=4,
            ),
            Producto.nombre.asc(),
        )
        .limit(6)
        .all()
    )
    if not filas:
        return None, []
    exactos = [
        item for item in filas
        if (item.codigo or '').strip().lower() == termino.lower()
        or (item.nombre or '').strip().lower() == termino.lower()
        or (item.codigo_barras or '').strip() == termino
    ]
    if len(filas) == 1:
        return filas[0], []
    if len(exactos) == 1:
        return exactos[0], []
    return None, [_producto_candidato_payload(item) for item in filas]


def _resolver_venta(args: dict | None) -> tuple[Venta | None, list[dict]]:
    data = args or {}
    venta_id = data.get('id_venta')
    base = Venta.query.options(
        joinedload(Venta.cliente),
        joinedload(Venta.vendedor),
    )
    if venta_id:
        try:
            venta = base.filter(Venta.id_venta == int(venta_id)).first()
        except Exception:
            venta = None
        return venta, []

    termino = _texto_busqueda(data)
    if not termino:
        return None, []

    like = f'%{termino}%'
    filas = (
        base.outerjoin(Ticket, Ticket.id_venta == Venta.id_venta)
        .filter(
            or_(
                Venta.numero_comprobante.ilike(like),
                Venta.client_request_id.ilike(like),
                Ticket.numero_ticket.ilike(like),
            )
        )
        .order_by(
            case(
                (Venta.numero_comprobante == termino, 0),
                (Venta.client_request_id == termino, 1),
                (Ticket.numero_ticket == termino, 2),
                else_=3,
            ),
            Venta.fecha_venta.desc(),
        )
        .limit(6)
        .all()
    )
    if not filas:
        return None, []
    exactos = [
        item for item in filas
        if (item.numero_comprobante or '').strip() == termino
        or (item.client_request_id or '').strip() == termino
        or (item.ticket and (item.ticket.numero_ticket or '').strip() == termino)
    ]
    if len(filas) == 1:
        return filas[0], []
    if len(exactos) == 1:
        return exactos[0], []
    return None, [_venta_candidata_payload(item) for item in filas]


def _hallazgo(prioridad: str, area: str, titulo: str, detalle: str, evidencia: dict | None, accion: str) -> dict:
    score = {'alta': 3, 'media': 2, 'baja': 1}.get(prioridad, 1)
    return {
        'score': score,
        'prioridad': prioridad,
        'area': area,
        'titulo': titulo,
        'detalle': detalle,
        'evidencia': evidencia or {},
        'accion_sugerida': accion,
    }
