import unittest
from datetime import UTC, datetime, timedelta

from app import create_app, db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class TestPedidosCaja(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, MetodoPago, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.cliente = db.session.get(Cliente, 1)
        if self.cliente is None:
            self.cliente = Cliente(nombre='Consumidor Final', tipo='minorista', activo=True)
            db.session.add(self.cliente)
            db.session.commit()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=500000,
            estado='abierta',
        )
        db.session.add(self.sesion)
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _crear_producto_simple(self, codigo='TEST-PED-001', precio=50000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Pedidos').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Pedidos', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=20000,
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=20,
            stock_minimo=1,
            es_servicio=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto

    def _crear_pedido(self, codigo='TEST-PED-001', precio=50000):
        from pedidos.models import PedidoCliente
        from pedidos.services.pedido_service import agregar_item_pedido, crear_pedido

        producto = self._crear_producto_simple(codigo=codigo, precio=precio)
        pedido = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Pedido de prueba caja',
        )
        db.session.flush()
        agregar_item_pedido(
            pedido,
            id_producto=int(producto.id_producto),
            cantidad=1,
            precio_unitario=precio,
            id_usuario=int(self.admin.id_usuario),
        )
        db.session.commit()
        return db.session.get(PedidoCliente, int(pedido.id_pedido))

    def test_sprint1_crear_pedido_borrador_y_editar_items_recalcula_totales(self):
        from pedidos.models import PedidoCliente
        from pedidos.services.pedido_service import actualizar_item_pedido, agregar_item_pedido, crear_pedido

        producto = self._crear_producto_simple(codigo='TEST-PED-SP1-001', precio=40000)
        pedido = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Sprint 1 alta manual',
        )
        db.session.flush()

        self.assertEqual((pedido.estado or '').strip(), 'borrador')
        self.assertAlmostEqual(float(pedido.total or 0), 0.0)
        self.assertAlmostEqual(float(pedido.saldo_pendiente or 0), 0.0)

        agregar_item_pedido(
            pedido,
            id_producto=int(producto.id_producto),
            cantidad=1,
            precio_unitario=40000,
            id_usuario=int(self.admin.id_usuario),
        )
        item = pedido.detalles.first()
        actualizar_item_pedido(
            pedido,
            item,
            cantidad=3,
            precio_unitario=45000,
            id_usuario=int(self.admin.id_usuario),
            observaciones='Cantidad ajustada',
        )
        db.session.commit()

        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual(pedido_actualizado.detalles.count(), 1)
        self.assertAlmostEqual(float(pedido_actualizado.total or 0), 135000.0)
        self.assertAlmostEqual(float(pedido_actualizado.saldo_pendiente or 0), 135000.0)

    def test_sprint2_pagos_parciales_acumulan_sin_crear_venta_ni_pago_venta(self):
        from app.models import PagoVenta, Venta
        from pedidos.models import PedidoCliente
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-SP2-001', precio=80000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=20000,
            tipo_pago='sena',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-SP2-SENA',
            sesion=self.sesion,
        )
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=15000,
            tipo_pago='pago_parcial',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-SP2-PARCIAL',
            sesion=self.sesion,
        )
        db.session.commit()

        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_actualizado.estado or '').strip(), 'pago_parcial')
        self.assertAlmostEqual(float(pedido_actualizado.total_pagado or 0), 35000.0)
        self.assertAlmostEqual(float(pedido_actualizado.saldo_pendiente or 0), 45000.0)
        self.assertEqual(Venta.query.count(), 0)
        self.assertEqual(PagoVenta.query.count(), 0)

    def test_sprint2_dos_pagos_parciales_acumulan_correctamente(self):
        from pedidos.models import PedidoCliente
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-SP2-002', precio=60000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=10000,
            tipo_pago='pago_parcial',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-SP2-P1',
            sesion=self.sesion,
        )
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=15000,
            tipo_pago='pago_parcial',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-SP2-P2',
            sesion=self.sesion,
        )
        db.session.commit()

        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_actualizado.estado or '').strip(), 'pago_parcial')
        self.assertAlmostEqual(float(pedido_actualizado.total_pagado or 0), 25000.0)
        self.assertAlmostEqual(float(pedido_actualizado.saldo_pendiente or 0), 35000.0)

    def test_sprint2_pago_total_anticipado_deja_pedido_pagado_sin_entregar(self):
        from pedidos.models import PedidoCliente
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-SP2-003', precio=75000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=75000,
            tipo_pago='pago_total',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-SP2-TOTAL',
            sesion=self.sesion,
        )
        db.session.commit()

        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_actualizado.estado or '').strip(), 'pagado')
        self.assertAlmostEqual(float(pedido_actualizado.saldo_pendiente or 0), 0.0)
        self.assertNotEqual((pedido_actualizado.estado or '').strip(), 'entregado')
        self.assertIsNone(pedido_actualizado.id_venta_generada)

    def test_api_pagos_detalle_incluye_cobros_de_pedidos_en_caja_estado(self):
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-DET-001', precio=54000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=54000,
            tipo_pago='pago_total',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-DET-001',
            sesion=self.sesion,
        )
        db.session.commit()

        response = self.client.get(f'/caja/api/pagos-detalle/{int(self.metodo_efectivo.id_metodo_pago)}')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(any((item.get('tipo_origen') or '') == 'pedido' for item in data))
        pago_pedido = next(item for item in data if (item.get('tipo_origen') or '') == 'pedido')
        self.assertEqual(pago_pedido.get('referencia_label'), pedido.numero_pedido_display)
        self.assertEqual(pago_pedido.get('cliente'), self.cliente.nombre)
        self.assertAlmostEqual(float(pago_pedido.get('monto') or 0), 54000.0)

    def test_enviar_pedido_a_caja_crea_pendiente_con_metadata(self):
        from app.models import ColaCobro

        pedido = self._crear_pedido(codigo='TEST-PED-COLA-001', precio=65000)

        response = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/pedidos/cola-cobro/', response.headers.get('Location') or '')
        self.assertIn('/pos', response.headers.get('Location') or '')
        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        self.assertIsNotNone(pendiente)
        self.assertAlmostEqual(float(pendiente.monto_total or 0), 65000.0)
        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['id_pedido']), int(pedido.id_pedido))
        self.assertEqual(metadata['numero_pedido'], pedido.numero_pedido_display)
        self.assertEqual(metadata['cliente_nombre'], self.cliente.nombre)
        self.assertAlmostEqual(float(metadata['saldo_pendiente'] or 0), 65000.0)

    def test_registrar_pago_redirige_directo_al_pos_de_caja(self):
        from app.models import ColaCobro

        pedido = self._crear_pedido(codigo='TEST-PED-COLA-002', precio=82000)

        response = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/pagos',
            data={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 82000,
                'tipo_pago': 'pago_total',
                'referencia': 'PED-COLA-002',
                'observaciones': 'Cobro para caja',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        self.assertIsNotNone(pendiente)
        location = response.headers.get('Location') or ''
        self.assertIn(f'/pedidos/cola-cobro/{int(pendiente.id)}/pos', location)

    def test_cobrar_pendiente_pedido_desde_caja_registra_pago_y_movimiento(self):
        from app.models import ColaCobro, MovimientoCaja, PedidoClientePago
        from pedidos.models import PedidoCliente

        pedido = self._crear_pedido(codigo='TEST-PED-COBRO-001', precio=70000)
        response_envio = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)
        self.assertEqual(response_envio.status_code, 302)

        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        self.assertIsNotNone(pendiente)
        cola_id = int(pendiente.id)

        response_tomar = self.client.post(
            f'/caja/api/cola-cobro/{cola_id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_tomar.status_code, 200)
        redirect_url = (response_tomar.get_json() or {}).get('redirect_url') or ''
        self.assertIn(f'/pedidos/cola-cobro/{cola_id}/pos', redirect_url)

        response_cobro = self.client.post(
            f'/caja/api/cola-cobro/{cola_id}/cobrar',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 70000,
                'tipo_pago': 'pago_total',
                'referencia': 'PED-CAJA-001',
            },
        )
        self.assertEqual(response_cobro.status_code, 200)
        data = response_cobro.get_json() or {}
        self.assertTrue(data.get('success'))

        pago = db.session.get(PedidoClientePago, int(data['id_pago_pedido']))
        self.assertIsNotNone(pago)
        self.assertEqual(int(pago.id_pedido), int(pedido.id_pedido))
        self.assertEqual((pago.tipo_pago or '').strip(), 'pago_total')
        self.assertEqual(int(pago.id_sesion_caja or 0), int(self.sesion.id_sesion))

        movimiento = db.session.get(MovimientoCaja, int(data['movimiento_caja_id']))
        self.assertIsNotNone(movimiento)
        self.assertEqual((movimiento.referencia_tipo or '').strip(), 'pago_pedido')

        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_actualizado.estado or '').strip(), 'pagado')
        self.assertAlmostEqual(float(pedido_actualizado.saldo_pendiente or 0), 0.0)

        pendiente = db.session.get(ColaCobro, cola_id)
        self.assertEqual((pendiente.estado or '').strip(), 'cobrado')
        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['id_pago_pedido']), int(pago.id_pago_pedido))

        response_estado = self.client.get('/caja/api/estado/resumen')
        self.assertEqual(response_estado.status_code, 200)
        data_estado = response_estado.get_json() or {}
        self.assertAlmostEqual(float(data_estado.get('total_cobros_pedidos_sesion') or 0), 70000.0)

        response_concepto = self.client.get(
            f'/caja/cierres/{int(self.sesion.id_sesion)}/conceptos/transacciones',
            query_string={
                'key': 'cobros_pedidos_metodo',
                'metodo_id': int(self.metodo_efectivo.id_metodo_pago),
            },
        )
        self.assertEqual(response_concepto.status_code, 200)
        data_concepto = response_concepto.get_json() or {}
        items = data_concepto.get('items') or []
        self.assertTrue(items)
        self.assertEqual((items[0].get('tx_tipo') or '').strip(), 'pago_pedido')

        response_detalle = self.client.get(
            f'/caja/cierres/{int(self.sesion.id_sesion)}/transacciones/detalle',
            query_string={'tipo': 'pago_pedido', 'id': int(pago.id_pago_pedido)},
        )
        self.assertEqual(response_detalle.status_code, 200)
        detalle = response_detalle.get_json() or {}
        self.assertEqual(detalle.get('tipo'), 'pago_pedido')
        self.assertEqual(int(((detalle.get('pedido') or {}).get('id') or 0)), int(pedido.id_pedido))

    def test_sprint3_caja_cobra_parcial_y_saldo_final_sin_entrega_automatica(self):
        from app.models import ColaCobro
        from pedidos.models import PedidoCliente

        pedido = self._crear_pedido(codigo='TEST-PED-SP3-001', precio=90000)
        response_envio = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)
        self.assertEqual(response_envio.status_code, 302)

        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        cola_id = int(pendiente.id)

        response_tomar = self.client.post(
            f'/caja/api/cola-cobro/{cola_id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_tomar.status_code, 200)

        response_cobro_parcial = self.client.post(
            f'/caja/api/cola-cobro/{cola_id}/cobrar',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 30000,
                'tipo_pago': 'pago_parcial',
                'referencia': 'PED-SP3-PARCIAL',
            },
        )
        self.assertEqual(response_cobro_parcial.status_code, 200)

        pedido_parcial = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_parcial.estado or '').strip(), 'pago_parcial')
        self.assertAlmostEqual(float(pedido_parcial.saldo_pendiente or 0), 60000.0)
        self.assertIsNone(pedido_parcial.id_venta_generada)

        response_reenvio = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)
        self.assertEqual(response_reenvio.status_code, 302)
        pendiente_final = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        cola_id_final = int(pendiente_final.id)
        self.assertNotEqual(cola_id_final, cola_id)

        response_tomar_final = self.client.post(
            f'/caja/api/cola-cobro/{cola_id_final}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_tomar_final.status_code, 200)

        response_cobro_final = self.client.post(
            f'/caja/api/cola-cobro/{cola_id_final}/cobrar',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 60000,
                'tipo_pago': 'pago_total',
                'referencia': 'PED-SP3-FINAL',
            },
        )
        self.assertEqual(response_cobro_final.status_code, 200)

        pedido_pagado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_pagado.estado or '').strip(), 'pagado')
        self.assertAlmostEqual(float(pedido_pagado.saldo_pendiente or 0), 0.0)
        self.assertIsNone(pedido_pagado.id_venta_generada)

    def test_estado_caja_y_resumen_exponen_pedidos_en_cola(self):
        from app.models import Configuracion

        Configuracion.establecer_bool('caja_alerta_pendientes_activa', True)
        pedido = self._crear_pedido(codigo='TEST-PED-UI-001', precio=55000)
        response_envio = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)
        self.assertEqual(response_envio.status_code, 302)

        response_estado = self.client.get('/caja/')
        self.assertEqual(response_estado.status_code, 200)
        html = response_estado.get_data(as_text=True)
        self.assertIn('value="pedido"', html)
        self.assertIn('data-cola-tipo="pedido"', html)
        self.assertIn('Abrir cobro', html)

        response_resumen = self.client.get('/caja/api/cola-cobro/resumen')
        self.assertEqual(response_resumen.status_code, 200)
        data = response_resumen.get_json() or {}
        self.assertEqual(int(((data.get('totales') or {}).get('pedido') or 0)), 1)
        pendientes = data.get('pendientes') or []
        self.assertTrue(pendientes)
        self.assertEqual((pendientes[0].get('tipo_origen') or '').strip().lower(), 'pedido')

    def test_listado_alerta_pedidos_listos_para_entregar(self):
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-LISTO-001', precio=55000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=55000,
            tipo_pago='pago_total',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-LISTO-001',
            sesion=self.sesion,
        )
        db.session.commit()

        response = self.client.get('/pedidos/')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Pedidos listos para entregar', html)
        self.assertIn(pedido.numero_pedido_display, html)

    def test_auditoria_ampliada_registra_eventos_clave_de_pedidos(self):
        from app.models import Auditoria, ColaCobro
        from pedidos.models import PedidoCliente

        producto = self._crear_producto_simple(codigo='TEST-PED-AUD-001', precio=50000)

        response_crear = self.client.post(
            '/pedidos/nuevo',
            data={
                'id_cliente': int(self.cliente.id_cliente),
                'observaciones': 'Pedido auditado',
                'descuento_monto': '0',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_crear.status_code, 302)

        pedido = PedidoCliente.query.order_by(PedidoCliente.id_pedido.desc()).first()
        self.assertIsNotNone(pedido)

        response_editar = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/editar',
            data={
                'id_cliente': int(self.cliente.id_cliente),
                'observaciones': 'Pedido auditado editado',
                'descuento_monto': '1000',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_editar.status_code, 302)

        response_item = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/items',
            data={
                'id_producto': int(producto.id_producto),
                'cantidad': 1,
                'precio_unitario': 50000,
                'observaciones': 'Item auditado',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_item.status_code, 302)

        pedido = db.session.get(PedidoCliente, int(pedido.id_pedido))
        item = pedido.detalles.first()
        self.assertIsNotNone(item)

        response_item_update = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/items/{int(item.id_detalle_pedido)}/actualizar',
            data={
                'cantidad': 2,
                'precio_unitario': 50000,
                'observaciones': 'Item auditado actualizado',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_item_update.status_code, 302)

        response_pago = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/pagos',
            data={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 99000,
                'tipo_pago': 'pago_total',
                'referencia': 'PED-AUD-001',
                'observaciones': 'Pago auditado',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_pago.status_code, 302)

        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        self.assertIsNotNone(pendiente)
        response_cobro = self.client.post(
            f'/pedidos/cola-cobro/{int(pendiente.id)}/cobrar',
            data={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 99000,
                'tipo_pago': 'pago_total',
                'referencia': 'PED-AUD-001',
                'observaciones': 'Pago auditado',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_cobro.status_code, 200)
        self.assertIn(b'Cobro confirmado', response_cobro.data)

        response_estado = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/estado',
            data={'estado': 'cancelado'},
            follow_redirects=False,
        )
        self.assertEqual(response_estado.status_code, 302)

        response_reabrir = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/reabrir',
            follow_redirects=False,
        )
        self.assertEqual(response_reabrir.status_code, 302)

        response_entregar = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/entregar',
            follow_redirects=False,
        )
        self.assertEqual(response_entregar.status_code, 302)

        acciones = {
            fila.accion
            for fila in Auditoria.query.filter_by(
                modulo='pedidos',
                referencia_tipo='pedido_cliente',
                referencia_id=int(pedido.id_pedido),
            ).all()
        }
        self.assertIn('crear_pedido', acciones)
        self.assertIn('actualizar_pedido', acciones)
        self.assertIn('agregar_item_pedido', acciones)
        self.assertIn('actualizar_item_pedido', acciones)
        self.assertIn('registrar_pago_pedido_manual', acciones)
        self.assertIn('registrar_cobro_pedido', acciones)
        self.assertIn('cambiar_estado_pedido', acciones)
        self.assertIn('reabrir_pedido', acciones)
        self.assertIn('confirmar_entrega_pedido', acciones)

    def test_reporte_diario_separa_recaudacion_de_ventas_cerradas_y_pedidos(self):
        from app.models import CuentaPorCobrar, PagoCuentaCobrar, PagoVenta, Venta
        from app.routes.reportes_ventas_diarias import construir_contexto_ventas_diarias
        from pedidos.services.pago_service import registrar_pago_pedido

        ahora = _utcnow()
        ayer = ahora - timedelta(days=1)

        venta_ayer_cobrada_hoy = Venta(
            id_cliente=int(self.cliente.id_cliente),
            id_sesion_caja=int(self.sesion.id_sesion),
            id_usuario_vendedor=int(self.admin.id_usuario),
            fecha_venta=ayer,
            subtotal=100000,
            total=100000,
            total_iva_10=0,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
            tipo_venta='contado',
            saldo_pendiente=0,
        )
        db.session.add(venta_ayer_cobrada_hoy)
        db.session.flush()
        db.session.add(
            PagoVenta(
                id_venta=int(venta_ayer_cobrada_hoy.id_venta),
                id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                monto=100000,
                fecha_pago=ahora,
            )
        )

        venta_hoy = Venta(
            id_cliente=int(self.cliente.id_cliente),
            id_sesion_caja=int(self.sesion.id_sesion),
            id_usuario_vendedor=int(self.admin.id_usuario),
            fecha_venta=ahora,
            subtotal=50000,
            total=50000,
            total_iva_10=0,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
            tipo_venta='contado',
            saldo_pendiente=0,
        )
        db.session.add(venta_hoy)
        db.session.flush()
        db.session.add(
            PagoVenta(
                id_venta=int(venta_hoy.id_venta),
                id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                monto=50000,
                fecha_pago=ahora,
            )
        )

        venta_credito = Venta(
            id_cliente=int(self.cliente.id_cliente),
            id_sesion_caja=int(self.sesion.id_sesion),
            id_usuario_vendedor=int(self.admin.id_usuario),
            fecha_venta=ayer,
            subtotal=30000,
            total=30000,
            total_iva_10=0,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
            tipo_venta='credito',
            saldo_pendiente=30000,
        )
        db.session.add(venta_credito)
        db.session.flush()

        cuenta = CuentaPorCobrar(
            id_venta=int(venta_credito.id_venta),
            id_cliente=int(self.cliente.id_cliente),
            monto_total=30000,
            monto_cobrado=30000,
            saldo_pendiente=0,
            estado='pagada',
        )
        db.session.add(cuenta)
        db.session.flush()
        db.session.add(
            PagoCuentaCobrar(
                id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar),
                id_sesion_caja=int(self.sesion.id_sesion),
                id_usuario=int(self.admin.id_usuario),
                monto=30000,
                id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                fecha_pago=ahora,
                estado='activo',
            )
        )

        pedido = self._crear_pedido(codigo='TEST-PED-REPORTE-001', precio=70000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=70000,
            tipo_pago='pago_total',
            id_usuario=int(self.admin.id_usuario),
            fecha_pago=ahora,
            sesion=self.sesion,
        )
        db.session.commit()

        contexto = construir_contexto_ventas_diarias(raw_fecha=__import__('app.utils.helpers', fromlist=['utc_naive_to_local']).utc_naive_to_local(ahora).date().isoformat())

        self.assertAlmostEqual(float(contexto['total_cobros_ventas_dia'] or 0), 150000.0)
        self.assertAlmostEqual(float(contexto['total_cobros_credito_dia'] or 0), 30000.0)
        self.assertAlmostEqual(float(contexto['cobros_pedidos_dia'] or 0), 70000.0)
        self.assertAlmostEqual(float(contexto['recaudacion_total_dia'] or 0), 250000.0)
        self.assertAlmostEqual(float(contexto['ventas_cerradas_dia'] or 0), 50000.0)
        self.assertEqual(len(contexto['ventas']), 1)
        self.assertEqual(int(contexto['ventas'][0].id_venta), int(venta_hoy.id_venta))

    def test_ticket_pedido_muestra_items_pagos_y_saldo(self):
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-TICKET-001', precio=91000)
        resultado = registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=25000,
            tipo_pago='sena',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-TICKET-REF-001',
            sesion=self.sesion,
        )
        db.session.commit()
        pago = resultado['pago']

        response = self.client.get(
            f'/pedidos/{int(pedido.id_pedido)}/ticket?preview=1&id_pago_pedido={int(pago.id_pago_pedido)}'
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('COMPROBANTE DE PEDIDO', html)
        self.assertIn(pedido.numero_pedido_display, html)
        self.assertIn(self.cliente.nombre, html)
        self.assertIn('Producto TEST-PED-TICKET-001', html)
        self.assertIn('Pagos registrados', html)
        self.assertIn(self.metodo_efectivo.nombre, html)
        self.assertIn('PED-TICKET-REF-001', html)
        self.assertIn('Saldo pendiente', html)
        self.assertIn('Cobro de esta operacion', html)

        response_popup = self.client.get(f'/pedidos/{int(pedido.id_pedido)}/ticket')
        self.assertEqual(response_popup.status_code, 200)
        html_popup = response_popup.get_data(as_text=True)
        self.assertIn('window.opener.location.replace', html_popup)

    def test_cobro_desde_caja_muestra_pantalla_de_impresion_del_ticket(self):
        from app.models import ColaCobro

        pedido = self._crear_pedido(codigo='TEST-PED-TICKET-002', precio=93000)
        response_envio = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)
        self.assertEqual(response_envio.status_code, 302)

        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        self.assertIsNotNone(pendiente)

        response_cobro = self.client.post(
            f'/pedidos/cola-cobro/{int(pendiente.id)}/cobrar',
            data={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 93000,
                'tipo_pago': 'pago_total',
                'referencia': 'PED-TICKET-002',
                'observaciones': 'Cobro con impresion',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_cobro.status_code, 200)
        html = response_cobro.get_data(as_text=True)
        self.assertIn('Cobro confirmado', html)
        self.assertIn('Abriendo ticket del pedido para impresion', html)
        self.assertIn(f'/pedidos/{int(pedido.id_pedido)}/ticket', html)
        self.assertIn('pedido-cobro-ticket-frame', html)
        self.assertIn("printU.searchParams.set('embedded', '1')", html)
        self.assertIn('printWindow.print()', html)
        self.assertIn('window.appNavigateActiveTab', html)
        self.assertIn('Volver al pedido', html)

    def test_pos_cobro_pedido_no_preabre_popup_vacio(self):
        from app.models import ColaCobro

        pedido = self._crear_pedido(codigo='TEST-PED-TICKET-POPUP', precio=48000)
        response_envio = self.client.post(f'/pedidos/{int(pedido.id_pedido)}/enviar-a-caja', follow_redirects=False)
        self.assertEqual(response_envio.status_code, 302)

        pendiente = (
            ColaCobro.query.filter_by(tipo_origen='pedido', id_origen=int(pedido.id_pedido))
            .order_by(ColaCobro.id.desc())
            .first()
        )
        self.assertIsNotNone(pendiente)

        response_pos = self.client.get(f'/pedidos/cola-cobro/{int(pendiente.id)}/pos')
        self.assertEqual(response_pos.status_code, 200)
        html = response_pos.get_data(as_text=True)
        self.assertNotIn('pedido-cobro-ticket-popup', html)
        self.assertNotIn("window.open('', popupName", html)

    def test_detalle_muestra_mensaje_para_cliente_con_resumen_y_saldo(self):
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-MSG-001', precio=64000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=14000,
            tipo_pago='sena',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-MSG-001',
            sesion=self.sesion,
        )
        db.session.commit()

        response = self.client.get(f'/pedidos/{int(pedido.id_pedido)}')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Mensaje para cliente', html)
        self.assertIn('Copiar resumen', html)
        self.assertIn(f'Aqui tienes el resumen de tu pedido {pedido.numero_pedido_display}', html)
        self.assertIn('Saldo pendiente: Gs. 50.000', html)

    def test_reserva_stock_blanda_bloquea_sobreasignacion_en_otro_pedido(self):
        from pedidos.services.pedido_service import agregar_item_pedido, crear_pedido

        producto = self._crear_producto_simple(codigo='TEST-PED-RES-001', precio=30000)
        producto.stock_actual = 5
        db.session.commit()

        pedido_a = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Reserva A',
        )
        db.session.flush()
        agregar_item_pedido(
            pedido_a,
            id_producto=int(producto.id_producto),
            cantidad=4,
            precio_unitario=30000,
            id_usuario=int(self.admin.id_usuario),
        )
        db.session.commit()

        pedido_b = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Reserva B',
        )
        db.session.flush()

        with self.assertRaises(ValueError):
            agregar_item_pedido(
                pedido_b,
                id_producto=int(producto.id_producto),
                cantidad=2,
                precio_unitario=30000,
                id_usuario=int(self.admin.id_usuario),
            )

    def test_reserva_stock_blanda_se_libera_si_pedido_se_cancela(self):
        from pedidos.services.pedido_service import agregar_item_pedido, crear_pedido

        producto = self._crear_producto_simple(codigo='TEST-PED-RES-002', precio=30000)
        producto.stock_actual = 5
        db.session.commit()

        pedido_a = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Reserva cancelable',
        )
        db.session.flush()
        agregar_item_pedido(
            pedido_a,
            id_producto=int(producto.id_producto),
            cantidad=4,
            precio_unitario=30000,
            id_usuario=int(self.admin.id_usuario),
        )
        pedido_a.estado = 'cancelado'
        db.session.commit()

        pedido_b = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Reserva nueva',
        )
        db.session.flush()
        agregar_item_pedido(
            pedido_b,
            id_producto=int(producto.id_producto),
            cantidad=2,
            precio_unitario=30000,
            id_usuario=int(self.admin.id_usuario),
        )
        db.session.commit()

        self.assertEqual(pedido_b.detalles.count(), 1)

    def test_producto_rapido_sobre_pedido_se_puede_agregar_como_item(self):
        from app.models import Categoria
        from pedidos.models import PedidoCliente
        from pedidos.services.pedido_service import crear_pedido

        categoria = Categoria.query.filter_by(nombre='Test Pedidos Rapidos').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Pedidos Rapidos', activo=True)
            db.session.add(categoria)
            db.session.commit()

        pedido = crear_pedido(
            id_cliente=int(self.cliente.id_cliente),
            id_usuario=int(self.admin.id_usuario),
            observaciones='Pedido con producto rapido',
        )
        db.session.commit()

        resp_producto = self.client.post(
            '/productos/crear_rapido',
            json={
                'codigo': 'SP-TEST-PED-RAP-001',
                'nombre': 'Producto rapido pedido',
                'id_categoria': int(categoria.id_categoria),
                'precio_compra': 0,
                'precio_venta': 75000,
                'stock_minimo': 0,
                'porcentaje_iva': 10,
                'es_servicio': True,
            },
        )
        self.assertEqual(resp_producto.status_code, 200)
        data_producto = resp_producto.get_json()
        self.assertTrue((data_producto or {}).get('success'))
        self.assertTrue((data_producto or {}).get('producto', {}).get('es_servicio'))

        resp_item = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/items',
            data={
                'id_producto': int(data_producto['producto']['id']),
                'cantidad': 1,
                'precio_unitario': 75000,
                'observaciones': 'Alta automatica',
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_item.status_code, 200)
        self.assertIn('Item agregado al pedido.', resp_item.get_data(as_text=True))

        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual(pedido_actualizado.detalles.count(), 1)
        item = pedido_actualizado.detalles.first()
        self.assertEqual(item.producto_codigo_snapshot, 'SP-TEST-PED-RAP-001')
        self.assertAlmostEqual(float(pedido_actualizado.total or 0), 75000.0)

    def test_reabrir_pedido_cancelado_recupera_estado_segun_saldo(self):
        from pedidos.models import PedidoCliente
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-REABRIR-001', precio=100000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=30000,
            tipo_pago='pago_parcial',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-REABRIR-001',
            sesion=self.sesion,
        )
        pedido.estado = 'cancelado'
        db.session.commit()

        response = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/reabrir',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_actualizado.estado or '').strip(), 'pago_parcial')
        self.assertAlmostEqual(float(pedido_actualizado.total_pagado or 0), 30000.0)
        self.assertAlmostEqual(float(pedido_actualizado.saldo_pendiente or 0), 70000.0)
        ultimo_evento = pedido_actualizado.historial.first()
        self.assertIsNotNone(ultimo_evento)
        self.assertEqual((ultimo_evento.tipo_evento or '').strip(), 'reapertura')

    def test_no_reabre_pedido_con_venta_generada(self):
        from pedidos.models import PedidoCliente
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-NO-REABRIR-001', precio=85000)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=85000,
            tipo_pago='pago_total',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-NO-REABRIR-001',
            sesion=self.sesion,
        )
        db.session.commit()
        self.client.post(f'/pedidos/{int(pedido.id_pedido)}/entregar', follow_redirects=False)

        pedido_entregado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertIsNotNone(pedido_entregado.id_venta_generada)

        response = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/reabrir',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        pedido_final = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_final.estado or '').strip(), 'entregado')

    def test_no_permite_entregar_pedido_con_saldo_pendiente(self):
        from pedidos.models import PedidoCliente

        pedido = self._crear_pedido(codigo='TEST-PED-ENT-BLOCK-001', precio=80000)

        response = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/entregar',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertIsNone(pedido_actualizado.id_venta_generada)
        self.assertNotEqual((pedido_actualizado.estado or '').strip(), 'entregado')

    def test_entregar_pedido_pagado_genera_venta_final_sin_duplicar_caja(self):
        from app.models import MovimientoCaja, MovimientoStock, PagoVenta, Producto, Ticket, Venta
        from app.routes.reportes_ventas_diarias import construir_contexto_ventas_diarias
        from pedidos.models import PedidoCliente
        from pedidos.services.pago_service import registrar_pago_pedido

        pedido = self._crear_pedido(codigo='TEST-PED-ENT-OK-001', precio=90000)
        item = pedido.detalles.first()
        producto = db.session.get(Producto, int(item.id_producto))
        self.assertIsNotNone(producto)
        stock_inicial = int(producto.stock_actual or 0)

        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=90000,
            tipo_pago='pago_total',
            id_usuario=int(self.admin.id_usuario),
            referencia='PED-ENTREGA-001',
            sesion=self.sesion,
        )
        db.session.commit()

        response = self.client.post(
            f'/pedidos/{int(pedido.id_pedido)}/entregar',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        pedido_actualizado = db.session.get(PedidoCliente, int(pedido.id_pedido))
        self.assertEqual((pedido_actualizado.estado or '').strip(), 'entregado')
        self.assertIsNotNone(pedido_actualizado.id_venta_generada)

        venta = db.session.get(Venta, int(pedido_actualizado.id_venta_generada))
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_cliente), int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(venta.total or 0), 90000.0)
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 0.0)

        pagos_venta = PagoVenta.query.filter_by(id_venta=int(venta.id_venta)).all()
        self.assertEqual(len(pagos_venta), 0)

        movimientos_caja_venta = MovimientoCaja.query.filter_by(
            referencia_tipo='venta',
            referencia_id=int(venta.id_venta),
        ).all()
        self.assertEqual(len(movimientos_caja_venta), 0)

        ticket = Ticket.query.filter_by(id_venta=int(venta.id_venta)).first()
        self.assertIsNotNone(ticket)

        movimientos_stock = MovimientoStock.query.filter_by(
            referencia_tipo='venta',
            referencia_id=int(venta.id_venta),
        ).all()
        self.assertEqual(len(movimientos_stock), 1)

        producto_actualizado = db.session.get(Producto, int(item.id_producto))
        self.assertEqual(int(producto_actualizado.stock_actual or 0), stock_inicial - 1)

        contexto = construir_contexto_ventas_diarias(raw_fecha=__import__('app.utils.helpers', fromlist=['utc_naive_to_local']).utc_naive_to_local(venta.fecha_venta).date().isoformat())
        self.assertAlmostEqual(float(contexto['cobros_pedidos_dia'] or 0), 90000.0)
        self.assertAlmostEqual(float(contexto['recaudacion_total_dia'] or 0), 90000.0)
        self.assertAlmostEqual(float(contexto['ventas_cerradas_dia'] or 0), 90000.0)
        self.assertEqual(len(contexto['ventas']), 1)


if __name__ == '__main__':
    unittest.main()
