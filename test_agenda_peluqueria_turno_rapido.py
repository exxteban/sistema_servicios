import unittest
from datetime import datetime

from app import create_app, db
from app.models import AgendaActividad, Cliente, ClienteServicio, Configuracion, Servicio, SesionCaja, Usuario
from app.utils.helpers import today_local
from app.utils.init_db import inicializar_datos_base


class TestAgendaPeluqueriaTurnoRapido(unittest.TestCase):
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

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def test_renderiza_turno_rapido_peluqueria(self):
        response = self.client.get('/agenda/turnos/peluqueria/nuevo')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Nuevo turno rápido', html)
        self.assertIn('/agenda/turnos/peluqueria/crear', html)
        self.assertIn('Corte + barba', html)
        self.assertIn('Crear y cobrar', html)
        self.assertIn('turno_rapido_tipo', self.client.get('/servicios/nuevo').get_data(as_text=True))

    def test_dashboard_peluqueria_apunta_al_turno_rapido(self):
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('/agenda/turnos/peluqueria/nuevo', html)

    def test_crear_turno_y_cobrar_redirige_a_pos_con_servicio_precargado(self):
        cliente = Cliente(nombre='Cliente Turno', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-CORTE-001',
            nombre='Corte premium',
            categoria='Salon',
            costo=12000,
            precio=45000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=100000,
            estado='abierta',
        )
        db.session.add_all([cliente, servicio, sesion])
        db.session.commit()

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'titulo': 'Corte - Cliente Turno',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'duracion': '30',
                'fecha_inicio': '2030-01-10T09:00',
                'fecha_fin': '2030-01-10T09:30',
                'descripcion': 'Turno desde test',
                'servicio_turno_id': 'corte',
                'servicio_turno_nombre': 'Corte',
                'servicio_catalogo_id': str(servicio.id_servicio),
                'accion': 'crear_y_cobrar',
            },
        )

        self.assertEqual(response.status_code, 302)
        location = response.headers.get('Location', '')
        self.assertIn('/ventas/pos?', location)
        self.assertIn('cliente_servicio_id=', location)

        actividad = AgendaActividad.query.filter_by(titulo='Corte - Cliente Turno').first()
        self.assertIsNotNone(actividad)
        self.assertEqual((actividad.estado or '').strip().lower(), 'pendiente')

        pos_response = self.client.get(location)
        self.assertEqual(pos_response.status_code, 200)
        html = pos_response.get_data(as_text=True)
        self.assertIn('const AGENDA_TURNO_DATA =', html)
        self.assertIn('Corte premium', html)

    def test_turno_crea_cliente_servicio_y_aparece_en_cobros_pendientes(self):
        fecha_hoy = today_local().isoformat()
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        cliente = Cliente(nombre='Cliente Agenda', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-LAVADO-001',
            nombre='Lavado full',
            categoria='Salon',
            costo=10000,
            precio=25000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='lavado',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'titulo': 'Lavado - Cliente Agenda',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'duracion': '20',
                'fecha_inicio': f'{fecha_hoy}T10:00',
                'fecha_fin': f'{fecha_hoy}T10:20',
                'descripcion': 'Turno de lavado',
                'servicio_turno_id': 'lavado',
                'servicio_turno_nombre': 'Lavado',
                'servicio_catalogo_id': str(servicio.id_servicio),
                'accion': 'crear',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        asignacion = ClienteServicio.query.filter_by(id_cliente=cliente.id_cliente, id_servicio=servicio.id_servicio).first()
        self.assertIsNotNone(asignacion)
        self.assertEqual((asignacion.estado or '').strip().lower(), 'agendado')
        self.assertIsNone(asignacion.id_venta)

        actividad = AgendaActividad.query.filter_by(titulo='Lavado - Cliente Agenda').first()
        self.assertIsNotNone(actividad)
        self.assertEqual(int(actividad.cliente_servicio_id), int(asignacion.id_cliente_servicio))

        dashboard = self.client.get('/')
        html = dashboard.get_data(as_text=True)
        self.assertIn('Cliente Agenda', html)
        self.assertIn('Lavado full', html)
        self.assertIn('1 servicio sin cobrar.', html)

    def test_iniciar_turno_lo_mueve_a_en_atencion(self):
        fecha_hoy = today_local().isoformat()
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        cliente = Cliente(nombre='Cliente Atencion', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-BARBA-001',
            nombre='Barba premium',
            categoria='Salon',
            costo=12000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='barba',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'titulo': 'Barba - Cliente Atencion',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'duracion': '20',
                'fecha_inicio': f'{fecha_hoy}T11:00',
                'fecha_fin': f'{fecha_hoy}T11:20',
                'descripcion': 'Turno de barba',
                'servicio_turno_id': 'barba',
                'servicio_turno_nombre': 'Barba',
                'servicio_catalogo_id': str(servicio.id_servicio),
                'accion': 'crear',
            },
        )

        actividad = AgendaActividad.query.filter_by(titulo='Barba - Cliente Atencion').first()
        self.assertIsNotNone(actividad)

        iniciar = self.client.post(
            f'/agenda/actividades/{int(actividad.id)}/iniciar',
            data={'next': '/'},
            follow_redirects=True,
        )
        self.assertEqual(iniciar.status_code, 200)

        asignacion = db.session.get(ClienteServicio, int(actividad.cliente_servicio_id))
        self.assertEqual((asignacion.estado or '').strip().lower(), 'en_proceso')

        dashboard = self.client.get('/')
        html = dashboard.get_data(as_text=True)
        self.assertIn('En atención', html)
        self.assertIn('Cliente Atencion', html)
        self.assertIn('Barba premium', html)

    def test_dashboard_muestra_turno_huerfano_en_cobros_pendientes(self):
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        cliente = Cliente(nombre='Cliente Huerfano', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        fecha_inicio = datetime.combine(today_local(), datetime.strptime('12:00', '%H:%M').time())

        actividad = AgendaActividad(
            titulo='Barba - Cliente Huerfano',
            tipo='cita',
            fecha_inicio=fecha_inicio,
            estado='pendiente',
            prioridad='media',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            cliente_id=cliente.id_cliente,
            origen_modulo='agenda',
            mostrar_agenda_en='solo_responsable',
            recordatorio_a='solo_responsable',
        )
        db.session.add(actividad)
        db.session.commit()

        dashboard = self.client.get('/')
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        self.assertIn('Cliente Huerfano', html)
        self.assertIn('Barba', html)
        self.assertIn('Turno agenda', html)


if __name__ == '__main__':
    unittest.main()
