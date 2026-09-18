"""
app.py — Punto de entrada del backend Flask (Controlador / Presentación).

IMPORTANTE (RA1): Este archivo responde EXCLUSIVAMENTE con JSON.
No usa render_template ni genera HTML.
El frontend se sirve por separado desde un origen estático (RA2).
"""
from __future__ import annotations

import os
import sys

# Ajuste de path para importar paquetes raíz (Modelo, Controlador)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from flask import Flask, jsonify, request
from flask_cors import CORS

from Modelo.evaluar_planta import EspecieNoSoportadaError, EvaluarPlanta, SolicitudDiagnostico
from Modelo.repositorio_csv import RepositorioEspeciesCSV
from Controlador.dtos import ErrorValidacion, parsear_solicitud

# ---------------------------------------------------------------------------
# Inicialización de la aplicación y dependencias
# ---------------------------------------------------------------------------
app = Flask(__name__)

# RA7: CORS habilitado para que el frontend en otro origen consuma la API
CORS(app, resources={r"/api/*": {"origins": "*"}})

ESPECIES_CSV = os.path.join(ROOT_DIR, "Modelo", "especies.csv")
repositorio = RepositorioEspeciesCSV(ESPECIES_CSV)
caso_uso = EvaluarPlanta(repositorio)


# ---------------------------------------------------------------------------
# Endpoints de la API — Solo JSON (RA1)
# ---------------------------------------------------------------------------

@app.route("/api/especies", methods=["GET"])
def listar_especies():
    """RF5: Devuelve la lista de especies soportadas y sus rangos óptimos."""
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
    """RF1-RF4: Recibe parámetros, valida y retorna diagnóstico con recomendaciones."""
    payload = request.get_json(silent=True) or {}

    # RA6: parsear transforma el dict crudo en valores validados antes del caso de uso
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


# ---------------------------------------------------------------------------
# Arranque directo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("   CONTROLADOR BACKEND — Planta-Plantol")
    print("   API disponible en: http://127.0.0.1:5000")
    print("   Endpoints:")
    print("     GET  /api/especies")
    print("     POST /api/diagnostico")
    print("=" * 60)
    app.run(debug=True, port=5000)
