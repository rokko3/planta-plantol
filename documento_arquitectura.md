# Documento de Arquitectura de Software — Planta-Plantol

**Asignatura:** Arquitectura de Software  
**Integrantes:** [Escribe aquí los nombres completos y códigos de los integrantes del equipo]  
**Fecha de entrega:** [Escribe aquí la fecha de entrega]  
**Repositorio:** [URL del repositorio de GitHub]  

---

## 1. Diagrama de Paquetes y Organización de Módulos

[INSTRUCCIÓN PARA EL ESTUDIANTE: Inserta aquí la imagen o diagrama Mermaid de paquetes que represente 1:1 la estructura física del repositorio:
 - Paquete Controlador (app.py, dtos.py, controlador.js)
 - Paquete Modelo (entidades.py, puertos.py, clasificador.py, agregador.py, evaluar_planta.py, repositorio_csv.py, especies.csv)
 - Paquete Vista (index.html, styles.css)
 - Paquete tests (test_dominio.py)
Asegúrate de mostrar las flechas de dependencia: Controlador depende de Modelo; infraestructura y aplicación dependen de las interfaces del dominio; el dominio no tiene dependencias salientes hacia frameworks ni infraestructura.]

---

## 2. Diagrama de Secuencia

[INSTRUCCIÓN PARA EL ESTUDIANTE: Inserta aquí el diagrama de secuencia UML (o código Mermaid) que ilustre el flujo de una petición de diagnóstico:
 1. Usuario hace clic en "Diagnosticar" en Vista/index.html.
 2. Controlador/controlador.js intercepta el submit, extrae los datos y ejecuta fetch() a /api/diagnostico.
 3. Controlador/app.py recibe la petición HTTP y llama a Controlador/dtos.py (parsear_solicitud).
 4. Controlador/app.py instancia SolicitudDiagnostico y ejecuta Modelo/evaluar_planta.py (EvaluarPlanta.ejecutar).
 5. EvaluarPlanta consulta Modelo/puertos.py (IRepositorioEspecies), resuelto por Modelo/repositorio_csv.py.
 6. EvaluarPlanta invoca a Modelo/clasificador.py (ClasificadorParametro) y luego a Modelo/agregador.py (AgregarEstado).
 7. El resultado DiagnosticoPlanta regresa a app.py, que lo serializa a JSON y responde HTTP 200.
 8. controlador.js recibe el JSON y actualiza el DOM de la Vista sin recargar la página.]

---

## 3. Tabla de Responsabilidades por Capa

| Capa | Módulos / Archivos | Responsabilidad Concreta | Justificación de Aislamiento |
|---|---|---|---|
| **Presentación** | `Controlador/app.py`, `Controlador/dtos.py`, `Vista/index.html`, `Controlador/controlador.js` | [Escribe aquí la descripción de la captura de inputs, validación sintáctica/física y retorno de JSON/renderizado DOM] | [Explica por qué esta capa no debe contener lógica de negocio ni cálculo de rangos] |
| **Aplicación** | `Modelo/evaluar_planta.py` | [Escribe aquí cómo orquesta el caso de uso EvaluarPlanta, interactuando con el puerto del repositorio y servicios de dominio] | [Explica por qué coordina servicios sin conocer detalles de transporte HTTP ni almacenamiento en disco] |
| **Dominio** | `Modelo/entidades.py`, `Modelo/puertos.py`, `Modelo/clasificador.py`, `Modelo/agregador.py` | [Escribe aquí las reglas de negocio puras: clasificación individual, rangos, recomendaciones y agregación de estado global] | [Explica por qué debe ser 100% independiente de frameworks, BD o librerías externas] |
| **Infraestructura** | `Modelo/repositorio_csv.py`, `Modelo/especies.csv` | [Escribe aquí el mecanismo concreto de persistencia, lectura y mapeo del CSV a entidades de dominio] | [Explica cómo implementa el puerto definido por el dominio mediante inversión de dependencias] |

---

## 4. Justificación de Principios SOLID

### Single Responsibility Principle (SRP)
[INSTRUCCIÓN: Cita las clases/funciones que evidencian SRP, sus responsabilidades únicas y las referencias exactas de archivo y línea:
 - Separación entre clasificador individual (Modelo/clasificador.py:58-90), agregador de estado global (Modelo/agregador.py:28-48), acceso a datos (Modelo/repositorio_csv.py:18-70) y controlador HTTP (Controlador/app.py:43-95).]

### Open/Closed Principle (OCP)
[INSTRUCCIÓN: Explica cómo el clasificador (Modelo/clasificador.py:29-55, 91-111) está abierto a la extensión y cerrado a la modificación mediante la lista PARAMETROS_EVALUABLES, permitiendo agregar nuevos parámetros sin modificar la lógica evaluadora.]

### Liskov Substitution Principle (LSP)
[INSTRUCCIÓN: Demuestra cómo cualquier implementación de IRepositorioEspecies (como FakeRepositorio en tests/test_dominio.py:45-58 o un futuro RepositorioPostgreSQL) puede sustituir a RepositorioEspeciesCSV sin alterar el caso de uso EvaluarPlanta.]

### Interface Segregation Principle (ISP)
[INSTRUCCIÓN: Justifica por qué el puerto IRepositorioEspecies (Modelo/puertos.py:14-27) define únicamente los dos métodos requeridos por el dominio (obtener_rangos y listar_especies), evitando interfaces gigantes o métodos innecesarios.]

### Dependency Inversion Principle (DIP)
[INSTRUCCIÓN: Explica cómo el caso de uso EvaluarPlanta (Modelo/evaluar_planta.py:38) depende de la abstracción IRepositorioEspecies y no de la clase concreta RepositorioEspeciesCSV, realizándose la inyección de dependencias en Controlador/app.py:35-36.]

---

## 5. Plan de Evolución para los 4 Escenarios de Negocio

### Escenario 1: Integración de Sensores IoT vía MQTT
[INSTRUCCIÓN PARA EL ESTUDIANTE: Explica qué componentes se agregarían o modificarían. 
 Pista: Se crea un adaptador de entrada en Controlador/ (ej. `mqtt_listener.py`) que suscribe al broker MQTT, transforma los mensajes entrantes en `SolicitudDiagnostico` y llama a `EvaluarPlanta`. ¡El dominio y el caso de uso no se modifican!]

### Escenario 2: Persistencia en Base de Datos Relacional (PostgreSQL / MySQL)
[INSTRUCCIÓN PARA EL ESTUDIANTE: Explica qué componentes se modificarían.
 Pista: Se crea `Modelo/repositorio_sql.py` que implementa `IRepositorioEspecies`. En `Controlador/app.py` se inyecta la nueva instancia en vez de `RepositorioEspeciesCSV`. El dominio ni se entera.]

### Escenario 3: Autenticación de Usuarios y Múltiples Plantas por Usuario
[INSTRUCCIÓN PARA EL ESTUDIANTE: Explica cómo evolucionaría el modelo.
 Pista: Nuevas entidades en dominio (`Usuario`, `PlantaUsuario`), nuevos casos de uso en aplicación (`RegistrarPlanta`, `ConsultarHistorialPlanta`), y middleware/decorador de autenticación JWT en Controlador.]

### Escenario 4: Gamificación y Sistema de Alertas Push
[INSTRUCCIÓN PARA EL ESTUDIANTE: Explica la arquitectura de eventos.
 Pista: Publicación de eventos de dominio (`DiagnosticoGenerado`), un despachador de eventos que calcula puntos/insignias de cuidado de la planta y emite notificaciones móviles/webhooks.]

---

## 6. Decisiones de Diseño y Alternativas Descartadas

### Decisión 1: Clasificación determinista por rangos vs. Clasificación por Machine Learning (KNN)
* **Decisión adoptada:** Reglas deterministas con rangos botánicos óptimos por especie.
* **Alternativa descartada:** Modelo de ML supervisado (KNN con dataset synthetic).
* **Justificación:** [Escribe aquí por qué un clasificador de ML era inapropiado para este problema: falta de explicabilidad en recomendaciones, necesidad de rangos agronómicos exactos, overhead innecesario de dependencias como scikit-learn/pandas].

### Decisión 2: Frontend estático desacoplado (CORS/Fetch) vs. Monolito con plantillas server-side (Jinja2)
* **Decisión adoptada:** Frontend HTML/JS completamente desacoplado servido en origen independiente.
* **Alternativa descartada:** Renderizado server-side con Flask (`render_template`).
* **Justificación:** [Escribe aquí las razones de mantenibilidad, cumplimiento de RA1/RA2, independencia de despliegue y preparación para clientes móviles].
