"""
Puertos de la Arquitectura Hexagonal de Plantol.
Define las interfaces abstractas (Protocolos) para:
- Puertos de Entrada: Exponen los casos de uso a los adaptadores de entrada.
- Puertos de Salida: Contratos requeridos por el dominio para interactuar con infraestructura.
Restricción arquitectural:
Este módulo NO importa Flask, HTTP, SQLite, CSV, JSON ni bibliotecas JWT.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from Modelo.entidades import (
    DiagnosticoPlanta,
    Dispositivo,
    Lectura,
    Planta,
    RangosEspecie,
    Usuario,
)


# =====================================================================
# Puertos de Entrada (Casos de Uso)
# =====================================================================

@runtime_checkable
class RegistrarLecturaPort(Protocol):
    """Puerto de entrada para procesar y persistir telemetría de un dispositivo."""
    def registrar(
        self,
        dispositivo_id: str,
        timestamp: str,
        luminosidad: float,
        humedad: float,
        temperatura: float,
    ) -> DiagnosticoPlanta:
        ...


@runtime_checkable
class ConsultarEstadoPort(Protocol):
    """Puerto de entrada para consultar salud e historial de plantas."""
    def consultar_estado_planta(self, usuario_id: int, planta_id: int) -> Dict[str, Any]:
        ...

    def consultar_plantas_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        ...

    def consultar_resumen_dashboard(self, usuario_id: int) -> Dict[str, Any]:
        ...


@runtime_checkable
class GestionPlantasPort(Protocol):
    """Puerto de entrada para administrar plantas y vinculación de hardware."""
    def crear_planta(
        self,
        usuario_id: int,
        nombre: str,
        especie: str,
        ubicacion: str,
        dispositivo_id: Optional[str] = None,
    ) -> Planta:
        ...

    def vincular_dispositivo(
        self,
        usuario_id: int,
        planta_id: int,
        dispositivo_id: str,
        codigo_vinculacion: Optional[str] = None,
    ) -> bool:
        ...

    def desvincular_dispositivo(
        self,
        usuario_id: int,
        planta_id: int,
    ) -> bool:
        ...

    def eliminar_planta(
        self,
        usuario_id: int,
        planta_id: int,
    ) -> bool:
        ...


@runtime_checkable
class AutenticacionPort(Protocol):
    """Puerto de entrada para registro e inicio de sesión de usuarios."""
    def registrar_usuario(
        self, username: str, password: str, nombre: str, email: str
    ) -> Tuple[Usuario, str]:
        ...

    def iniciar_sesion(self, username: str, password: str) -> Tuple[Usuario, str]:
        ...


# =====================================================================
# Puertos de Salida (Adaptadores de Infraestructura)
# =====================================================================

@runtime_checkable
class TablaReferenciaPort(Protocol):
    """Puerto de salida para consultar rangos óptimos por especie (Requisito R4)."""
    def obtener_rangos(self, especie: str) -> Optional[RangosEspecie]:
        ...

    def listar_especies(self) -> List[RangosEspecie]:
        ...


@runtime_checkable
class HistorialLecturasPort(Protocol):
    """Puerto de salida para persistir telemetría y consultar lecturas históricas (Requisito R5)."""
    def guardar_lectura(
        self, lectura: Lectura, diagnostico: Optional[DiagnosticoPlanta] = None
    ) -> None:
        ...

    def obtener_ultima_lectura(self, dispositivo_id: str) -> Optional[Lectura]:
        ...

    def obtener_ultima_lectura_por_planta(self, planta_id: int) -> Optional[Lectura]:
        ...

    def obtener_historial_por_planta(
        self, planta_id: int, limite: int = 50
    ) -> List[Dict[str, Any]]:
        ...

    def obtener_todas_recientes(self, limite: int = 50) -> List[Dict[str, Any]]:
        ...


@runtime_checkable
class RepositorioPlantasPort(Protocol):
    """Puerto de salida para almacenamiento y consulta de plantas."""
    def guardar_planta(self, planta: Planta) -> Planta:
        ...

    def obtener_por_id(self, planta_id: int) -> Optional[Planta]:
        ...

    def listar_por_usuario(self, usuario_id: int) -> List[Planta]:
        ...

    def obtener_por_dispositivo(self, dispositivo_id: str) -> Optional[Planta]:
        ...

    def vincular_dispositivo(self, planta_id: int, dispositivo_id: Optional[str]) -> None:
        ...

    def eliminar_planta(self, planta_id: int) -> bool:
        ...


@runtime_checkable
class RepositorioUsuariosPort(Protocol):
    """Puerto de salida para almacenamiento de credenciales y cuentas de usuario."""
    def guardar_usuario(self, usuario: Usuario) -> Usuario:
        ...

    def buscar_por_username(self, username: str) -> Optional[Usuario]:
        ...

    def buscar_por_id(self, usuario_id: int) -> Optional[Usuario]:
        ...


@runtime_checkable
class RepositorioDispositivosPort(Protocol):
    """Puerto de salida para gestión de dispositivos ESP32 y vinculación segura."""
    def guardar_dispositivo(self, dispositivo: Dispositivo) -> Dispositivo:
        ...

    def buscar_por_id(self, dispositivo_id: str) -> Optional[Dispositivo]:
        ...

    def listar_dispositivos(self) -> List[Dispositivo]:
        ...

    def listar_dispositivos_disponibles(self) -> List[Dispositivo]:
        ...

    def registrar_o_conectar_dispositivo(
        self, dispositivo_id: str, mac: Optional[str] = None, red_wifi: Optional[str] = None
    ) -> Dispositivo:
        ...

    def actualizar_ultimo_contacto(self, dispositivo_id: str, fecha_hora: str) -> None:
        ...

    def generar_codigo_vinculacion(self, dispositivo_id: str) -> str:
        ...

    def consumir_codigo_vinculacion(self, codigo: str) -> Optional[str]:
        ...


@runtime_checkable
class EmisorTokenPort(Protocol):
    """Puerto de salida para emisión y verificación técnica de tokens JWT (Requisito R7)."""
    def emitir_token_usuario(self, usuario_id: int, username: str) -> str:
        ...

    def emitir_token_dispositivo(self, dispositivo_id: str) -> str:
        ...

    def verificar_token(self, token: str) -> Dict[str, Any]:
        ...
