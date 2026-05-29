"""Configuracion general de usuarios y marca del sistema."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from app.routes.usuarios import usuarios_bp
from app.services.ia_backoffice.security import puede_gestionar_asistente_ia
from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from app.services.usuarios_branding import guardar_logo_empresa
from app.utils.public_url import CLAVE_URL_PUBLICA_SISTEMA, DESC_URL_PUBLICA_SISTEMA


CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS = 'pos_ocultar_selector_vendedor_cajero'
DESC_OCULTAR_SELECTOR_VENDEDOR_POS = 'Muestra selector de vendedor/cajero en POS (desactivado: usa usuario actual)'
CLAVE_CAJA_FLUJO_ENVIADO = 'caja_flujo_enviado_desde_vendedor'
DESC_CAJA_FLUJO_ENVIADO = 'Habilita flujo vendedor -> caja para cobro final'
CLAVE_CAJA_ALERTA_PENDIENTES = 'caja_alerta_pendientes_activa'
DESC_CAJA_ALERTA_PENDIENTES = 'Muestra alerta visual de pendientes de cobro para cajero'
CLAVE_CAJA_EXIGIR_CAJERO = 'caja_exigir_cajero_para_cobro'
DESC_CAJA_EXIGIR_CAJERO = 'Bloquea cobro directo cuando el flujo de caja esta activo'
FORM_MODO_COBRO_EXCLUSIVO_CAJERO = 'modo_cobro_exclusivo_cajero'
CLAVE_NOMBRE_EMPRESA_UI = 'nombre_empresa_ui'
DESC_NOMBRE_EMPRESA_UI = 'Nombre visible de la empresa en el encabezado'
CLAVE_LOGO_EMPRESA_UI = 'logo_empresa_ui_path'
DESC_LOGO_EMPRESA_UI = 'Ruta del logo de la empresa para el encabezado'
CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO = 'reparacion_whatsapp_mensaje_link'
DESC_MENSAJE_WHATSAPP_SEGUIMIENTO = 'Plantilla de mensaje WhatsApp para compartir link de seguimiento de reparacion'
MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT = 'Hola! Este es su link de {empresa} para ver el estado de reparacion de su equipo:\n\n{link}'


def _ocultar_selector_vendedor_pos():
    mostrar_selector = Configuracion.obtener_bool(CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS, default=False)
    return not mostrar_selector


def _modo_cobro_exclusivo_cajero_activo():
    return (
        Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
        and Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
    )


@usuarios_bp.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta accion esta deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        _guardar_configuracion_general()
        flash('Configuracion actualizada correctamente.', 'success')
        return redirect(url_for('usuarios.configuracion'))

    return render_template(
        'usuarios/configuracion.html',
        active_tab='configuracion',
        mostrar_selector_vendedor_pos=(not _ocultar_selector_vendedor_pos()),
        modo_cobro_exclusivo_cajero=_modo_cobro_exclusivo_cajero_activo(),
        caja_flujo_enviado_activo=Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False),
        caja_alerta_pendientes_activa=Configuracion.obtener_bool(CLAVE_CAJA_ALERTA_PENDIENTES, default=False),
        caja_exigir_cajero_para_cobro=Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False),
        nombre_empresa_ui=(Configuracion.obtener(CLAVE_NOMBRE_EMPRESA_UI, '') or '').strip(),
        url_publica_sistema=(Configuracion.obtener(CLAVE_URL_PUBLICA_SISTEMA, '') or '').strip(),
        mensaje_whatsapp_seguimiento=_mensaje_whatsapp_seguimiento(),
        logo_empresa_ui_path=(Configuracion.obtener(CLAVE_LOGO_EMPRESA_UI, '') or '').strip(),
        logo_tamano_recomendado='280 x 80 px',
        logo_tamano_maximo_mb=2,
        ia_backoffice_config=obtener_configuracion_asistente(),
        ia_backoffice_puede_gestionar=puede_gestionar_asistente_ia(current_user),
    )


def _guardar_configuracion_general():
    mostrar_selector = _leer_toggle('mostrar_selector_vendedor_pos', default=False)
    modo_cobro_exclusivo_cajero = _leer_modo_cobro_exclusivo()
    caja_alerta_pendientes = _leer_alerta_pendientes()
    logo_empresa_archivo = request.files.get('logo_empresa_ui')

    Configuracion.establecer_bool(CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS, mostrar_selector, DESC_OCULTAR_SELECTOR_VENDEDOR_POS)
    Configuracion.establecer_bool(CLAVE_CAJA_FLUJO_ENVIADO, modo_cobro_exclusivo_cajero, DESC_CAJA_FLUJO_ENVIADO)
    Configuracion.establecer_bool(CLAVE_CAJA_ALERTA_PENDIENTES, caja_alerta_pendientes, DESC_CAJA_ALERTA_PENDIENTES)
    Configuracion.establecer_bool(CLAVE_CAJA_EXIGIR_CAJERO, modo_cobro_exclusivo_cajero, DESC_CAJA_EXIGIR_CAJERO)
    Configuracion.establecer(CLAVE_NOMBRE_EMPRESA_UI, (request.form.get('nombre_empresa_ui') or '').strip(), DESC_NOMBRE_EMPRESA_UI)
    Configuracion.establecer(CLAVE_URL_PUBLICA_SISTEMA, (request.form.get('url_publica_sistema') or '').strip().rstrip('/'), DESC_URL_PUBLICA_SISTEMA)
    Configuracion.establecer(CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO, (request.form.get('mensaje_whatsapp_seguimiento') or '').strip(), DESC_MENSAJE_WHATSAPP_SEGUIMIENTO)

    ruta_logo_guardada, error_logo = guardar_logo_empresa(
        logo_empresa_archivo,
        ruta_anterior=(Configuracion.obtener(CLAVE_LOGO_EMPRESA_UI, '') or '').strip(),
    )
    if error_logo:
        flash(error_logo, 'warning')
    elif ruta_logo_guardada:
        Configuracion.establecer(CLAVE_LOGO_EMPRESA_UI, ruta_logo_guardada, DESC_LOGO_EMPRESA_UI)


def _leer_toggle(nombre, default=False):
    valores = request.form.getlist(nombre)
    raw = valores[-1] if valores else None
    return Configuracion.parse_bool(raw, default=default)


def _leer_modo_cobro_exclusivo():
    valores = request.form.getlist(FORM_MODO_COBRO_EXCLUSIVO_CAJERO)
    if valores:
        return Configuracion.parse_bool(valores[-1], default=False)
    return _modo_cobro_exclusivo_cajero_activo()


def _leer_alerta_pendientes():
    valores = request.form.getlist('caja_alerta_pendientes_activa')
    if valores:
        return Configuracion.parse_bool(valores[-1], default=False)
    return Configuracion.obtener_bool(CLAVE_CAJA_ALERTA_PENDIENTES, default=False)


def _mensaje_whatsapp_seguimiento():
    return (
        (Configuracion.obtener(CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO, MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT) or '').strip()
        or MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT
    )
