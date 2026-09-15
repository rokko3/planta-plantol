import numpy as np


class PredictorSalud:
    TRADUCCIONES = {
        "Healthy": "Saludable 🌿",
        "Moderate Stress": "Estrés Moderado ⚠️",
        "High Stress": "Estrés Alto 🚨",
    }

    def __init__(self, repositorio, muestras_minimas=5):
        self.repositorio = repositorio
        self.muestras_minimas = muestras_minimas
        self._datos_por_especie = {}

    def predecir(self, especie, luminosidad, humedad, temperatura):
        datos = self._obtener_datos(especie)
        if datos is None:
            return "Desconocido", {}

        std_lum = datos["luminosidad"].std() or 1.0
        std_hum = datos["humedad"].std() or 1.0
        std_temp = datos["temperatura"].std() or 1.0
        distancias = np.sqrt(
            ((datos["luminosidad"] - luminosidad) / std_lum) ** 2
            + ((datos["humedad"] - humedad) / std_hum) ** 2
            + ((datos["temperatura"] - temperatura) / std_temp) ** 2
        )

        indices_vecinos = distancias.nsmallest(self.muestras_minimas).index
        estado_raw = datos.loc[indices_vecinos, "estado_salud"].mode()[0]
        estado_formateado = self.TRADUCCIONES.get(estado_raw, estado_raw)
        detalles = {
            "estado_raw": estado_raw,
            "estado_formateado": estado_formateado,
            "distancia_similitud": round(float(distancias.min()), 4),
        }
        return estado_formateado, detalles

    def _obtener_datos(self, especie):
        clave = especie.strip().lower()
        if clave not in self._datos_por_especie:
            self._datos_por_especie[clave] = self.repositorio.cargar_datos_para_especie(
                especie, self.muestras_minimas
            )
        return self._datos_por_especie[clave]
