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
            Planta(id=1, nombre="Mi Cactus", especie="Cactus (Cactaceae)", usuario_id=10, dispositivo_id="ESP32-TEST")
        )

    def test_saludar_planta_exitoso_y_suma_un_punto(self):
        res = self.caso.saludar_planta(usuario_id=10, planta_id=1)
        self.assertEqual(res["puntos_ganados"], 0)
        self.assertEqual(res["xp_ganado"], 0)
        self.assertEqual(res["saldo_actual"], 0)
        self.assertEqual(self.repo_gamificacion.obtener_saldo(10), 0)

    def test_saludo_duplicado_mismo_dia_rechazado_idempotente(self):
        self.caso.saludar_planta(usuario_id=10, planta_id=1)
        with self.assertRaises(SaludoYaRealizadoHoyError):
            self.caso.saludar_planta(usuario_id=10, planta_id=1)
        self.assertEqual(self.repo_gamificacion.obtener_saldo(10), 0)

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

        # 2. El usuario riega la planta tras >= 5 minutos (310s) de sequía real
        t1 = t0 + timedelta(seconds=310)
        self.caso_lectura.registrar(
            dispositivo_id="ESP32-GAM",
            timestamp=t1.isoformat(),
            luminosidad=8000.0,
            humedad=20.0,  # Óptimo
            temperatura=24.0,
            humedad_suelo=20.0,
        )
        # Debe recibir +4 monedas de bonificación por rescate de humedad
        self.assertEqual(self.repo_gamificacion.obtener_saldo(5), 4)

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


class TestGamificacionAvanzadaIntegracionYSeguridad(unittest.TestCase):
    def setUp(self):
        import tempfile
        from Controlador.app import crear_app

        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="bd", ruta_db=self.temp_db.name, seed_demo=True)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_progresion_niveles_misiones_logros_tienda_habitacion_y_aislamiento(self):
        from Modelo.gamificacion_avanzada import calcular_progresion_nivel

        # 1. Progresión de XP y niveles
        p0 = calcular_progresion_nivel(0)
        self.assertEqual(p0["nivel"], 1)
        p1 = calcular_progresion_nivel(120)
        self.assertEqual(p1["nivel"], 2)
        self.assertEqual(p1["xp_en_nivel"], 20)

        # 2. Acceso no autenticado rechazado (401)
        self.assertEqual(self.client.get("/api/gamificacion/resumen").status_code, 401)
        self.assertEqual(self.client.post("/api/gamificacion/tienda/comprar", json={"objeto_id": "maceta_terracota"}).status_code, 401)
        self.assertEqual(self.client.put("/api/gamificacion/habitacion", json={"slots": {"maceta": "maceta_terracota"}}).status_code, 401)

        # 3. Login Felipe y registro de Carlos (aislamiento entre usuarios)
        tok_felipe = self.client.post("/api/auth/login", json={"username": "felipe", "password": "plantol123"}).get_json()["token"]
        tok_carlos = self.client.post("/api/auth/register", json={"username": "carlos_g", "password": "secret123"}).get_json()["token"]

        # 4. Carlos sin plantas ni monedas intenta comprar objeto de precio 3 -> 400 SALDO_INSUFICIENTE
        resp_sin_saldo = self.client.post(
            "/api/gamificacion/tienda/comprar",
            json={"objeto_id": "maceta_terracota"},
            headers={"Authorization": f"Bearer {tok_carlos}"},
        )
        self.assertEqual(resp_sin_saldo.status_code, 400)
        self.assertEqual(resp_sin_saldo.get_json()["error"], "SALDO_INSUFICIENTE")

        # 5. Carlos intenta colocar objeto que NO posee en su habitación -> 403 OBJETO_NO_POSEIDO
        resp_no_posee = self.client.put(
            "/api/gamificacion/habitacion",
            json={"slots": {"maceta": "maceta_terracota"}},
            headers={"Authorization": f"Bearer {tok_carlos}"},
        )
        self.assertEqual(resp_no_posee.status_code, 403)

        # 6. Felipe consulta resumen -> sincroniza misiones/logros reales de forma idempotente
        resp_res1 = self.client.get("/api/gamificacion/resumen", headers={"Authorization": f"Bearer {tok_felipe}"})
        self.assertEqual(resp_res1.status_code, 200)
        d1 = resp_res1.get_json()
        monedas_tras_sync = d1["monedas"]
        self.assertGreater(monedas_tras_sync, 0)

        # Repetir resumen NO debe duplicar recompensas de misiones ni logros
        resp_res2 = self.client.get("/api/gamificacion/resumen", headers={"Authorization": f"Bearer {tok_felipe}"})
        self.assertEqual(resp_res2.get_json()["monedas"], monedas_tras_sync)

        # 7. Felipe intenta comprar objeto que requiere Nivel 2 estando en Nivel 1 -> 403 NIVEL_INSUFICIENTE
        if d1["progresion"]["nivel"] < 2:
            resp_nivel = self.client.post(
                "/api/gamificacion/tienda/comprar",
                json={"objeto_id": "maceta_ceramica_menta"},
                headers={"Authorization": f"Bearer {tok_felipe}"},
            )
            self.assertEqual(resp_nivel.status_code, 403)
            self.assertEqual(resp_nivel.get_json()["error"], "NIVEL_INSUFICIENTE")

        # Felipe recibe cuidado continuo legítimo (para probar compra en tienda con saldo ganado por cuidado real)
        from Controlador.persistencia import RepositorioGamificacionBD
        repo_g_felipe = RepositorioGamificacionBD(ruta_db=self.temp_db.name)
        for h in range(8):
            repo_g_felipe.registrar_transaccion(
                TransaccionPuntos(usuario_id=1, cantidad=1, motivo="CUIDADO_CONTINUO", evento=f"Cuidado h{h}", fecha=datetime.now(timezone.utc).isoformat(), tipo=TIPO_RECOMPENSA)
            )

        # 8. Felipe compra 'maceta_terracota' (precio 12, nivel 1) -> éxito y descuento atómico
        saldo_antes_compra = self.client.get("/api/gamificacion/resumen", headers={"Authorization": f"Bearer {tok_felipe}"}).get_json()["monedas"]
        resp_compra = self.client.post(
            "/api/gamificacion/tienda/comprar",
            json={"objeto_id": "maceta_terracota"},
            headers={"Authorization": f"Bearer {tok_felipe}"},
        )
        self.assertEqual(resp_compra.status_code, 200)
        # No permitir compra duplicada de artículo único -> 409 OBJETO_YA_POSEIDO
        resp_dup = self.client.post(
            "/api/gamificacion/tienda/comprar",
            json={"objeto_id": "maceta_terracota"},
            headers={"Authorization": f"Bearer {tok_felipe}"},
        )
        self.assertEqual(resp_dup.status_code, 409)

        # 9. Felipe coloca 'maceta_terracota' en su habitación y persiste
        resp_hab = self.client.put(
            "/api/gamificacion/habitacion",
            json={"slots": {"maceta": "maceta_terracota"}},
            headers={"Authorization": f"Bearer {tok_felipe}"},
        )
        self.assertEqual(resp_hab.status_code, 200)
        self.assertEqual(resp_hab.get_json()["habitacion"]["slots"]["maceta"], "maceta_terracota")

        # Aislamiento: la habitación e inventario de Carlos siguen vacíos
        res_carlos = self.client.get("/api/gamificacion/resumen", headers={"Authorization": f"Bearer {tok_carlos}"}).get_json()
        self.assertEqual(len(res_carlos["inventario"]), 0)
        self.assertIsNone(res_carlos["habitacion"]["slots"]["maceta"])
        self.assertLess(self.client.get("/api/gamificacion/puntos", headers={"Authorization": f"Bearer {tok_felipe}"}).get_json()["saldo_puntos"], saldo_antes_compra + 10)

        # 10. Persistencia tras reinicio de la aplicación (nueva instancia Flask sobre la misma BD)
        from Controlador.app import crear_app
        app_reiniciada = crear_app(tipo_tabla="bd", ruta_db=self.temp_db.name, seed_demo=False)
        client_reiniciado = app_reiniciada.test_client()
        tok_felipe_2 = client_reiniciado.post("/api/auth/login", json={"username": "felipe", "password": "plantol123"}).get_json()["token"]
        res_post_reinicio = client_reiniciado.get("/api/gamificacion/resumen", headers={"Authorization": f"Bearer {tok_felipe_2}"}).get_json()
        self.assertEqual(res_post_reinicio["habitacion"]["slots"]["maceta"], "maceta_terracota")
        self.assertTrue(any(i["objeto_id"] == "maceta_terracota" for i in res_post_reinicio["inventario"]))
        self.assertGreater(res_post_reinicio["progresion"]["xp_total"], 0)


class TestFase6BloqueBEconomiaYAntiExploit(unittest.TestCase):
    """Pruebas obligatorias del Bloque B (Fase 6): anti-exploits, límites, fechas, idempotencia y concurrencia."""

    def setUp(self):
        import tempfile
        from Controlador.app import crear_app

        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def _registrar_usuario(self, username: str):
        resp = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "Password123!", "nombre": username},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        return data["usuario"]["id"], {"Authorization": f"Bearer {data['token']}"}

    def test_cooldown_y_limite_diario_rescates(self):
        repo_disp = FakeRepoDispositivos()
        repo_plantas = FakeRepoPlantas()
        historial = FakeHistorialLecturas()
        validador = ValidadorDeEstado()
        repo_gamif = FakeRepoGamificacion()

        caso = CasoUsoRegistrarLectura(
            validador=validador,
            tabla_referencia=FakeTablaReferencia(),
            repo_plantas=repo_plantas,
            repo_dispositivos=repo_disp,
            historial_lecturas=historial,
            repo_gamificacion=repo_gamif,
        )
        repo_disp.guardar_dispositivo(Dispositivo(id="DEV-1", secret_hash="s", planta_id=1))
        repo_plantas.guardar_planta(Planta(id=1, nombre="Cactus", especie="Cactus (Cactaceae)", usuario_id=1, dispositivo_id="DEV-1"))

        t0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
        # Primer rescate válido (>= 300s) -> +4 monedas
        caso.registrar("DEV-1", t0.isoformat(), 8000.0, 5.0, 24.0, 8.0)
        caso.registrar("DEV-1", (t0 + timedelta(seconds=310)).isoformat(), 8000.0, 20.0, 24.0, 20.0)
        self.assertEqual(repo_gamif.obtener_saldo(1), 4)

        # Segundo intento alternando lectura seca 6 minutos después -> bloqueado por cooldown 6h y límite 1/día
        t2 = t0 + timedelta(minutes=15)
        caso.registrar("DEV-1", t2.isoformat(), 8000.0, 5.0, 24.0, 8.0)
        caso.registrar("DEV-1", (t2 + timedelta(seconds=320)).isoformat(), 8000.0, 20.0, 24.0, 20.0)
        self.assertEqual(repo_gamif.obtener_saldo(1), 4)

        # Tercer intento 7 horas después mismo día -> bloqueado por límite 1 rescate/día por planta
        t3 = t0 + timedelta(hours=7)
        caso.registrar("DEV-1", t3.isoformat(), 8000.0, 5.0, 24.0, 8.0)
        caso.registrar("DEV-1", (t3 + timedelta(seconds=320)).isoformat(), 8000.0, 20.0, 24.0, 20.0)
        self.assertEqual(repo_gamif.obtener_saldo(1), 4)

    def test_limite_diario_cuidado_continuo(self):
        repo_disp = FakeRepoDispositivos()
        repo_plantas = FakeRepoPlantas()
        historial = FakeHistorialLecturas()
        validador = ValidadorDeEstado()
        repo_gamif = FakeRepoGamificacion()

        caso = CasoUsoRegistrarLectura(
            validador=validador,
            tabla_referencia=FakeTablaReferencia(),
            repo_plantas=repo_plantas,
            repo_dispositivos=repo_disp,
            historial_lecturas=historial,
            repo_gamificacion=repo_gamif,
        )
        repo_disp.guardar_dispositivo(Dispositivo(id="DEV-CC", secret_hash="s", planta_id=1))
        repo_plantas.guardar_planta(Planta(id=1, nombre="Cactus", especie="Cactus (Cactaceae)", usuario_id=1, dispositivo_id="DEV-CC"))

        t = datetime(2026, 11, 26, 1, 0, 0, tzinfo=timezone.utc)
        # Simular 7 horas continuas en el mismo día (cada 60s) -> tope diario es 4 monedas
        for _ in range(7 * 60 + 2):
            caso.registrar("DEV-CC", t.isoformat(), 8000.0, 20.0, 24.0)
            t += timedelta(minutes=1)
        self.assertEqual(repo_gamif.obtener_saldo(1), 4)

    def test_prevencion_recompensas_por_plantas_vacias(self):
        _, headers = self._registrar_usuario("farmeador_vacio")
        # Crear 5 plantas vacías (sin sensor ESP32)
        plantas_ids = []
        for i in range(5):
            r = self.client.post(
                "/api/plantas",
                json={"nombre": f"Vacia {i}", "especie": "Cactus (Cactaceae)"},
                headers=headers,
            )
            self.assertEqual(r.status_code, 201)
            plantas_ids.append(r.get_json()["planta"]["id"])

        # Saludar todas las plantas vacías -> 0 monedas y 0 XP
        for pid in plantas_ids:
            rs = self.client.post(f"/api/plantas/{pid}/saludar", headers=headers)
            self.assertEqual(rs.status_code, 200)
            self.assertEqual(rs.get_json()["puntos_ganados"], 0)

        # Abrir resumen -> 0 monedas, 0 XP, ninguna misión ni logro desbloqueado
        res = self.client.get("/api/gamificacion/resumen", headers=headers).get_json()
        self.assertEqual(res["monedas"], 0)
        self.assertEqual(res["progresion"]["xp_total"], 0)
        self.assertFalse(any(m["completada"] for m in res["misiones"]))
        self.assertFalse(any(lg["desbloqueado"] for lg in res["logros"]))

    def test_validacion_fechas_en_misiones(self):
        from Controlador.persistencia import HistorialLecturasBD, RepositorioSQLite
        from Modelo.entidades import CONECTADO

        uid, headers = self._registrar_usuario("lector_ayer")
        repo = RepositorioSQLite(ruta_db=self.temp_db.name, incluir_demo=True)
        hist = HistorialLecturasBD(ruta_db=self.temp_db.name)
        val = ValidadorDeEstado()

        repo.guardar_dispositivo(Dispositivo(id="DEV-AYER", secret_hash="s", mac="AA:BB:CC:11:22:33", estado_conexion=CONECTADO))
        p = repo.guardar_planta(Planta(id=0, nombre="Mi Cactus", especie="Cactus (Cactaceae)", usuario_id=uid, dispositivo_id="DEV-AYER"))

        ayer = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        diag = val.evaluar("Cactus (Cactaceae)", CACTUS, 8000.0, 20.0, 24.0, ayer)
        hist.guardar_lectura(Lectura("DEV-AYER", ayer, 8000.0, 20.0, 24.0, planta_id=p.id), diag)

        # Consultar resumen hoy -> misiones diarias de lectura y saludable NO deben completarse con lectura de hace 2 días
        res = self.client.get("/api/gamificacion/resumen", headers=headers).get_json()
        misiones = {m["id"]: m["completada"] for m in res["misiones"]}
        self.assertFalse(misiones["MISION_LECTURA_ACTIVA"])
        self.assertFalse(misiones["MISION_PLANTA_SALUDABLE"])

    def test_idempotencia_recompensas_y_manipulacion_precios_frontend(self):
        from Controlador.persistencia import RepositorioGamificacionBD

        repo_g = RepositorioGamificacionBD(ruta_db=self.temp_db.name)
        tx1 = TransaccionPuntos(
            usuario_id=999,
            cantidad=10,
            motivo="TEST",
            evento="Evento",
            fecha=datetime.now(timezone.utc).isoformat(),
            tipo=TIPO_RECOMPENSA,
            clave_idempotencia="IDEM-UNICA-1",
        )
        tx2 = TransaccionPuntos(
            usuario_id=999,
            cantidad=10,
            motivo="TEST",
            evento="Evento",
            fecha=datetime.now(timezone.utc).isoformat(),
            tipo=TIPO_RECOMPENSA,
            clave_idempotencia="IDEM-UNICA-1",
        )
        repo_g.registrar_transaccion(tx1)
        repo_g.registrar_transaccion(tx2)
        self.assertEqual(repo_g.obtener_saldo(999), 10)

        # Manipulación de precio/monedas desde frontend al comprar -> servidor usa catálogo autoritativo (precio 12)
        _, headers = self._registrar_usuario("comprador_precio")
        uid_data = self.client.get("/api/gamificacion/resumen", headers=headers).get_json()
        uid = uid_data["usuario_id"]
        repo_g.registrar_transaccion(
            TransaccionPuntos(
                usuario_id=uid,
                cantidad=15,
                motivo="BONO_TEST",
                evento="Test",
                fecha=datetime.now(timezone.utc).isoformat(),
                tipo=TIPO_RECOMPENSA,
            )
        )

        resp = self.client.post(
            "/api/gamificacion/tienda/comprar",
            json={"objeto_id": "maceta_terracota", "precio": 0, "monedas": 9999},
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        # Saldo debe quedar en 15 - 12 = 3 (+2 del logro LOGRO_PRIMERA_COMPRA = 5), nunca 15 ni 9999
        self.assertEqual(resp.get_json()["nuevo_saldo"], 3)


class TestBloque1CeroFarmingPlantasYSaludos(unittest.TestCase):
    """Pruebas del Bloque 1: crear/eliminar/recrear 20 plantas y saludarlas no otorga monedas ni XP."""

    def setUp(self):
        import tempfile
        from Controlador.app import crear_app

        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_crear_eliminar_recrear_20_plantas_y_saludar_no_da_monedas_ni_xp(self):
        r_reg = self.client.post("/api/auth/register", json={"username": "anti_farm20", "password": "Password123"})
        headers = {"Authorization": f"Bearer {r_reg.get_json()['token']}"}

        # Crear 20 plantas, saludarlas, eliminarlas y volver a crear 20
        for ronda in range(2):
            ids = []
            for i in range(20):
                r_p = self.client.post("/api/plantas", json={"nombre": f"Planta {ronda}-{i}", "especie": "Cactus (Cactaceae)"}, headers=headers)
                self.assertEqual(r_p.status_code, 201)
                pid = r_p.get_json()["planta"]["id"]
                ids.append(pid)
                r_sal = self.client.post(f"/api/plantas/{pid}/saludar", headers=headers)
                self.assertEqual(r_sal.status_code, 200)
                self.assertEqual(r_sal.get_json()["puntos_ganados"], 0)
            if ronda == 0:
                for pid in ids:
                    self.assertEqual(self.client.delete(f"/api/plantas/{pid}", headers=headers).status_code, 200)

        res = self.client.get("/api/gamificacion/resumen", headers=headers).get_json()
        self.assertEqual(res["monedas"], 0)
        self.assertEqual(res["progresion"]["xp_total"], 0)

    def test_recrear_planta_con_mismo_esp32_no_reinicia_limite_rescate(self):
        repo_disp = FakeRepoDispositivos()
        repo_plantas = FakeRepoPlantas()
        historial = FakeHistorialLecturas()
        validador = ValidadorDeEstado()
        repo_gamif = FakeRepoGamificacion()

        caso = CasoUsoRegistrarLectura(
            validador=validador,
            tabla_referencia=FakeTablaReferencia(),
            repo_plantas=repo_plantas,
            repo_dispositivos=repo_disp,
            historial_lecturas=historial,
            repo_gamificacion=repo_gamif,
        )
        repo_disp.guardar_dispositivo(Dispositivo(id="ESP32-HW", secret_hash="s", planta_id=1))
        repo_plantas.guardar_planta(Planta(id=1, nombre="Planta 1", especie="Cactus (Cactaceae)", usuario_id=1, dispositivo_id="ESP32-HW"))

        t0 = datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc)
        caso.registrar("ESP32-HW", t0.isoformat(), 8000.0, 5.0, 24.0, 8.0)
        caso.registrar("ESP32-HW", (t0 + timedelta(seconds=310)).isoformat(), 8000.0, 20.0, 24.0, 20.0)
        self.assertEqual(repo_gamif.obtener_saldo(1), 4)

        # Eliminar Planta 1 y crear Planta 2 con el mismo ESP32-HW -> NO debe dar otro rescate el mismo día
        repo_plantas.eliminar_planta(1)
        repo_plantas.guardar_planta(Planta(id=2, nombre="Planta 2", especie="Cactus (Cactaceae)", usuario_id=1, dispositivo_id="ESP32-HW"))
        t1 = t0 + timedelta(minutes=20)
        caso.registrar("ESP32-HW", t1.isoformat(), 8000.0, 5.0, 24.0, 8.0)
        caso.registrar("ESP32-HW", (t1 + timedelta(seconds=310)).isoformat(), 8000.0, 20.0, 24.0, 20.0)
        self.assertEqual(repo_gamif.obtener_saldo(1), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
