from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app import create_app, db
from app.models import Cliente, Reparacion, Rol, Usuario
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS
from control_de_empleados.models import Empleado, EmpleadoAusencia, EmpleadoMovimientoSalario, EmpleadoPago


def _crear_empleado_con_datos():
    suffix = uuid4().hex[:8]
    empleado = Empleado(
        nombre_completo=f'Empleado IA {suffix}',
        documento=f'DOC-{suffix}',
        cargo='Vendedor',
        area='Salon',
        salario_base=3000000,
        fecha_ingreso=date(2026, 1, 1),
        activo=True,
    )
    empleado_pendiente = Empleado(
        nombre_completo=f'Empleado Pendiente IA {suffix}',
        documento=f'DOC-P-{suffix}',
        cargo='Soporte',
        salario_base=2500000,
        fecha_ingreso=date(2026, 1, 1),
        activo=True,
    )
    db.session.add_all([empleado, empleado_pendiente])
    db.session.flush()
    db.session.add(EmpleadoPago(
        id_empleado=empleado.id_empleado,
        periodo='2026-04',
        fecha_pago=date(2026, 4, 25),
        salario_base=3000000,
        total_extras=200000,
        total_descuentos=50000,
        total_pagado=3150000,
    ))
    db.session.add(EmpleadoMovimientoSalario(
        id_empleado=empleado.id_empleado,
        periodo='2026-04',
        fecha_movimiento=date(2026, 4, 20),
        tipo='extra',
        concepto='Comision IA',
        monto=200000,
        incide_aguinaldo=True,
    ))
    db.session.add(EmpleadoAusencia(
        id_empleado=empleado.id_empleado,
        tipo='vacaciones',
        estado='aprobado',
        fecha_desde=date(2026, 4, 10),
        fecha_hasta=date(2026, 4, 12),
        motivo='Descanso programado IA',
    ))
    db.session.commit()
    return empleado


def _tecnico():
    rol = Rol.query.filter_by(nombre='Tecnico').first()
    tecnico = Usuario.query.filter_by(username='tecnico_ia_sprint6').first()
    if tecnico:
        return tecnico
    tecnico = Usuario(
        username='tecnico_ia_sprint6',
        nombre_completo='Tecnico IA Sprint 6',
        id_rol=rol.id_rol,
        activo=True,
    )
    tecnico.set_password('1234')
    db.session.add(tecnico)
    db.session.flush()
    return tecnico


def _crear_reparaciones_con_datos():
    suffix = uuid4().hex[:8]
    admin = Usuario.query.filter_by(username='admin').first()
    tecnico = _tecnico()
    cliente = Cliente(nombre=f'Cliente Reparacion IA {suffix}', tipo='minorista', activo=True)
    db.session.add(cliente)
    db.session.flush()
    atraso = Reparacion(
        cliente_id=cliente.id_cliente,
        id_usuario_vendedor=admin.id_usuario,
        id_usuario_tecnico=tecnico.id_usuario,
        tipo_equipo='Celular',
        marca_modelo=f'Modelo Atrasado {suffix}',
        falla_reportada='No carga',
        estado='en_proceso',
        prioridad='urgente',
        costo_estimado=120000,
        costo_final=150000,
        fecha_ingreso=datetime(2026, 4, 5, 10, 0, 0),
        fecha_estimada=datetime(2026, 4, 15, 18, 0, 0),
    )
    listo = Reparacion(
        cliente_id=cliente.id_cliente,
        id_usuario_vendedor=admin.id_usuario,
        id_usuario_tecnico=tecnico.id_usuario,
        tipo_equipo='Tablet',
        marca_modelo=f'Modelo Listo {suffix}',
        falla_reportada='No carga',
        estado='listo',
        prioridad='normal',
        costo_estimado=80000,
        costo_final=95000,
        fecha_ingreso=datetime(2026, 4, 20, 10, 0, 0),
        fecha_estimada=datetime(2026, 4, 28, 18, 0, 0),
        fecha_listo_tecnico=datetime(2026, 4, 22, 18, 0, 0),
    )
    entregado = Reparacion(
        cliente_id=cliente.id_cliente,
        id_usuario_vendedor=admin.id_usuario,
        id_usuario_tecnico=tecnico.id_usuario,
        tipo_equipo='Notebook',
        marca_modelo=f'Modelo Entregado {suffix}',
        falla_reportada='Pantalla rota',
        estado='entregado',
        costo_estimado=300000,
        costo_final=320000,
        fecha_ingreso=datetime(2026, 4, 21, 10, 0, 0),
        fecha_entrega=datetime(2026, 4, 25, 10, 0, 0),
    )
    db.session.add_all([atraso, listo, entregado])
    db.session.commit()
    return tecnico, atraso


def test_catalogo_habilita_tools_de_empleados_y_reparaciones():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'empleados_resumen',
        'empleados_ausencias_periodo',
        'empleados_pagos_periodo',
        'empleados_aguinaldo_resumen',
        'reparaciones_resumen',
        'reparaciones_atrasadas',
        'reparaciones_por_tecnico',
        'reparaciones_fallas_frecuentes',
    }.issubset(nombres)


def test_tools_empleados_resumen_ausencias_pagos_y_aguinaldo():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        empleado = _crear_empleado_con_datos()
        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}

        resumen = ejecutar_tool_backoffice('empleados_resumen', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['empleados_activos'] >= 2
        assert resumen['data']['total_pagado_periodo'] >= 3150000
        assert resumen['data']['extras_periodo'] >= 200000

        ausencias = ejecutar_tool_backoffice('empleados_ausencias_periodo', args, usuario=admin)
        assert ausencias['ok'] is True
        assert any(item['clave'] == 'vacaciones' for item in ausencias['data']['por_tipo'])

        pagos = ejecutar_tool_backoffice('empleados_pagos_periodo', args, usuario=admin)
        assert pagos['ok'] is True
        assert pagos['data']['empleados_pendientes_estimados'] >= 1
        assert any(item['id_empleado'] == empleado.id_empleado for item in pagos['data']['pagos'])

        aguinaldo = ejecutar_tool_backoffice('empleados_aguinaldo_resumen', args, usuario=admin)
        assert aguinaldo['ok'] is True
        assert aguinaldo['data']['aguinaldo_proyectado_total'] > 0


def test_tools_reparaciones_resumen_atrasos_tecnicos_y_fallas():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        tecnico, atraso = _crear_reparaciones_con_datos()
        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}

        resumen = ejecutar_tool_backoffice('reparaciones_resumen', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['total_ingresadas'] >= 3
        assert any(item['clave'] == 'en_proceso' for item in resumen['data']['por_estado'])

        atrasadas = ejecutar_tool_backoffice('reparaciones_atrasadas', args, usuario=admin)
        assert atrasadas['ok'] is True
        assert any(item['id_reparacion'] == atraso.id_reparacion for item in atrasadas['data']['reparaciones'])

        por_tecnico = ejecutar_tool_backoffice('reparaciones_por_tecnico', args, usuario=admin)
        assert por_tecnico['ok'] is True
        assert any(item['id_usuario_tecnico'] == tecnico.id_usuario for item in por_tecnico['data']['tecnicos'])

        fallas = ejecutar_tool_backoffice('reparaciones_fallas_frecuentes', args, usuario=admin)
        assert fallas['ok'] is True
        assert fallas['data']['fallas'][0]['falla'] == 'No carga'
        assert fallas['data']['fallas'][0]['cantidad'] >= 2


def test_tools_empleados_y_reparaciones_respetan_permisos():
    sin_permisos = SimpleNamespace(
        is_authenticated=True,
        es_admin=lambda: False,
        tiene_permiso=lambda _codigo: False,
    )
    solo_empleados = SimpleNamespace(
        is_authenticated=True,
        es_admin=lambda: False,
        tiene_permiso=lambda codigo: codigo == 'ver_control_empleados',
    )

    assert ejecutar_tool_backoffice('empleados_resumen', {}, usuario=sin_permisos)['error'] == 'sin_permiso_empleados'
    assert ejecutar_tool_backoffice('reparaciones_resumen', {}, usuario=solo_empleados)['error'] == 'sin_permiso_reparaciones'
