from datetime import datetime

from sqlalchemy import func

from app.models import Reparacion, Rol, Usuario


ROLES_TECNICO = {'tecnico', 'técnico'}
ROLES_ASIGNABLES_REPARACION = ROLES_TECNICO | {'administrador', 'admin'}
ESTADOS_TOMA_TECNICA = {
    'diagnostico',
    'espera_presupuesto',
    'espera_repuesto',
    'espera_cliente',
    'en_proceso',
    'listo',
    'no_se_pudo',
    'entregado',
}
ESTADOS_FINALIZACION_TECNICA = {'listo', 'no_se_pudo', 'entregado'}


def usuarios_tecnicos_activos():
    return _usuarios_activos_por_roles(ROLES_TECNICO)


def usuarios_asignables_reparacion_activos():
    return _usuarios_activos_por_roles(ROLES_ASIGNABLES_REPARACION)


def _usuarios_activos_por_roles(roles):
    return (
        Usuario.query
        .join(Rol, Usuario.id_rol == Rol.id_rol)
        .filter(
            Usuario.activo.is_(True),
            Rol.activo.is_(True),
            func.lower(Rol.nombre).in_(roles),
        )
        .order_by(Usuario.nombre_completo.asc())
        .all()
    )


def usuario_es_tecnico(usuario):
    rol = getattr(getattr(usuario, 'rol', None), 'nombre', '') or ''
    return rol.strip().lower() in ROLES_TECNICO


def aplicar_hitos_tecnicos(reparacion, estado_anterior=None, nuevo_estado=None, usuario=None):
    estado_prev = (estado_anterior or reparacion.estado or '').strip().lower()
    estado_next = (nuevo_estado or reparacion.estado or '').strip().lower()
    ahora = datetime.utcnow()

    if usuario_es_tecnico(usuario) and estado_next in ESTADOS_TOMA_TECNICA:
        if not reparacion.id_usuario_tecnico:
            reparacion.id_usuario_tecnico = usuario.id_usuario
        if int(reparacion.id_usuario_tecnico or 0) == int(usuario.id_usuario or 0):
            if not reparacion.fecha_toma_tecnico:
                reparacion.fecha_toma_tecnico = ahora

    if estado_next in ESTADOS_FINALIZACION_TECNICA:
        if not reparacion.fecha_listo_tecnico:
            reparacion.fecha_listo_tecnico = ahora
        if not reparacion.fecha_toma_tecnico and reparacion.id_usuario_tecnico:
            reparacion.fecha_toma_tecnico = ahora
    elif estado_prev in ESTADOS_FINALIZACION_TECNICA and estado_next not in ESTADOS_FINALIZACION_TECNICA:
        reparacion.fecha_listo_tecnico = None


def tomar_reparacion(reparacion, usuario):
    if not usuario_es_tecnico(usuario):
        raise ValueError('Solo un técnico puede tomar la reparación.')
    if reparacion.id_usuario_tecnico and int(reparacion.id_usuario_tecnico) != int(usuario.id_usuario):
        raise ValueError('La reparación ya está tomada por otro técnico.')

    ahora = datetime.utcnow()
    reparacion.id_usuario_tecnico = usuario.id_usuario
    if not reparacion.fecha_toma_tecnico:
        reparacion.fecha_toma_tecnico = ahora

    if (reparacion.estado or '').strip().lower() == 'pendiente':
        reparacion.estado = 'diagnostico'


def referencia_fecha_tecnica(reparacion):
    return reparacion.fecha_toma_tecnico or reparacion.fecha_ingreso
