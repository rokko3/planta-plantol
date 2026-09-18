# Capa: dominio
"""
Puertos (interfaces) del dominio (RA5).
Define los contratos que la infraestructura debe implementar.
El dominio NO depende de ninguna implementación concreta ni de infraestructura.
"""
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from Modelo.entidades import RangosEspecie


@runtime_checkable
class IRepositorioEspecies(Protocol):
    """Puerto de acceso a la tabla de referencia de especies.

    La implementación concreta (CSV, BD relacional, in-memory) vive en infraestructura.
    El dominio solo conoce esta interfaz (DIP, RA5).
    """

    def obtener_rangos(self, especie: str) -> Optional[RangosEspecie]:
        """Devuelve los rangos óptimos para la especie dada, o None si no se soporta."""
        ...

    def listar_especies(self) -> List[RangosEspecie]:
        """Devuelve todas las especies registradas con sus rangos."""
        ...
