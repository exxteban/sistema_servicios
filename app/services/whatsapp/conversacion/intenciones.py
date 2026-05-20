import unicodedata


def _normalizar_texto_intencion(texto: str) -> str:
    t = (texto or '').strip().lower()
    if not t:
        return ''
    t = unicodedata.normalize('NFD', t)
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    t = t.replace('¿', '').replace('?', '').replace('¡', '').replace('!', '')
    t = t.replace('.', ' ').replace(',', ' ').replace(';', ' ').replace(':', ' ')
    t = ' '.join(t.split())
    return t


def _es_saludo_simple(texto: str) -> bool:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False
    saludos = (
        'hola',
        'holaa',
        'holaaa',
        'buenas',
        'buen dia',
        'buen día',
        'buenas tardes',
        'buenas noches',
        'hello',
        'hi',
    )
    if t in saludos:
        return True
    if len(t.split()) <= 2 and t.startswith('hola'):
        return True
    if t in ('gola', 'golaa', 'golaaa', 'golaaaa', 'golaaaaa', 'golaaaaaa'):
        return True
    if len(t.split()) <= 2 and t.startswith('gola'):
        return True
    return False


def _es_confirmacion_corta(texto: str) -> bool:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False

    confirmaciones = (
        'si',
        'sí',
        'si por favor',
        'si porfa',
        'dale',
        'dale por favor',
        'ok',
        'okay',
        'ok por favor',
        'de una',
        'va',
        'genial',
        'perfecto',
        'contame',
        'contame nomas',
        'conta',
        'manda',
    )
    if t in confirmaciones:
        return True
    if len(t.split()) <= 3 and (t.startswith('si') or t.startswith('dale') or t.startswith('ok')):
        return True
    return False


def _pide_mas_detalle_reparacion(texto: str) -> bool:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False

    frases = (
        'mas datos',
        'algo mas',
        'mas info',
        'mas informacion',
        'mas detalle',
        'algun dato mas',
        'que mas',
        'otro dato',
        'contame mas',
        'amplia',
        'detallame',
    )
    return any(f in t for f in frases)


def _tiene_intencion_tiempo_reparacion(texto: str) -> bool:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False

    keywords = (
        'cuando va estar',
        'cuando va a estar',
        'que hora va estar',
        'que hora va a estar',
        'que fecha va estar',
        'que fecha va a estar',
        'que dia va estar',
        'que dia va a estar',
        'fecha de entrega',
        'dia de entrega',
        'a que hora',
        'que hora',
        'para cuando',
        'ya va estar',
        'ya va a estar',
        'falta mucho',
        'cuando estaria',
        'cuando esta',
        'ya esta',
        'esta listo',
        'esta lista',
    )
    return any(k in t for k in keywords)


def _modo_consulta_tiempo(texto: str) -> str:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return 'fecha_hora'

    if 'hora' in t or 'a que hora' in t:
        return 'hora'

    pistas_fecha = (
        'que fecha',
        'que dia',
        'para que fecha',
        'para que dia',
        'dia de entrega',
        'fecha de entrega',
    )
    if any(p in t for p in pistas_fecha):
        return 'fecha'

    return 'fecha_hora'


def _tiene_intencion_reparacion(texto: str) -> bool:
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False

    keywords = (
        'repar',
        'arreglo',
        'equipo',
        'celular',
        'telefono',
        'estado',
        'deje',
        'traje',
        'lleve',
        'en curso',
        'listo',
        'como va',
        'cuando esta',
        'cuando va estar',
        'cuando va a estar',
        'para cuando',
        'ya va estar',
        'ya va a estar',
        'falta mucho',
        'cuando estaria',
        'ya esta',
    )
    return any(k in t for k in keywords)


def _cliente_pide_asesor(texto: str) -> bool:
    t = (texto or '').strip().lower()
    if not t:
        return False

    if t in ('pasame', 'pásame', 'pasame.', 'pásame.', 'pasame!', 'pásame!', 'pasame ahora', 'pásame ahora'):
        return True

    keywords = (
        'asesor',
        'humano',
        'persona',
        'operador',
        'representante',
        'atencion al cliente',
        'atención al cliente',
    )
    if any(k in t for k in keywords):
        return True

    frases = (
        'hablar con alguien',
        'hablar con una persona',
        'hablar con un humano',
        'quiero hablar con',
        'pasame',
        'pásame',
        'pasame con',
        'pásame con',
        'pasar con',
        'pasame a',
        'pásame a',
    )
    return any(f in t for f in frases)


def _cliente_esta_enojado(texto: str) -> bool:
    t = (texto or '').strip().lower()
    if not t:
        return False
    keywords = (
        'reclamo',
        'queja',
        'enoj',
        'molest',
        'pesimo',
        'pésimo',
        'mal servicio',
        'estafa',
        'ladron',
        'ladrón',
        'denuncia',
        'vergüenza',
        'verguenza',
        'harto',
        'nunca mas',
        'nunca más',
    )
    return any(k in t for k in keywords)


def _cliente_pregunta_por_su_reparacion(texto: str) -> bool:
    """
    Detecta cuando el cliente CLARAMENTE menciona haber dejado algo para reparar
    o pregunta por el estado de su reparación propia.
    Más preciso que _tiene_intencion_reparacion para evitar falsos positivos con consultas de ventas.
    """
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False

    # Frases que indican claramente que el cliente dejó algo para reparar
    frases_dejo = (
        'deje',
        'deje para',
        'deje un',
        'deje mi',
        'traje',
        'traje para',
        'lleve',
        'lleve para',
        'entregue',
        'deje a reparar',
        'para reparar',
        'a reparar',
        'en reparacion',
        'en reparación',
        'mi reparacion',
        'mi reparación',
        'mi celular',
        'mi telefono',
        'mi teléfono',
        'mi equipo',
        'mi tablet',
        'mi notebook',
        'como va mi',
        'como esta mi',
        'como está mi',
        'estado de mi',
        'estado de la reparacion',
        'estado de la reparación',
        'cuando esta mi',
        'cuando está mi',
        'cuando va estar mi',
        'cuando va a estar mi',
        'ya esta mi',
        'ya está mi',
        'ya lo terminaron',
        'ya lo arreglaron',
        'ya arreglaron',
        'ya termino',
        'ya terminó',
        'repar',
    )
    return any(f in t for f in frases_dejo)


def _es_agradecimiento_o_cierre(texto: str) -> bool:
    """Detecta si el mensaje es un agradecimiento o expresión de cierre."""
    t = _normalizar_texto_intencion(texto)
    if not t:
        return False
    
    # Expresiones de agradecimiento
    agradecimientos = (
        'gracias',
        'grax',
        'graciass',
        'graciasss',
        'muchas gracias',
        'mil gracias',
        'te agradezco',
        'agradezco',
        'thanks',
        'thank you',
    )
    
    # Expresiones de cierre/confirmación satisfecha
    cierres = (
        'ah genial',
        'ah perfecto',
        'ah bueno',
        'ah ok',
        'ah dale',
        'genial gracias',
        'perfecto gracias',
        'buenisimo',
        'buenísimo',
        'excelente',
        'barbaro',
        'bárbaro',
        'joya',
        'de diez',
        'todo bien',
        'todo ok',
        'esta bien',
        'está bien',
        'listo gracias',
        'listo entonces',
        'entendido',
        'entiendo',
        'ya entendi',
        'ya entendí',
    )
    
    # Expresiones cortas de cierre cuando hay contexto previo
    cierres_cortos = (
        'dale gracias',
        'dale muchas gracias',
        'ok gracias',
        'perfecto',
        'genial',
        'bueno',
        'listo',
        'joya',
    )
    
    # Check agradecimientos
    if any(a in t for a in agradecimientos):
        return True
    
    # Check cierres
    if any(c in t for c in cierres):
        return True
    
    # Check cierres cortos solo si el mensaje es muy corto (máximo 3 palabras)
    palabras = t.split()
    if len(palabras) <= 3:
        if t in cierres_cortos:
            return True
        # También detectar variaciones con emojis o puntuación
        for c in cierres_cortos:
            if t.startswith(c) or t.endswith(c):
                return True
    
    return False

