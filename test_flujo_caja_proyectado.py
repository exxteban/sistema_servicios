import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from app import create_app, db
from sqlalchemy.exc import IntegrityError


class TestFlujoCajaProyectado(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id_usuario)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_prepara_semana_y_muestra_tesoreria(self):
        response = self.client.post(
            '/flujo-caja/preparar-semana',
            data={
                'semana': '2026-05-11',
                'saldo_inicial': '500000',
                'notas': 'Semana clave',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Flujo de caja proyectado'.encode(), response.data)
        self.assertIn('Semana clave'.encode(), response.data)
        self.assertIn('Generar PDF'.encode(), response.data)
        self.assertIn('Imprimir'.encode(), response.data)
        self.assertIn('auto_print=1'.encode(), response.data)

    def test_reporte_imprimible_muestra_resumen_y_movimientos(self):
        self.client.post(
            '/flujo-caja/preparar-semana',
            data={'semana': '2026-05-11', 'saldo_inicial': '250000', 'notas': 'Semana comercial'},
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-11',
                'tipo': 'ingreso',
                'categoria': 'ventas',
                'concepto': 'Cobros mostrador',
                'monto_estimado': '900000',
                'estado': 'confirmado',
            },
        )

        response = self.client.get('/flujo-caja/imprimir?semana=2026-05-11')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Semaforo de liquidez'.encode(), response.data)
        self.assertIn('Resumen diario'.encode(), response.data)
        self.assertIn('Cobros mostrador'.encode(), response.data)
        self.assertIn('Generar PDF'.encode(), response.data)

    def test_detecta_riesgo_de_liquidez_semanal(self):
        from flujo_caja.models import FlujoCajaMovimiento
        from flujo_caja.services import construir_contexto

        self.client.post(
            '/flujo-caja/preparar-semana',
            data={'semana': '2026-05-11', 'saldo_inicial': '0'},
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-11',
                'tipo': 'ingreso',
                'categoria': 'ventas',
                'concepto': 'Ventas previstas',
                'monto_estimado': '6000000',
                'estado': 'estimado',
            },
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-12',
                'tipo': 'egreso',
                'categoria': 'proveedores',
                'concepto': 'Pago proveedor',
                'monto_estimado': '7000000',
                'estado': 'confirmado',
            },
        )

        contexto = construir_contexto('2026-05-11')
        self.assertEqual(FlujoCajaMovimiento.query.count(), 2)
        self.assertEqual(contexto['resumen']['resultado'], Decimal('-1000000.00'))
        self.assertEqual(contexto['resumen']['semaforo_estado'], 'rojo')
        self.assertIn('Martes', contexto['resumen']['semaforo_mensaje'])

        response = self.client.get('/flujo-caja/?semana=2026-05-11&tab=semana')
        self.assertEqual(response.status_code, 200)
        self.assertIn('El Martes la caja queda en -Gs. 1.000.000.'.encode(), response.data)
        self.assertIn('Necesitas cobrar o mover pagos por Gs. 1.000.000 antes de ese dia.'.encode(), response.data)
        self.assertIn('Pago proveedor'.encode(), response.data)

    def test_explica_cuando_la_semana_cierra_bien_pero_falta_caja_antes(self):
        from flujo_caja.services import construir_contexto

        self.client.post(
            '/flujo-caja/preparar-semana',
            data={'semana': '2026-05-11', 'saldo_inicial': '1000000'},
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-11',
                'tipo': 'egreso',
                'categoria': 'proveedores',
                'concepto': 'Pago lunes',
                'monto_estimado': '5000000',
                'estado': 'confirmado',
            },
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-13',
                'tipo': 'ingreso',
                'categoria': 'ventas',
                'concepto': 'Cobro miercoles',
                'monto_estimado': '7000000',
                'estado': 'estimado',
            },
        )

        contexto = construir_contexto('2026-05-11')

        self.assertEqual(contexto['resumen']['resultado'], Decimal('2000000.00'))
        self.assertEqual(contexto['resumen']['saldo_final'], Decimal('3000000.00'))
        self.assertEqual(contexto['resumen']['semaforo_mensaje'], 'El Lunes la caja queda en -Gs. 4.000.000.')
        self.assertIn('La semana termina con saldo positivo', contexto['resumen']['recomendacion'])

    def test_actualiza_monto_real_y_comparativo_solo_con_realizados(self):
        from flujo_caja.models import FlujoCajaMovimiento
        from flujo_caja.services import construir_contexto

        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-11',
                'tipo': 'ingreso',
                'categoria': 'ventas',
                'concepto': 'Cobro pendiente',
                'monto_estimado': '100000',
                'estado': 'estimado',
            },
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-12',
                'tipo': 'egreso',
                'categoria': 'proveedores',
                'concepto': 'Pago real',
                'monto_estimado': '50000',
                'estado': 'confirmado',
            },
        )

        mov = FlujoCajaMovimiento.query.filter_by(concepto='Pago real').first()
        response = self.client.post(
            f'/flujo-caja/movimientos/{mov.id_flujo_movimiento}/estado',
            data={
                'estado': 'realizado',
                'monto_real': '70000',
                'tab': 'movimientos',
            },
            follow_redirects=True,
        )
        comparativo = self.client.get('/flujo-caja/?semana=2026-05-11&tab=comparativo')

        db.session.refresh(mov)
        contexto = construir_contexto('2026-05-11')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mov.estado, 'realizado')
        self.assertEqual(mov.monto_real, Decimal('70000.00'))
        self.assertEqual(contexto['resumen']['resultado_realizado'], Decimal('-70000.00'))
        self.assertEqual(contexto['resumen']['resultado_estimado_realizado'], Decimal('-50000.00'))
        self.assertEqual(contexto['resumen']['diferencia_real_vs_estimado'], Decimal('-20000.00'))
        self.assertEqual(contexto['dias'][1]['diferencia_real_estimado'], Decimal('-20000.00'))
        self.assertEqual(contexto['dias'][0]['diferencia_real_estimado'], Decimal('0.00'))
        self.assertIn('name="monto_real"'.encode(), response.data)
        self.assertIn('solo sobre movimientos ya realizados'.encode(), comparativo.data)

    def test_obtener_semana_actual_reusa_semana_si_hay_colision_de_unicidad(self):
        from datetime import date

        from flujo_caja.models import FlujoCajaSemana
        from flujo_caja.services import obtener_semana_actual

        semana_existente = FlujoCajaSemana(
            cliente_id=0,
            fecha_inicio=date(2026, 5, 11),
            fecha_fin=date(2026, 5, 17),
            nombre='Semana 11/05/2026',
            saldo_inicial_estimado=Decimal('0.00'),
        )
        query_mock = Mock()
        query_mock.filter.return_value.order_by.return_value.all.side_effect = [[], [semana_existente]]

        with patch('flujo_caja.services.aplicar_scope_cliente', return_value=query_mock):
            with patch('flujo_caja.services.db.session.flush', side_effect=IntegrityError('dup', {}, None)):
                semana = obtener_semana_actual('2026-05-11')

        self.assertIs(semana, semana_existente)

    def test_consolida_semanas_duplicadas_en_una_sola_semana(self):
        from datetime import date

        from sqlalchemy import text

        from flujo_caja.models import FlujoCajaMovimiento, FlujoCajaSemana
        from flujo_caja.services import obtener_o_crear_semana

        db.session.execute(text(
            """
            INSERT INTO flujo_caja_semanas (
                cliente_id, fecha_inicio, fecha_fin, nombre, saldo_inicial_estimado,
                estado, notas, fecha_creacion, fecha_actualizacion
            ) VALUES (
                NULL, :fecha_inicio, :fecha_fin, :nombre, :saldo_inicial,
                :estado, :notas, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ), {
            'fecha_inicio': date(2026, 5, 11),
            'fecha_fin': date(2026, 5, 17),
            'nombre': 'Semana A',
            'saldo_inicial': 0,
            'estado': 'abierta',
            'notas': None,
        })
        db.session.execute(text(
            """
            INSERT INTO flujo_caja_semanas (
                cliente_id, fecha_inicio, fecha_fin, nombre, saldo_inicial_estimado,
                estado, notas, fecha_creacion, fecha_actualizacion
            ) VALUES (
                NULL, :fecha_inicio, :fecha_fin, :nombre, :saldo_inicial,
                :estado, :notas, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ), {
            'fecha_inicio': date(2026, 5, 11),
            'fecha_fin': date(2026, 5, 17),
            'nombre': 'Semana B',
            'saldo_inicial': 250000,
            'estado': 'cerrada',
            'notas': 'Consolidar',
        })
        db.session.commit()

        semana_a = FlujoCajaSemana.query.filter_by(nombre='Semana A').first()
        semana_b = FlujoCajaSemana.query.filter_by(nombre='Semana B').first()

        db.session.add_all([
            FlujoCajaMovimiento(
                id_flujo_semana=semana_a.id_flujo_semana,
                fecha=date(2026, 5, 11),
                tipo='ingreso',
                categoria='ventas',
                concepto='Ingreso A',
                monto_estimado=Decimal('1000.00'),
                estado='estimado',
                origen='manual',
            ),
            FlujoCajaMovimiento(
                id_flujo_semana=semana_b.id_flujo_semana,
                fecha=date(2026, 5, 12),
                tipo='egreso',
                categoria='proveedores',
                concepto='Egreso B',
                monto_estimado=Decimal('500.00'),
                estado='confirmado',
                origen='manual',
            ),
        ])
        db.session.commit()

        semana = obtener_o_crear_semana(date(2026, 5, 11))
        db.session.commit()

        self.assertEqual(FlujoCajaSemana.query.filter_by(fecha_inicio=date(2026, 5, 11)).count(), 1)
        self.assertEqual(FlujoCajaMovimiento.query.count(), 2)
        self.assertEqual(semana.movimientos.count(), 2)
        self.assertEqual(semana.saldo_inicial_decimal(), Decimal('250000.00'))
        self.assertEqual(semana.notas, 'Consolidar')
        self.assertEqual(semana.estado, 'cerrada')

    def test_no_aplica_plantilla_archivada(self):
        from flujo_caja.models import FlujoCajaMovimiento, FlujoCajaPlantilla

        response = self.client.post(
            '/flujo-caja/plantillas',
            data={
                'nombre': 'Pago fijo',
                'concepto': 'Proveedor archivado',
                'monto_estimado': '100000',
                'tipo': 'egreso',
                'categoria': 'proveedores',
                'dia_semana': '1',
            },
        )
        self.assertEqual(response.status_code, 302)

        plantilla = FlujoCajaPlantilla.query.filter_by(nombre='Pago fijo').first()
        self.assertIsNotNone(plantilla)

        self.client.post(f'/flujo-caja/plantillas/{plantilla.id_flujo_plantilla}/eliminar')
        aplicar = self.client.post(
            f'/flujo-caja/plantillas/{plantilla.id_flujo_plantilla}/aplicar',
            data={'semana': '2026-05-11'},
        )

        self.assertEqual(aplicar.status_code, 404)
        self.assertEqual(FlujoCajaMovimiento.query.filter_by(concepto='Proveedor archivado').count(), 0)

    def test_plantilla_con_dia_invalido_no_rompe_y_cae_en_lunes(self):
        from flujo_caja.models import FlujoCajaPlantilla

        response = self.client.post(
            '/flujo-caja/plantillas',
            data={
                'nombre': 'Dia invalido',
                'concepto': 'Dia fallback',
                'monto_estimado': '1000',
                'tipo': 'egreso',
                'categoria': 'otros',
                'dia_semana': 'abc',
            },
            follow_redirects=True,
        )

        plantilla = FlujoCajaPlantilla.query.filter_by(nombre='Dia invalido').first()

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(plantilla)
        self.assertEqual(plantilla.dia_semana, 0)

    def test_semana_cerrada_bloquea_mutaciones(self):
        from datetime import date

        from flujo_caja.models import FlujoCajaMovimiento, FlujoCajaSemana

        self.client.post(
            '/flujo-caja/preparar-semana',
            data={'semana': '2026-05-11', 'saldo_inicial': '150000'},
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-12',
                'tipo': 'egreso',
                'categoria': 'proveedores',
                'concepto': 'Pago base',
                'monto_estimado': '50000',
                'estado': 'estimado',
            },
        )
        self.client.post('/flujo-caja/semana/estado', data={'semana': '2026-05-11', 'estado': 'cerrada'})

        agregar = self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-13',
                'tipo': 'ingreso',
                'categoria': 'ventas',
                'concepto': 'Ingreso bloqueado',
                'monto_estimado': '100000',
                'estado': 'estimado',
            },
            follow_redirects=True,
        )
        editar = self.client.post(
            '/flujo-caja/preparar-semana',
            data={'semana': '2026-05-11', 'saldo_inicial': '999999', 'notas': 'No deberia cambiar'},
            follow_redirects=True,
        )

        movimiento = FlujoCajaMovimiento.query.filter_by(concepto='Pago base').first()
        actualizar = self.client.post(
            f'/flujo-caja/movimientos/{movimiento.id_flujo_movimiento}/estado',
            data={'estado': 'realizado', 'monto_real': '70000', 'tab': 'movimientos'},
            follow_redirects=True,
        )
        eliminar = self.client.post(
            f'/flujo-caja/movimientos/{movimiento.id_flujo_movimiento}/eliminar',
            data={'tab': 'movimientos'},
            follow_redirects=True,
        )

        semana = FlujoCajaSemana.query.filter_by(fecha_inicio=date(2026, 5, 11)).first()
        db.session.refresh(movimiento)

        self.assertIn('La semana esta cerrada'.encode(), agregar.data)
        self.assertIn('La semana esta cerrada'.encode(), editar.data)
        self.assertIn('La semana esta cerrada'.encode(), actualizar.data)
        self.assertIn('La semana esta cerrada'.encode(), eliminar.data)
        self.assertEqual(FlujoCajaMovimiento.query.filter_by(concepto='Ingreso bloqueado').count(), 0)
        self.assertEqual(movimiento.estado, 'estimado')
        self.assertIsNone(movimiento.monto_real)
        self.assertEqual(FlujoCajaMovimiento.query.filter_by(concepto='Pago base').count(), 1)
        self.assertEqual(semana.saldo_inicial_decimal(), Decimal('150000.00'))
        self.assertIsNone(semana.notas)

    def test_comparativo_separa_cancelados_y_no_los_mezcla_con_totales(self):
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-11',
                'tipo': 'ingreso',
                'categoria': 'ventas',
                'concepto': 'Cobro vigente',
                'monto_estimado': '100000',
                'estado': 'realizado',
                'monto_real': '100000',
            },
        )
        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-12',
                'tipo': 'egreso',
                'categoria': 'otros',
                'concepto': 'Pago cancelado',
                'monto_estimado': '80000',
                'estado': 'cancelado',
            },
        )

        response = self.client.get('/flujo-caja/?semana=2026-05-11&tab=comparativo')

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cobro vigente', html)
        self.assertIn('Movimientos cancelados', html)
        self.assertIn('Pago cancelado', html)
        self.assertIn('Estos movimientos no afectan totales ni diferencias del comparativo.', html)

        detalle_activos = html.split('Movimientos cancelados')[0]
        self.assertNotIn('Pago cancelado', detalle_activos)

    def test_eliminar_movimiento_preserva_tab_origen(self):
        from flujo_caja.models import FlujoCajaMovimiento

        self.client.post(
            '/flujo-caja/movimientos',
            data={
                'semana': '2026-05-11',
                'fecha': '2026-05-11',
                'tipo': 'egreso',
                'categoria': 'otros',
                'concepto': 'Eliminar desde comparativo',
                'monto_estimado': '25000',
                'estado': 'estimado',
            },
        )

        mov = FlujoCajaMovimiento.query.filter_by(concepto='Eliminar desde comparativo').first()
        response = self.client.post(
            f'/flujo-caja/movimientos/{mov.id_flujo_movimiento}/eliminar',
            data={'tab': 'comparativo'},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=comparativo', response.headers['Location'])
        self.assertEqual(FlujoCajaMovimiento.query.filter_by(concepto='Eliminar desde comparativo').count(), 0)


if __name__ == '__main__':
    unittest.main()
