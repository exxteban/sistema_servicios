"""Fase 1 (paso 1) del plan de pasteleria: modelos y migracion de encargos."""
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.encargo_models import (
    ADELANTO_VIGENTE,
    GastronomiaPedidoAdelanto,
    GastronomiaPedidoFoto,
)
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaProducto,
)
from gastronomia.schema import ensure_gastronomia_schema


def _crear_pedido(app, nombre: str, username: str, **extra):
    with app.app_context():
        cliente = Cliente(nombre=nombre, ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {nombre}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.flush()
        pedido = GastronomiaPedido(
            cliente_id=cliente.id_cliente,
            usuario_id=usuario.id_usuario,
            tipo_pedido='retiro',
            **extra,
        )
        db.session.add(pedido)
        db.session.commit()
        return cliente.id_cliente, usuario.id_usuario, pedido.id_pedido


def _columnas(tabla: str) -> set[str]:
    return {row[1] for row in db.session.execute(text(f'PRAGMA table_info({tabla})')).fetchall()}


def _tablas() -> set[str]:
    return {
        row[0]
        for row in db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    }


def test_pedido_comun_no_es_encargo_y_serializa_los_campos_nuevos():
    app = create_app('testing')
    _, _, pedido_id = _crear_pedido(app, 'Enc Comun', 'enc_comun')

    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_id)
        assert pedido.es_encargo is False
        assert pedido.fecha_programada is None
        datos = pedido.to_dict()
        assert datos['es_encargo'] is False
        assert datos['fecha_programada'] is None


def test_encargo_guarda_fecha_programada_y_texto_personalizado():
    app = create_app('testing')
    programada = datetime(2030, 5, 4, 15, 30)
    cliente_id, _, pedido_id = _crear_pedido(
        app, 'Enc Datos', 'enc_datos', es_encargo=True, fecha_programada=programada,
    )

    with app.app_context():
        categoria = GastronomiaCategoria(cliente_id=cliente_id, nombre='Tortas')
        db.session.add(categoria)
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente_id, categoria_id=categoria.id_categoria, nombre='Torta', precio=100000,
        )
        db.session.add(producto)
        db.session.flush()
        item = GastronomiaPedidoItem(
            pedido_id=pedido_id,
            cliente_id=cliente_id,
            producto_id=producto.id_producto,
            nombre_producto='Torta',
            cantidad=1,
            precio_unitario=100000,
            subtotal=100000,
            texto_personalizado='Feliz cumple Ana',
        )
        db.session.add(item)
        db.session.commit()

        pedido = GastronomiaPedido.query.get(pedido_id)
        assert pedido.es_encargo is True
        assert pedido.fecha_programada == programada
        datos = pedido.to_dict()
        assert datos['es_encargo'] is True
        assert datos['fecha_programada'] == programada.isoformat()
        assert datos['items'][0]['texto_personalizado'] == 'Feliz cumple Ana'


def test_adelanto_y_foto_se_relacionan_con_el_pedido():
    app = create_app('testing')
    cliente_id, usuario_id, pedido_id = _crear_pedido(app, 'Enc Rel', 'enc_rel', es_encargo=True)

    with app.app_context():
        db.session.add_all([
            GastronomiaPedidoAdelanto(
                cliente_id=cliente_id, pedido_id=pedido_id, usuario_id=usuario_id, monto=20000,
            ),
            GastronomiaPedidoFoto(
                cliente_id=cliente_id, pedido_id=pedido_id, usuario_id=usuario_id, url='/static/x.webp',
            ),
        ])
        db.session.commit()

        pedido = GastronomiaPedido.query.get(pedido_id)
        adelanto = pedido.adelantos.one()
        assert adelanto.estado == ADELANTO_VIGENTE
        assert float(adelanto.monto_devuelto) == 0
        assert adelanto.metodo_pago == 'efectivo'
        assert adelanto.to_dict()['monto_retenido'] == 0
        assert pedido.fotos.one().to_dict()['url'] == '/static/x.webp'


def test_adelanto_rechaza_montos_invalidos():
    app = create_app('testing')
    cliente_id, usuario_id, pedido_id = _crear_pedido(app, 'Enc Check', 'enc_check', es_encargo=True)

    with app.app_context():
        for kwargs in ({'monto': 0}, {'monto': -5}, {'monto': 100, 'monto_devuelto': 101}):
            db.session.add(GastronomiaPedidoAdelanto(
                cliente_id=cliente_id, pedido_id=pedido_id, usuario_id=usuario_id, **kwargs,
            ))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


def test_borrar_pedido_borra_adelantos_y_fotos():
    app = create_app('testing')
    cliente_id, usuario_id, pedido_id = _crear_pedido(app, 'Enc Cascada', 'enc_cascada', es_encargo=True)

    with app.app_context():
        db.session.add_all([
            GastronomiaPedidoAdelanto(
                cliente_id=cliente_id, pedido_id=pedido_id, usuario_id=usuario_id, monto=1000,
            ),
            GastronomiaPedidoFoto(cliente_id=cliente_id, pedido_id=pedido_id, url='/static/y.webp'),
        ])
        db.session.commit()
        # SQLite aplica ON DELETE CASCADE solo con foreign_keys=ON: se borra por ORM para no depender de eso.
        db.session.query(GastronomiaPedidoAdelanto).filter_by(pedido_id=pedido_id).delete()
        db.session.query(GastronomiaPedidoFoto).filter_by(pedido_id=pedido_id).delete()
        db.session.delete(GastronomiaPedido.query.get(pedido_id))
        db.session.commit()
        assert GastronomiaPedido.query.get(pedido_id) is None


def test_migracion_agrega_columnas_y_tablas_de_encargos_a_base_vieja():
    app = create_app('testing')
    cliente_id, _, pedido_id = _crear_pedido(
        app, 'Enc Vieja', 'enc_vieja', notas='pedido previo',
    )

    with app.app_context():
        try:
            # Simula una base anterior a la Fase 1.
            db.session.execute(text('DROP INDEX IF EXISTS ix_gastronomia_pedidos_fecha_programada'))
            db.session.execute(text('ALTER TABLE gastronomia_pedidos DROP COLUMN es_encargo'))
            db.session.execute(text('ALTER TABLE gastronomia_pedidos DROP COLUMN fecha_programada'))
            db.session.execute(text('ALTER TABLE gastronomia_pedido_items DROP COLUMN texto_personalizado'))
            db.session.execute(text('DROP TABLE gastronomia_pedido_adelantos'))
            db.session.execute(text('DROP TABLE gastronomia_pedido_fotos'))
            db.session.commit()
            assert not {'es_encargo', 'fecha_programada'} & _columnas('gastronomia_pedidos')
            assert not {'gastronomia_pedido_adelantos', 'gastronomia_pedido_fotos'} & _tablas()

            ensure_gastronomia_schema()
            ensure_gastronomia_schema()  # idempotente

            assert {'es_encargo', 'fecha_programada'} <= _columnas('gastronomia_pedidos')
            assert 'texto_personalizado' in _columnas('gastronomia_pedido_items')
            assert {'gastronomia_pedido_adelantos', 'gastronomia_pedido_fotos'} <= _tablas()
            indices = {
                row[1]
                for row in db.session.execute(text('PRAGMA index_list(gastronomia_pedidos)')).fetchall()
            }
            assert 'ix_gastronomia_pedidos_fecha_programada' in indices

            db.session.expire_all()
            pedido = GastronomiaPedido.query.get(pedido_id)
            assert pedido.notas == 'pedido previo'
            assert pedido.es_encargo is False
            assert pedido.fecha_programada is None
        finally:
            db.session.rollback()
            ensure_gastronomia_schema()
            assert {'es_encargo', 'fecha_programada'} <= _columnas('gastronomia_pedidos')
