"""
Helpers para construir mensajes interactivos de WhatsApp (botones y listas).
"""


def botones_reparaciones(reparaciones: list[dict]) -> list[dict]:
    """
    Genera botones para seleccionar reparacion (max 3).
    Si hay mas de 3, usar lista en su lugar.
    """
    botones = []
    for i, rep in enumerate(reparaciones[:3]):
        equipo = rep.get('equipo', 'Equipo')
        # Titulo max 20 chars
        titulo = equipo[:17] + '...' if len(equipo) > 20 else equipo
        botones.append({
            'id': f'rep_{rep["id_reparacion"]}',
            'title': titulo
        })
    return botones


def lista_reparaciones(reparaciones: list[dict]) -> list[dict]:
    """
    Genera secciones de lista para seleccionar reparacion.
    Usar cuando hay mas de 3 reparaciones.
    """
    rows = []
    for rep in reparaciones[:10]:  # Max 10 items en lista
        equipo = rep.get('equipo', 'Equipo')
        estado = rep.get('estado_texto', rep.get('estado', ''))
        rows.append({
            'id': f'rep_{rep["id_reparacion"]}',
            'title': equipo[:24],
            'description': estado[:72]
        })

    return [{
        'title': 'Tus equipos',
        'rows': rows
    }]


def botones_si_no(prefijo: str = 'confirm') -> list[dict]:
    """Botones Si/No genericos."""
    return [
        {'id': f'{prefijo}_si', 'title': 'Si'},
        {'id': f'{prefijo}_no', 'title': 'No'}
    ]


def botones_menu_principal() -> list[dict]:
    """Botones del menu principal."""
    return [
        {'id': 'menu_estado', 'title': 'Estado reparacion'},
        {'id': 'menu_info', 'title': 'Info del local'},
        {'id': 'menu_asesor', 'title': 'Hablar con asesor'}
    ]
