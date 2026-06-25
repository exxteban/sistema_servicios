"""Traduce la configuración del emisor al formato 'params' que espera TIPS xmlgen.

Estructura de referencia: https://github.com/TIPS-SA/facturacionelectronicapy-xmlgen
Esta capa es pura (sin DB ni red) para poder validarla de forma aislada.
"""

VERSION_FORMATO = 150


def _texto(valor):
    valor = (valor or '').strip()
    return valor or None


def _entero(valor):
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def _ruc_con_dv(config):
    ruc = (config.ruc or '').strip()
    dv = (config.dv_ruc or '').strip()
    if ruc and dv:
        return f'{ruc}-{dv}'
    return ruc or None


def construir_establecimiento(config):
    return {
        'codigo': (config.establecimiento or '001').strip() or '001',
        'direccion': _texto(config.direccion),
        'numeroCasa': _texto(config.numero_casa) or '0',
        'departamento': _entero(config.departamento_codigo),
        'departamentoDescripcion': _texto(config.departamento_desc),
        'distrito': _entero(config.distrito_codigo),
        'distritoDescripcion': _texto(config.distrito_desc),
        'ciudad': _entero(config.ciudad_codigo),
        'ciudadDescripcion': _texto(config.ciudad_desc),
        'telefono': _texto(config.telefono),
        'email': _texto(config.email),
        'denominacion': _texto(config.nombre_fantasia) or 'Casa Matriz',
    }


def construir_params_emisor(config):
    return {
        'version': VERSION_FORMATO,
        'ruc': _ruc_con_dv(config),
        'razonSocial': _texto(config.razon_social),
        'nombreFantasia': _texto(config.nombre_fantasia),
        'actividadesEconomicas': [
            {
                'codigo': _texto(config.actividad_economica_codigo),
                'descripcion': _texto(config.actividad_economica_desc),
            }
        ],
        'timbradoNumero': _texto(config.timbrado_numero),
        'timbradoFecha': config.timbrado_fecha_inicio.isoformat() if config.timbrado_fecha_inicio else None,
        'tipoContribuyente': _entero(config.tipo_contribuyente),
        'tipoRegimen': _entero(config.tipo_regimen),
        'establecimientos': [construir_establecimiento(config)],
    }


__all__ = ['construir_params_emisor', 'construir_establecimiento', 'VERSION_FORMATO']
