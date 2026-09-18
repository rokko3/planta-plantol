"""Punto de entrada de la API Flask. Responde exclusivamente JSON."""
from __future__ import annotations

import os
import sys

# Permite importar los paquetes Modelo y Controlador al ejecutar este archivo directamente
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from flask import Flask, jsonify, request
from flask_cors import CORS

from Modelo.evaluar_planta import EspecieNoSoportadaError, EvaluarPlanta, SolicitudDiagnostico
from Modelo.repositorio_csv import RepositorioEspeciesCSV
from Controlador.dtos import ErrorValidacion, parsear_solicitud

app = Flask(__name__)

# Permite peticiones desde el frontend estático alojado en otro origen
CORS(app, resources={r"/api/*": {"origins": "*"}})

ESPECIES_CSV = os.path.join(ROOT_DIR, "Modelo", "especies.csv")
repositorio = RepositorioEspeciesCSV(ESPECIES_CSV)
caso_uso = EvaluarPlanta(repositorio)


@app.route("/api/especies", methods=["GET"])
def listar_especies():
    especies = repositorio.listar_especies()
    return jsonify(
        [
            {
                "nombre": e.nombre,
                "rangos": {
                    "luminosidad": {"min": e.lux_min, "max": e.lux_max, "unidad": "lux"},
                    "humedad": {"min": e.humedad_min, "max": e.humedad_max, "unidad": "%"},
                    "temperatura": {"min": e.temperatura_min, "max": e.temperatura_max, "unidad": "°C"},
                },
            }
            for e in especies
        ]
    )


@app.route("/api/diagnostico", methods=["POST"])
def diagnostico():
    payload = request.get_json(silent=True) or {}

    try:
        especie, lux, humedad, temperatura = parsear_solicitud(payload)
    except ErrorValidacion as exc:
        return jsonify(exc.to_dict()), 400

    solicitud = SolicitudDiagnostico(
        especie=especie,
        luminosidad=lux,
        humedad=humedad,
        temperatura=temperatura,
    )

    try:
        diagnostico_resultado = caso_uso.ejecutar(solicitud)
    except EspecieNoSoportadaError as exc:
        return (
            jsonify(
                {
                    "error": "ESPECIE_NO_SOPORTADA",
                    "mensaje": str(exc),
                    "detalle": {"especie": exc.especie},
                }
            ),
            404,
        )

    return jsonify({"success": True, **diagnostico_resultado.to_dict()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
