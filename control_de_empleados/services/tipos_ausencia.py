from __future__ import annotations

import re
import unicodedata

from control_de_empleados.models import EmpleadoTipoAusencia

LONGITUD_MAXIMA_CLAVE_TIPO_AUSENCIA = 20
LONGITUD_MAXIMA_NOMBRE_TIPO_AUSENCIA = 80
CLIENTE_GLOBAL_TIPOS_AUSENCIA = 0

TIPOS_AUSENCIA_BASE = [
    ('vacaciones', 'Vacaciones'),
    ('dia_libre', 'Día libre'),
    ('permiso', 'Permiso'),
    ('reposo', 'Reposo'),
    ('llegada_tardia', 'Llegada tardía'),
]

MAPA_TIPOS_AUSENCIA_BASE = dict(TIPOS_AUSENCIA_BASE)
TIPOS_AUSENCIA_BASE_VALIDOS = frozenset(MAPA_TIPOS_AUSENCIA_BASE)


def resolver_scope_tipos_ausencia(cliente_id: int | None) -> int:
    try:
        return int(cliente_id or CLIENTE_GLOBAL_TIPOS_AUSENCIA)
    except (TypeError, ValueError):
        return CLIENTE_GLOBAL_TIPOS_AUSENCIA


def es_tipo_ausencia_base(clave: str | None) -> bool:
    return (clave or '').strip().lower() in TIPOS_AUSENCIA_BASE_VALIDOS


def normalizar_nombre_tipo_ausencia(raw_value: str | None) -> str:
    texto = ' '.join((raw_value or '').split())
    return texto[:LONGITUD_MAXIMA_NOMBRE_TIPO_AUSENCIA]


def humanizar_clave_tipo_ausencia(clave: str | None) -> str:
    texto = (clave or '').strip().replace('_', ' ')
    return texto.title() if texto else 'Tipo'


def generar_clave_tipo_ausencia(nombre: str | None) -> str:
    texto = unicodedata.normalize('NFKD', nombre or '')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = re.sub(r'[^a-z0-9]+', '_', texto).strip('_')
    texto = re.sub(r'_+', '_', texto)
    return texto[:LONGITUD_MAXIMA_CLAVE_TIPO_AUSENCIA].strip('_')


def obtener_tipos_ausencia_personalizados(cliente_id: int | None) -> list[EmpleadoTipoAusencia]:
    scope = resolver_scope_tipos_ausencia(cliente_id)
    return EmpleadoTipoAusencia.query.filter(
        EmpleadoTipoAusencia.cliente_id == scope,
    ).order_by(
        EmpleadoTipoAusencia.nombre.asc(),
        EmpleadoTipoAusencia.id_tipo_ausencia.asc(),
    ).all()


def opciones_tipos_ausencia(cliente_id: int | None = None) -> list[dict]:
    opciones = [
        {
            'valor': valor,
            'label': label,
            'base': True,
            'eliminable': False,
        }
        for valor, label in TIPOS_AUSENCIA_BASE
    ]
    for tipo in obtener_tipos_ausencia_personalizados(cliente_id):
        if tipo.clave in TIPOS_AUSENCIA_BASE_VALIDOS:
            continue
        opciones.append(
            {
                'valor': tipo.clave,
                'label': tipo.nombre,
                'base': False,
                'eliminable': True,
                'id_tipo_ausencia': tipo.id_tipo_ausencia,
            }
        )
    return opciones


def obtener_tipos_validos_ausencia(cliente_id: int | None = None) -> set[str]:
    return {opcion['valor'] for opcion in opciones_tipos_ausencia(cliente_id)}


def etiqueta_tipo_ausencia(valor: str | None, cliente_id: int | None = None) -> str:
    clave = (valor or '').strip().lower()
    if not clave:
        return 'Tipo'
    for opcion in opciones_tipos_ausencia(cliente_id):
        if opcion['valor'] == clave:
            return opcion['label']
    return humanizar_clave_tipo_ausencia(clave)
