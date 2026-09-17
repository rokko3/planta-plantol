"""
Caso de uso: EvaluarPlanta

Orquesta los servicios de dominio para producir un diagnóstico completo.
Depende solo de la interfaz IRepositorioEspecies (RA5/DIP).
No importa Flask ni infraestructura concreta.
"""
from __future__ import annotations

from dataclasses import dataclass

from dominio.entidades import DiagnosticoPlanta
from dominio.puertos import IRepositorioEspecies
from dominio.servicios.agregador import AgregarEstado
from dominio.servicios.clasificador import ClasificadorParametro


# ---------------------------------------------------------------------------
# DTO de entrada (RA6) — objeto tipado, no dict crudo
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
    """Se lanza cuando la especie solicitada no está en la tabla de referencia."""

    def __init__(self, especie: str) -> None:
        self.especie = especie
        super().__init__(f"Especie no soportada: '{especie}'")
