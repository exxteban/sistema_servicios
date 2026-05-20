import unittest
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app import db
from test_caja_reparacion import TestCajaReparacion


class TestPlanBugfixes(TestCajaReparacion):
    def test_procesar_venta_rechaza_cantidad_no_positiva(self):
        from app.models import Producto, Venta

        producto = self._crear_producto_simple(codigo='TEST-PLAN-CANTIDAD', precio=70000)
        producto.stock_actual = 5
        db.session.commit()

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': -2}],
                'pagos': [],
                'client_request_id': 'plan-cantidad-negativa',
            },
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('cantidad inválida', data.get('error', '').lower())

        db.session.refresh(producto)
        self.assertEqual(int(producto.stock_actual), 5)
        self.assertIsNone(Venta.query.filter_by(client_request_id='plan-cantidad-negativa').first())

    def test_procesar_venta_rechaza_descuento_que_deja_total_no_positivo(self):
        from app.models import Venta

        producto = self._crear_producto_simple(codigo='TEST-PLAN-DESCUENTO', precio=48000)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'id_cliente': int(self.cliente.id_cliente),
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [],
                'descuento': 48000,
                'client_request_id': 'plan-descuento-cero',
            },
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('descuento', data.get('error', '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='plan-descuento-cero').first())

    def test_reparacion_rechaza_item_con_cantidad_no_positiva(self):
        from app.models import DetalleReparacion

        reparacion = self._crear_reparacion()
        producto = self._crear_producto_simple(codigo='TEST-REP-NEGATIVA', precio=25000)

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/items/agregar',
            data={
                'id_producto': int(producto.id_producto),
                'cantidad': -3,
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('mayor a cero', data.get('error', '').lower())
        detalle = DetalleReparacion.query.filter_by(
            id_reparacion=reparacion.id_reparacion,
            id_producto=producto.id_producto,
        ).first()
        self.assertIsNone(detalle)

    def test_cerrar_caja_rechaza_si_hay_pendiente_en_proceso_asignado(self):
        from app.models import ColaCobro, SesionCaja

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=321,
            id_cliente=self.cliente.id_cliente,
            monto_total=99000,
            id_usuario_origen=self.admin.id_usuario,
            id_usuario_destino=self.admin.id_usuario,
            estado='en_proceso',
            fecha_toma=datetime.utcnow() - timedelta(minutes=3),
        )
        db.session.add(pendiente)
        db.session.commit()

        resp = self.client.post(
            '/caja/cerrar',
            data={'monto_declarado': 500000, 'observaciones': 'cierre de prueba'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn('/caja/', resp.headers.get('Location', ''))

        sesion = db.session.get(SesionCaja, self.sesion.id_sesion)
        self.assertEqual(sesion.estado, 'abierta')

    def test_cerrar_caja_rechaza_si_es_ultima_caja_y_hay_pendiente_sin_tomar(self):
        from app.models import ColaCobro, SesionCaja

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=654,
            id_cliente=self.cliente.id_cliente,
            monto_total=348000,
            id_usuario_origen=self.admin.id_usuario,
            estado='pendiente',
        )
        db.session.add(pendiente)
        db.session.commit()

        resp = self.client.post(
            '/caja/cerrar',
            data={'monto_declarado': 500000, 'observaciones': 'cierre con cola pendiente'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn('/caja/', resp.headers.get('Location', ''))

        sesion = db.session.get(SesionCaja, self.sesion.id_sesion)
        self.assertEqual(sesion.estado, 'abierta')

    def test_cerrar_caja_muestra_detalle_del_pendiente_que_bloquea(self):
        from app.models import ColaCobro

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=656,
            id_cliente=self.cliente.id_cliente,
            monto_total=348000,
            id_usuario_origen=self.admin.id_usuario,
            estado='pendiente',
        )
        db.session.add(pendiente)
        db.session.commit()

        resp = self.client.post(
            '/caja/cerrar',
            data={'monto_declarado': 500000, 'observaciones': 'cierre con mensaje'},
            follow_redirects=True,
        )

        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True) or ''
        self.assertIn('última caja abierta', html)
        self.assertIn(f'#{pendiente.id}', html)
        self.assertIn('Consumidor Final', html)
        self.assertIn('₲ 348,000', html)

    def test_cerrar_caja_permite_cerrar_si_hay_otra_caja_abierta_para_pendientes(self):
        from app.models import ColaCobro, SesionCaja

        otro_cajero = self._crear_usuario('cajero_plan_respaldo', self.rol_cajero.id_rol)
        self._crear_sesion_para_usuario(otro_cajero, 'Caja Respaldo Pendientes')

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=655,
            id_cliente=self.cliente.id_cliente,
            monto_total=215000,
            id_usuario_origen=self.admin.id_usuario,
            estado='pendiente',
        )
        db.session.add(pendiente)
        db.session.commit()

        resp = self.client.post(
            '/caja/cerrar',
            data={'monto_declarado': 500000, 'observaciones': 'cierre con respaldo'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn('cierre_id=', resp.headers.get('Location', ''))

        sesion = db.session.get(SesionCaja, self.sesion.id_sesion)
        self.assertEqual(sesion.estado, 'cerrada')

    def test_cerrar_caja_rechaza_si_es_ultima_y_hay_en_proceso_de_otro_usuario(self):
        from app.models import ColaCobro, SesionCaja

        otro_cajero = self._crear_usuario('cajero_plan_en_proceso', self.rol_cajero.id_rol)
        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=657,
            id_cliente=self.cliente.id_cliente,
            monto_total=181000,
            id_usuario_origen=self.admin.id_usuario,
            id_usuario_destino=otro_cajero.id_usuario,
            estado='en_proceso',
            fecha_toma=datetime.utcnow() - timedelta(minutes=7),
        )
        db.session.add(pendiente)
        db.session.commit()

        resp = self.client.post(
            '/caja/cerrar',
            data={'monto_declarado': 500000, 'observaciones': 'cierre deja huérfano'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn('/caja/', resp.headers.get('Location', ''))

        sesion = db.session.get(SesionCaja, self.sesion.id_sesion)
        self.assertEqual(sesion.estado, 'abierta')

    def test_sesion_caja_impide_dos_abiertas_en_la_misma_caja(self):
        from app.models import SesionCaja

        cajero = self._crear_usuario('cajero_plan_unico', self.rol_cajero.id_rol)

        sesion_duplicada = SesionCaja(
            id_caja=self.sesion.id_caja,
            id_usuario=cajero.id_usuario,
            monto_inicial=150000,
            estado='abierta',
        )
        db.session.add(sesion_duplicada)

        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_rotar_token_reutiliza_registro_existente(self):
        from app.models.reparacion_seguimiento import ReparacionSeguimiento
        from app.utils.seguimiento_utils import hash_token

        reparacion = self._crear_reparacion()
        seguimiento = ReparacionSeguimiento(
            id_reparacion=reparacion.id_reparacion,
            token_hash=hash_token('token-inicial'),
            created_at=datetime.utcnow() - timedelta(days=2),
            revoked_at=datetime.utcnow() - timedelta(days=1),
            last_accessed_at=datetime.utcnow() - timedelta(hours=5),
            access_count=7,
        )
        db.session.add(seguimiento)
        db.session.commit()
        token_hash_inicial = seguimiento.token_hash

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/rotar_token',
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        seguimientos = ReparacionSeguimiento.query.filter_by(id_reparacion=reparacion.id_reparacion).all()
        self.assertEqual(len(seguimientos), 1)

        actualizado = seguimientos[0]
        self.assertEqual(actualizado.id, seguimiento.id)
        self.assertNotEqual(actualizado.token_hash, token_hash_inicial)
        self.assertIsNone(actualizado.revoked_at)
        self.assertIsNone(actualizado.last_accessed_at)
        self.assertEqual(int(actualizado.access_count or 0), 0)

    def test_abrir_caja_rechaza_caja_inactiva(self):
        from app.models import Caja, SesionCaja

        self.sesion.estado = 'cerrada'
        self.sesion.fecha_cierre = datetime.utcnow()
        db.session.commit()

        caja_inactiva = Caja(nombre='Caja Inactiva QA', ubicacion='QA', activa=False)
        db.session.add(caja_inactiva)
        db.session.commit()

        resp = self.client.post(
            '/caja/abrir',
            data={'id_caja': caja_inactiva.id_caja, 'monto_inicial': 1000},
            follow_redirects=True,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(SesionCaja.query.filter_by(id_caja=caja_inactiva.id_caja, estado='abierta').first())

    def test_abrir_caja_rechaza_monto_inicial_negativo(self):
        from app.models import Caja, SesionCaja

        self.sesion.estado = 'cerrada'
        self.sesion.fecha_cierre = datetime.utcnow()
        db.session.commit()

        caja = Caja(nombre='Caja Monto Negativo QA', ubicacion='QA', activa=True)
        db.session.add(caja)
        db.session.commit()

        resp = self.client.post(
            '/caja/abrir',
            data={'id_caja': caja.id_caja, 'monto_inicial': -1},
            follow_redirects=True,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(SesionCaja.query.filter_by(id_caja=caja.id_caja, estado='abierta').first())

    def test_cerrar_caja_rechaza_monto_declarado_negativo(self):
        from app.models import SesionCaja

        resp = self.client.post(
            '/caja/cerrar',
            data={'monto_declarado': -5, 'observaciones': 'monto inválido'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn('/caja/cerrar', resp.headers.get('Location', ''))
        sesion = db.session.get(SesionCaja, self.sesion.id_sesion)
        self.assertEqual(sesion.estado, 'abierta')

    def test_api_seguimiento_publico_usa_costo_final_calculado(self):
        from app.models import DetalleReparacion
        from app.models.reparacion_seguimiento import ReparacionSeguimiento
        from app.utils.seguimiento_utils import hash_token

        reparacion = self._crear_reparacion(costo_final=150000, abono=0)
        reparacion.mostrar_costo = True
        reparacion.costo_estimado = 120000
        producto = self._crear_producto_simple(codigo='TEST-PLAN-EXTRA', precio=30000)
        detalle = DetalleReparacion(
            id_reparacion=reparacion.id_reparacion,
            id_producto=producto.id_producto,
            cantidad=1,
            precio_unitario=30000,
            subtotal=30000,
            incluye_costo_final=True,
            nombre_producto='Extra QA',
            es_servicio=True,
        )
        token = 'token-plan-costo'
        seguimiento = ReparacionSeguimiento(
            id_reparacion=reparacion.id_reparacion,
            token_hash=hash_token(token),
        )
        db.session.add(detalle)
        db.session.add(seguimiento)
        db.session.commit()

        resp = self.client.get(f'/seguimiento/api/{token}')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(float(data.get('costo') or 0), 180000.0)

    def test_whatsapp_no_confunde_substrings_con_tipo_equipo(self):
        from app.services.whatsapp import conversacion_manager as cm

        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {"equipo": "Celular Redmi K60", "estado_texto": "Pendiente ⏳"}
                ]
            }
        }

        resp = cm._cliente_menciona_equipo_no_registrado("Queria saber si ya estaba listo", contexto)
        self.assertIsNone(resp)


if __name__ == '__main__':
    unittest.main()
