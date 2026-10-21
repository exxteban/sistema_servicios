"""Talonario de facturas en papel: número siguiente, timbrado y revisión del mes.

Sólo aplica sin facturación electrónica. La regla del sistema es **advertir,
nunca bloquear** una venta: un número fuera del talonario o repetido se guarda
igual y aparece como pendiente en el resumen del/la contador/a.

Los números se guardan como `001-001-0000123` (establecimiento, punto de
expedición y siete dígitos), que es como van en la factura y en Marangatu.
"""
import re

from app.models import TalonarioFactura, Venta
from app.services.pos_numero_factura import facturacion_electronica_activa
from app.utils.helpers import today_local, utc_bounds_for_local_dates, utc_naive_to_local

DIGITOS_NUMERO = 7
SALTOS_A_MOSTRAR = 10
_COMPLETO = re.compile(r'^(\d{3})-(\d{3})-(\d{1,7})$')
_SOLO_NUMERO = re.compile(r'^\d{1,7}$')


def formatear(talonario, numero):
    return f'{talonario.prefijo}{numero:0{DIGITOS_NUMERO}d}'


def parsear(numero):
    """'001-001-0000123' → ('001', '001', 123). None si no tiene ese formato."""
    coincide = _COMPLETO.match((numero or '').strip())
    if not coincide:
        return None
    establecimiento, punto, correlativo = coincide.groups()
    return establecimiento, punto, int(correlativo)


def _cubre(talonario, fecha, correlativo=None):
    if not (talonario.vigencia_desde <= fecha <= talonario.vigencia_hasta):
        return False
    return correlativo is None or talonario.numero_desde <= correlativo <= talonario.numero_hasta


def vigentes(fecha):
    """Talonarios activos con el timbrado vigente en `fecha`."""
    return [t for t in TalonarioFactura.query.filter_by(activo=True)
            .order_by(TalonarioFactura.establecimiento, TalonarioFactura.punto_expedicion).all()
            if _cubre(t, fecha)]


def _buscar(talonarios, numero, fecha):
    partes = parsear(numero)
    if partes is None:
        return None
    establecimiento, punto, correlativo = partes
    return next((t for t in talonarios
                 if t.establecimiento == establecimiento and t.punto_expedicion == punto
                 and _cubre(t, fecha, correlativo)), None)


def _todos():
    return TalonarioFactura.query.order_by(TalonarioFactura.vigencia_desde.desc()).all()


def talonario_de(numero, fecha):
    """El talonario (activo o no) al que pertenece el número en esa fecha."""
    return _buscar(_todos(), numero, fecha)


def resolvedor_de_timbrado():
    """Para recorrer muchas ventas: carga los talonarios una vez.

    Devuelve `(numero, fecha) → timbrado` o None si el número no cae en
    ningún talonario. Sirve para las ventas cargadas antes del talonario,
    que no tienen el timbrado guardado.
    """
    talonarios = _todos()

    def resolver(numero, fecha):
        talonario = _buscar(talonarios, numero, fecha)
        return talonario.timbrado if talonario else None
    return resolver


def normalizar_numero(texto, fecha):
    """Completa lo que se tipeó: '123' → '001-001-0000123' si hay un solo talonario vigente."""
    texto = (texto or '').strip()
    partes = parsear(texto)
    if partes is not None:
        establecimiento, punto, correlativo = partes
        return f'{establecimiento}-{punto}-{correlativo:0{DIGITOS_NUMERO}d}'
    if _SOLO_NUMERO.match(texto):
        candidatos = vigentes(fecha)
        if len(candidatos) == 1:
            return formatear(candidatos[0], int(texto))
    return texto


def _es_del_talonario(talonario, timbrado, fecha):
    """La venta usó este talonario: mismo timbrado o, sin timbrado guardado, fecha en su vigencia.

    Un timbrado nuevo vuelve a empezar la numeración con el mismo prefijo: las
    facturas del anterior no cuentan.
    """
    timbrado = (timbrado or '').strip()
    if timbrado:
        return timbrado == talonario.timbrado
    return fecha is not None and _cubre(talonario, utc_naive_to_local(fecha).date())


def _correlativos_usados(talonario):
    numeros = Venta.query.filter(Venta.numero_factura.like(f'{talonario.prefijo}%')) \
        .with_entities(Venta.numero_factura, Venta.timbrado, Venta.fecha_venta).all()
    usados = set()
    for numero, timbrado, fecha in numeros:
        partes = parsear(numero)
        if (partes and talonario.numero_desde <= partes[2] <= talonario.numero_hasta
                and _es_del_talonario(talonario, timbrado, fecha)):
            usados.add(partes[2])
    return usados


def siguiente(talonario):
    """El número que sigue al último usado, o None si el talonario se terminó."""
    usados = _correlativos_usados(talonario)
    proximo = max(usados) + 1 if usados else talonario.numero_desde
    return proximo if proximo <= talonario.numero_hasta else None


def sugerencias(fecha=None):
    """Lo que el POS ofrece: el número siguiente de cada talonario vigente."""
    fecha = fecha or today_local()
    resultado = []
    for t in vigentes(fecha):
        proximo = siguiente(t)
        resultado.append({
            'numero': formatear(t, proximo) if proximo is not None else None,
            'timbrado': t.timbrado,
            'vence': t.vigencia_hasta.strftime('%d/%m/%Y'),
            'dias_para_vencer': (t.vigencia_hasta - fecha).days,
            'restantes': (t.numero_hasta - proximo + 1) if proximo is not None else 0,
        })
    return resultado


def completar_venta(venta):
    """Antes de guardar: número con formato completo y timbrado del talonario."""
    if not venta.numero_factura or facturacion_electronica_activa():
        return
    fecha = utc_naive_to_local(venta.fecha_venta).date() if venta.fecha_venta else today_local()
    venta.numero_factura = normalizar_numero(venta.numero_factura, fecha)
    talonario = talonario_de(venta.numero_factura, fecha)
    venta.timbrado = talonario.timbrado if talonario else None


def _saltos(desde, hasta):
    """Números sin ninguna venta (ni anulada) entre el primero y el último del mes.

    Se mira dentro de cada talonario: un número mal tipeado (`…-0999999`) o el
    cambio de un timbrado al siguiente, que vuelve a empezar la numeración,
    no son saltos. Lo que no cae en ningún talonario ya es un pendiente aparte
    (`fuera_de_talonario`). La cantidad se cuenta sin armar la lista entera.
    """
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    ventas = Venta.query.filter(Venta.fecha_venta >= inicio, Venta.fecha_venta < fin,
                                Venta.numero_factura.isnot(None)) \
        .with_entities(Venta.numero_factura, Venta.fecha_venta).all()
    talonarios = _todos()
    por_talonario = {}
    for numero, fecha in ventas:
        partes = parsear(numero)
        if partes is None or fecha is None:
            continue
        talonario = _buscar(talonarios, numero, utc_naive_to_local(fecha).date())
        if talonario is not None:
            por_talonario.setdefault(talonario.id, (talonario, set()))[1].add(partes[2])

    cantidad, numeros = 0, []
    for talonario, usados in sorted(por_talonario.values(), key=lambda par: (par[0].prefijo, par[0].numero_desde)):
        primero, ultimo = min(usados), max(usados)
        cantidad += (ultimo - primero + 1) - len(usados)
        n = primero
        while n <= ultimo and len(numeros) < SALTOS_A_MOSTRAR:
            if n not in usados:
                numeros.append(formatear(talonario, n))
            n += 1
    return {'cantidad': cantidad, 'numeros': numeros}


def revision_del_mes(desde, hasta, filas):
    """Lo que el talonario permite revisar. None si no hay ningún talonario cargado.

    `filas` son las ventas con factura del mes (`iva_por_venta_con_factura`),
    que ya traen el timbrado resuelto.
    """
    if TalonarioFactura.query.count() == 0:
        return None
    fuera = [f for f in filas if not f['timbrado']]
    return {
        'fuera_de_talonario': [{'id_venta': f['id_venta'], 'numero': f['numero']} for f in fuera],
        'saltos': _saltos(desde, hasta),
    }


def _se_superponen(a, b):
    return (a.establecimiento == b.establecimiento and a.punto_expedicion == b.punto_expedicion
            and a.vigencia_desde <= b.vigencia_hasta and b.vigencia_desde <= a.vigencia_hasta
            and a.numero_desde <= b.numero_hasta and b.numero_desde <= a.numero_hasta)


def crear_talonario(timbrado, vigencia_desde, vigencia_hasta, establecimiento, punto,
                    numero_desde, numero_hasta):
    """Valida y arma el talonario (sin guardar). Devuelve (talonario, error)."""
    from app import db

    timbrado = (timbrado or '').strip()
    establecimiento, punto = (establecimiento or '').strip(), (punto or '').strip()
    if not (timbrado.isdigit() and len(timbrado) == 8):
        return None, 'El timbrado son 8 números, como figura en la factura.'
    if not (establecimiento.isdigit() and punto.isdigit() and len(establecimiento) <= 3 and len(punto) <= 3):
        return None, 'Establecimiento y punto de expedición son de hasta 3 números (ej.: 001).'
    if not (vigencia_desde and vigencia_hasta and vigencia_desde <= vigencia_hasta):
        return None, 'Revisá las fechas de vigencia del timbrado.'
    if not (numero_desde and numero_hasta and 1 <= numero_desde <= numero_hasta < 10 ** DIGITOS_NUMERO):
        return None, 'Revisá el rango de números: "desde" no puede ser mayor que "hasta".'
    nuevo = TalonarioFactura(
        timbrado=timbrado, vigencia_desde=vigencia_desde, vigencia_hasta=vigencia_hasta,
        establecimiento=establecimiento.zfill(3), punto_expedicion=punto.zfill(3),
        numero_desde=numero_desde, numero_hasta=numero_hasta, activo=True,
    )
    with db.session.no_autoflush:
        choca = next((t for t in TalonarioFactura.query.filter_by(activo=True) if _se_superponen(t, nuevo)), None)
    if choca is not None:
        return None, (f'Se superpone con el talonario {choca.prefijo}… del timbrado {choca.timbrado}: '
                      'mismos números en las mismas fechas. Desactivá ese primero si lo reemplaza.')
    return nuevo, None


__all__ = ['completar_venta', 'crear_talonario', 'formatear', 'normalizar_numero', 'parsear', 'resolvedor_de_timbrado',
           'revision_del_mes', 'siguiente', 'sugerencias', 'talonario_de', 'vigentes']
