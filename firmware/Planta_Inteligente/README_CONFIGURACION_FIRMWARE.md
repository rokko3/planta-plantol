# NOTA PARA AGENTES / DESARROLLADORES — GESTIÓN DE FIRMWARES EN ESTE PROYECTO

En esta carpeta (`Planta_Inteligente`) conviven dos perfiles de firmware para el microcontrolador ESP32-S3:

---

## 1. Archivo Activo en Compilación: `src/main.cpp` (Proyecto COMPLEXNET)
* **Propósito:** Baliza sensorial para red distribuida ad hoc (Proyecto ComplexNet).
* **Comportamiento:** 
  * Lee sensores en pines: DHT11 (GPIO 4), Suelo analógico (GPIO 5), BH1750 I2C (SDA GPIO 8, SCL GPIO 9).
  * Emite continuamente un JSON por Serial a 115200 baudios:
    `{"temp": 24.2, "hum_aire": 64.0, "suelo": 3565, "luz": 0.0}`
  * No utiliza Wi-Fi, BLE ni endpoints HTTP.

---

## 2. Archivo Guardado: `otro_proyecto_plantol/planta_inteligente_ble_wifi.cpp` (Proyecto PLANTOL / PLANTA INTELIGENTE)
* **Propósito:** Monitor IoT de Planta Inteligente v2.0.
* **Comportamiento:**
  * Incluye máquina de estados con Bluetooth Low Energy (BLE GATT `"Planta-Sensor-Config"`).
  * Conexión Wi-Fi, autenticación con tokens JWT y envíos `HTTP POST` periódicos a `http://192.168.1.50:5000` (reclamar dispositivo y telemetría).
  * Soporte para pantalla OLED (`PantallaOLED.h`).
* **¿Por qué está en una carpeta separada?**
  * PlatformIO compila automáticamente **todos** los archivos `.cpp` que estén dentro de la carpeta `src/`. Al tener ambos archivos funciones principales `setup()` y `loop()`, si ambos están dentro de `src/`, el enlazador arroja el error *multiple definition of setup / loop*. Al ubicarlo en `otro_proyecto_plantol/`, PlatformIO no lo compila y se mantiene a la mano con su extensión `.cpp` intacta.

---

## Cómo alternar entre ambos firmwares

### Para trabajar en PLANTA INTELIGENTE (Plantol BLE / Wi-Fi):
1. Mueve `src/main.cpp` a una carpeta de respaldo (o cámbiale el nombre a `main_complexnet.cpp.bak`).
2. Copia `otro_proyecto_plantol/planta_inteligente_ble_wifi.cpp` dentro de `src/main.cpp`.
3. Compila y flashea normalmente con PlatformIO.

### Para volver a COMPLEXNET (Malla distribuida):
1. Asegúrate de que en `src/` el único archivo sea `main.cpp` con el código de ComplexNet.
2. Compila y flashea normalmente.
