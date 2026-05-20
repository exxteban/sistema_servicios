"""
Servicio centralizado para identificar el "metodo de pago efectivo".

Problema que resuelve
---------------------
Antes existian 5+ implementaciones duplicadas que resolvian el metodo
efectivo por matcheo de nombre, con fallback silencioso a `id_metodo_pago = 1`.
Si alguien renombraba "Efectivo" o creaba otro metodo con id menor, todo el
cuadre y las validaciones de anulaciones apuntaban al metodo equivocado
sin errores visibles.

Este servicio:
- Permite fijar un `id_metodo_pago` canonico via `Configuracion`
  (clave `metodo_pago_efectivo_id`).
- Si no hay clave, cae en un matcher por nombre determinista.
- Nunca cae a `id = 1` por default: si no se puede resolver, devuelve
  `None` y el llamador trabaja en modo "sin efectivo conocido".

Todos los sitios de ventas, caja, cobranzas, pedidos y reportes deben
consumir este servicio en lugar de replicar logica.
"""
from __future__ import annotations

from typing import Iterable, Optional

from app import db
from app.models.configuracion import Configuracion
from app.models.venta import MetodoPago


# Clave de configuracion donde el admin puede fijar el metodo efectivo.
CLAVE_METODO_EFECTIVO_ID = 'metodo_pago_efectivo_id'
DESC_METODO_EFECTIVO_ID = (
    'Identificador del MetodoPago que representa "Efectivo" para el cuadre de caja. '
    'Si esta vacio se usa match por nombre.'
)


def _norm(nombre: Optional[str]) -> str:
    """Normaliza un nombre para comparacion insensitive a acentos/espacios."""
    s = (nombre or '').strip().lower()
    reemplazos = (
        ('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'),
    )
    for a, b in reemplazos:
        s = s.replace(a, b)
    return ' '.join(s.split())


def _ordenar_candidatos(metodos: Iterable[MetodoPago]) -> list[MetodoPago]:
    return sorted(
        metodos,
        key=lambda m: (
            int(getattr(m, 'orden_display', 0) or 0),
            int(getattr(m, 'id_metodo_pago', 0) or 0),
        ),
    )


def _resolver_por_nombre(metodos: Iterable[MetodoPago]) -> Optional[MetodoPago]:
    """Match por nombre: primero exacto "efectivo", luego contains "efectivo"."""
    lista = list(metodos)
    for m in lista:
        if _norm(getattr(m, 'nombre', '')) == 'efectivo':
            return m
    candidatos = [m for m in lista if 'efectivo' in _norm(getattr(m, 'nombre', ''))]
    if candidatos:
        return _ordenar_candidatos(candidatos)[0]
    return None


def obtener_metodo_efectivo(
    metodos: Optional[Iterable[MetodoPago]] = None,
    *,
    solo_activos: bool = False,
) -> Optional[MetodoPago]:
    """
    Resuelve cual es el MetodoPago que representa "Efectivo".

    Orden de resolucion:
      1. `Configuracion[CLAVE_METODO_EFECTIVO_ID]` si apunta a un metodo
         existente (y activo si `solo_activos=True`).
      2. Match por nombre ("efectivo" exacto -> contains "efectivo").
      3. None si no se encuentra (no hay fallback a id=1).
    """
    if metodos is None:
        query = MetodoPago.query
        if solo_activos:
            query = query.filter_by(activo=True)
        metodos_lista = query.all()
    else:
        metodos_lista = list(metodos)
        if solo_activos:
            metodos_lista = [m for m in metodos_lista if bool(getattr(m, 'activo', True))]

    id_configurado = Configuracion.obtener_int(CLAVE_METODO_EFECTIVO_ID, default=0)
    if id_configurado:
        for m in metodos_lista:
            if int(getattr(m, 'id_metodo_pago', 0) or 0) == int(id_configurado):
                return m
        # Si la config apunta a un id que no esta en la lista filtrada,
        # buscamos en la tabla completa para dar mejor diagnostico arriba.
        metodo = db.session.get(MetodoPago, int(id_configurado))
        if metodo is not None and (not solo_activos or bool(getattr(metodo, 'activo', True))):
            return metodo

    return _resolver_por_nombre(metodos_lista)


def asegurar_metodo_efectivo_configurado(*, solo_activos: bool = True) -> Optional[MetodoPago]:
    valor_actual = (Configuracion.obtener(CLAVE_METODO_EFECTIVO_ID, '') or '').strip()
    if valor_actual:
        return obtener_metodo_efectivo(solo_activos=solo_activos)

    query = MetodoPago.query
    if solo_activos:
        query = query.filter_by(activo=True)
    metodos = query.all()

    exactos = [m for m in metodos if _norm(getattr(m, 'nombre', '')) == 'efectivo']
    if len(exactos) == 1:
        metodo = exactos[0]
    elif len(exactos) > 1:
        return _resolver_por_nombre(metodos)
    else:
        candidatos = [m for m in metodos if 'efectivo' in _norm(getattr(m, 'nombre', ''))]
        if len(candidatos) != 1:
            return _resolver_por_nombre(metodos)
        metodo = candidatos[0]

    Configuracion.establecer(
        CLAVE_METODO_EFECTIVO_ID,
        str(int(metodo.id_metodo_pago)),
        DESC_METODO_EFECTIVO_ID,
    )
    return metodo


def obtener_metodo_efectivo_id(
    metodos: Optional[Iterable[MetodoPago]] = None,
    *,
    solo_activos: bool = False,
) -> Optional[int]:
    metodo = obtener_metodo_efectivo(metodos, solo_activos=solo_activos)
    if metodo is None:
        return None
    try:
        return int(metodo.id_metodo_pago)
    except Exception:
        return None


def es_metodo_efectivo(metodo_o_nombre, *, metodo_efectivo: Optional[MetodoPago] = None) -> bool:
    """
    Responde si `metodo_o_nombre` es "efectivo".

    Acepta:
      - Instancia de MetodoPago: compara por id con el metodo canonico.
      - str o None: compara por nombre normalizado.

    Para evitar N+1, los call sites que recorren muchos metodos pueden
    precargar el metodo canonico via `metodo_efectivo`.
    """
    if metodo_o_nombre is None:
        return False

    # Resolver el metodo canonico una sola vez si no fue pasado.
    canonico = metodo_efectivo if metodo_efectivo is not None else obtener_metodo_efectivo()

    if isinstance(metodo_o_nombre, MetodoPago):
        if canonico is not None:
            try:
                return int(metodo_o_nombre.id_metodo_pago) == int(canonico.id_metodo_pago)
            except Exception:
                pass
        # Fallback por nombre si no hay canonico resoluble.
        return 'efectivo' in _norm(metodo_o_nombre.nombre)

    # Recibimos string/nombre.
    nombre_norm = _norm(str(metodo_o_nombre))
    if canonico is not None:
        return nombre_norm == _norm(canonico.nombre)
    return 'efectivo' in nombre_norm


def diagnostico_metodo_efectivo() -> dict:
    """
    Informa como se esta resolviendo el metodo efectivo, para mostrar en
    herramientas de administracion o logs.

    Retorna: {
      'id_configurado': int | None,
      'config_valida': bool,
      'metodo_resuelto_id': int | None,
      'metodo_resuelto_nombre': str | None,
      'origen': 'configuracion' | 'nombre' | 'no_resuelto',
      'candidatos_nombre': [ { id, nombre, activo } ],
      'advertencias': [ str ],
    }
    """
    advertencias: list[str] = []
    id_configurado = Configuracion.obtener_int(CLAVE_METODO_EFECTIVO_ID, default=0)
    config_valida = False
    metodo_config = None
    if id_configurado:
        metodo_config = db.session.get(MetodoPago, int(id_configurado))
        if metodo_config is None:
            advertencias.append(
                f'La clave `{CLAVE_METODO_EFECTIVO_ID}` apunta al id {id_configurado}, '
                f'pero ese metodo de pago no existe.'
            )
        elif not bool(getattr(metodo_config, 'activo', True)):
            advertencias.append(
                f'La clave `{CLAVE_METODO_EFECTIVO_ID}` apunta a "{metodo_config.nombre}", '
                f'pero ese metodo esta inactivo.'
            )
            config_valida = True
        else:
            config_valida = True

    todos = MetodoPago.query.all()
    candidatos_por_nombre = [m for m in todos if 'efectivo' in _norm(getattr(m, 'nombre', ''))]

    if config_valida and metodo_config is not None:
        metodo_resuelto = metodo_config
        origen = 'configuracion'
    else:
        metodo_resuelto = _resolver_por_nombre(todos)
        origen = 'nombre' if metodo_resuelto is not None else 'no_resuelto'

    if origen == 'no_resuelto':
        advertencias.append(
            'No se pudo resolver el metodo efectivo. Configure la clave '
            f'`{CLAVE_METODO_EFECTIVO_ID}` o asegurese de que exista un metodo '
            'llamado "Efectivo" activo.'
        )
    elif origen == 'nombre' and len(candidatos_por_nombre) > 1:
        advertencias.append(
            'Hay mas de un metodo con "efectivo" en el nombre. Se esta usando '
            f'"{metodo_resuelto.nombre}" (id {metodo_resuelto.id_metodo_pago}). '
            f'Para forzar otro, seteá la clave `{CLAVE_METODO_EFECTIVO_ID}`.'
        )

    return {
        'id_configurado': int(id_configurado) if id_configurado else None,
        'config_valida': config_valida,
        'metodo_resuelto_id': int(metodo_resuelto.id_metodo_pago) if metodo_resuelto else None,
        'metodo_resuelto_nombre': metodo_resuelto.nombre if metodo_resuelto else None,
        'origen': origen,
        'candidatos_nombre': [
            {
                'id': int(m.id_metodo_pago),
                'nombre': m.nombre,
                'activo': bool(getattr(m, 'activo', True)),
            }
            for m in candidatos_por_nombre
        ],
        'advertencias': advertencias,
    }
