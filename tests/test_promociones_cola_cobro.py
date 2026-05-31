from datetime import datetime, timedelta

from app import create_app, db
from app.models import Categoria, Cliente, Producto, TiendaPromocion, TiendaPromocionProducto
from app.routes.ventas.parte1 import _normalizar_items_para_cola_cobro


def test_cola_normal_aplica_dos_por_uno_y_conserva_precio_base():
    app = create_app('testing')
    with app.app_context():
        cliente = Cliente(nombre='Cliente promo cola', tipo='minorista', activo=True)
        categoria = Categoria(nombre='Categoria promo cola', activo=True)
        db.session.add_all([cliente, categoria])
        db.session.flush()
        producto = Producto(
            codigo='PROMO-COLA-001',
            nombre='Producto promo cola',
            id_categoria=categoria.id_categoria,
            id_cliente=cliente.id_cliente,
            precio_compra=10000,
            precio_venta=25000,
            stock_actual=10,
            stock_minimo=0,
            activo=True,
        )
        promocion = TiendaPromocion(
            id_cliente=cliente.id_cliente,
            nombre='Dos por uno cola',
            tipo='cantidad',
            valor=1,
            cantidad_lleva=2,
            cantidad_paga=1,
            fecha_inicio=datetime.utcnow() - timedelta(hours=1),
            fecha_fin=datetime.utcnow() + timedelta(hours=1),
            activa=True,
        )
        db.session.add_all([producto, promocion])
        db.session.flush()
        db.session.add(TiendaPromocionProducto(
            id_promocion=promocion.id_promocion,
            id_producto=producto.id_producto,
        ))
        db.session.commit()

        items, subtotal = _normalizar_items_para_cola_cobro([{
            'id_producto': producto.id_producto,
            'cantidad': 3,
        }])

        assert subtotal == 50000
        assert items[0]['precio'] == 25000
        assert items[0]['subtotal'] == 50000
        assert items[0]['subtotal_cantidad'] == 3
        assert items[0]['promocion_activa']['tipo'] == 'cantidad'
