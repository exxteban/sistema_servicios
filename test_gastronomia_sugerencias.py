from datetime import datetime, timedelta

import pytest
from flask import Flask

from app import db
import app.models  # noqa: F401
from app.models import Cliente, Usuario, Rol, Venta, Caja, SesionCaja
from gastronomia.models import (
    GastronomiaCategoria, GastronomiaClienteConfig, GastronomiaProducto,
    GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago,
)
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaCalculo as Estado, GastronomiaSugerenciaPar as Par,
    GastronomiaSugerenciaExcluido as Excluido,
)
from gastronomia.services.sugerencias.calculo import _Conteo, medir, peso_por_antiguedad
from gastronomia.services.sugerencias.diagnostico import analizar
from gastronomia.services.sugerencias.tarea import recalcular


@pytest.fixture
def datos(request, tmp_path):
    app = Flask(__name__)
    uri = f"sqlite:///{(tmp_path / 'sugerencias.db').as_posix()}" if getattr(request, 'param', None) == 'archivo' else 'sqlite:///:memory:'
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, TESTING=True)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add(Rol(id_rol=3, nombre='Prueba'))
        db.session.commit()
        cliente = Cliente(nombre='Prueba', ruc_ci='sugerencias')
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(username='sugerencias', nombre_completo='Prueba', password_hash='x')
        db.session.add(usuario)
        db.session.add(GastronomiaClienteConfig(cliente_id=cliente.id_cliente, gastronomia_activo=True))
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Comidas')
        db.session.add(categoria)
        db.session.flush()
        productos = [GastronomiaProducto(cliente_id=cliente.id_cliente, categoria_id=categoria.id_categoria,
                                         nombre=f'Plato {i}', precio=10) for i in range(14)]
        db.session.add_all(productos)
        db.session.commit()
        yield cliente.id_cliente, usuario.id_usuario, [p.id_producto for p in productos]
        db.session.remove()


def pedido(datos, ids, *, pagado=True, encargo=False, cliente_id=None):
    cliente, usuario, _ = datos
    cliente = cliente_id or cliente
    p = GastronomiaPedido(cliente_id=cliente, usuario_id=usuario, es_encargo=encargo)
    db.session.add(p)
    db.session.flush()
    for producto in ids:
        db.session.add(GastronomiaPedidoItem(pedido_id=p.id_pedido, cliente_id=cliente,
                                           producto_id=producto, nombre_producto='Plato'))
    if pagado:
        db.session.add(GastronomiaPedidoPago(pedido_id=p.id_pedido, cliente_id=cliente, usuario_id=usuario))
    db.session.commit()
    return p


def test_matematica_y_soporte_real():
    assert medir(4, 4, 5, 10)['lift'] == 2
    assert medir(4, 8, 5, 10) is None  # bebida ubicua: lift 1
    ahora = datetime.utcnow()
    conteo = _Conteo()
    for _ in range(4):
        conteo.sumar({1, 2}, peso_por_antiguedad(ahora - timedelta(days=365), ahora))
    for _ in range(8):
        conteo.sumar({3}, 1)
    assert conteo.pares()[1][0]['soporte'] == 4
    corto = _Conteo()
    for _ in range(3):
        corto.sumar({1, 2}, 1)
    assert corto.pares() == {}


def test_tickets_filtrados_y_aislamiento(datos):
    cliente, _, ids = datos
    pedido(datos, [ids[0], ids[0], ids[1]])
    pedido(datos, ids[:2], pagado=False)
    pedido(datos, ids[:2], encargo=True)
    pedido(datos, ids[:13])
    otro = Cliente(nombre='Otro', ruc_ci='otro-sugerencias')
    db.session.add(otro)
    db.session.commit()
    pedido(datos, ids[:2], cliente_id=otro.id_cliente)
    resultado = analizar(cliente)
    assert resultado['pedidos'] == 1
    assert resultado['platos_promedio'] == 2
    db.session.add(Excluido(cliente_id=cliente, tipo='producto', id_ref=ids[1]))
    db.session.commit()
    assert analizar(cliente)['platos_promedio'] == 1


def test_reemplazo_candado_y_rollback(datos, monkeypatch):
    cliente, _, ids = datos
    for _ in range(4):
        pedido(datos, ids[:2])
    for _ in range(8):
        pedido(datos, [ids[2]])
    assert recalcular(cliente)
    assert Par.query.filter_by(cliente_id=cliente, nivel='producto').count() == 2
    estado = Estado.query.filter_by(cliente_id=cliente).one()
    estado.token = 'otro-worker'
    estado.inicio = datetime.utcnow()
    db.session.commit()
    assert recalcular(cliente) is False
    estado.token = None
    db.session.commit()
    def fallar(*args, **kwargs):
        raise RuntimeError('fallo simulado')
    monkeypatch.setattr('gastronomia.services.sugerencias.tarea.analizar', fallar)
    with pytest.raises(RuntimeError):
        recalcular(cliente)
    assert Par.query.filter_by(cliente_id=cliente).count() == 2
    assert Estado.query.filter_by(cliente_id=cliente).one().token is None


def test_venta_anulada_y_fecha_del_pago(datos):
    cliente, usuario, ids = datos
    p = pedido(datos, ids[:2])
    caja = Caja(nombre='Prueba')
    db.session.add(caja)
    db.session.flush()
    sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=usuario)
    db.session.add(sesion)
    db.session.flush()
    venta = Venta(id_cliente=cliente, id_sesion_caja=sesion.id_sesion,
                  subtotal=20, total=20, estado='anulada')
    db.session.add(venta)
    db.session.flush()
    p.pago.id_venta = venta.id_venta
    db.session.commit()
    assert analizar(cliente)['pedidos'] == 0
    venta.estado = 'completada'
    p.fecha_creacion = datetime.utcnow() - timedelta(days=400)
    db.session.commit()
    assert analizar(cliente)['pedidos'] == 1
    p.pago.fecha_pago = datetime.utcnow() - timedelta(days=400)
    db.session.commit()
    assert analizar(cliente)['pedidos'] == 0


def test_fallo_al_insertar_preserva_resultados(datos):
    from sqlalchemy import event
    cliente, _, ids = datos
    db.session.add(Par(cliente_id=cliente, id_origen=ids[0], id_destino=ids[1]))
    for _ in range(4):
        pedido(datos, ids[:2])
    for _ in range(8):
        pedido(datos, [ids[2]])
    def fallar(*args):
        raise RuntimeError('insert simulado')
    event.listen(Par, 'before_insert', fallar)
    try:
        with pytest.raises(RuntimeError, match='insert simulado'):
            recalcular(cliente)
    finally:
        event.remove(Par, 'before_insert', fallar)
    assert Par.query.filter_by(cliente_id=cliente).count() == 1
    assert Estado.query.filter_by(cliente_id=cliente).one().token is None


def test_esquema_aditivo_y_ddl_mysql(datos):
    from sqlalchemy.dialects import mysql
    from sqlalchemy.schema import CreateTable, CreateIndex
    db.create_all()  # Repetir no cambia ni elimina datos existentes.
    assert GastronomiaProducto.query.count() == 14
    for tabla in db.metadata.tables.values():
        if not tabla.name.startswith('gastronomia_sugerencias_'):
            continue
        assert 'CREATE TABLE' in str(CreateTable(tabla).compile(dialect=mysql.dialect()))
        for indice in tabla.indexes:
            assert len(indice.name) < 64
            assert str(CreateIndex(indice).compile(dialect=mysql.dialect()))
        assert all(len(c.name) < 64 for c in tabla.constraints if c.name)
