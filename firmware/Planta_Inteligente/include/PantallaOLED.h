#ifndef PANTALLA_OLED_H
#define PANTALLA_OLED_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

/**
 * ============================================================================
 * Módulo OLED 1.3" SH1106 (128x64 I2C) para Gamificación de Plantol.
 * Conectado al bus I2C: SDA GPIO 8, SCL GPIO 9, alimentación 3.3V.
 * ============================================================================
 */
#define ANCHO_OLED 128
#define ALTO_OLED  64
#define OLED_RESET -1

inline Adafruit_SH1106G& obtenerDisplayOLED() {
    static Adafruit_SH1106G display(ANCHO_OLED, ALTO_OLED, &Wire, OLED_RESET);
    return display;
}

inline bool& oledDisponibleFlag() {
    static bool disponible = false;
    return disponible;
}

class PantallaOLED {
public:
    static bool inicializar() {
        Adafruit_SH1106G& display = obtenerDisplayOLED();
        // Intentar dirección estándar 0x3C y alternativa 0x3D
        if (display.begin(0x3C, true)) {
            oledDisponibleFlag() = true;
            Serial.println("[OLED] Pantalla SH1106 1.3\" detectada en 0x3C.");
        } else if (display.begin(0x3D, true)) {
            oledDisponibleFlag() = true;
            Serial.println("[OLED] Pantalla SH1106 1.3\" detectada en 0x3D.");
        } else {
            oledDisponibleFlag() = false;
            Serial.println("[OLED][WARN] No se detectó pantalla OLED SH1106 en 0x3C ni 0x3D.");
            return false;
        }

        display.clearDisplay();
        display.setTextColor(SH110X_WHITE);
        dibujarCara(display, "RADIANTE", 26, 36);
        display.setTextSize(1);
        display.setCursor(56, 16);
        display.println("PLANTOL");
        display.setCursor(56, 28);
        display.println("Iniciando");
        display.setCursor(56, 40);
        display.println("sensores...");
        display.display();
        return true;
    }

    static void mostrarConfigBLE(
        const String& mac,
        const String& estadoBle,
        float temp = NAN,
        float humSuelo = 0,
        float luz = 0
    ) {
        if (!oledDisponibleFlag()) return;
        Adafruit_SH1106G& display = obtenerDisplayOLED();
        display.clearDisplay();

        dibujarCara(display, "BLE", 26, 36);

        display.setTextColor(SH110X_WHITE);
        display.setTextSize(1);
        display.setCursor(54, 2);
        display.println("MODO BLE");
        display.drawLine(54, 11, 127, 11, SH110X_WHITE);

        display.setCursor(54, 14);
        display.print("ID:");
        display.println(mac.length() >= 6 ? mac.substring(mac.length() - 6) : mac);

        display.setCursor(54, 24);
        String est = estadoBle;
        if (est.length() > 12) est = est.substring(0, 12);
        display.println(est);

        // Mostrar lecturas en vivo incluso antes de vincular Wi-Fi
        display.drawLine(54, 34, 127, 34, SH110X_WHITE);
        display.setCursor(54, 37);
        display.print("T:");
        if (isnan(temp)) display.print("--");
        else { display.print(temp, 1); display.print("C"); }

        display.setCursor(54, 46);
        display.print("S:");
        display.print((int)humSuelo);
        display.print("%");

        display.setCursor(54, 55);
        display.print("L:");
        display.print((int)luz);
        display.print("lx");

        display.display();
    }

    static void mostrarGamificacion(
        const String& emocion,
        int hp,
        float temp,
        float humSuelo,
        float luz,
        bool wifiOk
    ) {
        if (!oledDisponibleFlag()) return;
        Adafruit_SH1106G& display = obtenerDisplayOLED();
        display.clearDisplay();

        dibujarCara(display, emocion, 26, 36);

        display.setTextColor(SH110X_WHITE);
        display.setTextSize(1);

        String titulo = emocion;
        titulo.toUpperCase();
        if (titulo.length() > 11) titulo = titulo.substring(0, 11);
        display.setCursor(56, 2);
        display.println(titulo);

        int barraAncho = map(constrain(hp, 0, 100), 0, 100, 0, 44);
        display.drawRect(56, 12, 46, 6, SH110X_WHITE);
        if (barraAncho > 0) {
            display.fillRect(57, 13, barraAncho, 4, SH110X_WHITE);
        }
        display.setCursor(105, 11);
        display.print(hp);

        display.drawLine(56, 21, 127, 21, SH110X_WHITE);

        display.setCursor(56, 25);
        display.print("T: ");
        if (isnan(temp)) display.print("--");
        else { display.print(temp, 1); display.print("C"); }

        display.setCursor(56, 35);
        display.print("S: ");
        display.print((int)humSuelo);
        display.print("%");

        display.setCursor(56, 45);
        display.print("L: ");
        display.print((int)luz);
        display.print("lx");

        display.setCursor(56, 56);
        display.print(wifiOk ? "WiFi: OK" : "WiFi: --");

        display.display();
    }

    static void mostrarMensaje(const String& linea1, const String& linea2) {
        if (!oledDisponibleFlag()) return;
        Adafruit_SH1106G& display = obtenerDisplayOLED();
        display.clearDisplay();
        display.setTextColor(SH110X_WHITE);
        display.setTextSize(1);
        display.setCursor(4, 18);
        display.println(linea1);
        display.setCursor(4, 34);
        display.println(linea2);
        display.display();
    }

private:
    static void dibujarBrote(Adafruit_SH1106G& d, int cx, int topY) {
        d.drawLine(cx, topY, cx, topY - 7, SH110X_WHITE);
        d.fillCircle(cx - 4, topY - 7, 3, SH110X_WHITE);
        d.fillCircle(cx + 4, topY - 8, 3, SH110X_WHITE);
    }

    static void dibujarCara(Adafruit_SH1106G& d, const String& emocionRaw, int cx, int cy) {
        String e = emocionRaw;
        e.toUpperCase();

        const int r = 22;
        d.drawCircle(cx, cy, r, SH110X_WHITE);
        dibujarBrote(d, cx, cy - r);

        if (e.indexOf("PELIGRO") >= 0 || e.indexOf("CRITICO") >= 0) {
            d.drawLine(cx - 11, cy - 8, cx - 5, cy - 2, SH110X_WHITE);
            d.drawLine(cx - 5,  cy - 8, cx - 11, cy - 2, SH110X_WHITE);
            d.drawLine(cx + 5,  cy - 8, cx + 11, cy - 2, SH110X_WHITE);
            d.drawLine(cx + 11, cy - 8, cx + 5,  cy - 2, SH110X_WHITE);
            d.drawCircle(cx, cy + 12, 6, SH110X_WHITE);
            d.fillRect(cx - 7, cy + 12, 15, 7, SH110X_BLACK);
        } else if (e.indexOf("SEDIENTA") >= 0) {
            d.fillCircle(cx - 8, cy - 5, 3, SH110X_WHITE);
            d.fillCircle(cx + 8, cy - 5, 3, SH110X_WHITE);
            d.drawLine(cx - 12, cy - 10, cx - 5, cy - 8, SH110X_WHITE);
            d.drawLine(cx + 5,  cy - 8,  cx + 12, cy - 10, SH110X_WHITE);
            d.fillTriangle(cx + 14, cy - 1, cx + 12, cy + 4, cx + 16, cy + 4, SH110X_WHITE);
            d.drawLine(cx - 7, cy + 9, cx - 2, cy + 6, SH110X_WHITE);
            d.drawLine(cx - 2, cy + 6, cx + 2, cy + 9, SH110X_WHITE);
            d.drawLine(cx + 2, cy + 9, cx + 7, cy + 6, SH110X_WHITE);
        } else if (e.indexOf("ACALORADA") >= 0) {
            d.drawLine(cx - 11, cy - 8, cx - 6, cy - 5, SH110X_WHITE);
            d.drawLine(cx - 6,  cy - 5, cx - 11, cy - 2, SH110X_WHITE);
            d.drawLine(cx + 11, cy - 8, cx + 6, cy - 5, SH110X_WHITE);
            d.drawLine(cx + 6,  cy - 5, cx + 11, cy - 2, SH110X_WHITE);
            d.drawRoundRect(cx - 5, cy + 4, 10, 7, 3, SH110X_WHITE);
            d.fillCircle(cx + 15, cy - 10, 2, SH110X_WHITE);
        } else if (e.indexOf("FRIO") >= 0 || e.indexOf("FRÍO") >= 0) {
            d.fillCircle(cx - 8, cy - 5, 2, SH110X_WHITE);
            d.fillCircle(cx + 8, cy - 5, 2, SH110X_WHITE);
            for (int x = -8; x < 8; x += 4) {
                d.drawLine(cx + x, cy + 7, cx + x + 2, cy + 10, SH110X_WHITE);
                d.drawLine(cx + x + 2, cy + 10, cx + x + 4, cy + 7, SH110X_WHITE);
            }
        } else if (e.indexOf("DURMIENDO") >= 0) {
            d.drawLine(cx - 11, cy - 4, cx - 5, cy - 4, SH110X_WHITE);
            d.drawLine(cx + 5,  cy - 4, cx + 11, cy - 4, SH110X_WHITE);
            d.drawCircle(cx, cy + 7, 2, SH110X_WHITE);
            d.setTextSize(1);
            d.setCursor(cx + 12, cy - 18);
            d.print("zZ");
        } else if (e.indexOf("BLE") >= 0) {
            d.drawCircle(cx - 8, cy - 5, 3, SH110X_WHITE);
            d.drawCircle(cx + 8, cy - 5, 3, SH110X_WHITE);
            d.fillCircle(cx - 7, cy - 5, 1, SH110X_WHITE);
            d.fillCircle(cx + 9, cy - 5, 1, SH110X_WHITE);
            d.drawLine(cx - 5, cy + 7, cx + 5, cy + 7, SH110X_WHITE);
        } else {
            d.fillCircle(cx - 8, cy - 6, 3, SH110X_WHITE);
            d.fillCircle(cx + 8, cy - 6, 3, SH110X_WHITE);
            d.drawPixel(cx - 9, cy - 7, SH110X_BLACK);
            d.drawPixel(cx + 7, cy - 7, SH110X_BLACK);
            d.drawLine(cx - 14, cy + 1, cx - 11, cy + 1, SH110X_WHITE);
            d.drawLine(cx + 11, cy + 1, cx + 14, cy + 1, SH110X_WHITE);
            d.drawCircle(cx, cy + 3, 8, SH110X_WHITE);
            d.fillRect(cx - 9, cy - 6, 19, 10, SH110X_BLACK);
            d.fillCircle(cx - 8, cy - 6, 3, SH110X_WHITE);
            d.fillCircle(cx + 8, cy - 6, 3, SH110X_WHITE);
            d.drawPixel(cx - 9, cy - 7, SH110X_BLACK);
            d.drawPixel(cx + 7, cy - 7, SH110X_BLACK);
        }
    }
};

#endif // PANTALLA_OLED_H
