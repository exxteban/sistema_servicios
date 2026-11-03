"""Identidad de cliente final por telefono para el BI de gastronomia.

- La identidad es el telefono normalizado. Nunca se usa el nombre: dos personas
  con el mismo nombre no se agrupan.
- Un pedido queda identificado si trae cliente_final_id (tienda online) o un
  telefono valido (POS o carga manual).
- Sin pedidos la cobertura es None (dato desconocido), no 0.
"""
from __future__ import annotations

from app.utils.phone_utils import normalizar_telefono


def telefono_normalizado(celular: str | None) -> str | None:
    texto = (celular or '').strip()
    return normalizar_telefono(texto) if texto else None


def pedido_identificado(celular: str | None, cliente_final_id: int | None) -> bool:
    return cliente_final_id is not None or telefono_normalizado(celular) is not None


def telefono_invalido(celular: str | None, cliente_final_id: int | None) -> bool:
    """Hay telefono cargado pero no es valido: no crea identidad."""
    if cliente_final_id is not None or not (celular or '').strip():
        return False
    return telefono_normalizado(celular) is None


def cobertura_identidad(filas: list[dict]) -> dict:
    total = len(filas)
    identificados = sum(1 for fila in filas if fila['identificado'])
    return {
        'total': total,
        'identificados': identificados,
        'porcentaje': round(identificados * 100 / total, 1) if total else None,
        'telefonos_invalidos': sum(1 for fila in filas if fila['telefono_invalido']),
    }
