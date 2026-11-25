"""
Entidades y modelos del dominio puro de Plantol.
Restricción arquitectural estricta (Hexagonal):
Este módulo NO importa Flask, HTTP, SQLite, CSV, JSON ni bibliotecas JWT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Estados de clasificación de parámetros ambientales
BAJO = "BAJO"
OPTIMO = "OPTIMO"
ALTO = "ALTO"

# Estados de salud global de la planta
SALUDABLE = "SALUDABLE"
EN_RIESGO = "EN_RIESGO"
CRITICO = "CRITICO"

# Estados emocionales de la planta (Gamificación)
EMOCION_RADIANTE = "RADIANTE"
EMOCION_SEDIENTA = "SEDIENTA"
EMOCION_ACALORADA = "ACALORADA"
EMOCION_CON_FRIO = "CON FRÍO"
EMOCION_DURMIENDO = "DURMIENDO"
EMOCION_EN_PELIGRO = "EN PELIGRO"

# Tipos y motivos de transacciones de puntos (Gamificación)
TIPO_RECOMPENSA = "RECOMPENSA"
TIPO_PENALIZACION = "PENALIZACION"

MOTIVO_CUIDADO_CONTINUO = "CUIDADO_CONTINUO"
MOTIVO_RESCATE_HUMEDAD = "RESCATE_HUMEDAD"
MOTIVO_SALUDO_DIARIO = "SALUDO_DIARIO"
MOTIVO_PENALIZACION_DESCUIDO = "PENALIZACION_DESCUIDO"

# Estados de conectividad del dispositivo IoT
CONECTADO = "CONECTADO"
SIN_RESPUESTA = "SIN_RESPUESTA"


# =====================================================================
# Excepciones del Dominio
# =====================================================================

class DominioError(Exception):
    """Excepción base para violaciones de reglas de negocio del dominio."""
    pass


class EspecieNoSoportadaError(DominioError):
    def __init__(self, especie: str) -> None:
        self.especie = especie
        super().__init__(f"Especie no soportada en el sistema: '{especie}'")


class AccesoDenegadoPlantaError(DominioError):
    """Regla de negocio: un usuario solo puede consultar y gestionar sus propias plantas."""
    def __init__(self, usuario_id: int, planta_id: int) -> None:
        self.usuario_id = usuario_id
        self.planta_id = planta_id
        super().__init__(
            f"Acceso denegado: el usuario {usuario_id} no es propietario de la planta {planta_id}."
        )


class LecturaInvalidaError(DominioError):
    """Valores de telemetría físicamente imposibles o corruptos."""
    def __init__(self, detalle: str) -> None:
        self.detalle = detalle
        super().__init__(f"Lectura de sensor inválida: {detalle}")


class PlantaNoEncontradaError(DominioError):
    def __init__(self, planta_id: int) -> None:
        self.planta_id = planta_id
        super().__init__(f"Planta con id {planta_id} no encontrada.")


class DispositivoNoEncontradoError(DominioError):
    def __init__(self, dispositivo_id: str) -> None:
        self.dispositivo_id = dispositivo_id
        super().__init__(f"Dispositivo '{dispositivo_id}' no encontrado.")


class DispositivoNoVinculadoError(DominioError):
    def __init__(self, dispositivo_id: str) -> None:
        self.dispositivo_id = dispositivo_id
        super().__init__(f"El dispositivo '{dispositivo_id}' no está vinculado a ninguna planta activa.")


class SaludoYaRealizadoHoyError(DominioError):
    """Regla de gamificación: un usuario solo puede saludar a cada planta una vez al día."""
    def __init__(self, usuario_id: int, planta_id: int, fecha: str) -> None:
        self.usuario_id = usuario_id
        self.planta_id = planta_id
        self.fecha = fecha
        super().__init__(
            f"El usuario {usuario_id} ya saludó a la planta {planta_id} en la fecha {fecha}."
        )


class PuntosInsuficientesError(DominioError):
    def __init__(self, saldo_actual: int, cantidad: int) -> None:
        self.saldo_actual = saldo_actual
        self.cantidad = cantidad
        super().__init__(
            f"Saldo insuficiente ({saldo_actual} puntos) para descontar {cantidad} puntos."
        )


# =====================================================================
# Entidades del Dominio
# =====================================================================

@dataclass(frozen=True)
class RangosEspecie:
    """Rangos óptimos de luminosidad, humedad y temperatura por especie."""
    nombre: str
    lux_min: float
    lux_max: float
    humedad_min: float
    humedad_max: float
    temperatura_min: float
    temperatura_max: float


@dataclass(frozen=True)
class ResultadoParametro:
    """Evaluación individual de una variable ambiental."""
    nombre: str
    valor: float
    clasificacion: str
    recomendacion: str


@dataclass(frozen=True)
class DiagnosticoPlanta:
    """Diagnóstico consolidado del estado de salud y gamificación de una planta."""
    especie: str
    estado_global: str
    parametros: List[ResultadoParametro] = field(default_factory=list)
    fecha_hora: Optional[str] = None
    hp: int = 100
    estado_emocional: str = EMOCION_RADIANTE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "especie": self.especie,
            "estado_global": self.estado_global,
            "fecha_hora": self.fecha_hora,
            "hp": self.hp,
            "estado_emocional": self.estado_emocional,
            "parametros": [
                {
                    "nombre": p.nombre,
                    "valor": p.valor,
                    "clasificacion": p.clasificacion,
                    "recomendacion": p.recomendacion,
                }
                for p in self.parametros
            ],
        }


@dataclass(frozen=True)
class Lectura:
    """Medición ambiental enviada por una matera o simulador ESP32."""
    dispositivo_id: str
    timestamp: str
    luminosidad: float
    humedad: float
    temperatura: float
    id: Optional[int] = None
    planta_id: Optional[int] = None
    humedad_suelo: Optional[float] = None


@dataclass(frozen=True)
class TransaccionPuntos:
    """Registro inmutable de movimiento de saldo en la billetera de gamificación."""
    usuario_id: int
    cantidad: int
    motivo: str
    evento: str
    fecha: str
    tipo: str  # TIPO_RECOMPENSA o TIPO_PENALIZACION
    id: Optional[int] = None
    planta_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "planta_id": self.planta_id,
            "cantidad": self.cantidad,
            "motivo": self.motivo,
            "evento": self.evento,
            "fecha": self.fecha,
            "tipo": self.tipo,
        }


@dataclass
class EpisodioGamificacion:
    """Episodio continuo para evaluar estabilidad o descuido sin duplicar eventos."""
    planta_id: int
    tipo_episodio: str  # "SALUDABLE_CONTINUO", "CRITICO_CONTINUO", "HUMEDAD_BAJA"
    inicio_utc: str
    ultimo_registro_utc: str
    recompensado_penalizado: bool = False
    activo: bool = True
    id: Optional[int] = None


@dataclass(frozen=True)
class ResumenGamificacion:
    """Resumen de gamificación entregado a la vista."""
    usuario_id: int
    saldo_puntos: int
    total_transacciones: int = 0


@dataclass
class Planta:
    """Entidad planta registrada por un usuario."""
    id: int
    nombre: str
    especie: str
    usuario_id: int
    dispositivo_id: Optional[str] = None
    ubicacion: str = ""
    fecha_creacion: Optional[str] = None


@dataclass
class Usuario:
    """Usuario propietario del invernadero y sus plantas."""
    id: int
    username: str
    password_hash: str
    nombre: str
    email: str
    rol: str = "USUARIO"


@dataclass
class Dispositivo:
    """Dispositivo ESP32 que emite telemetría."""
    id: str
    secret_hash: str
    mac: str = ""
    planta_id: Optional[int] = None
    ultimo_contacto: Optional[str] = None
    estado_conexion: str = CONECTADO
