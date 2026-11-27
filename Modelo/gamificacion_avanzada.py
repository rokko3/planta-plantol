"""
Núcleo de Dominio Puro para Gamificación Avanzada de Plantol.
Contiene:
- Progresión (XP, niveles y títulos botánicos)
- Catálogo oficial de la Tienda (precios y requisitos autoritativos en backend)
- Definición de Misiones (diarias y progresivas) y Logros permanentes
- Puertos y Caso de Uso de Gamificación Avanzada

Restricción arquitectural estricta (Hexagonal):
Este módulo NO importa Flask, HTTP, SQLite, CSV, JSON ni bibliotecas JWT.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from Modelo.entidades import (
    SALUDABLE,
    TIPO_RECOMPENSA,
    TransaccionPuntos,
)
from Modelo.puertos import RepositorioGamificacionPort, RepositorioPlantasPort

TIPO_COMPRA = "COMPRA"


# =====================================================================
# Excepciones de Dominio de Gamificación Avanzada
# =====================================================================

class SaldoInsuficienteError(Exception):
    def __init__(self, saldo: int, precio: int) -> None:
        super().__init__(f"Saldo insuficiente ({saldo} monedas) para adquirir un objeto de {precio} monedas.")


class NivelInsuficienteError(Exception):
    def __init__(self, nivel_actual: int, nivel_requerido: int) -> None:
        super().__init__(f"Necesitas alcanzar el nivel {nivel_requerido} para desbloquear este objeto (nivel actual: {nivel_actual}).")


class ObjetoNoEncontradoError(Exception):
    def __init__(self, objeto_id: str) -> None:
        super().__init__(f"El objeto '{objeto_id}' no existe en el catálogo.")


class ObjetoYaPoseidoError(Exception):
    def __init__(self, objeto_id: str) -> None:
        super().__init__(f"Ya posees el objeto único '{objeto_id}' en tu inventario.")


class ObjetoNoPoseidoError(Exception):
    def __init__(self, objeto_id: str) -> None:
        super().__init__(f"No posees '{objeto_id}' en tu inventario.")


# =====================================================================
# Entidades de Progresión, Catálogo, Misiones, Logros y Habitación
# =====================================================================

TITULOS_NIVEL: Dict[int, str] = {
    1: "Semilla Curiosa",
    2: "Brote Verde",
    3: "Cuidador Dedicado",
    4: "Jardinero Urbano",
    5: "Botánico Experto",
    6: "Guardián del Invernadero",
}


def calcular_progresion_nivel(xp_total: int) -> Dict[str, Any]:
    """Calcula nivel actual, XP dentro del nivel y XP necesaria para el siguiente."""
    xp = max(0, int(xp_total))
    nivel = 1
    xp_restante = xp
    while True:
        costo_nivel = 100 * nivel
        if xp_restante < costo_nivel:
            break
        xp_restante -= costo_nivel
        nivel += 1

    costo_actual = 100 * nivel
    titulo = TITULOS_NIVEL.get(nivel, f"Maestro Botánico Nv.{nivel}")
    porcentaje = min(100, round((xp_restante / costo_actual) * 100)) if costo_actual > 0 else 100
    return {
        "xp_total": xp,
        "nivel": nivel,
        "titulo": titulo,
        "xp_en_nivel": xp_restante,
        "xp_siguiente_nivel": costo_actual,
        "porcentaje_nivel": porcentaje,
    }


@dataclass(frozen=True)
class ArticuloTienda:
    id: str
    nombre: str
    descripcion: str
    categoria: str  # maceta, mueble, lampara, alfombra, decoracion, planta_deco, fondo
    precio: int
    nivel_requerido: int = 1
    tipo: str = "unico"  # unico | consumible
    icono: str = "🪴"
    slot_habitacion: str = "decoracion"
    rareza: str = "comun"  # comun | rara | epica | legendaria

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "categoria": self.categoria,
            "precio": self.precio,
            "nivel_requerido": self.nivel_requerido,
            "tipo": self.tipo,
            "icono": self.icono,
            "slot_habitacion": self.slot_habitacion,
            "rareza": self.rareza,
        }


CATALOGO_TIENDA: List[ArticuloTienda] = [
    ArticuloTienda("maceta_terracota", "Maceta Terracota Clásica", "Maceta artesanal de barro cálido para tus plantas.", "maceta", 12, 1, "unico", "🪴", "maceta", "comun"),
    ArticuloTienda("deco_regadera_cobre", "Regadera de Cobre", "Accesorio decorativo clásico de jardinería.", "decoracion", 16, 1, "unico", "🚿", "decoracion", "comun"),
    ArticuloTienda("alfombra_yute", "Alfombra de Yute Natural", "Tapete tejido que aporta calidez al rincón botánico.", "alfombra", 18, 1, "unico", "🟫", "alfombra", "comun"),
    ArticuloTienda("fondo_invernadero_dia", "Ventanal Soleado", "Fondo luminoso con entrada de luz natural.", "fondo", 20, 1, "unico", "🪟", "fondo", "comun"),
    ArticuloTienda("mueble_repisa_roble", "Repisa de Roble", "Estantería de madera clara para exhibir tus materas.", "mueble", 22, 1, "unico", "🪵", "mueble", "comun"),
    ArticuloTienda("deco_helecho_colgante", "Helecho Colgante", "Planta decorativa para dar vida a la pared.", "planta_deco", 42, 2, "unico", "🌿", "decoracion", "rara"),
    ArticuloTienda("maceta_ceramica_menta", "Maceta Cerámica Menta", "Acabado esmaltado verde menta estilo nórdico.", "maceta", 45, 2, "unico", "🏺", "maceta", "rara"),
    ArticuloTienda("lampara_crecimiento", "Lámpara de Luz Cálida", "Iluminación ambiental suave para el invernadero.", "lampara", 48, 2, "unico", "💡", "lampara", "rara"),
    ArticuloTienda("alfombra_bosque", "Alfombra Musgo Suave", "Tapete verde inspirado en el suelo del bosque.", "alfombra", 50, 2, "unico", "🟩", "alfombra", "rara"),
    ArticuloTienda("mueble_escritorio_botanico", "Escritorio Botánico", "Mesa de trabajo para cuidar y observar tus plantas.", "mueble", 60, 2, "unico", "🪑", "mueble", "rara"),
    ArticuloTienda("fondo_noche_estrellada", "Invernadero Nocturno", "Ambiente sereno bajo luz de luna.", "fondo", 95, 3, "unico", "🌙", "fondo", "epica"),
    ArticuloTienda("maceta_dorada", "Maceta Solar Dorada", "Edición especial para cuidadores constantes.", "maceta", 140, 3, "unico", "✨", "maceta", "legendaria"),
]

MAPA_CATALOGO: Dict[str, ArticuloTienda] = {a.id: a for a in CATALOGO_TIENDA}


@dataclass(frozen=True)
class DefinicionMision:
    id: str
    titulo: str
    descripcion: str
    tipo: str  # diaria | progresiva
    meta: int
    recompensa_monedas: int
    recompensa_xp: int


MISIONES_DEFINICION: List[DefinicionMision] = [
    DefinicionMision(
        "MISION_LECTURA_ACTIVA",
        "Pulso del invernadero",
        "Mantén al menos 1 planta con lecturas activas de sensor hoy.",
        "diaria",
        1,
        2,
        20,
    ),
    DefinicionMision(
        "MISION_PLANTA_SALUDABLE",
        "Cuidado en equilibrio",
        "Logra que al menos 1 planta esté en estado SALUDABLE hoy.",
        "diaria",
        1,
        3,
        25,
    ),
]


@dataclass(frozen=True)
class DefinicionLogro:
    id: str
    titulo: str
    descripcion: str
    icono: str
    meta: int
    recompensa_monedas: int
    recompensa_xp: int


LOGROS_DEFINICION: List[DefinicionLogro] = [
    DefinicionLogro("LOGRO_PRIMER_RESCATE", "Rescatista Botánico", "Recupera una planta que estaba en estado crítico.", "💧", 1, 5, 40),
    DefinicionLogro("LOGRO_PRIMERA_COMPRA", "Primer Tesoro", "Adquiere tu primer objeto en la tienda virtual.", "🛍️", 1, 2, 20),
    DefinicionLogro("LOGRO_DECORADOR", "Diseñador de Espacios", "Coloca un objeto en tu habitación virtual.", "🏡", 1, 3, 25),
    DefinicionLogro("LOGRO_NIVEL_3", "Cuidador Dedicado", "Alcanza el Nivel 3 de experiencia.", "🏆", 3, 8, 50),
]


# =====================================================================
# Puerto de Salida para Persistencia Avanzada de Gamificación
# =====================================================================

@runtime_checkable
class RepositorioGamificacionAvanzadaPort(Protocol):
    def obtener_xp(self, usuario_id: int) -> int:
        ...

    def sumar_xp(self, usuario_id: int, delta_xp: int) -> int:
        ...

    def obtener_estado_misiones(self, usuario_id: int, fecha_dia: str) -> Dict[str, Dict[str, Any]]:
        ...

    def marcar_mision_completada(self, usuario_id: int, mision_id: str, periodo: str) -> bool:
        """Registra la misión como completada una sola vez para el periodo. True si es nueva."""
        ...

    def listar_logros_desbloqueados(self, usuario_id: int) -> Dict[str, str]:
        """Retorna {logro_id: fecha_desbloqueo_iso}."""
        ...

    def desbloquear_logro(self, usuario_id: int, logro_id: str, fecha_iso: str) -> bool:
        """Desbloquea el logro de forma idempotente. True si es nuevo."""
        ...

    def listar_inventario(self, usuario_id: int) -> List[Dict[str, Any]]:
        ...

    def comprar_articulo_atomico(
        self, usuario_id: int, articulo: ArticuloTienda, fecha_iso: str
    ) -> Dict[str, Any]:
        ...

    def obtener_habitacion(self, usuario_id: int) -> Dict[str, Any]:
        ...

    def guardar_habitacion(self, usuario_id: int, slots: Dict[str, Optional[str]], fecha_iso: str) -> Dict[str, Any]:
        ...


# =====================================================================
# Caso de Uso de Gamificación Avanzada
# =====================================================================

class CasoUsoGamificacionAvanzada:
    """Orquesta XP, niveles, misiones verificables, logros, tienda, inventario y habitación."""

    def __init__(
        self,
        repo_base: RepositorioGamificacionPort,
        repo_avanzada: RepositorioGamificacionAvanzadaPort,
        repo_plantas: RepositorioPlantasPort,
        consultar_estado_port: Any = None,
    ) -> None:
        self._base = repo_base
        self._avanzada = repo_avanzada
        self._plantas = repo_plantas
        self._consultar_estado = consultar_estado_port

    def _otorgar_recompensa(
        self,
        usuario_id: int,
        monedas: int,
        xp: int,
        motivo: str,
        evento: str,
        planta_id: Optional[int] = None,
        clave_idempotencia: Optional[str] = None,
    ) -> None:
        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if monedas > 0:
            self._base.registrar_transaccion(
                TransaccionPuntos(
                    id=None,
                    usuario_id=usuario_id,
                    planta_id=planta_id,
                    cantidad=monedas,
                    motivo=motivo,
                    evento=evento,
                    fecha=ahora,
                    tipo=TIPO_RECOMPENSA,
                    clave_idempotencia=clave_idempotencia,
                )
            )
        if xp > 0:
            xp_antes = self._avanzada.obtener_xp(usuario_id)
            niv_antes = calcular_progresion_nivel(xp_antes)["nivel"]
            xp_despues = self._avanzada.sumar_xp(usuario_id, xp)
            niv_despues = calcular_progresion_nivel(xp_despues)["nivel"]
            if niv_despues > niv_antes:
                bono = 5 * (niv_despues - niv_antes)
                self._base.registrar_transaccion(
                    TransaccionPuntos(
                        id=None,
                        usuario_id=usuario_id,
                        planta_id=None,
                        cantidad=bono,
                        motivo="SUBIDA_NIVEL",
                        evento=f"¡Subiste al Nivel {niv_despues}!",
                        fecha=ahora,
                        tipo=TIPO_RECOMPENSA,
                        clave_idempotencia=f"NIVEL:{usuario_id}:{niv_antes}->{niv_despues}",
                    )
                )

    @staticmethod
    def _es_lectura_de_hoy(ultima_lectura: Optional[Dict[str, Any]], hoy_utc: str) -> bool:
        if not isinstance(ultima_lectura, dict):
            return False
        ts = ultima_lectura.get("timestamp")
        if not ts:
            return False
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            return False
        hoy_local = datetime.datetime.now().strftime("%Y-%m-%d")
        if dt.tzinfo is not None:
            fecha_utc = dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d")
            return fecha_utc == hoy_utc
        return dt.strftime("%Y-%m-%d") in (hoy_utc, hoy_local)

    def sincronizar_progreso_usuario(self, usuario_id: int) -> Dict[str, Any]:
        """
        Evalúa de forma idempotente misiones y logros respaldados por hechos reales
        del día actual y plantas con hardware vinculado (evita recompensas pasivas o por plantas vacías).
        """
        hoy = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        ahora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        plantas_usuario = self._plantas.listar_por_usuario(usuario_id)
        plantas_con_sensor = [p for p in plantas_usuario if p.dispositivo_id]
        num_plantas_sensor = len(plantas_con_sensor)

        txs = self._base.listar_transacciones(usuario_id, limite=200)

        tiene_lectura_hoy = False
        tiene_saludable_hoy = False
        if self._consultar_estado is not None and num_plantas_sensor > 0:
            plantas_estado = self._consultar_estado.consultar_plantas_usuario(usuario_id)
            for pe in plantas_estado:
                if not pe.get("dispositivo_id"):
                    continue
                if self._es_lectura_de_hoy(pe.get("ultima_lectura"), hoy):
                    tiene_lectura_hoy = True
                    if pe.get("estado_global") == SALUDABLE:
                        tiene_saludable_hoy = True

        # Evaluar misiones verificables (solo cuidado real con sensor)
        progreso_misiones = {
            "MISION_LECTURA_ACTIVA": 1 if tiene_lectura_hoy else 0,
            "MISION_PLANTA_SALUDABLE": 1 if tiene_saludable_hoy else 0,
        }
        for m in MISIONES_DEFINICION:
            periodo = hoy if m.tipo == "diaria" else "PERMANENTE"
            if progreso_misiones.get(m.id, 0) >= m.meta:
                if self._avanzada.marcar_mision_completada(usuario_id, m.id, periodo):
                    self._otorgar_recompensa(
                        usuario_id,
                        m.recompensa_monedas,
                        m.recompensa_xp,
                        "MISION_COMPLETADA",
                        f"Misión completada: {m.titulo}",
                        clave_idempotencia=f"MISION:{m.id}:{periodo}:{usuario_id}",
                    )

        # Evaluar logros permanentes basados en eventos reales de cuidado (no por crear/saludar plantas)
        tuvo_rescate = any(t.motivo == "RESCATE_HUMEDAD" and t.cantidad > 0 for t in txs)
        inventario = self._avanzada.listar_inventario(usuario_id)
        habitacion = self._avanzada.obtener_habitacion(usuario_id)
        slots_colocados = sum(1 for v in (habitacion.get("slots") or {}).values() if v)
        nivel_actual = calcular_progresion_nivel(self._avanzada.obtener_xp(usuario_id))["nivel"]

        progreso_logros = {
            "LOGRO_PRIMER_RESCATE": 1 if tuvo_rescate else 0,
            "LOGRO_PRIMERA_COMPRA": len(inventario),
            "LOGRO_DECORADOR": slots_colocados,
            "LOGRO_NIVEL_3": nivel_actual,
        }
        for lg in LOGROS_DEFINICION:
            if progreso_logros.get(lg.id, 0) >= lg.meta:
                if self._avanzada.desbloquear_logro(usuario_id, lg.id, ahora_iso):
                    self._otorgar_recompensa(
                        usuario_id,
                        lg.recompensa_monedas,
                        lg.recompensa_xp,
                        "LOGRO_DESBLOQUEADO",
                        f"Logro desbloqueado: {lg.titulo}",
                        clave_idempotencia=f"LOGRO:{lg.id}:{usuario_id}",
                    )

        return self.obtener_resumen_completo(usuario_id)

    def obtener_resumen_completo(self, usuario_id: int) -> Dict[str, Any]:
        hoy = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        saldo = self._base.obtener_saldo(usuario_id)
        xp_total = self._avanzada.obtener_xp(usuario_id)
        progresion = calcular_progresion_nivel(xp_total)
        estado_misiones = self._avanzada.obtener_estado_misiones(usuario_id, hoy)
        logros_desbloqueados = self._avanzada.listar_logros_desbloqueados(usuario_id)
        inventario = self._avanzada.listar_inventario(usuario_id)
        habitacion = self._avanzada.obtener_habitacion(usuario_id)

        plantas_usuario = self._plantas.listar_por_usuario(usuario_id)
        num_plantas_sensor = sum(1 for p in plantas_usuario if p.dispositivo_id)
        txs = self._base.listar_transacciones(usuario_id, limite=100)
        saludo_recompensado_hoy = any(
            t.motivo == "SALUDO_DIARIO" and str(t.fecha or "").startswith(hoy) and t.cantidad > 0
            for t in txs
        )

        misiones_out = []
        for m in MISIONES_DEFINICION:
            periodo = hoy if m.tipo == "diaria" else "PERMANENTE"
            reg = estado_misiones.get(f"{m.id}:{periodo}")
            completada = bool(reg and reg.get("completada"))
            prog = m.meta if completada else (
                1 if (m.id == "MISION_SALUDO_DIARIO" and saludo_recompensado_hoy)
                else (min(num_plantas_sensor, m.meta) if m.id == "MISION_COLECCION_VERDE" else 0)
            )
            misiones_out.append({
                "id": m.id,
                "titulo": m.titulo,
                "descripcion": m.descripcion,
                "tipo": m.tipo,
                "progreso": prog,
                "meta": m.meta,
                "completada": completada,
                "recompensa_monedas": m.recompensa_monedas,
                "recompensa_xp": m.recompensa_xp,
            })

        logros_out = []
        for lg in LOGROS_DEFINICION:
            fecha_desb = logros_desbloqueados.get(lg.id)
            logros_out.append({
                "id": lg.id,
                "titulo": lg.titulo,
                "descripcion": lg.descripcion,
                "icono": lg.icono,
                "desbloqueado": fecha_desb is not None,
                "fecha_desbloqueo": fecha_desb,
                "recompensa_monedas": lg.recompensa_monedas,
                "recompensa_xp": lg.recompensa_xp,
            })

        ids_poseidos = {item["objeto_id"] for item in inventario}
        catalogo_out = []
        for art in CATALOGO_TIENDA:
            d = art.to_dict()
            d["poseido"] = art.id in ids_poseidos
            d["desbloqueado_nivel"] = progresion["nivel"] >= art.nivel_requerido
            catalogo_out.append(d)

        return {
            "usuario_id": usuario_id,
            "monedas": saldo,
            "progresion": progresion,
            "misiones": misiones_out,
            "logros": logros_out,
            "catalogo": catalogo_out,
            "inventario": inventario,
            "habitacion": habitacion,
        }

    def comprar_articulo(self, usuario_id: int, objeto_id: str) -> Dict[str, Any]:
        articulo = MAPA_CATALOGO.get(objeto_id)
        if not articulo:
            raise ObjetoNoEncontradoError(objeto_id)

        progresion = calcular_progresion_nivel(self._avanzada.obtener_xp(usuario_id))
        if progresion["nivel"] < articulo.nivel_requerido:
            raise NivelInsuficienteError(progresion["nivel"], articulo.nivel_requerido)

        ahora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        resultado = self._avanzada.comprar_articulo_atomico(usuario_id, articulo, ahora_iso)
        self.sincronizar_progreso_usuario(usuario_id)
        return {
            "success": True,
            "mensaje": f"¡Adquiriste '{articulo.nombre}'!",
            "articulo": articulo.to_dict(),
            "nuevo_saldo": resultado["nuevo_saldo"],
            "inventario": self._avanzada.listar_inventario(usuario_id),
        }

    def actualizar_habitacion(self, usuario_id: int, slots_solicitados: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Valida que cada objeto colocado en la habitación pertenezca realmente al inventario del usuario."""
        slots_validos = {"fondo", "alfombra", "mueble", "maceta", "lampara", "decoracion"}
        inventario = self._avanzada.listar_inventario(usuario_id)
        poseidos = {i["objeto_id"] for i in inventario}

        habitacion_actual = self._avanzada.obtener_habitacion(usuario_id).get("slots", {})
        nuevos_slots = dict(habitacion_actual)

        for slot, obj_id in (slots_solicitados or {}).items():
            if slot not in slots_validos:
                continue
            if obj_id is None or obj_id == "":
                nuevos_slots[slot] = None
            else:
                if obj_id not in poseidos:
                    raise ObjetoNoPoseidoError(obj_id)
                art = MAPA_CATALOGO.get(obj_id)
                if not art or art.slot_habitacion != slot:
                    raise ObjetoNoEncontradoError(obj_id)
                nuevos_slots[slot] = obj_id

        ahora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        guardado = self._avanzada.guardar_habitacion(usuario_id, nuevos_slots, ahora_iso)
        self.sincronizar_progreso_usuario(usuario_id)
        return {
            "success": True,
            "mensaje": "Habitación guardada correctamente.",
            "habitacion": guardado,
        }
