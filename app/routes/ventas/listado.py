"""Historial de ventas (/ventas/): buscar una venta para anularla, emitirle la
factura electronica o una nota de credito. La logica vive en
`app.services.ventas_listado`; aca solo el armado de la pantalla."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.models import SesionCaja, Venta
from app.services.ventas_listado import (
    RANGOS_RAPIDOS,
    detalles_por_venta,
    leer_filtros,
    query_ventas_filtrada,
    resumen_ventas,
)

from .parte1 import ventas_bp


@ventas_bp.route('/')
@login_required
def listar():
    """Lista de ventas"""
    if not current_user.tiene_permiso('ver_ventas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver ventas.', 'danger')
        return redirect(url_for('main.dashboard'))

    from facturacion_electronica import MOTIVOS_NOTA_CREDITO
    from facturacion_electronica.services.acciones import documentos_fe_de_ventas

    filtros = leer_filtros(request.args)
    query = query_ventas_filtrada(filtros, current_user)
    resumen = resumen_ventas(query)
    ventas = query.options(
        joinedload(Venta.cliente),
        joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
        joinedload(Venta.vendedor),
        joinedload(Venta.reparacion),
    ).order_by(Venta.fecha_venta.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=20, error_out=False
    )
    documentos_fe = documentos_fe_de_ventas([v.id_venta for v in ventas.items])

    return render_template(
        'ventas/listar.html',
        ventas=ventas,
        detalles_por_venta=detalles_por_venta(ventas.items),
        resumen=resumen,
        documentos_fe=documentos_fe,
        fe_motivos_nc=MOTIVOS_NOTA_CREDITO,
        rangos_rapidos=RANGOS_RAPIDOS,
        rango=filtros['rango'],
        estado=filtros['estado'],
        q=filtros['q'],
        todas=filtros['todas'],
        desde=filtros['desde'].isoformat() if filtros['desde'] else '',
        hasta=filtros['hasta'].isoformat() if filtros['hasta'] else '',
    )
