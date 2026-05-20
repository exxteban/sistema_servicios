from datetime import date


def periodo_actual() -> str:
    return date.today().strftime('%Y-%m')


def normalizar_periodo(raw_value: str | None) -> str:
    valor = (raw_value or '').strip()
    if len(valor) == 7 and valor[4] == '-':
        anio = valor[:4]
        mes = valor[5:]
        if anio.isdigit() and mes.isdigit():
            mes_int = int(mes)
            if 1 <= mes_int <= 12:
                return f'{int(anio):04d}-{mes_int:02d}'
    return periodo_actual()


def normalizar_tab(raw_value: str | None) -> str:
    valor = (raw_value or '').strip().lower()
    if valor in {'resumen', 'aguinaldo', 'vacaciones', 'asistencia'}:
        return valor
    return 'resumen'


def normalizar_busqueda_empleado(raw_value: str | None) -> str:
    return (raw_value or '').strip()


def resolver_filtros_estado(
    raw_estado: str | None,
    raw_mostrar_activos,
    raw_mostrar_inactivos,
) -> tuple[bool, bool]:
    def _parse_flag(raw_value) -> bool | None:
        if raw_value is None:
            return None
        valor = str(raw_value).strip().lower()
        if valor in {'1', 'true', 'on', 'yes'}:
            return True
        if valor in {'0', 'false', 'off', 'no', ''}:
            return False
        return bool(raw_value)

    mostrar_activos = _parse_flag(raw_mostrar_activos)
    mostrar_inactivos = _parse_flag(raw_mostrar_inactivos)
    estado = (raw_estado or '').strip().lower()
    if mostrar_activos is None and mostrar_inactivos is None:
        if estado == 'todos':
            return True, True
        if estado == 'inactivos':
            return False, True
        return True, False
    return bool(mostrar_activos), bool(mostrar_inactivos)
