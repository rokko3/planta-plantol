"""
Adaptadores de Salida y Persistencia de Plantol.
Consolida:
- TablaReferenciaCSV y TablaReferenciaBD (Requisito R4: Fuentes intercambiables)
- HistorialLecturasBD (Requisito R5: Historial en SQLite)
- RepositorioSQLite (Plantas, Usuarios y Dispositivos)
- ServicioJWT (Requisito R7: Tokens de usuario y dispositivo con PyJWT)
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import random
import sqlite3
import string
from typing import Any, Dict, List, Optional

import jwt

from Modelo.entidades import (
    CONECTADO,
    DiagnosticoPlanta,
    Dispositivo,
    EpisodioGamificacion,
    Lectura,
    Planta,
    RangosEspecie,
    SIN_RESPUESTA,
    TransaccionPuntos,
    Usuario,
)
from Modelo.puertos import (
    EmisorTokenPort,
    HistorialLecturasPort,
    RepositorioDispositivosPort,
    RepositorioGamificacionPort,
    RepositorioPlantasPort,
    RepositorioUsuariosPort,
    TablaReferenciaPort,
)

CLAVE_JWT_DEFECTO = "plantol_super_secret_key_2026_arquitectura_hexagonal_segura_32b"

ESPECIES_BASE_BD = [
    ("Cactus (Cactaceae)", 5000.0, 15000.0, 10.0, 30.0, 18.0, 35.0),
    ("Helecho (Nephrolepis)", 2000.0, 6000.0, 60.0, 80.0, 18.0, 24.0),
    ("Orquídea (Orchidaceae)", 1000.0, 3000.0, 50.0, 70.0, 18.0, 28.0),
    ("Monstera (Monstera deliciosa)", 2500.0, 7000.0, 60.0, 80.0, 20.0, 30.0),
    ("Suculenta (Crassulaceae)", 4000.0, 12000.0, 15.0, 35.0, 15.0, 30.0),
    ("Pothos (Epipremnum aureum)", 1500.0, 5000.0, 40.0, 70.0, 17.0, 30.0),
    ("Girasol (Helianthus annuus)", 10000.0, 25000.0, 30.0, 60.0, 15.0, 30.0),
    ("Tomate (Solanum lycopersicum)", 8000.0, 20000.0, 50.0, 80.0, 18.0, 30.0),
    ("Bonsái (Ficus retusa)", 3000.0, 8000.0, 40.0, 60.0, 15.0, 28.0),
    ("Aloe Vera (Aloe barbadensis)", 3000.0, 10000.0, 10.0, 30.0, 18.0, 32.0),
    ("Menta (Mentha spicata)", 2000.0, 6000.0, 50.0, 70.0, 15.0, 25.0),
    ("Lavanda (Lavandula angustifolia)", 4000.0, 12000.0, 30.0, 50.0, 10.0, 28.0),
]


# =====================================================================
# Adaptador 1: Tabla de Referencia en CSV (R4)
# =====================================================================

class TablaReferenciaCSV(TablaReferenciaPort):
    """Implementa TablaReferenciaPort leyendo un archivo CSV."""

    def __init__(self, ruta_csv: str) -> None:
        self._ruta = ruta_csv
        self._cache: Optional[Dict[str, RangosEspecie]] = None

    def obtener_rangos(self, especie: str) -> Optional[RangosEspecie]:
        return self._indice().get(especie.strip().lower())

    def listar_especies(self) -> List[RangosEspecie]:
        return list(self._indice().values())

    def _indice(self) -> Dict[str, RangosEspecie]:
        if self._cache is None:
            self._cache = self._cargar()
        return self._cache

    def _cargar(self) -> Dict[str, RangosEspecie]:
        indice: Dict[str, RangosEspecie] = {}
        if not os.path.exists(self._ruta):
            return indice

        with open(self._ruta, encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                nombre = fila.get("especie", "").strip()
                if not nombre or nombre.startswith("#"):
                    continue
                try:
                    rangos = RangosEspecie(
                        nombre=nombre,
                        lux_min=float(fila["lux_min"]),
                        lux_max=float(fila["lux_max"]),
                        humedad_min=float(fila["humedad_min"]),
                        humedad_max=float(fila["humedad_max"]),
                        temperatura_min=float(fila["temperatura_min"]),
                        temperatura_max=float(fila["temperatura_max"]),
                    )
                    indice[nombre.lower()] = rangos
                except (ValueError, KeyError):
                    continue
        return indice


# =====================================================================
# Adaptador 2: Tabla de Referencia en Base de Datos SQLite (R4)
# =====================================================================

class TablaReferenciaBD(TablaReferenciaPort):
    """Implementa TablaReferenciaPort persistida en SQLite."""

    def __init__(self, ruta_db: str) -> None:
        self._ruta_db = ruta_db
        dir_padre = os.path.dirname(os.path.abspath(self._ruta_db))
        if dir_padre:
            os.makedirs(dir_padre, exist_ok=True)
        self._inicializar_tabla()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._ruta_db, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar_tabla(self) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS especies_referencia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    lux_min REAL NOT NULL,
                    lux_max REAL NOT NULL,
                    humedad_min REAL NOT NULL,
                    humedad_max REAL NOT NULL,
                    temperatura_min REAL NOT NULL,
                    temperatura_max REAL NOT NULL
                )
                """
            )
            cursor.execute("SELECT COUNT(*) FROM especies_referencia")
            if cursor.fetchone()[0] == 0:
                cursor.executemany(
                    """
                    INSERT INTO especies_referencia 
                    (nombre, lux_min, lux_max, humedad_min, humedad_max, temperatura_min, temperatura_max)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ESPECIES_BASE_BD,
                )
            conn.commit()

    def obtener_rangos(self, especie: str) -> Optional[RangosEspecie]:
        especie_clean = especie.strip().lower()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT nombre, lux_min, lux_max, humedad_min, humedad_max, temperatura_min, temperatura_max "
                "FROM especies_referencia WHERE LOWER(nombre) = ?",
                (especie_clean,),
            )
            fila = cursor.fetchone()
            if not fila:
                return None
            return RangosEspecie(
                nombre=fila["nombre"],
                lux_min=float(fila["lux_min"]),
                lux_max=float(fila["lux_max"]),
                humedad_min=float(fila["humedad_min"]),
                humedad_max=float(fila["humedad_max"]),
                temperatura_min=float(fila["temperatura_min"]),
                temperatura_max=float(fila["temperatura_max"]),
            )

    def listar_especies(self) -> List[RangosEspecie]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT nombre, lux_min, lux_max, humedad_min, humedad_max, temperatura_min, temperatura_max "
                "FROM especies_referencia ORDER BY nombre ASC"
            )
            return [
                RangosEspecie(
                    nombre=fila["nombre"],
                    lux_min=float(fila["lux_min"]),
                    lux_max=float(fila["lux_max"]),
                    humedad_min=float(fila["humedad_min"]),
                    humedad_max=float(fila["humedad_max"]),
                    temperatura_min=float(fila["temperatura_min"]),
                    temperatura_max=float(fila["temperatura_max"]),
                )
                for fila in cursor.fetchall()
            ]


# =====================================================================
# Adaptador 3: Historial de Lecturas en SQLite (R5)
# =====================================================================

class HistorialLecturasBD(HistorialLecturasPort):
    """Implementa HistorialLecturasPort persistiendo telemetría en SQLite."""

    def __init__(self, ruta_db: str) -> None:
        self._ruta_db = ruta_db
        dir_padre = os.path.dirname(os.path.abspath(self._ruta_db))
        if dir_padre:
            os.makedirs(dir_padre, exist_ok=True)
        self._inicializar_tabla()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._ruta_db, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar_tabla(self) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS historial_lecturas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dispositivo_id TEXT NOT NULL,
                    planta_id INTEGER,
                    timestamp TEXT NOT NULL,
                    luminosidad REAL NOT NULL,
                    humedad REAL NOT NULL,
                    temperatura REAL NOT NULL,
                    estado_global TEXT,
                    diagnostico_json TEXT,
                    fecha_creacion TEXT NOT NULL,
                    humedad_suelo REAL
                )
                """
            )
            # Migración automática si la columna no existe en bases de datos existentes
            try:
                cursor.execute("ALTER TABLE historial_lecturas ADD COLUMN humedad_suelo REAL")
            except sqlite3.OperationalError:
                pass
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_historial_dispositivo ON historial_lecturas(dispositivo_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_historial_planta ON historial_lecturas(planta_id)"
            )
            self._asegurar_columna(cursor, "historial_lecturas", "humedad_suelo", "REAL")
            conn.commit()

    @staticmethod
    def _asegurar_columna(cursor: sqlite3.Cursor, tabla: str, columna: str, definicion: str) -> None:
        cursor.execute(f"PRAGMA table_info({tabla})")
        columnas = {fila[1] for fila in cursor.fetchall()}
        if columna not in columnas:
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")

    def guardar_lectura(
        self, lectura: Lectura, diagnostico: Optional[DiagnosticoPlanta] = None
    ) -> None:
        diag_json = json.dumps(diagnostico.to_dict()) if diagnostico else None
        estado = diagnostico.estado_global if diagnostico else None
        ahora = datetime.datetime.now().isoformat()
        hum_suelo = getattr(lectura, "humedad_suelo", None)

        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO historial_lecturas 
                (dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura, estado_global, diagnostico_json, fecha_creacion, humedad_suelo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lectura.dispositivo_id,
                    lectura.planta_id,
                    lectura.timestamp,
                    lectura.luminosidad,
                    lectura.humedad,
                    lectura.temperatura,
                    estado,
                    diag_json,
                    ahora,
                    hum_suelo,
                ),
            )
            conn.commit()

    def obtener_ultima_lectura(self, dispositivo_id: str) -> Optional[Lectura]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura, humedad_suelo
                FROM historial_lecturas
                WHERE dispositivo_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (dispositivo_id,),
            )
            fila = cursor.fetchone()
            if not fila:
                return None
            return Lectura(
                id=fila["id"],
                dispositivo_id=fila["dispositivo_id"],
                planta_id=fila["planta_id"],
                timestamp=fila["timestamp"],
                luminosidad=fila["luminosidad"],
                humedad=fila["humedad"],
                temperatura=fila["temperatura"],
                humedad_suelo=fila["humedad_suelo"] if "humedad_suelo" in fila.keys() else None,
            )

    def obtener_ultima_lectura_por_planta(self, planta_id: int) -> Optional[Lectura]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura, humedad_suelo
                FROM historial_lecturas
                WHERE planta_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (planta_id,),
            )
            fila = cursor.fetchone()
            if not fila:
                return None
            return Lectura(
                id=fila["id"],
                dispositivo_id=fila["dispositivo_id"],
                planta_id=fila["planta_id"],
                timestamp=fila["timestamp"],
                luminosidad=fila["luminosidad"],
                humedad=fila["humedad"],
                temperatura=fila["temperatura"],
                humedad_suelo=fila["humedad_suelo"] if "humedad_suelo" in fila.keys() else None,
            )

    def obtener_historial_por_planta(
        self, planta_id: int, limite: int = 50
    ) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura, humedad_suelo,
                       estado_global, diagnostico_json, fecha_creacion
                FROM historial_lecturas
                WHERE planta_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (planta_id, limite),
            )
            filas = cursor.fetchall()
            resultado = []
            for f in filas:
                diag = json.loads(f["diagnostico_json"]) if f["diagnostico_json"] else None
                resultado.append({
                    "id": f["id"],
                    "dispositivo_id": f["dispositivo_id"],
                    "planta_id": f["planta_id"],
                    "timestamp": f["timestamp"],
                    "luminosidad": f["luminosidad"],
                    "humedad": f["humedad"],
                    "humedad_suelo": f["humedad_suelo"] if "humedad_suelo" in f.keys() else None,
                    "temperatura": f["temperatura"],
                    "estado_global": f["estado_global"],
                    "diagnostico": diag,
                    "fecha_creacion": f["fecha_creacion"],
                })
            return resultado

    def obtener_todas_recientes(self, limite: int = 50) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura,
                       estado_global, diagnostico_json, fecha_creacion
                FROM historial_lecturas
                ORDER BY id DESC LIMIT ?
                """,
                (limite,),
            )
            filas = cursor.fetchall()
            resultado = []
            for f in filas:
                diag = json.loads(f["diagnostico_json"]) if f["diagnostico_json"] else None
                resultado.append({
                    "id": f["id"],
                    "dispositivo_id": f["dispositivo_id"],
                    "planta_id": f["planta_id"],
                    "timestamp": f["timestamp"],
                    "luminosidad": f["luminosidad"],
                    "humedad": f["humedad"],
                    "temperatura": f["temperatura"],
                    "estado_global": f["estado_global"],
                    "diagnostico": diag,
                })
            return resultado


# =====================================================================
# Adaptador 4: Repositorio SQLite (Plantas, Usuarios, Dispositivos)
# =====================================================================

VENTANA_ACTIVIDAD_DISPOSITIVO_SEG = 120


def evaluar_actividad_dispositivo(
    ultimo_contacto: Optional[str],
    estado_conexion: Optional[str],
    ventana_seg: int = VENTANA_ACTIVIDAD_DISPOSITIVO_SEG,
    ahora: Optional[datetime.datetime] = None,
) -> dict:
    """
    Evalúa si un dispositivo ESP32 tiene actividad real y reciente dentro de la ventana configurada.
    """
    estado_norm = (estado_conexion or "").strip().upper()
    if not ultimo_contacto:
        return {
            "en_linea": False,
            "estado_efectivo": SIN_RESPUESTA,
            "segundos_sin_contacto": None,
        }

    try:
        dt_contacto = datetime.datetime.fromisoformat(str(ultimo_contacto).replace("Z", "+00:00"))
    except ValueError:
        return {
            "en_linea": False,
            "estado_efectivo": SIN_RESPUESTA,
            "segundos_sin_contacto": None,
        }

    if ahora is None:
        ref = datetime.datetime.now(dt_contacto.tzinfo) if dt_contacto.tzinfo is not None else datetime.datetime.now()
    else:
        if dt_contacto.tzinfo is not None and ahora.tzinfo is None:
            ref = ahora.replace(tzinfo=dt_contacto.tzinfo)
        elif dt_contacto.tzinfo is None and ahora.tzinfo is not None:
            ref = ahora.replace(tzinfo=None)
        else:
            ref = ahora

    delta_seg = (ref - dt_contacto).total_seconds()
    segundos = max(0, int(delta_seg))
    en_linea = estado_norm == CONECTADO and (-5 <= delta_seg <= max(1, int(ventana_seg)))
    return {
        "en_linea": en_linea,
        "estado_efectivo": CONECTADO if en_linea else SIN_RESPUESTA,
        "segundos_sin_contacto": segundos,
    }


class RepositorioSQLite(
    RepositorioPlantasPort,
    RepositorioUsuariosPort,
    RepositorioDispositivosPort,
):
    """Implementa almacenamiento de entidades en base de datos SQLite."""

    def __init__(
        self,
        ruta_db: str,
        ventana_actividad_seg: Optional[int] = None,
        incluir_demo: bool = True,
    ) -> None:
        self._ruta_db = ruta_db
        if ventana_actividad_seg is not None:
            self._ventana_actividad_seg = max(1, int(ventana_actividad_seg))
        else:
            try:
                self._ventana_actividad_seg = max(
                    1, int(os.environ.get("PLANTOL_DISPOSITIVO_VENTANA_SEG", str(VENTANA_ACTIVIDAD_DISPOSITIVO_SEG)))
                )
            except ValueError:
                self._ventana_actividad_seg = VENTANA_ACTIVIDAD_DISPOSITIVO_SEG
        self._incluir_demo = bool(incluir_demo)
        dir_padre = os.path.dirname(os.path.abspath(self._ruta_db))
        if dir_padre:
            os.makedirs(dir_padre, exist_ok=True)
        self._inicializar_tablas()

    @property
    def ventana_actividad_seg(self) -> int:
        return self._ventana_actividad_seg

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._ruta_db, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar_tablas(self) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            # Tabla usuarios
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    email TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'USUARIO'
                )
                """
            )
            # Tabla dispositivos ESP32
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dispositivos (
                    id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    mac TEXT,
                    planta_id INTEGER,
                    ultimo_contacto TEXT,
                    estado_conexion TEXT NOT NULL DEFAULT 'CONECTADO'
                )
                """
            )
            # Tabla plantas
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plantas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    especie TEXT NOT NULL,
                    usuario_id INTEGER NOT NULL,
                    dispositivo_id TEXT UNIQUE,
                    ubicacion TEXT DEFAULT '',
                    fecha_creacion TEXT NOT NULL,
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
                    FOREIGN KEY(dispositivo_id) REFERENCES dispositivos(id)
                )
                """
            )
            # Tabla de códigos de vinculación temporal
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS codigos_vinculacion (
                    codigo TEXT PRIMARY KEY,
                    dispositivo_id TEXT NOT NULL,
                    fecha_creacion TEXT NOT NULL,
                    usado INTEGER DEFAULT 0
                )
                """
            )
            # Migraciones seguras no destructivas para esquemas previos
            self._asegurar_columna(cursor, "usuarios", "rol", "TEXT NOT NULL DEFAULT 'USUARIO'")
            self._asegurar_columna(cursor, "dispositivos", "mac", "TEXT")
            self._asegurar_columna(cursor, "dispositivos", "planta_id", "INTEGER")
            self._asegurar_columna(cursor, "dispositivos", "ultimo_contacto", "TEXT")
            self._asegurar_columna(cursor, "dispositivos", "estado_conexion", "TEXT NOT NULL DEFAULT 'CONECTADO'")
            self._asegurar_columna(cursor, "dispositivos", "es_demo", "INTEGER NOT NULL DEFAULT 0")
            self._asegurar_columna(cursor, "dispositivos", "usuario_id", "INTEGER")
            cursor.execute("PRAGMA table_info(codigos_vinculacion)")
            cols_cod = {fila[1] for fila in cursor.fetchall()}
            if "fecha_creacion" not in cols_cod:
                cursor.execute("ALTER TABLE codigos_vinculacion ADD COLUMN fecha_creacion TEXT NOT NULL DEFAULT ''")
                if "creado_en" in cols_cod:
                    cursor.execute("UPDATE codigos_vinculacion SET fecha_creacion = creado_en WHERE fecha_creacion = ''")
            conn.commit()

    @staticmethod
    def _asegurar_columna(cursor: sqlite3.Cursor, tabla: str, columna: str, definicion: str) -> None:
        cursor.execute(f"PRAGMA table_info({tabla})")
        columnas = {fila[1] for fila in cursor.fetchall()}
        if columna not in columnas:
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")

    # --- RepositorioUsuariosPort ---
    def guardar_usuario(self, usuario: Usuario) -> Usuario:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usuarios (username, password_hash, nombre, email, rol)
                VALUES (?, ?, ?, ?, ?)
                """,
                (usuario.username, usuario.password_hash, usuario.nombre, usuario.email, usuario.rol),
            )
            usuario_id = cursor.lastrowid
            conn.commit()
            return Usuario(
                id=usuario_id,
                username=usuario.username,
                password_hash=usuario.password_hash,
                nombre=usuario.nombre,
                email=usuario.email,
                rol=usuario.rol,
            )

    def buscar_por_username(self, username: str) -> Optional[Usuario]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE LOWER(username) = ?", (username.strip().lower(),))
            fila = cursor.fetchone()
            if not fila:
                return None
            return Usuario(
                id=fila["id"],
                username=fila["username"],
                password_hash=fila["password_hash"],
                nombre=fila["nombre"],
                email=fila["email"],
                rol=fila["rol"],
            )

    def buscar_por_id(self, usuario_id: int) -> Optional[Usuario]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
            fila = cursor.fetchone()
            if not fila:
                return None
            return Usuario(
                id=fila["id"],
                username=fila["username"],
                password_hash=fila["password_hash"],
                nombre=fila["nombre"],
                email=fila["email"],
                rol=fila["rol"],
            )

    # --- RepositorioPlantasPort ---
    def guardar_planta(self, planta: Planta) -> Planta:
        ahora = planta.fecha_creacion or datetime.datetime.now().isoformat()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO plantas (nombre, especie, usuario_id, dispositivo_id, ubicacion, fecha_creacion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (planta.nombre, planta.especie, planta.usuario_id, planta.dispositivo_id, planta.ubicacion, ahora),
            )
            planta_id = cursor.lastrowid
            if planta.dispositivo_id:
                cursor.execute(
                    "UPDATE dispositivos SET planta_id = ? WHERE id = ?",
                    (planta_id, planta.dispositivo_id),
                )
            conn.commit()
            return Planta(
                id=planta_id,
                nombre=planta.nombre,
                especie=planta.especie,
                usuario_id=planta.usuario_id,
                dispositivo_id=planta.dispositivo_id,
                ubicacion=planta.ubicacion,
                fecha_creacion=ahora,
            )

    def obtener_por_id(self, planta_id: int) -> Optional[Planta]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plantas WHERE id = ?", (planta_id,))
            fila = cursor.fetchone()
            if not fila:
                return None
            return Planta(
                id=fila["id"],
                nombre=fila["nombre"],
                especie=fila["especie"],
                usuario_id=fila["usuario_id"],
                dispositivo_id=fila["dispositivo_id"],
                ubicacion=fila["ubicacion"] or "",
                fecha_creacion=fila["fecha_creacion"],
            )

    def listar_por_usuario(self, usuario_id: int) -> List[Planta]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plantas WHERE usuario_id = ? ORDER BY id ASC", (usuario_id,))
            return [
                Planta(
                    id=fila["id"],
                    nombre=fila["nombre"],
                    especie=fila["especie"],
                    usuario_id=fila["usuario_id"],
                    dispositivo_id=fila["dispositivo_id"],
                    ubicacion=fila["ubicacion"] or "",
                    fecha_creacion=fila["fecha_creacion"],
                )
                for fila in cursor.fetchall()
            ]

    def obtener_por_dispositivo(self, dispositivo_id: str) -> Optional[Planta]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plantas WHERE UPPER(dispositivo_id) = ?", (dispositivo_id.upper(),))
            fila = cursor.fetchone()
            if not fila:
                return None
            return Planta(
                id=fila["id"],
                nombre=fila["nombre"],
                especie=fila["especie"],
                usuario_id=fila["usuario_id"],
                dispositivo_id=fila["dispositivo_id"],
                ubicacion=fila["ubicacion"] or "",
                fecha_creacion=fila["fecha_creacion"],
            )

    def vincular_dispositivo(self, planta_id: int, dispositivo_id: Optional[str]) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE plantas SET dispositivo_id = ? WHERE id = ?", (dispositivo_id, planta_id))
            if dispositivo_id:
                cursor.execute("UPDATE dispositivos SET planta_id = ? WHERE UPPER(id) = ?", (planta_id, dispositivo_id.upper()))
            else:
                cursor.execute("UPDATE dispositivos SET planta_id = NULL WHERE planta_id = ?", (planta_id,))
            conn.commit()

    def eliminar_planta(self, planta_id: int) -> bool:
        with self._conectar() as conn:
            cursor = conn.cursor()
            # 1. Desvincular cualquier sensor ESP32 para que quede disponible en la red
            cursor.execute("UPDATE dispositivos SET planta_id = NULL WHERE planta_id = ?", (planta_id,))
            # 2. Eliminar el historial de lecturas asociado a esta planta
            cursor.execute("DELETE FROM historial_lecturas WHERE planta_id = ?", (planta_id,))
            # 3. Eliminar el registro de la planta en la base de datos
            cursor.execute("DELETE FROM plantas WHERE id = ?", (planta_id,))
            filas_afectadas = cursor.rowcount
            conn.commit()
            return filas_afectadas > 0

    # --- RepositorioDispositivosPort ---
    @staticmethod
    def _fila_a_dispositivo(fila: sqlite3.Row) -> Dispositivo:
        claves = fila.keys()
        es_demo = bool(fila["es_demo"]) if "es_demo" in claves else False
        usuario_id = fila["usuario_id"] if "usuario_id" in claves else None
        return Dispositivo(
            id=fila["id"],
            secret_hash=fila["secret_hash"],
            mac=fila["mac"] or "",
            planta_id=fila["planta_id"],
            ultimo_contacto=fila["ultimo_contacto"],
            estado_conexion=fila["estado_conexion"],
            es_demo=es_demo,
            usuario_id=int(usuario_id) if usuario_id is not None else None,
        )

    def guardar_dispositivo(self, dispositivo: Dispositivo) -> Dispositivo:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO dispositivos 
                (id, secret_hash, mac, planta_id, ultimo_contacto, estado_conexion, es_demo, usuario_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dispositivo.id,
                    dispositivo.secret_hash,
                    dispositivo.mac,
                    dispositivo.planta_id,
                    dispositivo.ultimo_contacto,
                    dispositivo.estado_conexion,
                    1 if getattr(dispositivo, "es_demo", False) else 0,
                    getattr(dispositivo, "usuario_id", None),
                ),
            )
            conn.commit()
            return dispositivo

    def buscar_por_id(self, dispositivo_id: str) -> Optional[Dispositivo]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dispositivos WHERE UPPER(id) = ?", (dispositivo_id.upper(),))
            fila = cursor.fetchone()
            if not fila:
                return None
            return self._fila_a_dispositivo(fila)

    def listar_dispositivos(self, usuario_id: Optional[int] = None) -> List[Dispositivo]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            filtros = []
            params: list = []
            if not self._incluir_demo:
                filtros.append("COALESCE(es_demo, 0) = 0")
            if usuario_id is not None:
                filtros.append("usuario_id = ?")
                params.append(int(usuario_id))
            where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
            cursor.execute(f"SELECT * FROM dispositivos {where_sql} ORDER BY id ASC", params)
            return [self._fila_a_dispositivo(fila) for fila in cursor.fetchall()]

    def listar_dispositivos_disponibles(
        self,
        ventana_segundos: Optional[int] = None,
        usuario_id: Optional[int] = None,
    ) -> List[Dispositivo]:
        ventana = self._ventana_actividad_seg if ventana_segundos is None else max(1, int(ventana_segundos))
        with self._conectar() as conn:
            cursor = conn.cursor()
            filtros = ["(planta_id IS NULL OR planta_id = 0)", "usuario_id IS NOT NULL"]
            params: list = []
            if not self._incluir_demo:
                filtros.append("COALESCE(es_demo, 0) = 0")
            if usuario_id is not None:
                filtros.append("usuario_id = ?")
                params.append(int(usuario_id))
            cursor.execute(
                f"SELECT * FROM dispositivos WHERE {' AND '.join(filtros)} ORDER BY id ASC",
                params,
            )
            candidatos = [self._fila_a_dispositivo(fila) for fila in cursor.fetchall()]
            return [
                d
                for d in candidatos
                if evaluar_actividad_dispositivo(d.ultimo_contacto, d.estado_conexion, ventana)["en_linea"]
            ]

    def registrar_o_conectar_dispositivo(
        self,
        dispositivo_id: str,
        mac: Optional[str] = None,
        red_wifi: Optional[str] = None,
        liberar_planta: bool = False,
        usuario_id: Optional[int] = None,
    ) -> Dispositivo:
        ahora = datetime.datetime.now().isoformat()
        dev_id = dispositivo_id.strip().upper()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dispositivos WHERE UPPER(id) = ?", (dev_id,))
            fila = cursor.fetchone()
            if fila:
                mac_val = mac or fila["mac"] or f"24:6F:28:{dev_id[-4:]}"
                planta_id_val = fila["planta_id"]
                owner_actual = fila["usuario_id"] if "usuario_id" in fila.keys() else None
                owner_final = owner_actual if owner_actual is not None else usuario_id
                if liberar_planta and planta_id_val is not None:
                    cursor.execute(
                        "UPDATE plantas SET dispositivo_id = NULL WHERE UPPER(dispositivo_id) = ?",
                        (dev_id,),
                    )
                    cursor.execute(
                        "UPDATE dispositivos SET estado_conexion = ?, ultimo_contacto = ?, planta_id = NULL, usuario_id = ? WHERE UPPER(id) = ?",
                        (CONECTADO, ahora, owner_final, dev_id),
                    )
                    planta_id_val = None
                else:
                    cursor.execute(
                        "UPDATE dispositivos SET estado_conexion = ?, ultimo_contacto = ?, usuario_id = ? WHERE UPPER(id) = ?",
                        (CONECTADO, ahora, owner_final, dev_id),
                    )
                conn.commit()
                return Dispositivo(
                    id=dev_id,
                    secret_hash=fila["secret_hash"],
                    mac=mac_val,
                    planta_id=planta_id_val,
                    ultimo_contacto=ahora,
                    estado_conexion=CONECTADO,
                    usuario_id=int(owner_final) if owner_final is not None else None,
                )
            else:
                mac_val = mac or f"24:6F:28:{dev_id[-4:]}"
                cursor.execute(
                    """
                    INSERT INTO dispositivos (id, secret_hash, mac, planta_id, ultimo_contacto, estado_conexion, es_demo, usuario_id)
                    VALUES (?, ?, ?, NULL, ?, ?, 0, ?)
                    """,
                    (dev_id, "secret_hash_demo", mac_val, ahora, CONECTADO, usuario_id),
                )
                conn.commit()
                return Dispositivo(
                    id=dev_id,
                    secret_hash="secret_hash_demo",
                    mac=mac_val,
                    planta_id=None,
                    ultimo_contacto=ahora,
                    estado_conexion=CONECTADO,
                    usuario_id=usuario_id,
                )

    def actualizar_ultimo_contacto(self, dispositivo_id: str, fecha_hora: str) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE dispositivos SET ultimo_contacto = ?, estado_conexion = ? WHERE UPPER(id) = ?",
                (fecha_hora, CONECTADO, dispositivo_id.upper()),
            )
            conn.commit()

    def generar_codigo_vinculacion(self, dispositivo_id: str) -> str:
        caracteres = string.ascii_uppercase + string.digits
        codigo = "".join(random.choices(caracteres, k=6))
        ahora = datetime.datetime.now().isoformat()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO codigos_vinculacion (codigo, dispositivo_id, fecha_creacion, usado) VALUES (?, ?, ?, 0)",
                (codigo, dispositivo_id.upper(), ahora),
            )
            conn.commit()
        return codigo

    def consumir_codigo_vinculacion(self, codigo: str) -> Optional[str]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT dispositivo_id, usado FROM codigos_vinculacion WHERE codigo = ?",
                (codigo.strip().upper(),),
            )
            fila = cursor.fetchone()
            if not fila or fila["usado"] == 1:
                return None
            cursor.execute("UPDATE codigos_vinculacion SET usado = 1 WHERE codigo = ?", (codigo.strip().upper(),))
            conn.commit()
            return fila["dispositivo_id"]

    def guardar_token_pairing(self, token: str, usuario_id: int) -> None:
        ahora = datetime.datetime.now().isoformat()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO codigos_vinculacion (codigo, dispositivo_id, fecha_creacion, usado) VALUES (?, ?, ?, 0)",
                (token.strip().upper(), f"PAIRING-USER-{usuario_id}", ahora),
            )
            conn.commit()

    def consumir_token_pairing_con_usuario(self, token: str) -> Optional[int]:
        """Valida y consume atómicamente un token de pairing, retornando el usuario_id propietario."""
        if not token:
            return None
        token_norm = token.strip().upper()
        with self._conectar() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                fila = conn.execute(
                    "SELECT dispositivo_id, usado FROM codigos_vinculacion WHERE codigo = ?",
                    (token_norm,),
                ).fetchone()
                if not fila or fila["usado"] == 1:
                    conn.execute("ROLLBACK")
                    return None
                cur = conn.execute(
                    "UPDATE codigos_vinculacion SET usado = 1 WHERE codigo = ? AND usado = 0",
                    (token_norm,),
                )
                if cur.rowcount == 0:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute("COMMIT")
                ref = str(fila["dispositivo_id"] or "")
                if ref.startswith("PAIRING-USER-"):
                    try:
                        return int(ref.replace("PAIRING-USER-", "", 1))
                    except ValueError:
                        return None
                return None
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def validar_y_consumir_token_pairing(self, token: str) -> bool:
        if not token:
            return False
        token_norm = token.strip().upper()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT usado FROM codigos_vinculacion WHERE codigo = ?",
                (token_norm,),
            )
            fila = cursor.fetchone()
            if not fila or fila["usado"] == 1:
                return False
            cursor.execute("UPDATE codigos_vinculacion SET usado = 1 WHERE codigo = ?", (token_norm,))
            conn.commit()
            return True


# =====================================================================
# Adaptador 5: Servicio JWT con PyJWT (R7)
# =====================================================================

class ServicioJWT(EmisorTokenPort):
    """Implementa EmisorTokenPort utilizando la biblioteca PyJWT."""

    def __init__(self, clave_secreta: str = CLAVE_JWT_DEFECTO) -> None:
        self._clave = clave_secreta or CLAVE_JWT_DEFECTO
        self._algoritmo = "HS256"

    def emitir_token_usuario(self, usuario_id: int, username: str) -> str:
        payload = {
            "sub": str(usuario_id),
            "username": username,
            "scope": "usuario",
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        }
        return jwt.encode(payload, self._clave, algorithm=self._algoritmo)

    def emitir_token_dispositivo(self, dispositivo_id: str) -> str:
        payload = {
            "sub": str(dispositivo_id).strip().upper(),
            "scope": "dispositivo",
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=365),
        }
        return jwt.encode(payload, self._clave, algorithm=self._algoritmo)

    def verificar_token(self, token: str) -> Dict[str, Any]:
        return jwt.decode(token, self._clave, algorithms=[self._algoritmo])


# =====================================================================
# Adaptador 6: Repositorio de Gamificación en SQLite
# =====================================================================

class RepositorioGamificacionBD(RepositorioGamificacionPort):
    """Implementa RepositorioGamificacionPort persistido en SQLite."""

    def __init__(self, ruta_db: str) -> None:
        self._ruta_db = ruta_db
        dir_padre = os.path.dirname(os.path.abspath(self._ruta_db))
        if dir_padre:
            os.makedirs(dir_padre, exist_ok=True)
        self._inicializar_tablas()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._ruta_db, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar_tablas(self) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_puntos (
                    usuario_id INTEGER PRIMARY KEY,
                    saldo INTEGER NOT NULL DEFAULT 0,
                    actualizado_en TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_transacciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    planta_id INTEGER,
                    cantidad INTEGER NOT NULL,
                    motivo TEXT NOT NULL,
                    evento TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    clave_idempotencia TEXT
                )
                """
            )
            cursor.execute("PRAGMA table_info(gamificacion_transacciones)")
            cols_tx = {fila[1] for fila in cursor.fetchall()}
            if "clave_idempotencia" not in cols_tx:
                cursor.execute("ALTER TABLE gamificacion_transacciones ADD COLUMN clave_idempotencia TEXT")
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_idempotencia ON gamificacion_transacciones(clave_idempotencia) WHERE clave_idempotencia IS NOT NULL"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_saludos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    planta_id INTEGER NOT NULL,
                    fecha_dia TEXT NOT NULL,
                    UNIQUE(usuario_id, planta_id, fecha_dia)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_episodios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    planta_id INTEGER NOT NULL,
                    tipo_episodio TEXT NOT NULL,
                    inicio_utc TEXT NOT NULL,
                    ultimo_registro_utc TEXT NOT NULL,
                    recompensado_penalizado INTEGER NOT NULL DEFAULT 0,
                    activo INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_transacciones_usuario ON gamificacion_transacciones(usuario_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodios_planta ON gamificacion_episodios(planta_id, tipo_episodio)"
            )
            conn.commit()

    def obtener_saldo(self, usuario_id: int) -> int:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT saldo FROM gamificacion_puntos WHERE usuario_id = ?", (usuario_id,))
            fila = cursor.fetchone()
            if not fila:
                return 0
            return int(fila["saldo"])

    def registrar_transaccion(self, transaccion: TransaccionPuntos) -> TransaccionPuntos:
        ahora = transaccion.fecha or datetime.datetime.now(datetime.timezone.utc).isoformat()
        clave_idem = getattr(transaccion, "clave_idempotencia", None)
        with self._conectar() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.cursor()
                if clave_idem:
                    existente = cursor.execute(
                        "SELECT id FROM gamificacion_transacciones WHERE clave_idempotencia = ?",
                        (clave_idem,),
                    ).fetchone()
                    if existente is not None:
                        conn.execute("ROLLBACK")
                        return TransaccionPuntos(
                            id=int(existente["id"]),
                            usuario_id=transaccion.usuario_id,
                            planta_id=transaccion.planta_id,
                            cantidad=0,
                            motivo=transaccion.motivo,
                            evento=transaccion.evento,
                            fecha=ahora,
                            tipo=transaccion.tipo,
                            clave_idempotencia=clave_idem,
                        )

                cursor.execute(
                    """
                    INSERT INTO gamificacion_transacciones 
                    (usuario_id, planta_id, cantidad, motivo, evento, fecha, tipo, clave_idempotencia)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaccion.usuario_id,
                        transaccion.planta_id,
                        transaccion.cantidad,
                        transaccion.motivo,
                        transaccion.evento,
                        ahora,
                        transaccion.tipo,
                        clave_idem,
                    ),
                )
                tx_id = cursor.lastrowid

                cursor.execute("SELECT saldo FROM gamificacion_puntos WHERE usuario_id = ?", (transaccion.usuario_id,))
                fila = cursor.fetchone()
                if fila is None:
                    nuevo_saldo = max(0, transaccion.cantidad)
                    cursor.execute(
                        "INSERT INTO gamificacion_puntos (usuario_id, saldo, actualizado_en) VALUES (?, ?, ?)",
                        (transaccion.usuario_id, nuevo_saldo, ahora),
                    )
                else:
                    nuevo_saldo = max(0, int(fila["saldo"]) + transaccion.cantidad)
                    cursor.execute(
                        "UPDATE gamificacion_puntos SET saldo = ?, actualizado_en = ? WHERE usuario_id = ?",
                        (nuevo_saldo, ahora, transaccion.usuario_id),
                    )

                conn.execute("COMMIT")
                return TransaccionPuntos(
                    id=tx_id,
                    usuario_id=transaccion.usuario_id,
                    planta_id=transaccion.planta_id,
                    cantidad=transaccion.cantidad,
                    motivo=transaccion.motivo,
                    evento=transaccion.evento,
                    fecha=ahora,
                    tipo=transaccion.tipo,
                    clave_idempotencia=clave_idem,
                )
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")
                return TransaccionPuntos(
                    id=None,
                    usuario_id=transaccion.usuario_id,
                    planta_id=transaccion.planta_id,
                    cantidad=0,
                    motivo=transaccion.motivo,
                    evento=transaccion.evento,
                    fecha=ahora,
                    tipo=transaccion.tipo,
                    clave_idempotencia=clave_idem,
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def listar_transacciones(
        self, usuario_id: int, limite: int = 50
    ) -> List[TransaccionPuntos]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, usuario_id, planta_id, cantidad, motivo, evento, fecha, tipo
                FROM gamificacion_transacciones
                WHERE usuario_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (usuario_id, limite),
            )
            filas = cursor.fetchall()
            return [
                TransaccionPuntos(
                    id=f["id"],
                    usuario_id=f["usuario_id"],
                    planta_id=f["planta_id"],
                    cantidad=f["cantidad"],
                    motivo=f["motivo"],
                    evento=f["evento"],
                    fecha=f["fecha"],
                    tipo=f["tipo"],
                )
                for f in filas
            ]

    def registrar_saludo_hoy(self, usuario_id: int, planta_id: int, fecha_dia: str) -> bool:
        try:
            with self._conectar() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO gamificacion_saludos (usuario_id, planta_id, fecha_dia) VALUES (?, ?, ?)",
                    (usuario_id, planta_id, fecha_dia),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def ya_saludo_hoy(self, usuario_id: int, planta_id: int, fecha_dia: str) -> bool:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM gamificacion_saludos WHERE usuario_id = ? AND planta_id = ? AND fecha_dia = ?",
                (usuario_id, planta_id, fecha_dia),
            )
            return cursor.fetchone() is not None

    def obtener_episodio_activo(
        self, planta_id: int, tipo_episodio: str
    ) -> Optional[EpisodioGamificacion]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, planta_id, tipo_episodio, inicio_utc, ultimo_registro_utc,
                       recompensado_penalizado, activo
                FROM gamificacion_episodios
                WHERE planta_id = ? AND tipo_episodio = ? AND activo = 1
                ORDER BY id DESC LIMIT 1
                """,
                (planta_id, tipo_episodio),
            )
            f = cursor.fetchone()
            if not f:
                return None
            return EpisodioGamificacion(
                id=f["id"],
                planta_id=f["planta_id"],
                tipo_episodio=f["tipo_episodio"],
                inicio_utc=f["inicio_utc"],
                ultimo_registro_utc=f["ultimo_registro_utc"],
                recompensado_penalizado=bool(f["recompensado_penalizado"]),
                activo=bool(f["activo"]),
            )

    def guardar_episodio(self, episodio: EpisodioGamificacion) -> EpisodioGamificacion:
        with self._conectar() as conn:
            cursor = conn.cursor()
            if episodio.id:
                cursor.execute(
                    """
                    UPDATE gamificacion_episodios 
                    SET inicio_utc = ?, ultimo_registro_utc = ?, recompensado_penalizado = ?, activo = ?
                    WHERE id = ?
                    """,
                    (
                        episodio.inicio_utc,
                        episodio.ultimo_registro_utc,
                        1 if episodio.recompensado_penalizado else 0,
                        1 if episodio.activo else 0,
                        episodio.id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO gamificacion_episodios 
                    (planta_id, tipo_episodio, inicio_utc, ultimo_registro_utc, recompensado_penalizado, activo)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episodio.planta_id,
                        episodio.tipo_episodio,
                        episodio.inicio_utc,
                        episodio.ultimo_registro_utc,
                        1 if episodio.recompensado_penalizado else 0,
                        1 if episodio.activo else 0,
                    ),
                )
                episodio.id = cursor.lastrowid
            conn.commit()
            return episodio

    def cerrar_episodios_activos(
        self, planta_id: int, excluir_tipo: Optional[str] = None
    ) -> None:
        with self._conectar() as conn:
            cursor = conn.cursor()
            if excluir_tipo:
                cursor.execute(
                    "UPDATE gamificacion_episodios SET activo = 0 WHERE planta_id = ? AND activo = 1 AND tipo_episodio != ?",
                    (planta_id, excluir_tipo),
                )
            else:
                cursor.execute(
                    "UPDATE gamificacion_episodios SET activo = 0 WHERE planta_id = ? AND activo = 1",
                    (planta_id,),
                )
            conn.commit()


