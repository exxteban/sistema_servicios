"""Chequeo de completitud de la configuración del emisor.

Sólo valida lo que es responsabilidad del usuario y se puede ver antes de
enviar. Las validaciones fiscales/estructurales (códigos geográficos, reglas
del XML) las resuelve TIPS/SIFEN al momento del envío.
"""
import re

REQUISITOS = (
    (lambda c: bool(c.ruc and c.dv_ruc), 'RUC y dígito verificador'),
    (lambda c: bool(c.razon_social), 'Razón social'),
    (lambda c: bool(c.timbrado_numero), 'Número de timbrado'),
    (lambda c: bool(c.timbrado_fecha_inicio), 'Fecha de inicio del timbrado'),
    (lambda c: bool(c.establecimiento), 'Establecimiento'),
    (lambda c: bool(c.punto_expedicion), 'Punto de expedición'),
    (lambda c: bool(c.actividad_economica_codigo), 'Código de actividad económica'),
    (lambda c: c.certificado_cargado, 'Certificado digital (.p12)'),
    (lambda c: bool(c.cert_password), 'Contraseña del certificado'),
    (lambda c: bool(c.csc), 'CSC (Código de Seguridad del Contribuyente)'),
    (lambda c: bool(c.csc_id), 'ID del CSC'),
)


def validar_configuracion(config):
    """Datos que faltan para poder facturar, **sin pegar a la red**.

    Es la compuerta: la miran el render del POS y cada pasada del job de
    envío. Tiene que poder contestar con el proveedor caído, porque si no una
    caída pasajera del otro lado apaga las dos cosas en silencio.
    """
    from facturacion_electronica.services.proveedores import obtener_proveedor
    return obtener_proveedor(config).faltantes_configuracion(config)


def validar_readiness(config):
    """Lo anterior más lo que hay que preguntarle al proveedor (certificado,
    CSC). Puede tardar o fallar por red: sólo para la pantalla de
    configuración y para el momento de emitir."""
    from facturacion_electronica.services.proveedores import obtener_proveedor
    return obtener_proveedor(config).faltantes_readiness(config)


# Sufijos societarios en la razón social que delatan una persona jurídica.
_SUFIJOS_JURIDICA = re.compile(
    r'\b(S\.?A\.?|S\.?R\.?L\.?|S\.?A\.?E\.?C\.?A\.?|E\.?A\.?S\.?|LTDA\.?'
    r'|COOPERATIVA|SOCIEDAD|ASOCIACION|ASOCIACIÓN|FUNDACION|FUNDACIÓN|CONSORCIO)\b',
    re.IGNORECASE,
)


def validar_cliente(cliente):
    """Devuelve un error si el cliente parece empresa y su RUC no tiene DV; sino None.

    Sin el guion y el dígito verificador, el DE sale con el cliente como cédula
    o innominado y la empresa receptora pierde su crédito de IVA. No se calcula
    el DV automáticamente: se avisa para corregir la ficha del cliente y volver
    a emitir (el envío automático reintenta solo una vez corregido).
    """
    if cliente is None or cliente.id_cliente == 1:
        return None
    ruc_ci = (cliente.ruc_ci or '').strip()
    if not ruc_ci or '-' in ruc_ci:
        return None
    digitos = re.sub(r'\D', '', ruc_ci)
    if not digitos or set(digitos) == {'0'}:
        return None
    # Los RUC de personas jurídicas empiezan con 80 y tienen 8+ dígitos (las
    # cédulas viejas del rango 80xxxx son más cortas y no deben alertar).
    parece_ruc_empresa = digitos.startswith('80') and len(digitos) >= 8
    parece_juridica = bool(_SUFIJOS_JURIDICA.search(cliente.nombre or ''))
    if parece_ruc_empresa or parece_juridica:
        return (
            f'El cliente "{(cliente.nombre or "").strip()}" parece ser una empresa pero su '
            f'RUC ({ruc_ci}) no tiene dígito verificador. Cargalo con el formato RUC-DV '
            '(ej. 80012345-0) en la ficha del cliente y volvé a emitir; sin eso la factura '
            'no saldría a su nombre y perdería el crédito de IVA.'
        )
    return None


# Tope para facturar a un receptor sin identificar: NT 024 de la DNIT (regla
# D208c, rechazo `1321`), vigente desde el 01/01/2025. La NT 021 decía
# 35.000.000 para la misma regla; la 024 la reemplazó. xmlgen no lo valida, así
# que sin esta guarda el documento se firmaba, se transmitía y SIFEN lo
# rechazaba con el número ya consumido. Dato relevado en la API del compañero
# (fe_django, `apps/sifen/domain/validation.py`), que sí lo controla.
TOPE_INNOMINADO = 7_000_000


def validar_monto_innominado(cliente, total):
    """Error si la venta supera el tope para un receptor sin identificar.

    Se mira el total **redondeado** (dTotGralOpe), que es el que compara SIFEN.
    Se frena antes de reservar número: cargar la cédula en la ficha no tiene
    que costar un correlativo.
    """
    from facturacion_electronica.services.data_builder import (
        receptor_innominado,
        redondeo_sedeco,
    )

    if not receptor_innominado(cliente):
        return None
    total_documento, _redondeo = redondeo_sedeco(total)
    if total_documento < TOPE_INNOMINADO:
        return None
    problema = (
        f'La venta es de {total_documento:,.0f} Gs y el cliente no está identificado: '
        f'SIFEN no acepta facturas sin RUC ni cédula desde {TOPE_INNOMINADO:,.0f} Gs (NT 024).'
    ).replace(',', '.')
    # La salida depende de quién es el cliente. A un cliente real se le completa
    # la ficha y el envío automático reintenta solo. Pero una venta hecha a
    # Consumidor Final no se puede reasignar a otro cliente, así que "cargale la
    # cédula" sería una instrucción imposible de cumplir.
    if cliente is None or getattr(cliente, 'id_cliente', None) == 1:
        return (f'{problema} La venta quedó a nombre de Consumidor Final y no se puede '
                'cambiar de cliente: para facturarla hay que anular la venta y registrarla '
                'de nuevo con el cliente identificado.')
    return (f'{problema} Cargale el RUC o la cédula en la ficha del cliente; el envío '
            'automático la reintenta sola.')


# tEmail del XSD de SIFEN: el mismo patrón que valida la API.
_EMAIL_SIFEN = re.compile(
    r'^([0-9a-zA-Z]([0-9a-zA-Z\.\-_])*@([0-9a-zA-Z][0-9a-zA-Z\-_]*\.)+[a-zA-Z]{2,9})$'
)


def email_valido(texto):
    return bool(_EMAIL_SIFEN.match((texto or '').strip()))


def digito_verificador_ruc(raiz):
    """DV del RUC por módulo 11 con factores cíclicos 2..11 (algoritmo de la SET).

    Es el mismo cálculo que hace la API externa (`Mod11.digit` en fe_django)
    para validar `receiver.dv`.
    """
    total = 0
    factor = 2
    for caracter in reversed(raiz):
        total += int(caracter) * factor
        factor = 2 if factor == 11 else factor + 1
    resto = total % 11
    return 11 - resto if resto > 1 else 0


def validar_receptor_api(cliente):
    """Error si el receptor no pasa el borde de la API externa; sino None.

    Desde su 1.3.0/1.4.0 la API rechaza con 400 un receptor identificado cuyo
    nombre tiene menos de 4 caracteres, y un contribuyente cuyo DV no es el
    del RUC. Antes pasaban y los rechazaba SIFEN. Se chequea antes de reservar
    número, con el mismo receptor que se va a mandar (`construir_receptor`),
    para que la pantalla diga qué corregir en la ficha y no muestre el 400.

    Sólo para el proveedor API: el motor propio no se toca con esto.
    """
    from facturacion_electronica.services.proveedores.api_payload import (
        DOCUMENTO_TIPO_INNOMINADO,
        NATURALEZA_CONTRIBUYENTE,
        NOMBRE_RECEPTOR_MIN,
        construir_receptor,
    )

    if cliente is None:
        return None
    receptor = construir_receptor(cliente)
    nombre = receptor.get('name') or ''
    ficha = 'Corregilo en la ficha del cliente y volvé a emitir.'

    if receptor.get('id_type') != DOCUMENTO_TIPO_INNOMINADO and len(nombre) < NOMBRE_RECEPTOR_MIN:
        return (f'El nombre del cliente ("{nombre}") tiene menos de {NOMBRE_RECEPTOR_MIN} '
                f'caracteres y SIFEN no lo acepta en la factura. {ficha}')

    if receptor.get('nature') == NATURALEZA_CONTRIBUYENTE:
        ruc = receptor.get('ruc') or ''
        ruc_ci = (getattr(cliente, 'ruc_ci', '') or '').strip()
        dv_cargado = re.sub(r'\D', '', ruc_ci.partition('-')[2])
        if not ruc.isdigit():
            return f'El RUC del cliente ({ruc_ci}) no es válido. {ficha}'
        esperado = digito_verificador_ruc(ruc)
        if not dv_cargado or int(dv_cargado) != esperado:
            return (f'El dígito verificador del RUC del cliente ({ruc_ci}) no corresponde: '
                    f'para el RUC {ruc} es {esperado}. {ficha}')
    return None


__all__ = [
    'validar_configuracion', 'validar_readiness', 'validar_cliente',
    'validar_monto_innominado', 'validar_receptor_api', 'digito_verificador_ruc', 'email_valido',
    'TOPE_INNOMINADO',
]
