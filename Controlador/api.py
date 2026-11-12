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
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from Modelo.entidades import (
    AccesoDenegadoPlantaError,
    DispositivoNoVinculadoError,
    EspecieNoSoportadaError,
    LecturaInvalidaError,
    PlantaNoEncontradaError,
)
from Modelo.puertos import (
    AutenticacionPort,
    ConsultarEstadoPort,
    EmisorTokenPort,
    GestionPlantasPort,
    RegistrarLecturaPort,
    RepositorioDispositivosPort,
    TablaReferenciaPort,
)


def crear_blueprint_api(
    caso_registrar_lectura: RegistrarLecturaPort,
    caso_consultar_estado: ConsultarEstadoPort,
    caso_gestion_plantas: GestionPlantasPort,
    caso_autenticacion: AutenticacionPort,
    tabla_referencia: TablaReferenciaPort,
    repo_dispositivos: RepositorioDispositivosPort,
    emisor_token: EmisorTokenPort,
    tipo_fuente_actual: str = "csv",
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

    @bp.route("/dispositivos/bluetooth", methods=["GET"])
    @requiere_jwt_usuario
    def escanear_bluetooth(usuario_id: int):
        """
        Simula el escaneo BLE de dispositivos ESP32 en las inmediaciones.
        Permite al usuario ver los dispositivos físicos a su alrededor.
        """
        dispositivos_bd = repo_dispositivos.listar_dispositivos()
        candidatos = [d.id for d in dispositivos_bd]
        for extra in ["ESP32-B8E1", "ESP32-F41A"]:
            if extra not in candidatos:
                candidatos.append(extra)

        resultado = []
        for idx, dev_id in enumerate(candidatos):
            rssi = -48 - (idx * 7)
            dev_bd = repo_dispositivos.buscar_por_id(dev_id)
            vinculado = (dev_bd.planta_id is not None and dev_bd.planta_id != 0) if dev_bd else False
            resultado.append({
                "id": dev_id,
                "nombre_ble": f"Plantol-ESP32-{dev_id.split('-')[-1]}",
                "mac": dev_bd.mac if (dev_bd and dev_bd.mac) else f"24:6F:28:FE:{dev_id[-4:]}",
                "rssi": f"{rssi} dBm",
                "vinculado": vinculado,
                "estado_ble": "Enlazado a planta" if vinculado else "Disponible para conectar",
            })
        return jsonify(resultado)

    @bp.route("/dispositivos/gatt-provisionar", methods=["POST"])
    @requiere_jwt_usuario
    def provisionar_gatt(usuario_id: int):
        """
        Aprovisionamiento Wi-Fi mediante conexión Bluetooth GATT.
        El usuario envía las credenciales de la red (SSID y Password) al ESP32.
        El ESP32 se conecta a la red Wi-Fi y queda en la red listo para agregar.
        """
        payload = request.get_json(silent=True) or {}
        dispositivo_id = payload.get("dispositivo_id", "").strip().upper()
        ssid = payload.get("ssid", "").strip()
        password = payload.get("password", "").strip()

        if not dispositivo_id or not ssid:
            return jsonify({"error": "DATOS_INCOMPLETOS", "mensaje": "Se requiere 'dispositivo_id' y 'ssid'"}), 400

        dev = repo_dispositivos.registrar_o_conectar_dispositivo(dispositivo_id=dispositivo_id, red_wifi=ssid)

        return jsonify({
            "success": True,
            "mensaje": f"Credenciales Wi-Fi transmitidas mediante característica GATT. Dispositivo {dispositivo_id} conectado a la red '{ssid}' y disponible para agregar.",
            "dispositivo": {
                "id": dev.id,
                "mac": dev.mac,
                "estado_conexion": dev.estado_conexion,
                "red_wifi": ssid,
            },
        })

    @bp.route("/dispositivos/generar-token-pairing", methods=["POST"])
    @requiere_jwt_usuario
    def generar_token_pairing(usuario_id: int):
        token = f"PAIR-{os.urandom(4).hex().upper()}"
        return jsonify({"success": True, "token": token}), 200

    @bp.route("/dispositivos/reclamar", methods=["POST"])
    def reclamar_dispositivo():
        """
        Endpoint invocado directamente por el microcontrolador ESP32 tras conectarse a Wi-Fi.
        Registra el hardware en la base de datos para que aparezca como disponible en la red.
        """
        payload = request.get_json(silent=True) or {}
        mac = payload.get("mac", "").strip().upper()
        if not mac:
            return jsonify({"error": "MAC_REQUERIDA", "mensaje": "Se requiere el parámetro 'mac'"}), 400

        dev = repo_dispositivos.registrar_o_conectar_dispositivo(dispositivo_id=mac, mac=mac)
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

    return bp

