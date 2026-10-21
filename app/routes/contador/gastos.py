"""Cargar la factura de un pago de gasto corriente, para el crédito fiscal."""
from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import PagoGastoCorriente
from app.routes.contador import contador_bp, puede_cargar_factura_de_gasto
from app.services.gastos_credito_fiscal import registrar
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.helpers import parse_iso_date


@contador_bp.route('/gasto-pago/<int:id>/factura', methods=['POST'])
@login_required
def gasto_pago_factura(id):
    if not puede_cargar_factura_de_gasto(current_user):
        abort(403)
    pago = db.get_or_404(PagoGastoCorriente, id)
    volver = redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=pago.id_gasto_corriente))
    anterior = pago.comprobante_fiscal.numero if pago.comprobante_fiscal else None
    try:
        tasa = int(request.form.get('tasa_iva', ''))
    except ValueError:
        tasa = None
    comprobante, error = registrar(
        pago, request.form.get('numero'), request.form.get('timbrado'), request.form.get('ruc'),
        request.form.get('razon_social'), parse_iso_date(request.form.get('fecha')), tasa,
        id_usuario=current_user.id_usuario,
    )
    if error:
        db.session.rollback()
        flash(error, 'danger')
        return volver
    db.session.commit()
    registrar_auditoria('factura_gasto_corriente', 'gastos_corrientes',
                        f'Factura del pago #{pago.id_pago_gasto_corriente}: {anterior or "—"} → '
                        f'{comprobante.numero if comprobante else "—"}',
                        referencia_tipo='pago_gasto_corriente', referencia_id=pago.id_pago_gasto_corriente,
                        datos_anteriores={'numero': anterior},
                        datos_nuevos={'numero': comprobante.numero if comprobante else None})
    flash('Factura guardada: su IVA suma al crédito fiscal.' if comprobante else 'Factura quitada.', 'success')
    return volver
