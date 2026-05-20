from app.services.whatsapp.conversacion.intenciones import (
    _modo_consulta_tiempo,
    _normalizar_texto_intencion,
    _tiene_intencion_tiempo_reparacion,
)


def _respuesta_aclaratoria_intencion(contexto: dict) -> str:
    reps = (((contexto or {}).get('info_cliente') or {}).get('reparaciones_activas') or [])
    if reps:
        return (
            "No termine de entenderte del todo. Decime si queres consultar:\n"
            "1) El estado de tu reparacion en curso\n"
            "2) Un equipo/producto a la venta"
        )
    return (
        "Para ayudarte mejor, decime si tu consulta es por:\n"
        "1) Reparacion\n"
        "2) Producto/equipo a la venta\n"
        "3) Horarios/ubicacion"
    )


def _respuesta_estado_reparacion_desde_contexto(contexto: dict) -> str | None:
    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []
    if not reps:
        return None

    if len(reps) == 1:
        rep = reps[0]
        equipo = rep.get('equipo', 'tu equipo')
        estado = rep.get('estado_texto', 'En seguimiento')
        fecha_ingreso = rep.get('fecha_ingreso')
        if fecha_ingreso:
            return f"Dale! Tu {equipo} esta {estado}. Lo dejaste el {fecha_ingreso} 👍"
        return f"Dale! Tu {equipo} esta {estado} 👍"

    texto_resp = f"Veo que tenes {len(reps)} reparaciones en curso! 🔧\n\n"
    for i, rep in enumerate(reps, 1):
        texto_resp += f"{i}. *{rep.get('equipo', 'Equipo')}* - {rep.get('estado_texto', 'En seguimiento')}\n"
    texto_resp += "\nDe cual queres saber?"
    return texto_resp


def _texto_contiene_keyword_completa(texto: str, keyword: str) -> bool:
    texto_normalizado = f" {texto or ''} "
    keyword_normalizado = (keyword or '').strip()
    if not keyword_normalizado:
        return False
    return f" {keyword_normalizado} " in texto_normalizado


def _cliente_menciona_equipo_no_registrado(texto: str, contexto: dict) -> str | None:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return None

    tipos_equipo = {
        'tablet': ('tablet', 'tab'),
        'notebook': ('notebook', 'notbook', 'laptop', 'portatil'),
        'computadora': ('computadora', 'compu', 'pc', 'desktop'),
        'impresora': ('impresora',),
        'consola': ('consola', 'play', 'playstation', 'xbox', 'nintendo', 'switch'),
        'smartwatch': ('smartwatch', 'reloj',),
        'auricular': ('auricular', 'auriculares', 'audifono'),
        'parlante': ('parlante', 'speaker', 'bocina'),
    }

    tipo_mencionado = None
    tipo_label = None
    for label, keywords in tipos_equipo.items():
        for kw in keywords:
            if _texto_contiene_keyword_completa(t, kw):
                tipo_mencionado = kw
                tipo_label = label
                break
        if tipo_mencionado:
            break

    if not tipo_mencionado:
        return None

    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []
    if not reps:
        return None

    for rep in reps:
        equipo = _normalizar_texto_intencion(rep.get('equipo') or '')
        if _texto_contiene_keyword_completa(equipo, tipo_mencionado) or (
            tipo_label and _texto_contiene_keyword_completa(equipo, tipo_label)
        ):
            return None

    if len(reps) == 1:
        equipo_real = reps[0].get('equipo', 'tu equipo')
        return (
            f"No, no tengo ninguna {tipo_label} registrada a tu nombre. "
            f"Solo tengo anotado un *{equipo_real}*. "
            f"Puede ser que se haya ingresado con otro nombre o numero?"
        )

    lista = ', '.join(f"*{r.get('equipo', 'equipo')}*" for r in reps)
    return (
        f"No tengo ninguna {tipo_label} registrada a tu nombre. "
        f"Los equipos que tengo anotados son: {lista}. "
        f"Puede ser que se haya ingresado con otro nombre o numero?"
    )


def _generar_instruccion_tiempo_reparacion(contexto: dict, texto: str, es_followup: bool) -> str:
    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []

    if not reps or len(reps) != 1:
        return None

    rep = reps[0]
    modo_tiempo = _modo_consulta_tiempo(texto)
    fecha_estimada = (rep.get('fecha_estimada') or '').strip()
    hora_estimada = (rep.get('hora_estimada') or '').strip()
    equipo = rep.get('equipo', 'el equipo')

    instruccion = f"INSTRUCCION ESPECIAL: El cliente pregunta por el tiempo de entrega de su {equipo}. "

    if es_followup:
        instruccion += "Es un follow-up, responde breve y conversacional. "

    if modo_tiempo == 'hora':
        if hora_estimada:
            instruccion += f"La hora estimada es {hora_estimada}. "
        else:
            instruccion += "No hay hora estimada confirmada todavía. "
    elif modo_tiempo == 'fecha':
        if fecha_estimada:
            instruccion += f"La fecha estimada es {fecha_estimada}. "
        else:
            instruccion += "No hay fecha estimada confirmada todavía. "
    else:
        if fecha_estimada and hora_estimada:
            instruccion += f"Estará listo el {fecha_estimada} a las {hora_estimada} aproximadamente. "
        elif fecha_estimada:
            instruccion += f"Estará listo el {fecha_estimada} aproximadamente. "
        else:
            instruccion += "No hay fecha/hora estimada confirmada todavía. "

    instruccion += "Responde natural, en una sola frase si se puede. No uses listas ni títulos."
    return instruccion


def _generar_instruccion_estado_reparacion(contexto: dict) -> str:
    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []

    if not reps:
        return None

    if len(reps) == 1:
        rep = reps[0]
        equipo = rep.get('equipo', 'el equipo')
        estado = rep.get('estado_texto', 'En seguimiento')
        fecha_ingreso = rep.get('fecha_ingreso', '')

        instruccion = (
            f"INSTRUCCION ESPECIAL: El cliente pregunta por el estado de su {equipo}. "
            f"Estado actual: {estado}. "
        )
        if fecha_ingreso:
            instruccion += f"Fecha de ingreso: {fecha_ingreso}. "

        instruccion += "Responde natural y conversacional. No uses listas ni formatos tipo ficha."
        return instruccion

    lista_reps = []
    for i, rep in enumerate(reps, 1):
        lista_reps.append(f"{i}. {rep.get('equipo', 'Equipo')} - {rep.get('estado_texto', 'En seguimiento')}")

    instruccion = (
        f"INSTRUCCION ESPECIAL: El cliente tiene {len(reps)} reparaciones activas: "
        + "; ".join(lista_reps) + ". "
        "Responde natural y pregunta de cuál quiere saber."
    )
    return instruccion


def _generar_instruccion_detalle_reparacion(contexto: dict) -> str:
    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []

    if not reps:
        return None

    rep_objetivo = None
    id_followup = contexto.get('followup_reparacion_id')
    if id_followup is not None:
        for rep in reps:
            if rep.get('id_reparacion') == id_followup:
                rep_objetivo = rep
                break
    if rep_objetivo is None and len(reps) == 1:
        rep_objetivo = reps[0]

    if rep_objetivo is None:
        return None

    equipo = rep_objetivo.get('equipo', 'el equipo')
    estado = rep_objetivo.get('estado_texto', 'En seguimiento')
    fecha_estimada = (rep_objetivo.get('fecha_estimada') or '').strip()
    hora_estimada = (rep_objetivo.get('hora_estimada') or '').strip()
    falla = (rep_objetivo.get('falla_reportada') or '').strip()

    instruccion = (
        f"INSTRUCCION ESPECIAL: El cliente pide más detalles sobre su {equipo}. "
        f"Estado: {estado}. "
    )

    if falla:
        instruccion += f"Falla reportada: {falla}. "

    if fecha_estimada and hora_estimada:
        instruccion += f"Estimado de entrega: {fecha_estimada} a las {hora_estimada}. "
    elif fecha_estimada:
        instruccion += f"Estimado de entrega: {fecha_estimada}. "

    instruccion += "Responde natural, sin listas ni viñetas."
    return instruccion


def _respuesta_directa_reparacion_desde_contexto(
    contexto: dict,
    texto: str,
    forzar_intencion_tiempo: bool = False,
    es_followup: bool = False,
) -> str | None:
    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []
    if not reps:
        return None
    if not forzar_intencion_tiempo and not _tiene_intencion_tiempo_reparacion(texto):
        return None

    if len(reps) == 1:
        rep = reps[0]
        modo_tiempo = _modo_consulta_tiempo(texto)
        fecha_estimada = (rep.get('fecha_estimada') or '').strip()
        hora_estimada = (rep.get('hora_estimada') or '').strip()
        equipo = rep.get('equipo', 'tu equipo')

        if es_followup:
            if modo_tiempo == 'hora' and hora_estimada:
                return f"Seria tipo {hora_estimada} 👍"
            if modo_tiempo == 'hora':
                return "Todavia no tengo una hora confirmada, apenas tenga te aviso."
            if modo_tiempo == 'fecha' and fecha_estimada:
                return f"Seria el {fecha_estimada} 👍"
            if modo_tiempo == 'fecha':
                return "Todavia no tengo una fecha confirmada, apenas tenga te aviso."
            if fecha_estimada and hora_estimada:
                return f"Tu {equipo} estaria listo el {fecha_estimada} a las {hora_estimada} aprox 👍"
            if fecha_estimada:
                return f"Tu {equipo} estaria listo el {fecha_estimada} aprox 👍"
            return "Todavia no tengo una fecha/hora confirmada, apenas tenga te aviso."

        if modo_tiempo == 'hora':
            if hora_estimada:
                return f"Para tu {equipo}, seria tipo {hora_estimada} aprox 👍"
            return f"Para tu {equipo} todavia no tengo una hora confirmada."

        if modo_tiempo == 'fecha':
            if fecha_estimada:
                return f"Para tu {equipo}, seria el {fecha_estimada} aprox 👍"
            return f"Para tu {equipo} todavia no tengo una fecha confirmada."

        if fecha_estimada and hora_estimada:
            return f"Tu {equipo} estaria listo el {fecha_estimada} a las {hora_estimada} aprox 👍"
        if fecha_estimada:
            return f"Tu {equipo} estaria listo el {fecha_estimada} aprox 👍"
        return f"Para tu {equipo} todavia no tengo una fecha/hora confirmada."

    texto_resp = f"Veo que tenes {len(reps)} reparaciones en curso! 🔧\n\n"
    for i, rep in enumerate(reps, 1):
        texto_resp += f"{i}. *{rep.get('equipo', 'Equipo')}* - {rep.get('estado_texto', 'En seguimiento')}\n"
    texto_resp += "\nDecime de cual queres saber y te paso el estado."
    return texto_resp


def _respuesta_detalle_etapa_desde_contexto(contexto: dict) -> str | None:
    info_cliente = (contexto or {}).get('info_cliente') or {}
    reps = info_cliente.get('reparaciones_activas') or []
    if not reps:
        return None

    rep_objetivo = None
    id_followup = contexto.get('followup_reparacion_id')
    if id_followup is not None:
        for rep in reps:
            if rep.get('id_reparacion') == id_followup:
                rep_objetivo = rep
                break
    if rep_objetivo is None and len(reps) == 1:
        rep_objetivo = reps[0]
    if rep_objetivo is None:
        return None

    etapa_por_estado = {
        'pendiente': 'pendiente de ingreso a mesa tecnica',
        'diagnostico': 'en diagnostico tecnico',
        'espera_presupuesto': 'esperando aprobacion de presupuesto',
        'espera_repuesto': 'esperando repuesto',
        'espera_cliente': 'esperando confirmacion del cliente',
        'en_proceso': 'en reparacion',
        'listo': 'listo para retiro',
        'no_se_pudo': 'sin posibilidad de reparacion',
    }
    estado_codigo = (rep_objetivo.get('estado') or '').strip().lower()
    etapa = etapa_por_estado.get(estado_codigo, 'en seguimiento')

    fecha_estimada = (rep_objetivo.get('fecha_estimada') or '').strip()
    hora_estimada = (rep_objetivo.get('hora_estimada') or '').strip()
    if fecha_estimada and hora_estimada:
        linea_tiempo = f"Y en principio estaria para el {fecha_estimada} a las {hora_estimada} aprox."
    elif fecha_estimada:
        linea_tiempo = f"Y en principio estaria para el {fecha_estimada} aprox."
    else:
        linea_tiempo = "Todavia no tengo una hora exacta confirmada."

    falla = (rep_objetivo.get('falla_reportada') or '').strip()
    if falla:
        return (
            f"Dale 👍 Tu *{rep_objetivo.get('equipo', 'Tu equipo')}* esta {etapa} "
            f"({rep_objetivo.get('estado_texto', 'En seguimiento')}). "
            f"Me figura que entro por: {falla}. {linea_tiempo}"
        )
    return (
        f"Dale 👍 Tu *{rep_objetivo.get('equipo', 'Tu equipo')}* esta {etapa} "
        f"({rep_objetivo.get('estado_texto', 'En seguimiento')}). {linea_tiempo}"
    )
