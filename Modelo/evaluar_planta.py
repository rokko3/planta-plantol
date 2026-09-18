# Capa: aplicación
from __future__ import annotations

from dataclasses import dataclass

from Modelo.entidades import DiagnosticoPlanta
from Modelo.puertos import IRepositorioEspecies
from Modelo.agregador import AgregarEstado
from Modelo.clasificador import ClasificadorParametro


@dataclass(frozen=True)
class SolicitudDiagnostico:
    """Valores de entrada requeridos para evaluar una planta."""
    especie: str
    luminosidad: float
    humedad: float
    temperatura: float


class EvaluarPlanta:
    """Caso de uso que orquesta la clasificacion y agregacion del diagnostico."""

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
    def __init__(self, especie: str) -> None:
        self.especie = especie
        super().__init__(f"Especie no soportada: '{especie}'")
