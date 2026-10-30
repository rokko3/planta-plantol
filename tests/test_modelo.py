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
    DiagnosticoPlanta,
    Dispositivo,
    DispositivoNoVinculadoError,
    EspecieNoSoportadaError,
    Lectura,
    LecturaInvalidaError,
    Planta,
    RangosEspecie,
    ResultadoParametro,
)
from Modelo.negocio import (
    CasoUsoConsultarEstado,
    CasoUsoEvaluarPlantaManual,
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

    def actualizar_ultimo_contacto(self, dispositivo_id: str, fecha_hora: str):
        if dispositivo_id in self._dispositivos:
            self._dispositivos[dispositivo_id].ultimo_contacto = fecha_hora

    def generar_codigo_vinculacion(self, dispositivo_id: str):
        self._codigos["CODE-123"] = dispositivo_id
        return "CODE-123"

    def consumir_codigo_vinculacion(self, codigo: str):
        return self._codigos.pop(codigo, None)


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


class TestCasoUsoEvaluarPlantaManual(unittest.TestCase):
    def setUp(self):
        self.validador = ValidadorDeEstado()
        self.tabla = FakeTablaReferencia()
        self.caso = CasoUsoEvaluarPlantaManual(self.validador, self.tabla)

    def test_evaluacion_manual_valida(self):
        diag = self.caso.evaluar_manual(
            especie="Cactus (Cactaceae)",
            luminosidad=10000,
            humedad=20,
            temperatura=25,
        )
        self.assertEqual(diag.estado_global, SALUDABLE)

    def test_especie_desconocida_lanza_error(self):
        with self.assertRaises(EspecieNoSoportadaError):
            self.caso.evaluar_manual(
                especie="Bonsai Inexistente",
                luminosidad=10000,
                humedad=20,
                temperatura=25,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

