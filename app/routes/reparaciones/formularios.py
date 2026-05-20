import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Cliente, DetalleReparacion, Producto, Reparacion
from app.models.reparacion_seguimiento import ReparacionHistorialEstado, ReparacionSeguimiento
from app.utils.seguimiento_utils import generar_token, hash_token

from .base import (
    _a_float_seguro,
    _get_reparacion_or_404_safe,
    _usuarios_vendedores_cajeros_activos,
    reparaciones_bp,
)


@reparaciones_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not current_user.tiene_permiso('crear_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para crear reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    vendedores_cajeros = _usuarios_vendedores_cajeros_activos()
    vendedor_preseleccionado_id = None
    if any(int(u.id_usuario) == int(current_user.id_usuario) for u in vendedores_cajeros):
        vendedor_preseleccionado_id = int(current_user.id_usuario)
    vendedores_ids = {int(u.id_usuario) for u in vendedores_cajeros}
    if request.method == 'POST':
        cliente_id_raw = (request.form.get('cliente_id') or '').strip()
        try:
            cliente_id = int(cliente_id_raw) if cliente_id_raw else None
        except Exception:
            cliente_id = None
        id_usuario_vendedor_raw = (request.form.get('id_usuario_vendedor') or '').strip()
        try:
            id_usuario_vendedor = int(id_usuario_vendedor_raw) if id_usuario_vendedor_raw else None
        except Exception:
            id_usuario_vendedor = None
        if not id_usuario_vendedor and vendedor_preseleccionado_id:
            id_usuario_vendedor = int(vendedor_preseleccionado_id)
        if not id_usuario_vendedor and vendedores_cajeros:
            id_usuario_vendedor = int(vendedores_cajeros[0].id_usuario)
        if not id_usuario_vendedor:
            id_usuario_vendedor = int(current_user.id_usuario)
        tipo_equipo = (request.form.get('tipo_equipo') or '').strip()
        marca_modelo = (request.form.get('marca_modelo') or '').strip()
        imei_serie = (request.form.get('imei_serie') or '').strip()
        password_patron = (request.form.get('password_patron') or '').strip()
        patron_dibujo = request.form.get('patron_dibujo')
        falla_reportada = (request.form.get('falla_reportada') or '').strip()
        diagnostico_tecnico = request.form.get('diagnostico_tecnico')
        solucion = request.form.get('solucion')
        costo_estimado = _a_float_seguro(request.form.get('costo_estimado'))
        costo_final = _a_float_seguro(request.form.get('costo_final'))
        abono = _a_float_seguro(request.form.get('abono'))
        nota_cliente = request.form.get('nota_cliente')
        mostrar_costo = 'mostrar_costo' in request.form
        fecha_estimada_str = request.form.get('fecha_estimada')
        fecha_estimada_hora_str = request.form.get('fecha_estimada_hora')

        fecha_estimada = None
        if fecha_estimada_str:
            try:
                fecha_estimada = datetime.strptime(fecha_estimada_str, '%Y-%m-%d')
            except ValueError:
                pass

        fecha_estimada_hora = None
        if fecha_estimada_hora_str:
            try:
                fecha_estimada_hora = datetime.strptime(fecha_estimada_hora_str, '%H:%M').time()
            except ValueError:
                pass

        items_json = request.form.get('items_json')
        accesorios = [a.strip() for a in request.form.getlist('accesorios') if (a or '').strip()]
        accesorios_texto = (request.form.get('accesorios_texto') or '').strip()
        accesorios_extra = [a.strip() for a in accesorios_texto.split(',') if a.strip()] if accesorios_texto else []
        accesorios_merge = []
        accesorios_seen = set()
        for a in accesorios + accesorios_extra:
            k = a.lower()
            if k in accesorios_seen:
                continue
            accesorios_seen.add(k)
            accesorios_merge.append(a)
        accesorios_str = ", ".join(accesorios_merge)

        clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
        reparacion_form = SimpleNamespace(
            cliente_id=cliente_id,
            id_usuario_vendedor=id_usuario_vendedor,
            tipo_equipo=tipo_equipo,
            marca_modelo=marca_modelo,
            imei_serie=imei_serie or None,
            password_patron=password_patron or None,
            patron_dibujo=patron_dibujo,
            accesorios=accesorios_str,
            falla_reportada=falla_reportada,
            diagnostico_tecnico=diagnostico_tecnico,
            solucion=solucion,
            costo_estimado=costo_estimado,
            costo_final=costo_final,
            abono=abono,
            nota_cliente=nota_cliente,
            mostrar_costo=mostrar_costo,
            fecha_estimada=fecha_estimada,
            fecha_estimada_hora=fecha_estimada_hora,
        )

        if not cliente_id:
            flash('Selecciona un cliente válido', 'danger')
            return render_template(
                'reparaciones/form.html',
                clientes=clientes,
                reparacion=reparacion_form,
                vendedores_cajeros=vendedores_cajeros,
                vendedor_preseleccionado_id=vendedor_preseleccionado_id
            )
        cliente = db.session.get(Cliente, cliente_id)
        if not cliente or not getattr(cliente, 'activo', True):
            flash('Cliente no encontrado o inactivo', 'danger')
            return render_template(
                'reparaciones/form.html',
                clientes=clientes,
                reparacion=reparacion_form,
                vendedores_cajeros=vendedores_cajeros,
                vendedor_preseleccionado_id=vendedor_preseleccionado_id
            )
        if vendedores_ids and int(id_usuario_vendedor) not in vendedores_ids:
            flash('Selecciona un vendedor/cajero válido', 'danger')
            return render_template(
                'reparaciones/form.html',
                clientes=clientes,
                reparacion=reparacion_form,
                vendedores_cajeros=vendedores_cajeros,
                vendedor_preseleccionado_id=vendedor_preseleccionado_id
            )
        if not tipo_equipo or not marca_modelo or not falla_reportada:
            flash('Completa los campos obligatorios', 'danger')
            return render_template(
                'reparaciones/form.html',
                clientes=clientes,
                reparacion=reparacion_form,
                vendedores_cajeros=vendedores_cajeros,
                vendedor_preseleccionado_id=vendedor_preseleccionado_id
            )

        try:
            ventana = datetime.utcnow() - timedelta(seconds=20)
            dup_q = Reparacion.query.filter(Reparacion.cliente_id == cliente_id)
            dup_q = dup_q.filter(Reparacion.tipo_equipo == tipo_equipo)
            dup_q = dup_q.filter(Reparacion.marca_modelo == marca_modelo)
            dup_q = dup_q.filter(Reparacion.falla_reportada == falla_reportada)
            dup_q = dup_q.filter(Reparacion.fecha_ingreso >= ventana)

            if imei_serie:
                dup_q = dup_q.filter(Reparacion.imei_serie == imei_serie)
            else:
                dup_q = dup_q.filter(db.or_(Reparacion.imei_serie == None, Reparacion.imei_serie == ''))

            if password_patron:
                dup_q = dup_q.filter(Reparacion.password_patron == password_patron)
            else:
                dup_q = dup_q.filter(db.or_(Reparacion.password_patron == None, Reparacion.password_patron == ''))

            if accesorios_str:
                dup_q = dup_q.filter(Reparacion.accesorios == accesorios_str)
            else:
                dup_q = dup_q.filter(db.or_(Reparacion.accesorios == None, Reparacion.accesorios == ''))

            dup = dup_q.order_by(Reparacion.id_reparacion.desc()).first()
            if dup:
                flash('Esta recepción ya fue registrada (posible doble envío).', 'warning')
                return redirect(url_for('reparaciones.detalle', id=dup.id_reparacion))
        except Exception:
            pass

        if not current_user.tiene_permiso('editar_reparacion'):
            diagnostico_tecnico = None
            solucion = None
            costo_final = 0
            abono = 0
            items_json = None

        if patron_dibujo:
            patron_dibujo = patron_dibujo.strip()
            if not patron_dibujo.lower().startswith('data:image/'):
                patron_dibujo = None
            elif len(patron_dibujo) > 50000:
                patron_dibujo = None

        try:
            reparacion = Reparacion(
                cliente_id=cliente_id,
                id_usuario_vendedor=id_usuario_vendedor,
                tipo_equipo=tipo_equipo,
                marca_modelo=marca_modelo,
                imei_serie=imei_serie or None,
                password_patron=password_patron or None,
                patron_dibujo=patron_dibujo,
                accesorios=accesorios_str,
                falla_reportada=falla_reportada,
                diagnostico_tecnico=diagnostico_tecnico,
                solucion=solucion,
                costo_estimado=costo_estimado,
                costo_final=costo_final,
                abono=abono,
                nota_cliente=nota_cliente,
                mostrar_costo=mostrar_costo,
                fecha_estimada=fecha_estimada,
                fecha_estimada_hora=fecha_estimada_hora,
                estado='pendiente',
                fecha_ingreso=datetime.utcnow()
            )

            db.session.add(reparacion)
            db.session.flush()

            token = generar_token()
            seguimiento = ReparacionSeguimiento(
                id_reparacion=reparacion.id_reparacion,
                token_hash=hash_token(token)
            )
            db.session.add(seguimiento)

            historial_inicial = ReparacionHistorialEstado(
                id_reparacion=reparacion.id_reparacion,
                estado_anterior=None,
                estado_nuevo='pendiente',
                nota='Equipo recepcionado'
            )
            db.session.add(historial_inicial)

            items = []
            if items_json:
                try:
                    items = json.loads(items_json)
                except Exception:
                    items = []

            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    id_producto = it.get('id_producto')
                    cantidad = it.get('cantidad', 1)
                    incluye = bool(it.get('incluye_costo_final', False))

                    try:
                        id_producto = int(id_producto)
                        cantidad = int(cantidad)
                    except Exception:
                        continue
                    if cantidad <= 0:
                        continue

                    producto = db.session.get(Producto, id_producto)
                    if not producto:
                        continue

                    detalle = DetalleReparacion(
                        id_reparacion=reparacion.id_reparacion,
                        id_producto=id_producto,
                        cantidad=cantidad,
                        precio_unitario=producto.precio_venta,
                        subtotal=producto.precio_venta * cantidad,
                        nombre_producto=producto.nombre,
                        es_servicio=producto.es_servicio,
                        incluye_costo_final=incluye,
                    )
                    db.session.add(detalle)

            db.session.commit()

            flash('Equipo recepcionado correctamente', 'success')
            return redirect(url_for('reparaciones.detalle', id=reparacion.id_reparacion, auto_print=1))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
            return render_template(
                'reparaciones/form.html',
                clientes=clientes,
                reparacion=reparacion_form,
                vendedores_cajeros=vendedores_cajeros,
                vendedor_preseleccionado_id=vendedor_preseleccionado_id
            )

    clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    return render_template(
        'reparaciones/form.html',
        clientes=clientes,
        vendedores_cajeros=vendedores_cajeros,
        vendedor_preseleccionado_id=vendedor_preseleccionado_id
    )


@reparaciones_bp.route('/<int:id>/costos', methods=['POST'])
@login_required
def actualizar_costos(id):
    if not current_user.tiene_permiso('editar_reparacion'):
        wants_json = bool(request.is_json) or ('application/json' in (request.headers.get('Accept') or ''))
        if wants_json:
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'No tienes permisos para editar reparaciones', 'modo_demo': False}), 403
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    reparacion = _get_reparacion_or_404_safe(id)

    reparacion.costo_estimado = _a_float_seguro(request.form.get('costo_estimado'))
    reparacion.costo_final = _a_float_seguro(request.form.get('costo_final'))
    reparacion.abono = _a_float_seguro(request.form.get('abono'))

    wants_json = bool(request.is_json) or ('application/json' in (request.headers.get('Accept') or ''))

    try:
        db.session.commit()
        if wants_json:
            return jsonify({
                'success': True,
                'costo_estimado': float(reparacion.costo_estimado or 0),
                'costo_final_base': float(reparacion.costo_final or 0),
                'costo_final_calculado': float(reparacion.costo_final_calculado or 0),
                'abono': float(reparacion.abono or 0),
                'saldo_pendiente': float(reparacion.saldo_pendiente or 0),
            })
        flash('Costos actualizados', 'success')
    except Exception as e:
        db.session.rollback()
        if wants_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('reparaciones.detalle', id=reparacion.id_reparacion))


@reparaciones_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    if not current_user.tiene_permiso('editar_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    reparacion = _get_reparacion_or_404_safe(id)
    vendedores_cajeros = _usuarios_vendedores_cajeros_activos()
    vendedores_ids = {int(u.id_usuario) for u in vendedores_cajeros}
    vendedor_preseleccionado_id = int(reparacion.id_usuario_vendedor) if reparacion.id_usuario_vendedor else None

    if request.method == 'POST':
        cliente_id_raw = (request.form.get('cliente_id') or '').strip()
        if cliente_id_raw:
            try:
                cliente_id = int(cliente_id_raw)
            except Exception:
                cliente_id = None
            if not cliente_id:
                flash('Cliente inválido', 'danger')
                return render_template(
                    'reparaciones/form.html',
                    reparacion=reparacion,
                    editar=True,
                    vendedores_cajeros=vendedores_cajeros,
                    vendedor_preseleccionado_id=vendedor_preseleccionado_id
                )
            cliente = db.session.get(Cliente, cliente_id)
            if not cliente or not getattr(cliente, 'activo', True):
                flash('Cliente no encontrado o inactivo', 'danger')
                return render_template(
                    'reparaciones/form.html',
                    reparacion=reparacion,
                    editar=True,
                    vendedores_cajeros=vendedores_cajeros,
                    vendedor_preseleccionado_id=vendedor_preseleccionado_id
                )
            reparacion.cliente_id = cliente_id
        id_usuario_vendedor_raw = (request.form.get('id_usuario_vendedor') or '').strip()
        if id_usuario_vendedor_raw:
            try:
                id_usuario_vendedor = int(id_usuario_vendedor_raw)
            except Exception:
                id_usuario_vendedor = None
            if not id_usuario_vendedor:
                flash('Vendedor/Cajero inválido', 'danger')
                return render_template(
                    'reparaciones/form.html',
                    reparacion=reparacion,
                    editar=True,
                    vendedores_cajeros=vendedores_cajeros,
                    vendedor_preseleccionado_id=vendedor_preseleccionado_id
                )
            if vendedores_ids and int(id_usuario_vendedor) not in vendedores_ids:
                flash('Selecciona un vendedor/cajero válido', 'danger')
                return render_template(
                    'reparaciones/form.html',
                    reparacion=reparacion,
                    editar=True,
                    vendedores_cajeros=vendedores_cajeros,
                    vendedor_preseleccionado_id=vendedor_preseleccionado_id
                )
            reparacion.id_usuario_vendedor = id_usuario_vendedor
        reparacion.tipo_equipo = request.form.get('tipo_equipo')
        reparacion.marca_modelo = request.form.get('marca_modelo')
        reparacion.imei_serie = request.form.get('imei_serie')
        reparacion.password_patron = request.form.get('password_patron')
        patron_dibujo = request.form.get('patron_dibujo')
        if patron_dibujo:
            patron_dibujo = patron_dibujo.strip()
            if patron_dibujo.lower().startswith('data:image/') and len(patron_dibujo) <= 50000:
                reparacion.patron_dibujo = patron_dibujo
        else:
            reparacion.patron_dibujo = None
        reparacion.falla_reportada = request.form.get('falla_reportada')
        reparacion.diagnostico_tecnico = request.form.get('diagnostico_tecnico')
        reparacion.solucion = request.form.get('solucion')
        reparacion.costo_estimado = _a_float_seguro(request.form.get('costo_estimado'))
        reparacion.costo_final = _a_float_seguro(request.form.get('costo_final'))
        reparacion.abono = _a_float_seguro(request.form.get('abono'))
        reparacion.nota_cliente = request.form.get('nota_cliente')
        reparacion.mostrar_costo = 'mostrar_costo' in request.form

        fecha_estimada_str = request.form.get('fecha_estimada')
        if fecha_estimada_str:
            try:
                reparacion.fecha_estimada = datetime.strptime(fecha_estimada_str, '%Y-%m-%d')
            except ValueError:
                reparacion.fecha_estimada = None
        else:
            reparacion.fecha_estimada = None

        fecha_estimada_hora_str = request.form.get('fecha_estimada_hora')
        if fecha_estimada_hora_str:
            try:
                reparacion.fecha_estimada_hora = datetime.strptime(fecha_estimada_hora_str, '%H:%M').time()
            except ValueError:
                reparacion.fecha_estimada_hora = None
        else:
            reparacion.fecha_estimada_hora = None

        accesorios = [a.strip() for a in request.form.getlist('accesorios') if (a or '').strip()]
        accesorios_texto = (request.form.get('accesorios_texto') or '').strip()
        accesorios_extra = [a.strip() for a in accesorios_texto.split(',') if a.strip()] if accesorios_texto else []
        accesorios_merge = []
        accesorios_seen = set()
        for a in accesorios + accesorios_extra:
            k = a.lower()
            if k in accesorios_seen:
                continue
            accesorios_seen.add(k)
            accesorios_merge.append(a)
        reparacion.accesorios = ", ".join(accesorios_merge)

        try:
            db.session.commit()
            flash('Reparación actualizada', 'success')
            return redirect(url_for('reparaciones.detalle', id=reparacion.id_reparacion))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template(
        'reparaciones/form.html',
        reparacion=reparacion,
        editar=True,
        vendedores_cajeros=vendedores_cajeros,
        vendedor_preseleccionado_id=vendedor_preseleccionado_id
    )
