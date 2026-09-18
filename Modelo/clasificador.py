# Capa: dominio
from __future__ import annotations

from typing import List

from Modelo.entidades import (
    ALTO,
    BAJO,
    OPTIMO,
    RangosEspecie,
    ResultadoParametro,
)

# Mapeo de atributos de la especie a evaluar y sus recomendaciones asociadas
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
        # Los limites exactos (min y max) se consideran dentro del rango optimo
        return ResultadoParametro(
            nombre=nombre,
            valor=valor,
            clasificacion=OPTIMO,
            recomendacion="",
        )

    def clasificar_todos(
        self, rangos: RangosEspecie, **valores: float
    ) -> List[ResultadoParametro]:
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
