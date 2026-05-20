from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app import create_app, db
from app.models import Cliente, ClienteCalificacionHistorial, ClienteCalificacionRegla, Reparacion
from app.services.clientes_calificacion import aplicar_reglas_a_clientes, evaluar_cliente


def _limpiar_reglas():
    ClienteCalificacionHistorial.query.delete()
    ClienteCalificacionRegla.query.delete()
    db.session.commit()


def test_regla_asigna_estrellas_por_reparaciones_en_periodo():
    app = create_app('testing')

    with app.app_context():
        _limpiar_reglas()
        suffix = uuid4().hex[:8]
        cliente = Cliente(nombre=f'Cliente Regla Reparaciones {suffix}', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        ahora = datetime(2026, 4, 30, 12, 0, 0)
        for dias in (2, 5):
            db.session.add(Reparacion(
                cliente_id=cliente.id_cliente,
                tipo_equipo='Celular',
                marca_modelo='Modelo prueba',
                falla_reportada='Pantalla',
                estado='entregado',
                costo_estimado=Decimal('100000'),
                costo_final=Decimal('120000'),
                fecha_ingreso=ahora - timedelta(days=dias),
            ))
        regla = ClienteCalificacionRegla(
            nombre='Frecuente en reparaciones',
            metrica='reparaciones_cantidad',
            operador='>=',
            valor=Decimal('2'),
            periodo_dias=30,
            accion='asignar',
            estrellas=5,
            prioridad=10,
        )
        db.session.add(regla)
        db.session.commit()

        resultado = evaluar_cliente(cliente, reglas=[regla], ahora=ahora)

        assert resultado['cambio'] is True
        assert resultado['estrellas_nuevas'] == 5
        assert 'Frecuente en reparaciones' in resultado['motivo']


def test_resta_estrellas_respeta_reaplicacion_configurada():
    app = create_app('testing')

    with app.app_context():
        _limpiar_reglas()
        suffix = uuid4().hex[:8]
        cliente = Cliente(
            nombre=f'Cliente Inactivo {suffix}',
            tipo='minorista',
            activo=True,
            nivel_estrellas=5,
        )
        regla = ClienteCalificacionRegla(
            nombre='Inactividad 90 dias',
            metrica='dias_desde_ultima_compra',
            operador='>',
            valor=Decimal('90'),
            accion='restar',
            estrellas=1,
            prioridad=10,
            reaplicar_cada_dias=30,
        )
        db.session.add_all([cliente, regla])
        db.session.commit()

        ahora = datetime(2026, 4, 30, 12, 0, 0)
        primer_resultado = aplicar_reglas_a_clientes(ahora=ahora)
        cliente = db.session.get(Cliente, cliente.id_cliente)
        segundo_resultado = aplicar_reglas_a_clientes(ahora=ahora + timedelta(days=10))
        cliente = db.session.get(Cliente, cliente.id_cliente)

        assert primer_resultado['actualizados'] == 1
        assert segundo_resultado['actualizados'] == 0
        assert cliente.nivel_estrellas == 4
