"""
Adaptador de Salida SQLite para Gamificación Avanzada de Plantol.
Implementa RepositorioGamificacionAvanzadaPort con transacciones atómicas
para compras, progresión XP/niveles, misiones, logros, inventario y habitación virtual.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
from typing import Any, Dict, List, Optional

from Modelo.gamificacion_avanzada import (
    MAPA_CATALOGO,
    TIPO_COMPRA,
    ArticuloTienda,
    ObjetoYaPoseidoError,
    SaldoInsuficienteError,
)


class RepositorioGamificacionAvanzadaSQLite:
    """Adaptador SQLite para progresión, misiones, logros, tienda, inventario y habitación."""

    def __init__(self, ruta_db: str) -> None:
        self._ruta_db = ruta_db
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
                CREATE TABLE IF NOT EXISTS gamificacion_progresion (
                    usuario_id INTEGER PRIMARY KEY,
                    xp_total INTEGER NOT NULL DEFAULT 0,
                    actualizado_en TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_misiones (
                    usuario_id INTEGER NOT NULL,
                    mision_id TEXT NOT NULL,
                    periodo TEXT NOT NULL,
                    completada INTEGER NOT NULL DEFAULT 1,
                    completada_en TEXT NOT NULL,
                    PRIMARY KEY (usuario_id, mision_id, periodo)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_logros (
                    usuario_id INTEGER NOT NULL,
                    logro_id TEXT NOT NULL,
                    desbloqueado_en TEXT NOT NULL,
                    PRIMARY KEY (usuario_id, logro_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_inventario (
                    usuario_id INTEGER NOT NULL,
                    objeto_id TEXT NOT NULL,
                    cantidad INTEGER NOT NULL DEFAULT 1,
                    adquirido_en TEXT NOT NULL,
                    PRIMARY KEY (usuario_id, objeto_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gamificacion_habitacion (
                    usuario_id INTEGER PRIMARY KEY,
                    slots_json TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                )
                """
            )

    def obtener_xp(self, usuario_id: int) -> int:
        with self._conectar() as conn:
            fila = conn.execute(
                "SELECT xp_total FROM gamificacion_progresion WHERE usuario_id = ?",
                (usuario_id,),
            ).fetchone()
            return int(fila["xp_total"]) if fila else 0

    def sumar_xp(self, usuario_id: int, delta_xp: int) -> int:
        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conectar() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                fila = conn.execute(
                    "SELECT xp_total FROM gamificacion_progresion WHERE usuario_id = ?",
                    (usuario_id,),
                ).fetchone()
                actual = int(fila["xp_total"]) if fila else 0
                nuevo = max(0, actual + int(delta_xp))
                if fila is None:
                    conn.execute(
                        "INSERT INTO gamificacion_progresion (usuario_id, xp_total, actualizado_en) VALUES (?, ?, ?)",
                        (usuario_id, nuevo, ahora),
                    )
                else:
                    conn.execute(
                        "UPDATE gamificacion_progresion SET xp_total = ?, actualizado_en = ? WHERE usuario_id = ?",
                        (nuevo, ahora, usuario_id),
                    )
                conn.execute("COMMIT")
                return nuevo
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def obtener_estado_misiones(self, usuario_id: int, fecha_dia: str) -> Dict[str, Dict[str, Any]]:
        with self._conectar() as conn:
            filas = conn.execute(
                """
                SELECT mision_id, periodo, completada, completada_en
                FROM gamificacion_misiones
                WHERE usuario_id = ? AND (periodo = ? OR periodo = 'PERMANENTE')
                """,
                (usuario_id, fecha_dia),
            ).fetchall()
            return {
                f"{f['mision_id']}:{f['periodo']}": {
                    "completada": bool(f["completada"]),
                    "completada_en": f["completada_en"],
                }
                for f in filas
            }

    def marcar_mision_completada(self, usuario_id: int, mision_id: str, periodo: str) -> bool:
        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conectar() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO gamificacion_misiones
                    (usuario_id, mision_id, periodo, completada, completada_en)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (usuario_id, mision_id, periodo, ahora),
                )
                conn.execute("COMMIT")
                return cursor.rowcount > 0
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def listar_logros_desbloqueados(self, usuario_id: int) -> Dict[str, str]:
        with self._conectar() as conn:
            filas = conn.execute(
                "SELECT logro_id, desbloqueado_en FROM gamificacion_logros WHERE usuario_id = ?",
                (usuario_id,),
            ).fetchall()
            return {f["logro_id"]: f["desbloqueado_en"] for f in filas}

    def desbloquear_logro(self, usuario_id: int, logro_id: str, fecha_iso: str) -> bool:
        with self._conectar() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO gamificacion_logros (usuario_id, logro_id, desbloqueado_en)
                    VALUES (?, ?, ?)
                    """,
                    (usuario_id, logro_id, fecha_iso),
                )
                conn.execute("COMMIT")
                return cursor.rowcount > 0
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def listar_inventario(self, usuario_id: int) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            filas = conn.execute(
                """
                SELECT objeto_id, cantidad, adquirido_en
                FROM gamificacion_inventario
                WHERE usuario_id = ?
                ORDER BY adquirido_en DESC
                """,
                (usuario_id,),
            ).fetchall()
            resultado = []
            for f in filas:
                art = MAPA_CATALOGO.get(f["objeto_id"])
                if not art:
                    continue
                resultado.append({
                    "objeto_id": f["objeto_id"],
                    "cantidad": int(f["cantidad"]),
                    "adquirido_en": f["adquirido_en"],
                    "nombre": art.nombre,
                    "descripcion": art.descripcion,
                    "categoria": art.categoria,
                    "icono": art.icono,
                    "slot_habitacion": art.slot_habitacion,
                    "rareza": art.rareza,
                })
            return resultado

    def comprar_articulo_atomico(
        self, usuario_id: int, articulo: ArticuloTienda, fecha_iso: str
    ) -> Dict[str, Any]:
        with self._conectar() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                inv = conn.execute(
                    "SELECT cantidad FROM gamificacion_inventario WHERE usuario_id = ? AND objeto_id = ?",
                    (usuario_id, articulo.id),
                ).fetchone()
                if inv is not None and articulo.tipo == "unico":
                    raise ObjetoYaPoseidoError(articulo.id)

                fila_saldo = conn.execute(
                    "SELECT saldo FROM gamificacion_puntos WHERE usuario_id = ?",
                    (usuario_id,),
                ).fetchone()
                saldo_actual = int(fila_saldo["saldo"]) if fila_saldo else 0
                if saldo_actual < articulo.precio:
                    raise SaldoInsuficienteError(saldo_actual, articulo.precio)

                nuevo_saldo = saldo_actual - articulo.precio
                conn.execute(
                    "UPDATE gamificacion_puntos SET saldo = ?, actualizado_en = ? WHERE usuario_id = ?",
                    (nuevo_saldo, fecha_iso, usuario_id),
                )
                conn.execute(
                    """
                    INSERT INTO gamificacion_transacciones
                    (usuario_id, planta_id, cantidad, motivo, evento, fecha, tipo)
                    VALUES (?, NULL, ?, 'COMPRA_TIENDA', ?, ?, ?)
                    """,
                    (usuario_id, -articulo.precio, f"Compra en tienda: {articulo.nombre}", fecha_iso, TIPO_COMPRA),
                )
                if inv is None:
                    conn.execute(
                        """
                        INSERT INTO gamificacion_inventario (usuario_id, objeto_id, cantidad, adquirido_en)
                        VALUES (?, ?, 1, ?)
                        """,
                        (usuario_id, articulo.id, fecha_iso),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE gamificacion_inventario SET cantidad = cantidad + 1
                        WHERE usuario_id = ? AND objeto_id = ?
                        """,
                        (usuario_id, articulo.id),
                    )
                conn.execute("COMMIT")
                return {"nuevo_saldo": nuevo_saldo}
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def obtener_habitacion(self, usuario_id: int) -> Dict[str, Any]:
        default_slots: Dict[str, Optional[str]] = {
            "fondo": None,
            "alfombra": None,
            "mueble": None,
            "maceta": None,
            "lampara": None,
            "decoracion": None,
        }
        with self._conectar() as conn:
            fila = conn.execute(
                "SELECT slots_json, actualizado_en FROM gamificacion_habitacion WHERE usuario_id = ?",
                (usuario_id,),
            ).fetchone()
            if not fila:
                return {"slots": default_slots, "actualizado_en": None}
            try:
                guardados = json.loads(fila["slots_json"]) or {}
            except Exception:
                guardados = {}
            combinados = {**default_slots, **{k: guardados.get(k) for k in default_slots}}
            return {"slots": combinados, "actualizado_en": fila["actualizado_en"]}

    def guardar_habitacion(self, usuario_id: int, slots: Dict[str, Optional[str]], fecha_iso: str) -> Dict[str, Any]:
        slots_json = json.dumps(slots)
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO gamificacion_habitacion (usuario_id, slots_json, actualizado_en)
                VALUES (?, ?, ?)
                ON CONFLICT(usuario_id) DO UPDATE SET slots_json = excluded.slots_json, actualizado_en = excluded.actualizado_en
                """,
                (usuario_id, slots_json, fecha_iso),
            )
        return {"slots": slots, "actualizado_en": fecha_iso}
