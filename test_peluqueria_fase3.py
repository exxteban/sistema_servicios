"""Fase 3 del plan de peluquería: agenda del día por profesional."""
import unittest
from app import db
from app.models import AgendaActividad
from app.utils.helpers import today_local
from test_peluqueria_fase1 import PeluqueriaTestBase

FECHA = '2030-01-10'


class AgendaDiaTestBase(PeluqueriaTestBase):
    def _turno(self, servicio, hora, fecha=FECHA, **extra):
        datos = self._datos_turno(servicio, hora=hora, **extra)
        datos['fecha_inicio'] = f'{fecha}T{hora}'
        self.client.post('/agenda/turnos/peluqueria/crear', data=datos)
        return AgendaActividad.query.filter_by(tipo='cita').order_by(AgendaActividad.id.desc()).first()

    def _agenda(self, fecha=FECHA):
        response = self.client.get('/agenda/peluqueria/dia', query_string={'fecha': fecha})
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)


class TestAgendaDelDia(AgendaDiaTestBase):
    def test_columna_por_profesional_y_turnos_del_dia(self):
        from app.routes.agenda.visibilidad import query_usuarios_agenda_visibles

        profesionales = query_usuarios_agenda_visibles().all()
        servicio = self._crear_servicio(nombre='Corte fade')
        turno = self._turno(servicio, '10:00', cliente_nuevo_nombre='Lucas Recepcion')
        self._turno(servicio, '11:00', fecha='2030-01-11', cliente_nuevo_nombre='Otro Dia')

        html = self._agenda()

        self.assertIn('Agenda del día', html)
        for profesional in profesionales:
            self.assertIn(profesional.nombre_completo or profesional.username, html)
        self.assertEqual(html.count('agenda-dia-head agenda-dia-col'), len(profesionales))
        self.assertIn('Lucas Recepcion', html)
        self.assertNotIn('Otro Dia', html)
        self.assertIn(f'/agenda/turnos/peluqueria/{turno.id}/gestionar', html)
        self.assertIn('agenda-dia-turno--pendiente', html)

    def test_hueco_libre_abre_alta_con_profesional_fecha_y_hora(self):
        html = self._agenda()
        url = f'/agenda/turnos/peluqueria/nuevo?profesional_id={self.admin.id_usuario}&amp;fecha={FECHA}&amp;hora=09:30'
        self.assertIn(url, html)

        alta = self.client.get(url.replace('&amp;', '&')).get_data(as_text=True)

        self.assertIn(f'"profesional_id": {self.admin.id_usuario}', alta)
        self.assertIn('"hora": "09:30"', alta)
        self.assertIn(f'"fecha": "{FECHA}"', alta)

    def test_dia_pasado_no_ofrece_huecos(self):
        html = self._agenda(fecha='2020-01-10')

        self.assertNotIn('app-tab-link agenda-dia-libre', html)
        self.assertIn('app-tab-link agenda-dia-libre', self._agenda())

    def test_turno_ocupa_las_filas_de_su_duracion(self):
        servicio = self._crear_servicio()
        self._turno(servicio, '10:00', duracion='60')

        html = self._agenda()

        # 08:00 a 10:00 son 4 filas de 52px; 60 minutos son 2 filas (104px - 4 de margen).
        self.assertIn('style="top: 210px; height: 100px;"', html)

    def test_cancelados_van_aparte_y_liberan_el_hueco(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio, '15:00', cliente_nuevo_nombre='Cliente Cancela')
        turno.estado = 'cancelada'
        db.session.commit()

        html = self._agenda()

        self.assertIn('Cancelados y no-show', html)
        self.assertIn('Cliente Cancela', html)
        self.assertNotIn('agenda-dia-turno--cancelada', html)

    def test_flechas_y_fecha_invalida(self):
        html = self._agenda()
        self.assertIn('fecha=2030-01-09', html)
        self.assertIn('fecha=2030-01-11', html)

        self.assertIn(today_local().strftime('%d/%m/%Y'), self._agenda(fecha='no-es-fecha'))

    def test_turno_fuera_de_horario_amplia_la_grilla(self):
        servicio = self._crear_servicio()
        self._turno(servicio, '06:30')

        html = self._agenda()

        self.assertIn('>06:30</div>', html)

    def test_crear_turno_vuelve_a_la_agenda_de_ese_dia(self):
        servicio = self._crear_servicio()
        datos = self._datos_turno(servicio)
        datos['fecha_inicio'] = f'{FECHA}T09:00'

        response = self.client.post('/agenda/turnos/peluqueria/crear', data=datos)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], f'/agenda/peluqueria/dia?fecha={FECHA}')


class TestDashboardApuntaALaAgendaDelDia(AgendaDiaTestBase):
    def test_boton_agenda_del_dashboard_peluqueria(self):
        html = self.client.get('/').get_data(as_text=True)

        self.assertIn('href="/agenda/peluqueria/dia"', html)

    def test_mapa_del_dia_muestra_turnos_cobrados(self):
        from app.models import MetodoPago

        self._abrir_caja()
        servicio = self._crear_servicio(precio=40000)
        datos = self._datos_turno(servicio, hora='10:00', cliente_nuevo_nombre='Cliente Mapa')
        self.client.post('/agenda/turnos/peluqueria/crear', data=datos)
        turno = AgendaActividad.query.filter_by(tipo='cita').one()
        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        response = self.client.post('/ventas/procesar', json={
            'items': [{'tipo': 'servicio', 'id_servicio': int(servicio.id_servicio), 'cantidad': 1, 'precio': 40000, 'precio_manual': False}],
            'pagos': [{'id_metodo_pago': int(metodo.id_metodo_pago), 'monto': 40000}],
            'id_cliente': int(turno.cliente_id),
            'id_usuario_vendedor': int(self.admin.id_usuario),
            'agenda_actividad_id': int(turno.id),
            'client_request_id': 'mapa-dia-cobrado',
        })
        self.assertTrue((response.get_json() or {}).get('success'))

        html = self.client.get('/').get_data(as_text=True)

        self.assertIn('Mapa del día', html)
        self.assertIn('Cliente Mapa', html)
        self.assertIn('>Cobrado<', html)
        agenda = self._agenda(fecha=today_local().isoformat())
        self.assertIn('agenda-dia-turno--hecha', agenda)
        self.assertIn('Cliente Mapa', agenda)


if __name__ == '__main__':
    unittest.main()
