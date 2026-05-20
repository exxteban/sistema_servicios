from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import contains_eager

from app import db
from app.models import Categoria, Cliente, SesionCaja
from pedidos.models import PedidoCliente, PedidoClienteDetalle
from pedidos.schema import ESTADO_PEDIDO_PAGADO, ESTADOS_GESTIONABLES_SPRINT_1, ESTADOS_PEDIDO
from pedidos.services.pago_service import (
    TIPOS_PAGO_PEDIDO,
    listar_metodos_pago_activos,
)
from pedidos.services.entrega_service import confirmar_entrega_y_generar_venta
from pedidos.services.caja_queue_service import (
    obtener_o_crear_pendiente_cobro_pedido,
    obtener_pendiente_activo_pedido,
)
from pedidos.services.alta_service import (
    construir_resumen_inicial,
    crear_pedido_completo,
    extraer_items_iniciales_desde_form,
)
from pedidos.services.pedido_service import (
    actualizar_item_pedido,
    actualizar_pedido_base,
    agregar_item_pedido,
    buscar_productos_para_pedido,
    cambiar_estado_pedido,
    crear_pedido,
    eliminar_item_pedido,
    pedido_esta_bloqueado,
    reabrir_pedido,
)
from pedidos.services.ticket_service import build_pedido_ticket_context
from pedidos.services.mensaje_service import build_resumen_pedido_cliente
from pedidos.services.auditoria_service import (
    auditar_evento_pedido,
    item_snapshot,
    pedido_snapshot,
    venta_snapshot,
)


pedidos_bp = Blueprint(
    'pedidos',
    __name__,
    template_folder='templates',
)


def _puede_ver_pedidos() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('ver_clientes')


def _puede_editar_pedidos() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('editar_cliente') or current_user.tiene_permiso('crear_cliente')


def _resolver_denegacion(verbo: str = 'ver'):
    if verbo == 'ver' and _puede_ver_pedidos():
        return None
    if verbo == 'editar' and _puede_editar_pedidos():
        return None
    flash('No tienes permisos para acceder al modulo de pedidos.', 'danger')
    return redirect(url_for('main.dashboard'))


def _cargar_clientes():
    return Cliente.query.filter_by(activo=True).order_by(Cliente.nombre.asc()).all()


def _sesion_caja_activa_usuario():
    return SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()


def _categorias_producto_rapido():
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre.asc()).all()
    return [
        {
            'id_categoria': int(categoria.id_categoria),
            'nombre': str(categoria.nombre or '').strip(),
        }
        for categoria in categorias
    ]


def _puede_crear_producto_rapido() -> bool:
    return bool(current_user.tiene_permiso('crear_producto')) and not bool(getattr(current_user, 'modo_demo', False))


def _build_nuevo_pedido_context(items_iniciales: list[dict] | None = None):
    items_iniciales = items_iniciales or []
    productos_formulario = buscar_productos_para_pedido('', limit=15)
    productos_formulario_json = [
        {
            'id_producto': int(producto.id_producto),
            'codigo': producto.codigo or '',
            'nombre': producto.nombre or '',
            'precio_venta': float(producto.precio_venta or 0),
            'stock_disponible_pedidos': (
                int(producto.stock_disponible_pedidos)
                if getattr(producto, 'stock_disponible_pedidos', None) is not None else None
            ),
        }
        for producto in productos_formulario
    ]
    pago_inicial = request.form.get('monto_pago_inicial', '0') if request.method == 'POST' else '0'
    return {
        'pedido': None,
        'clientes': _cargar_clientes(),
        'productos_formulario_json': productos_formulario_json,
        'metodos_pago': listar_metodos_pago_activos(),
        'tipos_pago': TIPOS_PAGO_PEDIDO,
        'items_iniciales': items_iniciales,
        'resumen_inicial': construir_resumen_inicial(
            items=items_iniciales,
            descuento_monto=request.form.get('descuento_monto', '0'),
            pago_inicial=pago_inicial,
        ),
        'sesion_caja_activa': _sesion_caja_activa_usuario(),
    }


def _normalizar_destino_local(raw_destino: str, *, fallback: str = '') -> str:
    destino = (raw_destino or '').strip()
    if not destino:
        return fallback
    parsed = urlparse(destino)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not parsed.path.startswith('/') or parsed.path.startswith('//'):
        return fallback
    return destino


def _estados_para_detalle(pedido: PedidoCliente):
    estados = []
    for estado in ESTADOS_PEDIDO:
        if estado in ESTADOS_GESTIONABLES_SPRINT_1 or estado == pedido.estado:
            estados.append(estado)
    return estados


@pedidos_bp.route('/')
@login_required
def listar():
    denegacion = _resolver_denegacion('ver')
    if denegacion:
        return denegacion

    page = max(request.args.get('page', 1, type=int), 1)
    estado = (request.args.get('estado') or '').strip()
    q = (request.args.get('q') or '').strip()

    per_page = 20
    query = PedidoCliente.query.join(Cliente).options(contains_eager(PedidoCliente.cliente)).order_by(PedidoCliente.fecha_creacion.desc(), PedidoCliente.id_pedido.desc())
    if estado:
        query = query.filter(PedidoCliente.estado == estado)
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Cliente.nombre.ilike(like),
                PedidoCliente.numero_pedido.cast(db.String).ilike(like),
                PedidoCliente.observaciones.ilike(like),
            )
        )

    pedidos = query.paginate(page=page, per_page=per_page, error_out=False)
    listos_para_entregar = (
        PedidoCliente.query.join(Cliente)
        .filter(
            PedidoCliente.estado == ESTADO_PEDIDO_PAGADO,
            PedidoCliente.id_venta_generada.is_(None),
        )
        .order_by(PedidoCliente.fecha_modificacion.desc(), PedidoCliente.id_pedido.desc())
        .limit(5)
        .all()
    )
    return render_template(
        'pedidos/listar.html',
        pedidos=pedidos,
        q=q,
        estado=estado,
        estados=ESTADOS_GESTIONABLES_SPRINT_1,
        listos_para_entregar=listos_para_entregar,
    )


@pedidos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    items_iniciales = []
    if request.method == 'POST':
        try:
            items_iniciales = extraer_items_iniciales_desde_form(request.form)
            resultado = crear_pedido_completo(
                id_cliente=request.form.get('id_cliente', type=int),
                id_usuario=current_user.id_usuario,
                observaciones=request.form.get('observaciones', ''),
                descuento_monto=request.form.get('descuento_monto', '0'),
                items=items_iniciales,
                pago_inicial={
                    'monto': request.form.get('monto_pago_inicial', '0'),
                    'tipo_pago': request.form.get('tipo_pago_inicial', ''),
                    'id_metodo_pago': request.form.get('id_metodo_pago_inicial', type=int),
                    'referencia': request.form.get('referencia_pago_inicial', ''),
                    'observaciones': request.form.get('observaciones_pago_inicial', ''),
                },
                sesion_caja=_sesion_caja_activa_usuario(),
            )
            pedido = resultado['pedido']
            auditar_evento_pedido(
                accion='crear_pedido',
                descripcion=f'Creo el pedido {pedido.numero_pedido_display}.',
                pedido=pedido,
                datos_nuevos=pedido_snapshot(pedido),
            )
            db.session.commit()
            flash('Pedido creado correctamente.', 'success')
            return redirect(url_for('pedidos.detalle', id_pedido=pedido.id_pedido))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'warning')
        except Exception:
            db.session.rollback()
            flash('Ocurrio un error al crear el pedido.', 'danger')

    return render_template('pedidos/form.html', **_build_nuevo_pedido_context(items_iniciales=items_iniciales))


@pedidos_bp.route('/<int:id_pedido>/editar', methods=['GET', 'POST'])
@login_required
def editar(id_pedido: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    clientes = _cargar_clientes()
    if request.method == 'POST':
        try:
            snapshot_anterior = pedido_snapshot(pedido)
            actualizar_pedido_base(
                pedido,
                id_cliente=request.form.get('id_cliente', type=int),
                id_usuario=current_user.id_usuario,
                observaciones=request.form.get('observaciones', ''),
                descuento_monto=request.form.get('descuento_monto', '0'),
            )
            auditar_evento_pedido(
                accion='actualizar_pedido',
                descripcion=f'Actualizo los datos del pedido {pedido.numero_pedido_display}.',
                pedido=pedido,
                datos_anteriores=snapshot_anterior,
                datos_nuevos=pedido_snapshot(pedido),
            )
            db.session.commit()
            flash('Pedido actualizado correctamente.', 'success')
            return redirect(url_for('pedidos.detalle', id_pedido=pedido.id_pedido))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'warning')
        except Exception:
            db.session.rollback()
            flash('Ocurrio un error al actualizar el pedido.', 'danger')

    return render_template('pedidos/form.html', pedido=pedido, clientes=clientes)


@pedidos_bp.route('/<int:id_pedido>')
@login_required
def detalle(id_pedido: int):
    denegacion = _resolver_denegacion('ver')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    pagos_page = max(request.args.get('pagos_page', 1, type=int), 1)
    historial_page = max(request.args.get('historial_page', 1, type=int), 1)
    active_tab = request.args.get('tab') if request.args.get('tab') in {'registrar', 'pagos', 'historial'} else 'registrar'
    productos = buscar_productos_para_pedido(request.args.get('producto_q', ''), limit=25)
    pagos_paginados = pedido.pagos.filter_by(estado='activo').paginate(page=pagos_page, per_page=10, error_out=False)
    historial_paginado = pedido.historial.paginate(page=historial_page, per_page=10, error_out=False)
    return render_template(
        'pedidos/detalle.html',
        pedido=pedido,
        productos=productos,
        estados=_estados_para_detalle(pedido),
        bloqueado=pedido_esta_bloqueado(pedido),
        producto_q=request.args.get('producto_q', ''),
        metodos_pago=listar_metodos_pago_activos(),
        tipos_pago=TIPOS_PAGO_PEDIDO,
        pendiente_caja=obtener_pendiente_activo_pedido(int(pedido.id_pedido)),
        mensaje_cliente=build_resumen_pedido_cliente(pedido),
        pagos_paginados=pagos_paginados,
        historial_paginado=historial_paginado,
        active_tab=active_tab,
        puede_crear_producto_rapido=_puede_crear_producto_rapido(),
        categorias_producto_rapido=_categorias_producto_rapido(),
    )


@pedidos_bp.route('/<int:id_pedido>/ticket')
@login_required
def ticket_pedido(id_pedido: int):
    denegacion = _resolver_denegacion('ver')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    preview = request.args.get('preview') == '1'
    embedded = request.args.get('embedded') == '1'
    close_only = request.args.get('close_only') == '1'
    id_pago_destacado = request.args.get('id_pago_pedido', type=int)
    fallback = '' if preview or embedded else url_for('pedidos.detalle', id_pedido=int(id_pedido))
    return_to = _normalizar_destino_local(request.args.get('return_to') or '', fallback=fallback)
    contexto = build_pedido_ticket_context(
        pedido,
        preview=preview,
        embedded=embedded,
        return_to=return_to,
        id_pago_destacado=id_pago_destacado,
        close_only=close_only,
    )
    return render_template('pedidos/ticket.html', **contexto)


@pedidos_bp.route('/<int:id_pedido>/estado', methods=['POST'])
@login_required
def actualizar_estado(id_pedido: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    try:
        snapshot_anterior = pedido_snapshot(pedido)
        cambiar_estado_pedido(
            pedido,
            nuevo_estado=request.form.get('estado'),
            id_usuario=current_user.id_usuario,
        )
        auditar_evento_pedido(
            accion='cambiar_estado_pedido',
            descripcion=f'Cambio el estado del pedido {pedido.numero_pedido_display} a {pedido.estado_label}.',
            pedido=pedido,
            datos_anteriores=snapshot_anterior,
            datos_nuevos=pedido_snapshot(pedido),
        )
        db.session.commit()
        flash('Estado actualizado.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el estado del pedido.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))


@pedidos_bp.route('/<int:id_pedido>/reabrir', methods=['POST'])
@login_required
def reabrir(id_pedido: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    try:
        snapshot_anterior = pedido_snapshot(pedido)
        reabrir_pedido(
            pedido,
            id_usuario=current_user.id_usuario,
        )
        auditar_evento_pedido(
            accion='reabrir_pedido',
            descripcion=f'Reabrio el pedido {pedido.numero_pedido_display}.',
            pedido=pedido,
            datos_anteriores=snapshot_anterior,
            datos_nuevos=pedido_snapshot(pedido),
        )
        db.session.commit()
        flash('Pedido reabierto correctamente.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo reabrir el pedido.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))


@pedidos_bp.route('/<int:id_pedido>/items', methods=['POST'])
@login_required
def agregar_item(id_pedido: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    try:
        item = agregar_item_pedido(
            pedido,
            id_producto=request.form.get('id_producto', type=int),
            cantidad=request.form.get('cantidad', type=int),
            precio_unitario=request.form.get('precio_unitario'),
            observaciones=request.form.get('observaciones', ''),
            id_usuario=current_user.id_usuario,
        )
        auditar_evento_pedido(
            accion='agregar_item_pedido',
            descripcion=f'Agrego un item al pedido {pedido.numero_pedido_display}.',
            pedido=pedido,
            datos_nuevos={
                'pedido': pedido_snapshot(pedido),
                'item': item_snapshot(item),
            },
        )
        db.session.commit()
        flash('Item agregado al pedido.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo agregar el item.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))


@pedidos_bp.route('/<int:id_pedido>/items/<int:id_item>/actualizar', methods=['POST'])
@login_required
def actualizar_item(id_pedido: int, id_item: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    item = PedidoClienteDetalle.query.get_or_404(id_item)
    try:
        snapshot_anterior = item_snapshot(item)
        actualizar_item_pedido(
            pedido,
            item,
            cantidad=request.form.get('cantidad', type=int),
            precio_unitario=request.form.get('precio_unitario'),
            observaciones=request.form.get('observaciones', ''),
            id_usuario=current_user.id_usuario,
        )
        auditar_evento_pedido(
            accion='actualizar_item_pedido',
            descripcion=f'Actualizo un item del pedido {pedido.numero_pedido_display}.',
            pedido=pedido,
            datos_anteriores={'item': snapshot_anterior},
            datos_nuevos={
                'pedido': pedido_snapshot(pedido),
                'item': item_snapshot(item),
            },
        )
        db.session.commit()
        flash('Item actualizado.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el item.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))


@pedidos_bp.route('/<int:id_pedido>/items/<int:id_item>/eliminar', methods=['POST'])
@login_required
def eliminar_item(id_pedido: int, id_item: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    item = PedidoClienteDetalle.query.get_or_404(id_item)
    try:
        snapshot_item = item_snapshot(item)
        snapshot_pedido = pedido_snapshot(pedido)
        eliminar_item_pedido(
            pedido,
            item,
            id_usuario=current_user.id_usuario,
        )
        auditar_evento_pedido(
            accion='eliminar_item_pedido',
            descripcion=f'Elimino un item del pedido {pedido.numero_pedido_display}.',
            pedido=pedido,
            datos_anteriores={
                'pedido': snapshot_pedido,
                'item': snapshot_item,
            },
            datos_nuevos=pedido_snapshot(pedido),
        )
        db.session.commit()
        flash('Item eliminado.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo eliminar el item.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))


@pedidos_bp.route('/<int:id_pedido>/pagos', methods=['POST'])
@login_required
def registrar_pago(id_pedido: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    try:
        snapshot_anterior = pedido_snapshot(pedido)
        pendiente, creado = obtener_o_crear_pendiente_cobro_pedido(
            pedido,
            id_usuario_origen=int(current_user.id_usuario),
            datos_cobro={
                'tipo_pago': request.form.get('tipo_pago'),
                'id_metodo_pago': request.form.get('id_metodo_pago'),
                'monto': request.form.get('monto'),
                'referencia': request.form.get('referencia'),
                'observaciones': request.form.get('observaciones'),
            },
        )
        auditar_evento_pedido(
            accion='registrar_pago_pedido_manual',
            descripcion=f'Envio un cobro del pedido {pedido.numero_pedido_display} a caja.',
            pedido=pedido,
            datos_anteriores=snapshot_anterior,
            datos_nuevos={
                'pedido': pedido_snapshot(pedido),
                'cola_id': int(pendiente.id),
                'creado': bool(creado),
                'metadata': pendiente.get_metadata(),
            },
        )
        db.session.commit()
        flash('Cobro enviado a caja correctamente.', 'success')
        if current_user.es_admin() or current_user.tiene_permiso('tomar_cola_cobro'):
            sesion_activa = _sesion_caja_activa_usuario()
            if sesion_activa is not None:
                return redirect(url_for('pedidos_caja.pos_cobro_cola', cola_id=int(pendiente.id)))
            return redirect(url_for('caja.abrir'))
        if current_user.es_admin() or current_user.tiene_permiso('ver_cola_cobro') or current_user.tiene_permiso('ver_caja'):
            return redirect(url_for('caja.estado'))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo enviar el cobro del pedido a caja.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))


@pedidos_bp.route('/<int:id_pedido>/entregar', methods=['POST'])
@login_required
def confirmar_entrega(id_pedido: int):
    denegacion = _resolver_denegacion('editar')
    if denegacion:
        return denegacion

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    try:
        snapshot_anterior = pedido_snapshot(pedido)
        resultado = confirmar_entrega_y_generar_venta(
            pedido,
            id_usuario=current_user.id_usuario,
        )
        venta = resultado['venta']
        auditar_evento_pedido(
            accion='confirmar_entrega_pedido',
            descripcion=f'Confirmo la entrega del pedido {pedido.numero_pedido_display}.',
            pedido=pedido,
            datos_anteriores=snapshot_anterior,
            datos_nuevos={
                'pedido': pedido_snapshot(pedido),
                'venta': venta_snapshot(venta),
            },
        )
        db.session.commit()
        flash(f'Pedido entregado correctamente. Se genero la venta #{int(venta.id_venta)}.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    except Exception:
        db.session.rollback()
        flash('No se pudo confirmar la entrega del pedido.', 'danger')
    return redirect(url_for('pedidos.detalle', id_pedido=id_pedido))
