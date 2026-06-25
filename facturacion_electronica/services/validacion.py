"""Chequeo de completitud de la configuración del emisor.

Sólo valida lo que es responsabilidad del usuario y se puede ver antes de
enviar. Las validaciones fiscales/estructurales (códigos geográficos, reglas
del XML) las resuelve TIPS/SIFEN al momento del envío.
"""

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
    """Devuelve la lista de datos que faltan para poder facturar."""
    return [etiqueta for cumple, etiqueta in REQUISITOS if not cumple(config)]


__all__ = ['validar_configuracion']
