# Plantol — Sistema Inteligente de Monitoreo y Cuidado de Plantas IoT

**Plantol** es una aplicación web y plataforma IoT diseñada para monitorear en tiempo real las condiciones ambientales de plantas mediante dispositivos **ESP32-S3**, diagnosticar su estado de salud según rangos agronómicos por especie, traducir mediciones técnicas en recomendaciones claras y motivar el cuidado continuo mediante un sistema completo de **gamificación** (monedas, experiencia, niveles, misiones, logros, tienda, inventario y habitación virtual).

---

## 1. Problema que resuelve y objetivo
- **Problema:** Muchas personas no cuentan con conocimientos técnicos para interpretar variables como luminosidad (`lux`), temperatura (`°C`) o humedad del sustrato (`%`), ni para configurar manualmente microcontroladores IoT.
- **Objetivo:** Ofrecer una experiencia intuitiva y amigable donde cualquier usuario pueda conectar su matera por Bluetooth, ver explicaciones claras del estado de sus plantas y mantener hábitos positivos de cuidado mediante gamificación persistente en servidor, conservando una arquitectura **MVC + Arquitectura Hexagonal + SOLID** defendible académicamente.

---

## 2. Características principales
- **Monitoreo y diagnóstico vegetal:** Evaluación automática de luz, temperatura y humedad del suelo frente a tablas de referencia intercambiables (**CSV** o **SQLite**), con cálculo de salud (`HP` 0–100) y 6 estados emocionales (`RADIANTE`, `SEDIENTA`, `ACALORADA`, `CON FRÍO`, `DURMIENDO`, `EN PELIGRO`).
- **Aprovisionamiento Bluetooth BLE/GATT y Wi-Fi:** Emparejamiento desde Google Chrome / Microsoft Edge mediante Web Bluetooth sin editar código en la ESP32.
- **Autenticación y aislamiento por usuario (JWT):** Tokens separados por alcance (`scope: "usuario"` y `scope: "dispositivo"`), protección XSS en interfaz y validaciones estrictas en backend.
- **Gamificación completa en backend:**
  - Monedas de cuidado (`+1` saludo diario, `+2` cuidado continuo 60 min, `+3` rescate de humedad, `-2` descuido crítico prolongado, saldo nunca negativo).
  - Progresión independiente por **XP y Niveles** con bonificación por subida de nivel.
  - **Misiones diarias y progresivas** verificables por eventos reales.
  - **Logros permanentes** con fecha de desbloqueo.
  - **Tienda virtual** con **compras atómicas** e **inventario persistente**.
  - **Habitación virtual personalizable** que integra las plantas reales del usuario y su estado emocional en vivo.
- **Diseño responsive:** Pensado para escritorio (`1920×1080`, `1366×768`) y adaptado para tableta (`768 px`) y celulares (`430 px`, `390 px`, `360 px`).

---

## 3. Tecnologías utilizadas
- **Backend:** Python 3.11+, Flask, Flask-CORS, PyJWT, SQLite (`sqlite3`).
- **Frontend:** HTML5, CSS3, JavaScript (ES6+ Vanilla, Fetch API, Web Bluetooth API).
- **Hardware / Firmware:** ESP32-S3 (PlatformIO, Arduino-ESP32, NimBLE, HTTPClient, ArduinoJson).
- **Pruebas:** `unittest` (47 pruebas unitarias, de integración y seguridad).

---

## 4. Estructura del repositorio

```text
planta-plantol/
├── app.py                              # Punto de entrada del servidor Flask
├── especies.csv                        # Tabla de referencia agronómica (modo CSV)
├── requirements.txt                    # Dependencias de Python
├── simulador_esp32.py                  # Simulador CLI de telemetría ESP32
├── README.md                           # Guía de instalación, configuración y uso
├── DOCUMENTO_ARQUITECTURA.md           # Arquitectura real, flujos y diagramas
├── Modelo/                             # Núcleo de dominio puro (sin Flask ni SQLite)
│   ├── entidades.py                    # Entidades, constantes y excepciones de dominio
│   ├── puertos.py                      # Contratos abstractos (Protocol)
│   ├── negocio.py                      # Diagnóstico, cuidado, episodios y casos de uso base
│   └── gamificacion_avanzada.py        # XP, niveles, catálogo, misiones, logros y habitación
├── Controlador/                        # Adaptadores de entrada/salida y Composition Root
│   ├── app.py                          # Fábrica Flask e inyección de dependencias
│   ├── api.py                          # Blueprint REST (/api/*) y decoradores JWT
│   ├── persistencia.py                 # Adaptadores SQLite, CSV y ServicioJWT
│   └── persistencia_gamificacion.py    # Adaptador SQLite atómico de gamificación avanzada
├── Vista/                              # Interfaz web estática
│   ├── index.html                      # Estructura SPA por secciones y modales
│   ├── styles.css                      # Diseño botánico + reglas responsive
│   ├── app.js                          # Dashboard, auth, errores amigables, historial y BLE
│   └── gamificacion.js                 # Progresión, misiones, logros, tienda y habitación
├── firmware/Planta_Inteligente/        # Proyecto PlatformIO del ESP32-S3
├── data/                               # Base de datos SQLite (matera.db)
└── tests/                              # Suite de pruebas automatizadas
    ├── test_api.py
    ├── test_gamificacion.py
    └── test_modelo.py
```

---

## 5. Requisitos previos e instalación

### Requisitos
- Python 3.10 o superior (`pip`).
- Navegador **Google Chrome** o **Microsoft Edge** en escritorio (requerido para Web Bluetooth API).
- *(Opcional para hardware)* VS Code + PlatformIO y placa ESP32-S3.

### Instalación
```bash
git clone https://github.com/rokko3/planta-plantol.git
cd planta-plantol
pip install -r requirements.txt
```

---

## 6. Variables de entorno y configuración

| Variable | Valores posibles | Por defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `JWT_SECRET_KEY` | Cadena secreta (>= 32 chars) | Clave de desarrollo | Clave de firma JWT. **Definir obligatoriamente en despliegue.** |
| `TABLA_REFERENCIA` | `csv` \| `bd` | `csv` | Origen de rangos óptimos por especie. |
| `DB_PATH` | Ruta a archivo `.db` | `data/matera.db` | Ruta personalizada para la base SQLite. |
| `CSV_PATH` | Ruta a archivo `.csv` | `especies.csv` | Ruta personalizada del catálogo de especies CSV. |
| `PLANTOL_DEMO` | `0` \| `1` | `0` | Habilita datos iniciales y botón opcional **Entrar en Modo Demo** (`POST /api/auth/demo`). |
| `SERVER_HOST` | IP LAN del servidor | Detección automática | IP sugerida al ESP32 durante aprovisionamiento BLE. |
| `PORT` | Número de puerto | `5000` | Puerto reportado en `/api/servidor/info`. |

### Configuración de JWT y Modo Demo
- Por defecto, `PLANTOL_DEMO` está desactivado (`0`): la aplicación abre en **Cuenta y Acceso** sin iniciar sesión automáticamente ni exponer credenciales en el frontend.
- Para demostraciones académicas con datos precargados, inicia el servidor con:
  - **PowerShell (Windows):** `$env:PLANTOL_DEMO="1"; python app.py`
  - **Linux/macOS:** `PLANTOL_DEMO=1 python app.py`

---

## 7. Ejecución y acceso a la aplicación

1. **Iniciar el servidor Flask:**
   ```bash
   python app.py
   ```
2. **Abrir la web:**
   Ingresa a `http://127.0.0.1:5000` en **Google Chrome** o **Microsoft Edge** *(Web Bluetooth requiere `localhost`, `127.0.0.1` o `HTTPS`)*.
3. **Uso general:**
   - **Cuenta y Acceso:** Registra un usuario nuevo o inicia sesión (o usa **Entrar en Modo Demo** si `PLANTOL_DEMO=1`).
   - **Agregar Planta:** Registra el nombre, especie y ubicación de tu planta.
   - **Mis Plantas:** Observa el estado de salud (`HP`), emoción, guía de cuidado en lenguaje sencillo, lecturas e **Historial**.
   - **Tienda y Logros:** Consulta tu nivel/XP, misiones activas, logros desbloqueados y compra macetas o decoraciones.
   - **Habitación:** Personaliza tu espacio colocando objetos de tu inventario junto a tus plantas reales.

---

## 8. Conexión ESP32 y Simulador

### Con hardware real (ESP32-S3)
1. En **Conectar Matera (ESP32)** pulsa **Buscar Matera por Bluetooth** y elige **`Planta-Sensor-Config`**.
2. Ingresa el nombre y contraseña de tu red Wi-Fi **2.4 GHz** (el PC servidor y la ESP32 deben estar en la misma red) y pulsa **Conectar Matera al Wi-Fi**.
3. Al aparecer la MAC del ESP32 en **Asignar Sensor a tu Planta**, selecciona tu planta y pulsa **Vincular a Planta**.
4. Para resetear Wi-Fi/JWT en la ESP32, mantén presionado el botón físico **`BOOT` (GPIO 0)** durante **5 segundos** hasta ver `FACTORY RESET`.

### Sin hardware físico (Simulador CLI)
```bash
python simulador_esp32.py
```

---

## 9. Ejecución de pruebas automatizadas

```bash
python -m unittest discover tests -v
```
Ejecuta las pruebas unitarias del modelo (`test_modelo.py`), pruebas de integración HTTP/JWT/migración (`test_api.py`) y pruebas de gamificación, compras atómicas, persistencia y aislamiento entre usuarios (`test_gamificacion.py`).

---

## 10. Problemas comunes y limitaciones conocidas
- **No aparece la ESP32 en Bluetooth:** verifica usar Chrome o Edge en `http://127.0.0.1:5000` o `http://localhost:5000` y que el ESP32 no esté ya conectado a Wi-Fi (haz Factory Reset de 5s en `BOOT` si es necesario).
- **La ESP32 se conecta al Wi-Fi pero no llega al servidor:** algunos hotspots móviles aíslan clientes entre sí (AP Isolation) o el firewall de Windows bloquea el puerto `5000`. Usa una red Wi-Fi local estándar y permite el puerto `5000` TCP entrante.
- **Limitación de seguridad documentada en tokens de dispositivo:** `POST /api/dispositivos/<dispositivo_id>/token` sigue habilitado sin autenticación propia por compatibilidad con el firmware ya flasheado en el ESP32-S3. Aunque `POST /api/dispositivos/reclamar` ya devuelve el JWT directamente tras validar el token BLE de pairing, cerrar `POST /token` requiere una actualización coordinada futura del firmware.
- **Verificación visual responsive:** las reglas CSS para `768 px`, `430 px`, `390 px` y `360 px` requieren inspección visual final en Chrome/Edge DevTools según tu entorno local.
