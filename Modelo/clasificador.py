# Capa: dominio
"""
ClasificadorParametro — servicio de dominio (RF2, RF4).

Clasifica un valor numérico individual como BAJO, OPTIMO o ALTO
dado un rango [min, max] específico de la especie.
Asocia recomendaciones textuales específicas cuando el valor sale del rango óptimo.

Reglas de clasificación (RF2):
  valor < min                         → BAJO
  min <= valor <= max                 → OPTIMO
  valor > max                         → ALTO

No importa nada de infraestructura, Flask, pandas, csv ni requests.
"""
from __future__ import annotations

from typing import List

from Modelo.entidades import (
    ALTO,
    BAJO,
    OPTIMO,
    RangosEspecie,
    ResultadoParametro,
)


# ---------------------------------------------------------------------------
# Definición de los parámetros evaluables (OCP: extensible sin modificar el core)
# Cada tupla: (nombre_campo, min_attr, max_attr, unidad, reco_bajo, reco_alto)
# ---------------------------------------------------------------------------
PARAMETROS_EVALUABLES = [
    (
        "luminosidad",
        "lux_min",
        "lux_max",
        "lux",
        "Aumenta la exposición a la luz natural o artificial.",
        "Reduce la exposición a la luz directa o mueve la planta a sombra parcial.",
    ),
    (
        "humedad",
        "humedad_min",
        "humedad_max",
        "%",
        "Aumenta el riego o usa un humidificador cerca de la planta.",
        "Reduce la frecuencia de riego y asegura buen drenaje.",
    ),
    (
        "temperatura",
        "temperatura_min",
        "temperatura_max",
        "°C",
        "Mueve la planta a un lugar más cálido y alejado de corrientes de aire frío.",
        "Mueve la planta a un lugar más fresco o ventilado.",
    ),
]


class ClasificadorParametro:
    """Clasifica parámetros individuales contra los rangos de una especie."""

    def clasificar_uno(
        self,
        nombre: str,
        valor: float,
        v_min: float,
        v_max: float,
        reco_bajo: str,
        reco_alto: str,
    ) -> ResultadoParametro:
        if valor < v_min:
            return ResultadoParametro(
                nombre=nombre,
                valor=valor,
                clasificacion=BAJO,
                recomendacion=reco_bajo,
            )
        if valor > v_max:
            return ResultadoParametro(
                nombre=nombre,
                valor=valor,
                clasificacion=ALTO,
                recomendacion=reco_alto,
            )
        return ResultadoParametro(
            nombre=nombre,
            valor=valor,
            clasificacion=OPTIMO,
            recomendacion="",
        )

    def clasificar_todos(
        self, rangos: RangosEspecie, **valores: float
    ) -> List[ResultadoParametro]:
        """
        Itera sobre PARAMETROS_EVALUABLES (OCP: agregar un parámetro =
        agregar una entrada a la lista, sin tocar esta función).
        """
        resultados = []
        for nombre, min_attr, max_attr, _unidad, reco_bajo, reco_alto in PARAMETROS_EVALUABLES:
            if nombre not in valores:
                continue
            resultado = self.clasificar_uno(
                nombre=nombre,
                valor=valores[nombre],
                v_min=getattr(rangos, min_attr),
                v_max=getattr(rangos, max_attr),
                reco_bajo=reco_bajo,
                reco_alto=reco_alto,
            )
            resultados.append(resultado)
        return resultados
