import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app import create_app, db


CLAVE_CAJA_FLUJO_ENVIADO = 'caja_flujo_enviado_desde_vendedor'


class TestCajaReparacion(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, Permiso, Rol, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)
        self.rol_cajero = Rol.query.filter_by(nombre='Cajero').first()
        self.rol_vendedor = Rol.query.filter_by(nombre='Vendedor').first()
        self.permisos = {permiso.codigo: permiso for permiso in Permiso.query.all()}
        self.assertIsNotNone(self.rol_cajero)
        self.assertIsNotNone(self.rol_vendedor)

        self.cliente = db.session.get(Cliente, 1)
        if self.cliente is None:
            self.cliente = Cliente(nombre='Consumidor Final', tipo='minorista', activo=True)
            db.session.add(self.cliente)
            db.session.commit()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        Configuracion.establecer_bool(CLAVE_CAJA_FLUJO_ENVIADO, True)

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

    def _crear_reparacion(self, costo_final=150000, abono=20000):
        from app.models import Reparacion

        reparacion = Reparacion(
            cliente_id=self.cliente.id_cliente,
            id_usuario_vendedor=self.admin.id_usuario,
            tipo_equipo='Celular',
            marca_modelo='Samsung A15',
            imei_serie='IMEI-123456',
            falla_reportada='No enciende',
            diagnostico_tecnico='Batería dañada',
            solucion='Cambio de batería',
            estado='listo',
            costo_estimado=costo_final,
            costo_final=costo_final,
            abono=abono,
        )
        db.session.add(reparacion)
        db.session.commit()
        return reparacion

    def _crear_usuario(self, username, id_rol):
        from app.models import Usuario

        usuario = Usuario(
            username=username,
            nombre_completo=username,
            id_rol=id_rol,
            activo=True,
        )
        usuario.set_password('test1234')
        db.session.add(usuario)
        db.session.commit()
        return usuario

    def _crear_venta_con_vendedor(self, producto, vendedor, client_request_id):
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': float(producto.precio_venta),
                }],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(vendedor.id_usuario),
                'client_request_id': client_request_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        return int(data['id_venta'])

    def _crear_rol_con_permisos(self, nombre, codigos):
        from app.models import Rol

        rol = Rol(
            nombre=nombre,
            descripcion=f'Rol de pruebas {nombre}',
            nivel_jerarquia=5,
            activo=True,
        )
        for codigo in codigos:
            permiso = self.permisos.get(codigo)
            if permiso is not None:
                rol.permisos.append(permiso)
        db.session.add(rol)
        db.session.commit()
        return rol

    def _crear_sesion_para_usuario(self, usuario, nombre_caja):
        from app.models import Caja, SesionCaja

        caja = Caja(nombre=nombre_caja, ubicacion='QA')
        db.session.add(caja)
        db.session.flush()
        sesion = SesionCaja(
            id_caja=caja.id_caja,
            id_usuario=usuario.id_usuario,
            monto_inicial=250000,
            estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        return sesion

    def _crear_producto_simple(self, codigo='TEST-PROD-001', precio=50000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Ventas').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Ventas', activo=True)
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

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id_usuario)
            sess['_fresh'] = True

    def _enviar_venta_simple_a_caja(self, producto, client_request_id, cantidad=1, descuento=0):
        return self.client.post(
            '/ventas/enviar-a-caja',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': client_request_id,
                'descuento': descuento,
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': cantidad,
                }],
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

    def test_detalle_cierre_venta_muestra_vendedor_real_y_no_cajero(self):
        from app.models import Configuracion

        Configuracion.establecer_bool('pos_ocultar_selector_vendedor_cajero', True)
        vendedor = self._crear_usuario('vendedor_cierre_real', self.rol_vendedor.id_rol)
        producto = self._crear_producto_simple(codigo='TEST-CIERRE-VENDEDOR-001', precio=65000)
        venta_id = self._crear_venta_con_vendedor(producto, vendedor, 'cierre-vendedor-real-001')

        response = self.client.get(
            f'/caja/cierres/{int(self.sesion.id_sesion)}/transacciones/detalle',
            query_string={'tipo': 'venta', 'id': int(venta_id)},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertEqual(data.get('tipo'), 'venta')
        self.assertEqual(data.get('vendedor'), vendedor.nombre_completo)
        self.assertNotEqual(data.get('vendedor'), self.admin.nombre_completo)

    def test_detalle_reparacion_muestra_tipo_de_cliente(self):
        reparacion = self._crear_reparacion()
        self.cliente.tipo = 'mayorista'
        db.session.commit()

        response = self.client.get(f'/reparaciones/{reparacion.id_reparacion}')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Tipo de cliente', html)
        self.assertIn('Mayorista', html)

    def test_enviar_reparacion_a_caja_es_idempotente(self):
        from app.models import ColaCobro

        reparacion = self._crear_reparacion()

        resp_1 = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_1.status_code, 200)
        data_1 = resp_1.get_json()
        self.assertTrue(data_1['success'])

        resp_2 = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_2.status_code, 200)
        data_2 = resp_2.get_json()
        self.assertTrue(data_2['success'])
        self.assertEqual(data_1['cola_id'], data_2['cola_id'])

        pendientes = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).all()
        self.assertEqual(len(pendientes), 1)

        pendiente = pendientes[0]
        self.assertEqual(pendiente.estado, 'pendiente')
        self.assertAlmostEqual(float(pendiente.monto_total or 0), 130000.0)

        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['reparacion_id']), reparacion.id_reparacion)
        self.assertEqual(float(metadata['descuento']), 20000.0)
        self.assertTrue(isinstance(metadata.get('items'), list) and metadata['items'])

    def test_cobrar_pendiente_reparacion_desde_pos_vincula_venta_y_cierra_cola(self):
        from app.models import ColaCobro, Venta

        reparacion = self._crear_reparacion(costo_final=180000, abono=30000)

        resp_envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        metadata = pendiente.get_metadata()
        items_payload = []
        for item in metadata.get('items') or []:
            items_payload.append({
                'id_producto': int(item['id']),
                'cantidad': int(item['cantidad']),
                'precio': float(item['precio']),
                'precio_manual': bool(item.get('precio_manual') is True),
                'precio_opcion_id': item.get('precio_opcion_id'),
                'nombre': item.get('nombre'),
                'codigo': item.get('codigo'),
            })

        payload = {
            'items': items_payload,
            'pagos': [{
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': float(pendiente.monto_total or 0),
            }],
            'id_cliente': int(self.cliente.id_cliente),
            'id_usuario_vendedor': int(self.admin.id_usuario),
            'descuento': float(metadata.get('descuento') or 0),
            'cola_cobro_id': int(pendiente.id),
            'client_request_id': 'rep-pendiente-001',
        }

        resp_tomar = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_tomar.status_code, 200)

        resp_cobro = self.client.post('/ventas/procesar', json=payload)
        self.assertEqual(resp_cobro.status_code, 200)
        data = resp_cobro.get_json()
        self.assertTrue(data['success'])

        venta = db.session.get(Venta, data['id_venta'])
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_reparacion), reparacion.id_reparacion)
        self.assertAlmostEqual(float(venta.total or 0), 150000.0)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'cobrado')
        self.assertEqual(int(pendiente.id_origen), reparacion.id_reparacion)

        metadata_actualizado = pendiente.get_metadata()
        self.assertEqual(int(metadata_actualizado['venta_id']), int(venta.id_venta))
        self.assertEqual(int(metadata_actualizado['reparacion_id']), reparacion.id_reparacion)

    def test_cobrar_pendiente_reparacion_desde_endpoint_caja_genera_venta(self):
        from app.models import ColaCobro, Venta

        reparacion = self._crear_reparacion(costo_final=210000, abono=10000)

        resp_envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        resp_cobro = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/cobrar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_cobro.status_code, 200)
        data = resp_cobro.get_json()
        self.assertTrue(data['success'])
        self.assertIsNotNone(data.get('id_venta'))

        venta = db.session.get(Venta, data['id_venta'])
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_reparacion), reparacion.id_reparacion)
        self.assertAlmostEqual(float(venta.total or 0), 200000.0)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'cobrado')
        self.assertEqual(int(pendiente.id_usuario_destino), int(self.admin.id_usuario))
        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['venta_id']), int(venta.id_venta))
        self.assertEqual(int(metadata['cerrado_por_usuario']), int(self.admin.id_usuario))

    def test_admin_puede_liberar_pendiente_tomado_por_otro_cajero(self):
        from app.models import ColaCobro

        rol_cajero_qa = self._crear_rol_con_permisos('Cajero QA Liberar', ['tomar_cola_cobro'])
        cajero = self._crear_usuario('cajero_liberar_qa', rol_cajero_qa.id_rol)
        self._crear_sesion_para_usuario(cajero, 'Caja QA Liberar')

        client_cajero = self.app.test_client()
        self._login(client_cajero, cajero)

        reparacion = self._crear_reparacion(costo_final=180000, abono=10000)
        resp_envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        resp_tomar = client_cajero.post(
            f'/caja/api/cola-cobro/{pendiente.id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_tomar.status_code, 200)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'en_proceso')
        self.assertEqual(int(pendiente.id_usuario_destino), int(cajero.id_usuario))

        resp_liberar = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/liberar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_liberar.status_code, 200)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'pendiente')
        self.assertIsNone(pendiente.id_usuario_destino)
        self.assertIsNone(pendiente.fecha_toma)

    def test_procesar_reparacion_directa_respeta_precio_detalle_manual(self):
        from app.models import DetalleReparacion, MetodoPago, Venta

        reparacion = self._crear_reparacion(costo_final=0, abono=0)
        producto = self._crear_producto_simple(codigo='TEST-REP-DIRECTA', precio=20000)
        metodo_no_efectivo = MetodoPago.query.filter(
            MetodoPago.id_metodo_pago != self.metodo_efectivo.id_metodo_pago
        ).first()
        self.assertIsNotNone(metodo_no_efectivo)
        detalle = DetalleReparacion(
            id_reparacion=reparacion.id_reparacion,
            id_producto=producto.id_producto,
            nombre_producto=producto.nombre,
            cantidad=1,
            precio_unitario=75000,
            subtotal=75000,
            es_servicio=False,
            incluye_costo_final=True,
        )
        db.session.add(detalle)
        db.session.commit()

        payload = {
            'items': [{
                'id_producto': int(producto.id_producto),
                'cantidad': 1,
                'precio': 75000,
                'precio_manual': True,
                'nombre': producto.nombre,
                'codigo': producto.codigo,
            }],
            'pagos': [
                {
                    'id_metodo_pago': int(metodo_no_efectivo.id_metodo_pago),
                    'monto': 70000,
                },
                {
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': 5000,
                },
            ],
            'id_cliente': int(self.cliente.id_cliente),
            'id_usuario_vendedor': int(self.admin.id_usuario),
            'descuento': 0,
            'reparacion_id': int(reparacion.id_reparacion),
            'client_request_id': 'rep-directa-precio-manual-001',
        }

        resp = self.client.post('/ventas/procesar', json=payload)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json()
        self.assertTrue(data['success'])

        venta = db.session.get(Venta, data['id_venta'])
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_reparacion), reparacion.id_reparacion)
        self.assertAlmostEqual(float(venta.total or 0), 75000.0)

    def test_procesar_reparacion_directa_rechaza_vuelto_en_pago_mixto(self):
        from app.models import DetalleReparacion, MetodoPago

        reparacion = self._crear_reparacion(costo_final=0, abono=0)
        producto = self._crear_producto_simple(codigo='TEST-REP-VUELTO', precio=20000)
        metodo_no_efectivo = MetodoPago.query.filter(
            MetodoPago.id_metodo_pago != self.metodo_efectivo.id_metodo_pago
        ).first()
        self.assertIsNotNone(metodo_no_efectivo)

        detalle = DetalleReparacion(
            id_reparacion=reparacion.id_reparacion,
            id_producto=producto.id_producto,
            nombre_producto=producto.nombre,
            cantidad=1,
            precio_unitario=75000,
            subtotal=75000,
            es_servicio=False,
            incluye_costo_final=True,
        )
        db.session.add(detalle)
        db.session.commit()

        payload = {
            'items': [{
                'id_producto': int(producto.id_producto),
                'cantidad': 1,
                'precio': 75000,
                'precio_manual': True,
                'nombre': producto.nombre,
                'codigo': producto.codigo,
            }],
            'pagos': [
                {
                    'id_metodo_pago': int(metodo_no_efectivo.id_metodo_pago),
                    'monto': 70000,
                },
                {
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': 10000,
                },
            ],
            'id_cliente': int(self.cliente.id_cliente),
            'id_usuario_vendedor': int(self.admin.id_usuario),
            'descuento': 0,
            'reparacion_id': int(reparacion.id_reparacion),
            'client_request_id': 'rep-directa-vuelto-mixto-001',
        }

        resp = self.client.post('/ventas/procesar', json=payload)
        self.assertEqual(resp.status_code, 400, resp.get_json())
        data = resp.get_json() or {}
        self.assertIn('pagos mixtos', (data.get('error') or '').lower())

    def test_cobrar_pendiente_venta_desde_pos_usa_snapshot_guardado(self):
        from app.models import ColaCobro, DetalleVenta, Venta

        producto_snapshot = self._crear_producto_simple(codigo='TEST-PROD-SNAPSHOT-A', precio=50000)
        producto_inyectado = self._crear_producto_simple(codigo='TEST-PROD-SNAPSHOT-B', precio=90000)

        resp_envio = self._enviar_venta_simple_a_caja(producto_snapshot, 'venta-snapshot-cola')
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='venta').order_by(ColaCobro.id.desc()).first()
        self.assertIsNotNone(pendiente)

        resp_tomar = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_tomar.status_code, 200)

        resp_cobro = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'id_producto': int(producto_inyectado.id_producto),
                    'cantidad': 1,
                    'precio': 90000,
                }],
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': 50000,
                }],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'descuento': 40000,
                'cola_cobro_id': int(pendiente.id),
                'client_request_id': 'venta-snapshot-procesar',
            },
        )
        self.assertEqual(resp_cobro.status_code, 200)
        data = resp_cobro.get_json() or {}
        self.assertTrue(data.get('success'))

        venta = db.session.get(Venta, data.get('id_venta'))
        self.assertIsNotNone(venta)
        self.assertAlmostEqual(float(venta.total or 0), 50000.0)

        detalles = DetalleVenta.query.filter_by(id_venta=venta.id_venta).all()
        self.assertEqual(len(detalles), 1)
        self.assertEqual(int(detalles[0].id_producto), int(producto_snapshot.id_producto))
        self.assertNotEqual(int(detalles[0].id_producto), int(producto_inyectado.id_producto))

    def test_cobrar_pendiente_venta_preserva_vendedor_origen(self):
        from app.models import ColaCobro, Venta

        rol_vendedor = self._crear_rol_con_permisos('Vendedor Cola Origen', ['crear_venta', 'enviar_caja_venta'])
        rol_cajero = self._crear_rol_con_permisos('Cajero Cola Origen', ['crear_venta', 'tomar_cola_cobro'])
        vendedor = self._crear_usuario('vendedor_cola_origen', rol_vendedor.id_rol)
        cajero = self._crear_usuario('cajero_cola_origen', rol_cajero.id_rol)
        self._crear_sesion_para_usuario(cajero, 'Caja Cajero Cola Origen')

        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)
        client_cajero = self.app.test_client()
        self._login(client_cajero, cajero)

        producto = self._crear_producto_simple(codigo='TEST-PROD-VENDEDOR-ORIGEN', precio=73000)

        resp_envio = client_vendedor.post(
            '/ventas/enviar-a-caja',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(vendedor.id_usuario),
                'client_request_id': 'cola-vendedor-origen-001',
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='venta').order_by(ColaCobro.id.desc()).first()
        self.assertIsNotNone(pendiente)
        self.assertEqual(int(pendiente.id_usuario_origen), int(vendedor.id_usuario))

        resp_cobro = client_cajero.post(
            f'/caja/api/cola-cobro/{pendiente.id}/cobrar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_cobro.status_code, 200)
        data = resp_cobro.get_json() or {}
        self.assertTrue(data.get('success'))

        venta = db.session.get(Venta, int(data['id_venta']))
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_usuario_vendedor), int(vendedor.id_usuario))
        self.assertNotEqual(int(venta.id_usuario_vendedor), int(cajero.id_usuario))

    def test_cobrar_pendiente_desde_pos_requiere_toma_previa(self):
        from app.models import ColaCobro

        producto = self._crear_producto_simple(codigo='TEST-PROD-TAKE-FIRST', precio=42000)
        resp_envio = self._enviar_venta_simple_a_caja(producto, 'venta-take-first-cola')
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='venta').order_by(ColaCobro.id.desc()).first()
        self.assertIsNotNone(pendiente)

        resp_cobro = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': 42000,
                }],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'cola_cobro_id': int(pendiente.id),
                'client_request_id': 'venta-take-first-procesar',
            },
        )
        self.assertEqual(resp_cobro.status_code, 409)
        self.assertIn('debe tomar el pendiente', (resp_cobro.get_json() or {}).get('error', '').lower())

    def test_abrir_pos_con_pendiente_lo_marca_en_proceso(self):
        from app.models import ColaCobro

        producto = self._crear_producto_simple(codigo='TEST-PROD-POS-OPEN', precio=38000)
        resp_envio = self._enviar_venta_simple_a_caja(producto, 'venta-pos-open-cola')
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='venta').order_by(ColaCobro.id.desc()).first()
        self.assertIsNotNone(pendiente)
        self.assertEqual(pendiente.estado, 'pendiente')

        resp_pos = self.client.get(f'/ventas/pos?cola_id={pendiente.id}')
        self.assertEqual(resp_pos.status_code, 200)
        html = resp_pos.get_data(as_text=True)
        self.assertIn('const COLA_COBRO_DATA =', html)
        self.assertRegex(html, rf'const COLA_COBRO_DATA = .*"id":\s*{pendiente.id}')
        self.assertRegex(html, r'"items":\s*\[')

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'en_proceso')
        self.assertEqual(int(pendiente.id_usuario_destino), int(self.admin.id_usuario))
        self.assertIsNotNone(pendiente.fecha_toma)

    def test_pos_no_muestra_alerta_si_pendiente_ya_fue_cobrado(self):
        from app.models import ColaCobro

        producto = self._crear_producto_simple(codigo='TEST-PROD-SIN-ALERTA', precio=47000)
        resp_envio = self._enviar_venta_simple_a_caja(producto, 'venta-sin-alerta-cobrado')
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='venta').order_by(ColaCobro.id.desc()).first()
        self.assertIsNotNone(pendiente)

        resp_cobro = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/cobrar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_cobro.status_code, 200)

        resp_pos = self.client.get(f'/ventas/pos?cola_id={pendiente.id}')
        self.assertEqual(resp_pos.status_code, 200)
        html = resp_pos.get_data(as_text=True)
        self.assertNotIn('Este pendiente ya no está disponible', html)

    def test_cobro_rapido_revierte_toma_si_la_venta_falla(self):
        from app.models import ColaCobro

        producto = self._crear_producto_simple(codigo='TEST-PROD-ROLLBACK-LOCK', precio=61000)
        resp_envio = self._enviar_venta_simple_a_caja(producto, 'venta-rollback-lock-cola')
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='venta').order_by(ColaCobro.id.desc()).first()
        self.assertIsNotNone(pendiente)

        with patch('app.routes.caja.api._procesar_venta_payload', return_value=({'error': 'stock insuficiente'}, 400)):
            resp_cobro = self.client.post(
                f'/caja/api/cola-cobro/{pendiente.id}/cobrar',
                headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            )

        self.assertEqual(resp_cobro.status_code, 400)
        self.assertIn('stock insuficiente', (resp_cobro.get_json() or {}).get('error', '').lower())

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'pendiente')
        self.assertIsNone(pendiente.id_usuario_destino)
        self.assertIsNone(pendiente.fecha_toma)

    def test_liberar_y_cancelar_pendiente_caja_actualiza_estado(self):
        from app.models import ColaCobro

        reparacion = self._crear_reparacion(costo_final=170000, abono=20000)

        resp_envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        resp_tomar = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_tomar.status_code, 200)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'en_proceso')
        self.assertEqual(int(pendiente.id_usuario_destino), int(self.admin.id_usuario))

        resp_liberar = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/liberar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_liberar.status_code, 200)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'pendiente')
        self.assertIsNone(pendiente.id_usuario_destino)
        self.assertIsNone(pendiente.fecha_toma)

        resp_cancelar = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/cancelar',
            data={'motivo': 'Cliente desistió'},
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp_cancelar.status_code, 200)

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'cancelado')

        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['cancelado_por_usuario']), int(self.admin.id_usuario))
        self.assertEqual(metadata['cancelacion_motivo'], 'Cliente desistió')

    def test_tomar_y_cobrar_requieren_permiso_de_cola(self):
        from app.models import ColaCobro
        from app.routes.caja import api as caja_api

        class _FakeUser:
            def __init__(self, id_usuario):
                self.id_usuario = id_usuario
                self.is_authenticated = True

            def tiene_permiso(self, _codigo):
                return False

            def es_admin(self):
                return False

        reparacion = self._crear_reparacion()
        envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        with self.app.test_request_context(f'/caja/api/cola-cobro/{pendiente.id}/tomar', method='POST'):
            with patch('app.routes.caja.api.current_user', _FakeUser(self.admin.id_usuario + 3000)):
                resp_tomar, status_tomar = caja_api.cola_cobro_tomar.__wrapped__(pendiente.id)
        self.assertEqual(status_tomar, 403)
        self.assertEqual((resp_tomar.get_json() or {}).get('error'), 'Sin permisos')

        with self.app.test_request_context(f'/caja/api/cola-cobro/{pendiente.id}/cobrar', method='POST'):
            with patch('app.routes.caja.api.current_user', _FakeUser(self.admin.id_usuario + 3001)):
                resp_cobrar, status_cobrar = caja_api.cola_cobro_cobrar.__wrapped__(pendiente.id)
        self.assertEqual(status_cobrar, 403)
        self.assertEqual((resp_cobrar.get_json() or {}).get('error'), 'Sin permisos')

    def test_doble_toma_rechaza_segundo_cajero(self):
        from app.models import ColaCobro
        from app.routes.caja.api import _asegurar_en_proceso

        reparacion = self._crear_reparacion()
        envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(envio.status_code, 200)
        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        class _FakeUser:
            def __init__(self, id_usuario):
                self.id_usuario = id_usuario

        with patch('app.routes.caja.api.current_user', _FakeUser(self.admin.id_usuario)):
            item_1, error_1, status_1 = _asegurar_en_proceso(pendiente.id)

        self.assertIsNotNone(item_1)
        self.assertIsNone(error_1)
        self.assertIsNone(status_1)

        with patch('app.routes.caja.api.current_user', _FakeUser(self.admin.id_usuario + 999)):
            item_2, error_2, status_2 = _asegurar_en_proceso(pendiente.id)

        self.assertIsNotNone(item_2)
        self.assertEqual(status_2, 400)
        self.assertIn('asignado a otro cajero', (error_2 or {}).get('error', '').lower())

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'en_proceso')
        self.assertEqual(int(pendiente.id_usuario_destino), int(self.admin.id_usuario))

    def test_doble_cobro_devuelve_misma_venta_sin_duplicar(self):
        from app.models import Caja, ColaCobro, SesionCaja, Venta

        cajero_2 = self._crear_usuario('cajero_segundo_cobro', self.rol_cajero.id_rol)
        caja_2 = Caja(nombre='Caja Secundaria Test Cobro', ubicacion='QA')
        db.session.add(caja_2)
        db.session.flush()
        sesion_2 = SesionCaja(
            id_caja=caja_2.id_caja,
            id_usuario=cajero_2.id_usuario,
            monto_inicial=120000,
            estado='abierta',
        )
        db.session.add(sesion_2)
        db.session.commit()

        client_cajero_2 = self.app.test_client()
        self._login(client_cajero_2, cajero_2)

        reparacion = self._crear_reparacion(costo_final=260000, abono=30000)
        envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(envio.status_code, 200)
        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        cobrar_admin = self.client.post(
            f'/caja/api/cola-cobro/{pendiente.id}/cobrar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(cobrar_admin.status_code, 200)
        data_admin = cobrar_admin.get_json() or {}
        self.assertTrue(data_admin.get('success'))
        venta_id = int(data_admin.get('id_venta'))

        cobrar_segundo = client_cajero_2.post(
            f'/caja/api/cola-cobro/{pendiente.id}/cobrar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(cobrar_segundo.status_code, 200)
        data_segundo = cobrar_segundo.get_json() or {}
        self.assertTrue(data_segundo.get('success'))
        self.assertEqual(int(data_segundo.get('id_venta')), venta_id)
        self.assertIn('ya estaba cobrado', (data_segundo.get('message') or '').lower())

        ventas = Venta.query.filter_by(id_reparacion=reparacion.id_reparacion).all()
        self.assertEqual(len(ventas), 1)
        self.assertEqual(int(ventas[0].id_venta), venta_id)

    def test_enviar_reparacion_a_caja_bloqueado_si_flag_inactiva(self):
        from app.models import Configuracion

        reparacion = self._crear_reparacion()
        Configuracion.establecer_bool(CLAVE_CAJA_FLUJO_ENVIADO, False)

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 403)
        self.assertIn('no está habilitado', (resp.get_json() or {}).get('error', '').lower())

    def test_enviar_venta_a_caja_bloqueado_si_flag_inactiva(self):
        from app.models import Configuracion

        producto = self._crear_producto_simple(codigo='TEST-PROD-FLAG-OFF')
        Configuracion.establecer_bool(CLAVE_CAJA_FLUJO_ENVIADO, False)

        resp = self.client.post(
            '/ventas/enviar-a-caja',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-flag-off',
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 403)
        self.assertIn('no está habilitado', (resp.get_json() or {}).get('error', '').lower())

    def test_resumen_cola_respeta_flag_alerta(self):
        from app.models import ColaCobro, Configuracion

        pendiente = ColaCobro(
            tipo_origen='reparacion',
            id_origen=999,
            id_cliente=self.cliente.id_cliente,
            monto_total=150000,
            id_usuario_origen=self.admin.id_usuario,
            estado='pendiente',
        )
        en_proceso = ColaCobro(
            tipo_origen='venta',
            id_origen=111,
            id_cliente=self.cliente.id_cliente,
            monto_total=90000,
            id_usuario_origen=self.admin.id_usuario,
            id_usuario_destino=self.admin.id_usuario,
            estado='en_proceso',
        )
        db.session.add(pendiente)
        db.session.add(en_proceso)
        db.session.commit()

        Configuracion.establecer_bool('caja_alerta_pendientes_activa', False)
        resp_off = self.client.get('/caja/api/cola-cobro/resumen?detalle=0')
        self.assertEqual(resp_off.status_code, 200)
        data_off = resp_off.get_json() or {}
        self.assertEqual(data_off.get('count'), 0)
        self.assertFalse(data_off.get('alerta_activa'))

        Configuracion.establecer_bool('caja_alerta_pendientes_activa', True)
        resp_on = self.client.get('/caja/api/cola-cobro/resumen?detalle=0&firma=1')
        self.assertEqual(resp_on.status_code, 200)
        data_on = resp_on.get_json() or {}
        self.assertEqual(data_on.get('count'), 2)
        self.assertTrue(data_on.get('alerta_activa'))
        self.assertEqual(data_on.get('pendientes'), [])
        self.assertTrue(data_on.get('firma'))

        resp_filtrado = self.client.get('/caja/api/cola-cobro/resumen?detalle=0&firma=1&cola_estado=pendiente')
        self.assertEqual(resp_filtrado.status_code, 200)
        data_filtrado = resp_filtrado.get_json() or {}
        self.assertEqual(data_filtrado.get('count'), 1)
        self.assertTrue(data_filtrado.get('firma'))

        pendiente.estado = 'en_proceso'
        pendiente.id_usuario_destino = self.admin.id_usuario
        pendiente.fecha_toma = datetime.utcnow()
        db.session.commit()

        resp_filtrado_actualizado = self.client.get('/caja/api/cola-cobro/resumen?detalle=0&firma=1&cola_estado=pendiente')
        self.assertEqual(resp_filtrado_actualizado.status_code, 200)
        data_filtrado_actualizado = resp_filtrado_actualizado.get_json() or {}
        self.assertEqual(data_filtrado_actualizado.get('count'), 0)
        self.assertTrue(data_filtrado_actualizado.get('firma'))
        self.assertNotEqual(data_filtrado.get('firma'), data_filtrado_actualizado.get('firma'))

    def test_procesar_sin_caja_abierta_devuelve_json_para_pos(self):
        rol = self._crear_rol_con_permisos('Vendedor Sin Caja JSON', ['crear_venta'])
        vendedor = self._crear_usuario('vendedor_sin_caja_json', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        producto = self._crear_producto_simple(codigo='TEST-PROD-SIN-CAJA-JSON', precio=64000)

        resp = client_vendedor.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 64000}],
                'client_request_id': 'venta-sin-caja-json-001',
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('debe abrir una caja', (data.get('error') or '').lower())
        self.assertTrue(data.get('requiere_caja_abierta'))
        self.assertIn('/caja/abrir', data.get('redirect_url') or '')

    def test_venta_directa_requiere_cajero_si_flag_activa(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Vendedor sin Caja', ['crear_venta'])
        vendedor = self._crear_usuario('vendedor_flag_cajero', rol.id_rol)
        self._crear_sesion_para_usuario(vendedor, 'Caja Vendedor Flag')

        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        producto = self._crear_producto_simple(codigo='TEST-PROD-VENTA-FLAG-ON', precio=65000)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_vendedor.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 65000}],
                'client_request_id': 'venta-directa-flag-on',
            },
        )

        self.assertEqual(resp.status_code, 403)
        self.assertIn('debe enviar la venta a caja', (resp.get_json() or {}).get('error', '').lower())

    def test_pos_redirige_a_registro_vendedor_en_modo_exclusivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Registro', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_registro_redirect', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_vendedor.get('/ventas/pos', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/ventas/registro-vendedor', (resp.headers.get('Location') or ''))

    def test_registro_vendedor_permite_acceso_sin_caja_en_modo_exclusivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Registro Vista', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_registro_view', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_vendedor.get('/ventas/registro-vendedor')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('Registro Vendedor', html)
        self.assertIn('Registrar y Enviar al Cajero', html)

    def test_sidebar_muestra_registro_vendedor_y_oculta_pos_en_modo_exclusivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Sidebar Registro', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_sidebar_registro', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_vendedor.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('data-tab-title="Registro vendedor"', html)
        self.assertIn('/ventas/registro-vendedor/enviadas', html)
        self.assertNotIn('data-tab-title="POS"', html)

    def test_sidebar_muestra_pos_para_cajero_en_modo_exclusivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Cajero Sidebar POS', ['crear_venta', 'tomar_cola_cobro'])
        cajero = self._crear_usuario('cajero_sidebar_pos', rol.id_rol)
        client_cajero = self.app.test_client()
        self._login(client_cajero, cajero)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_cajero.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('data-tab-title="POS"', html)
        self.assertNotIn('data-tab-title="Registro vendedor"', html)

    def test_dashboard_oculta_alerta_sin_caja_para_vendedor_en_modo_exclusivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Dashboard', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_dashboard_sin_alerta', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_vendedor.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertNotIn('No tiene caja abierta', html)
        self.assertNotIn('Debe abrir una caja para realizar ventas', html)

    def test_dashboard_mantiene_alerta_sin_caja_para_cajero_en_modo_exclusivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Cajero Dashboard', ['crear_venta', 'tomar_cola_cobro'])
        cajero = self._crear_usuario('cajero_dashboard_con_alerta', rol.id_rol)
        client_cajero = self.app.test_client()
        self._login(client_cajero, cajero)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_cajero.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('No tiene caja abierta', html)
        self.assertIn('Debe abrir una caja para realizar ventas', html)

    def test_registro_vendedor_enviadas_filtra_por_estado(self):
        from app.models import ColaCobro, Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Enviadas', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_mis_enviadas', rol.id_rol)
        otro = self._crear_usuario('vendedor_otro_enviadas', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=self.cliente.id_cliente,
            monto_total=55000,
            id_usuario_origen=vendedor.id_usuario,
            estado='pendiente',
        )
        pendiente.set_metadata({'items': [{'cantidad': 1}], 'observaciones': 'Pendiente test'})
        db.session.add(pendiente)

        cobrado = ColaCobro(
            tipo_origen='venta',
            id_origen=1234,
            id_cliente=self.cliente.id_cliente,
            monto_total=91000,
            id_usuario_origen=vendedor.id_usuario,
            id_usuario_destino=self.admin.id_usuario,
            estado='cobrado',
        )
        cobrado.set_metadata({'venta_id': 1234, 'items': [{'cantidad': 2}]})
        db.session.add(cobrado)

        ajeno = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=self.cliente.id_cliente,
            monto_total=77000,
            id_usuario_origen=otro.id_usuario,
            estado='pendiente',
        )
        ajeno.set_metadata({'items': [{'cantidad': 3}]})
        db.session.add(ajeno)
        db.session.commit()

        resp = client_vendedor.get('/ventas/registro-vendedor/enviadas?estado=cobrado')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('Mis ventas enviadas', html)
        ids_renderizados = {int(v) for v in re.findall(r'<td[^>]*>#(\d+)</td>', html)}
        self.assertIn(int(cobrado.id), ids_renderizados)
        self.assertNotIn(int(pendiente.id), ids_renderizados)
        self.assertNotIn(int(ajeno.id), ids_renderizados)

    def test_registro_vendedor_enviadas_filtra_por_fecha_y_cliente(self):
        from app.models import Cliente, ColaCobro, Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Enviadas Fase3', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_fase3_filtros', rol.id_rol)
        otro = self._crear_usuario('vendedor_fase3_otro', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        cliente_match = Cliente(nombre='Cliente Fase3 Match', tipo='minorista', activo=True)
        cliente_otro = Cliente(nombre='Cliente Fase3 Otro', tipo='minorista', activo=True)
        db.session.add_all([cliente_match, cliente_otro])
        db.session.flush()

        fecha_base = datetime.utcnow() - timedelta(days=4)
        fecha_base = fecha_base.replace(hour=12, minute=0, second=0, microsecond=0)

        fila_match = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=cliente_match.id_cliente,
            monto_total=60000,
            id_usuario_origen=vendedor.id_usuario,
            estado='pendiente',
            fecha_envio=fecha_base,
        )
        fila_match.set_metadata({'items': [{'cantidad': 1}]})
        db.session.add(fila_match)

        fila_fuera_fecha = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=cliente_match.id_cliente,
            monto_total=61000,
            id_usuario_origen=vendedor.id_usuario,
            estado='pendiente',
            fecha_envio=fecha_base - timedelta(days=20),
        )
        fila_fuera_fecha.set_metadata({'items': [{'cantidad': 1}]})
        db.session.add(fila_fuera_fecha)

        fila_otro_cliente = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=cliente_otro.id_cliente,
            monto_total=62000,
            id_usuario_origen=vendedor.id_usuario,
            estado='pendiente',
            fecha_envio=fecha_base,
        )
        fila_otro_cliente.set_metadata({'items': [{'cantidad': 1}]})
        db.session.add(fila_otro_cliente)

        fila_otro_vendedor = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=cliente_match.id_cliente,
            monto_total=63000,
            id_usuario_origen=otro.id_usuario,
            estado='pendiente',
            fecha_envio=fecha_base,
        )
        fila_otro_vendedor.set_metadata({'items': [{'cantidad': 1}]})
        db.session.add(fila_otro_vendedor)
        db.session.commit()

        fecha_desde = (fecha_base.date() - timedelta(days=1)).isoformat()
        fecha_hasta = (fecha_base.date() + timedelta(days=1)).isoformat()
        resp = client_vendedor.get(
            f'/ventas/registro-vendedor/enviadas?cliente=Match&fecha_desde={fecha_desde}&fecha_hasta={fecha_hasta}'
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        ids_renderizados = {int(v) for v in re.findall(r'<td[^>]*>#(\d+)</td>', html)}
        self.assertIn(int(fila_match.id), ids_renderizados)
        self.assertNotIn(int(fila_fuera_fecha.id), ids_renderizados)
        self.assertNotIn(int(fila_otro_cliente.id), ids_renderizados)
        self.assertNotIn(int(fila_otro_vendedor.id), ids_renderizados)

    def test_registro_vendedor_enviadas_muestra_metricas_enviadas_vs_cobradas(self):
        from app.models import Cliente, ColaCobro, Configuracion, Venta

        rol = self._crear_rol_con_permisos('Vendedor Enviadas Metricas', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_fase3_metricas', rol.id_rol)
        otro = self._crear_usuario('vendedor_fase3_metricas_otro', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        cliente_metricas = Cliente(nombre='Cliente Fase3 Metricas', tipo='minorista', activo=True)
        db.session.add(cliente_metricas)
        db.session.flush()

        fecha_base = datetime.utcnow() - timedelta(days=3)
        fecha_base = fecha_base.replace(hour=13, minute=0, second=0, microsecond=0)

        envio_1 = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=cliente_metricas.id_cliente,
            monto_total=70000,
            id_usuario_origen=vendedor.id_usuario,
            estado='pendiente',
            fecha_envio=fecha_base,
        )
        envio_1.set_metadata({'items': [{'cantidad': 1}]})
        db.session.add(envio_1)

        envio_2 = ColaCobro(
            tipo_origen='venta',
            id_origen=555,
            id_cliente=cliente_metricas.id_cliente,
            monto_total=90000,
            id_usuario_origen=vendedor.id_usuario,
            estado='cobrado',
            fecha_envio=fecha_base,
        )
        envio_2.set_metadata({'venta_id': 555, 'items': [{'cantidad': 2}]})
        db.session.add(envio_2)

        venta_cobrada = Venta(
            id_cliente=cliente_metricas.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            id_usuario_vendedor=vendedor.id_usuario,
            fecha_venta=fecha_base + timedelta(hours=1),
            subtotal=90000,
            total=90000,
            estado='completada',
            client_request_id='fase3-metricas-vendedor-001',
        )
        db.session.add(venta_cobrada)

        venta_otro = Venta(
            id_cliente=cliente_metricas.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            id_usuario_vendedor=otro.id_usuario,
            fecha_venta=fecha_base + timedelta(hours=1),
            subtotal=120000,
            total=120000,
            estado='completada',
            client_request_id='fase3-metricas-vendedor-otro-001',
        )
        db.session.add(venta_otro)
        db.session.commit()

        fecha_desde = (fecha_base.date() - timedelta(days=1)).isoformat()
        fecha_hasta = (fecha_base.date() + timedelta(days=1)).isoformat()
        resp = client_vendedor.get(
            '/ventas/registro-vendedor/enviadas'
            f'?cliente=Metricas&fecha_desde={fecha_desde}&fecha_hasta={fecha_hasta}'
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('data-testid="metrica-enviadas" data-value="2"', html)
        self.assertIn('data-testid="metrica-cobradas" data-value="1"', html)
        self.assertIn('data-testid="metrica-pendientes" data-value="1"', html)
        self.assertIn('data-testid="metrica-tasa-cobro" data-value="50.0"', html)

    def test_vendedor_sin_caja_no_crea_pendiente_y_debe_abrir_caja(self):
        from app.models import ColaCobro, Configuracion

        rol = self._crear_rol_con_permisos('Vendedor Registro Envio', ['crear_venta', 'enviar_caja_venta'])
        vendedor = self._crear_usuario('vendedor_registro_envio', rol.id_rol)
        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        producto = self._crear_producto_simple(codigo='TEST-REGISTRO-VENDEDOR', precio=54000)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        total_antes = ColaCobro.query.count()
        resp = client_vendedor.post(
            '/ventas/enviar-a-caja',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(vendedor.id_usuario),
                'client_request_id': 'registro-vendedor-envio',
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('redirect_url'), '/caja/abrir')
        self.assertEqual(ColaCobro.query.count(), total_antes)

    def test_enviar_venta_a_caja_requiere_permiso_crear_venta(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Solo Enviar Caja', ['enviar_caja_venta'])
        usuario = self._crear_usuario('solo_envia_caja', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        producto = self._crear_producto_simple(codigo='TEST-SOLO-ENVIAR-CAJA', precio=45000)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_usuario.post(
            '/ventas/enviar-a-caja',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(usuario.id_usuario),
                'client_request_id': 'solo-enviar-sin-crear-venta',
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual((resp.get_json() or {}).get('error'), 'Sin permisos')

    def test_admin_puede_tomar_y_cobrar_pendiente_sin_permiso_explicito(self):
        from app.models import ColaCobro
        from app.routes.caja import api as caja_api

        class _FakeAdmin:
            def __init__(self, id_usuario):
                self.id_usuario = id_usuario
                self.is_authenticated = True

            def tiene_permiso(self, _codigo):
                return False

            def es_admin(self):
                return True

        reparacion = self._crear_reparacion(costo_final=198000, abono=8000)
        envio = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(envio.status_code, 200)

        pendiente = ColaCobro.query.filter_by(tipo_origen='reparacion', id_origen=reparacion.id_reparacion).first()
        self.assertIsNotNone(pendiente)

        with self.app.test_request_context(f'/caja/api/cola-cobro/{pendiente.id}/tomar', method='POST'):
            with patch('app.routes.caja.api.current_user', _FakeAdmin(self.admin.id_usuario)):
                resp_tomar = caja_api.cola_cobro_tomar.__wrapped__(pendiente.id)
        self.assertEqual(resp_tomar.status_code, 200)

        with self.app.test_request_context(f'/caja/api/cola-cobro/{pendiente.id}/cobrar', method='POST'):
            with patch('app.routes.caja.api.current_user', _FakeAdmin(self.admin.id_usuario)):
                resp_cobrar_raw = caja_api.cola_cobro_cobrar.__wrapped__(pendiente.id)
        if isinstance(resp_cobrar_raw, tuple):
            resp_cobrar, status_cobrar = resp_cobrar_raw
        else:
            resp_cobrar, status_cobrar = resp_cobrar_raw, resp_cobrar_raw.status_code
        self.assertEqual(status_cobrar, 200)
        data_cobrar = resp_cobrar.get_json() or {}
        self.assertTrue(data_cobrar.get('success'))

        db.session.refresh(pendiente)
        self.assertEqual(pendiente.estado, 'cobrado')

    def test_venta_directa_permitida_si_exigir_cajero_activa_pero_flujo_enviado_inactivo(self):
        from app.models import Configuracion, Venta

        rol = self._crear_rol_con_permisos('Vendedor modo mixto', ['crear_venta'])
        vendedor = self._crear_usuario('vendedor_flag_mixto', rol.id_rol)
        self._crear_sesion_para_usuario(vendedor, 'Caja Vendedor Mixto')

        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        producto = self._crear_producto_simple(codigo='TEST-PROD-VENTA-MIXTO', precio=68000)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', False)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_vendedor.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 68000}],
                'client_request_id': 'venta-directa-flag-mixto',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        venta = db.session.get(Venta, data.get('id_venta'))
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_usuario_vendedor), int(vendedor.id_usuario))

    def test_venta_directa_permitida_si_flag_cajero_inactiva(self):
        from app.models import Configuracion, Venta

        rol = self._crear_rol_con_permisos('Vendedor directo', ['crear_venta'])
        vendedor = self._crear_usuario('vendedor_flag_off', rol.id_rol)
        self._crear_sesion_para_usuario(vendedor, 'Caja Vendedor Directo')

        client_vendedor = self.app.test_client()
        self._login(client_vendedor, vendedor)

        producto = self._crear_producto_simple(codigo='TEST-PROD-VENTA-FLAG-OFF', precio=70000)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', False)

        resp = client_vendedor.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 70000}],
                'client_request_id': 'venta-directa-flag-off',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))

        venta = db.session.get(Venta, data.get('id_venta'))
        self.assertIsNotNone(venta)
        self.assertEqual(int(venta.id_usuario_vendedor), int(vendedor.id_usuario))

    def test_venta_sin_stock_permitida_con_permiso_directo_vender_sin_stock(self):
        from app.models import Configuracion, Venta

        rol = self._crear_rol_con_permisos('Cajero permiso stock', ['crear_venta', 'vender_sin_stock'])
        cajero = self._crear_usuario('cajero_permiso_sin_stock', rol.id_rol)
        self._crear_sesion_para_usuario(cajero, 'Caja Permiso Sin Stock')

        client_cajero = self.app.test_client()
        self._login(client_cajero, cajero)

        producto = self._crear_producto_simple(codigo='TEST-PROD-SIN-STOCK-PERMISO', precio=71000)
        producto.stock_actual = 0
        Configuracion.establecer_bool('stock_negativo_permitido', False)
        db.session.commit()

        resp = client_cajero.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 71000}],
                'client_request_id': 'venta-sin-stock-permiso-directo',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertTrue(bool(data.get('stock_warnings')))
        venta = db.session.get(Venta, data.get('id_venta'))
        self.assertIsNotNone(venta)

    def test_procesar_venta_rechaza_pago_negativo(self):
        from app.models import Venta

        producto = self._crear_producto_simple(codigo='TEST-PROD-PAGO-NEGATIVO', precio=50000)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 60000},
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': -10000},
                ],
                'client_request_id': 'venta-pago-negativo',
            },
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('mayor a cero', data.get('error', '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='venta-pago-negativo').first())

    def test_procesar_venta_rechaza_metodo_pago_inexistente(self):
        from app.models import Venta

        producto = self._crear_producto_simple(codigo='TEST-PROD-METODO-INVALIDO', precio=53000)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': 999999, 'monto': 53000}],
                'client_request_id': 'venta-metodo-inexistente',
            },
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('metodo de pago no encontrado', data.get('error', '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='venta-metodo-inexistente').first())

    def test_verificar_permiso_no_exige_autorizacion_si_permiso_directo(self):
        rol = self._crear_rol_con_permisos('Cajero verificar stock', ['crear_venta', 'vender_sin_stock'])
        cajero = self._crear_usuario('cajero_verificar_stock', rol.id_rol)
        client_cajero = self.app.test_client()
        self._login(client_cajero, cajero)

        resp = client_cajero.get('/api/autorizacion/verificar/vender_sin_stock')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('tiene_permiso'))
        self.assertFalse(data.get('requiere_autorizacion'))

    def test_generar_venta_reparacion_requiere_cajero_si_flag_activa(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Tecnico sin Caja', ['cobrar_reparacion'])
        tecnico = self._crear_usuario('tecnico_flag_on', rol.id_rol)
        self._crear_sesion_para_usuario(tecnico, 'Caja Tecnico Flag')

        client_tecnico = self.app.test_client()
        self._login(client_tecnico, tecnico)

        reparacion = self._crear_reparacion(costo_final=120000, abono=10000)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_tecnico.post(
            f'/reparaciones/{reparacion.id_reparacion}/generar_venta',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 403)
        self.assertIn('debe enviar la reparación a caja', (resp.get_json() or {}).get('error', '').lower())

    def test_generar_venta_reparacion_prioriza_bloqueo_cajero_antes_de_caja_abierta(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Tecnico Sin Caja Exclusivo', ['cobrar_reparacion'])
        tecnico = self._crear_usuario('tecnico_sin_caja_exclusivo', rol.id_rol)

        client_tecnico = self.app.test_client()
        self._login(client_tecnico, tecnico)

        reparacion = self._crear_reparacion(costo_final=123000, abono=0)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_tecnico.post(
            f'/reparaciones/{reparacion.id_reparacion}/generar_venta',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 403)
        self.assertIn('debe enviar la reparación a caja', (resp.get_json() or {}).get('error', '').lower())

    def test_generar_venta_reparacion_permitida_si_exigir_cajero_activa_pero_flujo_enviado_inactivo(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Tecnico modo mixto', ['cobrar_reparacion'])
        tecnico = self._crear_usuario('tecnico_flag_mixto', rol.id_rol)
        self._crear_sesion_para_usuario(tecnico, 'Caja Tecnico Mixto')

        client_tecnico = self.app.test_client()
        self._login(client_tecnico, tecnico)

        reparacion = self._crear_reparacion(costo_final=132000, abono=7000)
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', False)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_tecnico.post(
            f'/reparaciones/{reparacion.id_reparacion}/generar_venta',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertIn(f'reparacion_id={reparacion.id_reparacion}', data.get('redirect_url', ''))

    def test_generar_venta_reparacion_permitida_si_flag_cajero_inactiva(self):
        from app.models import Configuracion

        rol = self._crear_rol_con_permisos('Tecnico directo', ['cobrar_reparacion'])
        tecnico = self._crear_usuario('tecnico_flag_off', rol.id_rol)
        self._crear_sesion_para_usuario(tecnico, 'Caja Tecnico Directo')

        client_tecnico = self.app.test_client()
        self._login(client_tecnico, tecnico)

        reparacion = self._crear_reparacion(costo_final=145000, abono=5000)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', False)

        resp = client_tecnico.post(
            f'/reparaciones/{reparacion.id_reparacion}/generar_venta',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertIn(f'reparacion_id={reparacion.id_reparacion}', data.get('redirect_url', ''))

    def test_cambiar_estado_sin_permiso_redirige_a_detalle(self):
        from app.models import Reparacion

        rol = self._crear_rol_con_permisos('Solo ver reparaciones', ['ver_reparaciones'])
        usuario = self._crear_usuario('tecnico_sin_estado_perm', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        reparacion = self._crear_reparacion(costo_final=90000, abono=0)

        resp = client_usuario.post(
            f'/reparaciones/{reparacion.id_reparacion}/estado',
            data={'estado': 'en_proceso'},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/reparaciones/{reparacion.id_reparacion}', resp.headers.get('Location', ''))
        self.assertNotIn('/dashboard', resp.headers.get('Location', ''))

        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertEqual((rep_db.estado or '').strip().lower(), 'listo')

    def test_cambiar_estado_entregado_bloquea_entrega_con_saldo_pendiente(self):
        from app.models import Configuracion, DetalleReparacion, Reparacion

        rol = self._crear_rol_con_permisos(
            'Tecnico entrega sin crear venta',
            ['ver_reparaciones', 'cambiar_estado_reparacion', 'cobrar_reparacion']
        )
        usuario = self._crear_usuario('tecnico_entrega_sin_pos', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        reparacion = self._crear_reparacion(costo_final=0, abono=0)
        producto = self._crear_producto_simple(codigo='TEST-REP-ENTREGA', precio=75000)
        detalle = DetalleReparacion(
            id_reparacion=reparacion.id_reparacion,
            id_producto=producto.id_producto,
            nombre_producto=producto.nombre,
            cantidad=1,
            precio_unitario=75000,
            subtotal=75000,
            es_servicio=False,
            incluye_costo_final=True,
        )
        db.session.add(detalle)
        db.session.commit()

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', True)

        resp = client_usuario.post(
            f'/reparaciones/{reparacion.id_reparacion}/estado',
            data={'estado': 'entregado'},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/reparaciones/{reparacion.id_reparacion}', resp.headers.get('Location', ''))
        self.assertNotIn('/ventas/pos', resp.headers.get('Location', ''))

        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertEqual((rep_db.estado or '').strip().lower(), 'listo')


if __name__ == '__main__':
    unittest.main()
