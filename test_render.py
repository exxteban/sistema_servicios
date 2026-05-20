from app import create_app, db
from flask import render_template
from types import SimpleNamespace
from datetime import datetime
import json
import re

app = create_app()
with app.app_context():
    with app.test_request_context('/?partial=1'):
        try:
            print("Testing partial render...")
            render_template('base.html')
            print("Partial render OK")
        except Exception as e:
            print(f"Partial render FAILED: {e}")

    with app.test_request_context('/'):
        try:
            print("Testing full render...")
            render_template('base.html')
            print("Full render OK")
        except Exception as e:
            print(f"Full render FAILED: {e}")

    with app.test_request_context('/reparaciones/1/ticket'):
        try:
            print("Testing reparaciones ticket render...")
            reparacion = SimpleNamespace(
                id_reparacion=1,
                fecha_ingreso=datetime.utcnow(),
                estado='en_proceso',
                tipo_equipo='Celular',
                marca_modelo='Modelo Test',
                imei_serie='',
                falla_reportada='No enciende',
                accesorios='Cargador',
                cliente=SimpleNamespace(nombre='Cliente Test')
            )
            render_template(
                'reparaciones/ticket.html',
                reparacion=reparacion,
                qr_svg=None,
                seguimiento_url=None
            )
            print("Reparaciones ticket render OK")
        except Exception as e:
            print(f"Reparaciones ticket render FAILED: {e}")

    with app.test_request_context('/ventas/1/ticket?preview=1'):
        try:
            print("Testing ticket render...")
            venta = SimpleNamespace(
                id_venta=1,
                fecha_venta=datetime.utcnow(),
                total=28000,
                cliente=SimpleNamespace(nombre='CONSUMIDOR FINAL')
            )
            producto = SimpleNamespace(nombre='Mate de Calabaza Natural')
            detalles = [
                SimpleNamespace(producto=producto, precio_unitario=28000, subtotal=28000, cantidad=1)
            ]
            pagos = [
                SimpleNamespace(metodo=SimpleNamespace(nombre='Efectivo'), monto=28000, referencia='')
            ]
            empresa = {'nombre': 'Mi Negocio', 'ruc': '00000000-0', 'direccion': '', 'telefono': ''}
            render_template(
                'ventas/ticket.html',
                venta=venta,
                detalles=detalles,
                pagos=pagos,
                pagos_resumen=[{'nombre': 'Efectivo', 'monto': 28000, 'referencias': []}],
                empresa=empresa,
                subtotal=28000,
                descuento=0,
                total_pagado=28000,
                vuelto=0,
                preview=True,
                moneda_simbolo='₲'
            )
            print("Ticket render OK")
        except Exception as e:
            print(f"Ticket render FAILED: {e}")

    with app.test_request_context('/ventas/pos'):
        try:
            print("Testing POS render...")
            sesion = SimpleNamespace(caja=SimpleNamespace(nombre='Caja 1'))
            clientes = []
            metodos_pago = [
                SimpleNamespace(id_metodo_pago=1, nombre='Efectivo', orden_display=1),
                SimpleNamespace(id_metodo_pago=2, nombre='QR / Billetera Digital', orden_display=2),
            ]
            empresa = {'nombre': 'Mi Negocio', 'ruc': '00000000-0', 'direccion': '', 'telefono': ''}
            render_template(
                'ventas/pos.html',
                sesion=sesion,
                clientes=clientes,
                metodos_pago=metodos_pago,
                empresa=empresa
            )
            print("POS render OK")
        except Exception as e:
            print(f"POS render FAILED: {e}")

app_test = create_app('testing')
with app_test.app_context():
    from app.models import Usuario, Cliente, Producto, Categoria, SesionCaja, Reparacion, DetalleReparacion, Venta, PagoVenta, MovimientoCaja

    admin = Usuario.query.filter_by(username='admin').first()
    cat = Categoria.query.first()
    prod = Producto(
        codigo='PTEST1',
        nombre='Producto Test',
        id_categoria=cat.id_categoria,
        precio_compra=0,
        precio_venta=100,
        precio_mayorista=80,
        porcentaje_iva=10,
        stock_actual=10,
        stock_minimo=0
    )
    cli_mayorista = Cliente(nombre='Cliente Mayorista', tipo='mayorista', ruc_ci='1', activo=True)
    cli_minorista = Cliente(nombre='Cliente Minorista', tipo='minorista', ruc_ci='2', activo=True)
    db.session.add_all([prod, cli_mayorista, cli_minorista])
    db.session.flush()

    ses = SesionCaja(id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta')
    db.session.add(ses)
    db.session.commit()

    client = app_test.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(admin.id_usuario)
        s['_fresh'] = True

    html = client.get('/ventas/pos').get_data(as_text=True) or ''
    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
    csrf_token = m.group(1) if m else None

    resp = client.post('/ventas/procesar', json={
        'items': [{'id_producto': prod.id_producto, 'cantidad': 1}],
        'pagos': [{'id_metodo_pago': 1, 'monto': 80}],
        'id_cliente': cli_mayorista.id_cliente,
        'descuento': 0,
        'client_request_id': 'test-mayorista-1'
    }, headers={'X-CSRFToken': csrf_token} if csrf_token else None)
    data = resp.get_json() or {}
    ok = (resp.status_code == 200 and data.get('success') is True and float(data.get('total') or 0) == 80.0)
    print("Testing POS mayorista price...", "OK" if ok else f"FAILED: {resp.status_code} {data}")

    resp = client.post('/ventas/procesar', json={
        'items': [{'id_producto': prod.id_producto, 'cantidad': 1}],
        'pagos': [{'id_metodo_pago': 1, 'monto': 80}],
        'id_cliente': cli_minorista.id_cliente,
        'forzar_precio_mayorista': True,
        'descuento': 0,
        'client_request_id': 'test-forzado-1'
    }, headers={'X-CSRFToken': csrf_token} if csrf_token else None)
    data = resp.get_json() or {}
    ok = (resp.status_code == 200 and data.get('success') is True and float(data.get('total') or 0) == 80.0)
    print("Testing POS forced mayorista price...", "OK" if ok else f"FAILED: {resp.status_code} {data}")

    venta_sin_mov = Venta(
        id_cliente=cli_minorista.id_cliente,
        id_sesion_caja=ses.id_sesion,
        subtotal=100,
        total=100,
        total_iva_10=0,
        total_iva_5=0,
        total_exenta=0,
    )
    db.session.add(venta_sin_mov)
    db.session.flush()
    db.session.add(PagoVenta(id_venta=venta_sin_mov.id_venta, id_metodo_pago=1, monto=100))
    db.session.commit()

    html_det = client.get(f'/ventas/{venta_sin_mov.id_venta}').get_data(as_text=True) or ''
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_det)
    csrf_anular = m.group(1) if m else None
    resp = client.post(
        f'/ventas/{venta_sin_mov.id_venta}/anular',
        data={'csrf_token': csrf_anular, 'id_autorizacion': ''},
        follow_redirects=False
    )
    mov = MovimientoCaja.query.filter_by(
        referencia_tipo='anulacion_venta',
        referencia_id=venta_sin_mov.id_venta,
        tipo='egreso',
    ).first()
    ok = (
        resp.status_code in (302, 303)
        and mov is not None
        and abs(float(mov.monto or 0) - 100.0) < 0.01
    )
    print("Testing anulación venta efectivo sin MovimientoCaja previo...", "OK" if ok else f"FAILED: {resp.status_code} mov={float(mov.monto or 0) if mov else None}")

    html = client.get('/reparaciones/nuevo').get_data(as_text=True) or ''
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    csrf_form = m.group(1) if m else None

    payload = {
        'csrf_token': csrf_form,
        'cliente_id': cli_minorista.id_cliente,
        'tipo_equipo': 'Celular',
        'marca_modelo': 'Modelo Test',
        'imei_serie': '',
        'password_patron': '',
        'falla_reportada': 'No enciende',
        'diagnostico_tecnico': '',
        'solucion': '',
        'costo_estimado': '0',
        'costo_final': '1000',
        'items_json': json.dumps([{
            'id_producto': prod.id_producto,
            'cantidad': 2,
            'incluye_costo_final': True
        }]),
        'accesorios': ['Cargador', 'Cable USB'],
        'accesorios_texto': 'Vidrio'
    }

    resp = client.post('/reparaciones/nuevo', data=payload, follow_redirects=False)
    created = Reparacion.query.order_by(Reparacion.id_reparacion.desc()).first()
    detalles = DetalleReparacion.query.filter_by(id_reparacion=created.id_reparacion).all() if created else []
    total_calc = float(created.costo_final_calculado or 0) if created else 0.0
    ok = (
        resp.status_code in (302, 303)
        and created is not None
        and float(created.costo_final or 0) == 1000.0
        and len(detalles) == 1
        and int(detalles[0].cantidad or 0) == 2
        and bool(detalles[0].incluye_costo_final) is True
        and abs(total_calc - 1200.0) < 0.01
        and ('cargador' in (created.accesorios or '').lower())
        and ('cable usb' in (created.accesorios or '').lower())
        and ('vidrio' in (created.accesorios or '').lower())
    )
    print("Testing Reparacion nuevo with items_json...", "OK" if ok else f"FAILED: {resp.status_code} total_calc={total_calc} detalles={len(detalles)}")

    if created:
        resp = client.post(
            f'/reparaciones/{created.id_reparacion}/costos',
            data={'csrf_token': csrf_form, 'costo_estimado': '50000', 'costo_final': '100000'},
            headers={'X-Requested-With': 'XMLHttpRequest'},
            follow_redirects=False
        )
        ok = (resp.status_code in (302, 303)) and (not resp.is_json)
        print("Testing Reparacion costos via tab-AJAX (should redirect HTML)...", "OK" if ok else f"FAILED: {resp.status_code} is_json={resp.is_json}")

    payload_sin_items = {
        'csrf_token': csrf_form,
        'cliente_id': cli_minorista.id_cliente,
        'tipo_equipo': 'Celular',
        'marca_modelo': 'Modelo Test 2',
        'imei_serie': '',
        'password_patron': '',
        'falla_reportada': 'No carga',
        'diagnostico_tecnico': '',
        'solucion': '',
        'costo_estimado': '0',
        'costo_final': '150000',
        'accesorios': ['Funda'],
        'accesorios_texto': 'Papel'
    }
    resp = client.post('/reparaciones/nuevo', data=payload_sin_items, follow_redirects=False)
    created2 = Reparacion.query.order_by(Reparacion.id_reparacion.desc()).first()
    detalles2 = DetalleReparacion.query.filter_by(id_reparacion=created2.id_reparacion).all() if created2 else []
    ok = (
        resp.status_code in (302, 303)
        and created2 is not None
        and float(created2.costo_final or 0) == 150000.0
        and len(detalles2) == 0
        and ('funda' in (created2.accesorios or '').lower())
        and ('papel' in (created2.accesorios or '').lower())
    )
    print("Testing Reparacion nuevo sin items (solo costo final)...", "OK" if ok else f"FAILED: {resp.status_code} detalles={len(detalles2)}")

    if created2:
        resp = client.post(
            f'/reparaciones/{created2.id_reparacion}/generar_venta',
            data={'csrf_token': csrf_form},
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
            follow_redirects=False
        )
        data = resp.get_json(silent=True) or {}
        ok = resp.status_code == 200 and data.get('success') is True and str(created2.id_reparacion) in str(data.get('redirect_url') or '')
        print("Testing Reparacion cobrar en POS sin items (solo costo final)...", "OK" if ok else f"FAILED: {resp.status_code} {data}")

        created2.estado = 'entregado'
        created2.fecha_entrega = datetime.utcnow()
        db.session.commit()

        resp = client.post('/ventas/procesar', json={
            'items': [{'id_producto': prod.id_producto, 'cantidad': 1}],
            'pagos': [{'id_metodo_pago': 1, 'monto': 100}],
            'id_cliente': cli_minorista.id_cliente,
            'descuento': 0,
            'reparacion_id': created2.id_reparacion,
            'client_request_id': f'test-reparacion-venta-{created2.id_reparacion}-1'
        }, headers={'X-CSRFToken': csrf_token} if csrf_token else None)
        data = resp.get_json(silent=True) or {}
        venta_rep_id = data.get('id_venta')
        ok = (resp.status_code == 200 and data.get('success') is True and bool(venta_rep_id))
        print("Testing Venta asociada a reparación...", "OK" if ok else f"FAILED: {resp.status_code} {data}")

        if venta_rep_id:
            html_det = client.get(f'/ventas/{venta_rep_id}').get_data(as_text=True) or ''
            m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_det)
            csrf_anular = m.group(1) if m else None
            resp_an = client.post(
                f'/ventas/{venta_rep_id}/anular',
                data={'csrf_token': csrf_anular, 'id_autorizacion': ''},
                follow_redirects=False
            )
            rep_db = Reparacion.query.get(created2.id_reparacion)
            ok = (
                resp_an.status_code in (302, 303)
                and rep_db is not None
                and (rep_db.estado or '').strip().lower() == 'listo'
                and rep_db.fecha_entrega is None
            )
            print("Testing Anulación venta reparación reabre reparación...", "OK" if ok else f"FAILED: {resp_an.status_code} estado={getattr(rep_db,'estado',None)} fecha_entrega={getattr(rep_db,'fecha_entrega',None)}")

            resp2 = client.post('/ventas/procesar', json={
                'items': [{'id_producto': prod.id_producto, 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': 1, 'monto': 100}],
                'id_cliente': cli_minorista.id_cliente,
                'descuento': 0,
                'reparacion_id': created2.id_reparacion,
                'client_request_id': f'test-reparacion-venta-{created2.id_reparacion}-2'
            }, headers={'X-CSRFToken': csrf_token} if csrf_token else None)
            data2 = resp2.get_json(silent=True) or {}
            ok = (resp2.status_code == 200 and data2.get('success') is True and bool(data2.get('id_venta')))
            print("Testing Re-cobro de reparación tras anulación...", "OK" if ok else f"FAILED: {resp2.status_code} {data2}")

        html_edit = client.get(f'/reparaciones/{created2.id_reparacion}/editar').get_data(as_text=True) or ''
        tiene_data_permiso = re.search(r'id="btn-submit-reparacion"[^>]*\sdata-permiso=', html_edit) is not None
        solucion_tiene_form = re.search(r'<textarea[^>]*name="solucion"[^>]*\sform="form-reparacion"', html_edit) is not None
        costo_estimado_tiene_form = re.search(r'<input[^>]*name="costo_estimado"[^>]*\sform="form-reparacion"', html_edit) is not None
        costo_final_tiene_form = re.search(r'<input[^>]*name="costo_final"[^>]*\sform="form-reparacion"', html_edit) is not None
        accesorios_checks_tienen_form = re.search(r'<input[^>]*type="checkbox"[^>]*name="accesorios"[^>]*\sform="form-reparacion"', html_edit) is not None
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_edit)
        csrf_edit = m.group(1) if m else None
        nuevo_texto = 'Solución actualizada desde test'
        resp = client.post(
            f'/reparaciones/{created2.id_reparacion}/editar',
            data={
                'csrf_token': csrf_edit,
                'cliente_id': created2.cliente_id,
                'tipo_equipo': created2.tipo_equipo or '',
                'marca_modelo': created2.marca_modelo or '',
                'imei_serie': created2.imei_serie or '',
                'password_patron': created2.password_patron or '',
                'falla_reportada': created2.falla_reportada or '',
                'diagnostico_tecnico': created2.diagnostico_tecnico or '',
                'solucion': nuevo_texto,
                'costo_estimado': str(created2.costo_estimado or 0),
                'costo_final': str(created2.costo_final or 0),
                'accesorios': ['SIM/Chip', 'Memoria SD'],
                'accesorios_texto': 'Pin',
            },
            follow_redirects=False
        )
        updated = Reparacion.query.get(created2.id_reparacion)
        ok = (
            resp.status_code in (302, 303)
            and (updated and (updated.solucion or '') == nuevo_texto)
            and ('sim/chip' in (updated.accesorios or '').lower())
            and ('memoria sd' in (updated.accesorios or '').lower())
            and ('pin' in (updated.accesorios or '').lower())
            and (not tiene_data_permiso)
            and solucion_tiene_form
            and costo_estimado_tiene_form
            and costo_final_tiene_form
            and accesorios_checks_tienen_form
        )
        print("Testing Reparacion editar y guardar cambios...", "OK" if ok else f"FAILED: {resp.status_code} data-permiso={tiene_data_permiso} form_solucion={solucion_tiene_form} form_costo_estimado={costo_estimado_tiene_form} form_costo_final={costo_final_tiene_form} solucion={(updated.solucion if updated else None)}")

        if updated:
            updated.estado = 'no_se_pudo'
            db.session.commit()
            html_list = client.get('/reparaciones/?q=no%20se%20pudo').get_data(as_text=True) or ''
            ok = re.search(r'panelNoSePudo[\s\S]*?#' + str(updated.id_reparacion) + r'\b', html_list) is not None
            print("Testing Reparaciones buscar por estado 'No se pudo'...", "OK" if ok else f"FAILED: id={updated.id_reparacion}")
