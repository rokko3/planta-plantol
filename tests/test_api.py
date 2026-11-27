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

        # 2. Saludar a su planta 1 -> 200 OK como interacción social (0 monedas, 0 XP)
        resp_saludo = self.client.post(
            "/api/plantas/1/saludar",
            headers=headers,
        )
        self.assertEqual(resp_saludo.status_code, 200)
        saludo_data = resp_saludo.get_json()
        self.assertTrue(saludo_data["success"])
        self.assertEqual(saludo_data["puntos_ganados"], 0)
        self.assertEqual(saludo_data["xp_ganado"], 0)

        # 3. Intentar saludar de nuevo el mismo día -> 400 Bad Request (idempotente)
        resp_dup = self.client.post(
            "/api/plantas/1/saludar",
            headers=headers,
        )
        self.assertEqual(resp_dup.status_code, 400)
        self.assertEqual(resp_dup.get_json()["error"], "SALUDO_YA_REALIZADO")
        self.assertIn("ya saludó", resp_dup.get_json()["mensaje"].lower())

        # 4. Consultar saldo de puntos -> sigue en 0 (saludar no farmea monedas)
        resp_saldo = self.client.get("/api/gamificacion/puntos", headers=headers)
        self.assertEqual(resp_saldo.status_code, 200)
        self.assertEqual(resp_saldo.get_json()["saldo_puntos"], 0)

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

    def test_fase1_modo_demo_y_historial_humedad_suelo(self):
        # 1. Por defecto PLANTOL_DEMO no está habilitado -> /api/auth/demo responde 403
        os.environ.pop("PLANTOL_DEMO", None)
        resp_demo_off = self.client.post("/api/auth/demo")
        self.assertEqual(resp_demo_off.status_code, 403)

        resp_cfg = self.client.get("/api/config/fuente")
        self.assertFalse(resp_cfg.get_json()["modo_demo"])

        # 2. Con PLANTOL_DEMO=1 -> /api/auth/demo inicia sesión sin exponer credenciales en frontend
        os.environ["PLANTOL_DEMO"] = "1"
        try:
            resp_demo_on = self.client.post("/api/auth/demo")
            self.assertEqual(resp_demo_on.status_code, 200)
            self.assertIn("token", resp_demo_on.get_json())
        finally:
            os.environ.pop("PLANTOL_DEMO", None)

        # 3. GET en /token no debe emitir JWT (rechazado con 404/405)
        resp_get_tok = self.client.get("/api/dispositivos/ESP32-A7F9/token")
        self.assertIn(resp_get_tok.status_code, (404, 405))

        # 4. Historial debe incluir humedad_suelo explícitamente
        resp_login = self.client.post("/api/auth/login", json={"username": "felipe", "password": "plantol123"})
        token_felipe = resp_login.get_json()["token"]
        resp_dev = self.client.post("/api/dispositivos/ESP32-A7F9/token")
        dev_jwt = resp_dev.get_json()["token"]

        self.client.post(
            "/api/dispositivos/ESP32-A7F9/lecturas",
            json={"luminosidad": 5500.0, "humedad": 35.0, "humedad_suelo": 48.0, "temperatura": 24.0},
            headers={"Authorization": f"Bearer {dev_jwt}"},
        )
        resp_hist = self.client.get(
            "/api/plantas/1/historial",
            headers={"Authorization": f"Bearer {token_felipe}"},
        )
        self.assertEqual(resp_hist.status_code, 200)
        self.assertEqual(resp_hist.get_json()[0]["humedad_suelo"], 48.0)

    def test_fase1_migracion_segura_codigos_vinculacion(self):
        import sqlite3
        from Controlador.persistencia import RepositorioSQLite

        temp_mig = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_mig.close()
        try:
            with sqlite3.connect(temp_mig.name) as conn:
                conn.execute(
                    "CREATE TABLE codigos_vinculacion (codigo TEXT PRIMARY KEY, dispositivo_id TEXT NOT NULL, creado_en TEXT NOT NULL, usado INTEGER DEFAULT 0)"
                )
                conn.execute(
                    "INSERT INTO codigos_vinculacion (codigo, dispositivo_id, creado_en, usado) VALUES ('PLT-OLD1', 'ESP32-OLD', '2026-10-01T10:00:00', 0)"
                )
                conn.commit()

            repo = RepositorioSQLite(ruta_db=temp_mig.name)
            self.assertTrue(repo.validar_y_consumir_token_pairing("PLT-OLD1"))
        finally:
            try:
                os.unlink(temp_mig.name)
            except Exception:
                pass


class TestFase6BloqueADispositivos(unittest.TestCase):
    """Pruebas del Bloque A (Fase 6): detección real, ventana de actividad 120s y separación demo/real."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.client = self.app.test_client()
        resp_reg = self.client.post(
            "/api/auth/register",
            json={
                "username": "usuario_real",
                "password": "password123",
                "nombre": "Usuario Real",
                "email": "real@ejemplo.com",
            },
        )
        self.assertEqual(resp_reg.status_code, 201)
        self.token = resp_reg.get_json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_filtrado_dispositivos_conectados_y_recientes(self):
        import datetime
        from Controlador.persistencia import RepositorioSQLite
        from Modelo.entidades import CONECTADO, Dispositivo

        repo = RepositorioSQLite(ruta_db=self.temp_db.name, incluir_demo=False)
        ahora = datetime.datetime.now()
        hace_30s = (ahora - datetime.timedelta(seconds=30)).isoformat()
        hace_180s = (ahora - datetime.timedelta(seconds=180)).isoformat()

        repo.guardar_dispositivo(
            Dispositivo(id="441BF6823F1C", secret_hash="h1", mac="44:1B:F6:82:3F:1C", ultimo_contacto=hace_30s, estado_conexion=CONECTADO, usuario_id=1)
        )
        repo.guardar_dispositivo(
            Dispositivo(id="ESP32-VIEJO", secret_hash="h2", mac="AA:BB:CC:DD:EE:01", ultimo_contacto=hace_180s, estado_conexion=CONECTADO, usuario_id=1)
        )

        resp = self.client.get("/api/dispositivos/disponibles", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        datos = resp.get_json()
        ids = [d["id"] for d in datos]
        self.assertEqual(ids, ["441BF6823F1C"])
        self.assertTrue(datos[0]["en_linea"])
        self.assertEqual(datos[0]["ventana_actividad_seg"], 120)

    def test_ocultamiento_dispositivos_historicos_y_estado_sin_respuesta(self):
        import datetime
        from Controlador.persistencia import RepositorioSQLite
        from Modelo.entidades import CONECTADO, Dispositivo, SIN_RESPUESTA

        repo = RepositorioSQLite(ruta_db=self.temp_db.name, incluir_demo=False)
        ahora = datetime.datetime.now()
        hace_dos_dias = (ahora - datetime.timedelta(days=2)).isoformat()
        hace_10s = (ahora - datetime.timedelta(seconds=10)).isoformat()

        repo.guardar_dispositivo(
            Dispositivo(id="AC276EA8E100", secret_hash="h1", mac="AC276EA8E100", ultimo_contacto=hace_dos_dias, estado_conexion=CONECTADO, usuario_id=1)
        )
        repo.guardar_dispositivo(
            Dispositivo(id="DEV-CAIDO", secret_hash="h2", mac="11:22:33:44:55:66", ultimo_contacto=hace_10s, estado_conexion=SIN_RESPUESTA, usuario_id=1)
        )

        resp_disp = self.client.get("/api/dispositivos/disponibles", headers=self.headers)
        self.assertEqual(resp_disp.status_code, 200)
        self.assertEqual(resp_disp.get_json(), [])

        resp_todos = self.client.get("/api/dispositivos", headers=self.headers)
        self.assertEqual(resp_todos.status_code, 200)
        por_id = {d["id"]: d for d in resp_todos.get_json()}
        self.assertIn("AC276EA8E100", por_id)
        self.assertFalse(por_id["AC276EA8E100"]["en_linea"])
        self.assertEqual(por_id["AC276EA8E100"]["estado_conexion"], SIN_RESPUESTA)
        self.assertFalse(por_id["AC276EA8E100"]["disponible"])
        self.assertFalse(por_id["DEV-CAIDO"]["en_linea"])

    def test_separacion_datos_demo_y_reales(self):
        import datetime
        from Controlador.persistencia import RepositorioSQLite
        from Modelo.entidades import CONECTADO, Dispositivo

        # 1. En modo real (seed_demo=False), no existen dispositivos demo sembrados
        resp_init = self.client.get("/api/dispositivos", headers=self.headers)
        self.assertEqual(resp_init.status_code, 200)
        self.assertEqual(resp_init.get_json(), [])

        # 2. Aunque exista un registro marcado es_demo=True en la BD, el repositorio real lo excluye
        repo_demo = RepositorioSQLite(ruta_db=self.temp_db.name, incluir_demo=True)
        ahora = datetime.datetime.now().isoformat()
        repo_demo.guardar_dispositivo(
            Dispositivo(id="ESP32-A7F9", secret_hash="h", mac="A4:CF:12:8B:30:91", ultimo_contacto=ahora, estado_conexion=CONECTADO, es_demo=True, usuario_id=1)
        )
        repo_demo.guardar_dispositivo(
            Dispositivo(id="441BF6823F1C", secret_hash="h", mac="441BF6823F1C", ultimo_contacto=ahora, estado_conexion=CONECTADO, es_demo=False, usuario_id=1)
        )

        resp_real = self.client.get("/api/dispositivos/disponibles", headers=self.headers)
        self.assertEqual(resp_real.status_code, 200)
        ids = [d["id"] for d in resp_real.get_json()]
        self.assertEqual(ids, ["441BF6823F1C"])
        self.assertNotIn("ESP32-A7F9", ids)


class TestAutenticacionIndependienteYBloqueos(unittest.TestCase):
    """Pruebas del Objetivo B: bloqueo estricto de endpoints privados sin sesión y aislamiento entre usuarios."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_endpoints_privados_bloqueados_sin_sesion(self):
        rutas_get = [
            "/api/dashboard",
            "/api/plantas",
            "/api/dispositivos",
            "/api/dispositivos/disponibles",
            "/api/gamificacion/resumen",
        ]
        for ruta in rutas_get:
            resp = self.client.get(ruta)
            self.assertEqual(resp.status_code, 401, f"Se esperaba 401 en {ruta}")

        self.assertEqual(self.client.post("/api/plantas", json={"nombre": "X", "especie": "Cactus (Cactaceae)"}).status_code, 401)
        self.assertEqual(self.client.post("/api/gamificacion/tienda/comprar", json={"objeto_id": "maceta_terracota"}).status_code, 401)
        self.assertEqual(self.client.put("/api/gamificacion/habitacion", json={"slots": {"maceta": "maceta_terracota"}}).status_code, 401)

    def test_registro_login_y_aislamiento_entre_usuarios(self):
        r_a = self.client.post("/api/auth/register", json={"username": "ana_p", "password": "Password123", "nombre": "Ana"})
        r_b = self.client.post("/api/auth/register", json={"username": "luis_p", "password": "Password123", "nombre": "Luis"})
        self.assertEqual(r_a.status_code, 201)
        self.assertEqual(r_b.status_code, 201)

        tok_a = r_a.get_json()["token"]
        tok_b = r_b.get_json()["token"]
        p_id = self.client.post(
            "/api/plantas",
            json={"nombre": "Orquídea Ana", "especie": "Orquídea (Orchidaceae)"},
            headers={"Authorization": f"Bearer {tok_a}"},
        ).get_json()["planta"]["id"]

        # Usuario B no ve plantas de Ana y recibe 403 al intentar consultar su estado
        self.assertEqual(self.client.get("/api/plantas", headers={"Authorization": f"Bearer {tok_b}"}).get_json(), [])
        self.assertEqual(self.client.get(f"/api/plantas/{p_id}", headers={"Authorization": f"Bearer {tok_b}"}).status_code, 403)


class TestBloque2EstadoRealESP32(unittest.TestCase):
    """Pruebas del Bloque 2: estado real conectado/desconectado del ESP32 en dashboard y plantas."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_esp32_apagado_o_sin_comunicacion_aparece_desconectado_y_recupera_al_transmitir(self):
        import datetime
        from Controlador.persistencia import RepositorioSQLite
        from Modelo.entidades import CONECTADO, Dispositivo, SIN_RESPUESTA

        tok_u = self.client.post("/api/auth/register", json={"username": "carlos_esp", "password": "Password123"}).get_json()["token"]
        h_u = {"Authorization": f"Bearer {tok_u}"}

        # 1. Registrar y reclamar ESP32
        tok_pair = self.client.post("/api/dispositivos/generar-token-pairing", headers=h_u).get_json()["token"]
        rec = self.client.post("/api/dispositivos/reclamar", json={"mac": "AA:BB:CC:11:22:33", "token": tok_pair}).get_json()
        dev_id = rec["dispositivo_id"]
        h_d = {"Authorization": f"Bearer {rec['token']}"}

        p_id = self.client.post("/api/plantas", json={"nombre": "Pothos", "especie": "Pothos (Epipremnum aureum)"}, headers=h_u).get_json()["planta"]["id"]
        self.client.post("/api/dispositivos/vincular", json={"planta_id": p_id, "dispositivo_id": dev_id}, headers=h_u)

        # 2. ESP32 activo -> conectado en dashboard y detalle
        dash_on = self.client.get("/api/dashboard", headers=h_u).get_json()
        self.assertEqual(dash_on["stats"]["sensores_conectados"], 1)
        self.assertEqual(dash_on["plantas"][0]["dispositivo"]["estado_conexion"], CONECTADO)
        self.assertTrue(dash_on["plantas"][0]["dispositivo"]["en_linea"])

        # 3. Simular ESP32 apagado (último contacto hace 5 minutos > 120 s) aunque estado_conexion en BD siga 'CONECTADO'
        repo = RepositorioSQLite(ruta_db=self.temp_db.name, incluir_demo=False)
        dev = repo.buscar_por_id(dev_id)
        dev.ultimo_contacto = (datetime.datetime.now() - datetime.timedelta(minutes=5)).isoformat()
        repo.guardar_dispositivo(dev)

        dash_off = self.client.get("/api/dashboard", headers=h_u).get_json()
        self.assertEqual(dash_off["stats"]["sensores_conectados"], 0)
        self.assertEqual(dash_off["plantas"][0]["dispositivo"]["estado_conexion"], SIN_RESPUESTA)
        self.assertFalse(dash_off["plantas"][0]["dispositivo"]["en_linea"])

        # 4. ESP32 vuelve a transmitir lectura real -> recupera estado CONECTADO automáticamente
        ahora = datetime.datetime.now().isoformat()
        r_lec = self.client.post(f"/api/dispositivos/{dev_id}/lecturas", json={"luminosidad": 2000, "humedad": 55, "temperatura": 23, "timestamp": ahora}, headers=h_d)
        self.assertEqual(r_lec.status_code, 201)
        dash_back = self.client.get("/api/dashboard", headers=h_u).get_json()
        self.assertEqual(dash_back["stats"]["sensores_conectados"], 1)
        self.assertEqual(dash_back["plantas"][0]["dispositivo"]["estado_conexion"], CONECTADO)
        self.assertTrue(dash_back["plantas"][0]["dispositivo"]["en_linea"])


class TestBloque3RevinculacionSinBluetooth(unittest.TestCase):
    """Pruebas del Bloque 3: desvincular conserva ESP32/credenciales/historial y permite re-vincular sin BLE."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_flujo_completo_vincular_a_desvincular_re_vincular_b_sin_bluetooth(self):
        import datetime

        tok_u = self.client.post("/api/auth/register", json={"username": "lucia_v", "password": "Password123"}).get_json()["token"]
        h_u = {"Authorization": f"Bearer {tok_u}"}

        # 1-2. Configurar y reclamar ESP32 (equivalente al paso BLE + Wi-Fi)
        tok_pair = self.client.post("/api/dispositivos/generar-token-pairing", headers=h_u).get_json()["token"]
        rec = self.client.post("/api/dispositivos/reclamar", json={"mac": "BB:22:33:44:55:66", "token": tok_pair}).get_json()
        dev_id = rec["dispositivo_id"]
        h_d = {"Authorization": f"Bearer {rec['token']}"}

        # 3-4. Crear Planta A y Planta B, vincular a Planta A
        p_a = self.client.post("/api/plantas", json={"nombre": "Planta A", "especie": "Cactus (Cactaceae)"}, headers=h_u).get_json()["planta"]["id"]
        p_b = self.client.post("/api/plantas", json={"nombre": "Planta B", "especie": "Helecho (Nephrolepis)"}, headers=h_u).get_json()["planta"]["id"]
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_a, "dispositivo_id": dev_id}, headers=h_u).status_code, 200)

        # Prevenir vínculo simultáneo a Planta B mientras está en Planta A (409)
        r_dup = self.client.post("/api/dispositivos/vincular", json={"planta_id": p_b, "dispositivo_id": dev_id}, headers=h_u)
        self.assertEqual(r_dup.status_code, 409)

        # 5. Enviar lectura a Planta A
        t1 = datetime.datetime.now().isoformat()
        self.assertEqual(self.client.post(f"/api/dispositivos/{dev_id}/lecturas", json={"luminosidad": 7000, "humedad": 20, "temperatura": 25, "timestamp": t1}, headers=h_d).status_code, 201)

        # 6-7. Desvincular de Planta A -> dispositivo sigue registrado y disponible sin BLE
        self.assertEqual(self.client.post("/api/dispositivos/desvincular", json={"planta_id": p_a, "dispositivo_id": dev_id}, headers=h_u).status_code, 200)
        devs = self.client.get("/api/dispositivos", headers=h_u).get_json()
        self.assertTrue(any(d["id"] == dev_id and d["planta_id"] is None for d in devs))

        # 8-9. Re-vincular a Planta B SIN repetir Bluetooth ni token de pairing y enviar lectura a Planta B
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_b, "dispositivo_id": dev_id}, headers=h_u).status_code, 200)
        t2 = datetime.datetime.now().isoformat()
        self.assertEqual(self.client.post(f"/api/dispositivos/{dev_id}/lecturas", json={"luminosidad": 3000, "humedad": 70, "temperatura": 21, "timestamp": t2}, headers=h_d).status_code, 201)

        # 10. Historial de Planta A conserva su lectura original (7000 lux) y no se mezcla con Planta B (3000 lux)
        hist_a = self.client.get(f"/api/plantas/{p_a}/historial", headers=h_u).get_json()
        hist_b = self.client.get(f"/api/plantas/{p_b}/historial", headers=h_u).get_json()
        self.assertEqual(len(hist_a), 1)
        self.assertEqual(hist_a[0]["luminosidad"], 7000.0)
        self.assertEqual(len(hist_b), 1)
        self.assertEqual(hist_b[0]["luminosidad"], 3000.0)


class TestFase2PropiedadYAislamientoESP32(unittest.TestCase):
    """Pruebas de Fase 2: propiedad verificable por pairing, aislamiento estricto y cero dispositivos fantasma."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.app = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_aislamiento_estricto_y_bloqueo_dispositivos_ajenos_o_sin_propietario(self):
        import datetime
        from Controlador.persistencia import RepositorioSQLite
        from Modelo.entidades import CONECTADO, Dispositivo

        # Crear usuario A (dueño legítimo) y usuario B (cuenta nueva sin ESP32)
        tok_a = self.client.post("/api/auth/register", json={"username": "dueno_esp", "password": "Password123"}).get_json()["token"]
        tok_b = self.client.post("/api/auth/register", json={"username": "cuenta_nueva", "password": "Password123"}).get_json()["token"]
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}

        # 1. Usuario A reclama su ESP32 mediante token pairing BLE
        tok_pair = self.client.post("/api/dispositivos/generar-token-pairing", headers=h_a).get_json()["token"]
        rec = self.client.post("/api/dispositivos/reclamar", json={"mac": "441BF6823F1C", "token": tok_pair}).get_json()
        self.assertEqual(rec["dispositivo_id"], "441BF6823F1C")
        h_d = {"Authorization": f"Bearer {rec['token']}"}

        # También existe un dispositivo sin propietario (huérfano) en BD
        repo = RepositorioSQLite(ruta_db=self.temp_db.name, incluir_demo=False)
        repo.guardar_dispositivo(
            Dispositivo(id="HUERFANO01", secret_hash="h", mac="HUERFANO01", ultimo_contacto=datetime.datetime.now().isoformat(), estado_conexion=CONECTADO, usuario_id=None)
        )

        # 2. Cuenta nueva B NO ve dispositivos de A ni el huérfano
        self.assertEqual(self.client.get("/api/dispositivos", headers=h_b).get_json(), [])
        self.assertEqual(self.client.get("/api/dispositivos/disponibles", headers=h_b).get_json(), [])

        # 3. Cuenta B crea una planta e intenta vincular el ESP32 de A o el huérfano o uno inventado -> rechazado
        p_b = self.client.post("/api/plantas", json={"nombre": "Planta B", "especie": "Cactus (Cactaceae)"}, headers=h_b).get_json()["planta"]["id"]
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_b, "dispositivo_id": "441BF6823F1C"}, headers=h_b).status_code, 403)
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_b, "dispositivo_id": "HUERFANO01"}, headers=h_b).status_code, 403)
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_b, "dispositivo_id": "INVENTADO99"}, headers=h_b).status_code, 404)
        self.assertEqual(self.client.post("/api/plantas", json={"nombre": "Bypass", "especie": "Cactus (Cactaceae)", "dispositivo_id": "441BF6823F1C"}, headers=h_b).status_code, 403)

        # 4. Cuenta B tampoco puede reclamar el ESP32 ya perteneciente a A
        tok_pair_b = self.client.post("/api/dispositivos/generar-token-pairing", headers=h_b).get_json()["token"]
        self.assertEqual(self.client.post("/api/dispositivos/reclamar", json={"mac": "441BF6823F1C", "token": tok_pair_b}).status_code, 403)

        # 5. Usuario A sí ve su ESP32, vincula a Planta A1, envía lectura, desvincula y re-vincula a Planta A2 sin BLE
        self.assertEqual([d["id"] for d in self.client.get("/api/dispositivos/disponibles", headers=h_a).get_json()], ["441BF6823F1C"])
        p_a1 = self.client.post("/api/plantas", json={"nombre": "A1", "especie": "Cactus (Cactaceae)"}, headers=h_a).get_json()["planta"]["id"]
        p_a2 = self.client.post("/api/plantas", json={"nombre": "A2", "especie": "Helecho (Nephrolepis)"}, headers=h_a).get_json()["planta"]["id"]
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_a1, "dispositivo_id": "441BF6823F1C"}, headers=h_a).status_code, 200)
        self.assertEqual(self.client.post("/api/dispositivos/441BF6823F1C/lecturas", json={"luminosidad": 7200, "humedad": 20, "temperatura": 24, "timestamp": datetime.datetime.now().isoformat()}, headers=h_d).status_code, 201)
        self.assertEqual(self.client.post("/api/dispositivos/desvincular", json={"planta_id": p_a1, "dispositivo_id": "441BF6823F1C"}, headers=h_a).status_code, 200)
        self.assertEqual(self.client.post("/api/dispositivos/vincular", json={"planta_id": p_a2, "dispositivo_id": "441BF6823F1C"}, headers=h_a).status_code, 200)

        # 6. Persistencia de propiedad e historial tras reiniciar el backend
        app2 = crear_app(tipo_tabla="csv", ruta_db=self.temp_db.name, seed_demo=False)
        c2 = app2.test_client()
        tok_a2 = c2.post("/api/auth/login", json={"username": "dueno_esp", "password": "Password123"}).get_json()["token"]
        tok_b2 = c2.post("/api/auth/login", json={"username": "cuenta_nueva", "password": "Password123"}).get_json()["token"]
        self.assertEqual([d["id"] for d in c2.get("/api/dispositivos", headers={"Authorization": f"Bearer {tok_a2}"}).get_json()], ["441BF6823F1C"])
        self.assertEqual(c2.get("/api/dispositivos", headers={"Authorization": f"Bearer {tok_b2}"}).get_json(), [])
        self.assertEqual(len(c2.get(f"/api/plantas/{p_a1}/historial", headers={"Authorization": f"Bearer {tok_a2}"}).get_json()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

