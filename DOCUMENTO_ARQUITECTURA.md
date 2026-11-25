# Documento de Arquitectura de Software · Entrega 2 y Evolución IoT & Gamificación
**Universidad Sergio Arboleda · Escuela de Ciencias Exactas e Ingeniería**  
**Asignatura:** Arquitectura de Software · 2026-3  
**Proyecto:** Matera Inteligente (Plantol) — Evolución Integral: Hardware ESP32 Real, Web Bluetooth, Gamificación y Arquitectura Hexagonal

---

## 1. Visión General del Sistema y Diagrama Hexagonal

El sistema organiza sus responsabilidades alrededor de un **núcleo de dominio puro** y agnóstico de frameworks, tecnologías de persistencia y protocolos de red. La interacción con el exterior se estructura mediante **Puertos** (contratos abstractos en `Modelo/puertos.py`) y **Adaptadores** (tecnologías concretas en `Controlador/` y `Vista/`).

### Diagrama Hexagonal del Proyecto

```
                         +-------------------------------------------------------+
                         |                     ADAPTADORES                       |
                         |                                                       |
      [ Navegador Web ]  |  [ Adaptador Entrada ]         [ Adaptador Salida ]   |  [ Archivo CSV ]
      (Vista/app.js)  ----> |  Controlador/api.py           persistencia.py ------>  (especies.csv)
     (Web Bluetooth)     |       |                             ^                 |
                         |       v (P1, P2, P7)                | (P3)            |
                         |  +---------------------------------------+            |
                         |  |        PUERTOS (Modelo/puertos.py)    |            |
                         |  | P1: RegistrarLecturaPort              |            |
                         |  | P2: ConsultarEstadoPort               |            |
                         |  | P3: TablaReferenciaPort               |            |
                         |  | P4: HistorialLecturasPort             |            |
                         |  | P5: RepositorioPlantasPort            |            |
                         |  | P6: EmisorTokenPort                   |            |
                         |  | P7: GamificacionPort                  |            |
                         |  | P8: RepositorioGamificacionPort       |            |
                         |  +---------------------------------------+            |
                         |       |                             ^                 |
                         |       v                             |                 |
                         |  +---------------------------------------+            |
                         |  |         DOMINIO (Modelo/negocio.py)   |            |
                         |  |   ValidadorDeEstado · HP · Emociones  |            |
                         |  |   Gamificación · Puntos · Episodios   |            |
                         |  |   Planta · DiagnosticoPlanta          |            |
                         |  |   (Sin Flask, HTTP, SQLite ni JSON)   |            |
                         |  +---------------------------------------+            |
                         |       ^                             |                 |
                         |       | (P1)                        v (P4, P5, P8)    |
      [ ESP32 Real IoT ] |  [ Adaptador Entrada ]         [ Adaptador Salida ]   |  [ Base de Datos ]
     (Planta_Inteligente)-->|  Controlador/api.py           persistencia.py ------>  (data/matera.db)
     (BLE GATT + WiFi)   |       (Filtro JWT)             (SQLite & PyJWT)       |
                         +-------------------------------------------------------+
```

---

## 2. Tabla de Puertos y Adaptadores Reales

| Identificador | Componente en Código | Tipo | Ubicación | Rol y Tecnología Concreta |
| :--- | :--- | :--- | :--- | :--- |
| **P1** | `RegistrarLecturaPort` | Puerto Entrada | `Modelo/puertos.py` | Caso de uso para recibir telemetría ambiental (incluyendo humedad del suelo), validar límites físicos, asociar la planta, diagnosticar salud vegetal, evaluar episodios de gamificación y persistir. |
| **P2** | `ConsultarEstadoPort` | Puerto Entrada | `Modelo/puertos.py` | Caso de uso para consultar el dashboard, lista de plantas, HP biológico, estado emocional y saldo de puntos. |
| **P3** | `TablaReferenciaPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para consultar rangos por especie. Implementado por `TablaReferenciaCSV` (`especies.csv`) y `TablaReferenciaBD` (SQLite). |
| **P4** | `HistorialLecturasPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para persistir y consultar telemetría histórica con `humedad_suelo`. Implementado por `HistorialLecturasBD` (SQLite). |
| **P5** | `RepositorioPlantasPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para almacenamiento y consulta de plantas y vínculos de sensores. Implementado por `RepositorioSQLite`. |
| **P6** | `EmisorTokenPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para emisión y verificación criptográfica de tokens JWT. Implementado por `ServicioJWT`. |
| **P7** | `GamificacionPort` | Puerto Entrada | `Modelo/puertos.py` | Contrato de casos de uso para interacción de usuario: saludo diario, consulta de puntos y transacciones. |
| **P8** | `RepositorioGamificacionPort` | Puerto Salida | `Modelo/puertos.py` | Contrato de persistencia de saldo de puntos, transacciones, saludos diarios y episodios continuos. Implementado por `RepositorioGamificacionBD` (SQLite). |
| **Ad. In** | `Controlador/api.py` | Adaptador Entrada | `Controlador/` | Endpoints REST Flask para el navegador web (`/api/plantas`, `/api/dashboard`, `/api/gamificacion/*`) y ESP32 (`/api/dispositivos/<id>/lecturas`). Contiene los filtros/decoradores JWT. |
| **Ad. Out** | `TablaReferenciaCSV` | Adaptador Salida | `Controlador/persistencia.py` | Lee y cachea el archivo `especies.csv`. |
| **Ad. Out** | `TablaReferenciaBD` | Adaptador Salida | `Controlador/persistencia.py` | Consulta la tabla `especies_referencia` en SQLite. Intercambiable con CSV mediante `TABLA_REFERENCIA=bd`. |
| **Ad. Out** | `HistorialLecturasBD` | Adaptador Salida | `Controlador/persistencia.py` | Inserta y consulta registros en la tabla `historial_lecturas` de SQLite (incluyendo columna `humedad_suelo`). |
| **Ad. Out** | `RepositorioSQLite` | Adaptador Salida | `Controlador/persistencia.py` | Persistencia en SQLite de cuentas de usuario, plantas, dispositivos y códigos temporales de vinculación. |
| **Ad. Out** | `RepositorioGamificacionBD` | Adaptador Salida | `Controlador/persistencia.py` | Persistencia en SQLite de tablas `gamificacion_puntos`, `gamificacion_transacciones`, `gamificacion_saludos` y `gamificacion_episodios`. |
| **Ad. Out** | `ServicioJWT` | Adaptador Salida | `Controlador/persistencia.py` | Implementa `EmisorTokenPort` usando PyJWT para generar tokens con scopes (`usuario` vs `dispositivo`). |

---

## 3. Arquitectura del Firmware IoT Real (`Planta_Inteligente`)

El firmware base utilizado es el proyecto `Planta_Inteligente` configurado en PlatformIO para microcontroladores **ESP32-S3 DevKitC-1**:

### 3.1 Asignación de Pines Físicos
- **Sensor DHT11 (Temperatura y Humedad Ambiental):** GPIO 4.
- **Sensor Higrómetro Capacitivo/Resistivo de Suelo:** GPIO 5 (ADC 12 bits, lectura calibrada y mapeada de 0 a 100%).
- **Sensor de Luz BH1750 (I2C):** GPIO 8 (SDA), GPIO 9 (SCL), dirección I2C `0x23`.
- **LED Indicador de Estado:** GPIO 2 (Parpadeo durante BLE/WiFi, fijo al transmitir telemetría).
- **Botón BOOT / Reset de Fábrica:** GPIO 0 (Presionar > 5 segundos para borrar credenciales en NVS y reiniciar en modo aprovisionamiento BLE).

### 3.2 Aprovisionamiento BLE GATT
- **UUID de Servicio:** `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- **Característica de Configuración (Escritura):** `beb5483e-36e1-4688-b7f5-ea07361b26a8`
  - Recibe JSON con: `{"ssid": "...", "pass": "...", "token": "...", "host": "http://..."}`.
  - Almacena los parámetros en memoria no volátil (`Preferences`, espacio `"plantol"`).
- **Característica de Estado (Lectura / Notificación):** `beb5483e-36e1-4688-b7f5-ea07361b26a9`
  - Notifica estados: `"LISTO"`, `"CONFIGURADO"`, `"CONECTANDO_WIFI"`, `"CONECTADO"`, `"ERROR_WIFI"`.

### 3.3 Abstracción Modular para Pantalla OLED (Preparación Futura)
- En `include/PantallaOLED.h` se implementó una clase desacoplada `PantallaOLED` que abstrae el manejo de la pantalla.
- La pantalla permanece desactivada por defecto mediante la bandera `#define USAR_OLED 0`.
- No introduce librerías externas ni dependencias no instaladas. Para habilitarla en el futuro, basta con cambiar el flag a `1` y configurar los pines I2C correspondientes en la clase abstracta.

---

## 4. Web Bluetooth: Requisitos y Limitaciones Técnicas

Para aprovisionar la matera desde el navegador web mediante Web Bluetooth, deben cumplirse las siguientes condiciones:
1. **Navegador Compatible:** Google Chrome, Microsoft Edge u Opera en Windows, Linux, Android o macOS. (Firefox y Safari no soportan Web Bluetooth por políticas de seguridad de sus desarrolladores).
2. **Contexto Seguro (Secure Context):** El navegador exige acceder a través de `https://` o `localhost` / `127.0.0.1`.
3. **Gesto del Usuario (User Gesture):** La llamada `navigator.bluetooth.requestDevice` debe ser disparada por una acción explícita del usuario (clic en "Conectar Matera"), nunca automáticamente al cargar la página.
4. **Detección Automática de IP Local:** El frontend consulta `GET /api/servidor/info` para conocer la IP del servidor en la red de área local y enviarla al ESP32 a través de BLE, evitando hardcodear IPs o exigir al usuario ingresar configuraciones técnicas.

---

## 5. Sistema de Gamificación y Modelo Biológico

Todo el sistema de gamificación está implementado estrictamente en la capa **Modelo** (`Modelo/entidades.py` y `Modelo/negocio.py`):

### 5.1 Reglas de Puntos
- **Saldo no negativo:** El saldo de puntos de un usuario jamás desciende por debajo de 0.
- **Saludo Diario (+1 punto):** Se otorga 1 punto por saludar a la planta. Máximo 1 saludo por planta por día calendario (calculado con reloj UTC del servidor; reintentos el mismo día son rechazados idempotentemente).
- **Cuidado Continuo (+1 punto por hora):** Se otorga +1 punto por cada 1 hora continua (3600 segundos) de estabilidad saludable. Si la telemetría se interrumpe por más de 90 segundos, la ventana se reinicia para prevenir trampas.
- **Rescate de Humedad (+3 puntos):** Si la planta pasa de humedad baja a rango óptimo tras un riego, se bonifica al usuario con +3 puntos.
- **Penalización por Descuido (-2 puntos):** Si la planta permanece en estado crítico por más de 1 hora continua, se aplican -2 puntos (respetando saldo mínimo de 0).

### 5.2 Salud (HP) y Emociones
- **HP (0 - 100):** Se calcula a partir del diagnóstico biológico. 100 HP para estado óptimo/saludable; 50 HP para alerta en riesgo; 15 HP para estado crítico (10 HP si 3 o más parámetros están fuera de rango).
- **Jerarquía Estricta de Estados Emocionales:**
  1. Estado global `CRITICO` $\rightarrow$ `"EN PELIGRO"`
  2. Humedad baja (aire o suelo) $\rightarrow$ `"SEDIENTA"`
  3. Temperatura alta $\rightarrow$ `"ACALORADA"`
  4. Temperatura baja $\rightarrow$ `"CON FRÍO"`
  5. Luminosidad $< 50$ lux $\rightarrow$ `"DURMIENDO"`
  6. Condiciones óptimas $\rightarrow$ `"RADIANTE"`

---

## 6. Seguridad con JWT: Emisión y Verificación

La seguridad es una preocupación técnica de infraestructura y reside **fuera del dominio**:

1. **Dónde se emite el JWT:**
   - **Token de Usuario:** Se emite en el caso de uso `CasoUsoAutenticacion` apoyándose en el puerto de salida `EmisorTokenPort` cuando el usuario se registra (`POST /api/auth/register`) o inicia sesión (`POST /api/auth/login`). Payload: `{"sub": str(usuario_id), "scope": "usuario", "exp": 7 días}`.
   - **Token de Dispositivo:** Se emite en el endpoint `POST /api/dispositivos/<id>/token` mediante `EmisorTokenPort.emitir_token_dispositivo`. Payload: `{"sub": str(dispositivo_id), "scope": "dispositivo", "exp": 365 días}`.

2. **Dónde se verifica el JWT:**
   - La verificación ocurre en los **adaptadores de entrada** en `Controlador/api.py` mediante decoradores de Flask:
     - `@requiere_jwt_usuario`: extrae la cabecera `Authorization: Bearer <token>`, invoca `emisor_token.verificar_token(token)`, comprueba que `scope == "usuario"` y **entrega al caso de uso únicamente la identidad limpia (`usuario_id: int`)**. El caso de uso jamás toca tokens, firmas ni cabeceras HTTP.
     - `@requiere_jwt_dispositivo`: comprueba que `scope == "dispositivo"` y que el claim `sub` coincida exactamente con el `<dispositivo_id>` de la URL, evitando suplantación entre dispositivos.

3. **La regla de negocio en el dominio:**
   - Aunque la autenticación se ejecuta en la infraestructura, la regla de negocio **"un usuario solo ve y gestiona sus propias plantas"** vive 100% en el dominio:
     ```python
     # Modelo/negocio.py
     @staticmethod
     def verificar_propiedad_planta(planta: Planta, usuario_id: int) -> None:
         """Regla de negocio esencial de dominio: Un usuario solo accede a sus propias plantas."""
         if planta.usuario_id != usuario_id:
             raise AccesoDenegadoPlantaError(usuario_id=usuario_id, planta_id=planta.id)
     ```
     Si un usuario intenta solicitar o saludar una planta que no le pertenece, el dominio lanza `AccesoDenegadoPlantaError` y el adaptador responde con `HTTP 403 Forbidden` (`error: "ACCESO_DENEGADO"`).

---

## 7. Justificación de Principios SOLID en el Código

### 1. Inversión de Dependencias (DIP)
- **Definición:** Los módulos de alto nivel no deben depender de módulos de bajo nivel; ambos deben depender de abstracciones.
- **En nuestro código:** El caso de uso `CasoUsoRegistrarLectura` y la entidad `Planta` no importan ni conocen SQLite, CSV ni PyJWT. Dependen de las interfaces `TablaReferenciaPort`, `HistorialLecturasPort`, `RepositorioPlantasPort` y `RepositorioGamificacionPort` definidas en `Modelo/puertos.py`. Los adaptadores en `Controlador/persistencia.py` implementan estas interfaces y son inyectados en tiempo de ejecución en `Controlador/app.py`.

### 2. Responsabilidad Única (SRP)
- Cada módulo tiene un único motivo para cambiar: `Modelo/entidades.py` define estructuras y tipos, `Modelo/negocio.py` define lógica biológica y gamificación, `Controlador/api.py` maneja peticiones HTTP y JWT, y `Controlador/persistencia.py` se encarga de SQL y almacenamiento.

### 3. Abierto/Cerrado (OCP)
- Nuevas especies o fuentes de datos pueden agregarse implementando `TablaReferenciaPort` sin modificar las reglas de evaluación vegetal.

### 4. Segregación de Interfaces (ISP)
- Puertos específicos y bien delimitados (`HistorialLecturasPort`, `RepositorioPlantasPort`, `RepositorioGamificacionPort`, `EmisorTokenPort`) evitan que los clientes dependan de métodos que no utilizan.

### 5. Sustitución de Liskov (LSP)
- Cualquier implementación de `TablaReferenciaPort` (`TablaReferenciaCSV` o `TablaReferenciaBD`) o `RepositorioGamificacionPort` puede sustituirse de forma transparente sin alterar el comportamiento del sistema.


### 2. Principio Abierto/Cerrado (OCP)
- **Definición:** Las entidades de software deben estar abiertas a la extensión pero cerradas a la modificación.
- **En nuestro código:**
  - Cambiar el origen de datos de referencia de archivo CSV a SQLite se realizó creando una nueva clase `TablaReferenciaBD` que implementa `TablaReferenciaPort`, sin modificar una sola línea de `Modelo/negocio.py` ni de `Modelo/entidades.py`.
  - La selección se realiza en `Controlador/app.py` mediante la variable de entorno `TABLA_REFERENCIA`.

### 3. Segregación de Interfaces (ISP)
- **Definición:** Los clientes no deben estar forzados a depender de interfaces que no utilizan.
- **En nuestro código:** No existe una interfaz monolítica con decenas de métodos. Existen contratos pequeños, específicos y cohesivos:
  - `TablaReferenciaPort`: únicamente expone `obtener_rangos` y `listar_especies`.
  - `HistorialLecturasPort`: únicamente expone `guardar_lectura`, `obtener_ultima_lectura` y `obtener_historial`.
  - `EmisorTokenPort`: únicamente expone emisión y validación técnica de tokens.

### 4. Responsabilidad Única (SRP)
- **Definición:** Cada módulo o clase debe tener un único motivo de cambio.
- **En nuestro código:**
  - `ValidadorDeEstado` (`Modelo/negocio.py`): solo conoce las reglas biológicas de clasificación (BAJO/OPTIMO/ALTO) y cálculo de salud vegetal.
  - `Controlador/api.py`: solo traduce solicitudes HTTP y cabeceras JWT a llamadas de dominio.
  - `HistorialLecturasBD` (`Controlador/persistencia.py`): solo gestiona la persistencia SQL en la tabla `historial_lecturas`.

---

## 5. Pruebas de Cambio y Preguntas de Sustentación

### A. Prueba de Cambio: Inclusión de Dispositivos sin Modificar el Dominio
- Los archivos en `Modelo/` (`entidades.py`, `puertos.py`, `negocio.py`) definen el modelo conceptual y las reglas de negocio.
- Cuando se construyó el endpoint para dispositivos en `Controlador/api.py` y el simulador `simulador_esp32.py`, **ningún archivo de `Modelo/` requirió modificaciones**.
- Esto demuestra que la lógica de negocio es totalmente independiente del canal de adquisición.

### B. Pregunta de Cambio: "¿Qué cambiaría si las lecturas llegaran por MQTT en lugar de HTTP?"
- **Respuesta exacta:**
  1. **Archivos que NO se tocan:** Absolutamente ningún archivo de `Modelo/` (`entidades.py`, `puertos.py`, `negocio.py`). El caso de uso `CasoUsoRegistrarLectura` y sus reglas de negocio permanecen idénticos. Tampoco se modifican los adaptadores de salida (`persistencia.py`).
  2. **Archivos que se crean/modifican:**
     - Se crea un nuevo adaptador de entrada: `Controlador/mqtt_adapter.py` (usando una biblioteca como `paho-mqtt`).
     - Este adaptador se suscribe al tópico de telemetría (ej. `plantol/dispositivos/+/lecturas`), parsea el payload JSON entrante, valida las credenciales del dispositivo y ejecuta directamente el puerto existente:
       ```python
       caso_registrar_lectura.registrar(dispositivo_id, timestamp, lux, humedad, temp)
       ```
     - En el punto de composición (`Controlador/app.py`), se inicia el cliente del broker MQTT en un hilo de soporte durante el arranque de la aplicación.

### C. Pregunta de Cambio: "¿Qué cambiaría si se sustituye SQLite por PostgreSQL?"
- **Respuesta exacta:**
  1. El dominio (`Modelo/`) no experimenta ningún cambio, pues solo interactúa con los puertos `RepositorioPlantasPort` e `HistorialLecturasPort`.
  2. En `Controlador/persistencia.py`, se implementa una nueva clase adaptadora (ej. `RepositorioPostgres` e `HistorialLecturasPostgres`) usando `psycopg2` o SQLAlchemy.
  3. En `Controlador/app.py`, se instancian los nuevos adaptadores pasándoles el connection string de PostgreSQL.

---

## 6. Ejecución y Comprobación de Requisitos

1. **Instalación de Dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Pruebas Unitarias del Dominio (Aisladas sin servidor ni BD, con dobles de prueba):**
   ```bash
   python -m unittest tests/test_modelo.py
   ```
3. **Pruebas de Integración de Endpoints y Seguridad:**
   ```bash
   python -m unittest tests/test_api.py
   ```
4. **Ejecutar Toda la Suite de Pruebas (23 pruebas automáticas):**
   ```bash
   python -m unittest discover tests
   ```
5. **Ejecutar el Servidor Web:**
   ```bash
   python app.py
   ```
6. **Ejecutar el Simulador ESP32:**
   ```bash
   # Envío normal
   python simulador_esp32.py --intervalo 3

   # Alertas ambientales fuera de rango
   python simulador_esp32.py --modo fuera_rango

   # Verificación de robustez ante datos inválidos (HTTP 400)
   python simulador_esp32.py --modo invalido --conteo 4
   ```
