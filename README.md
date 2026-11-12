# Plantol — Sistema de Monitoreo y Diagnóstico de Plantas

Plantol es una aplicación integral diseñada para supervisar las condiciones ambientales de diversas especies vegetales, diagnosticar su estado de salud en tiempo real a partir de mediciones físicas (luminosidad, humedad del sustrato y temperatura) y recibir telemetría de dispositivos de hardware ESP32 o simuladores IoT.

El sistema está estructurado bajo una **Arquitectura Hexagonal (Puertos y Adaptadores)** pura y organizada formalmente en las capas **Modelo**, **Vista** y **Controlador**, garantizando que el núcleo de dominio vegetal permanezca 100 % desacoplado de dependencias externas como Flask, SQLite, CSV, HTTP y tokens JWT.

---

## 1. Funcionalidades Principales

El proyecto integra de manera nativa los siguientes servicios y capacidades:

- **Gestión y eliminación completa de plantas:** Registro, monitoreo continuo de condiciones ambientales, desvinculación de sensores y eliminación definitiva en base de datos (con purga de historial y liberación inmediata del microcontrolador ESP32 a la red local).
- **Recepción de lecturas de sensores:** Endpoint HTTP seguro para registrar telemetría enviada periódicamente por microcontroladores ESP32 con estampa de tiempo precisa.
- **Simulación de ESP32:** Simulador autónomo de hardware IoT por línea de comandos que envía telemetría cruda a un puerto, sin reglas de negocio (la evaluación de salud vegetal reside 100 % en el Modelo).
- **Consulta de historial:** Registro persistente de lecturas en SQLite con visualización temporal de mediciones y estados históricos por planta.
- **Autenticación y autorización (JWT):** Control de acceso robusto mediante tokens criptográficos con alcances (*scopes*) estrictamente delimitados para usuarios (`scope: "usuario"`) y dispositivos (`scope: "dispositivo"`).
- **Aprovisionamiento Bluetooth BLE/GATT y vinculación en red:** El usuario escanea dispositivos ESP32 a su alrededor, envía las credenciales de la red mediante una característica GATT y, una vez el ESP32 está conectado a la red local, lo asocia a su planta directamente sin requerir ingresar tokens ni códigos manuales.
- **Fuentes de referencia intercambiables:** Posibilidad de alternar el origen de los rangos óptimos de las especies entre un archivo CSV y una base de datos relacional SQLite mediante una simple variable de configuración, sin tocar el código de negocio.
- **Actualización automática de la interfaz:** Panel web interactivo con actualización asíncrona periódica (cada 3.5 segundos) que refleja cambios en vivo sin recargar la página.

---

## 2. Estructura del Proyecto

El proyecto organiza sus responsabilidades de forma modular, manteniendo una separación estricta entre dominio, adaptadores e interfaz:

```
planta-plantol/
├── Controlador/                    # Adaptadores de entrada, salida y Composition Root
│   ├── api.py                      # Adaptador de entrada: Endpoints REST Flask y decoradores JWT
│   ├── app.py                      # Composition Root: Fábrica Flask e inyección de dependencias
│   └── persistencia.py             # Adaptadores de salida: SQLite, CSV y servicio PyJWT
├── Modelo/                         # Núcleo de Dominio puro (independiente de tecnología)
│   ├── entidades.py                # Clases de dominio, tipos de datos, excepciones y constantes
│   ├── negocio.py                  # Reglas de negocio, evaluación de salud y casos de uso
│   └── puertos.py                  # Interfaces abstractas (Puertos de entrada y salida)
├── Vista/                          # Frontend web asíncrono
│   ├── app.js                      # Lógica JavaScript asíncrona, polling y consumo de API
│   ├── index.html                  # Interfaz semántica estructurada y accesible
│   └── styles.css                  # Sistema de diseño botánico profesional y responsivo
├── data/                           # Directorio gestionado para persistencia relacional
│   └── matera.db                   # Base de datos SQLite (creada y migrada automáticamente)
├── tests/                          # Suite completa de pruebas automatizadas
│   ├── test_api.py                 # Pruebas de integración de la API HTTP y seguridad
│   └── test_modelo.py              # Pruebas unitarias puras del dominio con dobles de prueba
├── DOCUMENTO_ARQUITECTURA.md       # Especificación arquitectónica técnica y justificación SOLID
├── README.md                       # Documentación principal de instalación y uso
├── app.py                          # Punto de entrada directo en la raíz para iniciar el servidor
├── especies.csv                    # Tabla de referencia ambiental en formato CSV
├── requirements.txt                # Dependencias externas de Python
└── simulador_esp32.py              # Script independiente para emular hardware ESP32
```

### Guía de Orientación para el Desarrollador

Si deseas inspeccionar o modificar un componente específico del sistema, consulta los siguientes archivos:

- **Una regla de negocio o cálculo de salud vegetal:** Dirígete a `Modelo/negocio.py` (`ValidadorDeEstado` y casos de uso del dominio).
- **Un endpoint HTTP o validación de solicitudes:** Consulta `Controlador/api.py` (rutas Flask y decoradores de autenticación).
- **Una consulta SQL, tabla relacional o lectura de archivos:** Revisa `Controlador/persistencia.py` (adaptadores `RepositorioSQLite`, `HistorialLecturasBD`, `TablaReferenciaCSV`).
- **Un elemento visual, formulario o estructura HTML:** Modifica `Vista/index.html` y sus estilos correspondientes en `Vista/styles.css`.
- **El comportamiento de la interfaz o sincronización en vivo:** Revisa `Vista/app.js` (`sincronizarDashboard`, `iniciarPollingAsincrono`, `apiFetch`).
- **El simulador de hardware IoT:** Edita `simulador_esp32.py` (perfiles de planta, generación de valores y envío HTTP).

---

## 3. Justificación de la Arquitectura Hexagonal

La Arquitectura Hexagonal (también conocida como patrón de *Puertos y Adaptadores*, propuesta por Alistair Cockburn) aísla el valor comercial del software frente a las tecnologías y herramientas externas que cambian con frecuencia.

En Plantol, el código refleja directamente estos conceptos:

| Concepto Arquitectónico | Aplicación Concreta en Plantol | Ubicación en el Código |
| :--- | :--- | :--- |
| **Dominio Puro** | Entidades (`Planta`, `Lectura`, `Diagnostico`), reglas de salud y casos de uso. No importa Flask, SQLite ni PyJWT. | `Modelo/entidades.py`<br>`Modelo/negocio.py` |
| **Puertos de Entrada** | Contratos que especifican qué casos de uso ofrece el sistema (`RegistrarLecturaPort`, `ConsultarEstadoPort`). | `Modelo/puertos.py` |
| **Puertos de Salida** | Contratos abstractos de infraestructura requeridos por el dominio (`TablaReferenciaPort`, `HistorialLecturasPort`, `RepositorioPlantasPort`, `EmisorTokenPort`). | `Modelo/puertos.py` |
| **Adaptadores de Entrada** | Reciben peticiones HTTP desde el navegador o el ESP32, validan tipos y tokens, y delegan la ejecución a los puertos de entrada. | `Controlador/api.py` |
| **Adaptadores de Salida** | Implementaciones técnicas concretas para interactuar con SQLite (`RepositorioSQLite`), CSV (`TablaReferenciaCSV`) y firmas criptográficas (`ServicioJWT`). | `Controlador/persistencia.py` |
| **Inyección de Dependencias** | Ensamblador o *Composition Root* que instancia los adaptadores y los inyecta en los casos de uso según la configuración. | `Controlador/app.py` |
| **Capa de Presentación** | Interfaz de usuario desacoplada que consume la API REST de manera asíncrona mediante JSON. | `Vista/index.html`<br>`Vista/app.js` |

### Independencia del Dominio con Respecto a la Infraestructura

El núcleo del modelo nunca interactúa directamente con bases de datos ni protocolos de transporte:
1. `ValidadorDeEstado` recibe valores numéricos flotantes puros y un objeto de rangos de especie; no sabe si los datos provienen de un sensor físico, un simulador o un formulario web.
2. La regla fundamental de seguridad **"un usuario solo puede acceder a sus propias plantas"** se evalúa dentro de la entidad `Planta` y el caso de uso `verificar_propiedad_planta(planta, usuario_id)`. El dominio recibe únicamente identificadores enteros limpios, abstrayendo si la identidad se verificó mediante JWT, sesiones de cookies o certificados.
3. El puerto `TablaReferenciaPort` permite que el caso de uso invoque `obtener_rangos(especie)` de forma polimórfica: la aplicación puede leer desde `especies.csv` o desde la tabla SQLite sin alterar una sola línea de lógica interna.

---

## 4. Trazabilidad de Requisitos Obligatorios

| Requisito | Descripción del Requisito | Cómo se Cumple en Plantol | Ubicación y Archivos |
| :---: | :--- | :--- | :--- |
| **R1** | Diagnóstico ambiental y gestión del ciclo de vida | El modelo evalúa automáticamente luminosidad, humedad y temperatura según los rangos de la especie, permitiendo crear, consultar, desvincular sensores y eliminar plantas permanentemente de la base de datos (liberando el ESP32 en red). | Endpoints `POST /api/plantas`, `DELETE /api/plantas/<id>`<br>`Modelo/negocio.py`<br>`Vista/app.js` |
| **R2** | Recepción de telemetría ESP32 | Endpoint protegido por token de dispositivo que procesa mediciones, valida rangos físicos, asocia la planta vinculada, diagnostica y guarda fecha/hora en BD. | Endpoint `POST /api/dispositivos/<id>/lecturas`<br>`Controlador/api.py`<br>`Modelo/negocio.py` |
| **R3** | Simulador ESP32 autónomo | Script CLI configurable (`--intervalo`, `--dispositivo`, `--modo`) capaz de simular telemetría normal, fuera de rango o corrupta para probar resiliencia. | `simulador_esp32.py` |
| **R4** | Fuentes de referencia intercambiables | Selección entre `TablaReferenciaCSV` (`especies.csv`) y `TablaReferenciaBD` (SQLite) mediante variable de entorno sin alterar el dominio. | Variable `TABLA_REFERENCIA`<br>`Controlador/app.py`<br>`Controlador/persistencia.py` |
| **R5** | Historial de lecturas persistente | Almacenamiento cronológico de lecturas en SQLite con capacidad de consulta de la última lectura y del historial completo por planta. | Endpoint `GET /api/plantas/<id>/historial`<br>`Controlador/persistencia.py` (`HistorialLecturasBD`) |
| **R6** | Actualización asíncrona de la vista | El frontend realiza polling periódico asíncrono (cada 3.5s) consultando `/api/dashboard` y actualizando tarjetas y métricas sin recargar el navegador. | `Vista/app.js` (`iniciarPollingAsincrono`)<br>`Vista/index.html` |
| **R7** | Autenticación y autorización por JWT | Tokens con *scopes* separados (`usuario` vs `dispositivo`). Protección contra suplantación de identidad y aislamiento estricto de plantas por propietario. | `Controlador/api.py` (decoradores)<br>`Modelo/negocio.py` (`AccesoDenegadoPlantaError`) |

---

## 5. Persistencia y Base de Datos

### Ubicación y Gestión del Archivo de Base de Datos
- **Ruta unificada:** La base de datos SQLite se almacena en `data/matera.db`.
- **Resolución robusta de rutas:** La ruta se calcula en `Controlador/app.py` utilizando la ubicación absoluta del directorio del proyecto (`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`), evitando que la base de datos se cree en carpetas erróneas según el directorio de trabajo desde el que se lance el comando.
- **Creación y migración automática:** Al arrancar el servidor, si el directorio `data/` no existe, se crea automáticamente (`os.makedirs`). Si existía un archivo `matera.db` previo en la raíz del proyecto, el sistema lo traslada de forma segura al directorio `data/` sin pérdida de datos.

### Esquema y Almacenamiento
La base de datos contiene las siguientes tablas relacionales:
1. `usuarios`: Cuentas de usuario registradas con contraseñas cifradas con hash SHA-256 y sal criptográfica.
2. `plantas`: Plantas registradas con su especie, ubicación y relación con el usuario propietario.
3. `dispositivos`: Registro de dispositivos ESP32, estado de vinculación y asociación a plantas.
4. `codigos_vinculacion`: Códigos de vinculación temporales de un solo uso para asociar hardware y plantas.
5. `historial_lecturas`: Registro histórico continuo de cada lectura ambiental recibida con su marca temporal.
6. `especies_referencia`: Tabla relacional con los rangos óptimos de luminosidad, humedad y temperatura para cada especie (utilizada cuando `TABLA_REFERENCIA=bd`).

### Diferencia entre Historial de Lecturas y Tabla de Referencia
- **Historial de lecturas (`historial_lecturas`):** Almacena datos dinámicos generados en el tiempo por los sensores ESP32 (telemetría mutable y acumulativa).
- **Tabla de referencia de especies (`especies.csv` o `especies_referencia`):** Contiene parámetros agronómicos estáticos de calibración (rangos mínimos y máximos para cada variable ambiental).

---

## 6. Instalación y Ejecución en Windows

### Requisitos Previos
- Python 3.10 o superior instalado en el sistema.
- Terminal de PowerShell o Símbolo del sistema (CMD).

### Paso a Paso para la Instalación

1. **Abrir la terminal e ingresar a la carpeta del proyecto:**
   ```powershell
   cd c:\Users\moral\.gemini\antigravity-ide\scratch\planta-plantol
   ```

2. **Crear y activar un entorno virtual:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   *(Si utilizas CMD, activa con: `.\.venv\Scripts\activate.bat`)*

3. **Instalar dependencias requeridas:**
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. **Ejecutar la aplicación web:**
   Puedes iniciar el servidor desde la raíz utilizando cualquiera de estos dos comandos equivalentes:
   ```powershell
   python app.py
   ```
   o directamente desde el módulo controlador:
   ```powershell
   python Controlador/app.py
   ```

5. **Acceder a la interfaz:**
   Abre tu navegador web e ingresa a:
   ```
   http://127.0.0.1:5000
   ```

---

## 7. Configuración de la Fuente de Referencia (CSV / SQLite)

La aplicación permite seleccionar el origen de datos de referencia mediante la variable de entorno `TABLA_REFERENCIA`:

### Ejecución en PowerShell:

- **Modo CSV (predeterminado):**
  ```powershell
  $env:TABLA_REFERENCIA="csv"
  python app.py
  ```

- **Modo Base de Datos (SQLite):**
  ```powershell
  $env:TABLA_REFERENCIA="bd"
  python app.py
  ```

### Ejecución en CMD:

- **Modo CSV:**
  ```cmd
  set TABLA_REFERENCIA=csv && python app.py
  ```

- **Modo Base de Datos:**
  ```cmd
  set TABLA_REFERENCIA=bd && python app.py
  ```

*Nota:* Al cambiar esta configuración, el panel lateral de la interfaz web mostrará automáticamente el indicador correspondiente (**Fuente: CSV** o **Fuente: BD**) confirmando la selección sin alterar la lógica de negocio.

---

## 8. Ejecución del Simulador ESP32

El simulador emula el comportamiento de un sensor físico transmitiendo telemetría periódica a la API. Siguiendo las buenas prácticas MVC, el simulador **no tiene ninguna regla de negocio** ni evalúa la salud de las plantas; únicamente transmite señales ambientales crudas al puerto HTTP:

1. **Simulación básica con envío cada 3 segundos:**
   ```powershell
   python simulador_esp32.py --intervalo 3
   ```

2. **Simular fluctuaciones ambientales variables:**
   ```powershell
   python simulador_esp32.py --dispositivo ESP32-A7F9 --modo variable --intervalo 2
   ```

3. **Simular envío de señales corruptas para verificar validaciones de hardware (HTTP 400):**
   ```powershell
   python simulador_esp32.py --dispositivo ESP32-A7F9 --modo invalido --conteo 5
   ```

---

## 9. Pruebas Automatizadas

El proyecto incluye 23 pruebas automatizadas organizadas en pruebas unitarias del modelo y pruebas de integración de la API.

### Comando de Ejecución
Ejecuta la suite completa desde la raíz del proyecto:
```powershell
python -m unittest discover tests
```

Para ver la ejecución detallada de cada prueba:
```powershell
python -m unittest -v tests/test_modelo.py tests/test_api.py
```

### Cobertura de las Pruebas
- **Pruebas unitarias (`tests/test_modelo.py` - 15 pruebas):**
  - Validación de límites físicos de sensores (valores negativos, extremos imposibles).
  - Algoritmo de clasificación de salud vegetal (`SALUDABLE`, `ADVERTENCIA`, `CRITICO`).
  - Dobles de prueba (*stubs/mocks*) para puertos de salida, verificando el dominio sin conexión a disco ni base de datos.
  - Regla de dominio de pertenencia y control de acceso entre usuarios.
- **Pruebas de integración (`tests/test_api.py` - 8 pruebas):**
  - Ciclo de vida completo de endpoints HTTP REST usando el cliente de pruebas de Flask.
  - Emisión y validación de tokens JWT y rechazo de tokens expirados o adulterados.
  - Verificación de separación estricta de *scopes* (`usuario` vs `dispositivo`).
  - Rechazo de lecturas no autorizadas y respuestas HTTP 403 Forbidden ante intentos de acceso cruzado entre usuarios.

---

## 10. Credenciales de Demostración Local

Para fines de demostración académica y pruebas funcionales en entorno local, la base de datos se inicializa con los siguientes usuarios de prueba:

| Usuario | Contraseña | Rol / Propósito |
| :--- | :--- | :--- |
| `felipe` | `plantol123` | Propietario de plantas demo (Cactus, Helecho) |
| `carlos` | `plantol123` | Usuario secundario para comprobar aislamiento de plantas (R7) |

> **Nota de Seguridad:** Estas credenciales son de uso exclusivo en entornos de prueba y desarrollo local. En implementaciones de producción deben sustituirse por mecanismos de gestión de identidades seguras y almacenamiento de secretos en variables de entorno.
