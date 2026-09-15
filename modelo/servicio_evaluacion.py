class ServicioEvaluacion:
    def __init__(self, predictor):
        self.predictor = predictor

    def evaluar(self, datos):
        especie = str(datos.get("especie", "")).strip()
        valores = {
            "luminosidad": datos.get("luminosidad"),
            "humedad": datos.get("humedad"),
            "temperatura": datos.get("temperatura"),
        }

        if not especie or any(valor is None for valor in valores.values()):
            raise ValueError(
                "Todos los campos son obligatorios: 'especie', 'luminosidad', "
                "'humedad' y 'temperatura'."
            )

        try:
            valores = {nombre: float(valor) for nombre, valor in valores.items()}
        except (ValueError, TypeError) as error:
            raise ValueError(
                "Los datos de luminosidad, humedad y temperatura deben ser numéricos."
            ) from error

        categoria, detalles = self.predictor.predecir(especie, **valores)
        return {
            "categoria_estado": categoria,
            "detalles": detalles,
            "datos_evaluados": {"especie": especie, **valores},
        }
