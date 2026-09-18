# Capa: dominio
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
            # Dos o mas parametros anomalos comprometen severamente la viabilidad de la planta
            estado = CRITICO

        return DiagnosticoPlanta(
            especie=especie,
            estado_global=estado,
            parametros=resultados,
        )
