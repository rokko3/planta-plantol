# Capa: dominio
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

BAJO = "BAJO"
OPTIMO = "OPTIMO"
ALTO = "ALTO"

SALUDABLE = "SALUDABLE"
EN_RIESGO = "EN_RIESGO"
CRITICO = "CRITICO"


@dataclass(frozen=True)
class RangosEspecie:
    """Rangos optimos de luminosidad, humedad y temperatura por especie."""
    nombre: str
    lux_min: float
    lux_max: float
    humedad_min: float
    humedad_max: float
    temperatura_min: float
    temperatura_max: float


@dataclass(frozen=True)
class ResultadoParametro:
    """Evaluacion individual de un parametro ambiental."""
    nombre: str
    valor: float
    clasificacion: str
    recomendacion: str


@dataclass(frozen=True)
class DiagnosticoPlanta:
    """Diagnostico consolidado del estado de salud de una planta."""
    especie: str
    estado_global: str
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
