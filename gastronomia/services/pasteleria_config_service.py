"""Configuracion de pasteleria/cafeteria que solo root puede cambiar.

Por ahora expone solo los encargos (Fase 1): los demas flags existen en la
tabla pero sus funciones todavia no estan construidas, asi que no se ofrecen.
Ver plan_pasteleria.md, decision 2.
"""
from __future__ import annotations

from app import db
from app.models import Cliente
from app.utils.auditoria_utils import registrar_auditoria
from gastronomia.config_flags import FLAG_ENCARGOS, FOTOS_ENCARGO_DEFAULT, OPCIONES_CANCELACION
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.services.pasteleria_flags import parametros_encargos


ANTICIPO_HORAS_MAX = 720
MAX_POR_DIA_MAX = 500
MAX_FOTOS_MAX = 10
ETIQUETAS_CANCELACION = {
    'devolver_todo': 'Devolver todo',
    'retener_todo': 'Retener todo',
    'retener_parcial': 'Retener una parte',
}


def listar_configs_pasteleria() -> list[dict]:
    """Negocios con Gastronomia activa y su configuracion de encargos."""
    configs = (
        GastronomiaClienteConfig.query
        .filter(GastronomiaClienteConfig.gastronomia_activo.is_(True))
        .order_by(GastronomiaClienteConfig.cliente_id.asc())
        .all()
    )
    resultado = []
    for config in configs:
        cliente = db.session.get(Cliente, int(config.cliente_id))
        resultado.append({
            'cliente_id': int(config.cliente_id),
            'cliente_nombre': getattr(cliente, 'nombre', None) or f'Cliente #{config.cliente_id}',
            'encargos_activo': bool(config.encargos_activo),
            'parametros': parametros_encargos(config.cliente_id),
        })
    return resultado


def guardar_config_encargos(cliente_id: int, data, *, usuario_id: int | None = None) -> GastronomiaClienteConfig:
    """Guarda flag y parametros de encargos. `data` es un dict o un MultiDict de formulario."""
    config = GastronomiaClienteConfig.query.filter_by(cliente_id=int(cliente_id)).first()
    if not config or not config.gastronomia_activo:
        raise ValueError('Este negocio no tiene Gastronomia activa.')

    anterior = _snapshot(config)
    config.encargos_activo = _bool(data.get(FLAG_ENCARGOS))
    config.encargos_anticipo_horas = _entero(data.get('encargos_anticipo_horas'), 'El anticipo', 0, ANTICIPO_HORAS_MAX) or 0
    config.encargos_max_por_dia = _entero(data.get('encargos_max_por_dia'), 'El tope por dia', 1, MAX_POR_DIA_MAX)
    max_fotos = _entero(data.get('encargos_max_fotos'), 'El maximo de fotos', 0, MAX_FOTOS_MAX)
    config.encargos_max_fotos = FOTOS_ENCARGO_DEFAULT if max_fotos is None else max_fotos  # 0 = sin fotos
    config.encargos_cancelacion_opciones = ','.join(_opciones(data))
    if usuario_id:
        config.actualizado_por_id = int(usuario_id)

    registrar_auditoria(
        accion='configurar_encargos_gastronomia',
        modulo='gastronomia',
        descripcion=f'Configuracion de encargos del cliente #{cliente_id}',
        referencia_tipo='gastronomia_cliente_config',
        referencia_id=int(config.id_config),
        datos_anteriores=anterior,
        datos_nuevos=_snapshot(config),
        commit=False,
    )
    db.session.commit()
    return config


def _snapshot(config: GastronomiaClienteConfig) -> dict:
    return {
        'encargos_activo': bool(config.encargos_activo),
        'encargos_anticipo_horas': config.encargos_anticipo_horas,
        'encargos_max_por_dia': config.encargos_max_por_dia,
        'encargos_max_fotos': config.encargos_max_fotos,
        'encargos_cancelacion_opciones': config.encargos_cancelacion_opciones,
    }


def _bool(valor) -> bool:
    return str(valor or '').strip().lower() in {'1', 'true', 'on', 'si', 'yes'}


def _entero(valor, nombre: str, minimo: int, maximo: int) -> int | None:
    """Entero dentro de rango; vacio devuelve None."""
    texto = str(valor if valor is not None else '').strip()
    if not texto:
        return None
    try:
        numero = int(texto)
    except ValueError:
        raise ValueError(f'{nombre} tiene que ser un numero entero.')
    if numero < minimo or numero > maximo:
        raise ValueError(f'{nombre} tiene que estar entre {minimo} y {maximo}.')
    return numero


def _opciones(data) -> list[str]:
    if hasattr(data, 'getlist'):
        pedidas = data.getlist('encargos_cancelacion_opciones')
    else:
        pedidas = data.get('encargos_cancelacion_opciones') or []
        if isinstance(pedidas, str):
            pedidas = pedidas.split(',')
    elegidas = [opcion for opcion in OPCIONES_CANCELACION if opcion in {str(p).strip() for p in pedidas}]
    if not elegidas:
        raise ValueError('Deja al menos una opcion para resolver la sena al cancelar.')
    return elegidas
