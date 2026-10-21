"""Gastos con factura: lo que suman al crédito fiscal del mes.

Un pago de gasto corriente (alquiler, luz, internet…) con su factura da
crédito fiscal igual que una compra. Se carga desde el pago con número,
timbrado, RUC y tasa; el monto es siempre el del pago. Cuenta en el mes de
la fecha de la factura. Los retiros del dueño no son gasto del negocio y no
dan crédito fiscal.
"""
import re

from app import db
from app.models import GastoComprobanteFiscal, PagoGastoCorriente
from app.services.resumen_contadora_controles import ruc_invalido
from app.services.talonario_facturas import DIGITOS_NUMERO, parsear
from gastos_corrientes.naturaleza import es_retiro_dueno

TASAS = (10, 5, 0)


def totales(monto, tasa):
    monto = float(monto or 0)
    t = {'exenta': 0.0, 'base5': 0.0, 'iva5': 0.0, 'base10': 0.0, 'iva10': 0.0, 'total': monto}
    if tasa == 10:
        t['iva10'] = monto / 11
        t['base10'] = monto - t['iva10']
    elif tasa == 5:
        t['iva5'] = monto / 21
        t['base5'] = monto - t['iva5']
    else:
        t['exenta'] = monto
    return t


def _pagado(pago):
    return (pago.estado or '').strip().lower() == 'pagado'


def registrar(pago, numero, timbrado, ruc, razon_social, fecha, tasa, id_usuario=None):
    """Guarda, cambia o (con número vacío) quita la factura del pago. Devuelve (comprobante, error)."""
    if not _pagado(pago):
        return None, 'Sólo un pago hecho (no anulado ni pendiente) lleva factura.'
    if es_retiro_dueno(pago.naturaleza_contable):
        return None, 'Es un retiro del dueño: no es gasto del negocio y no da crédito fiscal.'
    actual = pago.comprobante_fiscal
    numero = (numero or '').strip()
    if not numero:
        if actual is not None:
            db.session.delete(actual)
        return None, None
    timbrado, ruc, razon_social = (timbrado or '').strip(), (ruc or '').strip(), (razon_social or '').strip()
    if not (timbrado.isdigit() and len(timbrado) == 8):
        return None, 'El timbrado son 8 números, como figura en la factura.'
    ruc = ruc.replace('.', '').replace(' ', '')
    if not re.fullmatch(r'[0-9]+-[0-9]', ruc) or ruc_invalido(ruc):
        return None, 'Revisá el RUC del proveedor: va con guion y dígito verificador (ej.: 80012345-6).'
    if not razon_social:
        return None, 'Falta el nombre o la razón social del proveedor.'
    if fecha is None:
        return None, 'Falta la fecha de la factura.'
    if tasa not in TASAS:
        return None, 'Elegí la tasa de IVA de la factura.'
    partes = parsear(numero)
    if partes is not None:
        numero = f'{partes[0]}-{partes[1]}-{partes[2]:0{DIGITOS_NUMERO}d}'

    comprobante = actual or GastoComprobanteFiscal(id_pago_gasto_corriente=pago.id_pago_gasto_corriente)
    comprobante.numero, comprobante.timbrado, comprobante.ruc = numero[:80], timbrado, ruc[:50]
    comprobante.razon_social, comprobante.fecha, comprobante.tasa_iva = razon_social[:150], fecha, tasa
    comprobante.id_usuario = id_usuario
    db.session.add(comprobante)
    return comprobante, None


def gastos_del_mes(desde, hasta):
    """Una fila por factura de gasto con fecha en el mes (de pagos no anulados)."""
    filas = (
        GastoComprobanteFiscal.query
        .join(PagoGastoCorriente,
              PagoGastoCorriente.id_pago_gasto_corriente == GastoComprobanteFiscal.id_pago_gasto_corriente)
        .filter(GastoComprobanteFiscal.fecha >= desde, GastoComprobanteFiscal.fecha <= hasta,
                PagoGastoCorriente.estado == 'pagado')
        .order_by(GastoComprobanteFiscal.fecha.asc(), GastoComprobanteFiscal.id.asc())
        .all()
    )
    for c in filas:
        # Si después de cargar la factura el pago se reclasificó como retiro
        # del dueño, deja de ser gasto del negocio (igual que en `pagos_sin_factura`).
        if es_retiro_dueno(c.pago.naturaleza_contable):
            continue
        yield {
            'id_gasto_corriente': c.pago.id_gasto_corriente,
            'fecha': c.fecha, 'numero': c.numero, 'timbrado': c.timbrado,
            'proveedor': c.razon_social, 'ruc': c.ruc,
            'totales': totales(c.pago.monto_pagado, c.tasa_iva),
        }


def pagos_sin_factura(desde, hasta):
    """Pagos de gastos del negocio hechos en el mes sin factura cargada (sólo un aviso)."""
    pagos = (
        PagoGastoCorriente.query
        .outerjoin(GastoComprobanteFiscal,
                   GastoComprobanteFiscal.id_pago_gasto_corriente == PagoGastoCorriente.id_pago_gasto_corriente)
        .filter(PagoGastoCorriente.estado == 'pagado', GastoComprobanteFiscal.id.is_(None),
                PagoGastoCorriente.fecha_pago >= desde, PagoGastoCorriente.fecha_pago <= hasta)
        .all()
    )
    pagos = [p for p in pagos if not es_retiro_dueno(p.naturaleza_contable)]
    return {'cantidad': len(pagos), 'total': sum(float(p.monto_pagado or 0) for p in pagos)}


__all__ = ['TASAS', 'gastos_del_mes', 'pagos_sin_factura', 'registrar', 'totales']
