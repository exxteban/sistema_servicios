"""Pantalla "Facturas electrónicas": el listado de documentos emitidos.

Vive aparte de `routes.py` por tamaño y se cuelga del mismo blueprint. Es de
consulta: no hace nada con los documentos. Cada fila lleva a la venta, que ya
tiene el panel de factura con sus acciones (KuDE, XML, cancelar, inutilizar),
cada una con su propio permiso. Por eso acá alcanza con poder ver reportes: es
lo que necesita el contador.
"""
from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.utils.helpers import parse_iso_date, today_local
from app.utils.modulos import _modulo_activo
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO
from facturacion_electronica.routes import facturacion_electronica_bp
from facturacion_electronica.services.listado_documentos import (
    ETIQUETAS_FILTRO,
    csv_documentos,
    listar_documentos,
    periodo_por_defecto,
)


def puede_ver_documentos(usuario):
    return bool(usuario.es_admin()
                or usuario.tiene_permiso('editar_configuracion')
                or usuario.tiene_permiso('ver_reportes'))


def _filtros():
    """(desde, hasta, estado, tipo) de la query string, con el mes en curso por defecto."""
    desde_def, hasta_def = periodo_por_defecto(today_local())
    desde = parse_iso_date(request.args.get('desde')) or desde_def
    hasta = parse_iso_date(request.args.get('hasta')) or hasta_def
    if hasta < desde:
        desde, hasta = hasta, desde
    estado = (request.args.get('estado') or '').strip()
    tipo = (request.args.get('tipo') or '').strip()
    return desde, hasta, estado, tipo


def _sin_acceso():
    if not _modulo_activo(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, False):
        flash('La facturación electrónica no está activa.', 'warning')
        return redirect(url_for('main.dashboard'))
    if not puede_ver_documentos(current_user):
        flash('No tenés permisos para ver las facturas electrónicas.', 'danger')
        return redirect(url_for('main.dashboard'))
    return None


@facturacion_electronica_bp.route('/documentos')
@login_required
def documentos():
    salida = _sin_acceso()
    if salida:
        return salida
    desde, hasta, estado, tipo = _filtros()
    listado = listar_documentos(desde, hasta, estado, tipo, request.args.get('pagina', 1, type=int))
    return render_template(
        'facturacion_electronica/documentos.html',
        desde=desde, hasta=hasta, estado=estado, tipo=tipo,
        etiquetas_filtro=ETIQUETAS_FILTRO,
        **listado,
    )


@facturacion_electronica_bp.route('/documentos.csv')
@login_required
def documentos_csv():
    salida = _sin_acceso()
    if salida:
        return salida
    desde, hasta, estado, tipo = _filtros()
    nombre = f'facturas_electronicas_{desde.isoformat()}_{hasta.isoformat()}.csv'
    return Response(
        csv_documentos(desde, hasta, estado, tipo),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{nombre}"'},
    )
