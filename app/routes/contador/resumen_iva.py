"""Pantalla "Resumen de IVA del mes": débito, crédito y lo pendiente para cerrar.

El cálculo vive en `app.services.resumen_contadora`. Con facturación
electrónica el débito sale de SIFEN; sin ella, de las ventas con número de
factura en papel.

Portado de sistema_silvio_cel. Sin el aviso del campo "Nº Factura" del POS:
en este sistema ese campo llega con los talonarios (fase 4).
"""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.routes.contador import contador_bp, puede_ver_area_contador
from app.services.contador_meses import estado_del_mes, guardar_ajustes, marcar_presentado
from app.services.resumen_contadora import mes_por_defecto, mes_vecino, parse_mes, resumen_del_mes
from app.services.resumen_contadora_detalle import FILAS_SIFEN, FILAS_SIN_SIFEN, detalle_fila, excel_detalle
from app.services.resumen_contadora_exportar import respuesta_excel, respuesta_pdf
from app.services.resumen_contadora_informe import informe_del_mes
from app.utils.auditoria_utils import registrar_auditoria
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
        cierre=estado_del_mes(primero, resumen['debito'], resumen['credito']),
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
    """Lo que suma una fila del cuadro de IVA: HTML para el modal, o .xlsx."""
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
    if request.args.get('formato') == 'xlsx':
        return excel_detalle(detalle)
    return render_template('contador/_resumen_iva_detalle.html', detalle=detalle, mes=primero.strftime('%Y-%m'))


def _mes_del_formulario():
    if not puede_ver_area_contador(current_user):
        abort(403)
    primero = parse_mes(request.form.get('mes'))
    if primero is None:
        abort(400)
    return primero


@contador_bp.route('/iva/ajustes', methods=['POST'])
@login_required
def resumen_iva_ajustes():
    """Saldo a favor del mes anterior y retenciones: no se pueden calcular, se cargan."""
    primero = _mes_del_formulario()
    error = guardar_ajustes(primero, request.form.get('saldo_favor_anterior'), request.form.get('retenciones'))
    if error:
        flash(error, 'danger')
    else:
        db.session.commit()
        flash('Saldo anterior y retenciones guardados.', 'success')
    return redirect(url_for('contador.resumen_iva', mes=primero.strftime('%Y-%m')))


@contador_bp.route('/iva/presentado', methods=['POST'])
@login_required
def resumen_iva_presentado():
    """Marca el mes presentado con una foto del débito y el crédito, o lo desmarca."""
    primero = _mes_del_formulario()
    presentado = request.form.get('presentado') == '1'
    fe_activa, ambiente = _facturacion_y_ambiente()
    if presentado and fe_activa and ambiente == 'test':
        flash('El ambiente de prueba no tiene validez fiscal: no se puede marcar el mes como presentado.', 'danger')
        return redirect(url_for('contador.resumen_iva', mes=primero.strftime('%Y-%m')))
    resumen = resumen_del_mes(primero, fe_activa, ambiente)
    marcar_presentado(primero, presentado, resumen['debito'], resumen['credito'], current_user.id_usuario)
    db.session.commit()
    periodo = primero.strftime('%m/%Y')
    registrar_auditoria('contador_mes_presentado', 'contador',
                        f"IVA {periodo} {'marcado presentado' if presentado else 'vuelto a abrir'}",
                        referencia_tipo='contador_mes',
                        datos_nuevos={'debito': resumen['debito'], 'credito': resumen['credito']} if presentado else None)
    flash(f'IVA de {periodo} marcado como presentado.' if presentado else f'IVA de {periodo} vuelto a abrir.', 'success')
    return redirect(url_for('contador.resumen_iva', mes=primero.strftime('%Y-%m')))


def _informe_pedido():
    if not puede_ver_area_contador(current_user):
        abort(403)
    primero = parse_mes(request.args.get('mes')) or mes_por_defecto(today_local())
    fe_activa, ambiente = _facturacion_y_ambiente()
    return primero, informe_del_mes(primero, fe_activa, ambiente)


@contador_bp.route('/iva/pdf')
@login_required
def resumen_iva_pdf():
    """El informe del mes en PDF; `anexos=0` deja sólo el resumen."""
    primero, informe = _informe_pedido()
    respuesta = respuesta_pdf(informe, con_anexos=request.args.get('anexos') != '0')
    if respuesta is None:
        flash('No se pudo generar el PDF en este servidor. Probá con el Excel.', 'danger')
        return redirect(url_for('contador.resumen_iva', mes=primero.strftime('%Y-%m')))
    return respuesta


@contador_bp.route('/iva/excel')
@login_required
def resumen_iva_excel():
    """El informe del mes en un Excel: resumen y una hoja por anexo."""
    _primero, informe = _informe_pedido()
    return respuesta_excel(informe)
