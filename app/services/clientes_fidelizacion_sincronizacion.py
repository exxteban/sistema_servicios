from datetime import datetime, timedelta

from app import db
from app.models import ClienteFidelizacionMovimiento, Configuracion, Venta
from app.services.clientes_fidelizacion_support import compras_ventana_dias_config


CONFIG_FIDELIZACION_ACTIVA = 'clientes_fidelizacion_activa'


def sincronizar_compras_fidelizacion_pendientes(id_cliente=None):
    if not Configuracion.obtener_bool(CONFIG_FIDELIZACION_ACTIVA, default=False):
        return 0

    desde = datetime.utcnow() - timedelta(days=compras_ventana_dias_config())
    ventas_query = Venta.query.filter(
        Venta.estado == 'completada',
        Venta.id_cliente.isnot(None),
        Venta.id_cliente != 1,
        Venta.fecha_venta >= desde,
    )
    if id_cliente is not None:
        ventas_query = ventas_query.filter(Venta.id_cliente == int(id_cliente))

    ventas = ventas_query.order_by(Venta.fecha_venta.asc(), Venta.id_venta.asc()).all()
    if not ventas:
        return 0

    ids_venta = [int(venta.id_venta) for venta in ventas]
    ya_procesadas = {
        int(row[0])
        for row in db.session.query(ClienteFidelizacionMovimiento.referencia_id)
        .filter(
            ClienteFidelizacionMovimiento.tipo_movimiento == 'compra_venta',
            ClienteFidelizacionMovimiento.referencia_tipo == 'venta',
            ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
            ClienteFidelizacionMovimiento.referencia_id.in_(ids_venta),
        )
        .all()
        if row[0] is not None
    }
    pendientes = [venta for venta in ventas if int(venta.id_venta) not in ya_procesadas]
    if not pendientes:
        return 0

    from app.services.clientes_fidelizacion import registrar_compra_fidelizacion_por_venta

    procesadas = 0
    for venta in pendientes:
        registrar_compra_fidelizacion_por_venta(venta, id_usuario=None)
        procesadas += 1
    db.session.flush()
    return procesadas
