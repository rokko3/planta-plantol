/**
 * ============================================================================
 *  PLANTA INTELIGENTE — Firmware ESP32-S3 (Plantol)
 *  Versión: 2.1.0 (BLE + Wi-Fi + JWT + OLED Gamificación)
 *  Hardware: ESP32-S3-DevKitC-1
 *  Sensores y Pantalla:
 *    - DHT11 (GPIO 4): Temperatura y humedad ambiental
 *    - Sensor de Suelo Analógico (GPIO 5): Humedad del sustrato
 *    - BH1750 / GY-302 I2C (SDA GPIO 8, SCL GPIO 9, dir 0x23): Luminosidad
 *    - Pantalla OLED SSD1306 I2C (SDA GPIO 8, SCL GPIO 9, dir 0x3C/0x3D)
 * ============================================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <esp_mac.h>

// BLE (NimBLE / BLE Arduino ESP32)
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>

// Pantalla OLED con caras de gamificación
#include "PantallaOLED.h"

// ----------------------------------------------------------------------------
// CONFIGURACIÓN DE PINES (Hardware Planta_Inteligente)
// ----------------------------------------------------------------------------
#define DHT_PIN         4
#define DHT_TYPE        DHT11
#define SOIL_PIN        5
#define SDA_PIN         8
#define SCL_PIN         9
#define PIN_LED_ESTADO  2
#define PIN_BOTON_RESET 0

// Calibración de sensor analógico de suelo (ADC 12 bits: 0 - 4095)
#define SUELO_ADC_SECO    3500
#define SUELO_ADC_HUMEDO  1400

// ----------------------------------------------------------------------------
// BLE GATT UUIDs (Deben coincidir exactamente con Vista/app.js)
// ----------------------------------------------------------------------------
#define BLE_DEVICE_NAME      "Planta-Sensor-Config"
#define BLE_SERVICE_UUID     "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BLE_CHAR_CONFIG_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define BLE_CHAR_STATUS_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a9"

// ----------------------------------------------------------------------------
// PARÁMETROS TEMPORALES Y PREFERENCES
// ----------------------------------------------------------------------------
#define INTERVALO_TELEMETRIA_MS 5000UL
#define TIMEOUT_WIFI_MS         20000UL
#define TIEMPO_RESET_MS         5000UL
#define PARPADEO_LED_BLE_MS     400

#define PREFS_NAMESPACE  "plantol"
#define KEY_SSID         "ssid"
#define KEY_PASS         "pass"
#define KEY_HOST         "host"
#define KEY_PAIRED       "paired"
#define KEY_TOKEN_JWT    "jwt"

#define DEFAULT_BACKEND_HOST "http://192.168.2.8:5000"

// ----------------------------------------------------------------------------
// OBJETOS Y VARIABLES GLOBALES
// ----------------------------------------------------------------------------
DHT dht(DHT_PIN, DHT_TYPE);
BH1750 lightSensor;
Preferences prefs;

enum EstadoDispositivo {
    ESTADO_CONFIG,
    ESTADO_OPERACION
};
EstadoDispositivo estadoActual = ESTADO_CONFIG;

String wifiSSID;
String wifiPass;
String backendHost = DEFAULT_BACKEND_HOST;
String pairingToken;
String macDispositivo;
String jwtDispositivo;

// Estado de sensores I2C
bool   bh1750Activo  = false;

// Estado de gamificación recibido del backend
String emocionActual = "RADIANTE";
int    hpActual      = 100;

// BLE
BLEServer*         pServer                = nullptr;
BLECharacteristic* pCharConfig            = nullptr;
BLECharacteristic* pCharStatus            = nullptr;
bool               bleConectado           = false;
bool               hayNuevasCredenciales  = false;
String             payloadRecibido        = "";
String             estadoBleTexto         = "Listo p/ Web";
int                ultimoCodigoHTTP       = 0;

// Tiempos
unsigned long ultimoEnvio = 0;
unsigned long inicioBoton = 0;
bool botonPresionado = false;

// ----------------------------------------------------------------------------
// PROTOTIPOS
// ----------------------------------------------------------------------------
void   iniciarBLE();
void   detenerBLE();
void   enviarEstadoBLE(const String& estado);
void   procesarCredenciales(const String& payload);
bool   conectarWifi(const String& ssid, const String& pass);
bool   reclamarDispositivo(const String& host, const String& token, const String& mac);
bool   obtenerTokenJWT(const String& host, const String& mac);
void   enviarTelemetria();
float  leerTemperatura();
float  leerHumedadAire();
float  leerHumedadSuelo();
float  leerLuminosidad();
void   manejarBotonReset();
void   factoryReset();
void   setLED(bool encendido);
void   parpadearLED(int veces, int ms);

// ----------------------------------------------------------------------------
// CALLBACKS BLE
// ----------------------------------------------------------------------------
class CallbacksServidorBLE : public BLEServerCallbacks {
    void onConnect(BLEServer* server) override {
        bleConectado = true;
        estadoBleTexto = "Web conectada";
        Serial.println("[BLE] Cliente web conectado.");
        setLED(true);
        enviarEstadoBLE("LISTO");
    }
    void onDisconnect(BLEServer* server) override {
        bleConectado = false;
        setLED(false);
        Serial.println("[BLE] Cliente web desconectado.");
        if (estadoActual == ESTADO_CONFIG && !hayNuevasCredenciales) {
            estadoBleTexto = "Listo p/ Web";
            BLEDevice::startAdvertising();
        }
    }
};

class CallbacksEscrituraConfig : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* pChar) override {
        String payload = pChar->getValue().c_str();
        if (payload.length() == 0) return;
        Serial.print("[BLE] Configuración recibida (");
        Serial.print(payload.length());
        Serial.println(" bytes).");
        payloadRecibido = payload;
        hayNuevasCredenciales = true;
    }
};

// ----------------------------------------------------------------------------
// SETUP
// ----------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n================================================");
    Serial.println("  PLANTOL — Firmware ESP32-S3 v2.1 (BLE + OLED)");
    Serial.println("================================================");

    pinMode(PIN_LED_ESTADO, OUTPUT);
    pinMode(PIN_BOTON_RESET, INPUT_PULLUP);
    setLED(false);

    // Obtener MAC eFuse única
    uint8_t baseMac[6];
    esp_read_mac(baseMac, ESP_MAC_WIFI_STA);
    char macBuf[13];
    snprintf(macBuf, sizeof(macBuf), "%02X%02X%02X%02X%02X%02X",
             baseMac[0], baseMac[1], baseMac[2], baseMac[3], baseMac[4], baseMac[5]);
    macDispositivo = String(macBuf);
    Serial.print("[INFO] Identificador MAC del ESP32: ");
    Serial.println(macDispositivo);

    // Inicializar bus I2C compartido (GPIO 8 SDA, GPIO 9 SCL) a 100 kHz
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);

    // Inicializar sensores primero (antes de la OLED)
    dht.begin();
    analogReadResolution(12);
    if (lightSensor.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire)) {
        bh1750Activo = true;
        Serial.println("[SENSOR] Sensor BH1750 (GY-302) en 0x23: OK");
    } else if (lightSensor.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x5C, &Wire)) {
        bh1750Activo = true;
        Serial.println("[SENSOR] Sensor BH1750 (GY-302) en 0x5C: OK");
    } else {
        bh1750Activo = false;
        Serial.println("[SENSOR][WARN] BH1750 no detectado en 0x23 ni 0x5C. Escaneando bus I2C:");
        for (uint8_t addr = 1; addr < 127; addr++) {
            Wire.beginTransmission(addr);
            if (Wire.endTransmission() == 0) {
                Serial.print("  -> Dispositivo I2C encontrado en 0x");
                Serial.println(addr, HEX);
            }
        }
    }

    // Inicializar OLED compartiendo el bus I2C ya configurado
    PantallaOLED::inicializar();
    Wire.setClock(100000);

    // Consultar persistencia en NVS Flash
    prefs.begin(PREFS_NAMESPACE, true);
    bool vinculado = prefs.getBool(KEY_PAIRED, false);
    wifiSSID       = prefs.getString(KEY_SSID, "");
    wifiPass       = prefs.getString(KEY_PASS, "");
    backendHost    = prefs.getString(KEY_HOST, DEFAULT_BACKEND_HOST);
    jwtDispositivo = prefs.getString(KEY_TOKEN_JWT, "");
    prefs.end();

    if (vinculado && wifiSSID.length() > 0) {
        Serial.println("[INFO] Dispositivo vinculado previamente.");
        Serial.print("[INFO] Backend Host configurado: ");
        Serial.println(backendHost);
        estadoActual = ESTADO_OPERACION;
        PantallaOLED::mostrarMensaje("Conectando WiFi", wifiSSID);

        if (conectarWifi(wifiSSID, wifiPass)) {
            Serial.println("[WiFi] Conectado. Iniciando telemetría...");
            parpadearLED(3, 120);
            ultimoEnvio = millis() - INTERVALO_TELEMETRIA_MS; // Enviar de inmediato
        } else {
            Serial.println("[WiFi][WARN] No se pudo conectar al Wi-Fi guardado.");
            Serial.println("[INFO] Pasando a modo CONFIGURACIÓN BLE...");
            estadoActual = ESTADO_CONFIG;
            iniciarBLE();
        }
    } else {
        Serial.println("[INFO] Sin vinculación previa. Iniciando servicio BLE...");
        estadoActual = ESTADO_CONFIG;
        iniciarBLE();
    }
}

// ----------------------------------------------------------------------------
// LOOP
// ----------------------------------------------------------------------------
void loop() {
    manejarBotonReset();

    if (estadoActual == ESTADO_CONFIG) {
        if (hayNuevasCredenciales) {
            hayNuevasCredenciales = false;
            procesarCredenciales(payloadRecibido);
        }

        // Parpadeo suave en modo configuración y refresco OLED
        static unsigned long ultimoParpadeo = 0;
        static unsigned long ultimoOledBle  = 0;
        static bool estadoLED = false;
        if (millis() - ultimoParpadeo > PARPADEO_LED_BLE_MS) {
            ultimoParpadeo = millis();
            estadoLED = !estadoLED;
            setLED(estadoLED);
        }
        if (millis() - ultimoOledBle > 1000) {
            ultimoOledBle = millis();
            PantallaOLED::mostrarConfigBLE(macDispositivo, estadoBleTexto);
        }
    } else if (estadoActual == ESTADO_OPERACION) {
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[WiFi] Enlace perdido. Reconectando...");
            setLED(false);
            conectarWifi(wifiSSID, wifiPass);
        }

        if (millis() - ultimoEnvio >= INTERVALO_TELEMETRIA_MS) {
            ultimoEnvio = millis();
            enviarTelemetria();
        }

        setLED(WiFi.status() == WL_CONNECTED);
    }

    delay(30);
}

// ----------------------------------------------------------------------------
// BLE IMPLEMENTACIÓN
// ----------------------------------------------------------------------------
void iniciarBLE() {
    if (pServer == nullptr) {
        Serial.println("[BLE] Inicializando servidor GATT...");
        BLEDevice::init(BLE_DEVICE_NAME);
        BLEDevice::setMTU(517);
        pServer = BLEDevice::createServer();
        pServer->setCallbacks(new CallbacksServidorBLE());

        BLEService* pServicio = pServer->createService(BLE_SERVICE_UUID);

        // Característica para recibir configuración Wi-Fi + Host + Token (Write Request fiable)
        pCharConfig = pServicio->createCharacteristic(
            BLE_CHAR_CONFIG_UUID,
            BLECharacteristic::PROPERTY_WRITE
        );
        pCharConfig->setCallbacks(new CallbacksEscrituraConfig());

        // Característica para notificar estado (NimBLE crea el descriptor 0x2902 automáticamente)
        pCharStatus = pServicio->createCharacteristic(
            BLE_CHAR_STATUS_UUID,
            BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
        );

        pServicio->start();

        BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
        pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
        pAdvertising->setScanResponse(true);
        pAdvertising->setMinPreferred(0x06);
        pAdvertising->setMinPreferred(0x12);
    }

    BLEDevice::startAdvertising();
    estadoBleTexto = "Listo p/ Web";
    PantallaOLED::mostrarConfigBLE(macDispositivo, estadoBleTexto);
    Serial.print("[BLE] Anunciando servicio como: ");
    Serial.println(BLE_DEVICE_NAME);
    enviarEstadoBLE("LISTO");
}

void detenerBLE() {
    Serial.println("[BLE] Deteniendo publicidad para ceder antena a Wi-Fi...");
    BLEAdvertising* pAdv = BLEDevice::getAdvertising();
    if (pAdv != nullptr) pAdv->stop();
    delay(200);
}

void enviarEstadoBLE(const String& estado) {
    if (pCharStatus != nullptr && bleConectado) {
        pCharStatus->setValue(estado.c_str());
        pCharStatus->notify();
    }
}

void procesarCredenciales(const String& payload) {
    Serial.println("[BLE] Procesando configuración recibida...");
    estadoBleTexto = "Procesando...";
    PantallaOLED::mostrarConfigBLE(macDispositivo, estadoBleTexto);
    enviarEstadoBLE("PROCESANDO_CONFIG");

    bool parseOk = false;
    String hostTmp = DEFAULT_BACKEND_HOST;

    if (payload.startsWith("{")) {
        StaticJsonDocument<512> doc;
        DeserializationError err = deserializeJson(doc, payload);
        if (!err) {
            wifiSSID     = doc["ssid"].as<String>();
            wifiPass     = doc["pass"].as<String>();
            pairingToken = doc["token"].as<String>();
            if (doc.containsKey("host") && doc["host"].as<String>().length() > 0) {
                hostTmp = doc["host"].as<String>();
            }
            parseOk = true;
        }
    } else {
        // Formato delimitado: SSID|PASSWORD|TOKEN|HOST
        int sep1 = payload.indexOf('|');
        int sep2 = payload.indexOf('|', sep1 + 1);
        int sep3 = payload.indexOf('|', sep2 + 1);
        if (sep1 > 0 && sep2 > sep1) {
            wifiSSID     = payload.substring(0, sep1);
            wifiPass     = payload.substring(sep1 + 1, sep2);
            if (sep3 > sep2) {
                pairingToken = payload.substring(sep2 + 1, sep3);
                hostTmp      = payload.substring(sep3 + 1);
            } else {
                pairingToken = payload.substring(sep2 + 1);
            }
            parseOk = true;
        }
    }

    if (!parseOk || wifiSSID.isEmpty() || pairingToken.isEmpty()) {
        Serial.println("[BLE][ERROR] Formato de credenciales inválido.");
        estadoBleTexto = "Error formato";
        enviarEstadoBLE("ERROR_FORMATO");
        return;
    }

    backendHost = hostTmp;
    Serial.print("[BLE] SSID: "); Serial.println(wifiSSID);
    Serial.print("[BLE] Backend Host: "); Serial.println(backendHost);

    estadoBleTexto = "Conectando WiFi";
    PantallaOLED::mostrarConfigBLE(macDispositivo, estadoBleTexto);
    enviarEstadoBLE("CONECTANDO_WIFI");
    detenerBLE();

    if (!conectarWifi(wifiSSID, wifiPass)) {
        Serial.println("[BLE][ERROR] No se pudo conectar a la red Wi-Fi.");
        estadoBleTexto = "Error WiFi";
        enviarEstadoBLE("ERROR_WIFI");
        iniciarBLE();
        return;
    }

    estadoBleTexto = "Reclamando...";
    PantallaOLED::mostrarConfigBLE(macDispositivo, estadoBleTexto);
    enviarEstadoBLE("RECLAMANDO");

    if (reclamarDispositivo(backendHost, pairingToken, macDispositivo)) {
        bool jwtOk = obtenerTokenJWT(backendHost, macDispositivo);
        if (!jwtOk) {
            Serial.println("[WARN] Token JWT no obtenido inmediatamente.");
        }

        prefs.begin(PREFS_NAMESPACE, false);
        prefs.putString(KEY_SSID, wifiSSID);
        prefs.putString(KEY_PASS, wifiPass);
        prefs.putString(KEY_HOST, backendHost);
        prefs.putBool(KEY_PAIRED, true);
        if (jwtOk) prefs.putString(KEY_TOKEN_JWT, jwtDispositivo);
        prefs.end();

        Serial.println("[INFO] ¡Dispositivo configurado y vinculado con éxito!");
        enviarEstadoBLE("VINCULADO");
        PantallaOLED::mostrarMensaje("VINCULADO!", "Iniciando...");
        parpadearLED(5, 100);

        estadoActual = ESTADO_OPERACION;
        ultimoEnvio  = millis() - INTERVALO_TELEMETRIA_MS;
    } else {
        Serial.println("[ERROR] Rechazo en backend al reclamar dispositivo.");
        String msgErr = "HTTP ERR: " + String(ultimoCodigoHTTP);
        PantallaOLED::mostrarMensaje(msgErr, backendHost.substring(0, 20));
        delay(3500);
        estadoBleTexto = "Err HTTP " + String(ultimoCodigoHTTP);
        enviarEstadoBLE("ERROR_BACKEND");
        WiFi.disconnect(true);
        delay(500);
        iniciarBLE();
    }
}

// ----------------------------------------------------------------------------
// WI-FI & HTTP
// ----------------------------------------------------------------------------
bool conectarWifi(const String& ssid, const String& pass) {
    Serial.print("[WiFi] Conectando a red: ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);
    WiFi.setTxPower(WIFI_POWER_15dBm); // Evita picos de corriente/brownout en protoboard USB
    WiFi.begin(ssid.c_str(), pass.c_str());

    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - t0 > TIMEOUT_WIFI_MS) {
            Serial.println("\n[WiFi][ERROR] Timeout de conexión excedido.");
            WiFi.disconnect(true);
            return false;
        }
        Serial.print(".");
        delay(400);
    }
    Serial.println();
    Serial.print("[WiFi] Conectado. IP local del ESP32: ");
    Serial.println(WiFi.localIP());
    delay(800); // Permite estabilizar DHCP/ARP en hotspots móviles antes del primer HTTP
    return true;
}

int postHTTP(const String& url, const String& cuerpo, const String& tokenAuth, String& respuestaOut) {
    int codigo = -1;
    respuestaOut = "";

    if (url.startsWith("https://")) {
        WiFiClientSecure secClient;
        secClient.setInsecure();
        HTTPClient http;
        if (http.begin(secClient, url)) {
            http.setTimeout(8000);
            http.addHeader("Content-Type", "application/json");
            if (tokenAuth.length() > 0) {
                http.addHeader("Authorization", "Bearer " + tokenAuth);
            }
            codigo = http.POST(cuerpo);
            if (codigo > 0) respuestaOut = http.getString();
            http.end();
        }
    } else {
        WiFiClient normalClient;
        HTTPClient http;
        if (http.begin(normalClient, url)) {
            http.setTimeout(8000);
            http.addHeader("Content-Type", "application/json");
            if (tokenAuth.length() > 0) {
                http.addHeader("Authorization", "Bearer " + tokenAuth);
            }
            codigo = http.POST(cuerpo);
            if (codigo > 0) respuestaOut = http.getString();
            http.end();
        }
    }
    ultimoCodigoHTTP = codigo;
    return codigo;
}

bool reclamarDispositivo(const String& host, const String& token, const String& mac) {
    String url = host + "/api/dispositivos/reclamar";
    StaticJsonDocument<128> doc;
    doc["token"] = token;
    doc["mac"]   = mac;
    String cuerpo;
    serializeJson(doc, cuerpo);

    Serial.print("[HTTP] Reclamando en: "); Serial.println(url);
    String resp;
    int codigo = postHTTP(url, cuerpo, "", resp);
    Serial.print("[HTTP] Código: "); Serial.println(codigo);
    return (codigo == 200);
}

bool obtenerTokenJWT(const String& host, const String& mac) {
    String url = host + "/api/dispositivos/" + mac + "/token";
    Serial.print("[HTTP] Solicitando JWT en: "); Serial.println(url);

    String resp;
    int codigo = postHTTP(url, "", "", resp);
    if (codigo == 200) {
        StaticJsonDocument<512> doc;
        DeserializationError err = deserializeJson(doc, resp);
        if (!err && doc.containsKey("token")) {
            jwtDispositivo = doc["token"].as<String>();
            Serial.println("[HTTP] Token JWT recibido exitosamente.");
            return true;
        }
    }
    return false;
}

// ----------------------------------------------------------------------------
// TELEMETRÍA, GAMIFICACIÓN EN OLED Y SENSORES
// ----------------------------------------------------------------------------
void enviarTelemetria() {
    float temp     = leerTemperatura();
    float humSuelo = leerHumedadSuelo();
    float luz      = leerLuminosidad();

    Serial.println("\n[TELEMETRIA] ---- Lecturas Sensores ----");
    Serial.print("  Temperatura    : "); Serial.print(temp);     Serial.println(" °C");
    Serial.print("  Humedad Suelo  : "); Serial.print(humSuelo); Serial.println(" %");
    Serial.print("  Luz (BH1750)   : "); Serial.print(luz);      Serial.println(" lux");

    float tempEnvio     = isnan(temp)     ? 0.0f : temp;
    float humSueloEnvio = isnan(humSuelo) ? 0.0f : humSuelo;
    float luzEnvio      = isnan(luz)      ? 0.0f : luz;

    StaticJsonDocument<256> doc;
    doc["temperatura"]   = tempEnvio;
    // Se envía humedad_suelo también en 'humedad' para compatibilidad con evaluación agronómica del backend
    doc["humedad"]       = humSueloEnvio;
    doc["humedad_suelo"] = humSueloEnvio;
    doc["luminosidad"]   = luzEnvio;

    String cuerpo;
    serializeJson(doc, cuerpo);

    if (jwtDispositivo.length() == 0) {
        if (obtenerTokenJWT(backendHost, macDispositivo)) {
            prefs.begin(PREFS_NAMESPACE, false);
            prefs.putString(KEY_TOKEN_JWT, jwtDispositivo);
            prefs.end();
        }
    }

    String url = backendHost + "/api/dispositivos/" + macDispositivo + "/lecturas";
    String resp;
    int codigo = postHTTP(url, cuerpo, jwtDispositivo, resp);

    Serial.print("[HTTP] Enviar telemetría (POST "); Serial.print(codigo); Serial.print("): ");
    Serial.println(resp);

    if (codigo == 200 || codigo == 201) {
        parpadearLED(1, 60);
        // Extraer estado emocional y HP de gamificación desde el diagnóstico del backend
        DynamicJsonDocument respDoc(2048);
        DeserializationError err = deserializeJson(respDoc, resp);
        if (!err && respDoc.containsKey("diagnostico")) {
            JsonObject diag = respDoc["diagnostico"];
            if (diag.containsKey("estado_emocional")) {
                emocionActual = diag["estado_emocional"].as<String>();
            }
            if (diag.containsKey("hp")) {
                hpActual = diag["hp"].as<int>();
            }
        }
    } else if (codigo == 202) {
        // Dispositivo registrado en red pero aún sin planta asignada en la web
        emocionActual = "SIN PLANTA";
        hpActual = 100;
    } else if (codigo == 401 || codigo == 403) {
        Serial.println("[HTTP][WARN] Token JWT no autorizado (401/403). Renovando en siguiente ciclo.");
        jwtDispositivo = "";
    } else if (codigo == 404) {
        Serial.println("[HTTP][WARN] Dispositivo no registrado en backend (404).");
        jwtDispositivo = "";
    }

    // Actualizar pantalla OLED con la cara de gamificación y lecturas reales
    PantallaOLED::mostrarGamificacion(
        emocionActual,
        hpActual,
        tempEnvio,
        humSueloEnvio,
        luzEnvio,
        WiFi.status() == WL_CONNECTED
    );
}

float leerTemperatura() {
    return dht.readTemperature();
}

float leerHumedadAire() {
    return dht.readHumidity();
}

float leerHumedadSuelo() {
    int adc = analogRead(SOIL_PIN);
    float porcentaje = (float)map(adc, SUELO_ADC_SECO, SUELO_ADC_HUMEDO, 0, 100);
    porcentaje = constrain(porcentaje, 0.0f, 100.0f);
    return porcentaje;
}

float leerLuminosidad() {
    if (!bh1750Activo) {
        if (lightSensor.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire) ||
            lightSensor.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x5C, &Wire)) {
            bh1750Activo = true;
            Serial.println("[SENSOR] BH1750 reconectado en I2C.");
        } else {
            return 0.0f;
        }
    }
    float lux = lightSensor.readLightLevel();
    if (lux < 0) {
        bh1750Activo = false;
        return 0.0f;
    }
    return lux;
}

// ----------------------------------------------------------------------------
// RESET Y UTILIDADES
// ----------------------------------------------------------------------------
void manejarBotonReset() {
    bool presionado = (digitalRead(PIN_BOTON_RESET) == LOW);

    if (presionado && !botonPresionado) {
        botonPresionado = true;
        inicioBoton = millis();
        Serial.println("[RESET] Botón presionado. Mantén 5 s para Factory Reset...");
    }

    if (presionado && botonPresionado) {
        if (millis() - inicioBoton >= TIEMPO_RESET_MS) {
            Serial.println("[RESET] ¡Factory Reset ejecutado!");
            factoryReset();
        }
    }

    if (!presionado && botonPresionado) {
        botonPresionado = false;
    }
}

void factoryReset() {
    PantallaOLED::mostrarMensaje("FACTORY RESET", "Borrando flash...");
    prefs.begin(PREFS_NAMESPACE, false);
    prefs.clear();
    prefs.end();
    Serial.println("[RESET] Memoria Flash borrada. Reiniciando...");
    parpadearLED(10, 50);
    delay(500);
    ESP.restart();
}

void setLED(bool encendido) {
    digitalWrite(PIN_LED_ESTADO, encendido ? HIGH : LOW);
}

void parpadearLED(int veces, int ms) {
    for (int i = 0; i < veces; i++) {
        setLED(true);
        delay(ms);
        setLED(false);
        delay(ms);
    }
}
