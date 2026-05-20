from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.models import Configuracion

CLAVE_TIPOS_MOVIMIENTO_PERSONALIZADOS = 'control_empleados_tipos_movimiento'
DESC_TIPOS_MOVIMIENTO_PERSONALIZADOS = 'Tipos personalizados de movimientos salariales por cliente'
LONGITUD_MAXIMA_CLAVE_TIPO_MOVIMIENTO = 20
LONGITUD_MAXIMA_NOMBRE_TIPO_MOVIMIENTO = 80
LONGITUD_MAXIMA_UNIDAD_TIPO_MOVIMIENTO = 30
IMPACTO_POSITIVO = 'positivo'
IMPACTO_NEGATIVO = 'negativo'
IMPACTOS_VALIDOS = {IMPACTO_POSITIVO, IMPACTO_NEGATIVO}
MODO_CALCULO_MANUAL = 'manual'
MODO_CALCULO_CANTIDAD = 'cantidad'
MODOS_CALCULO_VALIDOS = {MODO_CALCULO_MANUAL, MODO_CALCULO_CANTIDAD}

TIPOS_MOVIMIENTO_BASE = [
    ('bono', 'Bono', IMPACTO_POSITIVO),
    ('horas_extra', 'Horas extra', IMPACTO_POSITIVO),
    ('comision', 'Comisión', IMPACTO_POSITIVO),
    ('ajuste', 'Ajuste', IMPACTO_POSITIVO),
    ('descuento', 'Descuento', IMPACTO_NEGATIVO),
    ('adelanto', 'Adelanto', IMPACTO_NEGATIVO),
]
TIPOS_MOVIMIENTO_BASE_VALIDOS = frozenset(valor for valor, _label, _impacto in TIPOS_MOVIMIENTO_BASE)
TIPOS_MOVIMIENTO_NEGATIVOS_BASE = frozenset(
    valor for valor, _label, impacto in TIPOS_MOVIMIENTO_BASE if impacto == IMPACTO_NEGATIVO
)


def resolver_scope_tipos_movimiento(cliente_id: int | None) -> int:
    try:
        return int(cliente_id or 0)
    except (TypeError, ValueError):
        return 0


def clave_config_tipos_movimiento(cliente_id: int | None) -> str:
    scope = resolver_scope_tipos_movimiento(cliente_id)
    if scope > 0:
        return f'{CLAVE_TIPOS_MOVIMIENTO_PERSONALIZADOS}__cliente_{scope}'
    return CLAVE_TIPOS_MOVIMIENTO_PERSONALIZADOS


def normalizar_nombre_tipo_movimiento(raw_value: str | None) -> str:
    texto = ' '.join((raw_value or '').split())
    return texto[:LONGITUD_MAXIMA_NOMBRE_TIPO_MOVIMIENTO]


def normalizar_impacto_tipo_movimiento(raw_value: str | None) -> str:
    impacto = (raw_value or '').strip().lower()
    return impacto if impacto in IMPACTOS_VALIDOS else IMPACTO_POSITIVO


def normalizar_modo_calculo_tipo_movimiento(raw_value: str | None) -> str:
    modo = (raw_value or '').strip().lower()
    return modo if modo in MODOS_CALCULO_VALIDOS else MODO_CALCULO_MANUAL


def normalizar_unidad_tipo_movimiento(raw_value: str | None) -> str:
    texto = ' '.join((raw_value or '').split())
    return texto[:LONGITUD_MAXIMA_UNIDAD_TIPO_MOVIMIENTO]


def normalizar_valor_unitario_tipo_movimiento(raw_value) -> Decimal:
    texto = str(raw_value or '').strip().replace(' ', '')
    if ',' in texto and '.' in texto:
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '').replace(',', '.')
        else:
            texto = texto.replace(',', '')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        valor = Decimal(texto or '0')
    except (InvalidOperation, ValueError):
        valor = Decimal('0')
    return max(valor, Decimal('0')).quantize(Decimal('0.01'))


def generar_clave_tipo_movimiento(nombre: str | None) -> str:
    texto = unicodedata.normalize('NFKD', nombre or '')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = re.sub(r'[^a-z0-9]+', '_', texto).strip('_')
    texto = re.sub(r'_+', '_', texto)
    return texto[:LONGITUD_MAXIMA_CLAVE_TIPO_MOVIMIENTO].strip('_')


def humanizar_clave_tipo_movimiento(clave: str | None) -> str:
    texto = (clave or '').strip().replace('_', ' ')
    return texto.title() if texto else 'Tipo'


def formatear_cantidad_movimiento(valor: Decimal) -> str:
    texto = f'{valor.normalize():f}'
    return texto.rstrip('0').rstrip('.') if '.' in texto else texto


def obtener_tipos_movimiento_personalizados(cliente_id: int | None) -> list[dict]:
    raw_value = Configuracion.obtener(clave_config_tipos_movimiento(cliente_id), '[]')
    try:
        datos = json.loads(raw_value or '[]')
    except (TypeError, ValueError):
        return []
    tipos = []
    for item in datos if isinstance(datos, list) else []:
        clave_raw = item.get('clave') if isinstance(item, dict) else None
        clave = (clave_raw or '').strip().lower()
        nombre = normalizar_nombre_tipo_movimiento(item.get('nombre') if isinstance(item, dict) else None)
        impacto = normalizar_impacto_tipo_movimiento(item.get('impacto') if isinstance(item, dict) else None)
        modo_calculo = normalizar_modo_calculo_tipo_movimiento(
            item.get('modo_calculo') if isinstance(item, dict) else None
        )
        unidad = normalizar_unidad_tipo_movimiento(item.get('unidad') if isinstance(item, dict) else None)
        valor_unitario = normalizar_valor_unitario_tipo_movimiento(
            item.get('valor_unitario') if isinstance(item, dict) else None
        )
        if modo_calculo == MODO_CALCULO_CANTIDAD and (not unidad or valor_unitario <= 0):
            modo_calculo = MODO_CALCULO_MANUAL
        if clave and nombre and clave not in TIPOS_MOVIMIENTO_BASE_VALIDOS:
            tipos.append({
                'valor': clave,
                'label': nombre,
                'impacto': impacto,
                'modo_calculo': modo_calculo,
                'unidad': unidad,
                'valor_unitario': str(valor_unitario),
                'eliminable': True,
            })
    return tipos


def guardar_tipos_movimiento_personalizados(cliente_id: int | None, tipos: list[dict]) -> None:
    payload = [
        {
            'clave': tipo['valor'],
            'nombre': tipo['label'],
            'impacto': normalizar_impacto_tipo_movimiento(tipo.get('impacto')),
            'modo_calculo': normalizar_modo_calculo_tipo_movimiento(tipo.get('modo_calculo')),
            'unidad': normalizar_unidad_tipo_movimiento(tipo.get('unidad')),
            'valor_unitario': str(normalizar_valor_unitario_tipo_movimiento(tipo.get('valor_unitario'))),
        }
        for tipo in tipos
        if tipo.get('valor') and tipo.get('label')
    ]
    Configuracion.establecer(
        clave_config_tipos_movimiento(cliente_id),
        json.dumps(payload, ensure_ascii=False),
        descripcion=DESC_TIPOS_MOVIMIENTO_PERSONALIZADOS,
    )


def opciones_tipos_movimiento(cliente_id: int | None = None) -> list[dict]:
    opciones = [
        {
            'valor': valor,
            'label': label,
            'impacto': impacto,
            'modo_calculo': MODO_CALCULO_MANUAL,
            'unidad': '',
            'valor_unitario': '0.00',
            'eliminable': False,
        }
        for valor, label, impacto in TIPOS_MOVIMIENTO_BASE
    ]
    opciones.extend(obtener_tipos_movimiento_personalizados(cliente_id))
    return opciones


def obtener_tipos_validos_movimiento(cliente_id: int | None = None) -> set[str]:
    return {opcion['valor'] for opcion in opciones_tipos_movimiento(cliente_id)}


def obtener_tipo_movimiento(valor: str | None, cliente_id: int | None = None) -> dict | None:
    clave = (valor or '').strip().lower()
    for opcion in opciones_tipos_movimiento(cliente_id):
        if opcion['valor'] == clave:
            return opcion
    return None


def es_tipo_movimiento_negativo(valor: str | None, cliente_id: int | None = None) -> bool:
    clave = (valor or '').strip().lower()
    if clave in TIPOS_MOVIMIENTO_NEGATIVOS_BASE:
        return True
    for opcion in obtener_tipos_movimiento_personalizados(cliente_id):
        if opcion['valor'] == clave:
            return opcion['impacto'] == IMPACTO_NEGATIVO
    return False


def etiqueta_tipo_movimiento(valor: str | None, cliente_id: int | None = None) -> str:
    clave = (valor or '').strip().lower()
    for opcion in opciones_tipos_movimiento(cliente_id):
        if opcion['valor'] == clave:
            return opcion['label']
    return humanizar_clave_tipo_movimiento(clave)
