"""Controles de los datos del mes antes de pasárselos al/la contador/a.

Lo que Marangatu (o el/la contador/a al cargarlo) rechazaría:

- **Compras sin timbrado:** el comprobante de compra lleva timbrado; sin él el
  IVA no se puede deducir.
- **Compras cuyo IVA no cierra:** el IVA cargado es mayor de lo que el total
  permite (gravadas + IVA > total). Suele ser un error al cargar la compra.
- **RUC con dígito verificador inválido:** de los proveedores de esas compras
  y, sin facturación electrónica, de los clientes de las ventas con factura
  (con SIFEN ya lo valida la emisión). Una cédula sola, sin guion, no tiene
  dígito verificador y no se marca.

Todo es pendiente: se corrige en la compra, el proveedor o el cliente.
"""
from sqlalchemy import func

from app.models import Cliente, Venta
from app.services.resumen_contadora import iva_por_compra
from app.utils.helpers import utc_bounds_for_local_dates

# Redondeos del IVA cargado a mano: unos guaraníes no son un error.
TOLERANCIA_GS = 5
FILAS_A_MOSTRAR = 10


def ruc_invalido(ruc):
    """True si es un RUC 'raíz-DV' cuyo DV no corresponde a la raíz."""
    from facturacion_electronica.services.validacion import digito_verificador_ruc

    texto = (ruc or '').strip().replace('.', '').replace(' ', '')
    if '-' not in texto:
        return False
    raiz, dv = texto.rsplit('-', 1)
    if not raiz.isdigit():
        return False   # RUC con letras (extranjeros): no se puede verificar acá.
    return not dv.isdigit() or digito_verificador_ruc(raiz) != int(dv)


def _iva_no_cierra(totales):
    con_iva = totales['iva10'] * 11 + totales['iva5'] * 21
    return con_iva > totales['total'] + TOLERANCIA_GS


def _clientes_de_ventas_con_factura(desde, hasta):
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    return (
        Cliente.query.join(Venta, Venta.id_cliente == Cliente.id_cliente)
        .filter(Venta.fecha_venta >= inicio, Venta.fecha_venta < fin, Venta.estado == 'completada',
                func.trim(func.coalesce(Venta.numero_factura, '')) != '')
        .distinct().all()
    )


def _bloque(filas):
    return {'cantidad': len(filas), 'filas': filas[:FILAS_A_MOSTRAR]}


def controles_del_mes(desde, hasta, fe_activa):
    from app.services.resumen_contadora_revision import comprobantes_repetidos, notas_excesivas

    compras = list(iva_por_compra(desde, hasta))
    sin_timbrado = [c for c in compras if not c['timbrado']]
    no_cierra = [c for c in compras if _iva_no_cierra(c['totales'])]

    ruc_invalidos, vistos = [], set()
    for c in compras:
        if c['ruc'] and ('proveedor', c['ruc']) not in vistos and ruc_invalido(c['ruc']):
            vistos.add(('proveedor', c['ruc']))
            ruc_invalidos.append({'tipo': 'Proveedor', 'nombre': c['proveedor'], 'ruc': c['ruc'],
                                  'id_compra': c['id_compra'], 'id_cliente': None})
    if not fe_activa:
        for cliente in _clientes_de_ventas_con_factura(desde, hasta):
            if ruc_invalido(cliente.ruc_ci):
                ruc_invalidos.append({'tipo': 'Cliente', 'nombre': cliente.nombre, 'ruc': cliente.ruc_ci.strip(),
                                      'id_compra': None, 'id_cliente': cliente.id_cliente})

    resultado = {
        'compras_sin_timbrado': _bloque(sin_timbrado),
        'iva_no_cierra': _bloque(no_cierra),
        'ruc_invalidos': _bloque(ruc_invalidos),
        'conciliacion': _bloque(comprobantes_repetidos(compras, desde, hasta)
                               + (notas_excesivas(desde, hasta) if not fe_activa else [])),
    }
    resultado['cantidad'] = sum(b['cantidad'] for b in resultado.values())
    return resultado


__all__ = ['controles_del_mes', 'ruc_invalido']
