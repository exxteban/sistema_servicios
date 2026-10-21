"""Avisos de conciliación; nunca corrigen ni eliminan datos históricos."""
from datetime import date

from app.models import Devolucion, NotaCreditoPapel, Venta
from app.services.devoluciones import monto_reembolsable, precio_reembolsable, precios_reembolsables
from app.services.talonario_facturas import parsear


def comprobantes_repetidos(compras, desde, hasta):
    """Un mismo comprobante en compras/gastos puede duplicar el crédito.

    Los pagos parciales pueden compartir factura: se pide revisar, no se
    excluye automáticamente ninguno de los importes registrados.
    """
    from app.services.gastos_credito_fiscal import gastos_del_mes

    grupos = {}
    for tipo, filas in (('Compra', compras), ('Gasto', gastos_del_mes(desde, hasta))):
        for fila in filas:
            ruc = fila['ruc'].strip().replace('.', '').replace(' ', '')
            numero = fila['numero'].strip()
            if not ruc or not numero:
                continue
            clave = (ruc, fila['timbrado'].strip(), parsear(numero) or numero)
            grupo = grupos.setdefault(clave, {'numero': numero, 'ruc': ruc, 'origenes': []})
            identificador = fila['id_compra'] if tipo == 'Compra' else fila['id_gasto_corriente']
            grupo['origenes'].append(f'{tipo} #{identificador}')
    return [
        f"Comprobante {g['numero']} del RUC {g['ruc']} repetido en "
        f"{', '.join(g['origenes'])}: todos los importes suman crédito. "
        "Verificá si son pagos parciales o una carga duplicada."
        for g in grupos.values() if len(g['origenes']) > 1
    ]


def notas_excesivas(desde: date, hasta: date):
    """NC antiguas que acreditaron precios sin el descuento de la venta."""
    devoluciones = (
        Devolucion.query.join(Venta, Venta.id_venta == Devolucion.id_venta)
        .join(NotaCreditoPapel, NotaCreditoPapel.id_devolucion == Devolucion.id_devolucion)
        .filter(NotaCreditoPapel.fecha >= desde, NotaCreditoPapel.fecha <= hasta,
                Devolucion.estado != 'anulada', Venta.estado != 'anulada')
        .all()
    )
    avisos = []
    for devolucion in devoluciones:
        precios = precios_reembolsables(devolucion.venta)
        for detalle in devolucion.detalles:
            original = detalle.detalle_venta_original
            if original is None:
                continue
            esperado = monto_reembolsable(
                precio_reembolsable(devolucion.venta, original, precios), detalle.cantidad)
            if float(detalle.subtotal or 0) > float(esperado) + 1:
                avisos.append(
                    f"Nota de crédito {devolucion.nota_credito_papel.numero}, "
                    f"venta #{devolucion.id_venta}: el importe devuelto supera el cobrado "
                    "para esos productos con su descuento. Revisá la devolución y el comprobante; "
                    "los importes históricos se mantienen.")
                break
    return avisos
