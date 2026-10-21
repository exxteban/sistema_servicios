"""Cargar la nota de crédito en papel de una devolución, desde la venta."""
from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Devolucion
from app.routes.contador import contador_bp, puede_corregir_numero_factura
from app.services.notas_credito_papel import registrar
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.helpers import parse_iso_date


@contador_bp.route('/devolucion/<int:id>/nota-credito', methods=['POST'])
@login_required
def devolucion_nota_credito(id):
    if not puede_corregir_numero_factura(current_user):
        abort(403)
    devolucion = db.get_or_404(Devolucion, id)
    anterior = devolucion.nota_credito_papel.numero if devolucion.nota_credito_papel else None
    nota, error = registrar(
        devolucion, request.form.get('numero'), request.form.get('timbrado'),
        parse_iso_date(request.form.get('fecha')), id_usuario=current_user.id_usuario,
    )
    if error:
        db.session.rollback()
        flash(error, 'danger')
        return redirect(url_for('ventas.detalle', id=devolucion.id_venta))
    db.session.commit()
    registrar_auditoria('nota_credito_papel', 'ventas',
                        f'NC de la devolución #{devolucion.id_devolucion}: {anterior or "—"} → {nota.numero if nota else "—"}',
                        referencia_tipo='devolucion', referencia_id=devolucion.id_devolucion,
                        datos_anteriores={'numero': anterior},
                        datos_nuevos={'numero': nota.numero if nota else None})
    flash('Nota de crédito guardada.' if nota else 'Nota de crédito quitada.', 'success')
    return redirect(url_for('ventas.detalle', id=devolucion.id_venta))
