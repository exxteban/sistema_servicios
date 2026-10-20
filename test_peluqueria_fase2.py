"""Fase 2 del plan de peluquería: alta de turno simple."""
import json
import re
import unittest
from datetime import timedelta

from app import db
from app.models import AgendaActividad, Configuracion, ServicioPrecioOpcion
from app.services.peluqueria_horario import horarios_turno_peluqueria
from app.utils.helpers import today_local
from test_peluqueria_fase1 import PeluqueriaTestBase


def _config_alpine(html):
    """Lee los arrays que el template le pasa a peluqueriaTurnoRapido(...)."""
    valores = {}
    for clave in ('catalogo', 'tiposBase', 'horarios'):
        match = re.search(rf'^\s*{clave}: (.*),$', html, re.MULTILINE)
        valores[clave] = json.loads(match.group(1)) if match else None
    return valores


class TestBotonesDelCatalogo(PeluqueriaTestBase):
    def test_botones_son_los_servicios_del_catalogo(self):
        servicio = self._crear_servicio(precio=45000, nombre='Fade', turno_rapido_tipo=None)
        servicio.duracion_minutos = 40
        db.session.commit()

        html = self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True)
        config = _config_alpine(html)

        self.assertEqual([item['nombre'] for item in config['catalogo']], ['Fade'])
        self.assertEqual(config['catalogo'][0]['duracion'], 40)
        self.assertIn('45.000', config['catalogo'][0]['precio_label'])
        self.assertEqual(config['tiposBase'], [])
        self.assertNotIn('Cargá tus servicios para verlos acá', html)

    def test_catalogo_vacio_muestra_botones_fijos_y_aviso(self):
        html = self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True)
        config = _config_alpine(html)

        self.assertEqual(config['catalogo'], [])
        self.assertEqual(len(config['tiposBase']), 7)
        self.assertIn('Cargá tus servicios para verlos acá', html)
        self.assertIn('/servicios/', html)

    def test_variantes_viajan_con_el_servicio(self):
        servicio = self._crear_servicio(nombre='Corte')
        db.session.add_all([
            ServicioPrecioOpcion(id_servicio=servicio.id_servicio, etiqueta='Caballero', costo=0, precio=35000, orden=0, activo=True),
            ServicioPrecioOpcion(id_servicio=servicio.id_servicio, etiqueta='Niño', costo=0, precio=25000, orden=1, activo=True),
        ])
        db.session.commit()

        config = _config_alpine(self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True))

        self.assertEqual([op['etiqueta'] for op in config['catalogo'][0]['opciones']], ['Caballero', 'Niño'])

    def test_pantalla_sin_terminos_tecnicos(self):
        self._crear_servicio()

        html = self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True)

        for termino in ('Vinculado', 'Sin vincular al catálogo', 'Base cobrable', 'Servicio base a cobrar'):
            self.assertNotIn(termino, html)
        self.assertIn('Cambiar precio', html)

    def test_turno_desde_catalogo_sin_tipo_rapido(self):
        servicio = self._crear_servicio(nombre='Perfilado', turno_rapido_tipo=None)

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data=self._datos_turno(servicio, servicio_turno_id='', servicio_turno_nombre='Perfilado', accion='crear_y_cobrar'),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'agenda_turno_servicio_id={servicio.id_servicio}', response.headers['Location'])


class TestHorariosOcupados(PeluqueriaTestBase):
    def _ocupados(self, fecha=None, profesional_id=None):
        return self.client.get(
            '/agenda/api/peluqueria/ocupados',
            query_string={
                'profesional_id': profesional_id or self.admin.id_usuario,
                'fecha': (fecha or today_local()).isoformat(),
            },
        )

    def test_devuelve_rangos_del_profesional_en_el_dia(self):
        servicio = self._crear_servicio()
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora='10:00'))

        response = self._ocupados()

        self.assertEqual(response.status_code, 200)
        ocupados = response.get_json()['ocupados']
        self.assertEqual(len(ocupados), 1)
        self.assertEqual((ocupados[0]['inicio'], ocupados[0]['fin']), (600, 630))

    def test_no_cuenta_turnos_cancelados_ni_de_otro_dia(self):
        servicio = self._crear_servicio()
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora='10:00'))
        AgendaActividad.query.filter_by(tipo='cita').one().estado = 'cancelada'
        db.session.commit()
        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora='11:00'))

        self.assertEqual(self._ocupados(fecha=today_local() + timedelta(days=1)).get_json()['ocupados'], [])
        ocupados = self._ocupados().get_json()['ocupados']
        self.assertEqual([rango['inicio'] for rango in ocupados], [660])

    def test_fecha_o_profesional_invalidos(self):
        self.assertEqual(
            self.client.get('/agenda/api/peluqueria/ocupados', query_string={'profesional_id': self.admin.id_usuario, 'fecha': 'x'}).status_code,
            400,
        )
        self.assertEqual(self._ocupados(profesional_id=999999).status_code, 404)


class TestHorarioConfigurable(PeluqueriaTestBase):
    def test_por_defecto_es_el_horario_de_siempre(self):
        horarios = horarios_turno_peluqueria()

        self.assertEqual(horarios[0], '08:00')
        self.assertEqual(horarios[-1], '20:30')
        self.assertEqual(len(horarios), 26)

    def test_guardar_horario_cambia_la_grilla(self):
        response = self.client.post(
            '/agenda/turnos/peluqueria/horario',
            data={'apertura': '09:00', 'cierre': '12:00', 'intervalo': '45'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Configuracion.obtener('peluqueria_hora_apertura'), '09:00')
        config = _config_alpine(self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True))
        self.assertEqual(config['horarios'], ['09:00', '09:45', '10:30', '11:15'])

    def test_horario_invalido_no_se_guarda(self):
        response = self.client.post(
            '/agenda/turnos/peluqueria/horario',
            data={'apertura': '18:00', 'cierre': '09:00', 'intervalo': '30'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('posterior a la de apertura', response.get_data(as_text=True))
        self.assertIsNone(Configuracion.obtener('peluqueria_hora_apertura'))

    def test_valor_roto_en_configuracion_vuelve_al_default(self):
        Configuracion.establecer('peluqueria_intervalo_minutos', 'abc')

        self.assertEqual(horarios_turno_peluqueria()[:2], ('08:00', '08:30'))


class TestVolverAUnLugarUtil(PeluqueriaTestBase):
    def test_crear_turno_vuelve_a_la_agenda_del_dia(self):
        servicio = self._crear_servicio()

        response = self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], f'/agenda/peluqueria/dia?fecha={today_local().isoformat()}')


if __name__ == '__main__':
    unittest.main()
