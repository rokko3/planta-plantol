import csv
import os

import pandas as pd


class RepositorioDatos:
    def __init__(self, especies_path, dataset_path):
        self.especies_path = especies_path
        self.dataset_path = dataset_path

    def obtener_especies(self):
        especies = []
        if os.path.exists(self.especies_path):
            try:
                with open(self.especies_path, mode="r", encoding="utf-8") as archivo:
                    for fila in csv.DictReader(archivo):
                        nombre = fila.get("nombre", "").strip()
                        if nombre:
                            especies.append(nombre)
            except (OSError, csv.Error):
                especies = []

        return especies or [
            "Orquídea (Orchidaceae)",
            "Helecho (Pteridophyta)",
            "Cactus (Cactaceae)",
            "Girasol (Helianthus annuus)",
            "Suculenta (Echeveria)",
        ]

    def cargar_datos_para_especie(self, especie, minimo_muestras):
        if not os.path.exists(self.dataset_path):
            return None

        datos = pd.read_csv(self.dataset_path)
        datos_especie = datos[
            datos["especie"].str.strip().str.lower() == especie.strip().lower()
        ]
        if datos_especie.empty or len(datos_especie) < minimo_muestras:
            return datos
        return datos_especie
