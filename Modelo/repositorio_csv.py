# Capa: infraestructura
"""
RepositorioEspeciesCSV — implementación concreta del puerto IRepositorioEspecies (RA5).

Lee el archivo CSV de rangos de especies y devuelve entidades de dominio (RangosEspecie).
Es el único módulo en Modelo/ autorizado para importar csv/IO de persistencia.
El dominio desconoce que los datos provienen de un archivo CSV.
"""
from __future__ import annotations

import csv
import os
from typing import Dict, List, Optional

from Modelo.entidades import RangosEspecie


class RepositorioEspeciesCSV:
    """Implementa IRepositorioEspecies leyendo el CSV de especies."""

    def __init__(self, ruta_csv: str) -> None:
        self._ruta = ruta_csv
        self._cache: Optional[Dict[str, RangosEspecie]] = None

    # ------------------------------------------------------------------
    # Puerto público (satisface IRepositorioEspecies)
    # ------------------------------------------------------------------

    def obtener_rangos(self, especie: str) -> Optional[RangosEspecie]:
        return self._indice().get(especie.strip().lower())

    def listar_especies(self) -> List[RangosEspecie]:
        return list(self._indice().values())

    # ------------------------------------------------------------------
    # Métodos internos de carga y cache
    # ------------------------------------------------------------------

    def _indice(self) -> Dict[str, RangosEspecie]:
        if self._cache is None:
            self._cache = self._cargar()
        return self._cache

    def _cargar(self) -> Dict[str, RangosEspecie]:
        indice: Dict[str, RangosEspecie] = {}
        if not os.path.exists(self._ruta):
            return indice

        with open(self._ruta, encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                nombre = fila.get("especie", "").strip()
                if not nombre or nombre.startswith("#"):
                    continue
                try:
                    rangos = RangosEspecie(
                        nombre=nombre,
                        lux_min=float(fila["lux_min"]),
                        lux_max=float(fila["lux_max"]),
                        humedad_min=float(fila["humedad_min"]),
                        humedad_max=float(fila["humedad_max"]),
                        temperatura_min=float(fila["temperatura_min"]),
                        temperatura_max=float(fila["temperatura_max"]),
                    )
                    indice[nombre.lower()] = rangos
                except (KeyError, ValueError):
                    continue  # fila malformada, se ignora

        return indice
