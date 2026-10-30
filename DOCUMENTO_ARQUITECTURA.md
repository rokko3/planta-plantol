# Documento de Arquitectura de Software · Entrega 2
**Universidad Sergio Arboleda · Escuela de Ciencias Exactas e Ingeniería**  
**Asignatura:** Arquitectura de Software · 2026-3  
**Proyecto:** Matera Inteligente (Plantol) — Fase 2: Del sensor al dominio (Arquitectura Hexagonal)

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
                         |       |                             ^                 |
                         |       v (P1, P2)                    | (P3)            |
                         |  +---------------------------------------+            |
                         |  |        PUERTOS (Modelo/puertos.py)    |            |
                         |  | P1: RegistrarLecturaPort              |            |
                         |  | P2: ConsultarEstadoPort               |            |
                         |  | P3: TablaReferenciaPort               |            |
                         |  | P4: HistorialLecturasPort             |            |
                         |  | P5: RepositorioPlantasPort            |            |
                         |  | P6: EmisorTokenPort                   |            |
                         |  +---------------------------------------+            |
                         |       |                             ^                 |
                         |       v                             |                 |
                         |  +---------------------------------------+            |
                         |  |         DOMINIO (Modelo/negocio.py)   |            |
                         |  |   ValidadorDeEstado · Lectura         |            |
                         |  |   Planta · DiagnosticoPlanta          |            |
                         |  |   (Sin Flask, HTTP, SQL ni JSON)      |            |
                         |  +---------------------------------------+            |
                         |       ^                             |                 |
                         |       | (P1)                        v (P4, P5)        |
      [ ESP32 / Sim ]    |  [ Adaptador Entrada ]         [ Adaptador Salida ]   |  [ Base de Datos ]
     (simulador_esp32)  --> |  Controlador/api.py           persistencia.py ------>  (data/matera.db)
                         |       (Filtro JWT)             (SQLite & PyJWT)       |
                         +-------------------------------------------------------+
```

---

## 2. Tabla de Puertos y Adaptadores Reales

| Identificador | Componente en Código | Tipo | Ubicación | Rol y Tecnología Concreta |
| :--- | :--- | :--- | :--- | :--- |
| **P1** | `RegistrarLecturaPort` | Puerto Entrada | `Modelo/puertos.py` | Caso de uso para recibir telemetría ambiental, validar límites físicos, asociar la planta, diagnosticar salud vegetal y persistir. |
| **P2** | `ConsultarEstadoPort` | Puerto Entrada | `Modelo/puertos.py` | Caso de uso para consultar el dashboard, lista de plantas e historial, aplicando en el dominio la regla de propiedad. |
| **P3** | `TablaReferenciaPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para consultar rangos por especie. Implementado por `TablaReferenciaCSV` (`especies.csv`) y `TablaReferenciaBD` (SQLite). |
| **P4** | `HistorialLecturasPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para persistir y consultar telemetría histórica. Implementado por `HistorialLecturasBD` (SQLite). |
| **P5** | `RepositorioPlantasPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para almacenamiento y consulta de plantas y vínculos de sensores. Implementado por `RepositorioSQLite`. |
| **P6** | `EmisorTokenPort` | Puerto Salida | `Modelo/puertos.py` | Contrato para emisión y verificación criptográfica de tokens JWT. Implementado por `ServicioJWT`. |
| **Ad. In** | `Controlador/api.py` | Adaptador Entrada | `Controlador/` | Endpoints REST Flask para el navegador web (`/api/plantas`, `/api/dashboard`, `/api/diagnostico`) y ESP32 (`/api/dispositivos/<id>/lecturas`). Contiene los filtros/decoradores JWT. |
| **Ad. Out** | `TablaReferenciaCSV` | Adaptador Salida | `Controlador/persistencia.py` | Lee y cachea el archivo `especies.csv`. |
| **Ad. Out** | `TablaReferenciaBD` | Adaptador Salida | `Controlador/persistencia.py` | Consulta la tabla `especies_referencia` en SQLite. Intercambiable con CSV mediante `TABLA_REFERENCIA=bd`. |
| **Ad. Out** | `HistorialLecturasBD` | Adaptador Salida | `Controlador/persistencia.py` | Inserta y consulta registros en la tabla `historial_lecturas` de SQLite. |
| **Ad. Out** | `RepositorioSQLite` | Adaptador Salida | `Controlador/persistencia.py` | Persistencia en SQLite de cuentas de usuario, plantas, dispositivos y códigos temporales de vinculación. |
| **Ad. Out** | `ServicioJWT` | Adaptador Salida | `Controlador/persistencia.py` | Implementa `EmisorTokenPort` usando PyJWT para generar tokens con scopes (`usuario` vs `dispositivo`). |

---

## 3. Seguridad con JWT: Emisión y Verificación

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
     Si un usuario intenta solicitar una planta que no le pertenece, el dominio lanza `AccesoDenegadoPlantaError` y el adaptador responde con `HTTP 403 Forbidden` (`error: "ACCESO_DENEGADO"`).

---

## 4. Justificación de Principios SOLID en el Código

### 1. Inversión de Dependencias (DIP)
- **Definición:** Los módulos de alto nivel no deben depender de módulos de bajo nivel; ambos deben depender de abstracciones.
- **En nuestro código:** El caso de uso `CasoUsoRegistrarLectura` y la entidad `Planta` no importan ni conocen SQLite, CSV ni PyJWT. Dependen de las interfaces `TablaReferenciaPort`, `HistorialLecturasPort` y `RepositorioPlantasPort` definidas en `Modelo/puertos.py`. Los adaptadores en `Controlador/persistencia.py` implementan estas interfaces y son inyectados en tiempo de ejecución en `Controlador/app.py`.

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
