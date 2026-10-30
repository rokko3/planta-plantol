#!/usr/bin/env python3
"""
simulador_esp32.py
Simulador de Hardware ESP32 para el proyecto Plantol (Fase 2).
Cumple los Requisitos R2, R3 y R7:
- Script independiente en Python
- Envía lecturas periódicas a POST /api/dispositivos/{id}/lecturas
- Intervalo configurable
- Genera valores en rango, valores fuera de rango y datos inválidos para probar la robustez
- Autenticado mediante JWT con alcance 'dispositivo'
"""
import argparse
import datetime
import math
import random
import sys
import time
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    print("Error: Se requiere la librería 'requests'. Ejecuta: pip install requests")
    sys.exit(1)

# Paleta ANSI para terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Perfiles de simulación de dispositivos
PERFILES_DISPOSITIVOS = {
    "ESP32-A7F9": {
        "nombre": "Cactus de escritorio",
        "especie": "Cactus (Cactaceae)",
        "lux_base": 7000.0,
        "hum_base": 22.0,
        "temp_base": 25.0,
    },
    "ESP32-C204": {
        "nombre": "Helecho de la ventana",
        "especie": "Helecho (Nephrolepis)",
        "lux_base": 4500.0,
        "hum_base": 68.0,
        "temp_base": 22.0,
    },
    "ESP32-91B2": {
        "nombre": "Orquídea morada",
        "especie": "Orquídea (Orchidaceae)",
        "lux_base": 2000.0,
        "hum_base": 62.0,
        "temp_base": 24.0,
    },
    "ESP32-6D30": {
        "nombre": "Monstera pequeña",
        "especie": "Monstera (Monstera deliciosa)",
        "lux_base": 5000.0,
        "hum_base": 65.0,
        "temp_base": 23.0,
    },
}


def obtener_token_dispositivo(url_base: str, dispositivo_id: str) -> Optional[str]:
    """Obtiene el token JWT de dispositivo desde la API."""
    url = f"{url_base.rstrip('/')}/api/dispositivos/{dispositivo_id}/token"
    try:
        resp = requests.post(url, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("token")
        print(f"{YELLOW}[AVISO]{RESET} No se pudo obtener token automático ({resp.status_code}): {resp.text}")
    except Exception as exc:
        print(f"{RED}[ERROR CONEXION]{RESET} No se pudo conectar a {url}: {exc}")
    return None


def generar_lectura(
    dispositivo_id: str,
    modo: str,
    paso: int,
) -> Dict[str, Any]:
    """Genera datos de telemetría según el perfil y el modo solicitado."""
    perfil = PERFILES_DISPOSITIVOS.get(
        dispositivo_id,
        {"lux_base": 4000.0, "hum_base": 50.0, "temp_base": 22.0},
    )

    now_iso = datetime.datetime.now().isoformat()
    t = paso * 0.2

    # Fluctuación natural
    lux = perfil["lux_base"] + math.sin(t) * 350 + random.uniform(-100, 100)
    hum = perfil["hum_base"] + math.cos(t * 0.7) * 4 + random.uniform(-1.5, 1.5)
    temp = perfil["temp_base"] + math.sin(t * 0.5) * 2 + random.uniform(-0.5, 0.5)

    tipo_caso = "NORMAL"

    if modo == "invalido" or (modo == "mixto" and paso % 15 == 0):
        # Generar dato físicamente inválido para probar robustez y manejo de error 400
        tipo_caso = "INVALIDO"
        variante = paso % 3
        if variante == 0:
            hum = -25.0  # Humedad negativa imposible
        elif variante == 1:
            temp = 145.0  # Temperatura destructiva fuera de rango físico
        else:
            lux = -500.0  # Luminosidad negativa

    elif modo == "fuera_rango" or (modo == "mixto" and paso % 5 == 0):
        # Generar dato fuera de rango de la especie para provocar alerta
        tipo_caso = "FUERA_DE_RANGO"
        if "Cactus" in perfil.get("nombre", ""):
            hum = 75.0  # Cactus ahogado
        elif "Orquídea" in perfil.get("nombre", ""):
            temp = 34.0  # Orquídea sofocada
            hum = 90.0
        else:
            lux = 400.0  # Luz muy baja

    return {
        "timestamp": now_iso,
        "luminosidad": round(lux, 1),
        "humedad": round(hum, 1),
        "temperatura": round(temp, 1),
        "_tipo_caso": tipo_caso,
    }


def enviar_lectura(
    url_base: str,
    dispositivo_id: str,
    token: str,
    lectura: Dict[str, Any],
) -> None:
    """Envía la lectura a la API con la cabecera JWT."""
    url = f"{url_base.rstrip('/')}/api/dispositivos/{dispositivo_id}/lecturas"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    tipo_caso = lectura.pop("_tipo_caso", "NORMAL")

    try:
        inicio = time.time()
        resp = requests.post(url, json=lectura, headers=headers, timeout=5)
        duracion_ms = (time.time() - inicio) * 1000

        hora = datetime.datetime.now().strftime("%H:%M:%S")

        if resp.status_code == 201:
            data = resp.json()
            estado = data.get("diagnostico", {}).get("estado_global", "DESCONOCIDO")
            color_estado = GREEN if estado == "SALUDABLE" else (YELLOW if estado == "EN_RIESGO" else RED)

            print(
                f"[{hora}] {CYAN}{dispositivo_id}{RESET} -> "
                f"Luz: {lectura['luminosidad']} lux | "
                f"Hum: {lectura['humedad']}% | "
                f"Temp: {lectura['temperatura']}°C "
                f"| HTTP {GREEN}{resp.status_code}{RESET} ({duracion_ms:.0f}ms) "
                f"| Estado: {color_estado}{BOLD}{estado}{RESET}"
            )
        elif resp.status_code == 400:
            # Caso de prueba de robustez exitoso: el backend rechazó la lectura inválida correctamente
            print(
                f"[{hora}] {CYAN}{dispositivo_id}{RESET} -> "
                f"Dato [{tipo_caso}] -> "
                f"Luz: {lectura['luminosidad']} | Hum: {lectura['humedad']} | Temp: {lectura['temperatura']} "
                f"| HTTP {YELLOW}{resp.status_code}{RESET} (Robustez comprobada: {resp.json().get('error')})"
            )
        elif resp.status_code == 202:
            print(
                f"[{hora}] {CYAN}{dispositivo_id}{RESET} -> "
                f"HTTP {YELLOW}202 Aceptado{RESET} (Dispositivo registrado pero no vinculado a planta)"
            )
        elif resp.status_code == 401 or resp.status_code == 403:
            print(
                f"[{hora}] {RED}[ERROR AUTENTICACIÓN {resp.status_code}]{RESET} {resp.json().get('mensaje')}"
            )
        else:
            print(f"[{hora}] {dispositivo_id} -> HTTP {resp.status_code}: {resp.text}")

    except Exception as exc:
        print(f"{RED}[ERROR ENVÍO]{RESET} {dispositivo_id} fallo de red: {exc}")


def main():
    parser = argparse.ArgumentParser(
        description="Simulador de telemetría ESP32 para Plantol (Fase 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python simulador_esp32.py --intervalo 3
  python simulador_esp32.py --dispositivo ESP32-91B2 --modo fuera_rango
  python simulador_esp32.py --multi --intervalo 2
  python simulador_esp32.py --modo invalido --conteo 5
        """,
    )
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="URL base de la API Flask")
    parser.add_argument("--dispositivo", default="ESP32-A7F9", help="ID del dispositivo a simular")
    parser.add_argument("--token", default=None, help="Token JWT de dispositivo (si se omite, se solicita a la API)")
    parser.add_argument("--intervalo", type=float, default=3.0, help="Segundos entre lecturas (default: 3.0)")
    parser.add_argument(
        "--modo",
        choices=["mixto", "normal", "fuera_rango", "invalido"],
        default="mixto",
        help="Modo de generación de datos (default: mixto)",
    )
    parser.add_argument("--multi", action="store_true", help="Simula todos los dispositivos ESP32 registrados")
    parser.add_argument("--conteo", type=int, default=0, help="Cantidad de lecturas a enviar (0 = infinito)")

    args = parser.parse_args()

    dispositivos = (
        list(PERFILES_DISPOSITIVOS.keys())
        if args.multi
        else [args.dispositivo.strip().upper()]
    )

    print("=" * 65)
    print(f"Plantol - Simulador de Hardware ESP32 (Fase 2)")
    print(f"API destino:       {args.url}")
    print(f"Intervalo:         {args.intervalo} segundos")
    print(f"Modo de prueba:    {args.modo.upper()}")
    print(f"Dispositivos:      {', '.join(dispositivos)}")
    print("=" * 65)

    tokens = {}
    for dev_id in dispositivos:
        token = args.token or obtener_token_dispositivo(args.url, dev_id)
        if not token:
            print(
                f"[ERROR CRITICO] No se pudo obtener token JWT para '{dev_id}'. "
                "Asegúrate de que el servidor Flask esté corriendo (`python app.py`)."
            )
            sys.exit(1)
        tokens[dev_id] = token
        print(f"[*] Token JWT asignado para {dev_id}: {token[:20]}...{token[-10:]}")

    print("\n[+] Iniciando transmision de telemetria... (Presiona Ctrl+C para detener)\n")

    paso = 0
    enviados = 0
    try:
        while True:
            paso += 1
            for dev_id in dispositivos:
                lectura = generar_lectura(dev_id, args.modo, paso)
                enviar_lectura(args.url, dev_id, tokens[dev_id], lectura)
                enviados += 1
                if args.conteo > 0 and enviados >= args.conteo:
                    print(f"\n[OK] Se completo el envio de {enviados} lecturas programadas.")
                    return

            time.sleep(args.intervalo)

    except KeyboardInterrupt:
        print(f"\n[STOP] Simulador detenido por el usuario. Total lecturas enviadas: {enviados}")


if __name__ == "__main__":
    main()
