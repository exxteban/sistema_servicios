"""Carga de los datos del emisor en la API externa (`PUT /sifen/me/`).

Con la API los datos del emisor que van en el XML son los de ella, no los de
nuestra configuración: si en la API falta la actividad económica, la emisión
rebota con 400 `company_missing_data` aunque acá esté cargada. Se edita en
"Datos del emisor" (con los selectores oficiales de ubicación) y desde acá se
sube todo lo que la API deja editar al comercio. El RUC y el DV los cambia
sólo el admin del proveedor.

El `PUT` pide `If-Match` con la `version` del último `GET /sifen/me/` (lock
optimista) y después se relee el perfil, igual que al cargar un timbrado.
"""
import re

from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_perfil import (
    aplicar_perfil_al_config,
    obtener_perfil,
    olvidar_perfil,
)
from facturacion_electronica.services.validacion import email_valido

# tdTel: de 6 a 15 caracteres.
TELEFONO_MIN = 6
TELEFONO_MAX = 15
TIPOS_CONTRIBUYENTE = {1: 'Persona física', 2: 'Persona jurídica'}


def actualizar_perfil_remoto(config, cuerpo):
    """`PUT /sifen/me/` con el lock optimista y resincroniza. (resumen, error)."""
    perfil, error = obtener_perfil(config, refrescar=True)
    if error:
        return None, error
    version = perfil.get('version')
    if version is None:
        return None, 'La API no informó la versión del perfil; no se puede actualizar.'

    _respuesta, error = api_client.solicitar(
        config, 'PUT', '/sifen/me/', json=cuerpo, headers={'If-Match': str(version)},
    )
    if error:
        return None, error

    olvidar_perfil()
    perfil, error = obtener_perfil(config, refrescar=True)
    if error:
        return None, f'Se cargó, pero no se pudo releer el perfil: {error}'
    return aplicar_perfil_al_config(config, perfil), None


def _entero(valor):
    try:
        return int(str(valor or '').strip())
    except ValueError:
        return None


def armar_datos_fiscales(config):
    """Cuerpo del `PUT` con el emisor guardado en la configuración. (cuerpo, error).

    Sale todo junto y no sólo lo que la API marca como faltante: la API no
    exige dirección ni ubicación (sus `emission_readiness` no las miran) y sus
    valores por defecto son Asunción con el departamento 11, que en SIFEN es
    Alto Paraná. Sin la dirección real la factura se arma con datos que no son
    del emisor, o no se arma.
    """
    faltan = []
    razon_social = (config.razon_social or '').strip()
    direccion = (config.direccion or '').strip()
    telefono = (config.telefono or '').strip()
    email = (config.email or '').strip()
    actividad = (config.actividad_economica_codigo or '').strip()
    actividad_desc = (config.actividad_economica_desc or '').strip()
    departamento = _entero(config.departamento_codigo)
    ciudad = _entero(config.ciudad_codigo)
    tipo = _entero(config.tipo_contribuyente)

    if not razon_social:
        faltan.append('razón social')
    if tipo not in TIPOS_CONTRIBUYENTE:
        faltan.append('tipo de contribuyente')
    elif tipo == 1 and (getattr(config, 'ruc', '') or '').strip().startswith('80'):
        # Los RUC 80… son de personas jurídicas (el mismo criterio que usa el
        # receptor). "Física" es el valor por defecto de la API y el que quedó
        # copiado acá; SIFEN lo contrasta con el padrón.
        faltan.append('tipo de contribuyente: un RUC que empieza con 80 es persona jurídica')
    if not re.fullmatch(r'\d{1,10}', actividad) or not actividad_desc:
        faltan.append('actividad económica (código y descripción)')
    if not direccion:
        faltan.append('dirección')
    if departamento is None or ciudad is None:
        faltan.append('departamento, distrito y ciudad')
    if not TELEFONO_MIN <= len(telefono) <= TELEFONO_MAX:
        faltan.append(f'teléfono ({TELEFONO_MIN} a {TELEFONO_MAX} caracteres)')
    if not email_valido(email):
        faltan.append('email válido')
    if faltan:
        return None, ('Completá en "Datos del emisor" y guardá antes de subir: '
                      + ', '.join(faltan) + '.')

    cuerpo = {
        'legal_name': razon_social[:255],
        'taxpayer_type': tipo,
        'address': direccion[:255],
        'house_number': _entero(config.numero_casa) or 0,
        'department_code': departamento,
        'department_name': (config.departamento_desc or '').strip()[:100],
        'city_code': ciudad,
        'city_name': (config.ciudad_desc or '').strip()[:100],
        'district_code': _entero(config.distrito_codigo),
        'district_name': (config.distrito_desc or '').strip()[:100],
        'phone': telefono,
        'email': email,
        'economic_activities': [{'code': actividad, 'description': actividad_desc[:255]}],
    }
    # Desde la API 1.7.4 el régimen viaja al XML como cTipReg. Es opcional: sin
    # dato acá no se manda, así no borra uno que cargaron allá.
    regimen = _entero(getattr(config, 'tipo_regimen', None))
    if regimen is not None:
        cuerpo['regime_type'] = regimen
    return cuerpo, None


def cargar_datos_fiscales(config):
    """Sube a la API el emisor guardado acá. (resumen, error)."""
    cuerpo, error = armar_datos_fiscales(config)
    if error:
        return None, error
    resumen, error = actualizar_perfil_remoto(config, cuerpo)
    if error:
        return None, f'La API no aceptó los datos del emisor. {error}'
    return f'Datos del emisor cargados en la API. {resumen}', None


__all__ = [
    'TIPOS_CONTRIBUYENTE',
    'actualizar_perfil_remoto',
    'armar_datos_fiscales',
    'cargar_datos_fiscales',
]
