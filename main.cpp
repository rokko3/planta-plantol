#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <BH1750.h>
#include <math.h>
#include <NimBLEDevice.h>

// Pines de tu montaje
#define SDA_PIN 8
#define SCL_PIN 9
#define SOIL_PIN 1
#define SOIL_ADC_DRY 3539
#define SOIL_ADC_WET 1500

// ---------------------------------------------------------------------------
// UUIDs GATT
// Servicio estándar: Environmental Sensing (0x181A)
// ---------------------------------------------------------------------------
#define ESS_SERVICE_UUID     ((uint16_t)0x181A)
// Temperatura   0x2A6E  sint16  resolución 0.01 °C
#define TEMP_CHAR_UUID       ((uint16_t)0x2A6E)
// Presión       0x2A6D  uint32  resolución 0.1 Pa
#define PRESS_CHAR_UUID      ((uint16_t)0x2A6D)
// Iluminancia   0x2AFB  uint24  resolución 0.01 lux
#define LUX_CHAR_UUID        ((uint16_t)0x2AFB)
// Servicio custom para humedad de suelo
#define SOIL_SERVICE_UUID    "ab12cd34-1234-1234-1234-1234567890ab"
#define SOIL_CHAR_UUID       "ab12cd34-5678-1234-1234-1234567890ab"

// ---------------------------------------------------------------------------
// Sensores
// ---------------------------------------------------------------------------
Adafruit_BMP280 bmp(&Wire);
BH1750 bh1750;

bool bmpDisponible = false;
bool luzDisponible = false;

// ---------------------------------------------------------------------------
// BLE
// ---------------------------------------------------------------------------
NimBLEServer*         pServer    = nullptr;
NimBLECharacteristic* pTempChar  = nullptr;
NimBLECharacteristic* pPressChar = nullptr;
NimBLECharacteristic* pLuxChar   = nullptr;
NimBLECharacteristic* pSoilChar  = nullptr;
bool deviceConnected = false;
class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo) override {
    deviceConnected = true;
    Serial.println("# BLE: cliente conectado");
  }
  void onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason) override {
    deviceConnected = false;
    Serial.println("# BLE: cliente desconectado, reiniciando advertising...");
    NimBLEDevice::startAdvertising();
  }
};

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1500);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  analogReadResolution(12);
  analogSetPinAttenuation(SOIL_PIN, ADC_11db);

  // --- Sensores ---
  bmpDisponible = bmp.begin(0x76);
  if (!bmpDisponible) {
    bmpDisponible = bmp.begin(0x77);
  }

  Serial.println("\n--- Diagnostico de sensores ---");

  if (bmpDisponible) {
    Serial.print("BMP280 detectado. ID: 0x");
    Serial.println(bmp.sensorID(), HEX);
    bmp.setSampling(
      Adafruit_BMP280::MODE_NORMAL,
      Adafruit_BMP280::SAMPLING_X1,
      Adafruit_BMP280::SAMPLING_X1,
      Adafruit_BMP280::FILTER_OFF,
      Adafruit_BMP280::STANDBY_MS_1000
    );
  } else {
    Serial.println("BMP280 NO DETECTADO");
  }

  luzDisponible = bh1750.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire);
  Serial.println(luzDisponible ? "GY-302: OK" : "GY-302: NO DETECTADO");

  // --- BLE ---
  NimBLEDevice::init("Planta-ESP32");
  pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  // ---- Servicio 1: Environmental Sensing (0x181A) ----
  // 3 características × 3 handles c/u + 1 servicio = 10 → reservamos 15
  NimBLEService* pEssService = pServer->createService(NimBLEUUID(ESS_SERVICE_UUID));

  pTempChar = pEssService->createCharacteristic(
    NimBLEUUID(TEMP_CHAR_UUID),
    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
  );

  pPressChar = pEssService->createCharacteristic(
    NimBLEUUID(PRESS_CHAR_UUID),
    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
  );

  pLuxChar = pEssService->createCharacteristic(
    NimBLEUUID(LUX_CHAR_UUID),
    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
  );

  pEssService->start();

  // ---- Servicio 2: Humedad de suelo (UUID custom) ----
  NimBLEService* pSoilService = pServer->createService(SOIL_SERVICE_UUID);

  pSoilChar = pSoilService->createCharacteristic(
    SOIL_CHAR_UUID,
    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
  );

  pSoilService->start();
  pServer->start();

  // Valores iniciales como texto para que los exploradores BLE los muestren legibles.
  pTempChar ->setValue("sin dato");
  { uint32_t value = 0xFFFFFFFF; pPressChar->setValue((uint8_t*)&value, 4); }
  pLuxChar  ->setValue("sin dato");
  pSoilChar ->setValue("sin dato");

  // Advertising: anuncia ambos servicios
  NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->enableScanResponse(true);
  pAdvertising->setName("Planta-ESP32");
  pAdvertising->addServiceUUID(NimBLEUUID(ESS_SERVICE_UUID));
  pAdvertising->addServiceUUID(SOIL_SERVICE_UUID);
  NimBLEDevice::startAdvertising();
  Serial.println("# BLE: advertising iniciado como 'Planta-ESP32'");

  Serial.println("humedad_suelo_pct,temperatura_c,presion_hpa,luz_lux");
}

// ---------------------------------------------------------------------------
// loop
// ---------------------------------------------------------------------------
void loop() {
  int sueloADC = analogRead(SOIL_PIN);
  int humedadSuelo = map(sueloADC, SOIL_ADC_DRY, SOIL_ADC_WET, 0, 100);
  humedadSuelo = constrain(humedadSuelo, 0, 100);

  float temperatura = NAN;
  float presion = NAN;
  float luz = NAN;

  if (bmpDisponible) {
    temperatura = bmp.readTemperature();
    presion = bmp.readPressure() / 100.0F;
  }

  if (luzDisponible) {
    luz = bh1750.readLightLevel();
  }

  // --- Actualizar características BLE ---

  // Texto ASCII para que el valor se vea como decimal en cualquier explorador BLE.
  {
    String tempBLE = isnan(temperatura) ? "sin dato" : String(temperatura, 2);
    pTempChar->setValue(tempBLE);
    if (deviceConnected) pTempChar->notify();
  }

  // Presión: uint32 en unidades de 0,1 Pa, como exige el UUID 0x2A6D.
  {
    uint32_t pressBLE = isnan(presion) ? 0xFFFFFFFF : (uint32_t)(presion * 1000.0F);
    pPressChar->setValue((uint8_t*)&pressBLE, 4);
    if (deviceConnected) pPressChar->notify();
  }

  // Iluminancia en lux.
  {
    String luxBLE = isnan(luz) ? "sin dato" : String(luz, 2);
    pLuxChar->setValue(luxBLE);
    if (deviceConnected) pLuxChar->notify();
  }

  // Humedad de suelo como porcentaje.
  {
    String soilBLE = String(humedadSuelo) + "%";
    pSoilChar->setValue(soilBLE);
    if (deviceConnected) pSoilChar->notify();
  }

  // --- Monitor serial ---
  Serial.print("ID del sensor: 0x");
  Serial.println(bmpDisponible ? String(bmp.sensorID(), HEX) : "NO DISPONIBLE");

  Serial.print("Temperatura: ");
  Serial.print(temperatura);
  Serial.println(" °C");

  Serial.print("Presion: ");
  Serial.print(presion);
  Serial.println(" hPa");

  Serial.print("Luz: ");
  Serial.print(luz);
  Serial.println(" lux");

  Serial.print("Humedad del suelo: ");
  Serial.print(humedadSuelo);
  Serial.println(" %");

  Serial.print("Lectura del suelo (ADC): ");
  Serial.println(sueloADC);

  // Formato CSV para Python
  Serial.print(humedadSuelo);
  Serial.print(",");
  Serial.print(temperatura, 2);
  Serial.print(",");
  Serial.print(presion, 2);
  Serial.print(",");
  Serial.println(luz, 2);

  Serial.println("--------------------");

  delay(2000);
}