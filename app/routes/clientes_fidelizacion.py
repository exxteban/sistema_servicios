from sqlalchemy import or_

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Cliente, ClienteFidelizacionMovimiento
from app.services.clientes_fidelizacion import (
    BENEFICIO_TIPOS,
    MODOS_GENERACION,
    beneficio_resumen_config,
    beneficio_resumen_movimiento,
    beneficio_resumen_snapshot,
    canjear_beneficios_cliente,
    fidelizacion_config,
    guardar_fidelizacion_config,
    obtener_beneficios_pos_cliente,
    obtener_resumen_beneficios_cliente,
    sincronizar_beneficios_vencidos,
)
from app.services.clientes_fidelizacion_sincronizacion import sincronizar_compras_fidelizacion_pendientes


clientes_fidelizacion_bp = Blueprint('clientes_fidelizacion', __name__)


@clientes_fidelizacion_bp.route('/fidelizacion')
@login_required
def panel():
    if not _puede_configurar():
        flash('No tienes permisos para administrar la fidelizacion.', 'danger')
        return redirect(url_for('clientes.listar'))

    cambios = sincronizar_compras_fidelizacion_pendientes()
    cambios += sincronizar_beneficios_vencidos(resumen_builder=beneficio_resumen_snapshot)
    if cambios:
        db.session.commit()

    buscar_cliente = (request.args.get('buscar_cliente') or '').strip()
    movimientos = ClienteFidelizacionMovimiento.query.order_by(
        ClienteFidelizacionMovimiento.fecha_movimiento.desc(),
        ClienteFidelizacionMovimiento.id_movimiento.desc(),
    ).paginate(page=max(request.args.get('page', 1, type=int), 1), per_page=20, error_out=False)
    clientes_query = Cliente.query.filter(
        Cliente.id_cliente != 1,
        Cliente.activo.is_(True),
        or_(
            Cliente.fidelizacion_compras_acumuladas != 0,
            Cliente.fidelizacion_consumos_disponibles != 0,
            Cliente.fidelizacion_consumos_canjeados != 0,
        ),
    )
    if buscar_cliente:
        patron = f'%{buscar_cliente}%'
        clientes_query = clientes_query.filter(or_(
            Cliente.nombre.ilike(patron),
            Cliente.ruc_ci.ilike(patron),
            Cliente.telefono.ilike(patron),
        ))
    clientes_con_saldo = clientes_query.order_by(
        Cliente.fidelizacion_consumos_disponibles.desc(),
        Cliente.fidelizacion_compras_acumuladas.desc(),
        Cliente.nombre.asc(),
    ).paginate(page=max(request.args.get('clientes_page', 1, type=int), 1), per_page=20, error_out=False)
    return render_template(
        'clientes/fidelizacion.html',
        config_fidelizacion=fidelizacion_config(),
        beneficio_tipos=BENEFICIO_TIPOS,
        modos_generacion=MODOS_GENERACION,
        beneficio_resumen_config=beneficio_resumen_config,
        beneficio_resumen_movimiento=beneficio_resumen_movimiento,
        movimientos=movimientos,
        clientes_con_saldo=clientes_con_saldo,
        buscar_cliente=buscar_cliente,
        beneficios_por_cliente={
            int(cliente.id_cliente): obtener_resumen_beneficios_cliente(cliente.id_cliente)
            for cliente in clientes_con_saldo.items
        },
    )


@clientes_fidelizacion_bp.route('/fidelizacion/config', methods=['POST'])
@login_required
def guardar_configuracion():
    if not _puede_configurar():
        flash('No tienes permisos para administrar la fidelizacion.', 'danger')
        return redirect(url_for('clientes.listar'))

    guardar_fidelizacion_config(
        request.form.get('activa') == '1',
        request.form.get('compras_requeridas', 5, type=int),
        request.form.get('premios_por_objetivo', 1, type=int),
        request.form.get('compras_ventana_dias', 365, type=int),
        request.form.get('modo_generacion', 'acumulativo'),
        request.form.get('max_beneficios_activos', 0, type=int),
        request.form.get('max_beneficios_ventana', 0, type=int),
        request.form.get('beneficio_tipo', 'consumo_libre'),
        request.form.get('beneficio_valor', '0'),
        request.form.get('beneficio_vigencia_dias', 30, type=int),
        request.form.get('beneficio_descripcion', ''),
    )
    flash('Configuracion de fidelizacion actualizada.', 'success')
    return redirect(url_for('clientes_fidelizacion.panel'))


@clientes_fidelizacion_bp.route('/<int:id_cliente>/fidelizacion_json')
@login_required
def fidelizacion_json(id_cliente):
    if not (
        current_user.tiene_permiso('ver_clientes')
        or current_user.tiene_permiso('crear_venta')
    ):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'success': False, 'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'success': False, 'error': 'Sin permisos', 'modo_demo': False}), 403

    cambios = sincronizar_compras_fidelizacion_pendientes(id_cliente=id_cliente)
    cambios += sincronizar_beneficios_vencidos(id_cliente=id_cliente, resumen_builder=beneficio_resumen_snapshot)
    if cambios:
        db.session.commit()

    cliente = Cliente.query.get_or_404(id_cliente)
    resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)
    pos = obtener_beneficios_pos_cliente(cliente.id_cliente)
    return jsonify({
        'success': True,
        'cliente': {
            'id_cliente': int(cliente.id_cliente),
            'nombre': cliente.nombre,
        },
        'beneficios': resumen,
        'beneficios_pos': pos,
    })


@clientes_fidelizacion_bp.route('/<int:id_cliente>/fidelizacion/canjear', methods=['POST'])
@login_required
def canjear(id_cliente):
    destino = (request.form.get('next') or '').strip()
    if not destino.startswith('/'):
        destino = url_for('clientes.detalle', id=id_cliente)

    if not _puede_configurar():
        flash('No tienes permisos para canjear fidelizacion.', 'danger')
        return redirect(destino)

    try:
        cantidad = request.form.get('cantidad', 1, type=int)
        descripcion = (request.form.get('descripcion') or '').strip()
        resultado = canjear_beneficios_cliente(
            id_cliente,
            cantidad,
            id_usuario=getattr(current_user, 'id_usuario', None),
            descripcion=descripcion,
        )
        db.session.commit()
        resumen = ', '.join(
            f'{item["cantidad"]} x {item["resumen"]}'
            for item in resultado['beneficios_canjeados_resumen']
        )
        flash(
            (
                f'Canje registrado{": " + resumen if resumen else ""}. '
                f'Quedan {resultado["beneficios_disponibles"]} beneficio(s) disponibles.'
            ),
            'success',
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo registrar el canje de fidelizacion.', 'danger')
    return redirect(destino)


def _puede_configurar():
    return (
        current_user.is_authenticated
        and not getattr(current_user, 'modo_demo', False)
        and current_user.tiene_permiso('editar_cliente')
    )
