# Capa: dominio
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from Modelo.entidades import RangosEspecie


@runtime_checkable
class IRepositorioEspecies(Protocol):
    """Contrato abstracto para la obtencion de rangos de referencia por especie."""

    def obtener_rangos(self, especie: str) -> Optional[RangosEspecie]:
        ...

    def listar_especies(self) -> List[RangosEspecie]:
        ...
