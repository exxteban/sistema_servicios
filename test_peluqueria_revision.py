"""Revisión del plan de peluquería: errores encontrados después de cerrar las 6 fases."""
import unittest
from urllib.parse import parse_qs, urlparse

from app import db
from app.models import AgendaActividad, MovimientoCaja, ServicioPrecioOpcion
from app.services.dashboard_servicios import obtener_resumen_cobros_pendientes_dashboard
from test_peluqueria_fase4 import TurnoTestBase


class TestRevisionPeluqueria(TurnoTestBase):
    def _cobros_pendientes(self):
        with self.app.test_request_context('/'):
            return obtener_resumen_cobros_pendientes_dashboard(limit=None)['items']

    def test_precio_manual_sin_cliente_se_conserva_al_cobrar_despues(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio, precio_manual='65000')
        self.assertEqual(float(turno.precio_manual), 65000)

        cobro = self.client.get(f'/agenda/turnos/peluqueria/{turno.id}/cobrar')
        params = parse_qs(urlparse(cobro.headers['Location']).query)
        self.assertEqual(float(params['agenda_turno_precio_manual'][0]), 65000)

        item = self._cobros_pendientes()[0]
        self.assertEqual(item['subtotal'], 65000)
        self.assertIn('agenda_turno_precio_manual=65000', item['cobrar_url'])

    def test_servicio_solo_con_variantes_aparece_en_cobros_pendientes(self):
        servicio = self._crear_servicio(precio=0)
        opcion = ServicioPrecioOpcion(id_servicio=servicio.id_servicio, etiqueta='Caballero', costo=0, precio=35000, orden=0, activo=True)
        db.session.add(opcion)
        db.session.commit()
        turno = self._turno(servicio, servicio_precio_opcion_id=str(opcion.id_opcion_precio))

        items = self._cobros_pendientes()

        self.assertEqual([item['agenda_actividad_id'] for item in items], [turno.id])
        self.assertEqual(items[0]['subtotal'], 35000)

    def test_sena_sin_cliente_no_puede_superar_el_precio(self):
        servicio = self._crear_servicio(precio=50000)
        sesion = self._abrir_caja()
        turno = self._turno(servicio)

        self._accion(turno, 'sena', monto_sena='60000')

        db.session.refresh(turno)
        self.assertIsNone(turno.sena_monto)
        self.assertEqual(MovimientoCaja.query.filter_by(id_sesion_caja=sesion.id_sesion).count(), 0)

    def test_turno_cobrado_por_adelantado_sigue_ocupando_el_horario(self):
        servicio = self._crear_servicio()
        self._abrir_caja()
        turno = self._turno(servicio, hora='18:00')
        self._cobrar_en_pos(turno, servicio)
        db.session.refresh(turno)
        self.assertEqual(turno.estado, 'hecha')

        response = self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora='18:00'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('ya tiene un turno en ese horario', response.get_data(as_text=True))
        self.assertEqual(AgendaActividad.query.filter_by(tipo='cita').count(), 1)

    def test_turno_terminado_libera_el_horario(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio, hora='18:00')
        self._accion(turno, 'terminar')

        self.client.post('/agenda/turnos/peluqueria/crear', data=self._datos_turno(servicio, hora='18:00'))

        self.assertEqual(AgendaActividad.query.filter_by(tipo='cita').count(), 2)

    def test_turno_cancelado_no_ofrece_registrar_sena(self):
        servicio = self._crear_servicio()
        turno = self._turno(servicio)
        self._accion(turno, 'cancelar')

        html = self._gestion(turno)

        self.assertNotIn('name="monto_sena"', html)
        self.assertIn('reprogramalo para registrar una seña', html)

    def test_reprogramar_turno_cancelado_en_atencion_vuelve_agendado(self):
        from app.services.peluqueria_turno_estado import AGENDADO, estado_turno
        from app.utils.helpers import today_local

        servicio = self._crear_servicio()
        turno = self._turno(servicio)
        self._accion(turno, 'empezar')
        self._accion(turno, 'cancelar')

        self._accion(turno, 'reprogramar', fecha=today_local().isoformat(), hora='18:00', duracion='30')

        db.session.refresh(turno)
        self.assertIsNone(turno.atencion_inicio)
        self.assertEqual(estado_turno(turno), AGENDADO)

    def test_dashboard_servicios_usa_la_moneda_configurada(self):
        from app.models import Configuracion

        for clave, valor in {'moneda_simbolo': 'R$', 'moneda_decimales': '2', 'moneda_sep_miles': '.',
                             'moneda_sep_decimal': ',', 'moneda_locale': 'pt-BR'}.items():
            Configuracion.establecer(clave, valor, 'test')
        db.session.commit()
        self._turno(self._crear_servicio(precio=50000))

        html = self.client.get('/').get_data(as_text=True)

        self.assertIn('R$ 50.000,00', html)  # Cobros pendientes
        self.assertIn('R$ 0,00', html)  # Caja y KPI de cobrado
        self.assertIn('"simbolo": "R$"', html)  # refresco en vivo de las tarjetas
        # Lo visible (sin scripts: el de totales es compartido con el dashboard general).
        import re
        self.assertNotIn('Gs. ', re.sub(r'<script.*?</script>', '', html, flags=re.S))

    def test_profesional_atendiendo_turno_sin_cliente_figura_ocupado(self):
        from app.services.dashboard_servicios import obtener_estado_profesionales_dashboard
        from app.utils.helpers import today_local

        turno = self._turno(self._crear_servicio(nombre='Barba express'))
        self._accion(turno, 'empezar')

        with self.app.test_request_context('/'):
            ocupados, detalles = obtener_estado_profesionales_dashboard([self.admin], can_ver_agenda=True, today=today_local())

        self.assertEqual(ocupados, {int(self.admin.id_usuario)})
        detalle = detalles[str(self.admin.id_usuario)]
        self.assertEqual(detalle['servicio_nombre'], 'Barba express')
        self.assertEqual(detalle['cliente_nombre'], 'Consumidor Final')


if __name__ == '__main__':
    unittest.main()
