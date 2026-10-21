"""Pantalla "Resumen de IVA del mes": débito, crédito y lo pendiente para cerrar.

El cálculo vive en `app.services.resumen_contadora`. Con facturación
electrónica el débito sale de SIFEN; sin ella, de las ventas con número de
factura en papel.

Fase 2 del port: sólo lectura (pantalla y detalle de cada fila). El cierre del
mes y las descargas en PDF/Excel llegan después.
"""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.contador import contador_bp, puede_ver_area_contador
from app.services.resumen_contadora import mes_por_defecto, mes_vecino, parse_mes, resumen_del_mes
from app.services.resumen_contadora_detalle import FILAS_SIFEN, FILAS_SIN_SIFEN, detalle_fila
from app.utils.helpers import today_local
from app.utils.modulos import _modulo_activo


@contador_bp.route('/iva')
@login_required
def resumen_iva():
    if not puede_ver_area_contador(current_user):
        flash('No tenés permisos para ver el resumen para el/la contador/a.', 'danger')
        return redirect(url_for('main.dashboard'))

    primero = parse_mes(request.args.get('mes')) or mes_por_defecto(today_local())
    fe_activa, ambiente = _facturacion_y_ambiente()
    resumen = resumen_del_mes(primero, fe_activa, ambiente)

    return render_template(
        'contador/resumen_iva.html',
        mes=primero.strftime('%Y-%m'),
        mes_anterior=mes_vecino(primero, -1).strftime('%Y-%m'),
        mes_siguiente=mes_vecino(primero, 1).strftime('%Y-%m'),
        vista='anuladas' if request.args.get('vista') == 'anuladas' else 'iva',
        **resumen,
    )


def _facturacion_y_ambiente():
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

    fe_activa = _modulo_activo(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, False)
    ambiente = None
    if fe_activa:
        from facturacion_electronica.services.config_service import obtener_configuracion

        ambiente = getattr(obtener_configuracion(), 'ambiente', None)
    return fe_activa, ambiente


@contador_bp.route('/iva/detalle')
@login_required
def resumen_iva_detalle():
    """Lo que suma una fila del cuadro de IVA, como HTML para el modal."""
    if not puede_ver_area_contador(current_user):
        abort(403)
    primero = parse_mes(request.args.get('mes')) or mes_por_defecto(today_local())
    fila = request.args.get('fila', '')
    fe_activa, ambiente = _facturacion_y_ambiente()
    if (fila in FILAS_SIFEN and not fe_activa) or (fila in FILAS_SIN_SIFEN and fe_activa):
        abort(404)
    detalle = detalle_fila(primero, fila, ambiente)
    if detalle is None:
        abort(404)
    return render_template('contador/_resumen_iva_detalle.html', detalle=detalle, mes=primero.strftime('%Y-%m'))
