"""
Punto de entrada principal para el servidor Flask de Plantol (Fase 2).
Delega al punto de composición en Controlador.app.
"""
import os
import sys

# Asegura que la raíz esté en sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from Controlador.app import app

if __name__ == "__main__":
    fuente = os.environ.get("TABLA_REFERENCIA", "csv")
    print("==================================================")
    print("Plantol - Arquitectura Hexagonal (Fase 2)")
    print(f"Fuente de tabla de referencia: {fuente.upper()}")
    print("Servidor disponible en http://127.0.0.1:5000")
    print("==================================================")
    app.run(host="0.0.0.0", port=5000, debug=True)
