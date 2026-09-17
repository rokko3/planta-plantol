"""
Pruebas unitarias del dominio.

- No importan Flask.
- No leen el CSV real.
- Usan FakeRepositorio como doble de prueba (implementa IRepositorioEspecies).
- Cubren: clasificación por parámetro, agregación de estado global,
  recomendaciones, casos límite y error de especie no soportada.
"""
import sys
import os
import unittest

# Ajuste de path para que Python encuentre el paquete dominio/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dominio.entidades import (
    ALTO, BAJO, CRITICO, EN_RIESGO, OPTIMO, SALUDABLE,
    RangosEspecie, ResultadoParametro,
)
from dominio.servicios.clasificador import ClasificadorParametro
from dominio.servicios.agregador import AgregarEstado
from aplicacion.evaluar_planta import EvaluarPlanta, SolicitudDiagnostico, EspecieNoSoportadaError


# ---------------------------------------------------------------------------
# Doble de prueba (Fake) — implementa IRepositorioEspecies sin tocar el CSV
# ---------------------------------------------------------------------------

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
    """Doble de prueba de IRepositorioEspecies."""

    _datos = {
        "cactus (cactaceae)": CACTUS,
        "orquídea (orchidaceae)": ORQUIDEA,
    }

    def obtener_rangos(self, especie):
        return self._datos.get(especie.strip().lower())

    def listar_especies(self):
        return list(self._datos.values())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestClasificadorParametro(unittest.TestCase):
    """Prueba la clasificación individual de parámetros (RF2)."""

    def setUp(self):
        self.clf = ClasificadorParametro()
        self.rangos = CACTUS

    # Test 1 — valor en rango óptimo
    def test_clasificacion_optimo(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=10000, humedad=20, temperatura=25
        )
        cls_map = {r.nombre: r.clasificacion for r in resultado}
        self.assertEqual(cls_map["luminosidad"], OPTIMO)
        self.assertEqual(cls_map["humedad"], OPTIMO)
        self.assertEqual(cls_map["temperatura"], OPTIMO)

    # Test 2 — valor por debajo del mínimo
    def test_clasificacion_bajo(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=100, humedad=20, temperatura=25
        )
        lux = next(r for r in resultado if r.nombre == "luminosidad")
        self.assertEqual(lux.clasificacion, BAJO)

    # Test 3 — valor por encima del máximo
    def test_clasificacion_alto(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=20000, humedad=20, temperatura=25
        )
        lux = next(r for r in resultado if r.nombre == "luminosidad")
        self.assertEqual(lux.clasificacion, ALTO)

    # Test 4 — recomendación no vacía cuando fuera de rango (RF4)
    def test_recomendacion_no_vacia_fuera_de_rango(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=100, humedad=20, temperatura=25
        )
        lux = next(r for r in resultado if r.nombre == "luminosidad")
        self.assertNotEqual(lux.recomendacion, "")

    # Test 5 — recomendación vacía cuando OPTIMO (RF4 complementario)
    def test_recomendacion_vacia_cuando_optimo(self):
        resultado = self.clf.clasificar_todos(
            self.rangos, luminosidad=10000, humedad=20, temperatura=25
        )
        temp = next(r for r in resultado if r.nombre == "temperatura")
        self.assertEqual(temp.recomendacion, "")

    # Test 6 — caso límite: valor exacto en el mínimo → OPTIMO
    def test_limite_inferior_es_optimo(self):
        resultado = self.clf.clasificar_uno(
            nombre="luminosidad",
            valor=5000,   # exactamente lux_min
            v_min=5000, v_max=15000,
            reco_bajo="sube la luz",
            reco_alto="baja la luz",
        )
        self.assertEqual(resultado.clasificacion, OPTIMO)

    # Test 7 — caso límite: valor exacto en el máximo → OPTIMO
    def test_limite_superior_es_optimo(self):
        resultado = self.clf.clasificar_uno(
            nombre="luminosidad",
            valor=15000,  # exactamente lux_max
            v_min=5000, v_max=15000,
            reco_bajo="sube la luz",
            reco_alto="baja la luz",
        )
        self.assertEqual(resultado.clasificacion, OPTIMO)


class TestAgregarEstado(unittest.TestCase):
    """Prueba la regla de agregación de estado global (RF3)."""

    def setUp(self):
        self.agg = AgregarEstado()

    def _r(self, nombre, cls):
        return ResultadoParametro(nombre=nombre, valor=0.0, clasificacion=cls, recomendacion="")

    # Test 8 — todos OPTIMO → SALUDABLE
    def test_todos_optimo_es_saludable(self):
        resultados = [self._r("luminosidad", OPTIMO), self._r("humedad", OPTIMO), self._r("temperatura", OPTIMO)]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, SALUDABLE)

    # Test 9 — uno fuera de rango → EN_RIESGO
    def test_uno_fuera_es_en_riesgo(self):
        resultados = [self._r("luminosidad", BAJO), self._r("humedad", OPTIMO), self._r("temperatura", OPTIMO)]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, EN_RIESGO)

    # Test 10 — dos fuera de rango → CRITICO
    def test_dos_fuera_es_critico(self):
        resultados = [self._r("luminosidad", BAJO), self._r("humedad", ALTO), self._r("temperatura", OPTIMO)]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, CRITICO)

    # Test 11 — tres fuera de rango → CRITICO
    def test_tres_fuera_es_critico(self):
        resultados = [self._r("luminosidad", BAJO), self._r("humedad", ALTO), self._r("temperatura", BAJO)]
        diag = self.agg.agregar("Cactus", resultados)
        self.assertEqual(diag.estado_global, CRITICO)


class TestEvaluarPlanta(unittest.TestCase):
    """Prueba el caso de uso completo con doble de repositorio (RA5/DIP)."""

    def setUp(self):
        self.caso = EvaluarPlanta(FakeRepositorio())

    # Test 12 — diagnóstico completo con especie conocida
    def test_diagnostico_con_especie_valida(self):
        sol = SolicitudDiagnostico(
            especie="Cactus (Cactaceae)",
            luminosidad=10000, humedad=20, temperatura=25
        )
        diag = self.caso.ejecutar(sol)
        self.assertEqual(diag.especie, "Cactus (Cactaceae)")
        self.assertEqual(diag.estado_global, SALUDABLE)
        self.assertEqual(len(diag.parametros), 3)

    # Test 13 — especie no soportada lanza EspecieNoSoportadaError (RF6)
    def test_especie_desconocida_lanza_error(self):
        sol = SolicitudDiagnostico(
            especie="Planta Inventada",
            luminosidad=500, humedad=50, temperatura=22
        )
        with self.assertRaises(EspecieNoSoportadaError) as ctx:
            self.caso.ejecutar(sol)
        self.assertEqual(ctx.exception.especie, "Planta Inventada")

    # Test 14 — LSP: FakeRepositorio es sustituible por el repositorio real
    def test_fake_repositorio_satisface_protocolo(self):
        from dominio.puertos import IRepositorioEspecies
        repo = FakeRepositorio()
        self.assertIsInstance(repo, IRepositorioEspecies)


if __name__ == "__main__":
    unittest.main(verbosity=2)
