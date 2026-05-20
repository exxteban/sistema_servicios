import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app import create_app, db
from app.models import Cliente, Configuracion, Permiso, Rol, Usuario
from control_de_empleados import (
    CLAVE_EMPRESA_DIRECCION,
    CLAVE_EMPRESA_NOMBRE,
    CLAVE_EMPRESA_RUC,
    CLAVE_LLEGADA_TARDIA_DESCUENTO_DESDE,
    CLAVE_LLEGADA_TARDIA_DESCUENTO_MONTO,
    CLAVE_MODULO_CONTROL_EMPLEADOS,
    DESC_MODULO_CONTROL_EMPLEADOS,
)
from control_de_empleados.models import (
    Empleado,
    EmpleadoMovimientoSalario,
    EmpleadoFeriado,
    EmpleadoPago,
    EmpleadoTipoAusencia,
)
from control_de_empleados.models import EmpleadoAusencia


class TestControlEmpleadosFormActions(unittest.TestCase):
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

        self.empleado = Empleado(
            nombre_completo='Empleado Prueba',
            salario_base=Decimal('2500000.00'),
            tipo_pago='mensual',
            activo=True,
        )
        db.session.add(self.empleado)
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id_usuario)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_formulario_nuevo_define_action_explicita(self):
        response = self.client.get('/control-empleados/nuevo')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/control-empleados/nuevo"', html)

    def test_listado_switches_aplican_filtro_automaticamente(self):
        response = self.client.get('/control-empleados/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("estado_empleados_switch", html)
        self.assertIn("estado_empleados_texto", html)
        self.assertIn('value="activos"', html)
        self.assertIn("Desactivados", html)
        self.assertIn("this.form.requestSubmit()", html)

    def test_formulario_edicion_define_action_explicita(self):
        response = self.client.get(f'/control-empleados/{self.empleado.id_empleado}/editar')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'action="/control-empleados/{self.empleado.id_empleado}/editar"',
            html,
        )

    def test_filtro_detalle_define_action_explicita(self):
        response = self.client.get(f'/control-empleados/{self.empleado.id_empleado}')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'action="/control-empleados/{self.empleado.id_empleado}"',
            html,
        )

    def test_detalle_vacaciones_oculta_llegada_tardia_en_formulario(self):
        response = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?tab=vacaciones&periodo=2026-04',
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="crear_tipo_ausencia_form"', html)
        self.assertIn('form="crear_tipo_ausencia_form"', html)
        self.assertNotIn('<option value="llegada_tardia"', html)

    def test_resumen_muestra_formulario_para_registrar_llegada_tardia(self):
        response = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?tab=resumen&periodo=2026-04',
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Registrar llegada tardía', html)
        self.assertIn(f'action="/control-empleados/{self.empleado.id_empleado}/llegadas-tardias"', html)
        self.assertIn('Las llegadas tardías se registran arriba para no mezclarlas con vacaciones.', html)

    def test_resumen_permite_crear_tipo_movimiento_personalizado(self):
        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/tipos-movimiento',
            data={
                'periodo': '2026-04',
                'nombre_tipo_movimiento': 'Viático',
                'impacto_tipo_movimiento': 'positivo',
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Tipo de movimiento &#34;Viático&#34; agregado correctamente.', html)
        self.assertIn('value="viatico"', html)
        self.assertIn('form="eliminar_tipo_movimiento_viatico"', html)

    def test_tipo_movimiento_personalizado_negativo_descuenta_salario(self):
        self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/tipos-movimiento',
            data={
                'periodo': '2026-04',
                'nombre_tipo_movimiento': 'Compra interna',
                'impacto_tipo_movimiento': 'negativo',
            },
            follow_redirects=False,
        )

        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/movimientos',
            data={
                'periodo': '2026-04',
                'tipo': 'compra_interna',
                'fecha_movimiento': '2026-04-12',
                'concepto': 'Compra de mercadería',
                'monto': '50000',
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Compra interna', html)
        self.assertIn('-Gs. 50.000', html)

    def test_tipo_movimiento_por_cantidad_calcula_monto(self):
        self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/tipos-movimiento',
            data={
                'periodo': '2026-04',
                'nombre_tipo_movimiento': 'Pago por kilo',
                'impacto_tipo_movimiento': 'positivo',
                'modo_calculo_tipo_movimiento': 'cantidad',
                'unidad_tipo_movimiento': 'kg',
                'valor_unitario_tipo_movimiento': '5000',
            },
            follow_redirects=False,
        )

        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/movimientos',
            data={
                'periodo': '2026-04',
                'tipo': 'pago_por_kilo',
                'fecha_movimiento': '2026-04-12',
                'cantidad_movimiento': '10',
            },
            follow_redirects=True,
        )
        movimiento = EmpleadoMovimientoSalario.query.filter_by(
            id_empleado=self.empleado.id_empleado,
            tipo='pago_por_kilo',
        ).first()
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(movimiento)
        self.assertEqual(movimiento.monto, Decimal('50000.00'))
        self.assertEqual(movimiento.cantidad_calculo, Decimal('10.000'))
        self.assertEqual(movimiento.unidad_calculo, 'kg')
        self.assertEqual(movimiento.valor_unitario_calculo, Decimal('5000.00'))
        self.assertIn('Pago por kilo: 10 kg', html)
        self.assertIn('10 kg x Gs. 5.000', html)
        self.assertIn('+Gs. 50.000', html)

    def test_resumen_usa_fecha_del_periodo_en_formularios_mensuales(self):
        response = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?tab=resumen&periodo=2024-02',
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="fecha_llegada_tardia" name="fecha_movimiento" type="date" value="2024-02-01"', html)
        self.assertIn('id="fecha_movimiento" name="fecha_movimiento" type="date" value="2024-02-01"', html)
        self.assertIn('id="fecha_pago" name="fecha_pago" type="date" value="2024-02-01"', html)

    def test_configuracion_guarda_regla_de_descuento_por_llegada_tardia(self):
        response = self.client.post(
            '/control-empleados/configuracion',
            data={
                'empresa_nombre': 'Mi Empresa',
                'empresa_ruc': '80000000-1',
                'empresa_direccion': 'Sucursal Central',
                'llegada_tardia_descuento_desde': '3',
                'llegada_tardia_descuento_monto': '25000',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Configuracion.obtener(CLAVE_LLEGADA_TARDIA_DESCUENTO_DESDE), '3')
        self.assertEqual(Configuracion.obtener(CLAVE_LLEGADA_TARDIA_DESCUENTO_MONTO), '25000.00')

    def test_configuracion_empresa_respeta_scope_cliente(self):
        Configuracion.establecer(CLAVE_EMPRESA_NOMBRE, 'Empresa Global')
        Configuracion.establecer(CLAVE_EMPRESA_RUC, '80000000-0')
        Configuracion.establecer(CLAVE_EMPRESA_DIRECCION, 'Casa Matriz')

        with patch('control_de_empleados.routes._cliente_scope_actual', return_value=7):
            response = self.client.post(
                '/control-empleados/configuracion',
                data={
                    'empresa_nombre': 'Empresa Cliente 7',
                    'empresa_ruc': '80000007-1',
                    'empresa_direccion': 'Sucursal 7',
                    'llegada_tardia_descuento_desde': '2',
                    'llegada_tardia_descuento_monto': '15000',
                },
                follow_redirects=False,
            )
            page = self.client.get('/control-empleados/configuracion')

        html = page.get_data(as_text=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Configuracion.obtener(CLAVE_EMPRESA_NOMBRE), 'Empresa Global')
        self.assertEqual(Configuracion.obtener(CLAVE_EMPRESA_RUC), '80000000-0')
        self.assertEqual(Configuracion.obtener(CLAVE_EMPRESA_DIRECCION), 'Casa Matriz')
        self.assertEqual(Configuracion.obtener(f'{CLAVE_EMPRESA_NOMBRE}__cliente_7'), 'Empresa Cliente 7')
        self.assertEqual(Configuracion.obtener(f'{CLAVE_EMPRESA_RUC}__cliente_7'), '80000007-1')
        self.assertEqual(Configuracion.obtener(f'{CLAVE_EMPRESA_DIRECCION}__cliente_7'), 'Sucursal 7')
        self.assertIn('value="Empresa Cliente 7"', html)

    def test_resumen_descuenta_llegadas_tardias_configuradas(self):
        Configuracion.establecer(CLAVE_LLEGADA_TARDIA_DESCUENTO_DESDE, '2')
        Configuracion.establecer(CLAVE_LLEGADA_TARDIA_DESCUENTO_MONTO, '15000.00')
        db.session.add_all([
            EmpleadoAusencia(
                id_empleado=self.empleado.id_empleado,
                tipo='llegada_tardia',
                estado='aprobado',
                fecha_desde=date(2026, 4, 3),
                fecha_hasta=date(2026, 4, 3),
                motivo='Llegó tarde',
            ),
            EmpleadoAusencia(
                id_empleado=self.empleado.id_empleado,
                tipo='llegada_tardia',
                estado='tomado',
                fecha_desde=date(2026, 4, 10),
                fecha_hasta=date(2026, 4, 10),
                motivo='Llegó tarde otra vez',
            ),
            EmpleadoAusencia(
                id_empleado=self.empleado.id_empleado,
                tipo='llegada_tardia',
                estado='rechazado',
                fecha_desde=date(2026, 4, 12),
                fecha_hasta=date(2026, 4, 12),
                motivo='No debe contar',
            ),
        ])
        db.session.commit()

        response = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?periodo=2026-04&tab=resumen'
        )
        html = response.get_data(as_text=True)
        listado = self.client.get('/control-empleados/?periodo=2026-04')
        html_listado = listado.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(listado.status_code, 200)
        self.assertIn('Llegadas tardías del mes', html)
        self.assertIn('<strong>2</strong> llegadas tardías computadas', html)
        self.assertIn('Gs. 15.000', html)
        self.assertIn('2 tardías', html_listado)

    def test_puede_registrar_llegada_tardia_desde_resumen(self):
        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/llegadas-tardias',
            data={
                'periodo': '2026-04',
                'fecha_movimiento': '2026-04-18',
                'motivo': 'Ingreso fuera de horario',
                'observaciones': 'Se demoró el colectivo',
            },
            follow_redirects=False,
        )

        ausencia = EmpleadoAusencia.query.filter_by(
            id_empleado=self.empleado.id_empleado,
            tipo='llegada_tardia',
        ).first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(ausencia)
        self.assertEqual(ausencia.estado, 'tomado')
        self.assertEqual(ausencia.fecha_desde, date(2026, 4, 18))
        self.assertEqual(ausencia.fecha_hasta, date(2026, 4, 18))
        self.assertEqual(ausencia.motivo, 'Ingreso fuera de horario')

    def test_rechaza_llegada_tardia_fuera_del_periodo(self):
        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/llegadas-tardias',
            data={
                'periodo': '2026-04',
                'fecha_movimiento': '2026-05-01',
                'motivo': 'Ingreso fuera de horario',
            },
            follow_redirects=False,
        )

        ausencia = EmpleadoAusencia.query.filter_by(
            id_empleado=self.empleado.id_empleado,
            tipo='llegada_tardia',
        ).first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(ausencia)

    def test_historial_del_mes_incluye_llegadas_tardias(self):
        movimiento = EmpleadoMovimientoSalario(
            id_empleado=self.empleado.id_empleado,
            periodo='2026-04',
            fecha_movimiento=date(2026, 4, 20),
            tipo='bono',
            concepto='Bono puntual',
            monto=Decimal('50000.00'),
        )
        tardia = EmpleadoAusencia(
            id_empleado=self.empleado.id_empleado,
            tipo='llegada_tardia',
            estado='tomado',
            fecha_desde=date(2026, 4, 18),
            fecha_hasta=date(2026, 4, 18),
            motivo='Ingreso tarde por tránsito',
            observaciones='15 minutos',
        )
        db.session.add_all([movimiento, tardia])
        db.session.commit()

        response = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?periodo=2026-04&tab=resumen'
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Historial del mes', html)
        self.assertIn('1 manuales · 1 tardanzas', html)
        self.assertIn('Ingreso tarde por tránsito', html)
        self.assertIn('Llegada tardía', html)
        self.assertIn('No aplica', html)

    def test_historial_del_mes_tiene_paginacion(self):
        for dia in range(1, 13):
            db.session.add(
                EmpleadoAusencia(
                    id_empleado=self.empleado.id_empleado,
                    tipo='llegada_tardia',
                    estado='tomado',
                    fecha_desde=date(2026, 4, dia),
                    fecha_hasta=date(2026, 4, dia),
                    motivo=f'Tardanza dia {dia:02d}',
                )
            )
        db.session.commit()

        response_1 = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?periodo=2026-04&tab=resumen'
        )
        html_1 = response_1.get_data(as_text=True)
        response_2 = self.client.get(
            f'/control-empleados/{self.empleado.id_empleado}?periodo=2026-04&tab=resumen&page_historial=2'
        )
        html_2 = response_2.get_data(as_text=True)

        self.assertEqual(response_1.status_code, 200)
        self.assertEqual(response_2.status_code, 200)
        self.assertIn('Página 1 de 2', html_1)
        self.assertIn('Tardanza dia 12', html_1)
        self.assertNotIn('Tardanza dia 01', html_1)
        self.assertIn('Página 2 de 2', html_2)
        self.assertIn('Tardanza dia 01', html_2)

    def test_puede_eliminar_llegada_tardia_desde_historial_resumen(self):
        tardia = EmpleadoAusencia(
            id_empleado=self.empleado.id_empleado,
            tipo='llegada_tardia',
            estado='tomado',
            fecha_desde=date(2026, 4, 18),
            fecha_hasta=date(2026, 4, 18),
            motivo='Ingreso tarde por tránsito',
        )
        db.session.add(tardia)
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/ausencias/{tardia.id_ausencia}/eliminar',
            data={
                'periodo': '2026-04',
                'tab': 'resumen',
                'page_historial': '2',
            },
            follow_redirects=False,
        )

        eliminada = db.session.get(EmpleadoAusencia, tardia.id_ausencia)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(eliminada)
        self.assertIn('tab=resumen', response.headers['Location'])
        self.assertIn('page_historial=2', response.headers['Location'])

    def test_creacion_persiste_cliente_scope_actual(self):
        with patch('control_de_empleados.routes._cliente_scope_actual', return_value=7):
            response = self.client.post(
                '/control-empleados/nuevo',
                data={
                    'nombre_completo': 'Empleado Tenant',
                    'salario_base': '2800000',
                    'tipo_pago': 'mensual',
                    'activo': '1',
                },
                follow_redirects=False,
            )

        creado = Empleado.query.filter_by(nombre_completo='Empleado Tenant').first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(creado)
        self.assertEqual(creado.cliente_id, 7)

    def test_scope_cliente_filtra_listado_y_detalle(self):
        empleado_mismo_cliente = Empleado(
            nombre_completo='Empleado Cliente 7',
            salario_base=Decimal('2100000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=7,
        )
        empleado_otro_cliente = Empleado(
            nombre_completo='Empleado Cliente 9',
            salario_base=Decimal('2300000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=9,
        )
        db.session.add_all([empleado_mismo_cliente, empleado_otro_cliente])
        db.session.commit()

        with patch('control_de_empleados.routes._cliente_scope_actual', return_value=7):
            listado = self.client.get('/control-empleados/?periodo=2026-04')
            detalle_ajeno = self.client.get(f'/control-empleados/{empleado_otro_cliente.id_empleado}')

        html = listado.get_data(as_text=True)
        self.assertEqual(listado.status_code, 200)
        self.assertIn('Empleado Cliente 7', html)
        self.assertNotIn('Empleado Cliente 9', html)
        self.assertEqual(detalle_ajeno.status_code, 404)

    def test_usuario_demo_sin_cliente_puede_ver_solo_registros_globales(self):
        permiso_ver = Permiso.query.filter_by(codigo='ver_control_empleados').first()
        rol_no_admin = Rol.query.filter(
            Rol.activo == True,
            Rol.id_rol != self.admin.id_rol,
        ).order_by(Rol.nivel_jerarquia.asc()).first()
        self.assertIsNotNone(permiso_ver)
        self.assertIsNotNone(rol_no_admin)

        demo = Usuario(
            username='demo_rrhh',
            nombre_completo='Demo RRHH',
            id_rol=rol_no_admin.id_rol,
            activo=True,
        )
        demo.set_password('1234')
        db.session.add(demo)
        db.session.flush()
        demo.permisos_adicionales.append(permiso_ver)
        demo.set_preferencia('modo_demo', '1')

        empleado_global = Empleado(
            nombre_completo='Empleado Global Demo',
            salario_base=Decimal('1750000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=None,
        )
        empleado_otro_cliente = Empleado(
            nombre_completo='Empleado Privado Cliente',
            salario_base=Decimal('1950000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=88,
        )
        db.session.add_all([empleado_global, empleado_otro_cliente])
        db.session.commit()

        with self.client.session_transaction() as session:
            session['_user_id'] = str(demo.id_usuario)
            session['_fresh'] = True

        response = self.client.get('/control-empleados/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Empleado Global Demo', html)
        self.assertNotIn('Empleado Privado Cliente', html)

    def test_usuario_sin_cliente_usa_cliente_unico_activo_del_servicio(self):
        permiso_ver = Permiso.query.filter_by(codigo='ver_control_empleados').first()
        rol_no_admin = Rol.query.filter(
            Rol.activo == True,
            Rol.id_rol != self.admin.id_rol,
        ).order_by(Rol.nivel_jerarquia.asc()).first()
        self.assertIsNotNone(permiso_ver)
        self.assertIsNotNone(rol_no_admin)

        usuario = Usuario(
            username='vendedora_auto_cliente',
            nombre_completo='Vendedora Auto Cliente',
            id_rol=rol_no_admin.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.flush()
        usuario.permisos_adicionales.append(permiso_ver)

        cliente_unico = Cliente(nombre='Cliente Unico Servicio', tipo='minorista', activo=True)
        db.session.add(cliente_unico)
        db.session.flush()

        empleado_visible = Empleado(
            nombre_completo='Empleado Cliente Unico',
            salario_base=Decimal('1750000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=cliente_unico.id_cliente,
        )
        empleado_global = Empleado(
            nombre_completo='Empleado Global Fuera Scope',
            salario_base=Decimal('1800000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=None,
        )
        db.session.add_all([empleado_visible, empleado_global])
        db.session.commit()

        with self.client.session_transaction() as session:
            session['_user_id'] = str(usuario.id_usuario)
            session['_fresh'] = True

        response = self.client.get('/control-empleados/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Empleado Cliente Unico', html)
        self.assertNotIn('Empleado Global Fuera Scope', html)

    def test_listado_filtra_por_nombre_y_estado(self):
        empleado_inactivo = Empleado(
            nombre_completo='Ana Inactiva',
            salario_base=Decimal('1800000.00'),
            tipo_pago='mensual',
            activo=False,
        )
        empleado_otro = Empleado(
            nombre_completo='Carlos Visible',
            salario_base=Decimal('1900000.00'),
            tipo_pago='mensual',
            activo=True,
        )
        db.session.add_all([empleado_inactivo, empleado_otro])
        db.session.commit()

        response = self.client.get('/control-empleados/?periodo=2026-04&q=Ana&estado=inactivos')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Ana Inactiva', html)
        self.assertNotIn('Carlos Visible', html)
        self.assertNotIn('Empleado Prueba', html)

    def test_listado_filtra_con_switch_de_inactivos(self):
        empleado_inactivo = Empleado(
            nombre_completo='Laura Oculta',
            salario_base=Decimal('1850000.00'),
            tipo_pago='mensual',
            activo=False,
        )
        db.session.add(empleado_inactivo)
        db.session.commit()

        response = self.client.get(
            '/control-empleados/?periodo=2026-04&mostrar_activos=0&mostrar_inactivos=1',
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Laura Oculta', html)
        self.assertNotIn('Empleado Prueba', html)

    def test_listado_muestra_estado_vacio_especifico_con_filtros(self):
        response = self.client.get('/control-empleados/?periodo=2026-04&q=ZZZ&estado=activos')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('No hay resultados para ese filtro', html)
        self.assertIn('Limpiar filtros', html)

    def test_listado_permite_apagar_ambos_switches(self):
        response = self.client.get(
            '/control-empleados/?periodo=2026-04&mostrar_activos=0&mostrar_inactivos=0',
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('No hay resultados para ese filtro', html)
        self.assertIn('0 registros', html)

    def test_toggle_activo_desactiva_empleado_desde_listado(self):
        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/toggle-activo',
            data={'next': '/control-empleados/?periodo=2026-04'},
            follow_redirects=False,
        )

        db.session.refresh(self.empleado)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.empleado.activo)

    def test_movimiento_y_pago_heredan_cliente_del_empleado(self):
        empleado_scope = Empleado(
            nombre_completo='Empleado Scope',
            salario_base=Decimal('2600000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=7,
        )
        db.session.add(empleado_scope)
        db.session.commit()

        movimiento_response = self.client.post(
            f'/control-empleados/{empleado_scope.id_empleado}/movimientos',
            data={
                'periodo': '2026-04',
                'tipo': 'bono',
                'concepto': 'Bono por rendimiento',
                'monto': '150000',
                'fecha_movimiento': '2026-04-10',
            },
            follow_redirects=False,
        )
        pago_response = self.client.post(
            f'/control-empleados/{empleado_scope.id_empleado}/pagar',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-10',
                'metodo_pago': 'Efectivo',
            },
            follow_redirects=False,
        )

        movimiento = EmpleadoMovimientoSalario.query.filter_by(id_empleado=empleado_scope.id_empleado).first()
        pago = EmpleadoPago.query.filter_by(id_empleado=empleado_scope.id_empleado).first()
        self.assertEqual(movimiento_response.status_code, 302)
        self.assertEqual(pago_response.status_code, 302)
        self.assertIsNotNone(movimiento)
        self.assertIsNotNone(pago)
        self.assertEqual(movimiento.cliente_id, 7)
        self.assertEqual(pago.cliente_id, 7)

    def test_puede_eliminar_movimiento_registrado(self):
        movimiento = EmpleadoMovimientoSalario(
            id_empleado=self.empleado.id_empleado,
            periodo='2026-04',
            fecha_movimiento=date(2026, 4, 10),
            tipo='bono',
            concepto='Bono corregible',
            monto=Decimal('100000.00'),
        )
        db.session.add(movimiento)
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/movimientos/{movimiento.id_movimiento}/eliminar',
            data={'periodo': '2026-04', 'tab': 'resumen'},
            follow_redirects=False,
        )

        eliminado = db.session.get(EmpleadoMovimientoSalario, movimiento.id_movimiento)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(eliminado)

    def test_rechaza_movimiento_fuera_del_periodo(self):
        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/movimientos',
            data={
                'periodo': '2026-04',
                'tipo': 'bono',
                'concepto': 'Bono fuera de periodo',
                'monto': '100000',
                'fecha_movimiento': '2026-05-02',
            },
            follow_redirects=False,
        )

        movimiento = EmpleadoMovimientoSalario.query.filter_by(
            id_empleado=self.empleado.id_empleado,
            concepto='Bono fuera de periodo',
        ).first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(movimiento)

    def test_puede_eliminar_pago_y_volver_a_detalle(self):
        pago = EmpleadoPago(
            id_empleado=self.empleado.id_empleado,
            periodo='2026-04',
            fecha_pago=date(2026, 4, 10),
            salario_base=Decimal('2500000.00'),
            total_extras=Decimal('0.00'),
            total_descuentos=Decimal('0.00'),
            total_pagado=Decimal('2500000.00'),
        )
        db.session.add(pago)
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/pago/{pago.id_pago}/eliminar',
            data={'periodo': '2026-04', 'return_to': 'detalle'},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        eliminado = db.session.get(EmpleadoPago, pago.id_pago)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(eliminado)
        self.assertIn('Pendiente de Pago', html)

    def test_puede_eliminar_ausencia_registrada(self):
        ausencia = EmpleadoAusencia(
            id_empleado=self.empleado.id_empleado,
            tipo='permiso',
            estado='pendiente',
            fecha_desde=date(2026, 4, 10),
            fecha_hasta=date(2026, 4, 10),
            motivo='Trámite personal',
        )
        db.session.add(ausencia)
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/ausencias/{ausencia.id_ausencia}/eliminar',
            data={'periodo': '2026-04', 'anio': '2026'},
            follow_redirects=False,
        )

        eliminada = db.session.get(EmpleadoAusencia, ausencia.id_ausencia)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(eliminada)

    def test_usuario_sin_scope_no_puede_eliminar_feriado_de_otro_cliente(self):
        permiso_gestionar = Permiso.query.filter_by(codigo='gestionar_control_empleados').first()
        rol_no_admin = Rol.query.filter(
            Rol.activo == True,
            Rol.id_rol != self.admin.id_rol,
        ).order_by(Rol.nivel_jerarquia.asc()).first()
        self.assertIsNotNone(permiso_gestionar)
        self.assertIsNotNone(rol_no_admin)

        usuario = Usuario(
            username='rrhh_sin_scope',
            nombre_completo='RRHH Sin Scope',
            id_rol=rol_no_admin.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.flush()
        usuario.permisos_adicionales.append(permiso_gestionar)

        feriado = EmpleadoFeriado(
            cliente_id=88,
            fecha=date(2026, 4, 15),
            motivo='Feriado privado',
        )
        db.session.add(feriado)
        db.session.commit()

        with self.client.session_transaction() as session:
            session['_user_id'] = str(usuario.id_usuario)
            session['_fresh'] = True

        with patch('control_de_empleados.routes._cliente_scope_actual', return_value=None):
            response = self.client.post(
                f'/control-empleados/feriados/{feriado.id_feriado}/eliminar',
                follow_redirects=False,
            )

        existente = db.session.get(EmpleadoFeriado, feriado.id_feriado)
        self.assertEqual(response.status_code, 404)
        self.assertIsNotNone(existente)

    def test_recibo_pdf_usa_datos_de_empresa_del_cliente(self):
        self.empleado.cliente_id = 7
        pago = EmpleadoPago(
            cliente_id=7,
            id_empleado=self.empleado.id_empleado,
            periodo='2026-04',
            fecha_pago=date(2026, 4, 10),
            salario_base=Decimal('2500000.00'),
            total_extras=Decimal('0.00'),
            total_descuentos=Decimal('0.00'),
            total_pagado=Decimal('2500000.00'),
        )
        db.session.add(pago)
        db.session.commit()

        Configuracion.establecer(CLAVE_EMPRESA_NOMBRE, 'Empresa Global')
        Configuracion.establecer(CLAVE_EMPRESA_RUC, '80000000-0')
        Configuracion.establecer(CLAVE_EMPRESA_DIRECCION, 'Casa Matriz')
        Configuracion.establecer(f'{CLAVE_EMPRESA_NOMBRE}__cliente_7', 'Empresa Cliente 7')
        Configuracion.establecer(f'{CLAVE_EMPRESA_RUC}__cliente_7', '80000007-1')
        Configuracion.establecer(f'{CLAVE_EMPRESA_DIRECCION}__cliente_7', 'Sucursal 7')

        captured = {}

        class FakePisa:
            @staticmethod
            def CreatePDF(html, dest, encoding='UTF-8'):
                captured['html'] = html
                dest.write(b'%PDF-1.4 fake')

                class Result:
                    err = False

                return Result()

        with patch('control_de_empleados.routes_pagos.import_pisa', return_value=FakePisa):
            response = self.client.get(f'/control-empleados/pago/{pago.id_pago}/recibo')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Empresa Cliente 7', captured['html'])
        self.assertNotIn('Empresa Global', captured['html'])

    def test_puede_agregar_tipo_personalizado_de_ausencia(self):
        self.empleado.cliente_id = 7
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/tipos-ausencia',
            data={
                'periodo': '2026-04',
                'anio': '2026',
                'nombre_tipo_ausencia': 'Capacitación',
            },
            follow_redirects=False,
        )

        tipo = EmpleadoTipoAusencia.query.filter_by(cliente_id=7, clave='capacitacion').first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(tipo)
        self.assertEqual(tipo.nombre, 'Capacitación')

    def test_puede_agregar_tipo_personalizado_global_sin_cliente(self):
        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/tipos-ausencia',
            data={
                'periodo': '2026-04',
                'anio': '2026',
                'nombre_tipo_ausencia': 'Guardia',
            },
            follow_redirects=False,
        )

        tipo = EmpleadoTipoAusencia.query.filter_by(cliente_id=0, clave='guardia').first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(tipo)
        self.assertEqual(tipo.nombre, 'Guardia')

    def test_no_puede_eliminar_tipo_personalizado_en_uso(self):
        self.empleado.cliente_id = 7
        tipo = EmpleadoTipoAusencia(
            cliente_id=7,
            clave='capacitacion',
            nombre='Capacitación',
        )
        db.session.add(tipo)
        db.session.flush()
        db.session.add(
            EmpleadoAusencia(
                cliente_id=7,
                id_empleado=self.empleado.id_empleado,
                tipo='capacitacion',
                estado='pendiente',
                fecha_desde=date(2026, 4, 15),
                fecha_hasta=date(2026, 4, 15),
                motivo='Curso interno',
            )
        )
        db.session.commit()

        response = self.client.post(
            f'/control-empleados/{self.empleado.id_empleado}/tipos-ausencia/{tipo.id_tipo_ausencia}/eliminar',
            data={'periodo': '2026-04', 'anio': '2026'},
            follow_redirects=False,
        )

        existente = db.session.get(EmpleadoTipoAusencia, tipo.id_tipo_ausencia)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(existente)


if __name__ == '__main__':
    unittest.main()
