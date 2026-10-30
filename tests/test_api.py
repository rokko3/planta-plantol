"""
Pruebas de Integración de la API y Adaptadores (tests/test_api.py).
Verifica:
- Requisito R1: Diagnóstico manual funcionando tras puerto de entrada (/api/diagnostico).
- Requisito R2: Recepción de telemetría ESP32 (/api/dispositivos/<id>/lecturas).
- Requisito R3: Rechazo de lecturas corruptas/inválidas (400 Bad Request).
- Requisito R4: Cambio de CSV a BD por configuración sin tocar el dominio (/api/config/fuente).
- Requisito R5: Historial de lecturas persistido en SQLite (/api/plantas/<id>/historial).
- Requisito R7: Autenticación con JWT (tokens de usuario vs tokens de dispositivo con alcances separados y regla de propiedad).
"""
import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from Controlador.app import crear_app


class TestAPI(unittest.TestCase):
    def setUp(self):
        # Crear base de datos SQLite temporal para aislamiento de pruebas
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        self.app = crear_app(tipo_tabla="bd", ruta_db=self.temp_db.name)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_auth_registro_e_inicio_sesion(self):
        # Registro
        resp = self.client.post(
            "/api/auth/register",
            json={
                "username": "mariana",
                "password": "passwordSeguro123",
                "nombre": "Mariana Gómez",
                "email": "mariana@test.com",
            },
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIn("token", data)
        token = data["token"]

        # Login
        resp_login = self.client.post(
            "/api/auth/login",
            json={"username": "mariana", "password": "passwordSeguro123"},
        )
        self.assertEqual(resp_login.status_code, 200)
        login_data = resp_login.get_json()
        self.assertIn("token", login_data)

        # Acceso con token de usuario a endpoint protegido
        resp_me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp_me.status_code, 200)

    def test_reporte_lectura_esp32_con_jwt_dispositivo(self):
        # 1. Obtener token del dispositivo
        resp_token = self.client.post("/api/dispositivos/ESP32-A7F9/token")
        self.assertEqual(resp_token.status_code, 200)
        token_dev = resp_token.get_json()["token"]

        # 2. Enviar lectura con token de dispositivo
        resp_lectura = self.client.post(
            "/api/dispositivos/ESP32-A7F9/lecturas",
            json={
                "timestamp": "2026-10-22T16:10:00",
                "luminosidad": 6000.0,
                "humedad": 22.0,
                "temperatura": 24.0,
            },
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        self.assertEqual(resp_lectura.status_code, 201)
        datos = resp_lectura.get_json()
        self.assertTrue(datos["success"])
        self.assertEqual(datos["diagnostico"]["estado_global"], "SALUDABLE")

    def test_rechazo_lectura_con_token_de_otro_dispositivo(self):
        # Token emitido para ESP32-A7F9 usado para suplantar ESP32-C204
        resp_token = self.client.post("/api/dispositivos/ESP32-A7F9/token")
        token_a7f9 = resp_token.get_json()["token"]

        resp_lectura = self.client.post(
            "/api/dispositivos/ESP32-C204/lecturas",
            json={"luminosidad": 4000.0, "humedad": 60.0, "temperatura": 22.0},
            headers={"Authorization": f"Bearer {token_a7f9}"},
        )
        self.assertEqual(resp_lectura.status_code, 403)
        self.assertEqual(resp_lectura.get_json()["error"], "IDENTIDAD_NO_COINCIDE")

    def test_rechazo_lecturas_invalidas_r3(self):
        resp_token = self.client.post("/api/dispositivos/ESP32-A7F9/token")
        token_dev = resp_token.get_json()["token"]

        # Telemetría físicamente corrupta (humedad negativa)
        resp_lectura = self.client.post(
            "/api/dispositivos/ESP32-A7F9/lecturas",
            json={"luminosidad": 4000.0, "humedad": -35.0, "temperatura": 22.0},
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        self.assertEqual(resp_lectura.status_code, 400)
        self.assertEqual(resp_lectura.get_json()["error"], "LECTURA_INVALIDA")

    def test_intercambio_tabla_referencia_csv_y_bd(self):
        # Modo BD
        app_bd = crear_app(tipo_tabla="bd", ruta_db=self.temp_db.name)
        client_bd = app_bd.test_client()
        resp_bd = client_bd.get("/api/config/fuente")
        self.assertEqual(resp_bd.get_json()["fuente_referencia"], "bd")

        # Modo CSV
        app_csv = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name)
        client_csv = app_csv.test_client()
        resp_csv = client_csv.get("/api/config/fuente")
        self.assertEqual(resp_csv.get_json()["fuente_referencia"], "csv")

    def test_regla_propiedad_usuario_no_accede_a_planta_ajena(self):
        # Usuario 1 (Felipe inicial)
        resp_login_felipe = self.client.post(
            "/api/auth/login",
            json={"username": "felipe", "password": "plantol123"},
        )
        token_felipe = resp_login_felipe.get_json()["token"]

        # Crear Usuario 2 (Carlos)
        resp_reg = self.client.post(
            "/api/auth/register",
            json={"username": "carlos", "password": "passCarlos123", "nombre": "Carlos"},
        )
        token_carlos = resp_reg.get_json()["token"]

        # Felipe consulta su planta (ID 1) -> HTTP 200
        resp_ok = self.client.get(
            "/api/plantas/1",
            headers={"Authorization": f"Bearer {token_felipe}"},
        )
        self.assertEqual(resp_ok.status_code, 200)

        # Carlos intenta consultar la planta de Felipe (ID 1) -> HTTP 403 Forbidden por regla de dominio
        resp_denegado = self.client.get(
            "/api/plantas/1",
            headers={"Authorization": f"Bearer {token_carlos}"},
        )
        self.assertEqual(resp_denegado.status_code, 403)
        self.assertEqual(resp_denegado.get_json()["error"], "ACCESO_DENEGADO")

    def test_diagnostico_manual_r1(self):
        resp = self.client.post(
            "/api/diagnostico",
            json={
                "especie": "Cactus (Cactaceae)",
                "luminosidad": 8000,
                "humedad": 20,
                "temperatura": 25,
            },
        )
        self.assertEqual(resp.status_code, 200)
        datos = resp.get_json()
        self.assertTrue(datos["success"])
        self.assertEqual(datos["estado_global"], "SALUDABLE")

    def test_historial_lecturas_r5(self):
        # Felipe consulta el historial de su planta 1
        resp_login = self.client.post(
            "/api/auth/login",
            json={"username": "felipe", "password": "plantol123"},
        )
        token = resp_login.get_json()["token"]

        resp_hist = self.client.get(
            "/api/plantas/1/historial",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp_hist.status_code, 200)
        historial = resp_hist.get_json()
        self.assertIsInstance(historial, list)
        self.assertGreater(len(historial), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

