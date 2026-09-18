# Capa: dominio
"""
AgregarEstado — servicio de dominio (RF3).

Regla de agregación explícita (determinista, sin ML, sin estadística):
  TODOS los parámetros son OPTIMO                  → SALUDABLE
  Exactamente 1 parámetro fuera de rango           → EN_RIESGO
  2 o más parámetros fuera de rango                → CRITICO

"Fuera de rango" = clasificación individual BAJO o ALTO.

No importa nada de infraestructura, Flask, pandas, csv ni requests.
"""
from __future__ import annotations

from typing import List

from Modelo.entidades import (
    CRITICO,
    EN_RIESGO,
    OPTIMO,
    SALUDABLE,
    DiagnosticoPlanta,
    ResultadoParametro,
)


class AgregarEstado:
    """Deriva el estado global de salud a partir de los resultados individuales."""

    def agregar(
        self, especie: str, resultados: List[ResultadoParametro]
    ) -> DiagnosticoPlanta:
        fuera_de_rango = [r for r in resultados if r.clasificacion != OPTIMO]
        n = len(fuera_de_rango)

        if n == 0:
            estado = SALUDABLE
        elif n == 1:
            estado = EN_RIESGO
        else:
            estado = CRITICO

        return DiagnosticoPlanta(
            especie=especie,
            estado_global=estado,
            parametros=resultados,
        )
