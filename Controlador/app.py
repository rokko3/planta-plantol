"""
Punto de Composición y Servidor Flask de Plantol (Controlador).
Este módulo actúa como Composition Root de la Arquitectura Hexagonal:
- Lee configuración de entorno (ej. TABLA_REFERENCIA=csv|bd).
- Instancia los adaptadores de salida concretos (SQLite, CSV, PyJWT).
- Instancia las reglas de negocio y casos de uso del dominio.
- Ensambla y registra el adaptador de entrada (API REST Flask).
- Sirve la interfaz gráfica web estática (Vista).
"""
from __future__ import annotations

import datetime
import os
import sys

# Asegura que la raíz del proyecto esté en el PYTHONPATH
RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ_PROYECTO not in sys.path:
    sys.path.insert(0, RAIZ_PROYECTO)

from flask import Flask, send_from_directory
from flask_cors import CORS

from Controlador.api import crear_blueprint_api
from Controlador.persistencia import (
    HistorialLecturasBD,
    RepositorioSQLite,
    ServicioJWT,
    TablaReferenciaBD,
    TablaReferenciaCSV,
)
from Modelo.entidades import CONECTADO, Dispositivo, Lectura, Planta, SIN_RESPUESTA, Usuario
from Modelo.negocio import (
    CasoUsoAutenticacion,
    CasoUsoConsultarEstado,
    CasoUsoEvaluarPlantaManual,
    CasoUsoGestionPlantas,
    CasoUsoRegistrarLectura,
    ValidadorDeEstado,
)


def sembrar_datos_iniciales(
    repo_sqlite: RepositorioSQLite,
    historial_bd: HistorialLecturasBD,
    validador: ValidadorDeEstado,
    tabla_ref,
    caso_auth: CasoUsoAutenticacion,
) -> None:
    """Siembra datos iniciales de demostración coherentes con el diseño si la BD está vacía."""
    # 1. Usuario demostración 'felipe'
    usuario_existente = repo_sqlite.buscar_por_username("felipe")
    if not usuario_existente:
        pwd_hash = caso_auth._hash_password("plantol123")
        usuario = repo_sqlite.guardar_usuario(
            Usuario(
                id=0,
                username="felipe",
                password_hash=pwd_hash,
                nombre="Felipe Morales",
                email="felipe@ejemplo.com",
            )
        )
    else:
        usuario = usuario_existente

    # 2. Dispositivos ESP32 registrados
    dispositivos_base = [
        ("ESP32-A7F9", "A4:CF:12:8B:30:91", CONECTADO),
        ("ESP32-C204", "7C:DF:A1:21:C2:04", CONECTADO),
        ("ESP32-91B2", "30:AE:A4:10:91:B2", CONECTADO),
        ("ESP32-6D30", "84:CC:A8:2E:6D:30", SIN_RESPUESTA),
    ]
    for dev_id, mac, estado in dispositivos_base:
        if not repo_sqlite.buscar_por_id(dev_id):
            repo_sqlite.guardar_dispositivo(
                Dispositivo(
                    id=dev_id,
                    secret_hash="secret_hash_demo",
                    mac=mac,
                    ultimo_contacto=datetime.datetime.now().isoformat(),
                    estado_conexion=estado,
                )
            )

    # 3. Plantas del usuario si aún no tiene registradas
    plantas_usuario = repo_sqlite.listar_por_usuario(usuario.id)
    if not plantas_usuario:
        p1 = repo_sqlite.guardar_planta(
            Planta(0, "Cactus de escritorio", "Cactus (Cactaceae)", usuario.id, "ESP32-A7F9", "SALA · MACETA 01")
        )
        p2 = repo_sqlite.guardar_planta(
            Planta(0, "Helecho de la ventana", "Helecho (Nephrolepis)", usuario.id, "ESP32-C204", "ESTUDIO · MACETA 02")
        )
        p3 = repo_sqlite.guardar_planta(
            Planta(0, "Orquídea morada", "Orquídea (Orchidaceae)", usuario.id, "ESP32-91B2", "BALCÓN · MACETA 03")
        )
        p4 = repo_sqlite.guardar_planta(
            Planta(0, "Monstera pequeña", "Monstera (Monstera deliciosa)", usuario.id, "ESP32-6D30", "COCINA · MACETA 04")
        )

        # 4. Lecturas iniciales para telemetría inicial realista
        lecturas_mockup = [
            (p1, "ESP32-A7F9", 7000.0, 22.0, 25.0),
            (p2, "ESP32-C204", 4500.0, 68.0, 22.0),
            (p3, "ESP32-91B2", 2000.0, 62.0, 24.0),
            (p4, "ESP32-6D30", 5000.0, 65.0, 23.0),
        ]
        ahora = datetime.datetime.now().isoformat()
        for planta, dev_id, lux, hum, temp in lecturas_mockup:
            rangos = tabla_ref.obtener_rangos(planta.especie)
            diag = validador.evaluar(planta.especie, rangos, lux, hum, temp, ahora) if rangos else None
            historial_bd.guardar_lectura(
                Lectura(
                    dispositivo_id=dev_id,
                    timestamp=ahora,
                    luminosidad=lux,
                    humedad=hum,
                    temperatura=temp,
                    planta_id=planta.id,
                ),
                diag,
            )


def crear_app(
    tipo_tabla: str = None,
    ruta_db: str = None,
    ruta_csv: str = None,
    secret_key: str = None,
) -> Flask:
    """
    Fábrica de composición. Ensambla adaptadores con puertos según configuración.
    """
    # 1. Configuración de rutas (Ruta absoluta calculada desde la raíz del proyecto)
    if ruta_db is None:
        carpeta_data = os.path.join(RAIZ_PROYECTO, "data")
        os.makedirs(carpeta_data, exist_ok=True)
        ruta_db_default = os.path.join(carpeta_data, "matera.db")

        # Migración segura: si existe matera.db en la raíz y no en data/, trasladar sin pérdida
        ruta_db_raiz = os.path.join(RAIZ_PROYECTO, "matera.db")
        if os.path.exists(ruta_db_raiz) and not os.path.exists(ruta_db_default):
            import shutil
            shutil.move(ruta_db_raiz, ruta_db_default)

        ruta_db = os.environ.get("DB_PATH", ruta_db_default)
    else:
        dir_padre = os.path.dirname(os.path.abspath(ruta_db))
        if dir_padre:
            os.makedirs(dir_padre, exist_ok=True)

    if ruta_csv is None:
        ruta_csv = os.environ.get("CSV_PATH", os.path.join(RAIZ_PROYECTO, "especies.csv"))
        if not os.path.exists(ruta_csv):
            ruta_csv = os.path.join(RAIZ_PROYECTO, "Modelo", "especies.csv")

    # 2. Selección de implementación de TablaReferenciaPort (Requisito R4)
    if tipo_tabla is None:
        tipo_tabla = os.environ.get("TABLA_REFERENCIA", "csv").lower().strip()

    if tipo_tabla == "bd":
        tabla_referencia = TablaReferenciaBD(ruta_db=ruta_db)
    else:
        tipo_tabla = "csv"
        tabla_referencia = TablaReferenciaCSV(ruta_csv=ruta_csv)

    # 3. Adaptadores de salida
    historial_lecturas = HistorialLecturasBD(ruta_db=ruta_db)
    repositorio_sqlite = RepositorioSQLite(ruta_db=ruta_db)
    emisor_token = ServicioJWT(clave_secreta=secret_key or "plantol_super_secret_key_2026_arquitectura_hexagonal_segura_32b")

    # 4. Dominio puro y casos de uso (Puertos de entrada)
    validador_estado = ValidadorDeEstado()

    caso_registrar_lectura = CasoUsoRegistrarLectura(
        validador=validador_estado,
        tabla_referencia=tabla_referencia,
        repo_plantas=repositorio_sqlite,
        repo_dispositivos=repositorio_sqlite,
        historial_lecturas=historial_lecturas,
    )
    caso_consultar_estado = CasoUsoConsultarEstado(
        validador=validador_estado,
        repo_plantas=repositorio_sqlite,
        historial_lecturas=historial_lecturas,
        repo_dispositivos=repositorio_sqlite,
    )
    caso_evaluar_manual = CasoUsoEvaluarPlantaManual(
        validador=validador_estado,
        tabla_referencia=tabla_referencia,
    )
    caso_gestion_plantas = CasoUsoGestionPlantas(
        validador=validador_estado,
        repo_plantas=repositorio_sqlite,
        repo_dispositivos=repositorio_sqlite,
        tabla_referencia=tabla_referencia,
    )
    caso_autenticacion = CasoUsoAutenticacion(
        repo_usuarios=repositorio_sqlite,
        emisor_token=emisor_token,
    )

    # 5. Siembra de datos iniciales
    sembrar_datos_iniciales(
        repo_sqlite=repositorio_sqlite,
        historial_bd=historial_lecturas,
        validador=validador_estado,
        tabla_ref=tabla_referencia,
        caso_auth=caso_autenticacion,
    )

    # 6. Adaptador de entrada: API REST
    bp_api = crear_blueprint_api(
        caso_registrar_lectura=caso_registrar_lectura,
        caso_consultar_estado=caso_consultar_estado,
        caso_evaluar_manual=caso_evaluar_manual,
        caso_gestion_plantas=caso_gestion_plantas,
        caso_autenticacion=caso_autenticacion,
        tabla_referencia=tabla_referencia,
        repo_dispositivos=repositorio_sqlite,
        emisor_token=emisor_token,
        tipo_fuente_actual=tipo_tabla,
    )

    # 7. Configuración de Flask y Frontend (Vista)
    carpeta_vista = os.path.join(RAIZ_PROYECTO, "Vista")
    app = Flask(__name__, static_folder=carpeta_vista, static_url_path="")
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.register_blueprint(bp_api)

    @app.route("/")
    def index():
        return send_from_directory(carpeta_vista, "index.html")

    @app.route("/<path:path>")
    def archivos_estaticos(path):
        if os.path.exists(os.path.join(carpeta_vista, path)):
            return send_from_directory(carpeta_vista, path)
        return send_from_directory(carpeta_vista, "index.html")

    return app


app = crear_app()

if __name__ == "__main__":
    fuente = os.environ.get("TABLA_REFERENCIA", "csv")
    print("==================================================")
    print("Plantol - Arquitectura Hexagonal (Fase 2)")
    print(f"Fuente de tabla de referencia: {fuente.upper()}")
    print("Servidor disponible en http://127.0.0.1:5000")
    print("==================================================")
    app.run(host="0.0.0.0", port=5000, debug=True)
