from __future__ import annotations

from flask import Blueprint, flash, jsonify, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from gastos_corrientes import CATEGORIAS_GASTO_CORRIENTE
from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente
from gastos_corrientes.services import (
    construir_panel_gastos_corrientes,
    generar_csv_panel_gastos_corrientes,
    generar_pdf_response_panel_gastos_corrientes,
    obtener_gasto_o_404,
    obtener_historial_pagos,
    obtener_recordatorios_gastos_corrientes,
    parse_decimal,
    parse_periodo,
    sincronizar_pagos_periodo,
)

gastos_corrientes_bp = Blueprint(
    'gastos_corrientes',
    __name__,
    template_folder='templates',
)


def _opciones_categorias() -> list[dict]:
    return [{'valor': valor, 'label': label} for valor, label in CATEGORIAS_GASTO_CORRIENTE]


def _resolver_denegacion(*permisos: str, mensaje: str | None = None):
    if current_user.es_admin() or all(current_user.tiene_permiso(permiso) for permiso in permisos):
        return None
    flash(mensaje or 'No tienes permisos para acceder a gastos corrientes.', 'danger')
    return redirect(url_for('main.dashboard'))


def _resolver_denegacion_api(permiso: str):
    if current_user.es_admin() or current_user.tiene_permiso(permiso):
        return None
    return jsonify({'error': 'forbidden', 'mensaje': 'No tienes permisos para acceder a gastos corrientes.'}), 403


def _parse_entero(raw_value: str | None, *, default: int, minimo: int, maximo: int) -> int:
    texto = (raw_value or '').strip()
    if not texto:
        return default
    try:
        numero = int(texto)
    except ValueError:
        return default
    return max(minimo, min(numero, maximo))


def _payload_gasto_desde_form() -> dict:
    return {
        'nombre': (request.form.get('nombre') or '').strip(),
        'categoria': (request.form.get('categoria') or 'otros').strip().lower() or 'otros',
        'descripcion': (request.form.get('descripcion') or '').strip() or None,
        'monto_estimado': parse_decimal(request.form.get('monto_estimado')),
        'dia_vencimiento': _parse_entero(
            request.form.get('dia_vencimiento'),
            default=1,
            minimo=1,
            maximo=31,
        ),
        'activo': bool(request.form.get('activo')),
        'requiere_caja_por_defecto': bool(request.form.get('requiere_caja_por_defecto')),
        'alerta_activa': bool(request.form.get('alerta_activa')),
        'dias_anticipacion_alerta': _parse_entero(
            request.form.get('dias_anticipacion_alerta'),
            default=3,
            minimo=0,
            maximo=60,
        ),
    }


def _render_form(gasto: GastoCorriente | None):
    return render_template(
        'gastos_corrientes/form.html',
        gasto=gasto,
        categorias=_opciones_categorias(),
    )


def _redirect_listado_contexto():
    params = {}
    for key in ('periodo', 'categoria', 'estado', 'tab'):
        value = (request.form.get(key) or request.args.get(key) or '').strip()
        if value:
            params[key] = value
    return redirect(url_for('gastos_corrientes.index', **params))


def _gasto_tiene_historial_bloqueante(gasto: GastoCorriente) -> bool:
    return gasto.pagos.filter(
        db.or_(
            PagoGastoCorriente.estado != 'pendiente',
            PagoGastoCorriente.fecha_pago.isnot(None),
            PagoGastoCorriente.monto_pagado > 0,
            PagoGastoCorriente.id_movimiento_caja.isnot(None),
            PagoGastoCorriente.id_movimiento_reversa.isnot(None),
        )
    ).count() > 0


@gastos_corrientes_bp.route('/')
@login_required
def index():
    denegacion = _resolver_denegacion('ver_gastos_corrientes')
    if denegacion:
        return denegacion

    panel = construir_panel_gastos_corrientes(
        periodo_raw=request.args.get('periodo'),
        categoria=request.args.get('categoria'),
        estado=request.args.get('estado'),
    )
    return render_template(
        'gastos_corrientes/index.html',
        panel=panel,
        categorias=_opciones_categorias(),
    )


@gastos_corrientes_bp.route('/exportar/csv')
@login_required
def exportar_csv():
    denegacion = _resolver_denegacion(
        'ver_gastos_corrientes',
        'ver_reportes_gastos_corrientes',
        mensaje='No tienes permisos para exportar reportes de gastos corrientes.',
    )
    if denegacion:
        return denegacion

    panel = construir_panel_gastos_corrientes(
        periodo_raw=request.args.get('periodo'),
        categoria=request.args.get('categoria'),
        estado=request.args.get('estado'),
    )
    response = make_response('\ufeff' + generar_csv_panel_gastos_corrientes(panel))
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = (
        f'attachment; filename="gastos_corrientes_{panel["periodo"]}.csv"'
    )
    return response


@gastos_corrientes_bp.route('/exportar/pdf')
@login_required
def exportar_pdf():
    denegacion = _resolver_denegacion(
        'ver_gastos_corrientes',
        'ver_reportes_gastos_corrientes',
        mensaje='No tienes permisos para exportar reportes de gastos corrientes.',
    )
    if denegacion:
        return denegacion

    panel = construir_panel_gastos_corrientes(
        periodo_raw=request.args.get('periodo'),
        categoria=request.args.get('categoria'),
        estado=request.args.get('estado'),
    )
    return generar_pdf_response_panel_gastos_corrientes(panel)


@gastos_corrientes_bp.route('/sincronizar-periodo', methods=['POST'])
@login_required
def sincronizar_periodo():
    denegacion = _resolver_denegacion('editar_gastos_corrientes')
    if denegacion:
        return denegacion

    periodo_anio, periodo_mes, periodo = parse_periodo(request.form.get('periodo'))
    resultado = sincronizar_pagos_periodo(periodo_anio=periodo_anio, periodo_mes=periodo_mes)
    flash(
        (
            f'Período {periodo} sincronizado. '
            f'Nuevos: {resultado["created"]} · Ajustados: {resultado["updated"]} · Sin cambios: {resultado["existing"]}.'
        ),
        'success',
    )
    return redirect(url_for('gastos_corrientes.index', periodo=periodo, categoria=request.form.get('categoria'), estado=request.form.get('estado')))


@gastos_corrientes_bp.route('/api/alertas/resumen')
@login_required
def resumen_alertas():
    denegacion = _resolver_denegacion_api('ver_gastos_corrientes')
    if denegacion:
        return denegacion

    resumen = obtener_recordatorios_gastos_corrientes(
        limit=request.args.get('limit', 20, type=int),
    )
    return jsonify(resumen)


@gastos_corrientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    denegacion = _resolver_denegacion('crear_gastos_corrientes')
    if denegacion:
        return denegacion

    if request.method == 'POST':
        payload = _payload_gasto_desde_form()
        if not payload['nombre'] or payload['monto_estimado'] is None or payload['monto_estimado'] <= 0:
            flash('Nombre y monto estimado son obligatorios.', 'warning')
            return _render_form(None)

        gasto = GastoCorriente(
            cliente_id=getattr(current_user, 'id_cliente', None) or None,
            nombre=payload['nombre'],
            categoria=payload['categoria'],
            descripcion=payload['descripcion'],
            monto_estimado=payload['monto_estimado'],
            dia_vencimiento=payload['dia_vencimiento'],
            activo=payload['activo'],
            requiere_caja_por_defecto=payload['requiere_caja_por_defecto'],
            alerta_activa=payload['alerta_activa'],
            dias_anticipacion_alerta=payload['dias_anticipacion_alerta'],
        )
        db.session.add(gasto)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_gasto_corriente',
                    modulo='gastos_corrientes',
                    descripcion=f'Creó gasto corriente "{gasto.nombre}"',
                    referencia_tipo='gasto_corriente',
                    referencia_id=gasto.id_gasto_corriente,
                    datos_nuevos={
                        'nombre': gasto.nombre,
                        'categoria': gasto.categoria,
                        'monto_estimado': str(gasto.monto_estimado),
                        'dia_vencimiento': gasto.dia_vencimiento_int(),
                        'activo': bool(gasto.activo),
                        'alerta_activa': bool(gasto.alerta_activa),
                    },
                    commit=False,
                )
        except Exception:
            pass

        db.session.commit()
        flash('Gasto corriente creado correctamente.', 'success')
        return redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=gasto.id_gasto_corriente))

    return _render_form(None)


@gastos_corrientes_bp.route('/<int:id_gasto_corriente>')
@login_required
def detalle(id_gasto_corriente: int):
    denegacion = _resolver_denegacion('ver_gastos_corrientes')
    if denegacion:
        return denegacion

    gasto = obtener_gasto_o_404(id_gasto_corriente)
    historial = obtener_historial_pagos(gasto)
    _, _, periodo = parse_periodo(request.args.get('periodo'))
    return render_template(
        'gastos_corrientes/detalle.html',
        gasto=gasto,
        historial=historial,
        periodo_actual=periodo,
    )


@gastos_corrientes_bp.route('/<int:id_gasto_corriente>/editar', methods=['GET', 'POST'])
@login_required
def editar(id_gasto_corriente: int):
    denegacion = _resolver_denegacion('editar_gastos_corrientes')
    if denegacion:
        return denegacion

    gasto = obtener_gasto_o_404(id_gasto_corriente)
    if request.method == 'POST':
        payload = _payload_gasto_desde_form()
        if not payload['nombre'] or payload['monto_estimado'] is None or payload['monto_estimado'] <= 0:
            flash('Nombre y monto estimado son obligatorios.', 'warning')
            return _render_form(gasto)

        datos_anteriores = {
            'nombre': gasto.nombre,
            'categoria': gasto.categoria,
            'monto_estimado': str(gasto.monto_estimado),
            'dia_vencimiento': gasto.dia_vencimiento_int(),
            'activo': bool(gasto.activo),
            'alerta_activa': bool(gasto.alerta_activa),
        }
        gasto.nombre = payload['nombre']
        gasto.categoria = payload['categoria']
        gasto.descripcion = payload['descripcion']
        gasto.monto_estimado = payload['monto_estimado']
        gasto.dia_vencimiento = payload['dia_vencimiento']
        gasto.activo = payload['activo']
        gasto.requiere_caja_por_defecto = payload['requiere_caja_por_defecto']
        gasto.alerta_activa = payload['alerta_activa']
        gasto.dias_anticipacion_alerta = payload['dias_anticipacion_alerta']

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='editar_gasto_corriente',
                    modulo='gastos_corrientes',
                    descripcion=f'Editó gasto corriente "{gasto.nombre}"',
                    referencia_tipo='gasto_corriente',
                    referencia_id=gasto.id_gasto_corriente,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos={
                        'nombre': gasto.nombre,
                        'categoria': gasto.categoria,
                        'monto_estimado': str(gasto.monto_estimado),
                        'dia_vencimiento': gasto.dia_vencimiento_int(),
                        'activo': bool(gasto.activo),
                        'alerta_activa': bool(gasto.alerta_activa),
                    },
                    commit=False,
                )
        except Exception:
            pass

        db.session.commit()
        flash('Gasto corriente actualizado.', 'success')
        return redirect(url_for('gastos_corrientes.detalle', id_gasto_corriente=gasto.id_gasto_corriente))

    return _render_form(gasto)


@gastos_corrientes_bp.route('/<int:id_gasto_corriente>/toggle', methods=['POST'])
@login_required
def toggle(id_gasto_corriente: int):
    denegacion = _resolver_denegacion('editar_gastos_corrientes')
    if denegacion:
        return denegacion

    gasto = obtener_gasto_o_404(id_gasto_corriente)
    estado_anterior = bool(gasto.activo)
    gasto.activo = not bool(gasto.activo)

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='activar_gasto_corriente' if gasto.activo else 'desactivar_gasto_corriente',
                modulo='gastos_corrientes',
                descripcion=f'{"Activó" if gasto.activo else "Desactivó"} gasto corriente "{gasto.nombre}"',
                referencia_tipo='gasto_corriente',
                referencia_id=gasto.id_gasto_corriente,
                datos_anteriores={'activo': estado_anterior},
                datos_nuevos={'activo': bool(gasto.activo)},
                commit=False,
            )
    except Exception:
        pass

    db.session.commit()
    flash(f'Gasto {"activado" if gasto.activo else "desactivado"} correctamente.', 'success')
    return redirect(request.form.get('next') or url_for('gastos_corrientes.index'))


@gastos_corrientes_bp.route('/<int:id_gasto_corriente>/eliminar', methods=['POST'])
@login_required
def eliminar(id_gasto_corriente: int):
    denegacion = _resolver_denegacion('editar_gastos_corrientes')
    if denegacion:
        return denegacion

    gasto = obtener_gasto_o_404(id_gasto_corriente)
    if _gasto_tiene_historial_bloqueante(gasto):
        flash(
            'No se puede eliminar este gasto porque ya tiene pagos o impacto operativo. '
            'Puedes desactivarlo para dejar de usarlo sin perder historial.',
            'warning',
        )
        return _redirect_listado_contexto()

    pagos_pendientes = gasto.pagos.count()
    datos_anteriores = {
        'nombre': gasto.nombre,
        'categoria': gasto.categoria,
        'monto_estimado': str(gasto.monto_estimado),
        'dia_vencimiento': gasto.dia_vencimiento_int(),
        'activo': bool(gasto.activo),
        'alerta_activa': bool(gasto.alerta_activa),
        'pagos_pendientes_eliminados': pagos_pendientes,
    }

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='eliminar_gasto_corriente',
                modulo='gastos_corrientes',
                descripcion=f'Eliminó gasto corriente "{gasto.nombre}"',
                referencia_tipo='gasto_corriente',
                referencia_id=gasto.id_gasto_corriente,
                datos_anteriores=datos_anteriores,
                commit=False,
            )
    except Exception:
        pass

    db.session.delete(gasto)
    db.session.commit()
    flash(
        (
            f'Gasto "{gasto.nombre}" eliminado correctamente.'
            if pagos_pendientes == 0
            else f'Gasto "{gasto.nombre}" eliminado junto con {pagos_pendientes} pendiente(s) automático(s).'
        ),
        'success',
    )
    return _redirect_listado_contexto()


from gastos_corrientes import routes_pagos as _routes_pagos  # noqa: F401,E402
