"""Fase 4 del plan de peluquería: gestión del turno de punta a punta."""
import unittest
from urllib.parse import parse_qs, unquote, urlparse

from app import db
from app.models import AgendaActividad, Cliente, ClienteServicio
from app.services.peluqueria_turno_estado import estado_turno
from app.utils.helpers import today_local
from test_peluqueria_fase1 import PeluqueriaTestBase


class TurnoTestBase(PeluqueriaTestBase):
    def _turno(self, servicio, hora='10:00', **extra):
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora=hora, **extra))
        return AgendaActividad.query.filter_by(tipo='cita').order_by(AgendaActividad.id.desc()).first()

    def _accion(self, turno, accion, **datos):
        return self.client.post(f'/agenda/turnos/peluqueria/{turno.id}/gestionar', data={'accion': accion, **datos})

    def _gestion(self, turno):
        return self.client.get(f'/agenda/turnos/peluqueria/{turno.id}/gestionar').get_data(as_text=True)

    def _cobrar_en_pos(self, turno, servicio, precio=50000):
        from app.models import MetodoPago

        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        payload = {
            'items': [{'tipo': 'servicio', 'id_servicio': int(servicio.id_servicio), 'cantidad': 1, 'precio': precio, 'precio_manual': False}],
            'pagos': [{'id_metodo_pago': int(metodo.id_metodo_pago), 'monto': precio}],
            'id_usuario_vendedor': int(self.admin.id_usuario),
            'agenda_actividad_id': int(turno.id),
            'client_request_id': f'fase4-{turno.id}',
        }
        if turno.cliente_id:
            payload['id_cliente'] = int(turno.cliente_id)
        response = self.client.post('/ventas/procesar', json=payload)
        self.assertTrue((response.get_json() or {}).get('success'), response.get_json())


class TestTurnoDePuntaAPunta(TurnoTestBase):
    def test_turno_sin_cliente_recorre_todos_los_estados(self):
        servicio = self._crear_servicio()
        self._abrir_caja()
        turno = self._turno(servicio)
        self.assertEqual(estado_turno(turno), 'agendado')
        self.assertEqual(turno.servicio_id, servicio.id_servicio)

        self._accion(turno, 'empezar')
        db.session.refresh(turno)
        self.assertEqual(estado_turno(turno), 'en_atencion')
        self.assertIsNotNone(turno.atencion_inicio)
        self.assertIn('Atención iniciada', self._gestion(turno))

        self._accion(turno, 'terminar')
        db.session.refresh(turno)
        self.assertEqual(estado_turno(turno), 'terminado')

        cobro = self.client.get(f'/agenda/turnos/peluqueria/{turno.id}/cobrar')
        self.assertEqual(cobro.status_code, 302)
        params = parse_qs(urlparse(cobro.headers['Location']).query)
        self.assertEqual(params['agenda_turno_actividad_id'], [str(turno.id)])
        self.assertEqual(params['agenda_turno_servicio_id'], [str(servicio.id_servicio)])
        self.assertEqual(params['agenda_turno_vendedor_id'], [str(self.admin.id_usuario)])

        self._cobrar_en_pos(turno, servicio)
        db.session.refresh(turno)
        self.assertEqual(estado_turno(turno), 'cobrado')
        html = self._gestion(turno)
        self.assertNotIn(f'/agenda/turnos/peluqueria/{turno.id}/cobrar', html)
        self.assertNotIn('Empezar atención</button>', html)

    def test_turno_terminado_sigue_en_cobros_pendientes(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio)
        self._accion(turno, 'terminar')

        html = self.client.get('/').get_data(as_text=True)

        self.assertIn(f'agenda_turno_actividad_id={turno.id}', html)

    def test_en_atencion_sin_cliente_cuenta_en_el_dashboard(self):
        servicio = self._crear_servicio(nombre='Barba express')
        turno = self._turno(servicio)
        self._accion(turno, 'empezar')

        from app.services.dashboard_agenda import obtener_resumen_en_atencion_dashboard

        resumen = obtener_resumen_en_atencion_dashboard(True, today_local(), usuario=self.admin)
        self.assertEqual(resumen['count'], 1)
        self.assertEqual(resumen['items'][0]['cliente_nombre'], 'Consumidor Final')
        self.assertEqual(resumen['items'][0]['servicio_nombre'], 'Barba express')

    def test_no_se_puede_empezar_dos_veces_ni_reprogramar_atendido(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio)
        self._accion(turno, 'empezar')

        self._accion(turno, 'empezar')
        html = self._gestion(turno)
        self.assertIn('ya no está agendado', html)

        inicio = turno.fecha_inicio
        self._accion(turno, 'reprogramar', fecha=today_local().isoformat(), hora='18:00', duracion='30')
        db.session.refresh(turno)
        self.assertIn('no se puede reprogramar', self._gestion(turno))
        self.assertEqual(turno.fecha_inicio, inicio)

    def test_terminado_no_se_puede_cancelar(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio)
        self._accion(turno, 'terminar')

        self._accion(turno, 'cancelar')
        db.session.refresh(turno)

        self.assertEqual(estado_turno(turno), 'terminado')


class TestCobroConServicioDelCliente(TurnoTestBase):
    def test_pos_recibe_al_profesional_como_vendedor(self):
        cliente = Cliente(nombre='Cliente Vendedor', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.commit()
        servicio = self._crear_servicio()
        turno = self._turno(servicio, cliente_id=str(cliente.id_cliente))
        self.assertIsNotNone(turno.cliente_servicio_id)

        cobro = self.client.get(f'/agenda/turnos/peluqueria/{turno.id}/cobrar')
        self.assertIn(f'cliente_servicio_id={turno.cliente_servicio_id}', cobro.headers['Location'])

        from app.services.clientes_servicios import build_pos_data_from_cliente_servicios

        datos = build_pos_data_from_cliente_servicios([db.session.get(ClienteServicio, turno.cliente_servicio_id)])
        self.assertEqual(datos['id_usuario_vendedor'], self.admin.id_usuario)


class TestNoShowComoDato(TurnoTestBase):
    def test_no_show_guarda_cierre_motivo(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio)

        self._accion(turno, 'no_show')
        db.session.refresh(turno)

        self.assertEqual(turno.estado, 'cancelada')
        self.assertEqual(turno.cierre_motivo, 'no_show')
        self.assertEqual(estado_turno(turno), 'no_show')

    def test_cancelado_no_es_no_show_aunque_la_nota_lo_diga(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio, observaciones='Avisó que quizás hace no-show')

        self._accion(turno, 'cancelar')
        db.session.refresh(turno)

        self.assertEqual(turno.cierre_motivo, 'cancelado')
        self.assertEqual(estado_turno(turno), 'cancelado')

    def test_turnos_viejos_sin_motivo_leen_las_notas(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio)
        turno.estado = 'cancelada'
        turno.observaciones = 'No-show desde peluquería/barbería.'
        db.session.commit()

        self.assertEqual(estado_turno(turno), 'no_show')


class TestWhatsApp(TurnoTestBase):
    def test_boton_arma_mensaje_con_telefono_del_cliente(self):
        cliente = Cliente(nombre='Ana Pérez', telefono='0981 123 456', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.commit()
        turno = self._turno(self._crear_servicio(nombre='Corte clásico'), cliente_id=str(cliente.id_cliente))

        html = self._gestion(turno)

        self.assertIn('https://wa.me/595981123456?text=', html)
        enlace = html.split('https://wa.me/595981123456?text=', 1)[1].split('"', 1)[0]
        texto = unquote(enlace.replace('&amp;', '&'))
        self.assertIn('Hola Ana', texto)
        self.assertIn('Corte clásico', texto)
        self.assertIn('10:00', texto)

    def test_sin_telefono_pide_cargarlo(self):
        cliente = Cliente(nombre='Sin Tel', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.commit()
        turno = self._turno(self._crear_servicio(), cliente_id=str(cliente.id_cliente))

        html = self._gestion(turno)

        self.assertNotIn('wa.me', html)
        self.assertIn('Cargá el teléfono de Sin Tel', html)


if __name__ == '__main__':
    unittest.main()
