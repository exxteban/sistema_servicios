"""
Parser tolerante para tool calls textuales DSML.
"""
import json
import re
from types import SimpleNamespace


ALIASES_TOOLS = {
    'clientes_a_recuperar': 'clientes_para_contactar',
}

INVOKE_RE = re.compile(
    r'<\s*\|\s*DSML\s*\|\s*invoke\s+name=["\'](?P<name>[\w_]+)["\']\s*>(?P<body>.*?)<\s*/\s*\|\s*DSML\s*\|\s*invoke\s*>',
    re.IGNORECASE | re.DOTALL,
)
PARAM_RE = re.compile(
    r'<\s*\|\s*DSML\s*\|\s*parameter\s+name=["\'](?P<name>[\w_]+)["\'](?:\s+\w+=["\'][^"\']*["\'])*\s*>(?P<value>.*?)<\s*/\s*\|\s*DSML\s*\|\s*parameter\s*>',
    re.IGNORECASE | re.DOTALL,
)


def _valor_parametro(raw: str):
    texto = (raw or '').strip()
    if texto.lower() in {'true', 'false'}:
        return texto.lower() == 'true'
    try:
        return int(texto)
    except Exception:
        return texto


def _argumentos_desde_json(body: str) -> dict:
    try:
        parsed = json.loads((body or '').strip())
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed.get('arguments') if isinstance(parsed.get('arguments'), dict) else parsed


def _argumentos_desde_parametros(body: str) -> dict:
    argumentos = {}
    for match in PARAM_RE.finditer(body or ''):
        argumentos[match.group('name')] = _valor_parametro(match.group('value'))
    return argumentos


def tool_calls_textuales(contenido: str) -> list:
    calls = []
    for idx, match in enumerate(INVOKE_RE.finditer(contenido or '')):
        nombre = ALIASES_TOOLS.get(match.group('name'), match.group('name'))
        body = match.group('body') or ''
        argumentos = _argumentos_desde_json(body) or _argumentos_desde_parametros(body)
        calls.append(SimpleNamespace(
            id=f'text_call_{idx + 1}',
            function=SimpleNamespace(name=nombre, arguments=json.dumps(argumentos)),
        ))
    return calls
