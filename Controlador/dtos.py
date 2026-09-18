"""Validación de entrada y normalización del payload JSON."""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# Umbrales fisicos extremos para descartar lecturas de sensores danados o corruptos
HUMEDAD_MIN_FISICA = 0.0
HUMEDAD_MAX_FISICA = 100.0
TEMPERATURA_MIN_FISICA = -89.0   # Record historico terrestre
TEMPERATURA_MAX_FISICA = 60.0    # Limite fisiologico maximo para vegetacion
LUX_MIN_FISICA = 0.0
LUX_MAX_FISICA = 120_000.0       # Radiacion solar directa cenital


class ErrorValidacion(ValueError):
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
