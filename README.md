# planta-plantol

Sistema de diagnóstico del estado de salud de plantas a partir de parámetros ambientales.  
Proyecto para el curso de **Arquitectura de Software**.

---

## Estructura del proyecto

El proyecto está organizado en **exactamente 3 carpetas de código** a nivel raíz, preservando la separación de capas a nivel de módulos:

```
planta-plantol/
├── Controlador/
│   ├── app.py              # Rutas Flask — responde EXCLUSIVAMENTE JSON (RA1)
│   ├── dtos.py             # DTOs y validación estricta de entrada con errores estructurados (RA6, RF6)
│   └── controlador.js      # Controlador cliente (JS) — maneja eventos, fetch asíncrono y DOM (RA2)
├── Modelo/
│   ├── entidades.py        # Capa: dominio — entidades y value objects (RangosEspecie, DiagnosticoPlanta)
│   ├── puertos.py          # Capa: dominio — interfaz/puerto IRepositorioEspecies (RA5, DIP)
│   ├── clasificador.py     # Capa: dominio — clasificación por rangos y recomendaciones (RF2, RF4, OCP)
│   ├── agregador.py        # Capa: dominio — regla determinista de agregación global (RF3, SRP)
│   ├── evaluar_planta.py   # Capa: aplicación — caso de uso EvaluarPlanta (orquestación pura)
│   ├── repositorio_csv.py  # Capa: infraestructura — acceso a datos CSV implementando el puerto (RA5)
│   └── especies.csv        # Tabla de referencia de rangos óptimos por especie
├── Vista/
│   ├── index.html          # Marcado semántico y estructura visual, sin lógica (RA2)
│   └── styles.css          # Estilos CSS modernos (modo oscuro, componentes visuales)
├── tests/
│   └── test_dominio.py     # 14 pruebas unitarias aisladas con doble de prueba (sin Flask ni CSV)
├── documento_arquitectura.md # Esqueleto para el informe de arquitectura del curso
├── bitacora_ia.md            # Esqueleto para el registro de uso de IA generativa
├── requirements.txt         # Dependencias mínimas del backend (Flask, flask-cors, pytest)
└── README.md
```

---

## Cómo ejecutar

### 1. Backend (API Flask)

En una primera terminal:

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Iniciar el servidor Flask desde la raíz del proyecto
python Controlador/app.py
```

El backend queda disponible en **`http://127.0.0.1:5000`**.  
> **Nota de arquitectura (RA1):** El backend no renderiza HTML ni plantillas Jinja2; responde únicamente payloads en formato JSON.

Endpoints disponibles:
* `GET  /api/especies` — Lista de especies soportadas y sus rangos óptimos.
* `POST /api/diagnostico` — Recibe parámetros ambientales y devuelve el diagnóstico con recomendaciones.

---

### 2. Frontend estático (Servidor independiente — RA2)

En una **segunda terminal**, corre un servidor HTTP estático desde la **raíz del proyecto**:

```bash
# Desde la raíz del repositorio:
python -m http.server 8080
```

Luego abre en tu navegador:
```
http://localhost:8080/Vista/index.html
```

#### ¿Cómo se sirven juntos `Vista/index.html` y `Controlador/controlador.js`?
* `Vista/index.html` referencia al script mediante la ruta relativa:
  ```html
  <script src="../Controlador/controlador.js"></script>
  ```
* Al levantar `python -m http.server 8080` desde la raíz, el servidor sirve tanto la carpeta `Vista/` como `Controlador/`.
* Cuando el navegador solicita `http://localhost:8080/Vista/index.html`, resuelve `../Controlador/controlador.js` a `http://localhost:8080/Controlador/controlador.js` (HTTP 200).
* **Desacoplamiento total (RA2):** El frontend reside en el origen `http://localhost:8080`, mientras que la API reside en `http://127.0.0.1:5000`. Todas las interacciones se realizan vía `fetch()` asíncrono con CORS habilitado, sin recargar la página.

---

### 3. Pruebas Unitarias del Dominio

Las pruebas corren de forma aislada, sin necesidad de levantar Flask ni leer el archivo CSV en disco (utilizan el doble de prueba `FakeRepositorio` en memoria):

```bash
python -m pytest tests/ -v
```

---

## Fuente de los rangos de referencia (`Modelo/especies.csv`)

Los valores de `lux_min`, `lux_max`, `humedad_min`, `humedad_max`, `temperatura_min` y `temperatura_max` se recopilaron de fuentes botánicas reconocidas para cultivo interior:

1. **Royal Horticultural Society (RHS):** [rhs.org.uk](https://www.rhs.org.uk)
2. **Missouri Botanical Garden:** [missouribotanicalgarden.org](https://www.missouribotanicalgarden.org)
3. **Houseplant411 Care Guides:** [houseplant411.com](https://www.houseplant411.com)

---

## Ejemplos de uso de la API

### `GET /api/especies`

**Respuesta exitosa (HTTP 200):**
```json
[
  {
    "nombre": "Cactus (Cactaceae)",
    "rangos": {
      "luminosidad": { "min": 5000.0, "max": 15000.0, "unidad": "lux" },
      "humedad":     { "min": 10.0,   "max": 30.0,    "unidad": "%" },
      "temperatura": { "min": 18.0,   "max": 35.0,    "unidad": "°C" }
    }
  }
]
```

### `POST /api/diagnostico`

**Cuerpo de la petición (JSON):**
```json
{
  "especie": "Cactus (Cactaceae)",
  "luminosidad": 2000,
  "humedad": 20,
  "temperatura": 25
}
```

**Respuesta exitosa (HTTP 200):**
```json
{
  "success": true,
  "especie": "Cactus (Cactaceae)",
  "estado_global": "EN_RIESGO",
  "parametros": [
    {
      "nombre": "luminosidad",
      "valor": 2000.0,
      "clasificacion": "BAJO",
      "recomendacion": "Aumenta la exposición a la luz natural o artificial."
    },
    {
      "nombre": "humedad",
      "valor": 20.0,
      "clasificacion": "OPTIMO",
      "recomendacion": ""
    },
    {
      "nombre": "temperatura",
      "valor": 25.0,
      "clasificacion": "OPTIMO",
      "recomendacion": ""
    }
  ]
}
```

**Errores controlados (RF6):**
* `HTTP 404` para especie desconocida (`ESPECIE_NO_SOPORTADA`).
* `HTTP 400` para parámetro faltante (`PARAMETRO_AUSENTE`).
* `HTTP 400` para valor no numérico (`VALOR_NO_NUMERICO`).
* `HTTP 400` para valor fuera de límites físicos (`VALOR_FUERA_DE_RANGO_FISICO`).
