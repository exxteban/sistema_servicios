from datetime import date, datetime
from io import BytesIO

from flask import flash, make_response, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.pdf_runtime import import_pisa, is_arm_machine
from control_de_empleados.models import Empleado, EmpleadoPago
from control_de_empleados.routes import (
    _aplicar_scope_cliente,
    _armar_resumen_empleado,
    _cliente_id_para_nuevo_registro,
    _obtener_configuracion_empresa_rrhh,
    _obtener_cliente_scope,
    _obtener_empleado_o_404,
    _parse_fecha,
    _resolver_denegacion,
    _tiene_permiso_control,
    control_empleados_bp,
)
from control_de_empleados.services.filtros import normalizar_periodo


@control_empleados_bp.route('/<int:id_empleado>/pagar', methods=['POST'])
@login_required
def registrar_pago(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    if empleado.pagos.filter_by(periodo=periodo).first():
        flash(f'El empleado ya tiene un pago registrado para el periodo {periodo}.', 'warning')
        return redirect(url_for('control_empleados.detalle', id_empleado=id_empleado, periodo=periodo))

    resumen = _armar_resumen_empleado(empleado, periodo)
    pago = EmpleadoPago(
        cliente_id=_cliente_id_para_nuevo_registro(empleado),
        id_empleado=empleado.id_empleado,
        periodo=periodo,
        fecha_pago=_parse_fecha(request.form.get('fecha_pago')) or date.today(),
        salario_base=resumen['salario_base'],
        total_extras=resumen['extras'],
        total_descuentos=resumen['descuentos'],
        total_pagado=resumen['total_estimado'],
        metodo_pago=(request.form.get('metodo_pago') or '').strip() or None,
        referencia=(request.form.get('referencia') or '').strip() or None,
        notas=(request.form.get('notas') or '').strip() or None,
    )
    db.session.add(pago)
    db.session.flush()

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='crear_pago_empleado',
                modulo='control_empleados',
                descripcion=f'Registró pago para "{empleado.nombre_completo}" en periodo {periodo}',
                referencia_tipo='empleado_pago',
                referencia_id=pago.id_pago,
                datos_nuevos={
                    'id_empleado': empleado.id_empleado,
                    'periodo': pago.periodo,
                    'total_pagado': str(pago.total_pagado),
                },
                commit=False,
            )
    except Exception:
        pass

    db.session.commit()
    flash(
        f'Pago de Gs. {pago.total_pagado_decimal():,.0f} registrado correctamente para el periodo {periodo}.'.replace(',', '.'),
        'success',
    )
    return redirect(url_for('control_empleados.detalle', id_empleado=id_empleado, periodo=periodo))


@control_empleados_bp.route('/pago/<int:id_pago>/recibo')
@login_required
def recibo_pago_pdf(id_pago: int):
    # Verificar permisos antes de intentar cargar la dependencia de PDF.
    denegacion = _resolver_denegacion('ver_control_empleados')
    if denegacion:
        return denegacion

    try:
        pisa = import_pisa()
    except Exception:
        if not is_arm_machine():
            raise
        flash('La generacion de PDF no esta disponible en este entorno.', 'warning')
        return redirect(url_for('control_empleados.index'))

    pago = _aplicar_scope_cliente(
        EmpleadoPago.query,
        EmpleadoPago,
    ).filter(
        EmpleadoPago.id_pago == id_pago,
    ).first_or_404()
    empleado = pago.empleado

    empresa = _obtener_configuracion_empresa_rrhh(_obtener_cliente_scope(empleado))

    html = render_template(
        'control_de_empleados/pdf_recibo.html',
        pago=pago,
        empleado=empleado,
        empresa_nombre=empresa['nombre'] or 'EMPRESA DEMO S.A.',
        empresa_ruc=empresa['ruc'] or '0000000-0',
        empresa_direccion=empresa['direccion'] or 'Dirección no configurada',
        fecha_impresion=datetime.now(),
    )

    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer, encoding='UTF-8')
    if status.err:
        flash('Error al generar el PDF del recibo.', 'danger')
        return redirect(url_for('control_empleados.historial_pagos', id_empleado=empleado.id_empleado))

    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="Recibo_{empleado.nombre_completo}_{pago.periodo}.pdf"'
    return response


@control_empleados_bp.route('/<int:id_empleado>/historial-pagos')
@login_required
def historial_pagos(id_empleado: int):
    denegacion = _resolver_denegacion('ver_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    page = request.args.get('page', 1, type=int)
    paginacion = empleado.pagos.order_by(
        EmpleadoPago.fecha_pago.desc(),
        EmpleadoPago.id_pago.desc(),
    ).paginate(page=page, per_page=10, error_out=False)
    return render_template(
        'control_de_empleados/historial_pagos.html',
        empleado=empleado,
        paginacion=paginacion,
        puede_gestionar=_tiene_permiso_control('gestionar_control_empleados'),
    )


@control_empleados_bp.route('/pago/<int:id_pago>/eliminar', methods=['POST'])
@login_required
def eliminar_pago(id_pago: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    pago = _aplicar_scope_cliente(
        EmpleadoPago.query,
        EmpleadoPago,
    ).filter(
        EmpleadoPago.id_pago == id_pago,
    ).first_or_404()
    empleado = pago.empleado
    periodo = normalizar_periodo(request.form.get('periodo') or pago.periodo)

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='eliminar_pago_empleado',
                modulo='control_empleados',
                descripcion=f'Eliminó pago de "{empleado.nombre_completo}" en periodo {pago.periodo}',
                referencia_tipo='empleado_pago',
                referencia_id=pago.id_pago,
                datos_anteriores={
                    'id_empleado': pago.id_empleado,
                    'periodo': pago.periodo,
                    'fecha_pago': pago.fecha_pago.isoformat(),
                    'total_pagado': str(pago.total_pagado),
                },
                commit=False,
            )
    except Exception:
        pass

    db.session.delete(pago)
    db.session.commit()
    flash('Pago eliminado correctamente.', 'success')

    if request.form.get('return_to') == 'detalle':
        return redirect(
            url_for(
                'control_empleados.detalle',
                id_empleado=empleado.id_empleado,
                periodo=periodo,
            )
        )
    return redirect(url_for('control_empleados.historial_pagos', id_empleado=empleado.id_empleado))
