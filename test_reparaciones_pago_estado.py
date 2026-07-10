import unittest

from app import db
import test_caja_reparacion


class ReparacionesBase(unittest.TestCase):
    def setUp(self):
        return test_caja_reparacion.TestCajaReparacion.setUp(self)

    def tearDown(self):
        return test_caja_reparacion.TestCajaReparacion.tearDown(self)

    def _crear_reparacion(self, *args, **kwargs):
        return test_caja_reparacion.TestCajaReparacion._crear_reparacion(self, *args, **kwargs)

    def _crear_rol_con_permisos(self, *args, **kwargs):
        return test_caja_reparacion.TestCajaReparacion._crear_rol_con_permisos(self, *args, **kwargs)

    def _crear_sesion_para_usuario(self, *args, **kwargs):
        return test_caja_reparacion.TestCajaReparacion._crear_sesion_para_usuario(self, *args, **kwargs)

    def _crear_usuario(self, *args, **kwargs):
        return test_caja_reparacion.TestCajaReparacion._crear_usuario(self, *args, **kwargs)

    def _login(self, *args, **kwargs):
        return test_caja_reparacion.TestCajaReparacion._login(self, *args, **kwargs)


class TestReparacionesPagoEstado(ReparacionesBase):
    def test_actualizar_costos_rechaza_importes_negativos(self):
        from app.models import Reparacion

        reparacion = self._crear_reparacion(costo_final=120000, abono=0)
        respuesta = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '-1', 'costo_final': '120000', 'abono': '0'},
            headers={'Accept': 'application/json'},
        )

        self.assertEqual(respuesta.status_code, 400)
        db.session.expire_all()
        actualizada = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertAlmostEqual(float(actualizada.costo_final or 0), 120000.0)

    def test_estado_rechaza_salto_no_permitido(self):
        from app.models import Reparacion

        reparacion = self._crear_reparacion(costo_final=0, abono=0)
        respuesta = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/estado',
            data={'estado': 'pendiente'},
            follow_redirects=False,
        )

        self.assertEqual(respuesta.status_code, 302)
        db.session.expire_all()
        actualizada = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertEqual((actualizada.estado or '').lower(), 'listo')

    def test_reimprimir_ticket_no_rota_el_token_de_seguimiento(self):
        from app.models.reparacion_seguimiento import ReparacionSeguimiento

        reparacion = self._crear_reparacion(costo_final=0, abono=0)
        primera = self.client.get(f'/reparaciones/{reparacion.id_reparacion}/ticket')
        self.assertEqual(primera.status_code, 200)
        seguimiento = ReparacionSeguimiento.query.filter_by(
            id_reparacion=reparacion.id_reparacion
        ).first()
        hash_original = seguimiento.token_hash

        segunda = self.client.get(f'/reparaciones/{reparacion.id_reparacion}/ticket')
        self.assertEqual(segunda.status_code, 200)
        db.session.expire_all()
        seguimiento = ReparacionSeguimiento.query.filter_by(
            id_reparacion=reparacion.id_reparacion
        ).first()
        self.assertEqual(seguimiento.token_hash, hash_original)

    def test_api_seguimiento_no_simula_actualizaciones(self):
        from app.models.reparacion_seguimiento import ReparacionSeguimiento
        from app.utils.seguimiento_utils import hash_token

        reparacion = self._crear_reparacion(costo_final=0, abono=0)
        token = 'token-seguimiento-estable'
        db.session.add(ReparacionSeguimiento(
            id_reparacion=reparacion.id_reparacion,
            token_hash=hash_token(token),
        ))
        db.session.commit()

        primera = self.client.get(f'/seguimiento/api/{token}').get_json()
        segunda = self.client.get(f'/seguimiento/api/{token}').get_json()
        self.assertEqual(primera.get('updated_at'), segunda.get('updated_at'))

    def test_orden_cobrada_bloquea_costos_e_items(self):
        from app.models import Venta

        reparacion = self._crear_reparacion(costo_final=120000, abono=0)
        db.session.add(Venta(
            id_cliente=self.cliente.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            id_reparacion=reparacion.id_reparacion,
            subtotal=120000,
            total=120000,
            estado='completada',
        ))
        db.session.commit()

        costos = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '120000', 'costo_final': '1', 'abono': '0'},
            headers={'Accept': 'application/json'},
        )
        item = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/items/agregar',
            data={'id_producto': '1', 'cantidad': '1'},
        )

        self.assertEqual(costos.status_code, 409)
        self.assertEqual(item.status_code, 409)

    def test_revertir_desde_entregado_limpia_fecha_entrega_y_registra_historial(self):
        from datetime import datetime

        from app.models import Reparacion
        from app.models.reparacion_seguimiento import ReparacionHistorialEstado

        rol = self._crear_rol_con_permisos(
            'Operador estado reparacion',
            ['ver_reparaciones', 'cambiar_estado_reparacion']
        )
        usuario = self._crear_usuario('operador_estado_reparacion', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        reparacion = self._crear_reparacion(costo_final=95000, abono=95000)
        reparacion.estado = 'entregado'
        reparacion.fecha_entrega = datetime.utcnow()
        db.session.commit()

        resp = client_usuario.post(
            f'/reparaciones/{reparacion.id_reparacion}/estado',
            data={'estado': 'listo'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertEqual((rep_db.estado or '').strip().lower(), 'listo')
        self.assertIsNone(rep_db.fecha_entrega)

        historial = (
            ReparacionHistorialEstado.query
            .filter_by(id_reparacion=reparacion.id_reparacion)
            .order_by(ReparacionHistorialEstado.fecha_cambio.desc())
            .first()
        )
        self.assertIsNotNone(historial)
        self.assertEqual((historial.estado_anterior or '').strip().lower(), 'entregado')
        self.assertEqual((historial.estado_nuevo or '').strip().lower(), 'listo')

    def test_tecnico_puede_tomar_reparacion_sin_permiso_editar(self):
        from app.models import Reparacion, Rol
        from app.models.reparacion_seguimiento import ReparacionHistorialEstado

        rol = Rol.query.filter(Rol.nombre.in_(['Tecnico', 'Técnico'])).first()
        if rol is None:
            rol = self._crear_rol_con_permisos('Técnico', ['ver_reparaciones'])
        usuario = self._crear_usuario('tecnico_toma_solo_rol', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        reparacion = self._crear_reparacion(costo_final=40000, abono=0)
        reparacion.estado = 'pendiente'
        reparacion.id_usuario_tecnico = None
        reparacion.fecha_toma_tecnico = None
        reparacion.fecha_listo_tecnico = None
        db.session.commit()

        resp = client_usuario.post(
            f'/reparaciones/{reparacion.id_reparacion}/tecnico',
            data={'accion': 'tomar'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertEqual(int(rep_db.id_usuario_tecnico), int(usuario.id_usuario))
        self.assertEqual((rep_db.estado or '').strip().lower(), 'diagnostico')
        self.assertIsNotNone(rep_db.fecha_toma_tecnico)

        historial = (
            ReparacionHistorialEstado.query
            .filter_by(id_reparacion=reparacion.id_reparacion)
            .order_by(ReparacionHistorialEstado.fecha_cambio.desc())
            .first()
        )
        self.assertIsNotNone(historial)
        self.assertEqual((historial.estado_anterior or '').strip().lower(), 'pendiente')
        self.assertEqual((historial.estado_nuevo or '').strip().lower(), 'diagnostico')
        self.assertEqual((historial.nota or '').strip(), 'Reparación tomada por técnico')

    def test_cambiar_estado_entregado_bloquea_costo_final_base_sin_items(self):
        from app.models import Configuracion, Reparacion

        rol = self._crear_rol_con_permisos(
            'Tecnico entrega base pendiente',
            ['ver_reparaciones', 'cambiar_estado_reparacion']
        )
        usuario = self._crear_usuario('tecnico_entrega_base', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', False)
        Configuracion.establecer_bool('caja_exigir_cajero_para_cobro', False)

        reparacion = self._crear_reparacion(costo_final=95000, abono=0)

        resp = client_usuario.post(
            f'/reparaciones/{reparacion.id_reparacion}/estado',
            data={'estado': 'entregado'},
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)
        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertEqual((rep_db.estado or '').strip().lower(), 'listo')

    def test_actualizar_costos_persiste_abono_y_devuelve_saldo(self):
        from app.models import Reparacion

        reparacion = self._crear_reparacion(costo_final=120000, abono=0)

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '50000', 'costo_final': '160000', 'abono': '35000'},
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertAlmostEqual(float(data.get('abono') or 0), 35000.0)
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 125000.0)

        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertAlmostEqual(float(rep_db.abono or 0), 35000.0)
        self.assertAlmostEqual(float(rep_db.saldo_pendiente or 0), 125000.0)

    def test_abono_en_costos_registra_ingreso_en_caja(self):
        from app.models import MovimientoCaja

        reparacion = self._crear_reparacion(costo_final=120000, abono=0)
        total_antes = float(self.sesion.calcular_total_efectivo() or 0)

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '0', 'costo_final': '120000', 'abono': '40000'},
            headers={'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 200)

        mov = (
            MovimientoCaja.query
            .filter_by(
                id_sesion_caja=self.sesion.id_sesion,
                referencia_tipo='reparacion_abono',
                referencia_id=reparacion.id_reparacion,
            )
            .first()
        )
        self.assertIsNotNone(mov, 'El abono debe generar un movimiento de caja')
        self.assertEqual(mov.tipo, 'ingreso')
        self.assertAlmostEqual(float(mov.monto), 40000.0)

        db.session.expire_all()
        total_despues = float(self.sesion.calcular_total_efectivo() or 0)
        self.assertAlmostEqual(total_despues - total_antes, 40000.0)

    def test_reducir_abono_registra_egreso_de_ajuste(self):
        from app.models import MovimientoCaja

        reparacion = self._crear_reparacion(costo_final=120000, abono=0)
        self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '0', 'costo_final': '120000', 'abono': '40000'},
            headers={'Accept': 'application/json'},
        )
        # Ahora se baja el abono de 40000 a 15000 -> egreso de ajuste por 25000
        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '0', 'costo_final': '120000', 'abono': '15000'},
            headers={'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 200)

        egreso = (
            MovimientoCaja.query
            .filter_by(
                id_sesion_caja=self.sesion.id_sesion,
                referencia_tipo='reparacion_abono',
                referencia_id=reparacion.id_reparacion,
                tipo='egreso',
            )
            .first()
        )
        self.assertIsNotNone(egreso, 'Bajar el abono debe generar un egreso de ajuste')
        self.assertAlmostEqual(float(egreso.monto), 25000.0)

    def test_abono_sin_caja_abierta_se_rechaza(self):
        from app.models import Reparacion

        rol = self._crear_rol_con_permisos(
            'Editor sin caja', ['ver_reparaciones', 'editar_reparacion']
        )
        usuario = self._crear_usuario('editor_sin_caja', rol.id_rol)
        client_usuario = self.app.test_client()
        self._login(client_usuario, usuario)

        reparacion = self._crear_reparacion(costo_final=120000, abono=0)
        resp = client_usuario.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={'costo_estimado': '0', 'costo_final': '120000', 'abono': '40000'},
            headers={'Accept': 'application/json'},
        )
        self.assertEqual(resp.status_code, 409)

        db.session.expire_all()
        rep_db = db.session.get(Reparacion, reparacion.id_reparacion)
        self.assertAlmostEqual(float(rep_db.abono or 0), 0.0)

    def test_enviar_a_caja_doble_no_crea_dos_pendientes(self):
        from app.models import ColaCobro

        reparacion = self._crear_reparacion(costo_final=100000, abono=0)

        r1 = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json'},
        )
        r2 = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/enviar_a_caja',
            headers={'Accept': 'application/json'},
        )

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)

        activos = (
            ColaCobro.query
            .filter(
                ColaCobro.tipo_origen == 'reparacion',
                ColaCobro.id_origen == reparacion.id_reparacion,
                ColaCobro.estado.in_(['pendiente', 'en_proceso']),
            )
            .count()
        )
        self.assertEqual(activos, 1, 'No debe existir más de un pendiente de cobro activo')

    def test_generar_venta_bloquea_si_abono_cubre_todo_el_saldo(self):
        reparacion = self._crear_reparacion(costo_final=65000, abono=65000)

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/generar_venta',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn('saldo pendiente', (resp.get_json() or {}).get('error', '').lower())


if __name__ == '__main__':
    unittest.main()
