# Capa: aplicación
"""
Caso de uso: EvaluarPlanta (Capa de Aplicación).

Orquesta los servicios de dominio para producir un diagnóstico completo.
Depende únicamente del puerto IRepositorioEspecies (RA5 / DIP).
NUNCA importa repositorio_csv.py directamente (se le inyecta en el constructor).
No importa Flask, pandas, csv ni infraestructura concreta.
"""
from __future__ import annotations

from dataclasses import dataclass

from Modelo.entidades import DiagnosticoPlanta
from Modelo.puertos import IRepositorioEspecies
from Modelo.agregador import AgregarEstado
from Modelo.clasificador import ClasificadorParametro


# ---------------------------------------------------------------------------
# DTO de entrada al caso de uso (RA6) — objeto tipado inmutable
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SolicitudDiagnostico:
    """Objeto de entrada al caso de uso. Reemplaza el dict crudo del request."""
    especie: str
    luminosidad: float
    humedad: float
    temperatura: float


# ---------------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------------

class EvaluarPlanta:
    """Orquesta clasificación + agregación para producir un DiagnosticoPlanta."""

    def __init__(self, repositorio: IRepositorioEspecies) -> None:
        self._repo = repositorio
        self._clasificador = ClasificadorParametro()
        self._agregador = AgregarEstado()

    def ejecutar(self, solicitud: SolicitudDiagnostico) -> DiagnosticoPlanta:
        rangos = self._repo.obtener_rangos(solicitud.especie)
        if rangos is None:
            raise EspecieNoSoportadaError(solicitud.especie)

        resultados = self._clasificador.clasificar_todos(
            rangos,
            luminosidad=solicitud.luminosidad,
            humedad=solicitud.humedad,
            temperatura=solicitud.temperatura,
        )
        return self._agregador.agregar(solicitud.especie, resultados)


class EspecieNoSoportadaError(ValueError):
    """Se lanza cuando la especie solicitada no existe en la tabla de referencia (RF6)."""

    def __init__(self, especie: str) -> None:
        self.especie = especie
        super().__init__(f"Especie no soportada: '{especie}'")
