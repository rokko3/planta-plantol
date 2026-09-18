# Capa: dominio
"""
Entidades y Value Objects del dominio.
No importa nada de infraestructura, Flask, pandas, csv ni requests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Clasificación de un parámetro individual (RF2)
# ---------------------------------------------------------------------------

BAJO = "BAJO"
OPTIMO = "OPTIMO"
ALTO = "ALTO"

# ---------------------------------------------------------------------------
# Estado global de salud de la planta (RF3)
# ---------------------------------------------------------------------------

SALUDABLE = "SALUDABLE"
EN_RIESGO = "EN_RIESGO"
CRITICO = "CRITICO"


@dataclass(frozen=True)
class RangosEspecie:
    """Límites óptimos (min/max) para cada parámetro ambiental de una especie."""

    nombre: str
    lux_min: float
    lux_max: float
    humedad_min: float
    humedad_max: float
    temperatura_min: float
    temperatura_max: float


@dataclass(frozen=True)
class ResultadoParametro:
    """Resultado de la evaluación de UN parámetro ambiental (RF2, RF4)."""

    nombre: str          # "luminosidad" | "humedad" | "temperatura"
    valor: float
    clasificacion: str   # BAJO | OPTIMO | ALTO
    recomendacion: str   # texto con recomendación si fuera de rango, o vacío si OPTIMO


@dataclass(frozen=True)
class DiagnosticoPlanta:
    """Resultado completo del diagnóstico para una planta (RF1-RF4)."""

    especie: str
    estado_global: str                        # SALUDABLE | EN_RIESGO | CRITICO
    parametros: List[ResultadoParametro] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "especie": self.especie,
            "estado_global": self.estado_global,
            "parametros": [
                {
                    "nombre": p.nombre,
                    "valor": p.valor,
                    "clasificacion": p.clasificacion,
                    "recomendacion": p.recomendacion,
                }
                for p in self.parametros
            ],
        }
