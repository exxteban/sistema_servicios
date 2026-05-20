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
