from io import BytesIO

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Cliente, PresupuestoEmpresarial
from app.services.presupuestos_empresariales import (
    PRESUPUESTO_CONDICIONES_DEFAULT,
    build_form_seed,
    company_payload,
    next_budget_number,
    payload_from_request,
    serialize_items_for_template,
)
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.pdf_runtime import import_pisa, is_arm_machine

presupuestos_empresariales_bp = Blueprint('presupuestos_empresariales', __name__)


def _puede_ver() -> bool:
    return current_user.tiene_permiso('ver_presupuestos_empresariales')


def _puede_crear() -> bool:
    return current_user.tiene_permiso('crear_presupuestos_empresariales')


def _forbidden(message: str, endpoint: str = 'main.dashboard'):
    if getattr(current_user, 'modo_demo', False):
        flash('Modo demo: esta acción está deshabilitada.', 'warning')
    else:
        flash(message, 'danger')
    return redirect(url_for(endpoint))


@presupuestos_empresariales_bp.route('/')
@login_required
def listar():
    if not _puede_ver():
        return _forbidden('No tienes permisos para ver presupuestos empresariales.')

    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()

    query = PresupuestoEmpresarial.query.outerjoin(
        Cliente,
        PresupuestoEmpresarial.id_cliente == Cliente.id_cliente,
    )
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                PresupuestoEmpresarial.numero_presupuesto.cast(db.String).ilike(like),
                PresupuestoEmpresarial.destinatario_nombre.ilike(like),
                PresupuestoEmpresarial.destinatario_ruc.ilike(like),
                PresupuestoEmpresarial.asunto.ilike(like),
                Cliente.nombre.ilike(like),
            )
        )

    presupuestos = query.order_by(
        PresupuestoEmpresarial.fecha_emision.desc(),
        PresupuestoEmpresarial.id_presupuesto_empresarial.desc(),
    ).paginate(page=page, per_page=12, error_out=False)

    return render_template(
        'presupuestos_empresariales/listar.html',
        presupuestos=presupuestos,
        q=q,
    )


@presupuestos_empresariales_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not _puede_crear():
        return _forbidden(
            'No tienes permisos para crear presupuestos empresariales.',
            endpoint='presupuestos_empresariales.listar',
        )

    if request.method == 'POST':
        form_seed = build_form_seed(request.form)
        payload, errores = payload_from_request(request.form)

        cliente = None
        if payload['id_cliente']:
            cliente = Cliente.query.filter_by(id_cliente=payload['id_cliente'], activo=True).first()
            if not cliente:
                payload['id_cliente'] = None

        if errores:
            for error in errores:
                flash(error, 'warning')
            return render_template(
                'presupuestos_empresariales/form.html',
                numero_preview=next_budget_number(),
                form_seed=form_seed,
                condiciones_default=PRESUPUESTO_CONDICIONES_DEFAULT,
            )

        presupuesto = PresupuestoEmpresarial(
            numero_presupuesto=next_budget_number(),
            fecha_emision=payload['fecha_emision'],
            validez_dias=payload['validez_dias'],
            id_usuario=current_user.id_usuario,
            id_cliente=cliente.id_cliente if cliente else None,
            destinatario_nombre=payload['destinatario_nombre'],
            destinatario_contacto=payload['destinatario_contacto'],
            destinatario_ruc=payload['destinatario_ruc'],
            destinatario_telefono=payload['destinatario_telefono'],
            destinatario_email=payload['destinatario_email'],
            destinatario_direccion=payload['destinatario_direccion'],
            asunto=payload['asunto'],
            moneda='PYG',
            subtotal=payload['subtotal'],
            descuento=payload['descuento'],
            total=payload['total'],
            observaciones=payload['observaciones'],
            condiciones=payload['condiciones'],
        )
        presupuesto.set_items(payload['items'])

        try:
            db.session.add(presupuesto)
            db.session.flush()
            registrar_auditoria(
                accion='crear_presupuesto_empresarial',
                modulo='presupuestos_empresariales',
                descripcion=f'Creó presupuesto empresarial {presupuesto.numero_presupuesto_display}',
                referencia_tipo='presupuesto_empresarial',
                referencia_id=presupuesto.id_presupuesto_empresarial,
                datos_nuevos={
                    'numero_presupuesto': presupuesto.numero_presupuesto,
                    'destinatario_nombre': presupuesto.destinatario_nombre,
                    'total': float(presupuesto.total or 0),
                },
            )
            db.session.commit()
            flash(f'Presupuesto Nº {presupuesto.numero_presupuesto_display} generado correctamente.', 'success')
            return redirect(
                url_for(
                    'presupuestos_empresariales.detalle',
                    id_presupuesto=presupuesto.id_presupuesto_empresarial,
                )
            )
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al crear presupuesto empresarial')
            flash('Ocurrió un error al guardar el presupuesto. Intente nuevamente.', 'danger')
            return render_template(
                'presupuestos_empresariales/form.html',
                numero_preview=next_budget_number(),
                form_seed=form_seed,
                condiciones_default=PRESUPUESTO_CONDICIONES_DEFAULT,
            )

    return render_template(
        'presupuestos_empresariales/form.html',
        numero_preview=next_budget_number(),
        form_seed=build_form_seed(),
        condiciones_default=PRESUPUESTO_CONDICIONES_DEFAULT,
    )


@presupuestos_empresariales_bp.route('/<int:id_presupuesto>')
@login_required
def detalle(id_presupuesto: int):
    if not _puede_ver():
        return _forbidden('No tienes permisos para ver presupuestos empresariales.')

    presupuesto = PresupuestoEmpresarial.query.get_or_404(id_presupuesto)
    return render_template(
        'presupuestos_empresariales/detalle.html',
        presupuesto=presupuesto,
        items_json=serialize_items_for_template(presupuesto.items),
    )


@presupuestos_empresariales_bp.route('/<int:id_presupuesto>/pdf')
@login_required
def pdf(id_presupuesto: int):
    try:
        pisa = import_pisa()
    except Exception:
        if not is_arm_machine():
            raise
        flash('La generacion de PDF no esta disponible en este entorno.', 'warning')
        return redirect(
            url_for(
                'presupuestos_empresariales.detalle',
                id_presupuesto=id_presupuesto,
            )
        )

    if not _puede_ver():
        return _forbidden('No tienes permisos para exportar presupuestos empresariales.')

    presupuesto = PresupuestoEmpresarial.query.get_or_404(id_presupuesto)
    empresa = company_payload()

    html = render_template(
        'presupuestos_empresariales/pdf.html',
        presupuesto=presupuesto,
        empresa=empresa,
        logo_src=empresa['logo_pdf_src'],
    )

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer, encoding='UTF-8')

    if pisa_status.err:
        current_app.logger.error(
            'Error al generar PDF de presupuesto empresarial %s',
            presupuesto.id_presupuesto_empresarial,
        )
        flash('Error al generar el PDF del presupuesto.', 'danger')
        return redirect(
            url_for(
                'presupuestos_empresariales.detalle',
                id_presupuesto=presupuesto.id_presupuesto_empresarial,
            )
        )

    presupuesto.cantidad_impresiones = int(presupuesto.cantidad_impresiones or 0) + 1
    presupuesto.fecha_ultima_impresion = db.func.now()
    db.session.commit()

    pdf_buffer.seek(0)
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = (
        f'inline; filename=presupuesto_empresarial_{presupuesto.numero_presupuesto_display}.pdf'
    )
    return response
