import unittest
from datetime import UTC, datetime

from app import create_app, db


class TestReportesVentasDiarias(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Caja, Cliente, MetodoPago, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.cliente = db.session.get(Cliente, 1)
        if self.cliente is None:
            self.cliente = Cliente(nombre='Consumidor Final', tipo='minorista', activo=True)
            db.session.add(self.cliente)
            db.session.flush()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        caja = Caja.query.first()
        if caja is None:
            caja = Caja(nombre='Caja Test', activa=True)
            db.session.add(caja)
            db.session.flush()

        self.sesion = SesionCaja(
            id_caja=int(caja.id_caja),
            id_usuario=int(self.admin.id_usuario),
            monto_inicial=100000,
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

    def test_desglosa_cobros_de_pedidos_por_pedido(self):
        from app.models import PedidoCliente, PedidoClientePago, Venta
        from app.routes.reportes_ventas_diarias import construir_contexto_ventas_diarias
        from app.utils.helpers import utc_naive_to_local

        ahora = datetime.now(UTC).replace(tzinfo=None)
        venta = Venta(
            id_cliente=int(self.cliente.id_cliente),
            id_sesion_caja=int(self.sesion.id_sesion),
            id_usuario_vendedor=int(self.admin.id_usuario),
            fecha_venta=ahora,
            subtotal=145000,
            total=145000,
            total_iva_10=0,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
            tipo_venta='contado',
            saldo_pendiente=0,
        )
        db.session.add(venta)
        db.session.flush()

        pedido_con_venta = PedidoCliente(
            numero_pedido=2,
            id_cliente=int(self.cliente.id_cliente),
            id_usuario_creacion=int(self.admin.id_usuario),
            id_venta_generada=int(venta.id_venta),
            estado='entregado',
            total=145000,
            total_pagado=145000,
            saldo_pendiente=0,
        )
        pedido_parcial = PedidoCliente(
            numero_pedido=1,
            id_cliente=int(self.cliente.id_cliente),
            id_usuario_creacion=int(self.admin.id_usuario),
            estado='pago_parcial',
            total=10000,
            total_pagado=6300,
            saldo_pendiente=3700,
        )
        db.session.add_all([pedido_con_venta, pedido_parcial])
        db.session.flush()

        pagos = [
            (pedido_con_venta, 'sena', 3000),
            (pedido_con_venta, 'pago_total', 142000),
            (pedido_parcial, 'sena', 1000),
            (pedido_parcial, 'pago_parcial', 5300),
        ]
        for pedido, tipo_pago, monto in pagos:
            db.session.add(
                PedidoClientePago(
                    id_pedido=int(pedido.id_pedido),
                    id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                    id_sesion_caja=int(self.sesion.id_sesion),
                    id_usuario=int(self.admin.id_usuario),
                    tipo_pago=tipo_pago,
                    monto=monto,
                    estado='activo',
                    fecha_pago=ahora,
                )
            )
        db.session.commit()

        fecha_local = utc_naive_to_local(ahora).date().isoformat()
        contexto = construir_contexto_ventas_diarias(raw_fecha=fecha_local)

        self.assertAlmostEqual(float(contexto['cobros_pedidos_dia']), 151300.0)
        desglose = contexto['desglose_cobros_pedidos']
        self.assertEqual([item['numero_pedido'] for item in desglose], ['PED-000002', 'PED-000001'])
        self.assertAlmostEqual(float(desglose[0]['total_cobrado']), 145000.0)
        self.assertAlmostEqual(float(desglose[1]['total_cobrado']), 6300.0)
        self.assertEqual(int(desglose[0]['id_venta_generada']), int(venta.id_venta))

    def test_detalle_txt_incluye_servicios_en_ventas_diarias(self):
        from app.models import DetalleVenta, Servicio, Venta
        from app.routes.reportes_ventas_diarias import construir_contexto_ventas_diarias
        from app.utils.helpers import utc_naive_to_local

        ahora = datetime.now(UTC).replace(tzinfo=None)
        servicio = Servicio(
            codigo='SRV-REP-001',
            nombre='Service premium',
            categoria='General',
            costo=30000,
            precio=60000,
            duracion_minutos=30,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.flush()

        venta = Venta(
            id_cliente=int(self.cliente.id_cliente),
            id_sesion_caja=int(self.sesion.id_sesion),
            id_usuario_vendedor=int(self.admin.id_usuario),
            fecha_venta=ahora,
            subtotal=120000,
            total=120000,
            total_iva_10=0,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
            tipo_venta='contado',
            saldo_pendiente=0,
        )
        db.session.add(venta)
        db.session.flush()

        db.session.add(
            DetalleVenta(
                id_venta=int(venta.id_venta),
                id_servicio=int(servicio.id_servicio),
                cantidad=2,
                precio_unitario=60000,
                precio_original=60000,
                porcentaje_iva=10,
                monto_iva=0,
                subtotal=120000,
            )
        )
        db.session.commit()

        fecha_local = utc_naive_to_local(ahora).date().isoformat()
        contexto = construir_contexto_ventas_diarias(raw_fecha=fecha_local)
        detalle_txt = contexto['detalles_por_venta'][int(venta.id_venta)]

        self.assertEqual(detalle_txt, 'Service premium x2')

    def test_productos_vendidos_muestra_servicios(self):
        from app.models import DetalleVenta, Servicio, Venta
        from app.utils.helpers import utc_naive_to_local

        ahora = datetime.now(UTC).replace(tzinfo=None)
        servicio = Servicio(
            codigo='SRV-RPT-001',
            nombre='Lavado premium',
            categoria='Spa',
            costo=20000,
            precio=45000,
            duracion_minutos=30,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.flush()

        venta = Venta(
            id_cliente=int(self.cliente.id_cliente),
            id_sesion_caja=int(self.sesion.id_sesion),
            id_usuario_vendedor=int(self.admin.id_usuario),
            fecha_venta=ahora,
            subtotal=45000,
            total=45000,
            total_iva_10=0,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
            tipo_venta='contado',
            saldo_pendiente=0,
        )
        db.session.add(venta)
        db.session.flush()

        db.session.add(
            DetalleVenta(
                id_venta=int(venta.id_venta),
                id_servicio=int(servicio.id_servicio),
                cantidad=1,
                precio_unitario=45000,
                precio_original=45000,
                porcentaje_iva=10,
                monto_iva=0,
                subtotal=45000,
            )
        )
        db.session.commit()

        fecha_local = utc_naive_to_local(ahora).date().isoformat()
        response = self.client.get(
            f'/reportes/productos-vendidos?desde={fecha_local}&hasta={fecha_local}',
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Lavado premium', html)
        self.assertIn('Servicio', html)


if __name__ == '__main__':
    unittest.main()
