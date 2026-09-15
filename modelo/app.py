import os
import sys

from flask import Flask, jsonify, render_template, request, send_from_directory

from predictor_salud import PredictorSalud
from repositorio_datos import RepositorioDatos
from servicio_evaluacion import ServicioEvaluacion


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "modelo")
CONTROLLER_DIR = os.path.join(BASE_DIR, "controlador")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "vista", "templates"),
    static_folder=os.path.join(BASE_DIR, "vista", "static"),
)

repositorio = RepositorioDatos(
    os.path.join(MODEL_DIR, "especies.csv"),
    os.path.join(MODEL_DIR, "plant_health_cleaned.csv"),
)
servicio_evaluacion = ServicioEvaluacion(PredictorSalud(repositorio))


@app.route("/controlador.js")
def controlador_js():
    return send_from_directory(CONTROLLER_DIR, "controlador.js")


@app.route("/")
def index():
    return render_template("index.html", especies=repositorio.obtener_especies())


@app.route("/procesar", methods=["POST"])
def procesar():
    try:
        resultado = servicio_evaluacion.evaluar(request.get_json() or {})
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    print("=" * 55)
    print("[CONSOLA - CLASIFICACIÓN DE ESTADO MÁS CERCANO]")
    print(f"  • Especie evaluada : {resultado['datos_evaluados']['especie']}")
    print(f"  • Luminosidad      : {resultado['datos_evaluados']['luminosidad']} lm")
    print(f"  • Humedad          : {resultado['datos_evaluados']['humedad']} %")
    print(f"  • Temperatura      : {resultado['datos_evaluados']['temperatura']} °C")
    print(f"  ➔ CATEGORÍA DETECTADA: {resultado['categoria_estado']}")
    print("=" * 55)
    return jsonify({"success": True, **resultado})

if __name__ == "__main__":
    print("=" * 60)
    print("   SERVIDOR FLASK - EVALUADOR DE ESTADO DE SALUD VEGETAL")
    print("   Disponible en: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True)
