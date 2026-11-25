"""
Pruebas Unitarias de Gamificación y Diagnóstico Biológico de Plantol (tests/test_gamificacion.py).
Verifica:
- Cálculo determinista de HP biológico (0-100).
- Jerarquía estricta de estados emocionales.
- Validación de humedad de suelo (0-100%).
- Acreditación de puntos por saludo diario (1 pt/día por planta) e idempotencia (anti-exploit).
- Recompensas por cuidado continuo saludable (+1 pt por cada hora continua).
- Recompensas por rescate de humedad crítica (+3 pts).
- Penalización por descuido continuo (>1 hora en estado crítico, -2 pts, balance nunca negativo).
- Reseteo de episodios por desconexión / gap temporal (> 90 segundos).
- Arquitectura Hexagonal: Testeable con dobles en memoria sin depender de Flask ni de la red.
"""
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from Modelo.entidades import (
    ALTO,
    BAJO,
    CRITICO,
    EN_RIESGO,
    OPTIMO,
    SALUDABLE,
    EMOCION_ACALORADA,
    EMOCION_CON_FRIO,
    EMOCION_DURMIENDO,
    EMOCION_EN_PELIGRO,
    EMOCION_RADIANTE,
    EMOCION_SEDIENTA,
    MOTIVO_SALUDO_DIARIO,
    TIPO_RECOMPENSA,
    AccesoDenegadoPlantaError,
    Dispositivo,
    EpisodioGamificacion,
    Lectura,
    LecturaInvalidaError,
    Planta,
    RangosEspecie,
    ResultadoParametro,
    SaludoYaRealizadoHoyError,
    TransaccionPuntos,
)
from Modelo.negocio import (
    CasoUsoGamificacion,
    CasoUsoRegistrarLectura,
    ValidadorDeEstado,
)
from Modelo.puertos import (
    HistorialLecturasPort,
    RepositorioDispositivosPort,
    RepositorioGamificacionPort,
    RepositorioPlantasPort,
    TablaReferenciaPort,
)

# ---------------------------------------------------------------------
# Dobles de prueba en memoria
# ---------------------------------------------------------------------

CACTUS = RangosEspecie(
    nombre="Cactus (Cactaceae)",
    lux_min=5000.0, lux_max=15000.0,
    humedad_min=10.0, humedad_max=30.0,
    temperatura_min=18.0, temperatura_max=35.0,
)


class FakeTablaReferencia(TablaReferenciaPort):
    def obtener_rangos(self, especie: str):
        return CACTUS

    def listar_especies(self):
        return [CACTUS]


class FakeHistorialLecturas(HistorialLecturasPort):
    def __init__(self):
        self.lecturas = []

    def guardar_lectura(self, lectura: Lectura, diagnostico=None):
        self.lecturas.append({"lectura": lectura, "diagnostico": diagnostico})

    def obtener_ultima_lectura(self, dispositivo_id: str):
        for item in reversed(self.lecturas):
            if item["lectura"].dispositivo_id == dispositivo_id:
                return item["lectura"]
        return None

    def obtener_ultima_lectura_por_planta(self, planta_id: int):
        for item in reversed(self.lecturas):
            if item["lectura"].planta_id == planta_id:
                return item["lectura"]
        return None

    def obtener_historial_por_planta(self, planta_id: int, limite: int = 50):
        res = [item["lectura"] for item in self.lecturas if item["lectura"].planta_id == planta_id]
        return list(reversed(res[-limite:]))


class FakeRepoDispositivos(RepositorioDispositivosPort):
    def __init__(self):
        self.dispositivos = {}

    def buscar_por_id(self, dispositivo_id: str):
        return self.dispositivos.get(dispositivo_id)

    def listar_todos(self):
        return list(self.dispositivos.values())

    def guardar_dispositivo(self, disp: Dispositivo):
        self.dispositivos[disp.id] = disp
        return disp

    def actualizar_ultimo_contacto(self, dispositivo_id: str, timestamp: str) -> None:
        if dispositivo_id in self.dispositivos:
            self.dispositivos[dispositivo_id].ultimo_contacto = timestamp

    def guardar_token_pairing(self, token: str, usuario_id: int) -> None:
        pass

    def validar_y_consumir_token_pairing(self, token: str) -> bool:
        return True


class FakeRepoPlantas(RepositorioPlantasPort):
    def __init__(self):
        self.plantas = {}

    def obtener_por_id(self, planta_id: int):
        return self.plantas.get(planta_id)

    def obtener_por_dispositivo(self, dispositivo_id: str):
        for p in self.plantas.values():
            if p.dispositivo_id == dispositivo_id:
                return p
        return None

    def listar_por_usuario(self, usuario_id: int):
        return [p for p in self.plantas.values() if p.usuario_id == usuario_id]

    def guardar_planta(self, planta: Planta):
        if not planta.id:
            planta.id = len(self.plantas) + 1
        self.plantas[planta.id] = planta
        return planta

    def eliminar_planta(self, planta_id: int) -> bool:
        return self.plantas.pop(planta_id, None) is not None


class FakeRepoGamificacion(RepositorioGamificacionPort):
    def __init__(self):
        self.saldos = {}  # usuario_id -> int
        self.transacciones = []
        self.saludos = set()  # (usuario_id, planta_id, fecha_dia)
        self.episodios = {}  # (planta_id, tipo_episodio) -> EpisodioGamificacion

    def obtener_saldo(self, usuario_id: int) -> int:
        return self.saldos.get(usuario_id, 0)

    def registrar_transaccion(self, tx: TransaccionPuntos) -> TransaccionPuntos:
        self.transacciones.append(tx)
        nuevo_saldo = max(0, self.saldos.get(tx.usuario_id, 0) + tx.cantidad)
        self.saldos[tx.usuario_id] = nuevo_saldo
        return tx

    def listar_transacciones(self, usuario_id: int, limite: int = 50):
        res = [tx for tx in self.transacciones if tx.usuario_id == usuario_id]
        return list(reversed(res[-limite:]))

    def ya_saludo_hoy(self, usuario_id: int, planta_id: int, fecha_dia: str) -> bool:
        return (usuario_id, planta_id, fecha_dia) in self.saludos

    def registrar_saludo_hoy(self, usuario_id: int, planta_id: int, fecha_dia: str) -> bool:
        if (usuario_id, planta_id, fecha_dia) in self.saludos:
            return False
        self.saludos.add((usuario_id, planta_id, fecha_dia))
        return True

    def obtener_episodio_activo(self, planta_id: int, tipo_episodio: str):
        ep = self.episodios.get((planta_id, tipo_episodio))
        if ep and ep.activo:
            return ep
        return None

    def guardar_episodio(self, episodio: EpisodioGamificacion) -> EpisodioGamificacion:
        self.episodios[(episodio.planta_id, episodio.tipo_episodio)] = episodio
        return episodio


# =====================================================================
# Casos de Prueba
# =====================================================================

class TestValidadorSaludYEmociones(unittest.TestCase):
    def setUp(self):
        self.validador = ValidadorDeEstado()

    def test_calcular_hp_todos_optimos(self):
        r_temp = ResultadoParametro("Temperatura", 24.0, OPTIMO, "Normal")
        r_hum = ResultadoParametro("Humedad", 20.0, OPTIMO, "Normal")
        r_lux = ResultadoParametro("Luminosidad", 8000.0, OPTIMO, "Normal")
        hp = self.validador.calcular_hp(SALUDABLE, [r_temp, r_hum, r_lux])
        self.assertEqual(hp, 100)

    def test_calcular_hp_desviaciones_y_suelo(self):
        r_temp = ResultadoParametro("Temperatura", 38.0, ALTO, "Calor")
        r_hum = ResultadoParametro("Humedad", 20.0, OPTIMO, "Normal")
        r_lux = ResultadoParametro("Luminosidad", 8000.0, OPTIMO, "Normal")
        hp_riesgo = self.validador.calcular_hp(EN_RIESGO, [r_temp, r_hum, r_lux])
        self.assertEqual(hp_riesgo, 50)

        # Crítico
        r_hum_crit = ResultadoParametro("Humedad", 5.0, BAJO, "Seco")
        hp_critico = self.validador.calcular_hp(CRITICO, [r_temp, r_hum_crit, r_lux])
        self.assertEqual(hp_critico, 15)

    def test_determinar_emocion_jerarquia_estricta(self):
        # 1. Estado Crítico -> EMOCION_EN_PELIGRO
        emocion_critica = self.validador.determinar_emocion(
            estado_global=CRITICO,
            resultados=[
                ResultadoParametro("temperatura", 45.0, ALTO, "Extremo"),
                ResultadoParametro("humedad", 5.0, BAJO, "Extremo"),
                ResultadoParametro("luminosidad", 100.0, OPTIMO, "Normal"),
            ],
            luminosidad=100.0,
        )
        self.assertEqual(emocion_critica, EMOCION_EN_PELIGRO)

        # 2. Sedienta (Humedad aire o suelo baja)
        emocion_sedienta = self.validador.determinar_emocion(
            estado_global=EN_RIESGO,
            resultados=[
                ResultadoParametro("temperatura", 24.0, OPTIMO, "Normal"),
                ResultadoParametro("humedad", 8.0, BAJO, "Seco"),
                ResultadoParametro("luminosidad", 8000.0, OPTIMO, "Normal"),
            ],
            luminosidad=8000.0,
        )
        self.assertEqual(emocion_sedienta, EMOCION_SEDIENTA)

        # 3. Acalorada (Temp ALTO)
        emocion_calor = self.validador.determinar_emocion(
            estado_global=EN_RIESGO,
            resultados=[
                ResultadoParametro("temperatura", 38.0, ALTO, "Calor"),
                ResultadoParametro("humedad", 20.0, OPTIMO, "Normal"),
                ResultadoParametro("luminosidad", 8000.0, OPTIMO, "Normal"),
            ],
            luminosidad=8000.0,
        )
        self.assertEqual(emocion_calor, EMOCION_ACALORADA)

        # 4. Con frío (Temp BAJO)
        emocion_frio = self.validador.determinar_emocion(
            estado_global=EN_RIESGO,
            resultados=[
                ResultadoParametro("temperatura", 12.0, BAJO, "Frío"),
                ResultadoParametro("humedad", 20.0, OPTIMO, "Normal"),
                ResultadoParametro("luminosidad", 8000.0, OPTIMO, "Normal"),
            ],
            luminosidad=8000.0,
        )
        self.assertEqual(emocion_frio, EMOCION_CON_FRIO)

        # 5. Durmiendo (Lux < 50)
        emocion_noche = self.validador.determinar_emocion(
            estado_global=SALUDABLE,
            resultados=[
                ResultadoParametro("temperatura", 24.0, OPTIMO, "Normal"),
                ResultadoParametro("humedad", 20.0, OPTIMO, "Normal"),
                ResultadoParametro("luminosidad", 20.0, OPTIMO, "Normal"),
            ],
            luminosidad=20.0,
        )
        self.assertEqual(emocion_noche, EMOCION_DURMIENDO)

        # 6. Radiante (Todo óptimo)
        emocion_radiante = self.validador.determinar_emocion(
            estado_global=SALUDABLE,
            resultados=[
                ResultadoParametro("temperatura", 24.0, OPTIMO, "Normal"),
                ResultadoParametro("humedad", 20.0, OPTIMO, "Normal"),
                ResultadoParametro("luminosidad", 8000.0, OPTIMO, "Normal"),
            ],
            luminosidad=8000.0,
        )
        self.assertEqual(emocion_radiante, EMOCION_RADIANTE)

    def test_validacion_fisica_humedad_suelo(self):
        # Valor válido
        self.validador.validar_lectura_fisica(
            luminosidad=1000.0,
            humedad=50.0,
            temperatura=22.0,
            humedad_suelo=45.5,
        )

        # Suelo negativo
        with self.assertRaises(LecturaInvalidaError):
            self.validador.validar_lectura_fisica(
                luminosidad=1000.0,
                humedad=50.0,
                temperatura=22.0,
                humedad_suelo=-5.0,
            )

        # Suelo mayor a 100
        with self.assertRaises(LecturaInvalidaError):
            self.validador.validar_lectura_fisica(
                luminosidad=1000.0,
                humedad=50.0,
                temperatura=22.0,
                humedad_suelo=105.0,
            )


class TestCasoUsoGamificacionAislado(unittest.TestCase):
    def setUp(self):
        self.repo_plantas = FakeRepoPlantas()
        self.repo_gamificacion = FakeRepoGamificacion()
        self.validador = ValidadorDeEstado()
        self.caso = CasoUsoGamificacion(
            repo_gamificacion=self.repo_gamificacion,
            repo_plantas=self.repo_plantas,
            validador=self.validador,
        )

        self.planta = self.repo_plantas.guardar_planta(
            Planta(id=1, nombre="Mi Cactus", especie="Cactus (Cactaceae)", usuario_id=10)
        )

    def test_saludar_planta_exitoso_y_suma_un_punto(self):
        res = self.caso.saludar_planta(usuario_id=10, planta_id=1)
        self.assertEqual(res["puntos_ganados"], 1)
        self.assertEqual(res["saldo_actual"], 1)
        self.assertEqual(self.repo_gamificacion.obtener_saldo(10), 1)

        # Historial de transacciones contiene el saludo
        hist = self.caso.consultar_historial_puntos(usuario_id=10)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["motivo"], MOTIVO_SALUDO_DIARIO)
        self.assertEqual(hist[0]["tipo"], TIPO_RECOMPENSA)

    def test_saludo_duplicado_mismo_dia_rechazado_idempotente(self):
        self.caso.saludar_planta(usuario_id=10, planta_id=1)
        with self.assertRaises(SaludoYaRealizadoHoyError):
            self.caso.saludar_planta(usuario_id=10, planta_id=1)
        self.assertEqual(self.repo_gamificacion.obtener_saldo(10), 1)

    def test_saludo_usuario_ajeno_denegado(self):
        with self.assertRaises(AccesoDenegadoPlantaError):
            self.caso.saludar_planta(usuario_id=99, planta_id=1)


class TestGamificacionEpisodiosYTelemetria(unittest.TestCase):
    def setUp(self):
        self.repo_disp = FakeRepoDispositivos()
        self.repo_plantas = FakeRepoPlantas()
        self.historial = FakeHistorialLecturas()
        self.validador = ValidadorDeEstado()
        self.repo_gamificacion = FakeRepoGamificacion()

        self.caso_lectura = CasoUsoRegistrarLectura(
            validador=self.validador,
            tabla_referencia=FakeTablaReferencia(),
            repo_plantas=self.repo_plantas,
            repo_dispositivos=self.repo_disp,
            historial_lecturas=self.historial,
            repo_gamificacion=self.repo_gamificacion,
        )

        self.dev = self.repo_disp.guardar_dispositivo(
            Dispositivo(id="ESP32-GAM", mac="AA:BB:CC:DD:EE:FF", secret_hash="secret", planta_id=1)
        )
        self.planta = self.repo_plantas.guardar_planta(
            Planta(id=1, nombre="Cactus", especie="Cactus (Cactaceae)", usuario_id=5, dispositivo_id="ESP32-GAM")
        )

    def test_recompensa_cuidado_continuo_una_hora(self):
        # 1. Lecturas periódicas cada 60s durante 61 minutos (sin violar gap de 90s)
        base_time = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
        curr_time = base_time

        # Primera lectura
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=curr_time.isoformat(),
            luminosidad=8000.0,
            humedad=20.0,
            temperatura=24.0,
        )
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 0)

        # 30 minutos después de cadencia continua
        for _ in range(30):
            curr_time += timedelta(minutes=1)
            self.caso_lectura.registrar(
                dispositivo_id="ESP32-GAM",
                timestamp=curr_time.isoformat(),
                luminosidad=8000.0,
                humedad=20.0,
                temperatura=24.0,
            )
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 0)

        # Completar hasta minuto 61
        for _ in range(31):
            curr_time += timedelta(minutes=1)
            self.caso_lectura.registrar(
                dispositivo_id="ESP32-GAM",
                timestamp=curr_time.isoformat(),
                luminosidad=8000.0,
                humedad=20.0,
                temperatura=24.0,
            )
        # Debe haber ganado +1 punto por cumplir 1 hora continua de estabilidad
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 1)

    def test_interrupcion_telemetria_mayor_90_segundos_reinicia_racha(self):
        base_time = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
        # Lectura inicial
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=base_time.isoformat(),
            luminosidad=8000.0,
            humedad=20.0,
            temperatura=24.0,
        )

        # Desconexión / gap de 10 minutos (> 90s)
        time_gap = base_time + timedelta(minutes=10)
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=time_gap.isoformat(),
            luminosidad=8000.0,
            humedad=20.0,
            temperatura=24.0,
        )

        # Avanzar 55 minutos desde el gap (no cumple 60m continuos desde el reinicio)
        curr = time_gap
        for _ in range(55):
            curr += timedelta(minutes=1)
            self.caso_lectura.registrar(
                dispositivo_id="ESP32-GAM",
                timestamp=curr.isoformat(),
                luminosidad=8000.0,
                humedad=20.0,
                temperatura=24.0,
            )
        # No debe haber ganado puntos porque el gap reinició la ventana
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 0)

    def test_recompensa_rescate_humedad_critica(self):
        # 1. Lectura en estado bajo de humedad (< 10%)
        t0 = datetime(2026, 11, 22, 10, 0, 0, tzinfo=timezone.utc)
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=t0.isoformat(),
            luminosidad=8000.0,
            humedad=5.0,  # Cactus min es 10%
            temperatura=24.0,
            humedad_suelo=8.0,
        )
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 0)

        # 2. El usuario riega la planta y la siguiente lectura entra en rango óptimo (20%)
        t1 = t0 + timedelta(seconds=40)
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=t1.isoformat(),
            luminosidad=8000.0,
            humedad=20.0,  # Óptimo
            temperatura=24.0,
            humedad_suelo=20.0,
        )
        # Debe recibir +3 puntos de bonificación por rescate de humedad
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 3)

    def test_fluctuacion_ruido_humedad_menor_30s_no_otorga_rescate(self):
        # 1. Lectura transitoria con ruido de sensor (< 30s)
        t0 = datetime(2026, 11, 22, 11, 0, 0, tzinfo=timezone.utc)
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=t0.isoformat(),
            luminosidad=8000.0,
            humedad=5.0,  # Baja
            temperatura=24.0,
            humedad_suelo=8.0,
        )
        # Salto inmediato a los 5 segundos (ruido del ADC, no sequía real)
        t_ruido = t0 + timedelta(seconds=5)
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=t_ruido.isoformat(),
            luminosidad=8000.0,
            humedad=20.0,  # Óptimo
            temperatura=24.0,
            humedad_suelo=20.0,
        )
        # Por anti-jitter (< 30 segundos de sequía), NO debe acreditar +3 puntos
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 0)

    def test_penalizacion_descuido_continuo_y_saldo_no_negativo(self):
        # Usuario inicia con saldo 1
        tx_init = TransaccionPuntos(None, 5, 1, 1, "INICIAL", "Inicial", datetime.now(timezone.utc).isoformat(), TIPO_RECOMPENSA)
        self.repo_gamificacion.registrar_transaccion(tx_init)

        # Lecturas en estado crítico por más de 1 hora (temp 50°C > max 35°C y lux 100 < min 5000)
        t0 = datetime(2026, 11, 22, 8, 0, 0, tzinfo=timezone.utc)
        curr = t0
        for _ in range(62):
            self.caso_lectura.registrar(
                dispositivo_id="ESP32-GAM",
                timestamp=curr.isoformat(),
                luminosidad=100.0,
                humedad=2.0,
                temperatura=50.0,
            )
            curr += timedelta(minutes=1)

        # Al cumplirse 1 hora en crítico, descuenta -2, pero el saldo no puede ser negativo (queda en 0)
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
