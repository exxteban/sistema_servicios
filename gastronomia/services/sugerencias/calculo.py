"""Matemática portada del padre, sin cambios de lógica."""
import math
from datetime import datetime
from gastronomia.services.sugerencias import constantes as C

class _Conteo:
    """Tickets por elemento y por par, en crudo y ponderados por recencia."""

    def __init__(self):
        self.crudo: dict[int, int] = {}
        self.peso: dict[int, float] = {}
        self.par_crudo: dict[tuple[int, int], int] = {}
        self.par_peso: dict[tuple[int, int], float] = {}
        self.peso_total = 0.0

    def sumar(self, elementos: set[int], peso: float):
        self.peso_total += peso
        ordenados = sorted(elementos)
        for e in ordenados:
            self.crudo[e] = self.crudo.get(e, 0) + 1
            self.peso[e] = self.peso.get(e, 0.0) + peso
        for i, a in enumerate(ordenados):
            for b in ordenados[i + 1:]:
                clave = (a, b)
                self.par_crudo[clave] = self.par_crudo.get(clave, 0) + 1
                self.par_peso[clave] = self.par_peso.get(clave, 0.0) + peso

    def pares(self, origen_valido=None, destino_valido=None):
        """Pares A -> B que pasan los minimos, los mejores por origen."""
        por_origen: dict[int, list[dict]] = {}
        if self.peso_total <= 0:
            return por_origen
        for (a, b), soporte in self.par_crudo.items():
            if soporte < C.SOPORTE_MINIMO:
                continue
            peso_par = self.par_peso[(a, b)]
            for origen, destino in ((a, b), (b, a)):
                if origen_valido and not origen_valido(origen):
                    continue
                if destino_valido and not destino_valido(destino):
                    continue
                medida = medir(peso_par, self.peso[origen], self.peso[destino], self.peso_total)
                if medida is None:
                    continue
                por_origen.setdefault(origen, []).append({
                    'id_destino': destino, 'soporte': soporte, **medida,
                })
        for origen, lista in por_origen.items():
            lista.sort(key=lambda d: (-d['puntaje'], d['id_destino']))
            del lista[C.MAX_DESTINOS_POR_ORIGEN:]
        return por_origen


def medir(peso_par: float, peso_origen: float, peso_destino: float, peso_total: float,
          confianza_minima: float = C.CONFIANZA_MINIMA, lift_minimo: float = C.LIFT_MINIMO):
    """Confianza, lift y puntaje de A -> B, o None si no pasa los minimos.

    Los minimos se pueden pasar para el diagnostico ("¿cuantos pasarian con...?").
    """
    if peso_origen <= 0 or peso_destino <= 0 or peso_total <= 0:
        return None
    confianza = peso_par / peso_origen
    if confianza < confianza_minima:
        return None
    lift = confianza / (peso_destino / peso_total)
    if lift < lift_minimo:
        return None
    # Suavizado: 4 de 5 no le gana a 60 de 100.
    confianza_ajustada = peso_par / (peso_origen + C.SUAVIZADO_CONFIANZA)
    return {
        'confianza': confianza,
        'lift': lift,
        'puntaje': confianza_ajustada * math.log(1 + lift),
    }


def peso_por_antiguedad(fecha: datetime | None, ahora: datetime) -> float:
    if fecha is None:
        return C.RECENCIA_PESO_MINIMO
    dias = max(0.0, (ahora - fecha).total_seconds() / 86400)
    if dias <= C.RECENCIA_DIAS_PLENO:
        return 1.0
    tramo = max(1, C.VENTANA_DIAS - C.RECENCIA_DIAS_PLENO)
    avance = min(1.0, (dias - C.RECENCIA_DIAS_PLENO) / tramo)
    return 1.0 - avance * (1.0 - C.RECENCIA_PESO_MINIMO)


