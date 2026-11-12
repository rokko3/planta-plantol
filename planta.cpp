/**
 * ============================================================================
 *  PLANTOL — Firmware ESP32 para Monitor de Planta Inteligente
 *  Versión: 1.0.0
 *  Framework: Arduino (compatible con Arduino IDE y PlatformIO)
 * ============================================================================
 *
 *  MÁQUINA DE ESTADOS:
 *    ESTADO 1 (CONFIG):   Sin credenciales → inicia BLE GATT para recibir
 *                         SSID, contraseña y token de emparejamiento.
 *    ESTADO 2 (OPERACIÓN): Vinculado → conecta a Wi-Fi y envía telemetría
 *                          de temperatura, humedad y luz cada N segundos.
 *    ESTADO 3 (RESET):    Botón BOOT (GPIO 0) pulsado > 5 s → Factory Reset.
 *
 *  LIBRERÍAS REQUERIDAS (instalar desde Library Manager o platformio.ini):
 *    - BLE (incluida en esp32 Arduino Core >= 2.x)
 *    - WiFi.h (incluida en esp32 Arduino Core)
 *    - HTTPClient.h (incluida en esp32 Arduino Core)
 *    - Preferences.h (incluida en esp32 Arduino Core)
 *    - DHT sensor library  → Adafruit DHT Sensor Library
 *    - Adafruit Unified Sensor (dependencia de DHT)
 *    - ArduinoJson          → Benoit Blanchon ≥ 6.x
 *    - (Opcional) BH1750    → Starmbi BH1750 si usas sensor I2C de luz
 *
 *  PlatformIO — platformio.ini:
 *    lib_deps =
 *      adafruit/DHT sensor library
 *      adafruit/Adafruit Unified Sensor
 *      bblanchon/ArduinoJson
 *      ; clydeps/BH1750   ← descomenta si usas el sensor I2C
 * ============================================================================
 */

// ============================================================================
//  SECCIÓN DE CONFIGURACIÓN — Modifica aquí sin tocar el resto del código
// ============================================================================

// ---- URLs del Backend (reemplaza con tu dominio real) ----------------------
#define BACKEND_HOST        "http://127.0.0.1:5000"
#define ENDPOINT_RECLAMAR   BACKEND_HOST "/api/dispositivos/reclamar"
#define ENDPOINT_MEDICIONES BACKEND_HOST "/api/dispositivos/PLACEHOLDER/lecturas"
//  Nota: PLACEHOLDER se reemplaza en tiempo de ejecución por la MAC real.

// ---- Pines de Sensores -----------------------------------------------------
#define PIN_DHT          4      // GPIO del sensor DHT11 / DHT22
#define DHT_TIPO         DHT22  // Cambia a DHT11 si es necesario
#define PIN_SUELO        34     // GPIO ADC para sensor de humedad de suelo
#define PIN_LDR          35     // GPIO ADC para LDR (sensor de luz analógico)
#define PIN_LED_ESTADO   2      // LED integrado en la mayoría de módulos ESP32
#define PIN_BOTON_RESET  0      // Botón BOOT del ESP32

// ---- BLE (UUID estándar de 128 bits) ----------------------------------------
#define BLE_DEVICE_NAME     "Planta-Sensor-Config"
#define BLE_SERVICE_UUID    "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BLE_CHAR_UUID       "beb5483e-36e1-4688-b7f5-ea07361b26a8"

// ---- Tiempos ----------------------------------------------------------------
#define INTERVALO_LECTURA_MS  5000UL   // Enviar telemetría cada 5 segundos
#define TIMEOUT_WIFI_MS       20000UL  // Espera máxima para conectar a Wi-Fi
#define TIEMPO_RESET_MS       5000UL   // Mantener botón pulsado para Factory Reset
#define PARPADEO_LED_MS       500      // Período de parpadeo durante BLE activo

// ---- Nombre de las claves en Preferences ------------------------------------
#define PREFS_NAMESPACE  "plantol"
#define KEY_SSID         "ssid"
#define KEY_PASS         "pass"
#define KEY_PAIRED       "paired"
#define KEY_TOKEN_JWT    "jwt"      // Token JWT de dispositivo emitido por el backend

// ============================================================================
//  INCLUDES
// ============================================================================
#include <Arduino.h>

// BLE
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// Wi-Fi y HTTP
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>

// Almacenamiento en Flash
#include <Preferences.h>

// Sensores
#include <DHT.h>
#include <ArduinoJson.h>

// (Opcional) Sensor de luz I2C BH1750 — descomenta si lo usas
// #include <BH1750.h>
// #include <Wire.h>
// BH1750 luxometro;
// bool usarBH1750 = false;

// ============================================================================
//  VARIABLES GLOBALES DE ESTADO
// ============================================================================

// Máquina de estados
enum EstadoDispositivo {
    ESTADO_CONFIG,     // BLE activo, esperando credenciales
    ESTADO_OPERACION   // Wi-Fi conectado, enviando telemetría
};
EstadoDispositivo estadoActual = ESTADO_CONFIG;

// Preferences (NVS Flash)
Preferences prefs;

// Credenciales obtenidas por BLE
String wifiSSID;
String wifiPass;
String pairingToken;
String macDispositivo;

// BLE
BLEServer*         pServer          = nullptr;
BLECharacteristic* pCaracteristica  = nullptr;
bool               bleConectado     = false;
bool               credencialesRecibidas = false;

// Sensor DHT
DHT dht(PIN_DHT, DHT_TIPO);

// Control de tiempo
unsigned long ultimoEnvio      = 0;
unsigned long inicioBoton      = 0;
bool          botonPresionado  = false;

// Token JWT del dispositivo (obtenido del backend tras vincularse)
String jwtDispositivo;

// ============================================================================
//  PROTOTIPOS DE FUNCIONES
// ============================================================================
void     iniciarBLE();
void     detenerBLE();
void     manejarCredencialesBLE(const String& payload);
bool     conectarWifi(const String& ssid, const String& pass);
bool     reclamarDispositivo(const String& token, const String& mac);
bool     obtenerTokenJWT(const String& mac);
void     enviarTelemetria();
float    leerTemperatura();
float    leerHumedad();
float    leerLuz();
void     manejarBotonReset();
void     factoryReset();
void     parpadearLED(int veces, int ms);
void     setLED(bool encendido);
String   construirURLMedicion(const String& mac);

// ============================================================================
//  CALLBACKS BLE
// ============================================================================

/** Callback de conexión/desconexión de un cliente BLE */
class CallbacksConexionBLE : public BLEServerCallbacks {
    void onConnect(BLEServer* server) override {
        bleConectado = true;
        Serial.println("[BLE] Cliente conectado.");
        setLED(true);
    }
    void onDisconnect(BLEServer* server) override {
        bleConectado = false;
        Serial.println("[BLE] Cliente desconectado. Reiniciando publicidad...");
        setLED(false);
        // Vuelve a hacer broadcast si aún no recibió credenciales
        if (!credencialesRecibidas) {
            BLEDevice::startAdvertising();
        }
    }
};

/** Callback de escritura en la característica BLE */
class CallbacksEscrituraGATT : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* pChar) override {
        std::string valorRaw = pChar->getValue();
        if (valorRaw.empty()) return;

        String payload = String(valorRaw.c_str());
        Serial.print("[BLE] Dato recibido (");
        Serial.print(payload.length());
        Serial.println(" bytes).");

        credencialesRecibidas = true;
        manejarCredencialesBLE(payload);
    }
};

// ============================================================================
//  SETUP
// ============================================================================
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n============================================");
    Serial.println("  PLANTOL — Firmware ESP32 v1.0");
    Serial.println("============================================");

    // Configurar pines
    pinMode(PIN_LED_ESTADO, OUTPUT);
    pinMode(PIN_BOTON_RESET, INPUT_PULLUP);
    setLED(false);

    // Leer la dirección MAC real del dispositivo
    macDispositivo = WiFi.macAddress();
    macDispositivo.replace(":", "");  // Formato: "AABBCCDDEEFF"
    Serial.print("[INFO] MAC del dispositivo: ");
    Serial.println(macDispositivo);

    // Iniciar sensor DHT
    dht.begin();
    Serial.println("[INFO] Sensor DHT inicializado.");

    // Leer estado guardado en Preferences
    prefs.begin(PREFS_NAMESPACE, true);  // true = solo lectura
    bool esPaired = prefs.getBool(KEY_PAIRED, false);
    wifiSSID = prefs.getString(KEY_SSID, "");
    wifiPass = prefs.getString(KEY_PASS, "");
    jwtDispositivo = prefs.getString(KEY_TOKEN_JWT, "");
    prefs.end();

    if (esPaired && wifiSSID.length() > 0) {
        Serial.println("[INFO] Dispositivo previamente vinculado. Iniciando MODO OPERACIÓN.");
        estadoActual = ESTADO_OPERACION;

        if (conectarWifi(wifiSSID, wifiPass)) {
            Serial.println("[WiFi] Conexión establecida. Sistema listo.");
            parpadearLED(3, 150);
        } else {
            Serial.println("[ERROR] No se pudo conectar al Wi-Fi guardado.");
            Serial.println("[INFO] Volviendo a MODO CONFIGURACIÓN BLE.");
            // Si el Wi-Fi guardado falla, limpiar y volver a BLE
            factoryReset();  // limpia y reinicia
        }
    } else {
        Serial.println("[INFO] Sin vinculación. Iniciando MODO CONFIGURACIÓN BLE.");
        estadoActual = ESTADO_CONFIG;
        iniciarBLE();
    }
}

// ============================================================================
//  LOOP PRINCIPAL
// ============================================================================
void loop() {
    // Siempre monitorear el botón de Factory Reset (cualquier estado)
    manejarBotonReset();

    if (estadoActual == ESTADO_CONFIG) {
        // En modo BLE: parpadear LED para indicar que espera configuración
        static unsigned long ultimoParpaded = 0;
        static bool ledState = false;
        if (millis() - ultimoParpaded > PARPADEO_LED_MS) {
            ultimoParpaded = millis();
            ledState = !ledState;
            setLED(ledState);
        }
        // La lógica real sucede en el callback CallbacksEscrituraGATT
    }

    if (estadoActual == ESTADO_OPERACION) {
        // Reconectar Wi-Fi si se cae
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[WiFi] Conexión perdida. Intentando reconectar...");
            setLED(false);
            conectarWifi(wifiSSID, wifiPass);
        }

        // Enviar telemetría según el intervalo configurado
        if (millis() - ultimoEnvio >= INTERVALO_LECTURA_MS) {
            ultimoEnvio = millis();
            enviarTelemetria();
        }

        setLED(WiFi.status() == WL_CONNECTED);
    }

    delay(50);  // Evitar saturar el procesador
}

// ============================================================================
//  IMPLEMENTACIÓN — MODO CONFIGURACIÓN BLE
// ============================================================================

/** Inicializa el stack BLE y pone el servidor en modo anuncio */
void iniciarBLE() {
    Serial.println("[BLE] Inicializando servidor GATT...");
    BLEDevice::init(BLE_DEVICE_NAME);

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new CallbacksConexionBLE());

    // Crear servicio y característica
    BLEService* pServicio = pServer->createService(BLE_SERVICE_UUID);
    pCaracteristica = pServicio->createCharacteristic(
        BLE_CHAR_UUID,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
    );
    pCaracteristica->setCallbacks(new CallbacksEscrituraGATT());
    pCaracteristica->addDescriptor(new BLE2902());

    pServicio->start();

    // Configurar advertising
    BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMinPreferred(0x12);
    BLEDevice::startAdvertising();

    Serial.print("[BLE] Publicando como: ");
    Serial.println(BLE_DEVICE_NAME);
    Serial.println("[BLE] Esperando conexión de la app web...");
}

/** Apaga completamente el stack BLE para liberar la antena 2.4 GHz */
void detenerBLE() {
    Serial.println("[BLE] Deteniendo BLE para liberar antena 2.4 GHz...");
    if (pServer != nullptr) {
        pServer->getAdvertising()->stop();
    }
    BLEDevice::deinit(true);  // true = libera toda la memoria BLE
    delay(500);
    Serial.println("[BLE] BLE detenido correctamente.");
}

/**
 * Procesa el payload recibido por GATT.
 * Acepta dos formatos:
 *   - Delimitado por pipe:  SSID|PASSWORD|TOKEN
 *   - JSON:                 {"ssid":"...","pass":"...","token":"..."}
 */
void manejarCredencialesBLE(const String& payload) {
    Serial.println("[BLE] Procesando credenciales recibidas...");

    bool parseOk = false;

    // Intentar parsear como JSON primero
    if (payload.startsWith("{")) {
        StaticJsonDocument<256> doc;
        DeserializationError err = deserializeJson(doc, payload);
        if (!err) {
            wifiSSID    = doc["ssid"].as<String>();
            wifiPass    = doc["pass"].as<String>();
            pairingToken = doc["token"].as<String>();
            parseOk = true;
            Serial.println("[BLE] Formato JSON detectado.");
        } else {
            Serial.print("[BLE][WARN] Error JSON: ");
            Serial.println(err.c_str());
        }
    }

    // Si no fue JSON, intentar formato SSID|PASS|TOKEN
    if (!parseOk) {
        int sep1 = payload.indexOf('|');
        int sep2 = payload.lastIndexOf('|');
        if (sep1 > 0 && sep2 > sep1) {
            wifiSSID    = payload.substring(0, sep1);
            wifiPass    = payload.substring(sep1 + 1, sep2);
            pairingToken = payload.substring(sep2 + 1);
            parseOk = true;
            Serial.println("[BLE] Formato PIPE detectado.");
        }
    }

    if (!parseOk || wifiSSID.isEmpty() || pairingToken.isEmpty()) {
        Serial.println("[ERROR] Formato de credenciales inválido. Volviendo a esperar...");
        credencialesRecibidas = false;
        return;
    }

    Serial.print("[BLE] SSID recibido: ");
    Serial.println(wifiSSID);
    Serial.println("[BLE] Token de emparejamiento recibido.");

    // Apagar BLE antes de intentar Wi-Fi (antena compartida)
    detenerBLE();

    // Intentar conectar a Wi-Fi
    if (!conectarWifi(wifiSSID, wifiPass)) {
        Serial.println("[ERROR] Falló la conexión Wi-Fi. Reiniciando BLE...");
        credencialesRecibidas = false;
        iniciarBLE();
        return;
    }

    // Reclamar el dispositivo en el backend con el token
    if (reclamarDispositivo(pairingToken, macDispositivo)) {
        // Obtener el token JWT de dispositivo para autenticar las lecturas
        bool tokenOk = obtenerTokenJWT(macDispositivo);
        if (!tokenOk) {
            Serial.println("[WARN] No se pudo obtener el token JWT. Las lecturas podrían ser rechazadas.");
        }

        // Guardar credenciales y cambiar a modo operación
        prefs.begin(PREFS_NAMESPACE, false);  // false = lectura/escritura
        prefs.putString(KEY_SSID, wifiSSID);
        prefs.putString(KEY_PASS, wifiPass);
        prefs.putBool(KEY_PAIRED, true);
        if (tokenOk) prefs.putString(KEY_TOKEN_JWT, jwtDispositivo);
        prefs.end();

        Serial.println("[INFO] ¡Dispositivo vinculado exitosamente!");
        parpadearLED(5, 200);

        estadoActual = ESTADO_OPERACION;
        ultimoEnvio  = millis() - INTERVALO_LECTURA_MS;  // Enviar inmediatamente
    } else {
        Serial.println("[ERROR] El backend rechazó el token. Volviendo a BLE...");
        WiFi.disconnect(true);
        delay(500);
        credencialesRecibidas = false;
        iniciarBLE();
    }
}

// ============================================================================
//  IMPLEMENTACIÓN — CONECTIVIDAD WI-FI
// ============================================================================

/** Conecta a la red Wi-Fi especificada con timeout configurable */
bool conectarWifi(const String& ssid, const String& pass) {
    Serial.print("[WiFi] Conectando a: ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid.c_str(), pass.c_str());

    unsigned long inicio = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - inicio > TIMEOUT_WIFI_MS) {
            Serial.println("\n[WiFi][ERROR] Timeout. No se pudo conectar.");
            WiFi.disconnect(true);
            return false;
        }
        Serial.print(".");
        delay(500);
    }

    Serial.println();
    Serial.print("[WiFi] Conectado. IP asignada: ");
    Serial.println(WiFi.localIP());
    return true;
}

// ============================================================================
//  HELPER HTTP UNIVERSAL (Soporta http:// y https://)
// ============================================================================
int ejecutarPost(const String& url, const String& payload, const String& tokenBearer, String& respuestaOut) {
    HTTPClient http;
    if (url.startsWith("https://")) {
        WiFiClientSecure clienteSeguro;
        clienteSeguro.setInsecure();
        http.begin(clienteSeguro, url);
    } else {
        WiFiClient clienteNormal;
        http.begin(clienteNormal, url);
    }
    http.addHeader("Content-Type", "application/json");
    if (tokenBearer.length() > 0) {
        http.addHeader("Authorization", "Bearer " + tokenBearer);
    }
    int codigo = http.POST(payload);
    respuestaOut = http.getString();
    http.end();
    return codigo;
}

// ============================================================================
//  IMPLEMENTACIÓN — REGISTRO EN EL BACKEND (EMPAREJAMIENTO)
// ============================================================================

/** Realiza el POST a /api/dispositivos/reclamar para vincular el dispositivo */
bool reclamarDispositivo(const String& token, const String& mac) {
    Serial.println("[HTTP] Registrando dispositivo en el backend...");
    Serial.print("[HTTP] URL: ");
    Serial.println(ENDPOINT_RECLAMAR);

    // Construir payload JSON
    StaticJsonDocument<128> doc;
    doc["token"] = token;
    doc["mac"]   = mac;
    String cuerpo;
    serializeJson(doc, cuerpo);

    Serial.print("[HTTP] POST payload: ");
    Serial.println(cuerpo);

    String respuesta;
    int codigoRespuesta = ejecutarPost(ENDPOINT_RECLAMAR, cuerpo, "", respuesta);

    Serial.print("[HTTP] Código de respuesta: ");
    Serial.println(codigoRespuesta);
    Serial.print("[HTTP] Respuesta backend: ");
    Serial.println(respuesta);

    return (codigoRespuesta == 200);
}

/**
 * Solicita al backend el token JWT del dispositivo.
 * El backend Plantol emite este token en:
 *   POST /api/dispositivos/<id>/token
 * El token se guarda en la variable global jwtDispositivo
 * y en Preferences para sobrevivir reinicios.
 *
 * El ID del dispositivo en el backend es la MAC (ej: "AABBCCDDEEFF").
 */
bool obtenerTokenJWT(const String& mac) {
    String urlToken = String(BACKEND_HOST) + "/api/dispositivos/" + mac + "/token";
    Serial.print("[HTTP] Obteniendo token JWT del dispositivo desde: ");
    Serial.println(urlToken);

    String respuesta;
    int codigo = ejecutarPost(urlToken, "", "", respuesta);

    Serial.print("[HTTP] Respuesta token: ");
    Serial.print(codigo);
    Serial.print(" → ");
    Serial.println(respuesta);

    if (codigo == 200) {
        StaticJsonDocument<256> doc;
        DeserializationError err = deserializeJson(doc, respuesta);
        if (!err && doc.containsKey("token")) {
            jwtDispositivo = doc["token"].as<String>();
            Serial.println("[HTTP] ✓ Token JWT de dispositivo obtenido correctamente.");
            return true;
        }
    }

    Serial.println("[HTTP] ✗ No se pudo obtener el token JWT.");
    return false;
}

// ============================================================================
//  IMPLEMENTACIÓN — TELEMETRÍA (MODO OPERACIÓN)
// ============================================================================

/** Construye la URL de medición reemplazando PLACEHOLDER por la MAC real */
String construirURLMedicion(const String& mac) {
    String url = String(ENDPOINT_MEDICIONES);
    url.replace("PLACEHOLDER", mac);
    return url;
}

/** Lee sensores y envía telemetría al backend */
void enviarTelemetria() {
    float temperatura = leerTemperatura();
    float humedad     = leerHumedad();
    float luz         = leerLuz();

    Serial.println("[SENSOR] ---- Lectura de sensores ----");
    Serial.print("  Temperatura : "); Serial.print(temperatura); Serial.println(" °C");
    Serial.print("  Humedad     : "); Serial.print(humedad);     Serial.println(" %");
    Serial.print("  Luz         : "); Serial.print(luz);         Serial.println(" lux");

    if (isnan(temperatura) || isnan(humedad)) {
        Serial.println("[ERROR] Lectura DHT inválida. Omitiendo envío.");
        return;
    }

    // Construir JSON de telemetría
    StaticJsonDocument<192> doc;
    doc["luminosidad"] = (int)luz;
    doc["humedad"]     = humedad;
    doc["temperatura"] = temperatura;
    String cuerpo;
    serializeJson(doc, cuerpo);

    String urlMedicion = construirURLMedicion(macDispositivo);

    // Asegurar que tengamos token JWT antes de enviar
    if (jwtDispositivo.length() == 0) {
        Serial.println("[WARN] Sin token JWT en memoria. Intentando obtenerlo...");
        if (obtenerTokenJWT(macDispositivo)) {
            prefs.begin(PREFS_NAMESPACE, false);
            prefs.putString(KEY_TOKEN_JWT, jwtDispositivo);
            prefs.end();
        }
    }

    Serial.print("[HTTP] Enviando telemetría a: ");
    Serial.println(urlMedicion);

    String respuesta;
    int codigoRespuesta = ejecutarPost(urlMedicion, cuerpo, jwtDispositivo, respuesta);

    Serial.print("[HTTP] Respuesta backend: ");
    Serial.print(codigoRespuesta);
    Serial.print(" → ");
    Serial.println(respuesta);

    if (codigoRespuesta == 201) {
        Serial.println("[HTTP] ✓ Lectura registrada exitosamente.");
        parpadearLED(1, 80);
    } else if (codigoRespuesta == 202) {
        Serial.println("[HTTP] ⚠ Dispositivo en red pero aún sin planta vinculada (202 Aceptado).");
    } else if (codigoRespuesta == 401 || codigoRespuesta == 403) {
        Serial.println("[HTTP] ✗ Token JWT expirado o inválido. Renovando...");
        if (obtenerTokenJWT(macDispositivo)) {
            prefs.begin(PREFS_NAMESPACE, false);
            prefs.putString(KEY_TOKEN_JWT, jwtDispositivo);
            prefs.end();
        }
    } else {
        Serial.print("[HTTP] ✗ Código de respuesta: ");
        Serial.println(codigoRespuesta);
    }
}

// ============================================================================
//  IMPLEMENTACIÓN — LECTURA DE SENSORES
// ============================================================================

/** Lee temperatura en °C desde el DHT11/DHT22 */
float leerTemperatura() {
    float t = dht.readTemperature();
    if (isnan(t)) {
        Serial.println("[SENSOR][WARN] Error leyendo temperatura del DHT.");
    }
    return t;
}

/** Lee humedad ambiental en % desde el DHT11/DHT22 */
float leerHumedad() {
    float h = dht.readHumidity();
    if (isnan(h)) {
        Serial.println("[SENSOR][WARN] Error leyendo humedad del DHT.");
    }
    return h;
}

/**
 * Lee el nivel de luz.
 * Por defecto usa el LDR analógico en PIN_LDR (rango ADC 0-4095 → 0-100000 lux).
 * Para usar el sensor digital BH1750 I2C, descomenta el bloque al final.
 */
float leerLuz() {
    // --- LDR ANALÓGICO ---
    int valorADC = analogRead(PIN_LDR);
    // El ESP32 tiene ADC de 12 bits (0-4095).
    // Un LDR en divisor de tensión: mayor ADC = más luz.
    // Ajusta la escala según el rango de tu sensor.
    float lux = map(valorADC, 0, 4095, 0, 100000);
    return lux;

    // --- BH1750 I2C (descomenta para usarlo) ---
    // Wire.begin();
    // if (luxometro.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    //     return luxometro.readLightLevel();
    // }
    // return -1.0;
}

/** Lee la humedad del suelo desde el pin analógico (0% = seco, 100% = húmedo) */
float leerHumedadSuelo() {
    int valorADC = analogRead(PIN_SUELO);
    // Los sensores capacitivos de suelo suelen leer:
    //   ~1500 en seco, ~4095 en mojado (invierte el map si es resistivo)
    float porcentaje = map(valorADC, 1500, 4095, 0, 100);
    porcentaje = constrain(porcentaje, 0, 100);
    return porcentaje;
}

// ============================================================================
//  IMPLEMENTACIÓN — FACTORY RESET Y BOTÓN BOOT
// ============================================================================

/** Monitorea el botón BOOT (GPIO 0). Si se mantiene > 5 s → Factory Reset */
void manejarBotonReset() {
    bool presionado = (digitalRead(PIN_BOTON_RESET) == LOW);  // LOW activo

    if (presionado && !botonPresionado) {
        // Comienza a contar
        botonPresionado = true;
        inicioBoton = millis();
        Serial.println("[RESET] Botón presionado. Mantén > 5 s para Factory Reset...");
    }

    if (presionado && botonPresionado) {
        unsigned long tiempoPresionado = millis() - inicioBoton;

        // Parpadeo rápido para avisar que está a punto de resetear
        if (tiempoPresionado > 3000) {
            setLED(millis() % 200 < 100);
        }

        if (tiempoPresionado >= TIEMPO_RESET_MS) {
            Serial.println("[RESET] ¡Factory Reset activado!");
            factoryReset();
        }
    }

    if (!presionado && botonPresionado) {
        botonPresionado = false;
        setLED(estadoActual == ESTADO_OPERACION && WiFi.status() == WL_CONNECTED);
        Serial.println("[RESET] Botón liberado antes del reset.");
    }
}

/** Borra todas las preferencias y reinicia el ESP32 */
void factoryReset() {
    Serial.println("[RESET] Limpiando memoria flash (Preferences)...");
    prefs.begin(PREFS_NAMESPACE, false);
    prefs.clear();
    prefs.end();
    Serial.println("[RESET] Memoria limpiada. Reiniciando en 1 segundo...");
    parpadearLED(10, 80);
    delay(500);
    ESP.restart();
}

// ============================================================================
//  UTILIDADES — LED
// ============================================================================

/** Enciende o apaga el LED de estado */
void setLED(bool encendido) {
    digitalWrite(PIN_LED_ESTADO, encendido ? HIGH : LOW);
}

/** Parpadea el LED N veces con el período dado en ms */
void parpadearLED(int veces, int ms) {
    for (int i = 0; i < veces; i++) {
        setLED(true);
        delay(ms);
        setLED(false);
        delay(ms);
    }
}

