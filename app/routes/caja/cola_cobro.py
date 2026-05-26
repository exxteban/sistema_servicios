from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import ColaCobro, SesionCaja
from app.routes.caja import caja_bp
from app.services.dashboard_servicios import obtener_resumen_cobros_pendientes_dashboard

VALID_QUEUE_TYPES = {'venta', 'reparacion', 'cobro_credito', 'pedido', 'gastronomia'}
VALID_QUEUE_STATES = {'pendiente', 'en_proceso'}
VALID_QUEUE_SCOPES = {'mias', 'disponibles'}


def puede_acceder_cola_cobro(usuario=None) -> bool:
    usuario = usuario or current_user
    return bool(
        usuario.es_admin()
        or usuario.tiene_permiso('ver_cola_cobro')
        or usuario.tiene_permiso('tomar_cola_cobro')
    )


def normalizar_filtros_cola_cobro(
    *,
    cola_tipo=None,
    cola_estado=None,
    cola_scope=None,
    default_estado='todas',
):
    tipo = (cola_tipo or 'todas').strip().lower()
    estado = (cola_estado or default_estado or 'todas').strip().lower()
    scope = (cola_scope or 'todas').strip().lower()
    return {
        'tipo': tipo if tipo in VALID_QUEUE_TYPES else 'todas',
        'estado': estado if estado in VALID_QUEUE_STATES else 'todas',
        'scope': scope if scope in VALID_QUEUE_SCOPES else 'todas',
    }


def construir_query_base_cola_cobro():
    return ColaCobro.query.filter(ColaCobro.estado.in_(['pendiente', 'en_proceso']))


def calcular_totales_cola_cobro(query_base=None):
    cola_base = (query_base or construir_query_base_cola_cobro()).all()
    return {
        'total': len(cola_base),
        'pendiente': sum(1 for item in cola_base if item.estado == 'pendiente'),
        'en_proceso': sum(1 for item in cola_base if item.estado == 'en_proceso'),
        'venta': sum(1 for item in cola_base if item.tipo_origen == 'venta'),
        'reparacion': sum(1 for item in cola_base if item.tipo_origen == 'reparacion'),
        'cobro_credito': sum(1 for item in cola_base if item.tipo_origen == 'cobro_credito'),
        'pedido': sum(1 for item in cola_base if item.tipo_origen == 'pedido'),
    }


def aplicar_filtros_cola_cobro(query, filtros, usuario=None):
    usuario = usuario or current_user
    if filtros['tipo'] in VALID_QUEUE_TYPES:
        query = query.filter(ColaCobro.tipo_origen == filtros['tipo'])
    if filtros['estado'] in VALID_QUEUE_STATES:
        query = query.filter(ColaCobro.estado == filtros['estado'])
    if filtros['scope'] == 'mias':
        query = query.filter(ColaCobro.id_usuario_destino == usuario.id_usuario)
    elif filtros['scope'] == 'disponibles':
        query = query.filter(ColaCobro.id_usuario_destino.is_(None))
    return query


def obtener_contexto_cola_cobro(*, usuario=None, limit=50, default_estado='todas'):
    usuario = usuario or current_user
    filtros = normalizar_filtros_cola_cobro(
        cola_tipo=request.args.get('cola_tipo', 'todas'),
        cola_estado=request.args.get('cola_estado', default_estado),
        cola_scope=request.args.get('cola_scope', 'todas'),
        default_estado=default_estado,
    )
    cola_base_query = construir_query_base_cola_cobro()
    cola_query = aplicar_filtros_cola_cobro(cola_base_query, filtros, usuario=usuario)
    cola_pendientes = (
        cola_query
        .order_by(ColaCobro.fecha_envio.asc())
        .limit(max(int(limit or 0), 1))
        .all()
    )
    return {
        'cola_pendientes': cola_pendientes,
        'cola_totales': calcular_totales_cola_cobro(cola_base_query),
        'cola_filtros': filtros,
    }


@caja_bp.route('/cobros-pendientes')
@login_required
def cobros_pendientes():
    if not puede_acceder_cola_cobro():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver los cobros pendientes.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta',
    ).first()
    if not sesion:
        return redirect(url_for('caja.abrir'))

    contexto_cola = obtener_contexto_cola_cobro(
        usuario=current_user,
        limit=100,
        default_estado='pendiente',
    )
    cobros_reales = obtener_resumen_cobros_pendientes_dashboard(limit=None)
    return render_template(
        'caja/cobros_pendientes.html',
        sesion=sesion,
        cola_realtime_activa=True,
        cola_force_activa=True,
        cobros_reales_items=cobros_reales['items'],
        cobros_reales_total_count=cobros_reales['total_count'],
        cobros_reales_total_monto=cobros_reales['total_monto'],
        puede_abrir_cobro_directo=bool(
            current_user.es_admin()
            or current_user.tiene_permiso('crear_venta')
            or current_user.tiene_permiso('tomar_cola_cobro')
        ),
        **contexto_cola,
    )
