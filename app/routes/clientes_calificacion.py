from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import ClienteCalificacionHistorial, ClienteCalificacionRegla
from app.services.clientes_calificacion import (
    ACCIONES,
    METRICAS,
    METRICAS_CON_PERIODO,
    OPERADORES,
    aplicar_reglas_a_clientes,
    config_auto,
    ejecutar_auto_si_corresponde,
    guardar_config_auto,
)
from app.utils.helpers import local_strftime


clientes_calificacion_bp = Blueprint('clientes_calificacion', __name__)


@clientes_calificacion_bp.before_app_request
def recalificar_clientes_si_corresponde():
    path = request.path or ''
    if not path.startswith('/clientes') or path.startswith('/clientes/calificacion'):
        return
    if request.method != 'GET':
        return
    if not current_user.is_authenticated or getattr(current_user, 'modo_demo', False):
        return
    if not current_user.tiene_permiso('editar_cliente'):
        return
    try:
        ejecutar_auto_si_corresponde(id_usuario=getattr(current_user, 'id_usuario', None))
    except Exception:
        db.session.rollback()


@clientes_calificacion_bp.route('/calificacion')
@login_required
def panel():
    if not _puede_configurar():
        flash('No tienes permisos para configurar la calificacion de clientes.', 'danger')
        return redirect(url_for('clientes.listar'))

    historial_page = max(request.args.get('historial_page', 1, type=int), 1)
    historial_per_page = 15
    reglas = ClienteCalificacionRegla.query.order_by(
        ClienteCalificacionRegla.prioridad.asc(),
        ClienteCalificacionRegla.id_regla.asc(),
    ).all()
    historial = ClienteCalificacionHistorial.query.order_by(
        ClienteCalificacionHistorial.fecha_cambio.desc()
    ).paginate(page=historial_page, per_page=historial_per_page, error_out=False)
    return render_template(
        'clientes/calificacion.html',
        reglas=reglas,
        historial=historial,
        metricas=METRICAS,
        metricas_con_periodo=METRICAS_CON_PERIODO,
        operadores=OPERADORES,
        acciones=ACCIONES,
        config_auto=config_auto(),
        local_strftime=local_strftime,
    )


@clientes_calificacion_bp.route('/calificacion/config', methods=['POST'])
@login_required
def guardar_configuracion():
    if not _puede_configurar():
        flash('No tienes permisos para configurar la calificacion de clientes.', 'danger')
        return redirect(url_for('clientes.listar'))

    activa = request.form.get('auto_activa') == '1'
    intervalo = request.form.get('intervalo_horas', 24, type=int)
    guardar_config_auto(activa, intervalo)
    flash('Configuracion automatica actualizada.', 'success')
    return redirect(url_for('clientes_calificacion.panel'))


@clientes_calificacion_bp.route('/calificacion/reglas', methods=['POST'])
@login_required
def crear_regla():
    if not _puede_configurar():
        flash('No tienes permisos para crear reglas.', 'danger')
        return redirect(url_for('clientes.listar'))

    datos = _leer_regla_form()
    if datos['error']:
        flash(datos['error'], 'warning')
        return redirect(url_for('clientes_calificacion.panel'))

    regla = ClienteCalificacionRegla(**datos['payload'])
    db.session.add(regla)
    db.session.commit()
    flash(f'Regla "{regla.nombre}" creada correctamente.', 'success')
    return redirect(url_for('clientes_calificacion.panel'))


@clientes_calificacion_bp.route('/calificacion/reglas/<int:id_regla>/editar', methods=['POST'])
@login_required
def editar_regla(id_regla):
    if not _puede_configurar():
        flash('No tienes permisos para editar reglas.', 'danger')
        return redirect(url_for('clientes.listar'))

    regla = ClienteCalificacionRegla.query.get_or_404(id_regla)
    datos = _leer_regla_form()
    if datos['error']:
        flash(datos['error'], 'warning')
        return redirect(url_for('clientes_calificacion.panel'))

    for campo, valor in datos['payload'].items():
        setattr(regla, campo, valor)
    db.session.commit()
    flash(f'Regla "{regla.nombre}" actualizada correctamente.', 'success')
    return redirect(url_for('clientes_calificacion.panel'))


@clientes_calificacion_bp.route('/calificacion/reglas/<int:id_regla>/toggle', methods=['POST'])
@login_required
def alternar_regla(id_regla):
    if not _puede_configurar():
        flash('No tienes permisos para modificar reglas.', 'danger')
        return redirect(url_for('clientes.listar'))

    regla = ClienteCalificacionRegla.query.get_or_404(id_regla)
    regla.activa = not bool(regla.activa)
    db.session.commit()
    estado = 'activada' if regla.activa else 'pausada'
    flash(f'Regla "{regla.nombre}" {estado}.', 'success')
    return redirect(url_for('clientes_calificacion.panel'))


@clientes_calificacion_bp.route('/calificacion/reglas/<int:id_regla>/eliminar', methods=['POST'])
@login_required
def eliminar_regla(id_regla):
    if not _puede_configurar():
        flash('No tienes permisos para eliminar reglas.', 'danger')
        return redirect(url_for('clientes.listar'))

    regla = ClienteCalificacionRegla.query.get_or_404(id_regla)
    nombre = regla.nombre
    db.session.delete(regla)
    db.session.commit()
    flash(f'Regla "{nombre}" eliminada.', 'success')
    return redirect(url_for('clientes_calificacion.panel'))


@clientes_calificacion_bp.route('/calificacion/aplicar', methods=['POST'])
@login_required
def aplicar_reglas():
    if not _puede_configurar():
        flash('No tienes permisos para aplicar reglas.', 'danger')
        return redirect(url_for('clientes.listar'))

    resultado = aplicar_reglas_a_clientes(id_usuario=getattr(current_user, 'id_usuario', None))
    flash(
        f'Se evaluaron {resultado["evaluados"]} clientes y se actualizaron '
        f'{resultado["actualizados"]}.',
        'success',
    )
    return redirect(url_for('clientes_calificacion.panel'))


def _puede_configurar():
    return (
        current_user.is_authenticated
        and not getattr(current_user, 'modo_demo', False)
        and current_user.tiene_permiso('editar_cliente')
    )


def _leer_regla_form():
    nombre = (request.form.get('nombre') or '').strip()
    metrica = (request.form.get('metrica') or '').strip()
    operador = (request.form.get('operador') or '').strip()
    accion = (request.form.get('accion') or '').strip()

    if not nombre:
        return _error('El nombre de la regla es obligatorio.')
    if metrica not in METRICAS:
        return _error('La metrica seleccionada no es valida.')
    if operador not in OPERADORES:
        return _error('El operador seleccionado no es valido.')
    if accion not in ACCIONES:
        return _error('La accion seleccionada no es valida.')

    valor = _decimal_form('valor', Decimal('0'))
    periodo_dias = _int_form('periodo_dias', 0)
    estrellas = max(1, min(5, _int_form('estrellas', 3)))
    prioridad = max(1, _int_form('prioridad', 100))
    reaplicar = max(0, _int_form('reaplicar_cada_dias', 0))
    if accion in {'sumar', 'restar'} and reaplicar <= 0:
        reaplicar = 30

    payload = {
        'nombre': nombre,
        'metrica': metrica,
        'operador': operador,
        'valor': valor,
        'periodo_dias': periodo_dias if metrica in METRICAS_CON_PERIODO and periodo_dias > 0 else None,
        'accion': accion,
        'estrellas': estrellas,
        'prioridad': prioridad,
        'reaplicar_cada_dias': reaplicar,
        'activa': request.form.get('activa', '1') == '1',
    }
    return {'error': '', 'payload': payload}


def _decimal_form(nombre, default):
    raw = (request.form.get(nombre) or '').strip()
    if not raw:
        return default
    raw = raw.replace('.', '').replace(',', '.') if ',' in raw and '.' in raw else raw.replace(',', '.')
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return default


def _int_form(nombre, default):
    try:
        return int(request.form.get(nombre, default))
    except (TypeError, ValueError):
        return default


def _error(mensaje):
    return {'error': mensaje, 'payload': {}}
