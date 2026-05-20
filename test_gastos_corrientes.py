import unittest
import tempfile
from io import BytesIO
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from app import create_app, db


class TestGastosCorrientes(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app.config['PROJECT_ROOT'] = self.tempdir.name
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
        self.tempdir.cleanup()

    def _login_como(self, usuario):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(usuario.id_usuario)
            session['_fresh'] = True

    def _crear_usuario_con_permisos(self, username, permisos):
        from app.models import Permiso, Rol, Usuario

        rol = Rol(
            nombre=f'Rol {username}',
            descripcion='Rol de pruebas para gastos corrientes',
            nivel_jerarquia=50,
            activo=True,
        )
        db.session.add(rol)
        db.session.flush()
        for permiso in Permiso.query.filter(Permiso.codigo.in_(permisos)).all():
            rol.permisos.append(permiso)

        usuario = Usuario(
            username=username,
            nombre_completo=username,
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('test123')
        db.session.add(usuario)
        db.session.commit()
        return usuario

    def _crear_gasto(self, nombre='Internet Fibra', *, dia_vencimiento=12, fecha_creacion=None):
        from gastos_corrientes.models import GastoCorriente

        gasto = GastoCorriente(
            nombre=nombre,
            categoria='internet',
            monto_estimado=Decimal('250000.00'),
            dia_vencimiento=dia_vencimiento,
            activo=True,
            requiere_caja_por_defecto=True,
            alerta_activa=True,
            dias_anticipacion_alerta=3,
            fecha_creacion=fecha_creacion or datetime(2026, 4, 1, 9, 0, 0),
        )
        db.session.add(gasto)
        db.session.commit()
        return gasto

    def _abrir_sesion_caja(self, monto_inicial='500000.00'):
        from app.models import SesionCaja

        sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=Decimal(monto_inicial),
            estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        return sesion

    def test_registrar_pago_desde_caja_crea_movimiento_egreso(self):
        from app.models import MovimientoCaja
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('ANDE')
        sesion = self._abrir_sesion_caja()

        response = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-10',
                'monto_pagado': '350000',
                'pagado_desde_caja': '1',
                'numero_comprobante': 'FAC-001',
                'observacion': 'Pago en efectivo',
            },
            follow_redirects=False,
        )

        pago = PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).first()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(pago)
        self.assertEqual(pago.estado, 'pagado')
        self.assertTrue(pago.pagado_desde_caja)
        self.assertEqual(pago.id_sesion_caja, sesion.id_sesion)
        self.assertIsNotNone(pago.id_movimiento_caja)

        movimiento = db.session.get(MovimientoCaja, pago.id_movimiento_caja)
        self.assertIsNotNone(movimiento)
        self.assertEqual(movimiento.tipo, 'egreso')
        self.assertEqual((movimiento.referencia_tipo or '').strip().lower(), 'gasto_corriente')
        self.assertEqual(movimiento.referencia_id, pago.id_pago_gasto_corriente)
        self.assertAlmostEqual(float(movimiento.monto or 0), 350000.0)

    def test_registrar_pago_sin_caja_no_crea_movimiento(self):
        from app.models import MovimientoCaja
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('Internet Claro')

        response = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '275000',
                'numero_comprobante': 'TRF-001',
                'observacion': 'Transferencia bancaria',
            },
            follow_redirects=False,
        )

        pago = PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).first()
        movimientos = MovimientoCaja.query.filter_by(referencia_tipo='gasto_corriente').all()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(pago)
        self.assertFalse(pago.pagado_desde_caja)
        self.assertIsNone(pago.id_sesion_caja)
        self.assertIsNone(pago.id_movimiento_caja)
        self.assertEqual(len(movimientos), 0)

    def test_anular_pago_con_caja_crea_reversa_y_marca_estado(self):
        from app.models import MovimientoCaja
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('Alquiler Local')
        self._abrir_sesion_caja(monto_inicial='900000.00')

        crear_response = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-09',
                'monto_pagado': '600000',
                'pagado_desde_caja': '1',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_response.status_code, 302)

        pago = PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).first()
        self.assertIsNotNone(pago)

        anular_response = self.client.post(
            f'/gastos-corrientes/pago/{pago.id_pago_gasto_corriente}/anular',
            data={'motivo_anulacion': 'Carga incorrecta'},
            follow_redirects=False,
        )

        db.session.refresh(pago)
        self.assertEqual(anular_response.status_code, 302)
        self.assertEqual(pago.estado, 'anulado')
        self.assertEqual((pago.motivo_anulacion or '').strip(), 'Carga incorrecta')
        self.assertIsNotNone(pago.id_movimiento_reversa)

        movimientos = (
            MovimientoCaja.query
            .filter(MovimientoCaja.referencia_id == pago.id_pago_gasto_corriente)
            .order_by(MovimientoCaja.id_movimiento_caja.asc())
            .all()
        )
        self.assertEqual(len(movimientos), 2)
        self.assertEqual(movimientos[0].tipo, 'egreso')
        self.assertEqual(movimientos[1].tipo, 'ingreso')
        self.assertEqual((movimientos[1].referencia_tipo or '').strip().lower(), 'gasto_corriente_reversa')

    def test_informe_contable_separa_gastos_corrientes_y_excluye_ingresos_manuales(self):
        from app.models import MovimientoCaja
        from app.routes.caja.common import _calcular_informe_contable_rango
        from app.utils.helpers import utc_bounds_for_local_dates

        gasto_caja = self._crear_gasto('Alquiler Oficina')
        gasto_fuera_caja = self._crear_gasto('Internet Fibra')
        sesion = self._abrir_sesion_caja(monto_inicial='1000000.00')

        response_caja = self.client.post(
            f'/gastos-corrientes/pago/{gasto_caja.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-08',
                'monto_pagado': '600000',
                'pagado_desde_caja': '1',
            },
            follow_redirects=False,
        )
        response_fuera_caja = self.client.post(
            f'/gastos-corrientes/pago/{gasto_fuera_caja.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-10',
                'monto_pagado': '200000',
            },
            follow_redirects=False,
        )
        self.assertEqual(response_caja.status_code, 302)
        self.assertEqual(response_fuera_caja.status_code, 302)

        db.session.add(
            MovimientoCaja(
                id_sesion_caja=sesion.id_sesion,
                id_usuario=self.admin.id_usuario,
                tipo='ingreso',
                monto=Decimal('500000.00'),
                motivo='Aporte de socios',
                fecha_movimiento=datetime(2026, 4, 12, 10, 0),
            )
        )
        db.session.commit()

        start_utc, end_utc = utc_bounds_for_local_dates(date(2026, 4, 1), date(2026, 4, 30))
        informe = _calcular_informe_contable_rango(start_utc, end_utc)
        conceptos = {row['concepto']: row for row in informe['conceptos']}

        self.assertAlmostEqual(informe['gastos_corrientes_mes'], 800000.0)
        self.assertAlmostEqual(informe['ingresos_manuales'], 500000.0)
        self.assertAlmostEqual(informe['resultado_caja_mes'], -100000.0)
        self.assertAlmostEqual(informe['ganancia_neta_mes'], -800000.0)
        self.assertIn('Gastos Corrientes (Caja)', conceptos)
        self.assertAlmostEqual(conceptos['Gastos Corrientes (Caja)']['salida'], 600000.0)

    def test_informe_contable_muestra_nombre_y_categoria_de_gasto_corriente(self):
        from app.routes.caja.common import _calcular_informe_contable_rango
        from app.utils.helpers import utc_bounds_for_local_dates

        gasto = self._crear_gasto('Internet Fibra')

        response = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '275000',
                'numero_comprobante': 'TRF-001',
                'observacion': 'Transferencia bancaria',
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        start_utc, end_utc = utc_bounds_for_local_dates(date(2026, 4, 1), date(2026, 4, 30))
        informe = _calcular_informe_contable_rango(start_utc, end_utc)
        detalle_gasto = next((item for item in informe['detalles'] if item['referencia'] == 'Internet Fibra'), None)

        self.assertIsNotNone(detalle_gasto)
        self.assertEqual(detalle_gasto['concepto'], 'Gasto Corriente')
        self.assertEqual(detalle_gasto['forma_pago'], 'Fuera de caja')
        self.assertIn('Categoría: Internet', detalle_gasto['detalle'])
        self.assertIn('Comprobante: TRF-001', detalle_gasto['detalle'])

    def test_exportar_csv_gastos_corrientes_devuelve_resumen_y_detalle(self):
        gasto = self._crear_gasto('Internet Fibra')

        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '275000',
                'numero_comprobante': 'TRF-001',
                'observacion': 'Transferencia bancaria',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        response = self.client.get('/gastos-corrientes/exportar/csv?periodo=2026-04')

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.headers.get('Content-Type', ''))
        self.assertIn('gastos_corrientes_2026-04.csv', response.headers.get('Content-Disposition', ''))

        contenido = response.get_data(as_text=True)
        self.assertIn('Reporte de Gastos Corrientes', contenido)
        self.assertIn('Total estimado', contenido)
        self.assertIn('Internet Fibra', contenido)
        self.assertIn('Transferencia bancaria', contenido)
        self.assertIn('TRF-001', contenido)

    def test_exportar_pdf_gastos_corrientes_devuelve_archivo_pdf(self):
        gasto = self._crear_gasto('Internet Fibra')

        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '275000',
                'numero_comprobante': 'TRF-001',
                'observacion': 'Transferencia bancaria',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        response = self.client.get('/gastos-corrientes/exportar/pdf?periodo=2026-04')

        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response.headers.get('Content-Type', ''))
        self.assertIn('gastos_corrientes_2026-04.pdf', response.headers.get('Content-Disposition', ''))

        contenido = response.get_data()
        self.assertTrue(contenido.startswith(b'%PDF'))
        self.assertGreater(len(contenido), 1500)

    def test_exportes_requieren_permiso_de_reportes_para_usuario_no_admin(self):
        self._crear_gasto('Internet Fibra')
        usuario = self._crear_usuario_con_permisos('gc_sin_reportes', ['ver_gastos_corrientes'])
        self._login_como(usuario)

        response_csv = self.client.get('/gastos-corrientes/exportar/csv?periodo=2026-04')
        response_pdf = self.client.get('/gastos-corrientes/exportar/pdf?periodo=2026-04')

        self.assertEqual(response_csv.status_code, 302)
        self.assertEqual(response_pdf.status_code, 302)

    def test_caja_estado_muestra_egreso_de_gasto_corriente_en_movimientos(self):
        gasto = self._crear_gasto('ANDE')
        self._abrir_sesion_caja()

        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-10',
                'monto_pagado': '350000',
                'pagado_desde_caja': '1',
                'numero_comprobante': 'FAC-001',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        response = self.client.get('/caja/')
        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)
        self.assertIn('Pago gasto corriente: ANDE', html)
        self.assertIn('Categoría: Internet', html)
        self.assertIn('Período: 2026-04', html)
        self.assertIn('Egresos: ₲ 350.000', html)

    def test_listado_gastos_corrientes_renderiza_alertas_roja_y_verde(self):
        gasto_vencido = self._crear_gasto('Luz vencida')
        gasto_vencido.dia_vencimiento = 5
        gasto_en_fecha = self._crear_gasto('Internet en fecha')
        gasto_en_fecha.dia_vencimiento = 25
        db.session.commit()

        with patch('gastos_corrientes.services.gasto_corriente_reporting.date') as mocked_date:
            mocked_date.today.return_value = date(2026, 4, 10)
            mocked_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            response = self.client.get('/gastos-corrientes/?periodo=2026-04')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Luz vencida', html)
        self.assertIn('Vencido 05/04', html)
        self.assertIn('bg-rose-100 text-rose-700', html)
        self.assertIn('Internet en fecha', html)
        self.assertIn('En fecha', html)
        self.assertIn('bg-emerald-100 text-emerald-700', html)

    def test_editar_gasto_corriente_conserva_historial_existente(self):
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('Internet Fibra')
        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '275000',
                'numero_comprobante': 'TRF-001',
                'observacion': 'Transferencia bancaria',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        pago = PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).first()
        self.assertIsNotNone(pago)
        pago_id = int(pago.id_pago_gasto_corriente)

        editar = self.client.post(
            f'/gastos-corrientes/{gasto.id_gasto_corriente}/editar',
            data={
                'nombre': 'Internet Fibra Empresarial',
                'categoria': 'internet',
                'descripcion': 'Plan actualizado',
                'monto_estimado': '300000',
                'dia_vencimiento': '15',
                'activo': '1',
                'requiere_caja_por_defecto': '1',
                'alerta_activa': '1',
                'dias_anticipacion_alerta': '5',
            },
            follow_redirects=False,
        )
        self.assertEqual(editar.status_code, 302)

        db.session.refresh(gasto)
        pago_actualizado = db.session.get(PagoGastoCorriente, pago_id)
        self.assertEqual(gasto.nombre, 'Internet Fibra Empresarial')
        self.assertIsNotNone(pago_actualizado)
        self.assertEqual(int(pago_actualizado.id_gasto_corriente), int(gasto.id_gasto_corriente))
        self.assertEqual(pago_actualizado.numero_comprobante, 'TRF-001')
        self.assertAlmostEqual(float(pago_actualizado.monto_pagado or 0), 275000.0)

        detalle = self.client.get(f'/gastos-corrientes/{gasto.id_gasto_corriente}')
        self.assertEqual(detalle.status_code, 200)
        html = detalle.get_data(as_text=True)
        self.assertIn('Internet Fibra Empresarial', html)
        self.assertIn('1 registros', html)
        self.assertIn('11/04/2026', html)
        self.assertIn('Pagado', html)

    def test_listado_automatiza_pendiente_mensual_para_gasto_activo(self):
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('Alquiler mensual')
        self.assertEqual(PagoGastoCorriente.query.count(), 0)

        response = self.client.get('/gastos-corrientes/?periodo=2026-04')
        self.assertEqual(response.status_code, 200)

        pago = PagoGastoCorriente.query.filter_by(
            id_gasto_corriente=gasto.id_gasto_corriente,
            periodo_anio=2026,
            periodo_mes=4,
        ).first()
        self.assertIsNotNone(pago)
        self.assertEqual(pago.estado, 'pendiente')
        self.assertAlmostEqual(float(pago.monto_pagado or 0), 0.0)
        self.assertIn('Alquiler mensual', response.get_data(as_text=True))

    def test_registrar_pago_convierte_pendiente_automatizado_en_pagado(self):
        from gastos_corrientes.models import PagoGastoCorriente
        from gastos_corrientes.services import sincronizar_pagos_periodo

        gasto = self._crear_gasto('Internet automático')
        sincronizar_pagos_periodo(periodo_anio=2026, periodo_mes=4)
        db.session.commit()

        pendiente = PagoGastoCorriente.query.filter_by(
            id_gasto_corriente=gasto.id_gasto_corriente,
            periodo_anio=2026,
            periodo_mes=4,
        ).first()
        self.assertIsNotNone(pendiente)
        pendiente_id = int(pendiente.id_pago_gasto_corriente)
        self.assertEqual(pendiente.estado, 'pendiente')

        response = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-12',
                'monto_pagado': '280000',
                'numero_comprobante': 'SYNC-001',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        pago = db.session.get(PagoGastoCorriente, pendiente_id)
        self.assertIsNotNone(pago)
        self.assertEqual(pago.estado, 'pagado')
        self.assertEqual(int(pago.id_pago_gasto_corriente), pendiente_id)
        self.assertEqual(pago.numero_comprobante, 'SYNC-001')
        self.assertAlmostEqual(float(pago.monto_pagado or 0), 280000.0)

    def test_gasto_creado_despues_del_vencimiento_inicia_en_el_mes_siguiente(self):
        from gastos_corrientes.models import PagoGastoCorriente
        from gastos_corrientes.services import sincronizar_pagos_periodo

        gasto = self._crear_gasto(
            'Luz diferida',
            dia_vencimiento=10,
            fecha_creacion=datetime(2026, 4, 16, 10, 0, 0),
        )

        abril = sincronizar_pagos_periodo(periodo_anio=2026, periodo_mes=4)
        self.assertEqual(abril['created'], 0)
        self.assertIsNone(
            PagoGastoCorriente.query.filter_by(
                id_gasto_corriente=gasto.id_gasto_corriente,
                periodo_anio=2026,
                periodo_mes=4,
            ).first()
        )

        mayo = sincronizar_pagos_periodo(periodo_anio=2026, periodo_mes=5)
        self.assertEqual(mayo['created'], 1)
        pago_mayo = PagoGastoCorriente.query.filter_by(
            id_gasto_corriente=gasto.id_gasto_corriente,
            periodo_anio=2026,
            periodo_mes=5,
        ).first()
        self.assertIsNotNone(pago_mayo)
        self.assertEqual(pago_mayo.estado, 'pendiente')

    def test_eliminar_gasto_corriente_borra_pendientes_automaticos(self):
        from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente

        gasto = self._crear_gasto('Sistema')
        listado = self.client.get('/gastos-corrientes/?periodo=2026-04')
        self.assertEqual(listado.status_code, 200)
        self.assertEqual(
            PagoGastoCorriente.query.filter_by(
                id_gasto_corriente=gasto.id_gasto_corriente,
                periodo_anio=2026,
                periodo_mes=4,
            ).count(),
            1,
        )

        response = self.client.post(
            f'/gastos-corrientes/{gasto.id_gasto_corriente}/eliminar',
            data={
                'periodo': '2026-04',
                'tab': 'listado',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(GastoCorriente, gasto.id_gasto_corriente))
        self.assertEqual(
            PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).count(),
            0,
        )

    def test_eliminar_gasto_corriente_con_historial_pagado_se_bloquea(self):
        from gastos_corrientes.models import GastoCorriente

        gasto = self._crear_gasto('Internet con historial')
        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '275000',
                'numero_comprobante': 'TRF-001',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        response = self.client.post(
            f'/gastos-corrientes/{gasto.id_gasto_corriente}/eliminar',
            data={
                'periodo': '2026-04',
                'tab': 'listado',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(db.session.get(GastoCorriente, gasto.id_gasto_corriente))

    def test_registrar_pago_con_adjunto_persiste_y_se_puede_descargar(self):
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('ANDE')
        archivo = (BytesIO(b'%PDF-1.4\n%adjunto de prueba\n'), 'comprobante.pdf')

        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-11',
                'monto_pagado': '350000',
                'numero_comprobante': 'FAC-ADJ-001',
                'comprobante_adjunto': archivo,
            },
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        pago = PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).first()
        self.assertIsNotNone(pago)
        self.assertEqual(pago.comprobante_adjunto_nombre, 'comprobante.pdf')
        self.assertTrue((pago.comprobante_adjunto_path or '').endswith('.pdf'))
        self.assertEqual(pago.comprobante_adjunto_mime, 'application/pdf')

        detalle = self.client.get(f'/gastos-corrientes/{gasto.id_gasto_corriente}')
        self.assertEqual(detalle.status_code, 200)
        self.assertIn('Ver adjunto', detalle.get_data(as_text=True))

        descarga = self.client.get(f'/gastos-corrientes/pago/{pago.id_pago_gasto_corriente}/comprobante')
        self.assertEqual(descarga.status_code, 200)
        self.assertIn('application/pdf', descarga.headers.get('Content-Type', ''))
        self.assertTrue(descarga.get_data().startswith(b'%PDF-1.4'))
        descarga.close()

    def test_detalle_pago_muestra_campo_motivo_anulacion(self):
        gasto = self._crear_gasto('ANDE')

        crear_pago = self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-10',
                'monto_pagado': '350000',
            },
            follow_redirects=False,
        )
        self.assertEqual(crear_pago.status_code, 302)

        detalle = self.client.get(f'/gastos-corrientes/{gasto.id_gasto_corriente}')
        self.assertEqual(detalle.status_code, 200)
        self.assertIn('name="motivo_anulacion"', detalle.get_data(as_text=True))

    def test_formulario_pago_premarca_caja_segun_configuracion_del_gasto(self):
        gasto = self._crear_gasto('Caja por defecto')

        response = self.client.get(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo?periodo=2026-04'
        )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.get_data(as_text=True),
            r'name="pagado_desde_caja" value="1"\s+checked',
        )


if __name__ == '__main__':
    unittest.main()
