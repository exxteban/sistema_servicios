"""
Templates de mensajes WhatsApp.
Mensajes predefinidos para situaciones comunes.
"""


def mensaje_bienvenida(nombre_local: str = 'el local') -> str:
    return (
        f'Hola! Soy el asistente virtual de {nombre_local} 🔧\n\n'
        'Puedo ayudarte con:\n'
        '📱 Estado de tu reparacion\n'
        '📅 Horarios y ubicacion\n'
        '💰 Consultas sobre costos y garantia\n'
        '❓ Preguntas frecuentes\n\n'
        'Si en algun momento preferis hablar con una persona, '
        'solo decime "quiero hablar con un asesor" y te comunico.\n\n'
        'En que te puedo ayudar?'
    )


def mensaje_lista_reparaciones(reparaciones: list[dict]) -> str:
    """Genera texto con lista numerada de reparaciones."""
    if not reparaciones:
        return 'No tenes reparaciones activas en este momento.'

    if len(reparaciones) == 1:
        r = reparaciones[0]
        return f'Tu {r["equipo"]} esta: {r["estado_texto"]}'

    lineas = ['Tenes estos equipos con nosotros:\n']
    for i, r in enumerate(reparaciones, 1):
        lineas.append(f'{i}. {r["equipo"]} - {r["estado_texto"]}')
    lineas.append('\nDe cual queres saber? (Responde con el numero)')
    return '\n'.join(lineas)


def mensaje_estado_reparacion(datos: dict, verificado: bool = False) -> str:
    """Genera texto con el estado detallado de una reparacion."""
    lineas = [
        f'📱 {datos.get("equipo", "Equipo")}',
        f'Estado: {datos.get("estado_texto", datos.get("estado", ""))}',
    ]

    if datos.get('fecha_ingreso'):
        lineas.append(f'Ingreso: {datos["fecha_ingreso"]}')

    if datos.get('fecha_estimada'):
        lineas.append(f'Fecha estimada: {datos["fecha_estimada"]}')

    if datos.get('nota_del_local'):
        lineas.append(f'\n📝 {datos["nota_del_local"]}')

    if verificado:
        if datos.get('diagnostico'):
            lineas.append(f'\n🔍 Diagnostico: {datos["diagnostico"]}')
        if datos.get('solucion'):
            lineas.append(f'🔧 Solucion: {datos["solucion"]}')
        if datos.get('costo_final') is not None and datos['costo_final'] > 0:
            lineas.append(f'\n💰 Costo: ${datos["costo_final"]:,.0f}')
            if datos.get('abono', 0) > 0:
                lineas.append(f'Abono: ${datos["abono"]:,.0f}')
            if datos.get('saldo_pendiente', 0) > 0:
                lineas.append(f'Saldo: ${datos["saldo_pendiente"]:,.0f}')

    return '\n'.join(lineas)


def mensaje_sin_asesores(horarios: str = 'Lun-Sáb 8:00-18:00') -> str:
    return (
        'En este momento no hay asesores disponibles.\n'
        f'Nuestro horario de atencion es: {horarios}\n'
        'Dejanos tu consulta y te respondemos apenas podamos. 📝'
    )


def mensaje_derivacion() -> str:
    return 'Te voy a comunicar con un asesor. Espera un momento... ⏳'


def mensaje_asesor_asignado(nombre: str) -> str:
    return f'Te atiende {nombre}. Ya puede escribirte. 👋'


def mensaje_volver_bot() -> str:
    return 'El asesor cerro la conversacion. Si necesitas algo mas, estoy para ayudarte! 🤖'


def mensaje_codigo_requerido() -> str:
    return (
        'Para ver esa informacion necesito verificar tu identidad.\n'
        'Por favor ingresa el codigo de 6 digitos que te dieron al dejar el equipo.'
    )
