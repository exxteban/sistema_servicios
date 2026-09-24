"""Numeración correlativa del documento electrónico.

SIFEN no asigna el número: lo lleva el emisor, correlativo por establecimiento
y punto de expedición, dentro del rango del timbrado (1 a 9.999.999). Este
servicio reserva el próximo número de forma atómica al emitir; el número del
DE no tiene relación con `venta.numero_factura` (que registra facturas externas).
"""
from app import db
from facturacion_electronica import TIPO_FACTURA, TIPO_NOTA_CREDITO
from facturacion_electronica.models import DocumentoElectronico, SecuenciaNumeracionDE

NUMERO_MAX = 9_999_999

NOMBRE_TIPO = {TIPO_FACTURA: 'Factura', TIPO_NOTA_CREDITO: 'Nota de crédito'}


def _normalizar_codigo(valor, default='001'):
    valor = (valor or '').strip() or default
    return valor.zfill(3)[-3:]


def formatear_numero(numero):
    return str(int(numero or 0)).zfill(7)


def _obtener_secuencia(establecimiento, punto, tipo_documento=TIPO_FACTURA, bloquear=False):
    query = SecuenciaNumeracionDE.query.filter_by(
        tipo_documento=tipo_documento, establecimiento=establecimiento, punto=punto
    )
    if bloquear:
        query = query.with_for_update()
    return query.first()


def peek_proximo_numero(establecimiento, punto, tipo_documento=TIPO_FACTURA):
    """Próximo número sin reservarlo (para vista previa). Devuelve string de 7 dígitos."""
    estab = _normalizar_codigo(establecimiento)
    pto = _normalizar_codigo(punto)
    seq = _obtener_secuencia(estab, pto, tipo_documento)
    return formatear_numero((seq.ultimo_numero if seq else 0) + 1)


def reservar_numero(establecimiento, punto, tipo_documento=TIPO_FACTURA):
    """Reserva atómicamente el próximo correlativo. Devuelve (numero_str, error).

    No hace commit: la reserva participa de la transacción del documento que la
    llama, así un fallo posterior no consume un número en una transacción aparte.
    """
    estab = _normalizar_codigo(establecimiento)
    pto = _normalizar_codigo(punto)

    seq = _obtener_secuencia(estab, pto, tipo_documento, bloquear=True)
    if seq is None:
        seq = SecuenciaNumeracionDE(
            tipo_documento=tipo_documento, establecimiento=estab, punto=pto, ultimo_numero=0,
        )
        db.session.add(seq)
        db.session.flush()

    if seq.ultimo_numero >= NUMERO_MAX:
        return None, f'Se agotó el rango de numeración del timbrado ({NUMERO_MAX:,}).'

    seq.ultimo_numero += 1
    db.session.flush()
    return formatear_numero(seq.ultimo_numero), None


def sembrar_minimo(establecimiento, punto, primer_numero, tipo_documento=TIPO_FACTURA):
    """Sube el correlativo para que el próximo número sea al menos `primer_numero`.

    El timbrado reserva un rango que **no siempre arranca en 1**: el proveedor
    lo declara en `dNumIni`. Si ese rango empieza en 0000501 y nuestro contador
    está en 0, la primera factura saldría 0000001 — fuera del rango del
    timbrado, y SIFEN la rechaza.

    Sólo sube. Bajar repetiría números ya emitidos, así que un `dNumIni` por
    debajo de donde ya vamos se ignora en silencio: significa que el rango
    arrancó antes y nosotros ya avanzamos dentro de él.

    No hace commit: participa de la transacción de quien la llama (la sincro
    del emisor). Devuelve el próximo número si lo movió, o None si no tocó nada.
    """
    estab = _normalizar_codigo(establecimiento)
    pto = _normalizar_codigo(punto)

    try:
        piso = int(str(primer_numero).strip() or 0)
    except (TypeError, ValueError):
        return None
    # 0 y 1 no adelantan nada: el contador ya arranca en 0 y el próximo es 1.
    if piso <= 1 or piso > NUMERO_MAX:
        return None

    seq = _obtener_secuencia(estab, pto, tipo_documento, bloquear=True)
    if seq is None:
        seq = SecuenciaNumeracionDE(
            tipo_documento=tipo_documento, establecimiento=estab, punto=pto, ultimo_numero=0,
        )
        db.session.add(seq)
        db.session.flush()

    if seq.ultimo_numero >= piso - 1:
        return None
    seq.ultimo_numero = piso - 1
    db.session.flush()
    return formatear_numero(piso)


def _maximo_emitido(establecimiento, punto, tipo_documento=TIPO_FACTURA):
    """Mayor número ya emitido en ese establecimiento/punto (0 si no hay ninguno).

    `numero` se guarda como string de 7 dígitos con ceros a la izquierda, así que
    el orden lexicográfico coincide con el numérico.
    """
    fila = (
        db.session.query(db.func.max(DocumentoElectronico.numero))
        .filter(
            DocumentoElectronico.establecimiento == establecimiento,
            DocumentoElectronico.punto == punto,
            _mismo_tipo(tipo_documento),
        )
        .scalar()
    )
    try:
        return int(fila or 0)
    except (TypeError, ValueError):
        return 0


def _mismo_tipo(tipo_documento):
    """Filtro por tipo tolerando los documentos viejos sin tipo cargado: antes
    de las notas de crédito todo lo emitido era factura."""
    if tipo_documento == TIPO_FACTURA:
        return db.or_(
            DocumentoElectronico.tipo_documento.is_(None),
            DocumentoElectronico.tipo_documento == TIPO_FACTURA,
        )
    return DocumentoElectronico.tipo_documento == tipo_documento


def listar_secuencias():
    """Correlativos actuales, para mostrarlos en la pantalla de configuración.

    Incluye el mayor número ya emitido: bajar el correlativo por debajo de ese
    valor haría que se repitan números sobre el mismo timbrado, y SIFEN los
    rechaza.
    """
    filas = SecuenciaNumeracionDE.query.order_by(
        SecuenciaNumeracionDE.tipo_documento,
        SecuenciaNumeracionDE.establecimiento,
        SecuenciaNumeracionDE.punto,
    ).all()

    return [
        {
            'tipo_documento': fila.tipo_documento,
            'tipo_desc': NOMBRE_TIPO.get(fila.tipo_documento, f'Tipo {fila.tipo_documento}'),
            'establecimiento': fila.establecimiento,
            'punto': fila.punto,
            'ultimo_numero': fila.ultimo_numero,
            'proximo': formatear_numero(fila.ultimo_numero + 1),
            'max_emitido': _maximo_emitido(fila.establecimiento, fila.punto, fila.tipo_documento),
            'updated_at': fila.updated_at,
        }
        for fila in filas
    ]


def ajustar_secuencia(establecimiento, punto, ultimo_numero, forzar=False,
                      tipo_documento=TIPO_FACTURA):
    """Fija el correlativo a mano. Devuelve (secuencia, error).

    Sirve para dos casos puntuales del administrador:

    - Volver a 0 antes de pasar a producción: las emisiones de prueba en ambiente
      test consumen correlativo, así que sin el reset la primera factura real
      saldría con el número que dejaron las pruebas.
    - Sembrar el último número usado cuando el cliente ya venía emitiendo con el
      mismo timbrado desde otro sistema.

    A diferencia de `reservar_numero`, hace commit: es una acción aislada y no
    forma parte de la transacción de un documento.
    """
    estab = _normalizar_codigo(establecimiento)
    pto = _normalizar_codigo(punto)

    try:
        valor = int(str(ultimo_numero).strip() or 0)
    except (TypeError, ValueError):
        return None, 'El número debe ser un entero.'

    if valor < 0 or valor > NUMERO_MAX:
        return None, f'El número debe estar entre 0 y {NUMERO_MAX:,}.'

    if not forzar:
        maximo = _maximo_emitido(estab, pto, tipo_documento)
        if valor < maximo:
            return None, (
                f'Ya hay documentos emitidos hasta el {formatear_numero(maximo)} en '
                f'{estab}-{pto}. Bajar el correlativo repetiría números sobre el mismo '
                'timbrado y SIFEN los rechazaría.'
            )

    seq = _obtener_secuencia(estab, pto, tipo_documento, bloquear=True)
    if seq is None:
        seq = SecuenciaNumeracionDE(
            tipo_documento=tipo_documento, establecimiento=estab, punto=pto, ultimo_numero=0,
        )
        db.session.add(seq)

    seq.ultimo_numero = valor
    db.session.commit()
    return seq, None


__all__ = [
    'reservar_numero',
    'sembrar_minimo',
    'peek_proximo_numero',
    'formatear_numero',
    'listar_secuencias',
    'ajustar_secuencia',
    'NUMERO_MAX',
]
