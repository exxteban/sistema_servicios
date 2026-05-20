from __future__ import annotations

from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Configuracion
from app.utils.helpers import now_local
from flujo_caja import CLAVE_MODULO_FLUJO_CAJA
from flujo_caja.services import (
    aplicar_plantilla,
    construir_contexto,
    crear_movimiento,
    crear_plantilla,
    obtener_movimiento_o_404,
    obtener_o_crear_semana,
    obtener_plantilla_o_404,
    parse_decimal,
    parse_fecha,
    rango_semana,
)

flujo_caja_bp = Blueprint('flujo_caja', __name__, template_folder='templates')


def _modulo_activo() -> bool:
    return Configuracion.obtener_bool(CLAVE_MODULO_FLUJO_CAJA, default=True)


def _denegar(*permisos: str, mensaje: str | None = None):
    if not _modulo_activo():
        flash('El modulo de flujo de caja estimado esta desactivado.', 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.es_admin() or all(current_user.tiene_permiso(permiso) for permiso in permisos):
        return None
    flash(mensaje or 'No tienes permisos para acceder a flujo de caja proyectado.', 'danger')
    return redirect(url_for('main.dashboard'))


def _redirect_tab(tab: str = 'semana'):
    params = {'tab': tab}
    semana = (request.form.get('semana') or request.args.get('semana') or '').strip()
    if semana:
        params['semana'] = semana
    return redirect(url_for('flujo_caja.index', **params))


def _validar_tab_origen(default: str = 'movimientos') -> str:
    tab_origen = (request.form.get('tab') or request.args.get('tab') or default).strip().lower()
    if tab_origen not in {'semana', 'movimientos', 'historial', 'plantillas', 'comparativo'}:
        return default
    return tab_origen


def _bloquear_semana_cerrada(semana, *, tab: str = 'semana'):
    if semana.estado != 'cerrada':
        return None
    flash('La semana esta cerrada. Reabrila antes de modificar movimientos o configuracion.', 'warning')
    return redirect(url_for('flujo_caja.index', semana=semana.fecha_inicio.isoformat(), tab=tab))


@flujo_caja_bp.route('/')
@login_required
def index():
    denegacion = _denegar('ver_flujo_caja')
    if denegacion:
        return denegacion

    contexto = construir_contexto(request.args.get('semana'))
    return render_template(
        'flujo_caja/index.html',
        ctx=contexto,
        active_tab=(request.args.get('tab') or 'semana').strip().lower(),
    )


@flujo_caja_bp.route('/imprimir')
@login_required
def imprimir():
    denegacion = _denegar('ver_flujo_caja')
    if denegacion:
        return denegacion

    contexto = construir_contexto(request.args.get('semana'))
    return render_template(
        'flujo_caja/imprimir.html',
        ctx=contexto,
        fecha_generacion=now_local(),
        auto_pdf=(request.args.get('auto_pdf') or '').strip() == '1',
        auto_print=(request.args.get('auto_print') or '').strip() == '1',
    )


@flujo_caja_bp.route('/preparar-semana', methods=['POST'])
@login_required
def preparar_semana():
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    fecha_inicio, _fecha_fin = rango_semana(request.form.get('semana'))
    saldo = parse_decimal(request.form.get('saldo_inicial'), Decimal('0.00'))
    semana = obtener_o_crear_semana(fecha_inicio, saldo_inicial=saldo)
    bloqueo = _bloquear_semana_cerrada(semana)
    if bloqueo:
        db.session.rollback()
        return bloqueo
    semana.notas = (request.form.get('notas') or '').strip() or None
    semana.nombre = (request.form.get('nombre') or '').strip() or semana.nombre
    db.session.commit()
    flash('Semana preparada para proyectar caja.', 'success')
    return redirect(url_for('flujo_caja.index', semana=semana.fecha_inicio.isoformat(), tab='semana'))


@flujo_caja_bp.route('/movimientos', methods=['POST'])
@login_required
def agregar_movimiento():
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    fecha_inicio, _fecha_fin = rango_semana(request.form.get('semana'))
    semana = obtener_o_crear_semana(fecha_inicio)
    bloqueo = _bloquear_semana_cerrada(semana)
    if bloqueo:
        return bloqueo
    monto = parse_decimal(request.form.get('monto_estimado'), Decimal('0.00'))
    concepto = (request.form.get('concepto') or '').strip()
    if not concepto or monto <= 0:
        flash('Concepto y monto son obligatorios.', 'warning')
        return _redirect_tab('semana')

    crear_movimiento(
        semana,
        {
            'fecha': parse_fecha(request.form.get('fecha')) or semana.fecha_inicio,
            'tipo': request.form.get('tipo'),
            'categoria': request.form.get('categoria'),
            'concepto': concepto,
            'monto_estimado': monto,
            'estado': request.form.get('estado') or 'estimado',
            'notas': request.form.get('notas'),
        },
    )
    db.session.commit()
    flash('Movimiento proyectado agregado.', 'success')
    return redirect(url_for('flujo_caja.index', semana=semana.fecha_inicio.isoformat(), tab='semana'))


@flujo_caja_bp.route('/movimientos/<int:id_movimiento>/estado', methods=['POST'])
@login_required
def actualizar_estado_movimiento(id_movimiento: int):
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    movimiento = obtener_movimiento_o_404(id_movimiento)
    tab_origen = _validar_tab_origen()
    bloqueo = _bloquear_semana_cerrada(movimiento.semana, tab=tab_origen)
    if bloqueo:
        return bloqueo
    estado = (request.form.get('estado') or '').strip().lower()
    if estado in {'estimado', 'confirmado', 'realizado', 'cancelado'}:
        movimiento.estado = estado
    monto_real = parse_decimal(request.form.get('monto_real'))
    if movimiento.estado == 'realizado':
        # Solo se usa monto_real cuando el movimiento está realizado.
        movimiento.monto_real = monto_real if monto_real is not None else movimiento.monto_estimado
    else:
        # Si el estado vuelve a estimado/confirmado/cancelado, limpiar monto_real
        # para evitar que un valor guardado previamente confunda al usuario
        # si luego vuelve a marcar como realizado.
        movimiento.monto_real = None
    db.session.commit()
    flash('Estado actualizado.', 'success')
    return redirect(url_for('flujo_caja.index', semana=movimiento.semana.fecha_inicio.isoformat(), tab=tab_origen))


@flujo_caja_bp.route('/movimientos/<int:id_movimiento>/eliminar', methods=['POST'])
@login_required
def eliminar_movimiento(id_movimiento: int):
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    movimiento = obtener_movimiento_o_404(id_movimiento)
    tab_origen = _validar_tab_origen()
    bloqueo = _bloquear_semana_cerrada(movimiento.semana, tab=tab_origen)
    if bloqueo:
        return bloqueo
    semana_inicio = movimiento.semana.fecha_inicio.isoformat()
    db.session.delete(movimiento)
    db.session.commit()
    flash('Movimiento eliminado.', 'success')
    return redirect(url_for('flujo_caja.index', semana=semana_inicio, tab=tab_origen))


@flujo_caja_bp.route('/plantillas', methods=['POST'])
@login_required
def agregar_plantilla():
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    monto = parse_decimal(request.form.get('monto_estimado'), Decimal('0.00'))
    nombre = (request.form.get('nombre') or '').strip()
    concepto = (request.form.get('concepto') or '').strip()
    if not nombre or not concepto or monto <= 0:
        flash('Nombre, concepto y monto de plantilla son obligatorios.', 'warning')
        return _redirect_tab('plantillas')

    crear_plantilla(
        {
            'nombre': nombre,
            'tipo': request.form.get('tipo'),
            'categoria': request.form.get('categoria'),
            'concepto': concepto,
            'monto_estimado': monto,
            'dia_semana': request.form.get('dia_semana'),
        }
    )
    db.session.commit()
    flash('Plantilla creada.', 'success')
    return _redirect_tab('plantillas')


@flujo_caja_bp.route('/plantillas/<int:id_plantilla>/aplicar', methods=['POST'])
@login_required
def aplicar_plantilla_route(id_plantilla: int):
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    fecha_inicio, _fecha_fin = rango_semana(request.form.get('semana'))
    semana = obtener_o_crear_semana(fecha_inicio)
    bloqueo = _bloquear_semana_cerrada(semana)
    if bloqueo:
        return bloqueo
    plantilla = obtener_plantilla_o_404(id_plantilla, solo_activas=True)
    aplicar_plantilla(semana, plantilla)
    db.session.commit()
    flash('Plantilla aplicada a la semana.', 'success')
    return redirect(url_for('flujo_caja.index', semana=semana.fecha_inicio.isoformat(), tab='semana'))


@flujo_caja_bp.route('/plantillas/<int:id_plantilla>/eliminar', methods=['POST'])
@login_required
def eliminar_plantilla(id_plantilla: int):
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    plantilla = obtener_plantilla_o_404(id_plantilla)
    plantilla.activa = False
    db.session.commit()
    flash('Plantilla archivada.', 'success')
    return _redirect_tab('plantillas')


@flujo_caja_bp.route('/semana/estado', methods=['POST'])
@login_required
def cambiar_estado_semana():
    denegacion = _denegar('gestionar_flujo_caja')
    if denegacion:
        return denegacion

    fecha_inicio, _fecha_fin = rango_semana(request.form.get('semana'))
    semana = obtener_o_crear_semana(fecha_inicio)
    estado = (request.form.get('estado') or '').strip().lower()
    if estado in {'abierta', 'cerrada'}:
        semana.estado = estado
    db.session.commit()
    flash('Estado de semana actualizado.', 'success')
    return redirect(url_for('flujo_caja.index', semana=semana.fecha_inicio.isoformat(), tab='historial'))
