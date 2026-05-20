import unittest
from datetime import date
from decimal import Decimal

from app import create_app, db
from app.models import Configuracion, Usuario
from control_de_empleados import (
    CLAVE_MODULO_CONTROL_EMPLEADOS,
    DESC_MODULO_CONTROL_EMPLEADOS,
)
from control_de_empleados.models import Empleado, EmpleadoMovimientoSalario, EmpleadoPago
from control_de_empleados.services.aguinaldo import calcular_resumen_aguinaldo


class TestControlEmpleadosAguinaldo(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        self.admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(
            CLAVE_MODULO_CONTROL_EMPLEADOS,
            True,
            DESC_MODULO_CONTROL_EMPLEADOS,
        )

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id_usuario)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_calcula_aguinaldo_diario_desde_fecha_ingreso(self):
        empleado = Empleado(
            nombre_completo='Empleado Diario',
            salario_base=Decimal('3000000.00'),
            salario_incluye_ips=True,
            tipo_pago='mensual',
            fecha_ingreso=date(2026, 3, 16),
            activo=True,
        )
        db.session.add(empleado)
        db.session.flush()
        db.session.add(
            EmpleadoMovimientoSalario(
                id_empleado=empleado.id_empleado,
                periodo='2026-03',
                fecha_movimiento=date(2026, 3, 18),
                tipo='bono',
                concepto='Bono productividad',
                monto=Decimal('1200000.00'),
                incide_aguinaldo=True,
            )
        )
        db.session.commit()

        resumen = calcular_resumen_aguinaldo(empleado, '2026-03', hoy=date(2026, 3, 20))

        self.assertEqual(resumen['fecha_corte'], date(2026, 3, 20))
        self.assertEqual(resumen['aguinaldo_acumulado'], Decimal('56451.61'))
        self.assertEqual(resumen['tasa_diaria_actual'], Decimal('11290.32'))
        self.assertEqual(resumen['ips_obrero_estimado'], Decimal('270000.00'))
        self.assertEqual(resumen['salario_neto_estimado'], Decimal('2730000.00'))

    def test_movimiento_no_marcado_no_suma_aguinaldo(self):
        empleado = Empleado(
            nombre_completo='Empleado Sin Bono',
            salario_base=Decimal('4000000.00'),
            tipo_pago='mensual',
            fecha_ingreso=date(2026, 4, 1),
            activo=True,
        )
        db.session.add(empleado)
        db.session.flush()
        db.session.add(
            EmpleadoMovimientoSalario(
                id_empleado=empleado.id_empleado,
                periodo='2026-04',
                fecha_movimiento=date(2026, 4, 9),
                tipo='bono',
                concepto='Bono no computable',
                monto=Decimal('100000.00'),
                incide_aguinaldo=False,
            )
        )
        db.session.add(
            EmpleadoPago(
                id_empleado=empleado.id_empleado,
                periodo='2026-04',
                fecha_pago=date(2026, 4, 9),
                salario_base=Decimal('4000000.00'),
                total_extras=Decimal('100000.00'),
                total_descuentos=Decimal('100000.00'),
                total_pagado=Decimal('4000000.00'),
            )
        )
        db.session.commit()

        resumen = calcular_resumen_aguinaldo(empleado, '2026-04', hoy=date(2026, 4, 9))

        self.assertEqual(resumen['meses'][3]['remuneracion_proyectada_mes'], Decimal('4000000.00'))
        self.assertEqual(resumen['meses'][3]['fuente'], 'pago_registrado')

    def test_reinicia_calculo_en_enero_con_anio_nuevo(self):
        empleado = Empleado(
            nombre_completo='Empleado Reinicio',
            salario_base=Decimal('2400000.00'),
            tipo_pago='mensual',
            fecha_ingreso=date(2025, 1, 1),
            activo=True,
        )
        db.session.add(empleado)
        db.session.flush()
        db.session.add(
            EmpleadoPago(
                id_empleado=empleado.id_empleado,
                periodo='2026-12',
                fecha_pago=date(2027, 1, 5),
                salario_base=Decimal('2600000.00'),
                total_extras=Decimal('400000.00'),
                total_descuentos=Decimal('0.00'),
                total_pagado=Decimal('3000000.00'),
            )
        )
        db.session.commit()

        resumen = calcular_resumen_aguinaldo(empleado, '2027-01', hoy=date(2027, 1, 10))

        self.assertEqual(resumen['anio'], 2027)
        self.assertEqual(resumen['aguinaldo_acumulado'], Decimal('64516.13'))
        self.assertEqual(resumen['aguinaldo_proyectado'], Decimal('2400000.00'))
        self.assertEqual(resumen['meses'][0]['dias_computados'], 10)
        self.assertEqual(resumen['meses'][1]['dias_computados'], 0)

    def test_jefe_puede_marcar_movimiento_para_aguinaldo_despues(self):
        empleado = Empleado(
            nombre_completo='Empleado Toggle',
            salario_base=Decimal('4000000.00'),
            tipo_pago='mensual',
            fecha_ingreso=date(2026, 4, 1),
            activo=True,
        )
        db.session.add(empleado)
        db.session.flush()
        movimiento = EmpleadoMovimientoSalario(
            id_empleado=empleado.id_empleado,
            periodo='2026-04',
            fecha_movimiento=date(2026, 4, 9),
            tipo='bono',
            concepto='Bono revisable',
            monto=Decimal('100000.00'),
            incide_aguinaldo=False,
        )
        db.session.add(movimiento)
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/movimientos/{movimiento.id_movimiento}/aguinaldo',
            data={
                'periodo': '2026-04',
                'tab': 'resumen',
                'incide_aguinaldo': '1',
            },
            follow_redirects=False,
        )

        actualizado = EmpleadoMovimientoSalario.query.get(movimiento.id_movimiento)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(actualizado.incide_aguinaldo)

    def test_detalle_renderiza_tab_de_aguinaldo(self):
        empleado = Empleado(
            nombre_completo='Empleado Vista',
            salario_base=Decimal('2500000.00'),
            salario_incluye_ips=True,
            tipo_pago='mensual',
            fecha_ingreso=date(2026, 1, 1),
            activo=True,
        )
        db.session.add(empleado)
        db.session.commit()

        response = self.client.get(
            f'/control-empleados/{empleado.id_empleado}?periodo=2026-04&tab=aguinaldo'
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Control de aguinaldo', html)
        self.assertIn('El aguinaldo no descuenta IPS.', html)
        self.assertIn('Sueldo con IPS incluido', html)
        self.assertIn('Base aguinaldo', html)

    def test_detalle_aguinaldo_tolera_periodo_invalido(self):
        empleado = Empleado(
            nombre_completo='Empleado Periodo',
            salario_base=Decimal('2500000.00'),
            tipo_pago='mensual',
            fecha_ingreso=date(2026, 1, 1),
            activo=True,
        )
        db.session.add(empleado)
        db.session.commit()

        response = self.client.get(
            f'/control-empleados/{empleado.id_empleado}?periodo=2026-13&tab=aguinaldo'
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Control de aguinaldo', html)


if __name__ == '__main__':
    unittest.main()
