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
    Lectura,
    Planta,
    RangosEspecie,
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
        conn = sqlite3.connect(self._ruta_db)
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
        conn = sqlite3.connect(self._ruta_db)
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
                    fecha_creacion TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_historial_dispositivo ON historial_lecturas(dispositivo_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_historial_planta ON historial_lecturas(planta_id)"
            )
            conn.commit()

    def guardar_lectura(
        self, lectura: Lectura, diagnostico: Optional[DiagnosticoPlanta] = None
    ) -> None:
        diag_json = json.dumps(diagnostico.to_dict()) if diagnostico else None
        estado = diagnostico.estado_global if diagnostico else None
        ahora = datetime.datetime.now().isoformat()

        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO historial_lecturas 
                (dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura, estado_global, diagnostico_json, fecha_creacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()

    def obtener_ultima_lectura(self, dispositivo_id: str) -> Optional[Lectura]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura
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
            )

    def obtener_ultima_lectura_por_planta(self, planta_id: int) -> Optional[Lectura]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura
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
            )

    def obtener_historial_por_planta(
        self, planta_id: int, limite: int = 50
    ) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dispositivo_id, planta_id, timestamp, luminosidad, humedad, temperatura,
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

class RepositorioSQLite(
    RepositorioPlantasPort,
    RepositorioUsuariosPort,
    RepositorioDispositivosPort,
):
    """Implementa almacenamiento de entidades en base de datos SQLite."""

    def __init__(self, ruta_db: str) -> None:
        self._ruta_db = ruta_db
        dir_padre = os.path.dirname(os.path.abspath(self._ruta_db))
        if dir_padre:
            os.makedirs(dir_padre, exist_ok=True)
        self._inicializar_tablas()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._ruta_db)
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
            conn.commit()

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
                cursor.execute("UPDATE dispositivos SET planta_id = ? WHERE id = ?", (planta_id, dispositivo_id))
            conn.commit()

    # --- RepositorioDispositivosPort ---
    def guardar_dispositivo(self, dispositivo: Dispositivo) -> Dispositivo:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO dispositivos 
                (id, secret_hash, mac, planta_id, ultimo_contacto, estado_conexion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dispositivo.id,
                    dispositivo.secret_hash,
                    dispositivo.mac,
                    dispositivo.planta_id,
                    dispositivo.ultimo_contacto,
                    dispositivo.estado_conexion,
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
            return Dispositivo(
                id=fila["id"],
                secret_hash=fila["secret_hash"],
                mac=fila["mac"] or "",
                planta_id=fila["planta_id"],
                ultimo_contacto=fila["ultimo_contacto"],
                estado_conexion=fila["estado_conexion"],
            )

    def listar_dispositivos(self) -> List[Dispositivo]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dispositivos ORDER BY id ASC")
            return [
                Dispositivo(
                    id=fila["id"],
                    secret_hash=fila["secret_hash"],
                    mac=fila["mac"] or "",
                    planta_id=fila["planta_id"],
                    ultimo_contacto=fila["ultimo_contacto"],
                    estado_conexion=fila["estado_conexion"],
                )
                for fila in cursor.fetchall()
            ]

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

