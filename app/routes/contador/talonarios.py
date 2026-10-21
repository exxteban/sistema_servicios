"""Talonarios de factura en papel y corrección del número en una venta.

Todo esto es para instalaciones sin facturación electrónica: con SIFEN el
timbrado y la numeración los maneja `facturacion_electronica`, y estas
pantallas lo dicen en vez de mostrar formularios que no sirven.
"""
from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Devolucion, NotaCreditoPapel, TalonarioFactura, Venta
from app.routes.contador import contador_bp, puede_corregir_numero_factura, puede_gestionar_talonarios
from app.services.pos_numero_factura import facturacion_electronica_activa
from app.services.talonario_facturas import completar_venta, crear_talonario, siguiente, sugerencias
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.helpers import parse_iso_date, today_local


def _entero(nombre):
    try:
        return int((request.form.get(nombre) or '').strip())
    except ValueError:
        return None


@contador_bp.route('/talonarios', methods=['GET', 'POST'])
@login_required
def talonarios():
    if not puede_gestionar_talonarios(current_user):
        flash('No tenés permisos para configurar los talonarios de factura.', 'danger')
        return redirect(url_for('main.dashboard'))
    fe_activa = facturacion_electronica_activa()

    if request.method == 'POST' and not fe_activa:
        talonario, error = crear_talonario(
            request.form.get('timbrado'),
            parse_iso_date(request.form.get('vigencia_desde')),
            parse_iso_date(request.form.get('vigencia_hasta')),
            request.form.get('establecimiento'), request.form.get('punto_expedicion'),
            _entero('numero_desde'), _entero('numero_hasta'),
        )
        if error:
            flash(error, 'danger')
            return render_template('contador/talonarios.html', **_contexto(fe_activa, request.form))
        db.session.add(talonario)
        db.session.commit()
        registrar_auditoria('crear_talonario_factura', 'contador',
                            f'Talonario {talonario.prefijo} timbrado {talonario.timbrado}',
                            referencia_tipo='talonario_factura', referencia_id=talonario.id)
        flash('Talonario guardado. El POS ya ofrece el número siguiente.', 'success')
        return redirect(url_for('contador.talonarios'))

    return render_template('contador/talonarios.html', **_contexto(fe_activa, {}))


def _contexto(fe_activa, formulario):
    hoy = today_local()
    filas = []
    for t in TalonarioFactura.query.order_by(TalonarioFactura.activo.desc(),
                                             TalonarioFactura.vigencia_hasta.desc()).all():
        proximo = siguiente(t)
        filas.append({'t': t, 'siguiente': proximo, 'vencido': t.vigencia_hasta < hoy,
                      'dias_para_vencer': (t.vigencia_hasta - hoy).days})
    return {'fe_activa': fe_activa, 'filas': filas, 'form': formulario, 'hoy': hoy}


@contador_bp.route('/talonarios/<int:id>/activo', methods=['POST'])
@login_required
def talonario_activo(id):
    if not puede_gestionar_talonarios(current_user):
        abort(403)
    talonario = db.get_or_404(TalonarioFactura, id)
    talonario.activo = not talonario.activo
    db.session.commit()
    registrar_auditoria('cambiar_talonario_factura', 'contador',
                        f"Talonario {talonario.prefijo} {'activado' if talonario.activo else 'desactivado'}",
                        referencia_tipo='talonario_factura', referencia_id=talonario.id)
    return redirect(url_for('contador.talonarios'))


@contador_bp.route('/talonarios/siguiente')
@login_required
def talonario_siguiente():
    """Para el POS: el número que sigue en cada talonario vigente."""
    if not (current_user.es_admin() or current_user.tiene_permiso('crear_venta')):
        abort(403)
    if facturacion_electronica_activa():
        return jsonify({'sugerencias': []})
    return jsonify({'sugerencias': sugerencias()})


def _tiene_notas_credito(venta):
    return NotaCreditoPapel.query.join(Devolucion, Devolucion.id_devolucion == NotaCreditoPapel.id_devolucion) \
        .filter(Devolucion.id_venta == venta.id_venta).first() is not None


@contador_bp.route('/venta/<int:id>/numero-factura', methods=['POST'])
@login_required
def venta_numero_factura(id):
    """Cargar o corregir el número de la factura en papel de una venta ya hecha."""
    if not puede_corregir_numero_factura(current_user):
        abort(403)
    if facturacion_electronica_activa():
        abort(404)
    venta = db.get_or_404(Venta, id)
    nuevo = (request.form.get('numero_factura') or '').strip()
    if len(nuevo) > 80:
        flash('El número de factura es demasiado largo.', 'danger')
        return redirect(url_for('ventas.detalle', id=id))
    if not nuevo and _tiene_notas_credito(venta):
        # Sin número la venta sale del débito, pero su NC seguiría restando IVA.
        flash('La venta tiene notas de crédito cargadas: quitalas antes de quitar el número de factura.', 'danger')
        return redirect(url_for('ventas.detalle', id=id))
    anterior = {'numero_factura': venta.numero_factura, 'timbrado': venta.timbrado}
    venta.numero_factura = nuevo or None
    if venta.numero_factura:
        completar_venta(venta)
    else:
        venta.timbrado = None
    db.session.commit()
    registrar_auditoria('corregir_numero_factura', 'ventas',
                        f'Nº factura de la venta #{venta.id_venta}: {anterior["numero_factura"] or "—"} → {venta.numero_factura or "—"}',
                        referencia_tipo='venta', referencia_id=venta.id_venta, datos_anteriores=anterior,
                        datos_nuevos={'numero_factura': venta.numero_factura, 'timbrado': venta.timbrado})
    flash('Número de factura guardado.', 'success')
    return redirect(url_for('ventas.detalle', id=id))
