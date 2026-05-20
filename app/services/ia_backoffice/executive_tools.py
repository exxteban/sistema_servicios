from sqlalchemy import String, cast

from app import db
from app.models import Categoria, Cliente, Compra, PedidoCliente, Producto, Proveedor, Reparacion, Venta
from app.services.ia_backoffice.periods import normalizar_top_n


PALABRAS_IGNORADAS_PRODUCTOS = {
    'que', 'hay', 'tenes', 'tienes', 'producto', 'productos', 'articulo', 'articulos',
    'item', 'items', 'de', 'del', 'para', 'con', 'los', 'las', 'un', 'una',
}
TERMINOS_MOVILES = {'celular', 'celulares', 'telefono', 'telefonos', 'android', 'smartphone', 'movil', 'moviles'}
SINONIMOS_MOVILES = (
    'samsung', 'sam', 'xiaomi', 'redmi', 'motorola', 'moto', 'huawei', 'honor',
    'iphone', 'iph', 'oppo', 'vivo', 'realme', 'tecno', 'infinix', 'modulo',
    'pantalla', 'display', 'bateria', 'case', 'lamina', 'templado', 'cargador',
    'cable', 'repuesto', 'accesorio',
)


def _like_busqueda(texto: str):
    return f'%{(texto or "").strip()}%'


def _tokens_busqueda(texto: str) -> list[str]:
    tokens = []
    for raw in (texto or '').lower().replace('?', ' ').replace('.', ' ').split():
        token = raw.strip(' ,;:!?"\'()[]{}')
        if len(token) < 3 or token in PALABRAS_IGNORADAS_PRODUCTOS:
            continue
        if token.endswith('es') and len(token) > 4:
            tokens.append(token[:-2])
        if token.endswith('s') and len(token) > 4:
            tokens.append(token[:-1])
        tokens.append(token)
    return list(dict.fromkeys(tokens))


def _es_busqueda_moviles(busqueda: str, tokens: list[str]) -> bool:
    texto = (busqueda or '').lower()
    return bool(TERMINOS_MOVILES.intersection(tokens) or any(term in texto for term in TERMINOS_MOVILES))


def _condiciones_producto(termino: str):
    patron = _like_busqueda(termino)
    return db.or_(
        Producto.codigo.ilike(patron),
        Producto.nombre.ilike(patron),
        Producto.codigo_barras.ilike(patron),
        Categoria.nombre.ilike(patron),
    )


def _producto_payload(producto: Producto) -> dict:
    return {
        'id_producto': producto.id_producto,
        'codigo': producto.codigo,
        'nombre': producto.nombre,
        'stock_actual': producto.stock_actual,
        'precio_venta': float(producto.precio_venta or 0),
        'categoria': producto.categoria.nombre if producto.categoria else '',
    }


def _buscar_productos(busqueda: str, top_n: int) -> list[dict]:
    tokens = _tokens_busqueda(busqueda)
    terminos = [busqueda.strip(), *tokens]
    if _es_busqueda_moviles(busqueda, tokens):
        terminos.extend(SINONIMOS_MOVILES)
    terminos = [t for t in dict.fromkeys(terminos) if t]
    base = (
        Producto.query
        .outerjoin(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .filter(Producto.activo.is_(True), Producto.es_servicio.is_(False))
    )
    condiciones = [_condiciones_producto(termino) for termino in terminos]
    query = base.filter(db.or_(*condiciones)) if condiciones else base
    filas = query.order_by(Producto.stock_actual.desc(), Producto.nombre.asc()).limit(top_n).all()
    if not filas and _es_busqueda_moviles(busqueda, tokens):
        filas = base.order_by(Producto.stock_actual.desc(), Producto.nombre.asc()).limit(top_n).all()
    return [_producto_payload(producto) for producto in filas]


def buscar_entidad_backoffice(args: dict, usuario=None) -> dict:
    busqueda = (args.get('busqueda') or args.get('referencia') or '').strip()
    top_n = normalizar_top_n(args.get('top_n'), default=5, maximo=10)
    if not busqueda:
        return {'error': 'busqueda_requerida', 'resultados': {}}
    patron = _like_busqueda(busqueda)
    resultados = {}
    resultados['clientes'] = [
        {'id_cliente': c.id_cliente, 'nombre': c.nombre, 'ruc_ci': c.ruc_ci, 'telefono': c.telefono}
        for c in Cliente.query.filter(
            db.or_(Cliente.nombre.ilike(patron), Cliente.ruc_ci.ilike(patron), Cliente.telefono.ilike(patron))
        ).limit(top_n).all()
    ]
    resultados['productos'] = _buscar_productos(busqueda, top_n)
    resultados['proveedores'] = [
        {'id_proveedor': p.id_proveedor, 'nombre': p.nombre, 'ruc': p.ruc, 'telefono': p.telefono}
        for p in Proveedor.query.filter(
            db.or_(Proveedor.nombre.ilike(patron), Proveedor.ruc.ilike(patron), Proveedor.telefono.ilike(patron))
        ).limit(top_n).all()
    ]
    resultados['ventas'] = [
        {'id_venta': v.id_venta, 'numero_comprobante': v.numero_comprobante, 'fecha_venta': v.fecha_venta.isoformat() if v.fecha_venta else None, 'total': float(v.total or 0)}
        for v in Venta.query.filter(Venta.numero_comprobante.ilike(patron)).limit(top_n).all()
    ]
    resultados['compras'] = [
        {'id_compra': c.id_compra, 'numero_factura': c.numero_factura, 'fecha_compra': c.fecha_compra.isoformat() if c.fecha_compra else None, 'total': float(c.total or 0)}
        for c in Compra.query.filter(Compra.numero_factura.ilike(patron)).limit(top_n).all()
    ]
    resultados['reparaciones'] = [
        {'id_reparacion': r.id_reparacion, 'equipo': f'{r.tipo_equipo} {r.marca_modelo}', 'estado': r.estado}
        for r in Reparacion.query.filter(
            db.or_(Reparacion.marca_modelo.ilike(patron), Reparacion.falla_reportada.ilike(patron))
        ).limit(top_n).all()
    ]
    resultados['pedidos'] = [
        {'id_pedido': p.id_pedido, 'numero_pedido': p.numero_pedido, 'estado': p.estado, 'total': float(p.total or 0)}
        for p in PedidoCliente.query.filter(cast(PedidoCliente.numero_pedido, String).ilike(patron)).limit(top_n).all()
    ]
    total = sum(len(items) for items in resultados.values())
    return {'busqueda': busqueda, 'total_resultados': total, 'resultados': resultados}


def _safe_tool(nombre: str, args, usuario):
    try:
        from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
        return ejecutar_tool_backoffice(nombre, args, usuario=usuario)
    except Exception as exc:
        return {'error': type(exc).__name__}


def dashboard_operativo_hoy(args: dict, usuario=None) -> dict:
    hoy_args = {'periodo': 'hoy', 'top_n': 5}
    return {
        'periodo': 'hoy',
        'ventas': _safe_tool('ventas_resumen_periodo', hoy_args, usuario),
        'cobranzas': _safe_tool('cobranzas_resumen', hoy_args, usuario),
        'caja': _safe_tool('caja_estado_actual', hoy_args, usuario),
        'gastos_vencidos': _safe_tool('gastos_vencidos', hoy_args, usuario),
        'reparaciones_atrasadas': _safe_tool('reparaciones_atrasadas', hoy_args, usuario),
        'pedidos_pagos_pendientes': _safe_tool('pedidos_pagos_pendientes', hoy_args, usuario),
        'stock_critico': _safe_tool('inventario_productos_reponer', hoy_args, usuario),
    }
