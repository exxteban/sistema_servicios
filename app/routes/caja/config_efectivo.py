"""
Rutas admin para configurar el "metodo de pago efectivo" canonico.

Permite al admin:
- Ver como se esta resolviendo hoy el metodo efectivo.
- Ver advertencias (config invalida, varios candidatos, etc.).
- Fijar explicitamente un `id_metodo_pago` en `Configuracion`.

Se consume desde el panel de gestion de cajas.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import MetodoPago
from app.routes.caja import caja_bp
from app.services.caja_metodos import (
    CLAVE_METODO_EFECTIVO_ID,
    DESC_METODO_EFECTIVO_ID,
    asegurar_metodo_efectivo_configurado,
    diagnostico_metodo_efectivo,
)
from app.models.configuracion import Configuracion
from app.utils.auditoria_utils import registrar_auditoria


@caja_bp.route('/config/metodo-efectivo', methods=['GET', 'POST'])
@login_required
def config_metodo_efectivo():
    if not current_user.es_admin() and not current_user.tiene_permiso('gestionar_cajas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar la caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    metodos_activos = (
        MetodoPago.query.filter_by(activo=True)
        .order_by(MetodoPago.orden_display.asc(), MetodoPago.nombre.asc())
        .all()
    )
    metodos_todos = (
        MetodoPago.query
        .order_by(MetodoPago.orden_display.asc(), MetodoPago.nombre.asc())
        .all()
    )

    if request.method == 'POST':
        raw_id = (request.form.get('id_metodo_pago') or '').strip()
        if raw_id == '' or raw_id == '0':
            nuevo_valor = ''
        else:
            try:
                id_seleccionado = int(raw_id)
            except ValueError:
                flash('Seleccione un metodo de pago valido.', 'warning')
                return redirect(url_for('caja.config_metodo_efectivo'))

            metodo = db.session.get(MetodoPago, id_seleccionado)
            if metodo is None:
                flash('El metodo de pago seleccionado no existe.', 'warning')
                return redirect(url_for('caja.config_metodo_efectivo'))
            if not bool(getattr(metodo, 'activo', True)):
                flash(
                    'El metodo seleccionado esta inactivo. Actívelo antes de usarlo como efectivo canonico.',
                    'warning',
                )
                return redirect(url_for('caja.config_metodo_efectivo'))
            nuevo_valor = str(int(metodo.id_metodo_pago))

        valor_previo = (Configuracion.obtener(CLAVE_METODO_EFECTIVO_ID, '') or '').strip()
        Configuracion.establecer(
            CLAVE_METODO_EFECTIVO_ID,
            nuevo_valor,
            DESC_METODO_EFECTIVO_ID,
        )

        try:
            registrar_auditoria(
                accion='configurar_metodo_efectivo',
                modulo='caja',
                descripcion='Actualizacion del metodo de pago efectivo canonico',
                referencia_tipo='configuracion',
                referencia_id=None,
                datos_anteriores={'id_metodo_pago': valor_previo or None},
                datos_nuevos={'id_metodo_pago': nuevo_valor or None},
            )
        except Exception:
            pass

        if nuevo_valor:
            flash(f'Metodo efectivo canonico actualizado a id {nuevo_valor}.', 'success')
        else:
            flash(
                'Metodo efectivo canonico limpiado. Se volvera a resolver por nombre.',
                'success',
            )
        return redirect(url_for('caja.config_metodo_efectivo'))

    asegurar_metodo_efectivo_configurado(solo_activos=True)
    diag = diagnostico_metodo_efectivo()
    id_preseleccionado = diag.get('id_configurado') or diag.get('metodo_resuelto_id')
    return render_template(
        'caja/config_metodo_efectivo.html',
        diagnostico=diag,
        metodos_activos=metodos_activos,
        metodos_todos=metodos_todos,
        id_configurado=diag.get('id_configurado'),
        id_preseleccionado=id_preseleccionado,
    )
