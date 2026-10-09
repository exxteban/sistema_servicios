"""Historial de ventas: filtros, totales del periodo y texto de detalle por fila.

Es la pantalla desde donde se busca una venta para anularla, emitirle la
factura o una nota de credito. Por eso abre en el dia de hoy y trae arriba lo
que se vendio, lo que entro y lo que quedo a credito en el rango filtrado.
"""
from datetime import timedelta

from sqlalchemy import case, func, or_

from app import db
from app.models import (
    Cliente, DetalleVenta, PagoVenta, PedidoCliente, PedidoClientePago, Producto, SesionCaja, Venta,
)
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates

ESTADOS_FILTRO = ('completada', 'anulada')
RANGOS_RAPIDOS = (
    ('hoy', 'Hoy'),
    ('ayer', 'Ayer'),
    ('7d', '7 días'),
    ('mes', 'Este mes'),
)


def _rango_rapido(clave, hoy):
    if clave == 'hoy':
        return hoy, hoy
    if clave == 'ayer':
        ayer = hoy - timedelta(days=1)
        return ayer, ayer
    if clave == '7d':
        return hoy - timedelta(days=6), hoy
    if clave == 'mes':
        return hoy.replace(day=1), hoy
    return None, None


def leer_filtros(args):
    """Filtros del querystring.

    Sin ningun filtro abre en el dia de hoy. Una busqueda o un estado sin
    fechas recorre todo el historial: quien busca una venta vieja para
    anularla no tiene por que acordarse de que dia fue.
    """
    hoy = today_local()
    desde = parse_iso_date(args.get('desde'))
    hasta = parse_iso_date(args.get('hasta'))
    rango = (args.get('rango') or '').strip()
    q = (args.get('q') or '').strip()
    estado = (args.get('estado') or '').strip().lower()
    estado = estado if estado in ESTADOS_FILTRO else ''
    todas = args.get('todas') == '1'

    if rango:
        desde, hasta = _rango_rapido(rango, hoy)
    elif not (desde or hasta):
        if q or estado:
            todas = True
        elif not todas:
            rango = 'hoy'
            desde, hasta = hoy, hoy

    if desde or hasta:
        desde = desde or hasta
        hasta = hasta or desde
        if desde > hasta:
            desde, hasta = hasta, desde

    return {
        'desde': desde,
        'hasta': hasta,
        'rango': rango,
        'todas': todas and not (desde or hasta),
        'estado': estado,
        'q': q,
    }


def query_ventas_filtrada(filtros, usuario):
    """Query de ventas con los filtros aplicados, sin orden ni paginado."""
    query = Venta.query

    # Sin permiso de ver otras cajas, solo las ventas de sus propias sesiones.
    if not (usuario.es_admin() or usuario.tiene_permiso('ver_otras_cajas')):
        mis_sesiones = (
            db.session.query(SesionCaja.id_sesion)
            .filter(SesionCaja.id_usuario == usuario.id_usuario)
            .subquery()
        )
        query = query.filter(Venta.id_sesion_caja.in_(mis_sesiones))

    if filtros['desde'] and filtros['hasta']:
        start_utc, end_utc = utc_bounds_for_local_dates(filtros['desde'], filtros['hasta'])
        query = query.filter(Venta.fecha_venta >= start_utc, Venta.fecha_venta < end_utc)

    if filtros['estado']:
        query = query.filter(Venta.estado == filtros['estado'])

    texto = filtros['q']
    if texto:
        condiciones = [Venta.cliente.has(Cliente.nombre.ilike(f'%{texto}%'))]
        numero = texto.lstrip('#').strip()
        if numero.isdigit():
            condiciones.append(Venta.id_venta == int(numero))
        # Numero de factura electronica: "001-001-0000031" o solo "31".
        numero_factura = texto.rsplit('-', 1)[-1].strip()
        if numero_factura.isdigit() and len(numero_factura) <= 7:
            from facturacion_electronica.models import DocumentoElectronico

            condiciones.append(Venta.id_venta.in_(
                db.session.query(DocumentoElectronico.id_venta)
                .filter(DocumentoElectronico.numero == numero_factura.zfill(7))
            ))
        query = query.filter(or_(*condiciones))

    return query


def resumen_ventas(query):
    """Totales del rango filtrado (todas las paginas, no solo la visible)."""
    ids_subq = query.with_entities(Venta.id_venta).subquery()
    base = db.session.query(Venta).filter(Venta.id_venta.in_(db.select(ids_subq.c.id_venta)))

    completadas = base.filter(Venta.estado == 'completada')
    cantidad, total = completadas.with_entities(
        func.count(Venta.id_venta), func.coalesce(func.sum(Venta.total), 0)
    ).one()

    # Lo cobrado en la venta se tope en el total: los pagos guardan lo que
    # entrego el cliente y el vuelto sale aparte como egreso de caja.
    pagado = (
        db.session.query(PagoVenta.id_venta, func.sum(PagoVenta.monto).label('monto'))
        .group_by(PagoVenta.id_venta)
        .subquery()
    )
    # Una venta que sale de la entrega de un pedido no tiene pagos propios:
    # lo cobrado son las senas y pagos del pedido.
    pagado_pedido = (
        db.session.query(
            PedidoCliente.id_venta_generada.label('id_venta'),
            func.sum(PedidoClientePago.monto).label('monto'),
        )
        .join(PedidoClientePago, PedidoClientePago.id_pedido == PedidoCliente.id_pedido)
        .filter(PedidoCliente.id_venta_generada.isnot(None), PedidoClientePago.estado == 'activo')
        .group_by(PedidoCliente.id_venta_generada)
        .subquery()
    )
    pagado_venta = func.coalesce(pagado.c.monto, 0) + func.coalesce(pagado_pedido.c.monto, 0)
    cobrado_venta = case((pagado_venta > Venta.total, Venta.total), else_=pagado_venta)
    es_credito = func.lower(func.coalesce(Venta.tipo_venta, 'contado')) == 'credito'
    cobrado, financiado, pendiente = (
        completadas.outerjoin(pagado, pagado.c.id_venta == Venta.id_venta)
        .outerjoin(pagado_pedido, pagado_pedido.c.id_venta == Venta.id_venta)
        .with_entities(
            func.coalesce(func.sum(cobrado_venta), 0),
            # Lo que la venta dejo a credito, aunque despues se haya cobrado.
            func.coalesce(func.sum(case((es_credito, Venta.total - cobrado_venta), else_=0)), 0),
            # Lo que todavia se debe hoy de esas ventas (cuotas e intereses incluidos).
            func.coalesce(func.sum(case((es_credito, Venta.saldo_pendiente), else_=0)), 0),
        )
        .one()
    )
    anuladas, total_anulado = base.filter(Venta.estado == 'anulada').with_entities(
        func.count(Venta.id_venta), func.coalesce(func.sum(Venta.total), 0)
    ).one()

    return {
        'cantidad': int(cantidad or 0),
        'total': float(total or 0),
        'cobrado': float(cobrado or 0),
        'financiado': float(financiado or 0),
        'pendiente_credito': float(pendiente or 0),
        'anuladas': int(anuladas or 0),
        'total_anulado': float(total_anulado or 0),
    }


def detalles_por_venta(ventas):
    """Texto corto de cada fila: productos vendidos o la reparacion cobrada."""
    detalles = {}
    venta_ids = [v.id_venta for v in ventas]
    if not venta_ids:
        return detalles

    for v in ventas:
        txt = ''
        rep = getattr(v, 'reparacion', None)
        if rep is not None:
            txt = (rep.solucion or rep.diagnostico_tecnico or rep.falla_reportada or '').strip()
            txt = f"Reparación: {txt}" if txt else "Reparación"
        detalles[v.id_venta] = txt

    rows = (
        db.session.query(
            DetalleVenta.id_venta,
            Producto.nombre,
            func.sum(DetalleVenta.cantidad).label('cantidad'),
        )
        .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
        .filter(DetalleVenta.id_venta.in_(venta_ids))
        .group_by(DetalleVenta.id_venta, Producto.nombre)
        .order_by(DetalleVenta.id_venta.asc(), Producto.nombre.asc())
        .all()
    )
    agrupado = {}
    for id_venta, nombre, cantidad in rows:
        try:
            cant_int = int(cantidad or 0)
        except Exception:
            cant_int = 0
        agrupado.setdefault(int(id_venta), []).append((nombre, cant_int))

    obs_by_id = {v.id_venta: (v.observaciones or '').strip() for v in ventas}
    for id_venta in venta_ids:
        if detalles.get(id_venta):
            continue
        partes = [
            f"{nombre} x{cant}" if cant and cant != 1 else f"{nombre}"
            for nombre, cant in agrupado.get(int(id_venta), [])
        ]
        detalles[id_venta] = ", ".join(p for p in partes if p) or obs_by_id.get(id_venta, '')
    return detalles
