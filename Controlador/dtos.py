"""
DTOs y validación de entrada para la capa de presentación/controlador.

Transforma el dict crudo del request HTTP en datos validados y tipados
antes de que lleguen al caso de uso (RA6).
Maneja de forma estructurada los errores requeridos por RF6.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# Límites físicos razonables para validación (RF6)
HUMEDAD_MIN_FISICA = 0.0
HUMEDAD_MAX_FISICA = 100.0
TEMPERATURA_MIN_FISICA = -89.0   # récord histórico más frío en la Tierra
TEMPERATURA_MAX_FISICA = 60.0    # límite superior razonable para plantas
LUX_MIN_FISICA = 0.0
LUX_MAX_FISICA = 120_000.0       # luz solar directa máxima en ecuador ≈ 100 000 lux


class ErrorValidacion(ValueError):
    """Error de validación de entrada con código y detalle estructurado (RF6)."""

    def __init__(self, codigo: str, mensaje: str, detalle: Optional[Dict] = None) -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalle = detalle or {}
        super().__init__(mensaje)

    def to_dict(self) -> dict:
        return {
            "error": self.codigo,
            "mensaje": self.mensaje,
            "detalle": self.detalle,
        }


def parsear_solicitud(datos: dict) -> Tuple[str, float, float, float]:
    """
    Valida y extrae los campos del payload JSON recibido.
    Lanza ErrorValidacion para cada caso requerido por RF6:
      - parámetro ausente
      - valor no numérico
      - valor fuera de rango físicamente posible
    Devuelve (especie, luminosidad, humedad, temperatura).
    """
    # 1. Parámetros ausentes
    campos_requeridos = ("especie", "luminosidad", "humedad", "temperatura")
    faltantes = [c for c in campos_requeridos if datos.get(c) is None]
    if faltantes:
        raise ErrorValidacion(
            codigo="PARAMETRO_AUSENTE",
            mensaje="Faltan parámetros obligatorios en la solicitud.",
            detalle={"faltantes": faltantes},
        )

    especie = str(datos["especie"]).strip()
    if not especie:
        raise ErrorValidacion(
            codigo="PARAMETRO_AUSENTE",
            mensaje="El campo 'especie' no puede estar vacío.",
        )

    # 2. Valores no numéricos
    numericos = {}
    for campo in ("luminosidad", "humedad", "temperatura"):
        try:
            numericos[campo] = float(datos[campo])
        except (TypeError, ValueError):
            raise ErrorValidacion(
                codigo="VALOR_NO_NUMERICO",
                mensaje=f"El campo '{campo}' debe ser numérico.",
                detalle={"campo": campo, "valor_recibido": str(datos[campo])},
            )

    # 3. Rangos físicamente posibles
    limites = {
        "luminosidad": (LUX_MIN_FISICA, LUX_MAX_FISICA, "lux"),
        "humedad": (HUMEDAD_MIN_FISICA, HUMEDAD_MAX_FISICA, "%"),
        "temperatura": (TEMPERATURA_MIN_FISICA, TEMPERATURA_MAX_FISICA, "°C"),
    }
    for campo, (minimo, maximo, unidad) in limites.items():
        val = numericos[campo]
        if not (minimo <= val <= maximo):
            raise ErrorValidacion(
                codigo="VALOR_FUERA_DE_RANGO_FISICO",
                mensaje=(
                    f"El valor de '{campo}' ({val} {unidad}) está fuera del rango "
                    f"físicamente posible [{minimo}, {maximo}] {unidad}."
                ),
                detalle={"campo": campo, "valor": val, "min": minimo, "max": maximo},
            )

    return especie, numericos["luminosidad"], numericos["humedad"], numericos["temperatura"]
