"""Fase 6 del plan de peluquería: comisiones y recordatorios."""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

from app import db
from app.models import AgendaActividad, Cliente, Configuracion, Usuario, Venta
from app.services.peluqueria_comisiones import calcular_comisiones
from app.services.peluqueria_recordatorios import enviar_recordatorios_pendientes
from app.utils.helpers import today_local
from test_peluqueria_fase1 import PeluqueriaTestBase


class ComisionesTestBase(PeluqueriaTestBase):
    def setUp(self):
        super().setUp()
        self._abrir_caja()
        self.servicio = self._crear_servicio(precio=100000)

    def _vender(self, vendedor_id, precio=100000, con_producto=False, request_id=None):
        from app.models import MetodoPago, Producto

        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        items = [{'tipo': 'servicio', 'id_servicio': int(self.servicio.id_servicio), 'cantidad': 1, 'precio': precio, 'precio_manual': True}]
        total = precio
        if con_producto:
            producto = Producto.query.filter(Producto.activo.is_(True)).first()
            if producto is not None:
                items.append({'tipo': 'producto', 'id_producto': int(producto.id_producto), 'cantidad': 1, 'precio': 5000, 'precio_manual': True})
                total += 5000
        response = self.client.post('/ventas/procesar', json={
            'items': items,
            'pagos': [{'id_metodo_pago': int(metodo.id_metodo_pago), 'monto': total}],
            'id_usuario_vendedor': int(vendedor_id),
            'client_request_id': request_id or f'com-{vendedor_id}-{precio}-{datetime.utcnow().timestamp()}',
        })
        data = response.get_json() or {}
        self.assertTrue(data.get('success'), data)
        return db.session.get(Venta, int(data['id_venta']))


class TestComisiones(ComisionesTestBase):
    def test_comision_sobre_servicios_con_porcentaje(self):
        self.admin.comision_porcentaje = Decimal('40')
        db.session.commit()
        self._vender(self.admin.id_usuario, 100000, con_producto=True)
        self._vender(self.admin.id_usuario, 50000)

        resumen = calcular_comisiones(today_local(), today_local(), profesionales=[self.admin])

        fila = resumen['filas'][0]
        self.assertEqual(fila['servicios'], 2)
        self.assertEqual(fila['base'], 150000.0)  # el producto no suma
        self.assertEqual(fila['comision'], 60000.0)
        self.assertEqual(resumen['total_comision'], 60000.0)

    def test_anuladas_no_cuentan(self):
        self.admin.comision_porcentaje = Decimal('50')
        db.session.commit()
        venta = self._vender(self.admin.id_usuario, 80000)
        venta.estado = 'anulada'
        db.session.commit()

        resumen = calcular_comisiones(today_local(), today_local(), profesionales=[self.admin])

        self.assertEqual(resumen['filas'][0]['base'], 0.0)

    def test_devolucion_de_la_linea_se_descuenta(self):
        from app.models import Categoria, DetalleDevolucion, Devolucion, Producto

        self.admin.comision_porcentaje = Decimal('10')
        db.session.commit()
        venta = self._vender(self.admin.id_usuario, 100000)
        detalle = next(iter(venta.detalles))
        categoria = Categoria(nombre='Cat test devolución')
        db.session.add(categoria)
        db.session.flush()
        producto = Producto(codigo='DEV-TEST', nombre='Producto devolución', id_categoria=categoria.id_categoria, precio_venta=1)
        db.session.add(producto)
        db.session.flush()
        devolucion = Devolucion(id_venta=venta.id_venta, id_usuario=self.admin.id_usuario, id_sesion_caja=venta.id_sesion_caja,
                                motivo='test', accion_stock='ninguna', monto_total=40000)
        db.session.add(devolucion)
        db.session.flush()
        # Lo que importa es la línea original devuelta; id_producto es obligatorio en el esquema.
        db.session.add(DetalleDevolucion(id_devolucion=devolucion.id_devolucion, id_producto=producto.id_producto,
                                         id_detalle_venta_original=detalle.id_detalle_venta, cantidad=1,
                                         precio_unitario=40000, subtotal=40000))
        db.session.commit()

        resumen = calcular_comisiones(today_local(), today_local(), profesionales=[self.admin])

        self.assertEqual(resumen['filas'][0]['base'], 60000.0)
        self.assertEqual(resumen['filas'][0]['comision'], 6000.0)

    def test_sin_porcentaje_avisa_y_no_inventa(self):
        self._vender(self.admin.id_usuario, 70000)

        resumen = calcular_comisiones(today_local(), today_local(), profesionales=[self.admin])

        self.assertIsNone(resumen['filas'][0]['porcentaje'])
        self.assertEqual(resumen['filas'][0]['comision'], 0.0)
        self.assertIn(self.admin.nombre_completo, resumen['sin_porcentaje'])

    def test_rango_de_fechas(self):
        self.admin.comision_porcentaje = Decimal('40')
        db.session.commit()
        venta = self._vender(self.admin.id_usuario, 100000)
        venta.fecha_venta = venta.fecha_venta - timedelta(days=10)
        db.session.commit()

        hoy = today_local()
        self.assertEqual(calcular_comisiones(hoy, hoy, [self.admin])['total_comision'], 0.0)
        self.assertEqual(calcular_comisiones(hoy - timedelta(days=15), hoy, [self.admin])['total_comision'], 40000.0)

    def test_reporte_y_tarjeta_del_dashboard(self):
        self.admin.comision_porcentaje = Decimal('40')
        db.session.commit()
        self._vender(self.admin.id_usuario, 100000)

        reporte = self.client.get('/agenda/peluqueria/comisiones').get_data(as_text=True)
        dashboard = self.client.get('/').get_data(as_text=True)

        self.assertIn('40.000', reporte)
        self.assertIn('Comisiones del día', dashboard)
        self.assertIn('40% de', dashboard)

    def test_reporte_requiere_permiso(self):
        from app.routes.agenda.peluqueria_comisiones import puede_ver_comisiones

        sin_permiso = mock.Mock(es_admin=mock.Mock(return_value=False), tiene_permiso=mock.Mock(return_value=False))
        con_reportes = mock.Mock(es_admin=mock.Mock(return_value=False), tiene_permiso=lambda codigo: codigo == 'ver_reporte_ventas')

        self.assertFalse(puede_ver_comisiones(sin_permiso))
        self.assertTrue(puede_ver_comisiones(con_reportes))
        self.assertTrue(puede_ver_comisiones(self.admin))


class TestRecordatorios(PeluqueriaTestBase):
    def _turno_en(self, horas, telefono='0981123456'):
        cliente = Cliente(nombre='Lucía Gómez', telefono=telefono, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        inicio = datetime.utcnow() + timedelta(hours=horas)
        turno = AgendaActividad(
            titulo='Corte', tipo='cita', fecha_inicio=inicio, fecha_fin=inicio + timedelta(minutes=30), estado='pendiente',
            prioridad='media', usuario_id=self.admin.id_usuario, creado_por_id=self.admin.id_usuario, cliente_id=cliente.id_cliente,
            mostrar_agenda_en='solo_responsable', recordatorio_a='solo_responsable',
        )
        db.session.add(turno)
        db.session.commit()
        return turno

    def _activar(self, horas='3', template=''):
        Configuracion.establecer('peluqueria_recordatorio_horas_antes', horas)
        Configuracion.establecer('peluqueria_recordatorio_template', template)

    @mock.patch.dict('os.environ', {'WHATSAPP_PHONE_NUMBER_ID': '1', 'WHATSAPP_ACCESS_TOKEN': 't'})
    def test_desactivado_por_defecto(self):
        self._turno_en(1)
        with mock.patch('app.services.whatsapp.client.enviar_texto') as enviar:
            resumen = enviar_recordatorios_pendientes()
        enviar.assert_not_called()
        self.assertEqual(resumen['enviados'], 0)

    @mock.patch.dict('os.environ', {'WHATSAPP_PHONE_NUMBER_ID': '', 'WHATSAPP_ACCESS_TOKEN': '', 'WHATSAPP_PHONE_ID': '', 'WHATSAPP_TOKEN': '', 'WHATSAPP_DRY_RUN': '0'})
    def test_sin_whatsapp_configurado_no_envia(self):
        self._activar()
        self._turno_en(1)
        with mock.patch('app.services.whatsapp.client.enviar_texto') as enviar:
            enviar_recordatorios_pendientes()
        enviar.assert_not_called()

    @mock.patch.dict('os.environ', {'WHATSAPP_PHONE_NUMBER_ID': '1', 'WHATSAPP_ACCESS_TOKEN': 't'})
    def test_envia_una_vez_dentro_de_la_ventana(self):
        self._activar('3')
        cercano = self._turno_en(2)
        lejano = self._turno_en(5)
        with mock.patch('app.services.whatsapp.client.enviar_texto', return_value={'ok': True}) as enviar:
            primero = enviar_recordatorios_pendientes()
            segundo = enviar_recordatorios_pendientes()

        self.assertEqual(primero['enviados'], 1)
        self.assertEqual(segundo['enviados'], 0)
        enviar.assert_called_once()
        telefono, texto = enviar.call_args[0]
        self.assertEqual(telefono, '595981123456')
        self.assertIn('Hola Lucía', texto)
        db.session.refresh(cercano)
        db.session.refresh(lejano)
        self.assertIsNotNone(cercano.recordatorio_whatsapp_at)
        self.assertIsNone(lejano.recordatorio_whatsapp_at)

    @mock.patch.dict('os.environ', {'WHATSAPP_PHONE_NUMBER_ID': '1', 'WHATSAPP_ACCESS_TOKEN': 't'})
    def test_usa_plantilla_si_esta_configurada(self):
        self._activar('3', 'recordatorio_turno')
        self._turno_en(1)
        with mock.patch('app.services.whatsapp.client.enviar_template', return_value={'ok': True}) as enviar:
            enviar_recordatorios_pendientes()

        args, kwargs = enviar.call_args
        self.assertEqual(args[1], 'recordatorio_turno')
        parametros = [p['text'] for p in kwargs['componentes'][0]['parameters']]
        self.assertEqual(parametros[0], 'Lucía')
        self.assertEqual(len(parametros), 4)

    @mock.patch.dict('os.environ', {'WHATSAPP_PHONE_NUMBER_ID': '1', 'WHATSAPP_ACCESS_TOKEN': 't'})
    def test_sin_telefono_y_turnos_cancelados_no_se_envian(self):
        self._activar('3')
        self._turno_en(1, telefono='')
        cancelado = self._turno_en(1)
        cancelado.estado = 'cancelada'
        db.session.commit()
        with mock.patch('app.services.whatsapp.client.enviar_texto') as enviar:
            resumen = enviar_recordatorios_pendientes()

        enviar.assert_not_called()
        self.assertEqual(resumen['sin_telefono'], 1)

    def test_pantalla_guarda_configuracion(self):
        response = self.client.post('/agenda/turnos/peluqueria/horario', data={'seccion': 'recordatorios', 'horas_antes': '24', 'template': 'recordatorio_turno'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Configuracion.obtener('peluqueria_recordatorio_horas_antes'), '24')
        html = self.client.get('/agenda/turnos/peluqueria/horario').get_data(as_text=True)
        self.assertIn('Recordatorio automático por WhatsApp', html)

    def test_reprogramar_vuelve_a_habilitar_el_recordatorio(self):
        turno = self._turno_en(30)
        turno.recordatorio_whatsapp_at = datetime.utcnow()
        db.session.commit()
        manana = (today_local() + timedelta(days=3)).isoformat()

        self.client.post(f'/agenda/turnos/peluqueria/{turno.id}/gestionar', data={'accion': 'reprogramar', 'fecha': manana, 'hora': '11:00', 'duracion': '30'})
        db.session.refresh(turno)

        self.assertIsNone(turno.recordatorio_whatsapp_at)


if __name__ == '__main__':
    unittest.main()
