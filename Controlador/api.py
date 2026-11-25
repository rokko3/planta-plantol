"""
Adaptadores de Entrada: API REST de Plantol (Flask).
Expone:
- Endpoints para el frontend asíncrono (Auth, Dashboard, Plantas, Especies, Diagnóstico manual)
- Endpoints para los dispositivos ESP32 / simulador (Token de dispositivo, Recepción de telemetría)
- Filtros/decoradores de autenticación JWT (Requisito R7) que aíslan la seguridad HTTP
  del dominio y entregan identidades limpias y verificadas.
"""
from __future__ import annotations

import datetime
from functools import wraps
import os
import socket
from typing import Optional

from flask import Blueprint, jsonify, request

from Modelo.entidades import (
    AccesoDenegadoPlantaError,
    DispositivoNoVinculadoError,
    EspecieNoSoportadaError,
    LecturaInvalidaError,
    PlantaNoEncontradaError,
    SaludoYaRealizadoHoyError,
)
from Modelo.puertos import (
    AutenticacionPort,
    ConsultarEstadoPort,
    EmisorTokenPort,
    GamificacionPort,
    GestionPlantasPort,
    RegistrarLecturaPort,
    RepositorioDispositivosPort,
    TablaReferenciaPort,
)


def obtener_ip_local() -> str:
    """Detecta la IP local en red LAN para permitir aprovisionamiento directo del ESP32."""
    host_env = os.environ.get("SERVER_HOST") or os.environ.get("HOST_IP")
    if host_env:
        return host_env.strip()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def crear_blueprint_api(
    caso_registrar_lectura: RegistrarLecturaPort,
    caso_consultar_estado: ConsultarEstadoPort,
    caso_gestion_plantas: GestionPlantasPort,
    caso_autenticacion: AutenticacionPort,
    tabla_referencia: TablaReferenciaPort,
    repo_dispositivos: RepositorioDispositivosPort,
    emisor_token: EmisorTokenPort,
    tipo_fuente_actual: str = "csv",
    caso_gamificacion: Optional[GamificacionPort] = None,
) -> Blueprint:
    """Crea y configura el Blueprint unificado de la API REST."""
    bp = Blueprint("api", __name__, url_prefix="/api")

    # =====================================================================
    # Decoradores de Seguridad JWT (Tecnología en infraestructura, R7)
    # =====================================================================

    def requiere_jwt_usuario(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header or not auth_header.startswith("Bearer "):
                return (
                    jsonify({
                        "error": "AUTENTICACION_REQUERIDA",
                        "mensaje": "Se requiere cabecera 'Authorization: Bearer <token_jwt_usuario>'",
                    }),
                    401,
                )
            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = emisor_token.verificar_token(token)
            except Exception:
                return (
                    jsonify({
                        "error": "TOKEN_INVALIDO",
                        "mensaje": "Token JWT de usuario inválido o expirado.",
                    }),
                    401,
                )

            if payload.get("scope") != "usuario":
                return (
                    jsonify({
                        "error": "ALCANCE_INVALIDO",
                        "mensaje": "El token presentado no corresponde a una identidad de usuario.",
                    }),
                    403,
                )

            try:
                usuario_id = int(payload.get("sub"))
            except (ValueError, TypeError):
                return jsonify({"error": "TOKEN_INVALIDO", "mensaje": "Identificador de usuario inválido en token."}), 401

            # Pasa al caso de uso únicamente la identidad limpia (usuario_id)
            return f(usuario_id=usuario_id, *args, **kwargs)

        return wrapper

    def requiere_jwt_dispositivo(f):
        @wraps(f)
        def wrapper(dispositivo_id: str, *args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header or not auth_header.startswith("Bearer "):
                return (
                    jsonify({
                        "error": "AUTENTICACION_DISPOSITIVO_REQUERIDA",
                        "mensaje": "Se requiere cabecera 'Authorization: Bearer <token_jwt_dispositivo>'",
                    }),
                    401,
                )

            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = emisor_token.verificar_token(token)
            except Exception:
                return (
                    jsonify({
                        "error": "TOKEN_DISPOSITIVO_INVALIDO",
                        "mensaje": "Token JWT de dispositivo inválido o expirado.",
                    }),
                    401,
                )

            # Valida alcance exclusivo de dispositivo (R7)
            if payload.get("scope") != "dispositivo":
                return (
                    jsonify({
                        "error": "ALCANCE_INVALIDO",
                        "mensaje": "El token presentado no posee alcance de dispositivo ('dispositivo').",
                    }),
                    403,
                )

            token_device_id = str(payload.get("sub", "")).strip().upper()
            solicitud_device_id = str(dispositivo_id).strip().upper()

            # Valida que el token corresponda exactamente al dispositivo que reporta
            if token_device_id != solicitud_device_id:
                return (
                    jsonify({
                        "error": "IDENTIDAD_NO_COINCIDE",
                        "mensaje": f"El token emitido para '{token_device_id}' no puede usarse para '{solicitud_device_id}'.",
                    }),
                    403,
                )

            return f(dispositivo_id=solicitud_device_id, *args, **kwargs)

        return wrapper

    # =====================================================================
    # Rutas de Autenticación de Usuario (R7)
    # =====================================================================

    @bp.route("/auth/register", methods=["POST"])
    def register():
        datos = request.get_json(silent=True) or {}
        username = datos.get("username", "").strip()
        password = datos.get("password", "").strip()
        nombre = datos.get("nombre", username).strip()
        email = datos.get("email", f"{username}@ejemplo.com").strip()

        if not username or not password:
            return jsonify({"error": "DATOS_INCOMPLETOS", "mensaje": "Se requiere 'username' y 'password'"}), 400

        try:
            usuario, token = caso_autenticacion.registrar_usuario(
                username=username, password=password, nombre=nombre, email=email
            )
            return (
                jsonify({
                    "mensaje": "Usuario registrado exitosamente",
                    "token": token,
                    "usuario": {
                        "id": usuario.id,
                        "username": usuario.username,
                        "nombre": usuario.nombre,
                        "email": usuario.email,
                        "rol": usuario.rol,
                    },
                }),
                201,
            )
        except ValueError as exc:
            return jsonify({"error": "REGISTRO_FALLIDO", "mensaje": str(exc)}), 400

    @bp.route("/auth/login", methods=["POST"])
    def login():
        datos = request.get_json(silent=True) or {}
        username = datos.get("username", "").strip()
        password = datos.get("password", "").strip()

        if not username or not password:
            return jsonify({"error": "DATOS_INCOMPLETOS", "mensaje": "Se requiere 'username' y 'password'"}), 400

        try:
            usuario, token = caso_autenticacion.iniciar_sesion(username=username, password=password)
            return jsonify({
                "mensaje": "Inicio de sesión exitoso",
                "token": token,
                "usuario": {
                    "id": usuario.id,
                    "username": usuario.username,
                    "nombre": usuario.nombre,
                    "email": usuario.email,
                    "rol": usuario.rol,
                },
            })
        except ValueError as exc:
            return jsonify({"error": "CREDENCIALES_INVALIDAS", "mensaje": str(exc)}), 401

    @bp.route("/auth/me", methods=["GET"])
    @requiere_jwt_usuario
    def me(usuario_id: int):
        return jsonify({"usuario_id": usuario_id, "estado": "autenticado"})

    # =====================================================================
    # Rutas de Configuración y Especies (R4)
    # =====================================================================

    @bp.route("/especies", methods=["GET"])
    def listar_especies():
        especies = tabla_referencia.listar_especies()
        return jsonify([
            {
                "nombre": e.nombre,
                "rangos": {
                    "luminosidad": {"min": e.lux_min, "max": e.lux_max, "unidad": "lux"},
                    "humedad": {"min": e.humedad_min, "max": e.humedad_max, "unidad": "%"},
                    "temperatura": {"min": e.temperatura_min, "max": e.temperatura_max, "unidad": "°C"},
                },
            }
            for e in especies
        ])

    @bp.route("/config/fuente", methods=["GET"])
    def fuente_actual():
        return jsonify({
            "fuente_referencia": tipo_fuente_actual,
            "descripcion": f"Tabla de referencia provista mediante {tipo_fuente_actual.upper()}",
        })

    # =====================================================================
    # Dashboard y Gestión de Plantas Asíncrono (R6, R7)
    # =====================================================================

    @bp.route("/dashboard", methods=["GET"])
    @requiere_jwt_usuario
    def dashboard(usuario_id: int):
        resumen = caso_consultar_estado.consultar_resumen_dashboard(usuario_id=usuario_id)
        return jsonify(resumen)

    @bp.route("/plantas", methods=["GET"])
    @requiere_jwt_usuario
    def listar_plantas(usuario_id: int):
        plantas = caso_consultar_estado.consultar_plantas_usuario(usuario_id=usuario_id)
        return jsonify(plantas)

    @bp.route("/plantas", methods=["POST"])
    @requiere_jwt_usuario
    def crear_planta(usuario_id: int):
        payload = request.get_json(silent=True) or {}
        nombre = payload.get("nombre", "").strip()
        especie = payload.get("especie", "").strip()
        ubicacion = payload.get("ubicacion", "").strip()
        dispositivo_id = payload.get("dispositivo_id")

        if not nombre or not especie:
            return jsonify({"error": "DATOS_INCOMPLETOS", "mensaje": "Se requiere 'nombre' y 'especie'"}), 400

        try:
            planta = caso_gestion_plantas.crear_planta(
                usuario_id=usuario_id,
                nombre=nombre,
                especie=especie,
                ubicacion=ubicacion,
                dispositivo_id=dispositivo_id,
            )
            return jsonify({
                "mensaje": "Planta creada con éxito",
                "planta": {
                    "id": planta.id,
                    "nombre": planta.nombre,
                    "especie": planta.especie,
                    "ubicacion": planta.ubicacion,
                    "dispositivo_id": planta.dispositivo_id,
                },
            }), 201
        except EspecieNoSoportadaError as exc:
            return jsonify({"error": "ESPECIE_NO_SOPORTADA", "mensaje": str(exc)}), 400

    @bp.route("/plantas/<int:planta_id>", methods=["GET"])
    @requiere_jwt_usuario
    def detalle_planta(usuario_id: int, planta_id: int):
        try:
            detalle = caso_consultar_estado.consultar_estado_planta(usuario_id=usuario_id, planta_id=planta_id)
            return jsonify(detalle)
        except AccesoDenegadoPlantaError as exc:
            return jsonify({"error": "ACCESO_DENEGADO", "mensaje": str(exc)}), 403
        except PlantaNoEncontradaError as exc:
            return jsonify({"error": "NO_ENCONTRADA", "mensaje": str(exc)}), 404

    @bp.route("/plantas/<int:planta_id>/historial", methods=["GET"])
    @requiere_jwt_usuario
    def historial_planta(usuario_id: int, planta_id: int):
        try:
            detalle = caso_consultar_estado.consultar_estado_planta(usuario_id=usuario_id, planta_id=planta_id)
            return jsonify(detalle.get("historial", []))
        except AccesoDenegadoPlantaError as exc:
            return jsonify({"error": "ACCESO_DENEGADO", "mensaje": str(exc)}), 403
        except PlantaNoEncontradaError as exc:
            return jsonify({"error": "NO_ENCONTRADA", "mensaje": str(exc)}), 404

    @bp.route("/plantas/<int:planta_id>", methods=["DELETE"])
    @bp.route("/plantas/<int:planta_id>/eliminar", methods=["POST"])
    @requiere_jwt_usuario
    def eliminar_planta(usuario_id: int, planta_id: int):
        try:
            exito = caso_gestion_plantas.eliminar_planta(usuario_id=usuario_id, planta_id=planta_id)
            if not exito:
                return jsonify({"error": "ELIMINACION_FALLIDA", "mensaje": "No se pudo eliminar la planta solicitada."}), 400

            return jsonify({
                "success": True,
                "mensaje": f"Planta {planta_id} eliminada exitosamente. Su sensor fue desvinculado y liberado en la red.",
                "planta_id": planta_id,
            })
        except AccesoDenegadoPlantaError as exc:
            return jsonify({"error": "ACCESO_DENEGADO", "mensaje": str(exc)}), 403
        except PlantaNoEncontradaError as exc:
            return jsonify({"error": "NO_ENCONTRADA", "mensaje": str(exc)}), 404

    # =====================================================================
    # Dispositivos, Aprovisionamiento BLE/GATT y Vinculación en Red
    # =====================================================================

    @bp.route("/dispositivos", methods=["GET"])
    @requiere_jwt_usuario
    def listar_dispositivos(usuario_id: int):
        dispositivos = repo_dispositivos.listar_dispositivos()
        return jsonify([
            {
                "id": d.id,
                "mac": d.mac,
                "planta_id": d.planta_id,
                "disponible": d.planta_id is None or d.planta_id == 0,
                "ultimo_contacto": d.ultimo_contacto,
                "estado_conexion": d.estado_conexion,
            }
            for d in dispositivos
        ])

    # =====================================================================
    # Rutas de Información del Servidor y Aprovisionamiento
    # =====================================================================

    @bp.route("/servidor/info", methods=["GET"])
    def info_servidor():
        """
        Informa la IP local LAN y el puerto del servidor Flask para que
        el frontend Web Bluetooth pueda configurar el host del backend en el
        ESP32 de forma 100% automática, sin manipulación técnica del usuario.
        """
        req_host = request.host.split(":")[0] if request.host else ""
        if req_host and req_host not in ("localhost", "127.0.0.1"):
            ip = req_host
        else:
            ip = obtener_ip_local()
        puerto = int(os.environ.get("PORT", 5000))
        return jsonify({
            "ip": ip,
            "puerto": puerto,
            "host_sugerido": f"http://{ip}:{puerto}",
            "estado": "ACTIVO",
        }), 200

    @bp.route("/dispositivos/generar-token-pairing", methods=["POST"])
    @requiere_jwt_usuario
    def generar_token_pairing(usuario_id: int):
        token = f"PAIR-{os.urandom(4).hex().upper()}"
        repo_dispositivos.guardar_token_pairing(token, usuario_id)
        return jsonify({"success": True, "token": token}), 200

    @bp.route("/dispositivos/reclamar", methods=["POST"])
    def reclamar_dispositivo():
        """
        Endpoint invocado directamente por el microcontrolador ESP32 tras conectarse a Wi-Fi.
        Exige el token de emparejamiento emitido durante la sesión BLE del usuario.
        Evita que cualquier dispositivo ajeno se vincule conociendo solo una MAC.
        """
        payload = request.get_json(silent=True) or {}
        mac = payload.get("mac", "").strip().upper()
        token = payload.get("token", "").strip().upper()

        if not mac:
            return jsonify({"error": "MAC_REQUERIDA", "mensaje": "Se requiere el parámetro 'mac'"}), 400

        if not token or not repo_dispositivos.validar_y_consumir_token_pairing(token):
            return (
                jsonify({
                    "error": "TOKEN_PAIRING_INVALIDO",
                    "mensaje": "Se requiere un token de emparejamiento válido emitido por la sesión del usuario.",
                }),
                401,
            )

        dev = repo_dispositivos.registrar_o_conectar_dispositivo(
            dispositivo_id=mac, mac=mac, liberar_planta=True
        )
        return jsonify({
            "success": True,
            "mensaje": f"Dispositivo {mac} registrado y en línea exitosamente.",
            "dispositivo_id": dev.id,
            "mac": dev.mac,
        }), 200

    @bp.route("/dispositivos/disponibles", methods=["GET"])
    @requiere_jwt_usuario
    def listar_dispositivos_disponibles(usuario_id: int):
        """
        Retorna los dispositivos ESP32 presentes en la red y listos para agregar o vincular a una planta.
        """
        disponibles = repo_dispositivos.listar_dispositivos_disponibles()
        return jsonify([
            {
                "id": d.id,
                "mac": d.mac,
                "estado_conexion": d.estado_conexion,
                "ultimo_contacto": d.ultimo_contacto,
            }
            for d in disponibles
        ])

    @bp.route("/dispositivos/codigo", methods=["POST"])
    @requiere_jwt_usuario
    def generar_codigo(usuario_id: int):
        payload = request.get_json(silent=True) or {}
        dispositivo_id = payload.get("dispositivo_id", "").strip().upper()
        if not dispositivo_id:
            return jsonify({"error": "DISPOSITIVO_REQUERIDO", "mensaje": "Se requiere 'dispositivo_id'"}), 400

        codigo = repo_dispositivos.generar_codigo_vinculacion(dispositivo_id)
        return jsonify({
            "dispositivo_id": dispositivo_id,
            "codigo_temporal": codigo,
            "mensaje": f"Código temporal de vinculación generado para {dispositivo_id}.",
        })

    @bp.route("/dispositivos/vincular", methods=["POST"])
    @requiere_jwt_usuario
    def vincular(usuario_id: int):
        payload = request.get_json(silent=True) or {}
        planta_id = payload.get("planta_id")
        dispositivo_id = payload.get("dispositivo_id", "").strip().upper()
        codigo = payload.get("codigo")
        if codigo:
            codigo = codigo.strip().upper()

        if not planta_id or not dispositivo_id:
            return jsonify({"error": "DATOS_INCOMPLETOS", "mensaje": "Se requiere 'planta_id' y 'dispositivo_id'"}), 400

        try:
            exito = caso_gestion_plantas.vincular_dispositivo(
                usuario_id=usuario_id,
                planta_id=int(planta_id),
                dispositivo_id=dispositivo_id,
                codigo_vinculacion=codigo,
            )
            if not exito:
                return jsonify({"error": "VINCULACION_FALLIDA", "mensaje": "No se pudo vincular el dispositivo a la planta."}), 400

            return jsonify({
                "success": True,
                "mensaje": f"Dispositivo {dispositivo_id} vinculado correctamente a la planta {planta_id}.",
                "dispositivo_id": dispositivo_id,
                "planta_id": planta_id,
            })
        except AccesoDenegadoPlantaError as exc:
            return jsonify({"error": "ACCESO_DENEGADO", "mensaje": str(exc)}), 403
        except PlantaNoEncontradaError as exc:
            return jsonify({"error": "PLANTA_NO_ENCONTRADA", "mensaje": str(exc)}), 404

    @bp.route("/dispositivos/desvincular", methods=["POST"])
    @requiere_jwt_usuario
    def desvincular(usuario_id: int):
        payload = request.get_json(silent=True) or {}
        planta_id = payload.get("planta_id")
        dispositivo_id = payload.get("dispositivo_id")

        if not planta_id and not dispositivo_id:
            return jsonify({"error": "DATOS_INCOMPLETOS", "mensaje": "Se requiere 'planta_id' o 'dispositivo_id'"}), 400

        if not planta_id and dispositivo_id:
            dev = repo_dispositivos.buscar_por_id(str(dispositivo_id).strip().upper())
            if not dev or not dev.planta_id:
                return jsonify({"error": "DISPOSITIVO_NO_VINCULADO", "mensaje": f"El dispositivo {dispositivo_id} no está vinculado a ninguna planta."}), 400
            planta_id = dev.planta_id

        try:
            exito = caso_gestion_plantas.desvincular_dispositivo(
                usuario_id=usuario_id,
                planta_id=int(planta_id),
            )
            if not exito:
                return jsonify({"error": "DESVINCULACION_FALLIDA", "mensaje": "La planta no tiene ningún sensor vinculado."}), 400

            return jsonify({
                "success": True,
                "mensaje": f"Sensor desvinculado con éxito de la planta {planta_id}. Ahora está libre y disponible en la red.",
                "planta_id": planta_id,
            })
        except AccesoDenegadoPlantaError as exc:
            return jsonify({"error": "ACCESO_DENEGADO", "mensaje": str(exc)}), 403
        except PlantaNoEncontradaError as exc:
            return jsonify({"error": "PLANTA_NO_ENCONTRADA", "mensaje": str(exc)}), 404

    @bp.route("/dispositivos/<dispositivo_id>/token", methods=["POST", "GET"])
    def obtener_token_dispositivo(dispositivo_id: str):
        """
        Emite el token JWT para un ESP32 o simulador.
        Alcance restringido exclusivamente a 'dispositivo'.
        """
        dev = repo_dispositivos.buscar_por_id(dispositivo_id)
        if not dev:
            return jsonify({"error": "DISPOSITIVO_NO_REGISTRADO", "mensaje": f"El dispositivo {dispositivo_id} no está registrado."}), 404

        token = emisor_token.emitir_token_dispositivo(dispositivo_id)
        return jsonify({
            "dispositivo_id": dev.id,
            "scope": "dispositivo",
            "token": token,
            "instrucciones": "Envía este token en la cabecera 'Authorization: Bearer <token>' en cada POST de telemetría.",
        })

    # =====================================================================
    # Endpoint de Recepción de Lecturas ESP32 (Requisitos R2 y R7)
    # =====================================================================

    @bp.route("/dispositivos/<dispositivo_id>/lecturas", methods=["POST"])
    @requiere_jwt_dispositivo
    def reportar_lectura(dispositivo_id: str):
        payload = request.get_json(silent=True) or {}

        # Marca de tiempo: provista por el sensor o generada por el servidor
        timestamp = payload.get("timestamp") or datetime.datetime.now().isoformat()

        # Soporta claves en español o inglés comunes en telemetría IoT
        raw_lux = payload.get("luminosidad") if "luminosidad" in payload else payload.get("lux")
        raw_hum = payload.get("humedad") if "humedad" in payload else payload.get("humidity")
        raw_temp = payload.get("temperatura") if "temperatura" in payload else payload.get("temperature")
        raw_suelo = payload.get("humedad_suelo") if "humedad_suelo" in payload else payload.get("suelo")

        if raw_lux is None or raw_hum is None or raw_temp is None:
            return (
                jsonify({
                    "error": "CAMPOS_FALTANTES",
                    "mensaje": "Cada lectura debe incluir 'luminosidad', 'humedad' y 'temperatura'.",
                }),
                400,
            )

        try:
            lux = float(raw_lux)
            humedad = float(raw_hum)
            temp = float(raw_temp)
            hum_suelo = float(raw_suelo) if raw_suelo is not None else None
        except (ValueError, TypeError):
            return (
                jsonify({
                    "error": "FORMATO_NUMERICO_INVALIDO",
                    "mensaje": "Los valores de luminosidad, humedad y temperatura deben ser numéricos.",
                    "recibido": {"luminosidad": raw_lux, "humedad": raw_hum, "temperatura": raw_temp},
                }),
                400,
            )

        try:
            # Invoca el caso de uso del dominio a través de su puerto de entrada
            diagnostico = caso_registrar_lectura.registrar(
                dispositivo_id=dispositivo_id,
                timestamp=str(timestamp),
                luminosidad=lux,
                humedad=humedad,
                temperatura=temp,
                humedad_suelo=hum_suelo,
            )

            return (
                jsonify({
                    "success": True,
                    "mensaje": "Lectura registrada y evaluada con éxito",
                    "dispositivo_id": dispositivo_id,
                    "timestamp": timestamp,
                    "lectura": {
                        "luminosidad": lux,
                        "humedad": humedad,
                        "temperatura": temp,
                        "humedad_suelo": hum_suelo,
                    },
                    "diagnostico": diagnostico.to_dict(),
                }),
                201,
            )

        except LecturaInvalidaError as exc:
            return (
                jsonify({
                    "error": "LECTURA_INVALIDA",
                    "mensaje": str(exc),
                    "dispositivo_id": dispositivo_id,
                }),
                400,
            )

        except DispositivoNoVinculadoError as exc:
            return (
                jsonify({
                    "aviso": "DISPOSITIVO_NO_VINCULADO",
                    "mensaje": str(exc),
                    "dispositivo_id": dispositivo_id,
                }),
                202,
            )

        except EspecieNoSoportadaError as exc:
            return (
                jsonify({
                    "error": "ESPECIE_NO_SOPORTADA",
                    "mensaje": str(exc),
                }),
                400,
            )

    # =====================================================================
    # Rutas de Gamificación (Puntos, Saludos, Recompensas)
    # =====================================================================

    @bp.route("/plantas/<int:planta_id>/saludar", methods=["POST"])
    @requiere_jwt_usuario
    def saludar_planta(usuario_id: int, planta_id: int):
        if not caso_gamificacion:
            return jsonify({"error": "MODULO_NO_DISPONIBLE", "mensaje": "Gamificación no inicializada."}), 503

        try:
            resultado = caso_gamificacion.saludar_planta(usuario_id=usuario_id, planta_id=planta_id)
            return jsonify({
                "success": True,
                **resultado,
            }), 200
        except SaludoYaRealizadoHoyError as exc:
            return jsonify({"error": "SALUDO_YA_REALIZADO", "mensaje": str(exc)}), 400
        except AccesoDenegadoPlantaError as exc:
            return jsonify({"error": "ACCESO_DENEGADO", "mensaje": str(exc)}), 403
        except PlantaNoEncontradaError as exc:
            return jsonify({"error": "PLANTA_NO_ENCONTRADA", "mensaje": str(exc)}), 404

    @bp.route("/gamificacion/puntos", methods=["GET"])
    @requiere_jwt_usuario
    def consultar_puntos(usuario_id: int):
        if not caso_gamificacion:
            return jsonify({"saldo_puntos": 0}), 200
        saldo = caso_gamificacion.consultar_saldo(usuario_id)
        return jsonify({
            "usuario_id": usuario_id,
            "saldo_puntos": saldo,
        }), 200

    @bp.route("/gamificacion/historial", methods=["GET"])
    @requiere_jwt_usuario
    def consultar_historial_puntos(usuario_id: int):
        if not caso_gamificacion:
            return jsonify({"historial": []}), 200
        limite = request.args.get("limite", 50, type=int)
        historial = caso_gamificacion.consultar_historial_puntos(usuario_id, limite=limite)
        saldo = caso_gamificacion.consultar_saldo(usuario_id)
        return jsonify({
            "usuario_id": usuario_id,
            "saldo_puntos": saldo,
            "historial": historial,
        }), 200

    return bp

