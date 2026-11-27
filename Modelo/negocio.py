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
    EMOCION_ACALORADA,
    EMOCION_CON_FRIO,
    EMOCION_DURMIENDO,
    EMOCION_EN_PELIGRO,
    EMOCION_RADIANTE,
    EMOCION_SEDIENTA,
    EN_RIESGO,
    MOTIVO_CUIDADO_CONTINUO,
    MOTIVO_PENALIZACION_DESCUIDO,
    MOTIVO_RESCATE_HUMEDAD,
    MOTIVO_SALUDO_DIARIO,
    OPTIMO,
    SALUDABLE,
    SIN_RESPUESTA,
    TIPO_PENALIZACION,
    TIPO_RECOMPENSA,
    AccesoDenegadoPlantaError,
    DiagnosticoPlanta,
    DispositivoNoAutorizadoError,
    DispositivoNoEncontradoError,
    DispositivoNoVinculadoError,
    EpisodioGamificacion,
    EspecieNoSoportadaError,
    Lectura,
    LecturaInvalidaError,
    Planta,
    PlantaNoEncontradaError,
    RangosEspecie,
    ResultadoParametro,
    SaludoYaRealizadoHoyError,
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


def es_dispositivo_en_linea(
    ultimo_contacto: Optional[str],
    estado_registrado: Optional[str],
    ventana_seg: int = 120,
) -> tuple[bool, str, Optional[int]]:
    """
    Determina en el dominio si un ESP32 está realmente en línea según su última comunicación real
    y la ventana de inactividad configurada (120 s por defecto).
    """
    estado_norm = (estado_registrado or "").strip().upper()
    if not ultimo_contacto:
        return False, SIN_RESPUESTA, None
    try:
        dt_contacto = datetime.datetime.fromisoformat(str(ultimo_contacto).replace("Z", "+00:00"))
    except ValueError:
        return False, SIN_RESPUESTA, None

    ahora = datetime.datetime.now(dt_contacto.tzinfo) if dt_contacto.tzinfo is not None else datetime.datetime.now()
    delta_seg = (ahora - dt_contacto).total_seconds()
    segundos = max(0, int(delta_seg))
    en_linea = estado_norm == CONECTADO and (-5 <= delta_seg <= max(1, int(ventana_seg)))
    return en_linea, (CONECTADO if en_linea else SIN_RESPUESTA), segundos


def _clave_dispositivo_en_evento(dispositivo_id: Optional[str]) -> str:
    return f"[DEV:{(dispositivo_id or 'SIN_DEV').strip().upper()}]"


class ValidadorDeEstado:
    """Núcleo del dominio: clasificación ambiental y validación de reglas de salud vegetal."""

    @staticmethod
    def validar_lectura_fisica(
        luminosidad: float,
        humedad: float,
        temperatura: float,
        humedad_suelo: Optional[float] = None,
    ) -> None:
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

        if humedad_suelo is not None:
            if not isinstance(humedad_suelo, (int, float)) or humedad_suelo < 0 or humedad_suelo > 100:
                raise LecturaInvalidaError(f"Humedad del suelo fuera de rango físico: {humedad_suelo} %")

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
        humedad_suelo: Optional[float] = None,
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

        # Si se incluye humedad de suelo, evaluarla respecto a los rangos óptimos de humedad
        if humedad_suelo is not None:
            resultado_suelo = self.clasificar_uno(
                nombre="humedad_suelo",
                valor=humedad_suelo,
                v_min=rangos.humedad_min,
                v_max=rangos.humedad_max,
                reco_bajo="Riega el sustrato de la planta; la tierra está seca.",
                reco_alto="Reduce el riego del sustrato; el drenaje puede estar saturado.",
            )
            resultados.append(resultado_suelo)

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

    def calcular_hp(self, estado_global: str, resultados: List[ResultadoParametro]) -> int:
        """
        Calcula los Puntos de Salud (HP) entre 0 y 100 de forma gradual y coherente.
        - SALUDABLE: 100 HP (o 90 si leve aproximación a límite)
        - EN_RIESGO: 50 HP (un parámetro fuera de rango)
        - CRITICO: 15 HP (múltiples parámetros fuera de rango)
        """
        if estado_global == SALUDABLE:
            return 100
        elif estado_global == EN_RIESGO:
            return 50
        else:
            # En crítico, si todos los 3 o 4 parámetros están fuera de rango, cae a 10 HP
            fuera = len([r for r in resultados if r.clasificacion != OPTIMO])
            if fuera >= 3:
                return 10
            return 15

    def determinar_emocion(
        self,
        estado_global: str,
        resultados: List[ResultadoParametro],
        luminosidad: float,
    ) -> str:
        """
        Determina el estado emocional según jerarquía biológica estricta:
        1. CRITICO -> EN PELIGRO / MARCHITA
        2. Humedad baja (aire o suelo) -> SEDIENTA
        3. Temperatura alta -> ACALORADA
        4. Temperatura baja -> CON FRÍO
        5. Luminosidad muy baja (< 50 lux) -> DURMIENDO
        6. Óptimo / Saludable -> RADIANTE
        """
        if estado_global == CRITICO:
            return EMOCION_EN_PELIGRO

        # Buscar clasificaciones específicas
        dict_params = {r.nombre: r for r in resultados}

        # Comprobar sed
        hum_res = dict_params.get("humedad")
        suelo_res = dict_params.get("humedad_suelo")
        if (hum_res and hum_res.clasificacion == BAJO) or (suelo_res and suelo_res.clasificacion == BAJO):
            return EMOCION_SEDIENTA

        # Comprobar temperatura
        temp_res = dict_params.get("temperatura")
        if temp_res:
            if temp_res.clasificacion == ALTO:
                return EMOCION_ACALORADA
            elif temp_res.clasificacion == BAJO:
                return EMOCION_CON_FRIO

        # Comprobar ciclo circadiano / oscuridad (reposo)
        if luminosidad < 50.0:
            return EMOCION_DURMIENDO

        return EMOCION_RADIANTE

    def evaluar_iluminacion_contextual(
        self,
        especie: str,
        rangos: RangosEspecie,
        luminosidad: float,
        historial_lux: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Evalúa la iluminación considerando necesidades de la especie y exposición histórica reciente.
        Diferencia: CRITICA_INSUFICIENTE, BAJA_TOLERABLE, ADECUADA y EXCESIVA,
        y evita falsos positivos ante picos momentáneos (p. ej. linterna) tras oscuridad crónica.
        """
        umbral_critico = min(rangos.lux_min, max(100.0, rangos.lux_min * 0.30))
        muestra = [float(x) for x in (historial_lux or []) if isinstance(x, (int, float))][:10]
        prom_reciente = round(sum(muestra) / len(muestra), 1) if muestra else round(float(luminosidad), 1)

        es_pico_momentaneo = False
        if luminosidad >= rangos.lux_min and len(muestra) >= 3:
            criticas_previas = sum(1 for x in muestra if x < umbral_critico)
            consecutivas_optimas_previas = 0
            for x in muestra:
                if x >= rangos.lux_min:
                    consecutivas_optimas_previas += 1
                else:
                    break
            if criticas_previas >= max(3, int(len(muestra) * 0.7)) and consecutivas_optimas_previas < 2:
                es_pico_momentaneo = True

        if es_pico_momentaneo:
            nivel = "CRITICA_INSUFICIENTE"
            clasificacion = BAJO
            explicacion = (
                f"Lectura puntual de {luminosidad:.0f} lux, pero {especie} acumula oscuridad sostenida "
                f"(promedio reciente {prom_reciente:.0f} lux en {len(muestra)} lecturas; mínimo {rangos.lux_min:.0f} lux). "
                "Requiere luz continua, no un destello momentáneo."
            )
        elif luminosidad < umbral_critico:
            nivel = "CRITICA_INSUFICIENTE"
            clasificacion = BAJO
            explicacion = (
                f"Iluminación crítica para {especie}: recibe {luminosidad:.0f} lux "
                f"(muy por debajo del mínimo de {rangos.lux_min:.0f} lux). Acércala a una fuente de luz."
            )
        elif luminosidad < rangos.lux_min:
            nivel = "BAJA_TOLERABLE"
            clasificacion = BAJO
            explicacion = (
                f"Iluminación baja pero tolerable para {especie}: {luminosidad:.0f} lux "
                f"(ideal {rangos.lux_min:.0f}–{rangos.lux_max:.0f} lux). Conviene mejorar su ubicación gradualmente."
            )
        elif luminosidad > rangos.lux_max:
            nivel = "EXCESIVA"
            clasificacion = ALTO
            explicacion = (
                f"Iluminación excesiva para {especie}: {luminosidad:.0f} lux supera el máximo "
                f"recomendado ({rangos.lux_max:.0f} lux). Muévela a sombra parcial."
            )
        else:
            nivel = "ADECUADA"
            clasificacion = OPTIMO
            explicacion = (
                f"Iluminación adecuada para {especie}: {luminosidad:.0f} lux dentro del rango "
                f"({rangos.lux_min:.0f}–{rangos.lux_max:.0f} lux)."
            )

        return {
            "nivel": nivel,
            "clasificacion": clasificacion,
            "lux_actual": round(float(luminosidad), 1),
            "lux_promedio_reciente": prom_reciente,
            "lecturas_analizadas": len(muestra),
            "es_pico_momentaneo": es_pico_momentaneo,
            "explicacion": explicacion,
        }

    def evaluar(
        self,
        especie: str,
        rangos: RangosEspecie,
        luminosidad: float,
        humedad: float,
        temperatura: float,
        fecha_hora: Optional[str] = None,
        humedad_suelo: Optional[float] = None,
        historial_lux: Optional[List[float]] = None,
    ) -> DiagnosticoPlanta:
        self.validar_lectura_fisica(luminosidad, humedad, temperatura, humedad_suelo)
        resultados = self.clasificar_todos(
            rangos=rangos,
            luminosidad=luminosidad,
            humedad=humedad,
            temperatura=temperatura,
            humedad_suelo=humedad_suelo,
        )
        resumen_lum = self.evaluar_iluminacion_contextual(
            especie=especie,
            rangos=rangos,
            luminosidad=luminosidad,
            historial_lux=historial_lux,
        )

        for idx, res in enumerate(resultados):
            if res.nombre == "luminosidad":
                reco = "" if resumen_lum["clasificacion"] == OPTIMO else resumen_lum["explicacion"]
                resultados[idx] = ResultadoParametro(
                    nombre="luminosidad",
                    valor=res.valor,
                    clasificacion=resumen_lum["clasificacion"],
                    recomendacion=reco,
                )
                break

        estado_global = self.determinar_estado(resultados)
        hp = self.calcular_hp(estado_global, resultados)
        if estado_global == EN_RIESGO and resumen_lum["nivel"] == "BAJA_TOLERABLE":
            fuera = [r for r in resultados if r.clasificacion != OPTIMO]
            if len(fuera) == 1 and fuera[0].nombre == "luminosidad":
                hp = 75

        luz_efectiva = luminosidad if not resumen_lum["es_pico_momentaneo"] else resumen_lum["lux_promedio_reciente"]
        emocion = self.determinar_emocion(estado_global, resultados, luz_efectiva)

        return DiagnosticoPlanta(
            especie=especie,
            estado_global=estado_global,
            parametros=resultados,
            fecha_hora=fecha_hora,
            hp=hp,
            estado_emocional=emocion,
            resumen_luminico=resumen_lum,
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
    Aplica las reglas de gamificación en el dominio (estabilidad, rescate, penalización).
    """

    def __init__(
        self,
        validador: ValidadorDeEstado,
        tabla_referencia: TablaReferenciaPort,
        repo_plantas: RepositorioPlantasPort,
        repo_dispositivos: RepositorioDispositivosPort,
        historial_lecturas: HistorialLecturasPort,
        repo_gamificacion: Optional[RepositorioGamificacionPort] = None,
    ) -> None:
        self._validador = validador
        self._tabla = tabla_referencia
        self._plantas = repo_plantas
        self._dispositivos = repo_dispositivos
        self._historial = historial_lecturas
        self._gamificacion = repo_gamificacion

    @staticmethod
    def _parsear_tiempo_utc(ts_str: str) -> datetime.datetime:
        try:
            # Reemplazar Z por +00:00 para compatibilidad ISO
            limpio = ts_str.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(limpio)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            return datetime.datetime.now(datetime.timezone.utc)

    def _procesar_gamificacion(
        self, planta: Planta, diagnostico: DiagnosticoPlanta, timestamp: str
    ) -> None:
        if not self._gamificacion:
            return

        # Reloj de observación: valida avance temporal evitando manipulación
        ahora_utc = self._parsear_tiempo_utc(timestamp) if timestamp else datetime.datetime.now(datetime.timezone.utc)
        ahora_iso = ahora_utc.isoformat()

        # -------------------------------------------------------------
        # 1. Cuidado Continuo (+1 punto por 1 hora continua de salud)
        # -------------------------------------------------------------
        ep_saludable = self._gamificacion.obtener_episodio_activo(
            planta.id, "SALUDABLE_CONTINUO"
        )
        if diagnostico.estado_global == SALUDABLE:
            if not ep_saludable:
                ep_saludable = EpisodioGamificacion(
                    id=None,
                    planta_id=planta.id,
                    tipo_episodio="SALUDABLE_CONTINUO",
                    inicio_utc=ahora_iso,
                    ultimo_registro_utc=ahora_iso,
                    recompensado_penalizado=False,
                    activo=True,
                )
                self._gamificacion.guardar_episodio(ep_saludable)
            else:
                ultimo_t = self._parsear_tiempo_utc(ep_saludable.ultimo_registro_utc)
                inicio_t = self._parsear_tiempo_utc(ep_saludable.inicio_utc)

                # Si hubo interrupción de telemetría > 90 segundos, reiniciar ventana
                if (ahora_utc - ultimo_t).total_seconds() > 90:
                    ep_saludable.inicio_utc = ahora_iso

                ep_saludable.ultimo_registro_utc = ahora_iso

                # Si cumplió 1 hora continua (3600 segundos) de estabilidad
                if (ahora_utc - inicio_t).total_seconds() >= 3600:
                    hoy_utc = ahora_utc.strftime("%Y-%m-%d")
                    txs_recientes = self._gamificacion.listar_transacciones(planta.usuario_id, limite=100)
                    cuidado_hoy = sum(
                        1
                        for t in txs_recientes
                        if t.motivo == MOTIVO_CUIDADO_CONTINUO and str(t.fecha or "").startswith(hoy_utc)
                    )
                    if planta.dispositivo_id and cuidado_hoy < 4:
                        tx = TransaccionPuntos(
                            id=None,
                            usuario_id=planta.usuario_id,
                            planta_id=planta.id,
                            cantidad=1,
                            motivo=MOTIVO_CUIDADO_CONTINUO,
                            evento=f"1 hora continua de estabilidad saludable en {planta.nombre} {_clave_dispositivo_en_evento(planta.dispositivo_id)}",
                            fecha=ahora_iso,
                            tipo=TIPO_RECOMPENSA,
                            clave_idempotencia=f"CUIDADO:{planta.usuario_id}:{hoy_utc}:{cuidado_hoy}",
                        )
                        self._gamificacion.registrar_transaccion(tx)
                    # Reiniciar marca de inicio para la siguiente hora
                    ep_saludable.inicio_utc = ahora_iso

                self._gamificacion.guardar_episodio(ep_saludable)
        else:
            # Si dejó de estar saludable, cerrar el episodio continuo
            if ep_saludable:
                ep_saludable.activo = False
                self._gamificacion.guardar_episodio(ep_saludable)

        # -------------------------------------------------------------
        # 2. Bonificación por Rescate (+4 monedas, >=5 min en sequía, cooldown 6h, 1/planta/día, 2/usuario/día)
        # -------------------------------------------------------------
        hum_baja = False
        for param in diagnostico.parametros:
            if param.nombre in ["humedad", "humedad_suelo"] and param.clasificacion == BAJO:
                hum_baja = True
                break

        ep_humedad_baja = self._gamificacion.obtener_episodio_activo(
            planta.id, "HUMEDAD_BAJA"
        )
        if hum_baja:
            if not ep_humedad_baja:
                ep_humedad_baja = EpisodioGamificacion(
                    id=None,
                    planta_id=planta.id,
                    tipo_episodio="HUMEDAD_BAJA",
                    inicio_utc=ahora_iso,
                    ultimo_registro_utc=ahora_iso,
                    recompensado_penalizado=False,
                    activo=True,
                )
                self._gamificacion.guardar_episodio(ep_humedad_baja)
            else:
                ep_humedad_baja.ultimo_registro_utc = ahora_iso
                self._gamificacion.guardar_episodio(ep_humedad_baja)
        else:
            # Si antes estaba en humedad baja y ahora se recuperó
            if ep_humedad_baja and not ep_humedad_baja.recompensado_penalizado:
                # Anti-jitter y anti-farm: confirmar sequía sostenida >= 300s (5 minutos reales)
                inicio_h = self._parsear_tiempo_utc(ep_humedad_baja.inicio_utc)
                if (ahora_utc - inicio_h).total_seconds() >= 300 and planta.dispositivo_id:
                    hoy_utc = ahora_utc.strftime("%Y-%m-%d")
                    tag_dev = _clave_dispositivo_en_evento(planta.dispositivo_id)
                    txs_usuario = self._gamificacion.listar_transacciones(planta.usuario_id, limite=100)
                    rescates_usuario_hoy = [
                        t
                        for t in txs_usuario
                        if t.motivo == MOTIVO_RESCATE_HUMEDAD and str(t.fecha or "").startswith(hoy_utc)
                    ]
                    rescates_disp_hoy = [
                        t for t in rescates_usuario_hoy
                        if tag_dev in str(t.evento or "") or t.planta_id == planta.id
                    ]
                    ultimo_rescate_disp = next(
                        (
                            t for t in txs_usuario
                            if t.motivo == MOTIVO_RESCATE_HUMEDAD and (tag_dev in str(t.evento or "") or t.planta_id == planta.id)
                        ),
                        None,
                    )
                    en_cooldown = False
                    if ultimo_rescate_disp and ultimo_rescate_disp.fecha:
                        dt_ult = self._parsear_tiempo_utc(ultimo_rescate_disp.fecha)
                        if (ahora_utc - dt_ult).total_seconds() < 6 * 3600:
                            en_cooldown = True

                    if (
                        not en_cooldown
                        and len(rescates_disp_hoy) < 1
                        and len(rescates_usuario_hoy) < 2
                    ):
                        tx = TransaccionPuntos(
                            id=None,
                            usuario_id=planta.usuario_id,
                            planta_id=planta.id,
                            cantidad=4,
                            motivo=MOTIVO_RESCATE_HUMEDAD,
                            evento=f"Rescate exitoso de humedad en {planta.nombre} {tag_dev}",
                            fecha=ahora_iso,
                            tipo=TIPO_RECOMPENSA,
                            clave_idempotencia=f"RESCATE:{planta.usuario_id}:{planta.dispositivo_id.strip().upper()}:{hoy_utc}",
                        )
                        self._gamificacion.registrar_transaccion(tx)
                ep_humedad_baja.recompensado_penalizado = True
                ep_humedad_baja.activo = False
                self._gamificacion.guardar_episodio(ep_humedad_baja)

        # -------------------------------------------------------------
        # 3. Penalización por Descuido (-2 puntos por > 1 hora en CRITICO)
        # -------------------------------------------------------------
        ep_critico = self._gamificacion.obtener_episodio_activo(
            planta.id, "CRITICO_CONTINUO"
        )
        if diagnostico.estado_global == CRITICO:
            if not ep_critico:
                ep_critico = EpisodioGamificacion(
                    id=None,
                    planta_id=planta.id,
                    tipo_episodio="CRITICO_CONTINUO",
                    inicio_utc=ahora_iso,
                    ultimo_registro_utc=ahora_iso,
                    recompensado_penalizado=False,
                    activo=True,
                )
                self._gamificacion.guardar_episodio(ep_critico)
            else:
                inicio_c = self._parsear_tiempo_utc(ep_critico.inicio_utc)
                ep_critico.ultimo_registro_utc = ahora_iso

                if not ep_critico.recompensado_penalizado:
                    if (ahora_utc - inicio_c).total_seconds() >= 3600:
                        saldo_actual = self._gamificacion.obtener_saldo(planta.usuario_id)
                        descuento = min(2, saldo_actual)  # Nunca saldo negativo
                        if descuento > 0:
                            tx = TransaccionPuntos(
                                id=None,
                                usuario_id=planta.usuario_id,
                                planta_id=planta.id,
                                cantidad=-descuento,
                                motivo=MOTIVO_PENALIZACION_DESCUIDO,
                                evento=f"Planta {planta.nombre} en estado crítico durante más de 1 hora",
                                fecha=ahora_iso,
                                tipo=TIPO_PENALIZACION,
                            )
                            self._gamificacion.registrar_transaccion(tx)
                        ep_critico.recompensado_penalizado = True

                self._gamificacion.guardar_episodio(ep_critico)
        else:
            if ep_critico:
                ep_critico.activo = False
                self._gamificacion.guardar_episodio(ep_critico)

    def registrar(
        self,
        dispositivo_id: str,
        timestamp: str,
        luminosidad: float,
        humedad: float,
        temperatura: float,
        humedad_suelo: Optional[float] = None,
    ) -> DiagnosticoPlanta:
        # 1. Valida reglas físicas de la telemetría en el dominio
        self._validador.validar_lectura_fisica(luminosidad, humedad, temperatura, humedad_suelo)

        # 2. Busca la planta asignada al dispositivo
        planta = self._plantas.obtener_por_dispositivo(dispositivo_id)
        if not planta:
            lectura_huerfana = Lectura(
                dispositivo_id=dispositivo_id,
                timestamp=timestamp,
                luminosidad=luminosidad,
                humedad=humedad,
                temperatura=temperatura,
                humedad_suelo=humedad_suelo,
            )
            self._historial.guardar_lectura(lectura_huerfana, None)
            self._dispositivos.actualizar_ultimo_contacto(dispositivo_id, timestamp)
            raise DispositivoNoVinculadoError(dispositivo_id)

        # 3. Obtiene rangos de la especie desde el puerto de salida
        rangos = self._tabla.obtener_rangos(planta.especie)
        if not rangos:
            raise EspecieNoSoportadaError(planta.especie)

        # 4. Consultar historial reciente de iluminación para evitar falsos positivos por picos momentáneos
        historial_lux: List[float] = []
        try:
            hist_reciente = self._historial.obtener_historial_por_planta(planta.id, limite=10)
            for item in hist_reciente:
                if isinstance(item, dict) and item.get("luminosidad") is not None:
                    historial_lux.append(float(item["luminosidad"]))
                elif hasattr(item, "luminosidad") and item.luminosidad is not None:
                    historial_lux.append(float(item.luminosidad))
        except Exception:
            historial_lux = []

        # 5. Ejecuta el núcleo de dominio para calcular el diagnóstico y gamificación
        diagnostico = self._validador.evaluar(
            especie=planta.especie,
            rangos=rangos,
            luminosidad=luminosidad,
            humedad=humedad,
            temperatura=temperatura,
            fecha_hora=timestamp,
            humedad_suelo=humedad_suelo,
            historial_lux=historial_lux,
        )

        # 5. Persiste la lectura y su diagnóstico en el puerto de historial
        lectura = Lectura(
            dispositivo_id=dispositivo_id,
            timestamp=timestamp,
            luminosidad=luminosidad,
            humedad=humedad,
            temperatura=temperatura,
            planta_id=planta.id,
            humedad_suelo=humedad_suelo,
        )
        self._historial.guardar_lectura(lectura, diagnostico)

        # 6. Actualiza último contacto del dispositivo
        self._dispositivos.actualizar_ultimo_contacto(dispositivo_id, timestamp)

        # 7. Evaluar eventos de gamificación (cuidado continuo, rescate, descuido)
        self._procesar_gamificacion(planta, diagnostico, timestamp)

        return diagnostico


class CasoUsoConsultarEstado:
    """
    Caso de uso P2: Consultar estado actual e historial de las plantas.
    Aplica rigurosamente la regla de negocio: un usuario solo ve sus propias plantas.
    Entrega el estado de gamificación (HP, estado emocional, puntos, saludo disponible).
    """

    def __init__(
        self,
        validador: ValidadorDeEstado,
        repo_plantas: RepositorioPlantasPort,
        historial_lecturas: HistorialLecturasPort,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_gamificacion: Optional[RepositorioGamificacionPort] = None,
    ) -> None:
        self._validador = validador
        self._plantas = repo_plantas
        self._historial = historial_lecturas
        self._dispositivos = repo_dispositivos
        self._gamificacion = repo_gamificacion

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
                ref_contacto = dev.ultimo_contacto or (ultima_lectura.timestamp if ultima_lectura else None)
                en_linea, estado_efectivo, segs = es_dispositivo_en_linea(ref_contacto, dev.estado_conexion)
                dispositivo_info = {
                    "id": dev.id,
                    "mac": dev.mac,
                    "ultimo_contacto": ref_contacto,
                    "estado_conexion": estado_efectivo,
                    "en_linea": en_linea,
                    "segundos_sin_contacto": segs,
                }

        # Extraer diagnóstico reciente o valores por defecto
        diag_reciente = historial[0].get("diagnostico") if historial else None
        hp = diag_reciente.get("hp", 100) if diag_reciente else 100
        estado_emocional = diag_reciente.get("estado_emocional", EMOCION_RADIANTE) if diag_reciente else EMOCION_RADIANTE
        estado_global = diag_reciente.get("estado_global", "SIN_DATOS") if diag_reciente else "SIN_DATOS"

        hoy_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        ya_saludado = False
        saldo_usuario = 0
        if self._gamificacion:
            ya_saludado = self._gamificacion.ya_saludo_hoy(usuario_id, planta_id, hoy_utc)
            saldo_usuario = self._gamificacion.obtener_saldo(usuario_id)

        return {
            "planta": {
                "id": planta.id,
                "nombre": planta.nombre,
                "especie": planta.especie,
                "ubicacion": planta.ubicacion,
                "dispositivo_id": planta.dispositivo_id,
            },
            "dispositivo": dispositivo_info,
            "estado_global": estado_global,
            "hp": hp,
            "estado_emocional": estado_emocional,
            "ya_saludado_hoy": ya_saludado,
            "saldo_puntos": saldo_usuario,
            "diagnostico": diag_reciente,
            "ultima_lectura": {
                "timestamp": ultima_lectura.timestamp if ultima_lectura else None,
                "luminosidad": ultima_lectura.luminosidad if ultima_lectura else None,
                "humedad": ultima_lectura.humedad if ultima_lectura else None,
                "temperatura": ultima_lectura.temperatura if ultima_lectura else None,
                "humedad_suelo": getattr(ultima_lectura, "humedad_suelo", None) if ultima_lectura else None,
            } if ultima_lectura else None,
            "historial": historial,
        }

    def consultar_plantas_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        plantas = self._plantas.listar_por_usuario(usuario_id)
        hoy_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        res: List[Dict[str, Any]] = []

        for p in plantas:
            ultima = self._historial.obtener_ultima_lectura_por_planta(p.id)
            hist = self._historial.obtener_historial_por_planta(p.id, limite=1)
            diag_dict = hist[0].get("diagnostico") if hist else None
            estado_global = diag_dict.get("estado_global", "DESCONOCIDO") if diag_dict else "SIN_DATOS"
            hp = diag_dict.get("hp", 100) if diag_dict else 100
            emocion = diag_dict.get("estado_emocional", EMOCION_RADIANTE) if diag_dict else EMOCION_RADIANTE

            dev_info = None
            if p.dispositivo_id:
                dev = self._dispositivos.buscar_por_id(p.dispositivo_id)
                if dev:
                    ref_contacto = dev.ultimo_contacto or (ultima.timestamp if ultima else None)
                    en_linea, estado_efectivo, segs = es_dispositivo_en_linea(ref_contacto, dev.estado_conexion)
                    dev_info = {
                        "id": dev.id,
                        "ultimo_contacto": ref_contacto,
                        "estado_conexion": estado_efectivo,
                        "en_linea": en_linea,
                        "segundos_sin_contacto": segs,
                    }

            ya_saludado = False
            if self._gamificacion:
                ya_saludado = self._gamificacion.ya_saludo_hoy(usuario_id, p.id, hoy_utc)

            res.append({
                "id": p.id,
                "nombre": p.nombre,
                "especie": p.especie,
                "ubicacion": p.ubicacion,
                "dispositivo_id": p.dispositivo_id,
                "estado_global": estado_global,
                "hp": hp,
                "estado_emocional": emocion,
                "ya_saludado_hoy": ya_saludado,
                "diagnostico": diag_dict,
                "dispositivo": dev_info,
                "ultima_lectura": {
                    "timestamp": ultima.timestamp if ultima else None,
                    "luminosidad": ultima.luminosidad if ultima else None,
                    "humedad": ultima.humedad if ultima else None,
                    "temperatura": ultima.temperatura if ultima else None,
                    "humedad_suelo": getattr(ultima, "humedad_suelo", None) if ultima else None,
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

        saldo_usuario = 0
        if self._gamificacion:
            saldo_usuario = self._gamificacion.obtener_saldo(usuario_id)

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
                "saldo_puntos": saldo_usuario,
            },
            "plantas": plantas_info,
            "alertas": alertas,
        }


class CasoUsoGamificacion:
    """
    Caso de uso de Gamificación del Dominio (Puertos de Entrada).
    Orquesta saldo, saludos diarios, prevención de exploits e historial.
    """

    def __init__(
        self,
        repo_gamificacion: RepositorioGamificacionPort,
        repo_plantas: RepositorioPlantasPort,
        validador: ValidadorDeEstado,
    ) -> None:
        self._gamificacion = repo_gamificacion
        self._plantas = repo_plantas
        self._validador = validador

    def saludar_planta(self, usuario_id: int, planta_id: int) -> Dict[str, Any]:
        planta = self._plantas.obtener_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(planta_id)

        # Regla de pertenencia
        self._validador.verificar_propiedad_planta(planta, usuario_id)

        # Validar límite de 1 saludo por día calendario (reloj servidor UTC)
        hoy_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        if self._gamificacion.ya_saludo_hoy(usuario_id, planta_id, hoy_utc):
            raise SaludoYaRealizadoHoyError(usuario_id, planta_id, hoy_utc)

        # Registrar saludo diario (interacción visual/social, sin recompensas económicas ni XP)
        self._gamificacion.registrar_saludo_hoy(usuario_id, planta_id, hoy_utc)
        nuevo_saldo = self._gamificacion.obtener_saldo(usuario_id)

        return {
            "mensaje": f"¡Has saludado a {planta.nombre}! La planta se siente acompañada.",
            "puntos_ganados": 0,
            "xp_ganado": 0,
            "saldo_actual": nuevo_saldo,
            "planta_id": planta_id,
            "fecha": hoy_utc,
        }

    def consultar_saldo(self, usuario_id: int) -> int:
        return self._gamificacion.obtener_saldo(usuario_id)

    def consultar_historial_puntos(
        self, usuario_id: int, limite: int = 50
    ) -> List[Dict[str, Any]]:
        txs = self._gamificacion.listar_transacciones(usuario_id, limite)
        return [t.to_dict() for t in txs]


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

        dev_id_limpio = dispositivo_id.strip().upper() if dispositivo_id else None
        if dev_id_limpio:
            dev = self._dispositivos.buscar_por_id(dev_id_limpio)
            if not dev:
                raise DispositivoNoEncontradoError(dev_id_limpio)
            if dev.usuario_id is None or int(dev.usuario_id) != int(usuario_id):
                raise DispositivoNoAutorizadoError(dev_id_limpio)
            if dev.planta_id is not None and dev.planta_id != 0:
                raise ValueError(
                    f"El dispositivo {dev_id_limpio} ya está vinculado a otra planta (ID {dev.planta_id})."
                )

        planta = Planta(
            id=0,
            nombre=nombre.strip(),
            especie=especie.strip(),
            usuario_id=usuario_id,
            dispositivo_id=dev_id_limpio,
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

        dev = self._dispositivos.buscar_por_id(dispositivo_id)
        if not dev:
            raise DispositivoNoEncontradoError(dispositivo_id)

        # Seguridad: solo el propietario verificado del dispositivo puede vincularlo
        if dev.usuario_id is None or int(dev.usuario_id) != int(usuario_id):
            raise DispositivoNoAutorizadoError(dispositivo_id)

        # Garantizar relación 1:1 (no permitir vincular un ESP32 ya enlazado a otra planta)
        if dev.planta_id is not None and dev.planta_id != 0 and int(dev.planta_id) != int(planta_id):
            raise ValueError(
                f"El dispositivo {dispositivo_id} ya está vinculado a otra planta (ID {dev.planta_id}). Desvincúlalo primero."
            )

        # Si la planta tenía otro dispositivo distinto vinculado, liberarlo primero sin borrar su configuración
        if planta.dispositivo_id and planta.dispositivo_id.upper() != dispositivo_id.upper():
            dev_anterior = self._dispositivos.buscar_por_id(planta.dispositivo_id)
            if dev_anterior:
                dev_anterior.planta_id = None
                self._dispositivos.guardar_dispositivo(dev_anterior)

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

