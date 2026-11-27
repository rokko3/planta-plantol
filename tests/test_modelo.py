"""
Pruebas Unitarias Aisladas del Dominio de Plantol (tests/test_modelo.py).
Restricción arquitectural estricta (Hexagonal):
Corren SIN levantar el servidor web Flask, SIN base de datos y SIN archivos en disco.
Utilizan dobles de prueba (Fakes en memoria) para los puertos de salida.
"""
import os
import sys
import unittest

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
    AccesoDenegadoPlantaError,
    Dispositivo,
    DispositivoNoVinculadoError,
    EspecieNoSoportadaError,
    Lectura,
    LecturaInvalidaError,
    Planta,
    PlantaNoEncontradaError,
    RangosEspecie,
)
from Modelo.negocio import (
    CasoUsoConsultarEstado,
    CasoUsoGestionPlantas,
    CasoUsoRegistrarLectura,
    ValidadorDeEstado,
)
from Modelo.puertos import (
    HistorialLecturasPort,
    RepositorioDispositivosPort,
    RepositorioPlantasPort,
    TablaReferenciaPort,
)

# =====================================================================
# Dobles de Prueba (Fakes en memoria) para los Puertos de Salida
# =====================================================================

CACTUS = RangosEspecie(
    nombre="Cactus (Cactaceae)",
    lux_min=5000.0, lux_max=15000.0,
    humedad_min=10.0, humedad_max=30.0,
    temperatura_min=18.0, temperatura_max=35.0,
)

ORQUIDEA = RangosEspecie(
    nombre="Orquídea (Orchidaceae)",
    lux_min=1000.0, lux_max=3000.0,
    humedad_min=50.0, humedad_max=70.0,
    temperatura_min=18.0, temperatura_max=28.0,
)


class FakeTablaReferencia(TablaReferenciaPort):
    def __init__(self):
        self._datos = {
            "cactus (cactaceae)": CACTUS,
            "orquídea (orchidaceae)": ORQUIDEA,
        }

    def obtener_rangos(self, especie: str):
        return self._datos.get(especie.strip().lower())

    def listar_especies(self):
        return list(self._datos.values())


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
        res = [
            {"lectura": item["lectura"], "diagnostico": item["diagnostico"].to_dict() if item["diagnostico"] else None}
            for item in self.lecturas if item["lectura"].planta_id == planta_id
        ]
        return list(reversed(res))[:limite]

    def obtener_todas_recientes(self, limite: int = 50):
        return list(reversed(self.lecturas))[:limite]


class FakeRepositorioPlantas(RepositorioPlantasPort):
    def __init__(self):
        self._plantas = {}
        self._seq = 1

    def guardar_planta(self, planta: Planta):
        pid = self._seq
        self._seq += 1
        p = Planta(
            id=pid,
            nombre=planta.nombre,
            especie=planta.especie,
            usuario_id=planta.usuario_id,
            dispositivo_id=planta.dispositivo_id,
            ubicacion=planta.ubicacion,
            fecha_creacion=planta.fecha_creacion,
        )
        self._plantas[pid] = p
        return p

    def obtener_por_id(self, planta_id: int):
        return self._plantas.get(planta_id)

    def listar_por_usuario(self, usuario_id: int):
        return [p for p in self._plantas.values() if p.usuario_id == usuario_id]

    def obtener_por_dispositivo(self, dispositivo_id: str):
        for p in self._plantas.values():
            if p.dispositivo_id and p.dispositivo_id.upper() == dispositivo_id.upper():
                return p
        return None

    def vincular_dispositivo(self, planta_id: int, dispositivo_id: str):
        if planta_id in self._plantas:
            self._plantas[planta_id].dispositivo_id = dispositivo_id

    def eliminar_planta(self, planta_id: int) -> bool:
        if planta_id in self._plantas:
            del self._plantas[planta_id]
            return True
        return False


class FakeRepositorioDispositivos(RepositorioDispositivosPort):
    def __init__(self):
        self._dispositivos = {}
        self._codigos = {}

    def guardar_dispositivo(self, dispositivo: Dispositivo):
        self._dispositivos[dispositivo.id] = dispositivo
        return dispositivo

    def buscar_por_id(self, dispositivo_id: str):
        return self._dispositivos.get(dispositivo_id)

    def listar_dispositivos(self):
        return list(self._dispositivos.values())

    def listar_dispositivos_disponibles(self):
        return [d for d in self._dispositivos.values() if d.planta_id is None]

    def registrar_o_conectar_dispositivo(self, dispositivo_id: str, mac=None, red_wifi=None):
        dev = Dispositivo(id=dispositivo_id, secret_hash="hash", mac=mac or "24:6F:28:00:00:00")
        self._dispositivos[dispositivo_id] = dev
        return dev

    def actualizar_ultimo_contacto(self, dispositivo_id: str, fecha_hora: str):
        if dispositivo_id in self._dispositivos:
            self._dispositivos[dispositivo_id].ultimo_contacto = fecha_hora

    def generar_codigo_vinculacion(self, dispositivo_id: str):
        self._codigos["CODE-123"] = dispositivo_id
        return "CODE-123"

    def consumir_codigo_vinculacion(self, codigo: str):
        return self._codigos.pop(codigo, None)

    def guardar_token_pairing(self, token: str, usuario_id: int) -> None:
        self._codigos[token] = f"USER-{usuario_id}"

    def validar_y_consumir_token_pairing(self, token: str) -> bool:
        return self._codigos.pop(token, None) is not None


# =====================================================================
# Pruebas Unitarias del Núcleo de Dominio
# =====================================================================

class TestValidadorDeEstado(unittest.TestCase):
    def setUp(self):
        self.validador = ValidadorDeEstado()
        self.rangos = CACTUS

    def test_clasificacion_optimo(self):
        resultados = self.validador.clasificar_todos(
            self.rangos, luminosidad=10000, humedad=20, temperatura=25
        )
        cls_map = {r.nombre: r.clasificacion for r in resultados}
        self.assertEqual(cls_map["luminosidad"], OPTIMO)
        self.assertEqual(cls_map["humedad"], OPTIMO)
        self.assertEqual(cls_map["temperatura"], OPTIMO)

    def test_clasificacion_bajo_y_alto(self):
        r_bajo = self.validador.clasificar_uno("humedad", 5, 10, 30, "Aumentar", "Reducir")
        self.assertEqual(r_bajo.clasificacion, BAJO)
        self.assertEqual(r_bajo.recomendacion, "Aumentar")

        r_alto = self.validador.clasificar_uno("humedad", 45, 10, 30, "Aumentar", "Reducir")
        self.assertEqual(r_alto.clasificacion, ALTO)
        self.assertEqual(r_alto.recomendacion, "Reducir")

    def test_limites_exactos_son_optimos(self):
        r_min = self.validador.clasificar_uno("lux", 5000, 5000, 15000, "b", "a")
        r_max = self.validador.clasificar_uno("lux", 15000, 5000, 15000, "b", "a")
        self.assertEqual(r_min.clasificacion, OPTIMO)
        self.assertEqual(r_max.clasificacion, OPTIMO)

    def test_agregacion_saludable(self):
        diag = self.validador.evaluar(
            especie="Cactus (Cactaceae)",
            rangos=self.rangos,
            luminosidad=10000,
            humedad=20,
            temperatura=25,
        )
        self.assertEqual(diag.estado_global, SALUDABLE)

    def test_agregacion_en_riesgo(self):
        # 1 parámetro fuera de rango -> EN_RIESGO
        diag = self.validador.evaluar(
            especie="Cactus (Cactaceae)",
            rangos=self.rangos,
            luminosidad=2000,  # Bajo
            humedad=20,
            temperatura=25,
        )
        self.assertEqual(diag.estado_global, EN_RIESGO)

    def test_agregacion_critico(self):
        # 2 parámetros fuera de rango -> CRITICO
        diag = self.validador.evaluar(
            especie="Cactus (Cactaceae)",
            rangos=self.rangos,
            luminosidad=2000,  # Bajo
            humedad=50,       # Alto
            temperatura=25,
        )
        self.assertEqual(diag.estado_global, CRITICO)

    def test_validacion_lectura_fisica_valida(self):
        # No debe lanzar excepción
        self.validador.validar_lectura_fisica(luminosidad=5000, humedad=50, temperatura=22)

    def test_validacion_lectura_fisica_invalida(self):
        # Humedad negativa imposible
        with self.assertRaises(LecturaInvalidaError):
            self.validador.validar_lectura_fisica(luminosidad=5000, humedad=-15, temperatura=22)

        # Temperatura extrema imposible
        with self.assertRaises(LecturaInvalidaError):
            self.validador.validar_lectura_fisica(luminosidad=5000, humedad=50, temperatura=150)

        # Luminosidad negativa
        with self.assertRaises(LecturaInvalidaError):
            self.validador.validar_lectura_fisica(luminosidad=-100, humedad=50, temperatura=22)


class TestReglaDeNegocioPropiedadPlanta(unittest.TestCase):
    """Prueba que la regla de negocio 'un usuario solo ve sus plantas' pertenece al dominio."""

    def setUp(self):
        self.validador = ValidadorDeEstado()
        self.repo_plantas = FakeRepositorioPlantas()
        self.historial = FakeHistorialLecturas()
        self.repo_dispositivos = FakeRepositorioDispositivos()

        self.caso = CasoUsoConsultarEstado(
            validador=self.validador,
            repo_plantas=self.repo_plantas,
            historial_lecturas=self.historial,
            repo_dispositivos=self.repo_dispositivos,
        )

        # Usuario 1 crea su planta (id 1)
        self.planta_usuario_1 = self.repo_plantas.guardar_planta(
            Planta(id=0, nombre="Mi Cactus", especie="Cactus (Cactaceae)", usuario_id=1)
        )

    def test_usuario_propietario_accede_con_exito(self):
        resultado = self.caso.consultar_estado_planta(usuario_id=1, planta_id=self.planta_usuario_1.id)
        self.assertEqual(resultado["planta"]["nombre"], "Mi Cactus")

    def test_usuario_ajeno_recibe_acceso_denegado(self):
        # Usuario 2 intenta consultar la planta del Usuario 1
        with self.assertRaises(AccesoDenegadoPlantaError) as ctx:
            self.caso.consultar_estado_planta(usuario_id=2, planta_id=self.planta_usuario_1.id)

        self.assertIn("Acceso denegado", str(ctx.exception))
        self.assertEqual(ctx.exception.usuario_id, 2)
        self.assertEqual(ctx.exception.planta_id, self.planta_usuario_1.id)


class TestCasoUsoRegistrarLectura(unittest.TestCase):
    def setUp(self):
        self.validador = ValidadorDeEstado()
        self.tabla = FakeTablaReferencia()
        self.repo_plantas = FakeRepositorioPlantas()
        self.historial = FakeHistorialLecturas()
        self.repo_dispositivos = FakeRepositorioDispositivos()

        self.caso = CasoUsoRegistrarLectura(
            validador=self.validador,
            tabla_referencia=self.tabla,
            repo_plantas=self.repo_plantas,
            repo_dispositivos=self.repo_dispositivos,
            historial_lecturas=self.historial,
        )

        # Registra dispositivo y planta vinculada
        self.dev = self.repo_dispositivos.guardar_dispositivo(
            Dispositivo(id="ESP32-A7F9", secret_hash="hash")
        )
        self.planta = self.repo_plantas.guardar_planta(
            Planta(0, "Cactus", "Cactus (Cactaceae)", usuario_id=1, dispositivo_id="ESP32-A7F9")
        )

    def test_registro_exitoso_y_persistencia(self):
        diag = self.caso.registrar(
            dispositivo_id="ESP32-A7F9",
            timestamp="2026-10-22T16:00:00",
            luminosidad=8000,
            humedad=20,
            temperatura=25,
        )
        self.assertEqual(diag.estado_global, SALUDABLE)
        self.assertEqual(len(self.historial.lecturas), 1)
        self.assertEqual(self.dev.ultimo_contacto, "2026-10-22T16:00:00")

    def test_registro_dispositivo_no_vinculado_lanza_error(self):
        with self.assertRaises(DispositivoNoVinculadoError):
            self.caso.registrar(
                dispositivo_id="ESP32-DESCONOCIDO",
                timestamp="2026-10-22T16:00:00",
                luminosidad=8000,
                humedad=20,
                temperatura=25,
            )

    def test_registro_con_telemetria_invalida_lanza_error(self):
        with self.assertRaises(LecturaInvalidaError):
            self.caso.registrar(
                dispositivo_id="ESP32-A7F9",
                timestamp="2026-10-22T16:00:00",
                luminosidad=-50,
                humedad=20,
                temperatura=25,
            )


class TestCasoUsoGestionPlantas(unittest.TestCase):
    def setUp(self):
        self.validador = ValidadorDeEstado()
        self.tabla = FakeTablaReferencia()
        self.repo_plantas = FakeRepositorioPlantas()
        self.repo_dispositivos = FakeRepositorioDispositivos()

        self.caso = CasoUsoGestionPlantas(
            validador=self.validador,
            repo_plantas=self.repo_plantas,
            repo_dispositivos=self.repo_dispositivos,
            tabla_referencia=self.tabla,
        )

        # Dispositivo registrado en la red
        self.dev = self.repo_dispositivos.guardar_dispositivo(
            Dispositivo(id="ESP32-A7F9", secret_hash="hash")
        )
        # Planta del usuario 1 vinculada al ESP32
        self.planta = self.repo_plantas.guardar_planta(
            Planta(id=0, nombre="Cactus", especie="Cactus (Cactaceae)", usuario_id=1, dispositivo_id="ESP32-A7F9")
        )
        self.dev.planta_id = self.planta.id

    def test_crear_planta_exitoso(self):
        nueva = self.caso.crear_planta(
            usuario_id=1,
            nombre="Orquídea Sala",
            especie="Orquídea (Orchidaceae)",
            ubicacion="Sala",
        )
        self.assertEqual(nueva.nombre, "Orquídea Sala")
        self.assertEqual(nueva.usuario_id, 1)

    def test_crear_planta_especie_no_soportada(self):
        with self.assertRaises(EspecieNoSoportadaError):
            self.caso.crear_planta(
                usuario_id=1,
                nombre="Pino",
                especie="Pino Desconocido",
                ubicacion="Jardín",
            )

    def test_desvincular_dispositivo_libera_esp32(self):
        ok = self.caso.desvincular_dispositivo(usuario_id=1, planta_id=self.planta.id)
        self.assertTrue(ok)
        planta_act = self.repo_plantas.obtener_por_id(self.planta.id)
        self.assertIsNone(planta_act.dispositivo_id)
        dev_act = self.repo_dispositivos.buscar_por_id("ESP32-A7F9")
        self.assertIsNone(dev_act.planta_id)

    def test_eliminar_planta_exitoso_y_libera_esp32(self):
        ok = self.caso.eliminar_planta(usuario_id=1, planta_id=self.planta.id)
        self.assertTrue(ok)

        # La planta ya no existe en el repositorio
        self.assertIsNone(self.repo_plantas.obtener_por_id(self.planta.id))

        # El ESP32 fue liberado
        dev_act = self.repo_dispositivos.buscar_por_id("ESP32-A7F9")
        self.assertIsNone(dev_act.planta_id)

    def test_eliminar_planta_usuario_ajeno_denegado(self):
        with self.assertRaises(AccesoDenegadoPlantaError):
            self.caso.eliminar_planta(usuario_id=2, planta_id=self.planta.id)

    def test_eliminar_planta_inexistente(self):
        self.assertRaises(PlantaNoEncontradaError, self.caso.eliminar_planta, usuario_id=1, planta_id=999)


class TestDiagnosticoLuminicoContextual(unittest.TestCase):
    """Pruebas del Objetivo A: 4 niveles de iluminación, especies y protección ante picos momentáneos."""

    def setUp(self):
        self.val = ValidadorDeEstado()
        self.orquidea = RangosEspecie("Orquídea (Orchidaceae)", 1000.0, 3000.0, 50.0, 70.0, 18.0, 28.0)
        self.cactus = RangosEspecie("Cactus (Cactaceae)", 5000.0, 15000.0, 10.0, 30.0, 18.0, 35.0)

    def test_cuatro_niveles_iluminacion_y_especies(self):
        # Crítica insuficiente (< 30% de 1000 = 300 lux)
        d_crit = self.val.evaluar("Orquídea (Orchidaceae)", self.orquidea, 50.0, 60.0, 22.0)
        self.assertEqual(d_crit.resumen_luminico["nivel"], "CRITICA_INSUFICIENTE")
        self.assertEqual(d_crit.estado_global, EN_RIESGO)
        self.assertEqual(d_crit.hp, 50)

        # Baja pero tolerable (500 lux para Orquídea 1000-3000) -> 75 HP
        d_tol = self.val.evaluar("Orquídea (Orchidaceae)", self.orquidea, 500.0, 60.0, 22.0)
        self.assertEqual(d_tol.resumen_luminico["nivel"], "BAJA_TOLERABLE")
        self.assertEqual(d_tol.hp, 75)

        # Para Cactus (min 5000), esos mismos 500 lux son CRITICA_INSUFICIENTE
        d_cac = self.val.evaluar("Cactus (Cactaceae)", self.cactus, 500.0, 20.0, 24.0)
        self.assertEqual(d_cac.resumen_luminico["nivel"], "CRITICA_INSUFICIENTE")
        self.assertEqual(d_cac.hp, 50)

        # Adecuada y Excesiva
        d_ok = self.val.evaluar("Orquídea (Orchidaceae)", self.orquidea, 1800.0, 60.0, 22.0)
        self.assertEqual(d_ok.resumen_luminico["nivel"], "ADECUADA")
        self.assertEqual(d_ok.estado_global, SALUDABLE)
        self.assertEqual(d_ok.hp, 100)

        d_exc = self.val.evaluar("Orquídea (Orchidaceae)", self.orquidea, 6500.0, 60.0, 22.0)
        self.assertEqual(d_exc.resumen_luminico["nivel"], "EXCESIVA")
        self.assertEqual(d_exc.estado_global, EN_RIESGO)

    def test_pico_momentaneo_no_declara_saludable_tras_oscuridad_cronica(self):
        # Historial reciente en oscuridad (5 lecturas de 20 lux)
        hist_oscuro = [20.0, 22.0, 18.0, 25.0, 19.0]
        # 1 lectura puntual alta (linterna 8000 lux) -> NO debe marcar SALUDABLE
        d_pico = self.val.evaluar("Cactus (Cactaceae)", self.cactus, 8000.0, 20.0, 24.0, historial_lux=hist_oscuro)
        self.assertTrue(d_pico.resumen_luminico["es_pico_momentaneo"])
        self.assertEqual(d_pico.resumen_luminico["lux_actual"], 8000.0)
        self.assertNotEqual(d_pico.estado_global, SALUDABLE)

        # Lectura sostenida (>= 2 previas óptimas + actual = 3 consecutivas) -> sí marca ADECUADA / SALUDABLE
        hist_sostenido = [7500.0, 7800.0, 20.0, 20.0, 20.0]
        d_sost = self.val.evaluar("Cactus (Cactaceae)", self.cactus, 8000.0, 20.0, 24.0, historial_lux=hist_sostenido)
        self.assertFalse(d_sost.resumen_luminico["es_pico_momentaneo"])
        self.assertEqual(d_sost.resumen_luminico["nivel"], "ADECUADA")
        self.assertEqual(d_sost.estado_global, SALUDABLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)

