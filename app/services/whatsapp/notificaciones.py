"""
Notificaciones automaticas por WhatsApp.
Se disparan cuando cambia el estado de una reparacion.
"""
import os
import logging

from app import db
from app.models.reparacion import Reparacion
from app.models.cliente import Cliente
from app.models.whatsapp import WhatsAppConversacion, WhatsAppMensaje, WhatsAppConfiguracion
from app.services.whatsapp import client as wa_client
from app.utils.phone_utils import normalizar_telefono

logger = logging.getLogger(__name__)

# Mapeo estado -> mensaje de notificacion
NOTIFICACION_ESTADOS = {
    'diagnostico': (
        'Tu {equipo} ya esta en diagnostico 🔍\n'
        'Te avisamos cuando tengamos novedades.'
    ),
    'espera_presupuesto': (
        'Ya tenemos el presupuesto de tu {equipo} 💰\n'
        'Contactanos para mas detalles o responde a este mensaje.'
    ),
    'en_proceso': (
        'Tu {equipo} ya esta en reparacion 🔧\n'
        'Te avisamos cuando este listo.'
    ),
    'listo': (
        '¡Tu {equipo} esta listo para retirar! ✅\n'
        'Podes pasar a buscarlo en nuestro horario de atencion.\n'
        'Recorda traer tu cedula y el comprobante de ingreso.'
    ),
    'no_se_pudo': (
        'Lamentablemente no pudimos reparar tu {equipo} 😔\n'
        'Contactanos para coordinar el retiro y hablar sobre las opciones.'
    ),
}


def _notificacion_habilitada(estado: str) -> bool:
    """Verifica si la notificacion para este estado esta habilitada."""
    mapeo_env = {
        'listo': 'WHATSAPP_NOTIFICAR_LISTO',
        'espera_cliente': 'WHATSAPP_NOTIFICAR_ESPERA_CLIENTE',
        'no_se_pudo': 'WHATSAPP_NOTIFICAR_NO_SE_PUDO',
    }

    env_var = mapeo_env.get(estado)
    if env_var:
        return os.environ.get(env_var, '1').strip().lower() in ('1', 'true', 'yes')

    # Por defecto, notificar para estados con template definido
    return estado in NOTIFICACION_ESTADOS


def notificar_cambio_estado(id_reparacion: int, estado_nuevo: str, estado_anterior: str = None):
    """
    Envia notificacion al cliente cuando cambia el estado de su reparacion.
    Se llama desde la ruta de reparaciones cuando se actualiza el estado.
    """
    if not os.environ.get('WHATSAPP_ENABLED', '0').strip().lower() in ('1', 'true', 'yes'):
        return

    if not _notificacion_habilitada(estado_nuevo):
        return

    template = NOTIFICACION_ESTADOS.get(estado_nuevo)
    if not template:
        return

    rep = Reparacion.query.get(id_reparacion)
    if not rep or not rep.cliente:
        logger.warning(f"Reparacion {id_reparacion} no encontrada o sin cliente para notificar")
        return

    telefono = rep.cliente.telefono
    if not telefono:
        logger.info(f"Cliente {rep.cliente.id_cliente} sin telefono, no se notifica")
        return

    tel_norm = normalizar_telefono(telefono)
    if not tel_norm:
        logger.warning(f"Telefono invalido para notificar: {telefono}")
        return

    equipo = f'{rep.tipo_equipo} {rep.marca_modelo}'
    texto = template.format(equipo=equipo)

    # Agregar nota del local si existe
    if rep.nota_cliente:
        texto += f'\n\n📝 Nota: {rep.nota_cliente}'

    tel_envio = tel_norm.lstrip('+')

    try:
        resultado = wa_client.enviar_texto(tel_envio, texto)
        if resultado:
            # Registrar en historial si hay conversacion activa
            conv = WhatsAppConversacion.query.filter_by(
                telefono=tel_norm, activa=True
            ).first()
            if conv:
                msg = WhatsAppMensaje(
                    id_conversacion=conv.id,
                    direccion='saliente',
                    remitente='bot',
                    tipo_mensaje='text',
                    contenido=texto,
                )
                db.session.add(msg)
                db.session.commit()

            logger.info(f"Notificacion enviada: rep={id_reparacion} estado={estado_nuevo} tel={tel_norm}")
        else:
            logger.error(f"Fallo envio notificacion: rep={id_reparacion} tel={tel_norm}")
    except Exception as e:
        logger.error(f"Error enviando notificacion: {e}", exc_info=True)
