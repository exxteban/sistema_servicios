import unittest

from app import create_app, db


class TestAgendaTurnosPeluqueria(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_servicios_cobrables_incluyen_variantes_aunque_el_precio_base_sea_cero(self):
        from app.models import Servicio, ServicioPrecioOpcion
        from app.services.agenda_turnos_peluqueria import build_turno_peluqueria_chargeable_catalog_services

        servicio = Servicio(
            codigo='SRV-TURNO-VAR-001',
            nombre='Color fantasia',
            categoria='Color',
            costo=15000,
            precio=0,
            duracion_minutos=90,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='color',
        )
        db.session.add(servicio)
        db.session.flush()

        db.session.add(
            ServicioPrecioOpcion(
                id_servicio=int(servicio.id_servicio),
                etiqueta='Cabello largo',
                costo=22000,
                precio=65000,
                orden=1,
                activo=True,
            )
        )
        db.session.commit()

        items = build_turno_peluqueria_chargeable_catalog_services()
        servicio_payload = next(
            (item for item in items if int(item['id']) == int(servicio.id_servicio)),
            None,
        )

        self.assertIsNotNone(servicio_payload)
        self.assertEqual(float(servicio_payload.get('precio') or 0), 0.0)
        self.assertEqual(len(servicio_payload.get('precios_opciones') or []), 1)
        self.assertEqual(servicio_payload['precios_opciones'][0]['etiqueta'], 'Cabello largo')
        self.assertEqual(float(servicio_payload['precios_opciones'][0]['precio'] or 0), 65000.0)
