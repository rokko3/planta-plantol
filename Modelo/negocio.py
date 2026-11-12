"""
Reglas de Negocio y Casos de Uso del Dominio de Plantol.
Contiene:
- ValidadorDeEstado: Reglas de validación física, clasificación y determinación de salud vegetal.
- Casos de Uso que orquestan las entidades y los puertos sin conocer la tecnología concreta.
Restricción arquitectural estricta (Hexagonal):
Este módulo NO importa Flask, HTTP, SQLite, CSV, JSON ni bibliotecas JWT.
"""
from __future__ import annotations

import datetime
import hashlib
import os
from typing import Any, Dict, List, Optional, Tuple

from Modelo.entidades import (
    ALTO,
    BAJO,
    CONECTADO,
    CRITICO,
    EN_RIESGO,
    OPTIMO,
    SALUDABLE,
    AccesoDenegadoPlantaError,
    DiagnosticoPlanta,
    Dispositivo,
    DispositivoNoVinculadoError,
    EspecieNoSoportadaError,
    Lectura,
    LecturaInvalidaError,
    Planta,
    PlantaNoEncontradaError,
    RangosEspecie,
    ResultadoParametro,
    Usuario,
)
from Modelo.puertos import (
    EmisorTokenPort,
    HistorialLecturasPort,
    RepositorioDispositivosPort,
    RepositorioPlantasPort,
    RepositorioUsuariosPort,
    TablaReferenciaPort,
)

PARAMETROS_EVALUABLES = [
    (
        "luminosidad",
        "lux_min",
        "lux_max",
        "lux",
        "Aumenta la exposición a la luz natural o artificial.",
        "Reduce la exposición a la luz directa o mueve la planta a sombra parcial.",
    ),
    (
        "humedad",
        "humedad_min",
        "humedad_max",
        "%",
        "Aumenta el riego o usa un humidificador cerca de la planta.",
        "Reduce la frecuencia de riego y asegura buen drenaje.",
    ),
    (
        "temperatura",
        "temperatura_min",
        "temperatura_max",
        "°C",
        "Mueve la planta a un lugar más cálido y alejado de corrientes de aire frío.",
        "Mueve la planta a un lugar más fresco o ventilado.",
    ),
]


class ValidadorDeEstado:
    """Núcleo del dominio: clasificación ambiental y validación de reglas de salud vegetal."""

    @staticmethod
    def validar_lectura_fisica(luminosidad: float, humedad: float, temperatura: float) -> None:
        """
        Verifica que los valores de telemetría sean físicamente plausibles.
        Detecta anomalías físicas, sensores averiados o lecturas corruptas.
        """
        if not isinstance(luminosidad, (int, float)) or luminosidad < 0 or luminosidad > 200000:
            raise LecturaInvalidaError(f"Luminosidad fuera de rango físico: {luminosidad} lux")

        if not isinstance(humedad, (int, float)) or humedad < 0 or humedad > 100:
            raise LecturaInvalidaError(f"Humedad relativa fuera de rango físico: {humedad} %")

        if not isinstance(temperatura, (int, float)) or temperatura < -40 or temperatura > 80:
            raise LecturaInvalidaError(f"Temperatura fuera de rango físico: {temperatura} °C")

    def clasificar_uno(
        self,
        nombre: str,
        valor: float,
        v_min: float,
        v_max: float,
        reco_bajo: str,
        reco_alto: str,
    ) -> ResultadoParametro:
        if valor < v_min:
            return ResultadoParametro(
                nombre=nombre,
                valor=valor,
                clasificacion=BAJO,
                recomendacion=reco_bajo,
            )
        if valor > v_max:
            return ResultadoParametro(
                nombre=nombre,
                valor=valor,
                clasificacion=ALTO,
                recomendacion=reco_alto,
            )
        return ResultadoParametro(
            nombre=nombre,
            valor=valor,
            clasificacion=OPTIMO,
            recomendacion="",
        )

    def clasificar_todos(
        self,
        rangos: RangosEspecie,
        luminosidad: float,
        humedad: float,
        temperatura: float,
    ) -> List[ResultadoParametro]:
        valores = {
            "luminosidad": luminosidad,
            "humedad": humedad,
            "temperatura": temperatura,
        }
        resultados: List[ResultadoParametro] = []
        for nombre, min_attr, max_attr, _unidad, reco_bajo, reco_alto in PARAMETROS_EVALUABLES:
            resultado = self.clasificar_uno(
                nombre=nombre,
                valor=valores[nombre],
                v_min=getattr(rangos, min_attr),
                v_max=getattr(rangos, max_attr),
                reco_bajo=reco_bajo,
                reco_alto=reco_alto,
            )
            resultados.append(resultado)
        return resultados

    def determinar_estado(self, resultados: List[ResultadoParametro]) -> str:
        fuera_de_rango = [r for r in resultados if r.clasificacion != OPTIMO]
        n = len(fuera_de_rango)
        if n == 0:
            return SALUDABLE
        elif n == 1:
            return EN_RIESGO
        else:
            return CRITICO

    def evaluar(
        self,
        especie: str,
        rangos: RangosEspecie,
        luminosidad: float,
        humedad: float,
        temperatura: float,
        fecha_hora: Optional[str] = None,
    ) -> DiagnosticoPlanta:
        self.validar_lectura_fisica(luminosidad, humedad, temperatura)
        resultados = self.clasificar_todos(
            rangos=rangos,
            luminosidad=luminosidad,
            humedad=humedad,
            temperatura=temperatura,
        )
        estado_global = self.determinar_estado(resultados)
        return DiagnosticoPlanta(
            especie=especie,
            estado_global=estado_global,
            parametros=resultados,
            fecha_hora=fecha_hora,
        )

    @staticmethod
    def verificar_propiedad_planta(planta: Planta, usuario_id: int) -> None:
        """
        Regla de negocio esencial de dominio: Un usuario solo accede a sus propias plantas.
        """
        if planta.usuario_id != usuario_id:
            raise AccesoDenegadoPlantaError(usuario_id=usuario_id, planta_id=planta.id)


# =====================================================================
# Implementaciones de los Casos de Uso (Puertos de Entrada)
# =====================================================================

class CasoUsoRegistrarLectura:
    """
    Caso de uso P1: Registrar telemetría reportada por ESP32 o simulador.
    Valida físicamente la medición, busca la planta asociada, diagnostica y persiste.
    """

    def __init__(
        self,
        validador: ValidadorDeEstado,
        tabla_referencia: TablaReferenciaPort,
        repo_plantas: RepositorioPlantasPort,
        repo_dispositivos: RepositorioDispositivosPort,
        historial_lecturas: HistorialLecturasPort,
    ) -> None:
        self._validador = validador
        self._tabla = tabla_referencia
        self._plantas = repo_plantas
        self._dispositivos = repo_dispositivos
        self._historial = historial_lecturas

    def registrar(
        self,
        dispositivo_id: str,
        timestamp: str,
        luminosidad: float,
        humedad: float,
        temperatura: float,
    ) -> DiagnosticoPlanta:
        # 1. Valida reglas físicas de la telemetría en el dominio
        self._validador.validar_lectura_fisica(luminosidad, humedad, temperatura)

        # 2. Busca la planta asignada al dispositivo
        planta = self._plantas.obtener_por_dispositivo(dispositivo_id)
        if not planta:
            # Registra la lectura sin planta vinculada y lanza error de negocio
            lectura_huerfana = Lectura(
                dispositivo_id=dispositivo_id,
                timestamp=timestamp,
                luminosidad=luminosidad,
                humedad=humedad,
                temperatura=temperatura,
            )
            self._historial.guardar_lectura(lectura_huerfana, None)
            self._dispositivos.actualizar_ultimo_contacto(dispositivo_id, timestamp)
            raise DispositivoNoVinculadoError(dispositivo_id)

        # 3. Obtiene rangos de la especie desde el puerto de salida
        rangos = self._tabla.obtener_rangos(planta.especie)
        if not rangos:
            raise EspecieNoSoportadaError(planta.especie)

        # 4. Ejecuta el núcleo de dominio para calcular el diagnóstico
        diagnostico = self._validador.evaluar(
            especie=planta.especie,
            rangos=rangos,
            luminosidad=luminosidad,
            humedad=humedad,
            temperatura=temperatura,
            fecha_hora=timestamp,
        )

        # 5. Persiste la lectura y su diagnóstico en el puerto de historial
        lectura = Lectura(
            dispositivo_id=dispositivo_id,
            timestamp=timestamp,
            luminosidad=luminosidad,
            humedad=humedad,
            temperatura=temperatura,
            planta_id=planta.id,
        )
        self._historial.guardar_lectura(lectura, diagnostico)

        # 6. Actualiza último contacto del dispositivo
        self._dispositivos.actualizar_ultimo_contacto(dispositivo_id, timestamp)

        return diagnostico


class CasoUsoConsultarEstado:
    """
    Caso de uso P2: Consultar estado actual e historial de las plantas.
    Aplica rigurosamente la regla de negocio: un usuario solo ve sus propias plantas.
    """

    def __init__(
        self,
        validador: ValidadorDeEstado,
        repo_plantas: RepositorioPlantasPort,
        historial_lecturas: HistorialLecturasPort,
        repo_dispositivos: RepositorioDispositivosPort,
    ) -> None:
        self._validador = validador
        self._plantas = repo_plantas
        self._historial = historial_lecturas
        self._dispositivos = repo_dispositivos

    def consultar_estado_planta(self, usuario_id: int, planta_id: int) -> Dict[str, Any]:
        planta = self._plantas.obtener_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(planta_id)

        # Regla de negocio de dominio: control de pertenencia
        self._validador.verificar_propiedad_planta(planta, usuario_id)

        ultima_lectura = self._historial.obtener_ultima_lectura_por_planta(planta_id)
        historial = self._historial.obtener_historial_por_planta(planta_id, limite=20)

        dispositivo_info = None
        if planta.dispositivo_id:
            dev = self._dispositivos.buscar_por_id(planta.dispositivo_id)
            if dev:
                dispositivo_info = {
                    "id": dev.id,
                    "mac": dev.mac,
                    "ultimo_contacto": dev.ultimo_contacto,
                    "estado_conexion": dev.estado_conexion,
                }

        return {
            "planta": {
                "id": planta.id,
                "nombre": planta.nombre,
                "especie": planta.especie,
                "ubicacion": planta.ubicacion,
                "dispositivo_id": planta.dispositivo_id,
            },
            "dispositivo": dispositivo_info,
            "ultima_lectura": {
                "timestamp": ultima_lectura.timestamp if ultima_lectura else None,
                "luminosidad": ultima_lectura.luminosidad if ultima_lectura else None,
                "humedad": ultima_lectura.humedad if ultima_lectura else None,
                "temperatura": ultima_lectura.temperatura if ultima_lectura else None,
            } if ultima_lectura else None,
            "historial": historial,
        }

    def consultar_plantas_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        plantas = self._plantas.listar_por_usuario(usuario_id)
        res: List[Dict[str, Any]] = []
        for p in plantas:
            ultima = self._historial.obtener_ultima_lectura_por_planta(p.id)
            hist = self._historial.obtener_historial_por_planta(p.id, limite=1)
            diag_dict = hist[0].get("diagnostico") if hist else None
            estado_global = diag_dict.get("estado_global", "DESCONOCIDO") if diag_dict else "SIN_DATOS"

            dev_info = None
            if p.dispositivo_id:
                dev = self._dispositivos.buscar_por_id(p.dispositivo_id)
                if dev:
                    dev_info = {
                        "id": dev.id,
                        "ultimo_contacto": dev.ultimo_contacto,
                        "estado_conexion": dev.estado_conexion,
                    }

            res.append({
                "id": p.id,
                "nombre": p.nombre,
                "especie": p.especie,
                "ubicacion": p.ubicacion,
                "dispositivo_id": p.dispositivo_id,
                "estado_global": estado_global,
                "diagnostico": diag_dict,
                "dispositivo": dev_info,
                "ultima_lectura": {
                    "timestamp": ultima.timestamp if ultima else None,
                    "luminosidad": ultima.luminosidad if ultima else None,
                    "humedad": ultima.humedad if ultima else None,
                    "temperatura": ultima.temperatura if ultima else None,
                } if ultima else None,
            })
        return res

    def consultar_resumen_dashboard(self, usuario_id: int) -> Dict[str, Any]:
        plantas_info = self.consultar_plantas_usuario(usuario_id)
        total_plantas = len(plantas_info)
        sensores_conectados = sum(
            1 for p in plantas_info if p.get("dispositivo") and p["dispositivo"].get("estado_conexion") == CONECTADO
        )
        en_buen_estado = sum(1 for p in plantas_info if p.get("estado_global") == SALUDABLE)
        alertas_pendientes = sum(1 for p in plantas_info if p.get("estado_global") in ["EN_RIESGO", "CRITICO"])

        alertas: List[Dict[str, Any]] = []
        for p in plantas_info:
            estado = p.get("estado_global")
            diag = p.get("diagnostico")
            if estado in ["EN_RIESGO", "CRITICO"] and diag:
                for param in diag.get("parametros", []):
                    if param.get("clasificacion") != OPTIMO:
                        alertas.append({
                            "planta": p["nombre"],
                            "especie": p["especie"],
                            "tipo": estado,
                            "parametro": param["nombre"],
                            "valor": param["valor"],
                            "recomendacion": param["recomendacion"],
                            "timestamp": p["ultima_lectura"]["timestamp"] if p.get("ultima_lectura") else "Reciente",
                        })

        return {
            "stats": {
                "total_plantas": total_plantas,
                "sensores_conectados": sensores_conectados,
                "en_buen_estado": en_buen_estado,
                "alertas_pendientes": alertas_pendientes,
            },
            "plantas": plantas_info,
            "alertas": alertas,
        }


class CasoUsoGestionPlantas:
    """Permite crear, vincular, desvincular y eliminar plantas y dispositivos ESP32."""

    def __init__(
        self,
        validador: ValidadorDeEstado,
        repo_plantas: RepositorioPlantasPort,
        repo_dispositivos: RepositorioDispositivosPort,
        tabla_referencia: TablaReferenciaPort,
    ) -> None:
        self._validador = validador
        self._plantas = repo_plantas
        self._dispositivos = repo_dispositivos
        self._tabla = tabla_referencia

    def crear_planta(
        self,
        usuario_id: int,
        nombre: str,
        especie: str,
        ubicacion: str,
        dispositivo_id: Optional[str] = None,
    ) -> Planta:
        rangos = self._tabla.obtener_rangos(especie)
        if not rangos:
            raise EspecieNoSoportadaError(especie)

        planta = Planta(
            id=0,
            nombre=nombre.strip(),
            especie=especie.strip(),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id.strip() if dispositivo_id else None,
            ubicacion=ubicacion.strip(),
            fecha_creacion=datetime.datetime.now().isoformat(),
        )
        return self._plantas.guardar_planta(planta)

    def vincular_dispositivo(
        self,
        usuario_id: int,
        planta_id: int,
        dispositivo_id: str,
        codigo_vinculacion: Optional[str] = None,
    ) -> bool:
        planta = self._plantas.obtener_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(planta_id)

        # Regla de negocio de dominio: Un usuario solo accede a sus propias plantas
        self._validador.verificar_propiedad_planta(planta, usuario_id)

        # Si se suministra un código de vinculación temporal (compatibilidad previa), validarlo
        if codigo_vinculacion:
            dev_id_autorizado = self._dispositivos.consumir_codigo_vinculacion(codigo_vinculacion)
            if not dev_id_autorizado or dev_id_autorizado.upper() != dispositivo_id.upper():
                return False

        # Vinculación directa autorizada para el propietario
        self._plantas.vincular_dispositivo(planta_id, dispositivo_id)
        return True

    def desvincular_dispositivo(
        self,
        usuario_id: int,
        planta_id: int,
    ) -> bool:
        planta = self._plantas.obtener_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(planta_id)

        # Regla de negocio de dominio: Un usuario solo accede a sus propias plantas
        self._validador.verificar_propiedad_planta(planta, usuario_id)

        if not planta.dispositivo_id:
            return False

        dispositivo_id = planta.dispositivo_id
        # Desvincula la planta (dispositivo_id = None)
        self._plantas.vincular_dispositivo(planta_id, None)

        # Libera el dispositivo para que vuelva a estar disponible en la red
        dev = self._dispositivos.buscar_por_id(dispositivo_id)
        if dev:
            dev.planta_id = None
            self._dispositivos.guardar_dispositivo(dev)

        return True

    def eliminar_planta(
        self,
        usuario_id: int,
        planta_id: int,
    ) -> bool:
        planta = self._plantas.obtener_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(planta_id)

        # Regla de negocio de dominio: Un usuario solo accede y gestiona sus propias plantas
        self._validador.verificar_propiedad_planta(planta, usuario_id)

        # Si tiene sensor vinculado, liberarlo en la red
        if planta.dispositivo_id:
            dev = self._dispositivos.buscar_por_id(planta.dispositivo_id)
            if dev:
                dev.planta_id = None
                self._dispositivos.guardar_dispositivo(dev)

        # Eliminar la planta de la persistencia
        return self._plantas.eliminar_planta(planta_id)


class CasoUsoAutenticacion:
    """Gestión de usuarios y autenticación segura con PBKDF2 y emisión de JWT."""

    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        emisor_token: EmisorTokenPort,
    ) -> None:
        self._usuarios = repo_usuarios
        self._emisor = emisor_token

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return f"{salt.hex()}:{hash_bytes.hex()}"

    @staticmethod
    def _verificar_password(password: str, stored_hash: str) -> bool:
        try:
            salt_hex, hash_hex = stored_hash.split(":")
            salt = bytes.fromhex(salt_hex)
            expected_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000).hex()
            return expected_hash == hash_hex
        except Exception:
            return False

    def registrar_usuario(
        self, username: str, password: str, nombre: str, email: str
    ) -> Tuple[Usuario, str]:
        username = username.strip().lower()
        existente = self._usuarios.buscar_por_username(username)
        if existente:
            raise ValueError(f"El nombre de usuario '{username}' ya está registrado.")

        pwd_hash = self._hash_password(password)
        nuevo_usuario = Usuario(
            id=0,
            username=username,
            password_hash=pwd_hash,
            nombre=nombre.strip(),
            email=email.strip(),
        )
        guardado = self._usuarios.guardar_usuario(nuevo_usuario)
        token = self._emisor.emitir_token_usuario(guardado.id, guardado.username)
        return guardado, token

    def iniciar_sesion(self, username: str, password: str) -> Tuple[Usuario, str]:
        username = username.strip().lower()
        usuario = self._usuarios.buscar_por_username(username)
        if not usuario or not self._verificar_password(password, usuario.password_hash):
            raise ValueError("Credenciales inválidas.")

        token = self._emisor.emitir_token_usuario(usuario.id, usuario.username)
        return usuario, token

