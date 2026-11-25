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

        self.app = crear_app(tipo_tabla="bd", ruta_db=self.temp_db.name, seed_demo=True)
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

    def test_eliminar_planta(self):
        # 1. Login felipe y registrar carlos
        resp_felipe = self.client.post("/api/auth/login", json={"username": "felipe", "password": "plantol123"})
        token_felipe = resp_felipe.get_json()["token"]

        resp_carlos = self.client.post(
            "/api/auth/register",
            json={"username": "carlos_del", "password": "passCarlos123", "nombre": "Carlos Del"},
        )
        token_carlos = resp_carlos.get_json()["token"]

        # 2. Carlos intenta eliminar la planta 1 de Felipe -> 403 Forbidden
        resp_denegado = self.client.delete(
            "/api/plantas/1",
            headers={"Authorization": f"Bearer {token_carlos}"},
        )
        self.assertEqual(resp_denegado.status_code, 403)

        # 3. Felipe elimina su propia planta 1 -> 200 OK
        resp_del = self.client.delete(
            "/api/plantas/1",
            headers={"Authorization": f"Bearer {token_felipe}"},
        )
        self.assertEqual(resp_del.status_code, 200)
        self.assertTrue(resp_del.get_json()["success"])

        # 4. Consultar la planta eliminada retorna 404
        resp_check = self.client.get(
            "/api/plantas/1",
            headers={"Authorization": f"Bearer {token_felipe}"},
        )
        self.assertEqual(resp_check.status_code, 404)

        # 5. El sensor ESP32-A7F9 que tenía vinculado queda libre en la red
        resp_disp = self.client.get(
            "/api/dispositivos/disponibles",
            headers={"Authorization": f"Bearer {token_felipe}"},
        )
        self.assertEqual(resp_disp.status_code, 200)
        ids = [d["id"] for d in resp_disp.get_json()]
        self.assertIn("ESP32-A7F9", ids)

        # 6. Intentar eliminar planta inexistente -> 404
        resp_inexistente = self.client.delete(
            "/api/plantas/999",
            headers={"Authorization": f"Bearer {token_felipe}"},
        )
        self.assertEqual(resp_inexistente.status_code, 404)

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

    def test_desvincular_dispositivo_y_comportamiento_en_red(self):
        # 1. Login felipe
        resp_login = self.client.post(
            "/api/auth/login",
            json={"username": "felipe", "password": "plantol123"},
        )
        token = resp_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Desvincular ESP32-A7F9 de la planta 1
        resp_desvincular = self.client.post(
            "/api/dispositivos/desvincular",
            json={"planta_id": 1},
            headers=headers,
        )
        self.assertEqual(resp_desvincular.status_code, 200)
        self.assertTrue(resp_desvincular.get_json()["success"])

        # 3. Verificar que la planta ya no tiene sensor asociado
        resp_planta = self.client.get("/api/plantas/1", headers=headers)
        self.assertEqual(resp_planta.status_code, 200)
        self.assertIsNone(resp_planta.get_json()["planta"]["dispositivo_id"])

        # 4. Verificar que el ESP32-A7F9 ahora aparece en los dispositivos disponibles en red
        resp_disp = self.client.get("/api/dispositivos/disponibles", headers=headers)
        self.assertEqual(resp_disp.status_code, 200)
        disponibles = [d["id"] for d in resp_disp.get_json()]
        self.assertIn("ESP32-A7F9", disponibles)

        # 5. Obtener token del dispositivo y enviar telemetría mientras está desvinculado -> HTTP 202
        resp_token = self.client.post("/api/dispositivos/ESP32-A7F9/token")
        token_dev = resp_token.get_json()["token"]
        resp_lectura_unlinked = self.client.post(
            "/api/dispositivos/ESP32-A7F9/lecturas",
            json={"luminosidad": 6000.0, "humedad": 22.0, "temperatura": 24.0},
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        self.assertEqual(resp_lectura_unlinked.status_code, 202)

        # 6. Re-vincular directamente sin códigos ni tokens manuales
        resp_revincular = self.client.post(
            "/api/dispositivos/vincular",
            json={"planta_id": 1, "dispositivo_id": "ESP32-A7F9"},
            headers=headers,
        )
        self.assertEqual(resp_revincular.status_code, 200)

        # 7. La telemetría vuelve a registrarse con éxito -> HTTP 201
        resp_lectura_relinked = self.client.post(
            "/api/dispositivos/ESP32-A7F9/lecturas",
            json={"luminosidad": 6000.0, "humedad": 22.0, "temperatura": 24.0},
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        self.assertEqual(resp_lectura_relinked.status_code, 201)

    def test_info_servidor_ip_y_puerto(self):
        resp = self.client.get("/api/servidor/info")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("ip", data)
        self.assertIn("puerto", data)
        self.assertIn("host_sugerido", data)
        self.assertTrue(data["host_sugerido"].startswith("http://"))

    def test_telemetria_con_humedad_suelo_y_diagnostico_hp_emocion(self):
        resp_token = self.client.post("/api/dispositivos/ESP32-A7F9/token")
        token_dev = resp_token.get_json()["token"]

        # Para Cactus (10-30% humedad), suelo a 22.0% es óptimo
        resp_lectura = self.client.post(
            "/api/dispositivos/ESP32-A7F9/lecturas",
            json={
                "luminosidad": 6000.0,
                "humedad": 22.0,
                "temperatura": 24.0,
                "humedad_suelo": 22.0,
            },
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        self.assertEqual(resp_lectura.status_code, 201)
        datos = resp_lectura.get_json()
        self.assertTrue(datos["success"])
        diag = datos["diagnostico"]
        self.assertIn("hp", diag)
        self.assertIn("estado_emocional", diag)
        self.assertEqual(diag["hp"], 100)
        self.assertEqual(diag["estado_emocional"], "RADIANTE")

    def test_saludo_diario_y_consulta_gamificacion(self):
        # 1. Login felipe (dueño de planta 1 por seed inicial)
        resp_login = self.client.post(
            "/api/auth/login",
            json={"username": "felipe", "password": "plantol123"},
        )
        self.assertEqual(resp_login.status_code, 200)
        token_user = resp_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token_user}"}

        # 2. Saludar a su planta 1 -> 200 OK con +1 punto
        resp_saludo = self.client.post(
            "/api/plantas/1/saludar",
            headers=headers,
        )
        self.assertEqual(resp_saludo.status_code, 200)
        saludo_data = resp_saludo.get_json()
        self.assertTrue(saludo_data["success"])
        self.assertEqual(saludo_data["puntos_ganados"], 1)

        # 3. Intentar saludar de nuevo el mismo día -> 400 Bad Request (idempotente)
        resp_dup = self.client.post(
            "/api/plantas/1/saludar",
            headers=headers,
        )
        self.assertEqual(resp_dup.status_code, 400)
        self.assertEqual(resp_dup.get_json()["error"], "SALUDO_YA_REALIZADO")
        self.assertIn("ya saludó", resp_dup.get_json()["mensaje"].lower())

        # 4. Consultar saldo de puntos
        resp_saldo = self.client.get("/api/gamificacion/puntos", headers=headers)
        self.assertEqual(resp_saldo.status_code, 200)
        self.assertEqual(resp_saldo.get_json()["saldo_puntos"], 1)

        # 5. Consultar historial de transacciones
        resp_hist = self.client.get("/api/gamificacion/historial", headers=headers)
        self.assertEqual(resp_hist.status_code, 200)
        transacciones = resp_hist.get_json()["historial"]
        self.assertEqual(len(transacciones), 1)
        self.assertEqual(transacciones[0]["motivo"], "SALUDO_DIARIO")

    def test_pairing_seguro_y_reclamar_dispositivo(self):
        # 1. Login felipe para obtener token de usuario
        resp_login = self.client.post(
            "/api/auth/login",
            json={"username": "felipe", "password": "plantol123"},
        )
        token_user = resp_login.get_json()["token"]
        headers_user = {"Authorization": f"Bearer {token_user}"}

        # 2. Generar token de emparejamiento desde la sesión del usuario
        resp_gen = self.client.post("/api/dispositivos/generar-token-pairing", headers=headers_user)
        self.assertEqual(resp_gen.status_code, 200)
        token_pairing = resp_gen.get_json()["token"]
        self.assertTrue(token_pairing.startswith("PAIR-"))

        # 3. Intentar reclamar sin token -> HTTP 401
        resp_sin_token = self.client.post(
            "/api/dispositivos/reclamar",
            json={"mac": "ESP32-NUEVO-01"},
        )
        self.assertEqual(resp_sin_token.status_code, 401)
        self.assertEqual(resp_sin_token.get_json()["error"], "TOKEN_PAIRING_INVALIDO")

        # 4. Intentar reclamar con token falso -> HTTP 401
        resp_token_falso = self.client.post(
            "/api/dispositivos/reclamar",
            json={"mac": "ESP32-NUEVO-01", "token": "PAIR-FALSO123"},
        )
        self.assertEqual(resp_token_falso.status_code, 401)

        # 5. Reclamar con el token de pairing legítimo -> HTTP 200
        resp_reclamar = self.client.post(
            "/api/dispositivos/reclamar",
            json={"mac": "ESP32-NUEVO-01", "token": token_pairing},
        )
        self.assertEqual(resp_reclamar.status_code, 200)
        self.assertTrue(resp_reclamar.get_json()["success"])

        # 6. Intentar REUTILIZAR el mismo token de pairing -> HTTP 401 (token ya consumido)
        resp_reuso = self.client.post(
            "/api/dispositivos/reclamar",
            json={"mac": "ESP32-NUEVO-02", "token": token_pairing},
        )
        self.assertEqual(resp_reuso.status_code, 401)

        # 7. El dispositivo reclamado ahora puede obtener su token JWT
        resp_dev_jwt = self.client.post("/api/dispositivos/ESP32-NUEVO-01/token")
        self.assertEqual(resp_dev_jwt.status_code, 200)
        dev_jwt = resp_dev_jwt.get_json()["token"]

        # 8. Un dispositivo desconocido NO puede obtener token JWT -> HTTP 404
        resp_no_dev = self.client.post("/api/dispositivos/ESP32-DESCONOCIDO/token")
        self.assertEqual(resp_no_dev.status_code, 404)

        # 9. Telemetría con token malformado o falso -> HTTP 401
        resp_telemetria_falsa = self.client.post(
            "/api/dispositivos/ESP32-NUEVO-01/lecturas",
            json={"luminosidad": 5000.0, "humedad": 25.0, "temperatura": 24.0},
            headers={"Authorization": "Bearer token_falso_o_corrupto"},
        )
        self.assertEqual(resp_telemetria_falsa.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)

