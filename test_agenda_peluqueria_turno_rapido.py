import unittest
from datetime import datetime

from app import create_app, db
from app.models import AgendaActividad, Cliente, ClienteServicio, Configuracion, Servicio, ServicioPrecioOpcion, SesionCaja, Usuario
from app.services.agenda_turnos_peluqueria import build_turno_peluqueria_services
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
        self.assertIn('Elegí la variante exacta para usar su nombre y costo', html)
        self.assertIn('Crear y cobrar', html)
        self.assertIn('turno_rapido_tipo', self.client.get('/servicios/nuevo').get_data(as_text=True))

    def test_servicio_se_carga_por_categoria_rapida_y_variantes(self):
        response = self.client.post(
            '/servicios/nuevo',
            data={
                'codigo': 'CAT-CORTE',
                'nombre': '',
                'categoria': 'Corte',
                'turno_rapido_tipo': 'corte',
                'costo': '',
                'precio': '',
                'duracion_minutos': '30',
                'porcentaje_iva': '10',
                'variantes': 'Clasico | 10000 | 30000\nPremium | 15000 | 50000',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        servicio = Servicio.query.filter_by(codigo='CAT-CORTE').first()
        self.assertIsNotNone(servicio)
        self.assertEqual(servicio.nombre, 'Corte')
        self.assertEqual(servicio.categoria, 'Corte')
        self.assertEqual(servicio.turno_rapido_tipo, 'corte')
        self.assertEqual(float(servicio.costo), 10000.0)
        self.assertEqual(float(servicio.precio), 30000.0)
        self.assertEqual(servicio.opciones.filter_by(activo=True).count(), 2)

    def test_asignar_servicio_cliente_exige_y_usa_subtipo(self):
        cliente = Cliente(nombre='Cliente Subtipo', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='CLI-CORTE-SUB',
            nombre='Corte',
            categoria='Corte',
            costo=10000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        db.session.add_all([cliente, servicio])
        db.session.flush()
        opcion = ServicioPrecioOpcion(
            id_servicio=servicio.id_servicio,
            etiqueta='Corte premium',
            costo=18000,
            precio=55000,
            orden=0,
            activo=True,
        )
        db.session.add(opcion)
        db.session.commit()

        sin_subtipo = self.client.post(
            f'/clientes/{cliente.id_cliente}/servicios/asignar',
            data={
                'id_servicio': str(servicio.id_servicio),
                'cantidad': '1',
                'estado': 'solicitado',
            },
            follow_redirects=True,
        )

        self.assertEqual(sin_subtipo.status_code, 200)
        self.assertIn('Selecciona el subtipo o variante', sin_subtipo.get_data(as_text=True))
        self.assertIsNone(ClienteServicio.query.filter_by(id_cliente=cliente.id_cliente, id_servicio=servicio.id_servicio).first())

        con_subtipo = self.client.post(
            f'/clientes/{cliente.id_cliente}/servicios/asignar',
            data={
                'id_servicio': str(servicio.id_servicio),
                'servicio_precio_opcion_id': str(opcion.id_opcion_precio),
                'cantidad': '1',
                'estado': 'solicitado',
            },
            follow_redirects=True,
        )

        self.assertEqual(con_subtipo.status_code, 200)
        asignacion = ClienteServicio.query.filter_by(id_cliente=cliente.id_cliente, id_servicio=servicio.id_servicio).first()
        self.assertIsNotNone(asignacion)
        self.assertEqual(float(asignacion.costo_pactado), 18000.0)
        self.assertEqual(float(asignacion.precio_pactado), 55000.0)
        self.assertIn('Tipo: Corte premium', asignacion.observaciones or '')

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

    def test_turno_rapido_exige_tipo_cuando_servicio_tiene_variantes(self):
        cliente = Cliente(nombre='Cliente Variantes', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-CORTE-VAR',
            nombre='Corte',
            categoria='Salon',
            costo=12000,
            precio=35000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        db.session.add_all([cliente, servicio])
        db.session.flush()
        db.session.add(ServicioPrecioOpcion(
            id_servicio=servicio.id_servicio,
            etiqueta='Caballero',
            costo=12000,
            precio=35000,
            orden=0,
            activo=True,
        ))
        db.session.commit()

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'titulo': 'Corte - Cliente Variantes',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'duracion': '30',
                'fecha_inicio': '2030-01-10T09:00',
                'fecha_fin': '2030-01-10T09:30',
                'descripcion': 'Turno sin tipo',
                'servicio_turno_id': 'corte',
                'servicio_turno_nombre': 'Corte',
                'servicio_catalogo_id': str(servicio.id_servicio),
                'accion': 'crear',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Selecciona el tipo o variante del servicio', response.get_data(as_text=True))
        self.assertIsNone(AgendaActividad.query.filter_by(titulo='Corte - Cliente Variantes').first())

    def test_turno_rapido_usa_precio_y_titulo_de_la_variante_seleccionada(self):
        cliente = Cliente(nombre='Cliente Tipo', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-CORTE-TIPO',
            nombre='Corte',
            categoria='Salon',
            costo=12000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        db.session.add_all([cliente, servicio])
        db.session.flush()
        opcion = ServicioPrecioOpcion(
            id_servicio=servicio.id_servicio,
            etiqueta='Premium',
            costo=15000,
            precio=50000,
            orden=0,
            activo=True,
        )
        db.session.add(opcion)
        db.session.commit()

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'titulo': 'Corte - Premium - Cliente Tipo',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'duracion': '30',
                'fecha_inicio': '2030-01-10T10:00',
                'fecha_fin': '2030-01-10T10:30',
                'descripcion': 'Turno con tipo',
                'servicio_turno_id': 'corte',
                'servicio_turno_nombre': 'Corte - Premium',
                'servicio_catalogo_id': str(servicio.id_servicio),
                'servicio_precio_opcion_id': str(opcion.id_opcion_precio),
                'accion': 'crear',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        actividad = AgendaActividad.query.filter_by(titulo='Corte - Premium - Cliente Tipo').first()
        self.assertIsNotNone(actividad)
        asignacion = db.session.get(ClienteServicio, int(actividad.cliente_servicio_id))
        self.assertIsNotNone(asignacion)
        self.assertEqual(float(asignacion.costo_pactado), 15000.0)
        self.assertEqual(float(asignacion.precio_pactado), 50000.0)

    def test_turno_rapido_agrupa_variantes_de_servicios_de_la_categoria(self):
        cliente = Cliente(nombre='Cliente Categoria Corte', tipo='minorista', activo=True)
        servicio_vinculado = Servicio(
            codigo='TURNO-CORTE-BASE',
            nombre='Corte base',
            categoria='Corte',
            costo=10000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        servicio_categoria = Servicio(
            codigo='TURNO-CORTE-JUNIOR',
            nombre='Corte',
            categoria='Corte',
            costo=12000,
            precio=35000,
            porcentaje_iva=10,
            activo=True,
        )
        servicio_por_nombre = Servicio(
            codigo='TURNO-CORTE-SENIOR',
            nombre='Corte senior',
            categoria='Peluqueria',
            costo=15000,
            precio=50000,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add_all([cliente, servicio_vinculado, servicio_categoria, servicio_por_nombre])
        db.session.flush()
        opcion = ServicioPrecioOpcion(
            id_servicio=servicio_categoria.id_servicio,
            etiqueta='Corte junior',
            costo=13000,
            precio=42000,
            orden=0,
            activo=True,
        )
        db.session.add(opcion)
        db.session.commit()

        corte = next(item for item in build_turno_peluqueria_services() if item['id'] == 'corte')
        labels = {item['etiqueta'] for item in corte['catalogo_opciones']}
        self.assertIn('Corte base', labels)
        self.assertIn('Corte junior', labels)
        self.assertIn('Corte senior', labels)

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'titulo': 'Corte - Corte junior - Cliente Categoria Corte',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'duracion': '30',
                'fecha_inicio': '2030-01-10T11:00',
                'fecha_fin': '2030-01-10T11:30',
                'descripcion': 'Turno con variante de otro servicio de la categoria',
                'servicio_turno_id': 'corte',
                'servicio_turno_nombre': 'Corte - Corte junior',
                'servicio_catalogo_id': str(servicio_categoria.id_servicio),
                'servicio_precio_opcion_id': str(opcion.id_opcion_precio),
                'accion': 'crear',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        actividad = AgendaActividad.query.filter_by(titulo='Corte - Corte junior - Cliente Categoria Corte').first()
        self.assertIsNotNone(actividad)
        asignacion = db.session.get(ClienteServicio, int(actividad.cliente_servicio_id))
        self.assertEqual(int(asignacion.id_servicio), int(servicio_categoria.id_servicio))
        self.assertEqual(float(asignacion.costo_pactado), 13000.0)
        self.assertEqual(float(asignacion.precio_pactado), 42000.0)

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
        self.assertIn(f'agenda_turno_actividad_id={int(actividad.id)}', html)

    def test_cobrar_turno_huerfano_vincula_venta_y_sale_de_pendientes(self):
        from app.models import MetodoPago, Venta

        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        cliente = Cliente(nombre='Cliente Cobrado', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-COBRO-001',
            nombre='Corte cobrado',
            categoria='Salon',
            costo=10000,
            precio=70000,
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
        db.session.flush()
        actividad = AgendaActividad(
            titulo='Corte - Cliente Cobrado',
            tipo='cita',
            fecha_inicio=datetime.combine(today_local(), datetime.strptime('14:00', '%H:%M').time()),
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

        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'tipo': 'servicio',
                    'id_servicio': int(servicio.id_servicio),
                    'cantidad': 1,
                    'precio': 70000,
                    'precio_manual': False,
                }],
                'pagos': [{'id_metodo_pago': int(metodo.id_metodo_pago), 'monto': 70000}],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'agenda_actividad_id': int(actividad.id),
                'client_request_id': 'agenda-turno-cobrado-qa',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        db.session.refresh(actividad)
        self.assertEqual(int(actividad.venta_id), int(data['id_venta']))
        self.assertEqual((actividad.estado or '').strip().lower(), 'hecha')
        self.assertIsNotNone(db.session.get(Venta, int(data['id_venta'])))

        dashboard = self.client.get('/')
        html = dashboard.get_data(as_text=True)
        self.assertNotIn('Cliente Cobrado', html)


if __name__ == '__main__':
    unittest.main()
