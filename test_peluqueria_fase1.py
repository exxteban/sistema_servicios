"""Fase 1 del plan de peluquería: errores que afectaban dinero o datos."""
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from app import create_app, db
from app.models import AgendaActividad, Configuracion, Servicio, SesionCaja, Usuario
from app.utils.helpers import today_local
from app.utils.init_db import inicializar_datos_base


class PeluqueriaTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        cls.ctx.pop()

    def setUp(self):
        db.session.remove()
        db.drop_all()
        db.create_all()
        inicializar_datos_base(config_name='testing')

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def _crear_servicio(self, precio=50000, **extra):
        servicio = Servicio(
            codigo=extra.pop('codigo', 'PELU-CORTE'),
            nombre=extra.pop('nombre', 'Corte clásico'),
            categoria='Salon',
            costo=10000,
            precio=precio,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo=extra.pop('turno_rapido_tipo', 'corte'),
        )
        db.session.add(servicio)
        db.session.commit()
        return servicio

    def _abrir_caja(self):
        sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=100000, estado='abierta')
        db.session.add(sesion)
        db.session.commit()
        return sesion

    def _datos_turno(self, servicio, hora='10:00', **extra):
        fecha = today_local().isoformat()
        datos = {
            'usuario_id': str(self.admin.id_usuario),
            'servicio_turno_id': 'corte',
            'servicio_turno_nombre': 'Corte',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'fecha_inicio': f'{fecha}T{hora}',
            'duracion': '30',
            'accion': 'crear',
        }
        datos.update(extra)
        return datos

    def _efectivo_id(self):
        from app.models import MetodoPago

        return int(MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first().id_metodo_pago)


class TestTurnoSinCliente(PeluqueriaTestBase):
    def test_crear_y_cobrar_sin_cliente_pasa_el_turno_al_pos(self):
        servicio = self._crear_servicio()
        self._abrir_caja()

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data=self._datos_turno(servicio, accion='crear_y_cobrar'),
        )

        self.assertEqual(response.status_code, 302)
        actividad = AgendaActividad.query.filter_by(tipo='cita').one()
        self.assertIsNone(actividad.cliente_id)
        params = parse_qs(urlparse(response.headers['Location']).query)
        self.assertEqual(params.get('agenda_turno_actividad_id'), [str(actividad.id)])

    def test_cobrar_turno_sin_cliente_lo_marca_hecho(self):
        servicio = self._crear_servicio(precio=40000)
        self._abrir_caja()
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio))
        actividad = AgendaActividad.query.filter_by(tipo='cita').one()

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'tipo': 'servicio',
                    'id_servicio': int(servicio.id_servicio),
                    'cantidad': 1,
                    'precio': 40000,
                    'precio_manual': False,
                }],
                'pagos': [{'id_metodo_pago': self._efectivo_id(), 'monto': 40000}],
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'agenda_actividad_id': int(actividad.id),
                'client_request_id': 'turno-sin-cliente',
            },
        )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        db.session.refresh(actividad)
        self.assertEqual((actividad.estado or '').lower(), 'hecha')
        self.assertIsNotNone(actividad.venta_id)

    def test_turno_sin_cliente_aparece_en_cobros_pendientes(self):
        servicio = self._crear_servicio(nombre='Barba express', turno_rapido_tipo='barba')
        actividad = AgendaActividad(
            titulo='Barba',
            tipo='cita',
            fecha_inicio=datetime.combine(today_local(), datetime.strptime('11:00', '%H:%M').time()),
            estado='pendiente',
            prioridad='media',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            origen_modulo='agenda',
            mostrar_agenda_en='solo_responsable',
            recordatorio_a='solo_responsable',
        )
        db.session.add(actividad)
        db.session.commit()

        html = self.client.get('/').get_data(as_text=True)

        self.assertIn(f'agenda_turno_actividad_id={int(actividad.id)}', html)
        self.assertIn(servicio.nombre, html)


class TestChoqueDeHorarioConservaDatos(PeluqueriaTestBase):
    def test_turno_solapado_vuelve_al_formulario_con_lo_cargado(self):
        servicio = self._crear_servicio()
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora='15:00'))

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data=self._datos_turno(
                servicio,
                hora='15:15',
                observaciones='Prefiere tijera',
                cliente_nuevo_nombre='Juan Recepcion',
                cliente_nuevo_telefono='0981111222',
            ),
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Ese profesional ya tiene un turno en ese horario', html)
        self.assertIn('Prefiere tijera', html)
        self.assertIn('Juan Recepcion', html)
        self.assertIn('15:15', html)
        self.assertEqual(AgendaActividad.query.filter_by(tipo='cita').count(), 1)

    def test_formulario_nuevo_no_trae_valores_iniciales(self):
        html = self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True)

        self.assertIn('inicial: null', html)


class TestSenaEntraACaja(PeluqueriaTestBase):
    def _turno_con_cliente(self, servicio, hora='16:00'):
        from app.models import Cliente

        cliente = Cliente(nombre='Cliente Seña', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.commit()
        self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data=self._datos_turno(servicio, hora=hora, cliente_id=str(cliente.id_cliente)),
        )
        return AgendaActividad.query.filter_by(tipo='cita').order_by(AgendaActividad.id.desc()).first()

    def _registrar_sena(self, actividad, monto):
        return self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'sena', 'monto_sena': str(monto), 'nota_sena': 'efectivo'},
        )

    def _movimientos_sena(self):
        from app.models import MovimientoCaja

        return MovimientoCaja.query.filter_by(referencia_tipo='turno_sena').order_by(MovimientoCaja.id_movimiento_caja.asc()).all()

    def test_formularios_de_gestion_apuntan_al_turno(self):
        # La app abre esta pantalla dentro de pestañas cuya URL es "/": sin action explícito el POST iba a "/".
        actividad = self._turno_con_cliente(self._crear_servicio())

        html = self.client.get(f'/agenda/turnos/peluqueria/{actividad.id}/gestionar').get_data(as_text=True)

        accion = f'action="/agenda/turnos/peluqueria/{actividad.id}/gestionar"'
        self.assertEqual(html.count('<form method="POST"'), html.count(accion))
        self.assertGreaterEqual(html.count(accion), 4)
        self.assertNotIn('step="1000"', html)

    def test_sena_sin_caja_abierta_no_se_registra(self):
        actividad = self._turno_con_cliente(self._crear_servicio())

        self._registrar_sena(actividad, 10000)

        db.session.refresh(actividad)
        self.assertIsNone(actividad.sena_monto)
        self.assertEqual(self._movimientos_sena(), [])

    def test_sena_ingresa_a_caja_y_se_descuenta_en_pos(self):
        servicio = self._crear_servicio(precio=50000)
        self._abrir_caja()
        actividad = self._turno_con_cliente(servicio)

        self._registrar_sena(actividad, 15000)

        db.session.refresh(actividad)
        self.assertEqual(float(actividad.sena_monto), 15000.0)
        movimientos = self._movimientos_sena()
        self.assertEqual([(m.tipo, float(m.monto)) for m in movimientos], [('ingreso', 15000.0)])

        pos_html = self.client.get(f'/ventas/pos?cliente_servicio_id={actividad.cliente_servicio_id}').get_data(as_text=True)
        self.assertIn('"sena": 15000.0', pos_html)

    def test_sena_no_puede_igualar_el_precio(self):
        servicio = self._crear_servicio(precio=30000)
        self._abrir_caja()
        actividad = self._turno_con_cliente(servicio)

        self._registrar_sena(actividad, 30000)

        db.session.refresh(actividad)
        self.assertIsNone(actividad.sena_monto)
        self.assertEqual(self._movimientos_sena(), [])

    def test_cancelar_con_devolucion_saca_la_sena_de_caja(self):
        servicio = self._crear_servicio(precio=50000)
        self._abrir_caja()
        actividad = self._turno_con_cliente(servicio)
        self._registrar_sena(actividad, 20000)

        self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'cancelar', 'motivo': 'Avisó', 'devolver_sena': '1'},
        )

        db.session.refresh(actividad)
        self.assertEqual(actividad.estado, 'cancelada')
        self.assertIsNone(actividad.sena_monto)
        self.assertEqual(
            [(m.tipo, float(m.monto)) for m in self._movimientos_sena()],
            [('ingreso', 20000.0), ('egreso', 20000.0)],
        )

    def test_no_show_sin_devolucion_retiene_la_sena(self):
        servicio = self._crear_servicio(precio=50000)
        self._abrir_caja()
        actividad = self._turno_con_cliente(servicio)
        self._registrar_sena(actividad, 20000)

        self.client.post(f'/agenda/turnos/peluqueria/{actividad.id}/gestionar', data={'accion': 'no_show'})

        db.session.refresh(actividad)
        self.assertEqual(actividad.estado, 'cancelada')
        self.assertIn('Seña retenida', actividad.observaciones or '')
        self.assertEqual([m.tipo for m in self._movimientos_sena()], ['ingreso'])

    def test_turno_cobrado_no_se_puede_cancelar(self):
        servicio = self._crear_servicio(precio=40000)
        self._abrir_caja()
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio))
        actividad = AgendaActividad.query.filter_by(tipo='cita').one()
        self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'tipo': 'servicio', 'id_servicio': int(servicio.id_servicio), 'cantidad': 1, 'precio': 40000, 'precio_manual': False}],
                'pagos': [{'id_metodo_pago': self._efectivo_id(), 'monto': 40000}],
                'agenda_actividad_id': int(actividad.id),
                'client_request_id': 'turno-cobrado-no-cancela',
            },
        )

        self.client.post(f'/agenda/turnos/peluqueria/{actividad.id}/gestionar', data={'accion': 'cancelar'})

        db.session.refresh(actividad)
        self.assertEqual(actividad.estado, 'hecha')


class TestComisionesInventadasOcultas(PeluqueriaTestBase):
    def test_dashboard_no_muestra_comisiones_falsas(self):
        # La tarjeta volvió en la Fase 6 con el cálculo real; el 30% inventado no debe aparecer nunca.
        html = self.client.get('/').get_data(as_text=True)

        self.assertNotIn('30% de ventas', html)
        self.assertNotIn('Listo para el módulo de comisiones', html)


if __name__ == '__main__':
    unittest.main()
