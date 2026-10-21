"""Saldo del mes con lo que se carga a mano, y el mes presentado.

    saldo = débito − crédito − saldo a favor del mes anterior − retenciones

Si da negativo es saldo a favor para el mes siguiente. Cuando un mes se marca
presentado, su saldo a favor se sugiere en el siguiente (sólo de meses
presentados: de uno abierto el número todavía puede cambiar).
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from app import db
from app.models import ContadorMes
from app.services.resumen_contadora import mes_vecino

# Diferencias de redondeo entre la foto y el cálculo de ahora no son cambios.
TOLERANCIA_GS = 1


def _periodo(primero):
    return primero.strftime('%Y-%m')


def registro(primero):
    return ContadorMes.query.filter_by(periodo=_periodo(primero)).first()


def _saldo(debito, credito, saldo_favor_anterior, retenciones):
    return float(debito) - float(credito) - float(saldo_favor_anterior or 0) - float(retenciones or 0)


def saldo_favor_sugerido(primero):
    """El saldo a favor con que cerró el mes anterior, si se marcó presentado."""
    anterior = registro(mes_vecino(primero, -1))
    if anterior is None or not anterior.presentado:
        return None
    saldo = _saldo(anterior.debito_presentado or 0, anterior.credito_presentado or 0,
                   anterior.saldo_favor_anterior, anterior.retenciones)
    return -saldo if saldo < 0 else 0.0


def estado_del_mes(primero, debito, credito):
    """Lo que la pantalla muestra del saldo y de la presentación del mes."""
    r = registro(primero)
    sugerido = saldo_favor_sugerido(primero)
    # El registro sólo nace al guardar los ajustes o al marcar presentado: si
    # existe, lo cargado manda, aunque sea 0 (es la forma de descartar la
    # sugerencia, y es lo que `marcar_presentado` deja guardado).
    cargado = r is not None
    saldo_favor = float(r.saldo_favor_anterior or 0) if cargado else (sugerido or 0.0)
    retenciones = float(r.retenciones or 0) if cargado else 0.0
    cambio = None
    if r is not None and r.presentado:
        antes_d, antes_c = float(r.debito_presentado or 0), float(r.credito_presentado or 0)
        if abs(antes_d - debito) > TOLERANCIA_GS or abs(antes_c - credito) > TOLERANCIA_GS:
            cambio = {'debito_antes': antes_d, 'credito_antes': antes_c}
    return {
        'registro': r,
        'saldo_favor_anterior': saldo_favor,
        'saldo_favor_sugerido': sugerido if not cargado else None,
        'retenciones': retenciones,
        'saldo_final': _saldo(debito, credito, saldo_favor, retenciones),
        'cambio_desde_presentado': cambio,
    }


def _monto(texto):
    limpio = (texto or '').strip()
    if not limpio:
        return Decimal('0')
    # Formato local y capacidad de Numeric(15, 2). No aceptar NaN, infinito,
    # exponentes ni separadores mal puestos que cambien el importe en silencio.
    if not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,[0-9]{1,2})?', limpio):
        return None
    try:
        valor = Decimal(limpio.replace('.', '').replace(',', '.'))
    except InvalidOperation:
        return None
    return valor if valor.is_finite() and 0 <= valor <= Decimal('9999999999999.99') else None


def guardar_ajustes(primero, saldo_favor_texto, retenciones_texto):
    """Guarda saldo anterior y retenciones del mes. Devuelve un error o None."""
    saldo_favor, retenciones = _monto(saldo_favor_texto), _monto(retenciones_texto)
    if saldo_favor is None or retenciones is None:
        return 'Los montos van en guaraníes, sin signo (ej.: 150.000).'
    r = registro(primero) or ContadorMes(periodo=_periodo(primero))
    if r.presentado:
        return 'Volvé a abrir el mes antes de cambiar el saldo anterior o las retenciones.'
    r.saldo_favor_anterior, r.retenciones = saldo_favor, retenciones
    db.session.add(r)
    return None


def marcar_presentado(primero, presentado, debito, credito, id_usuario):
    """Marca (con foto del débito y el crédito de ahora) o desmarca el mes."""
    r = registro(primero) or ContadorMes(periodo=_periodo(primero))
    # Un doble envío o una pestaña vieja no debe reemplazar la foto original.
    if presentado and r.presentado:
        return
    if presentado and r.saldo_favor_anterior is None:
        r.saldo_favor_anterior = Decimal(str(saldo_favor_sugerido(primero) or 0))
    r.presentado = bool(presentado)
    r.presentado_en = datetime.utcnow() if presentado else None
    r.id_usuario_presentado = id_usuario if presentado else None
    r.debito_presentado = Decimal(str(round(debito, 2))) if presentado else None
    r.credito_presentado = Decimal(str(round(credito, 2))) if presentado else None
    db.session.add(r)


__all__ = ['estado_del_mes', 'guardar_ajustes', 'marcar_presentado', 'registro', 'saldo_favor_sugerido']
