from app import db
from app.models import Permiso, Rol, Usuario
from app.models.usuario import usuario_permisos_adicionales


def nivel_jerarquia(usuario):
    return usuario.rol.nivel_jerarquia if usuario and usuario.rol else 0


def puede_gestionar_usuario(usuario_actual, usuario_objetivo):
    if not usuario_actual or not usuario_objetivo:
        return False
    if usuario_objetivo.id_usuario == usuario_actual.id_usuario:
        return True
    return nivel_jerarquia(usuario_actual) > nivel_jerarquia(usuario_objetivo)


def roles_asignables(usuario_actual):
    nivel_actual = nivel_jerarquia(usuario_actual)
    return Rol.query.filter(
        Rol.activo == True,
        Rol.nivel_jerarquia < nivel_actual,
    ).order_by(Rol.nivel_jerarquia.desc()).all()


def agrupar_permisos(permisos):
    agrupados = {}
    for permiso in permisos:
        modulo = permiso.modulo or 'otros'
        agrupados.setdefault(modulo, []).append(permiso)
    return agrupados


def map_permisos_por_rol(roles):
    resultado = {}
    for rol in roles:
        permisos = rol.permisos.filter_by(activo=True).order_by(
            Permiso.modulo.asc(),
            Permiso.nombre.asc(),
        ).all()
        resultado[rol.id_rol] = [
            {'codigo': permiso.codigo, 'nombre': permiso.nombre}
            for permiso in permisos
        ]
    return resultado


def set_permisos_adicionales(id_usuario, ids_permiso, concedido_por):
    db.session.execute(
        usuario_permisos_adicionales.delete().where(
            usuario_permisos_adicionales.c.id_usuario == id_usuario
        )
    )
    ids_permiso = sorted({int(x) for x in ids_permiso if str(x).isdigit()})
    if not ids_permiso:
        return

    permisos_validos = Permiso.query.filter(
        Permiso.activo == True,
        Permiso.id_permiso.in_(ids_permiso),
    ).all()
    for permiso in permisos_validos:
        db.session.execute(
            usuario_permisos_adicionales.insert().values(
                id_usuario=id_usuario,
                id_permiso=permiso.id_permiso,
                concedido_por=concedido_por,
            )
        )


def tiene_otro_admin_activo(id_usuario_excluido):
    usuarios_activos = Usuario.query.filter(
        Usuario.activo == True,
        Usuario.id_usuario != id_usuario_excluido,
    ).all()
    return any(usuario.es_admin() for usuario in usuarios_activos)
