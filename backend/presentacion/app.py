"""
app.py — punto de entrada Flask.

IMPORTANTE: este archivo NO genera HTML (RA1).
Todas las rutas devuelven exclusivamente JSON.
El frontend es servido por separado (RA2).
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Ajuste de path para importaciones relativas al directorio 'backend/'
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))  # .../planta-plantol/backend
sys.path.insert(0, BACKEND_DIR)

from flask import Flask, jsonify, request
from flask_cors import CORS

from aplicacion.evaluar_planta import EspecieNoSoportadaError, EvaluarPlanta, SolicitudDiagnostico
from infraestructura.repositorio_csv import RepositorioEspeciesCSV
from presentacion.dtos import ErrorValidacion, parsear_solicitud

# ---------------------------------------------------------------------------
# Inicialización de la aplicación y dependencias
# ---------------------------------------------------------------------------
app = Flask(__name__)

# RA7: CORS para que el front servido en otro origen pueda consumir la API
CORS(app, resources={r"/api/*": {"origins": "*"}})

ESPECIES_CSV = os.path.join(BACKEND_DIR, "especies.csv")
repositorio = RepositorioEspeciesCSV(ESPECIES_CSV)
caso_uso = EvaluarPlanta(repositorio)


# ---------------------------------------------------------------------------
# Rutas — solo JSON, nunca render_template (RA1)
# ---------------------------------------------------------------------------

@app.route("/api/especies", methods=["GET"])
def listar_especies():
    """RF5: devuelve la lista de especies soportadas y sus rangos."""
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
    """RF1-RF4: recibe parámetros, devuelve diagnóstico completo con recomendaciones."""
    payload = request.get_json(silent=True) or {}

    # RA6: parsear transforma el dict crudo en datos validados antes del caso de uso
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
# Arranque
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("   BACKEND — Evaluador de Estado de Salud Vegetal")
    print("   API disponible en: http://127.0.0.1:5000")
    print("   Front: sirve frontend/ con 'python -m http.server 8080'")
    print("=" * 60)
    app.run(debug=True, port=5000)
