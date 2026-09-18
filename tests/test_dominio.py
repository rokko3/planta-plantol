import os
import sys
import unittest

# Permite ejecutar las pruebas directamente sin requerir instalacion previa del paquete
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
    RangosEspecie,
    ResultadoParametro,
)
from Modelo.clasificador import ClasificadorParametro
from Modelo.agregador import AgregarEstado
from Modelo.evaluar_planta import (
    EspecieNoSoportadaError,
    EvaluarPlanta,
    SolicitudDiagnostico,
)
from Modelo.puertos import IRepositorioEspecies

# Doble de prueba en memoria para aislar los tests de archivos en disco o red
CACTUS = RangosEspecie(
    nombre="Cactus (Cactaceae)",
    lux_min=5000, lux_max=15000,
    humedad_min=10, humedad_max=30,
    temperatura_min=18, temperatura_max=35,
)

ORQUIDEA = RangosEspecie(
    nombre="Orquídea (Orchidaceae)",
    lux_min=1000, lux_max=3000,
    humedad_min=50, humedad_max=70,
    temperatura_min=18, temperatura_max=28,
)


class FakeRepositorio:
    _datos = {
        "cactus (cactaceae)": CACTUS,
        "orquídea (orchidaceae)": ORQUIDEA,
    }

    def obtener_rangos(self, especie: str):
        return self._datos.get(especie.strip().lower())

    def listar_especies(self):
        return list(self._datos.values())


class TestClasificadorParametro(unittest.TestCase):
    def setUp(self):
        self.clf = ClasificadorParametro()
        self.rangos = CACTUS

    def test_clasificacion_optimo(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=10000, humedad=20, temperatura=25
        )
        cls_map = {r.nombre: r.clasificacion for r in resultado}
        self.assertEqual(cls_map["luminosidad"], OPTIMO)
        self.assertEqual(cls_map["humedad"], OPTIMO)
        self.assertEqual(cls_map["temperatura"], OPTIMO)

    def test_clasificacion_bajo(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=100, humedad=20, temperatura=25
        )
        lux = next(r for r in resultado if r.nombre == "luminosidad")
        self.assertEqual(lux.clasificacion, BAJO)

    def test_clasificacion_alto(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=20000, humedad=20, temperatura=25
        )
        lux = next(r for r in resultado if r.nombre == "luminosidad")
        self.assertEqual(lux.clasificacion, ALTO)

    def test_recomendacion_no_vacia_fuera_de_rango(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=100, humedad=20, temperatura=25
        )
        lux = next(r for r in resultado if r.nombre == "luminosidad")
        self.assertNotEqual(lux.recomendacion, "")

    def test_recomendacion_vacia_cuando_optimo(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=10000, humedad=20, temperatura=25
        )
        temp = next(r for r in resultado if r.nombre == "temperatura")
        self.assertEqual(temp.recomendacion, "")

    def test_limite_inferior_es_optimo(self):
        resultado = self.clf.clasificar_uno(
            nombre="luminosidad",
            valor=5000,
            v_min=5000, v_max=15000,
            reco_bajo="sube la luz",
            reco_alto="baja la luz",
        )
        self.assertEqual(resultado.clasificacion, OPTIMO)

    def test_limite_superior_es_optimo(self):
        resultado = self.clf.clasificar_uno(
            nombre="luminosidad",
            valor=15000,
            v_min=5000, v_max=15000,
            reco_bajo="sube la luz",
            reco_alto="baja la luz",
        )
        self.assertEqual(resultado.clasificacion, OPTIMO)


class TestAgregarEstado(unittest.TestCase):
    def setUp(self):
        self.agg = AgregarEstado()

    def _r(self, nombre, cls):
        return ResultadoParametro(nombre=nombre, valor=0.0, clasificacion=cls, recomendacion="")

    def test_todos_optimo_es_saludable(self):
        resultados = [
            self._r("luminosidad", OPTIMO),
            self._r("humedad", OPTIMO),
            self._r("temperatura", OPTIMO),
        ]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, SALUDABLE)

    def test_uno_fuera_es_en_riesgo(self):
        resultados = [
            self._r("luminosidad", BAJO),
            self._r("humedad", OPTIMO),
            self._r("temperatura", OPTIMO),
        ]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, EN_RIESGO)

    def test_dos_fuera_es_critico(self):
        resultados = [
            self._r("luminosidad", BAJO),
            self._r("humedad", ALTO),
            self._r("temperatura", OPTIMO),
        ]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, CRITICO)

    def test_tres_fuera_es_critico(self):
        resultados = [
            self._r("luminosidad", BAJO),
            self._r("humedad", ALTO),
            self._r("temperatura", BAJO),
        ]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, CRITICO)


class TestEvaluarPlanta(unittest.TestCase):
    def setUp(self):
        self.caso = EvaluarPlanta(FakeRepositorio())

    def test_diagnostico_con_especie_valida(self):
        sol = SolicitudDiagnostico(
            especie="Cactus (Cactaceae)",
            luminosidad=10000, humedad=20, temperatura=25
        )
        diag = self.caso.ejecutar(sol)
        self.assertEqual(diag.especie, "Cactus (Cactaceae)")
        self.assertEqual(diag.estado_global, SALUDABLE)
        self.assertEqual(len(diag.parametros), 3)

    def test_especie_desconocida_lanza_error(self):
        sol = SolicitudDiagnostico(
            especie="Planta Fantasma",
            luminosidad=500, humedad=50, temperatura=22
        )
        with self.assertRaises(EspecieNoSoportadaError) as ctx:
            self.caso.ejecutar(sol)
        self.assertEqual(ctx.exception.especie, "Planta Fantasma")

    def test_fake_repositorio_satisface_protocolo(self):
        repo = FakeRepositorio()
        self.assertIsInstance(repo, IRepositorioEspecies)


if __name__ == "__main__":
    unittest.main(verbosity=2)
