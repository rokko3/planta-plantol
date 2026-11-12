#!/usr/bin/env python3
"""
simulador_esp32.py
Simulador de Hardware ESP32 para el proyecto Plantol.
Responsabilidad técnica:
- Emula un sensor físico con microcontrolador ESP32 conectado a una red local.
- Adquiere mediciones físicas de sensores (luminosidad, humedad, temperatura).
- Transmite telemetría cruda vía HTTP POST a la API (/api/dispositivos/{id}/lecturas).
- NO CONTIENE REGLAS DE NEGOCIO NI TIPOS DE CASO:
  El simulador solo envía los datos físicos crudos del sensor.
  Toda la lógica de evaluación, salud y diagnóstico reside exclusivamente en el Modelo (MVC).
"""
import argparse
import datetime
import math
import random
import sys
import time
from typing import Any, Dict, List, Optional

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

# Identificadores de hardware estándar disponibles
DISPOSITIVOS_HARDWARE = [
    "ESP32-A7F9",
    "ESP32-C204",
    "ESP32-91B2",
    "ESP32-6D30",
]


def obtener_token_dispositivo(url_base: str, dispositivo_id: str) -> Optional[str]:
    """
    Obtiene automáticamente el token JWT del hardware desde el servidor.
    El usuario final no interviene en este proceso ni debe ingresar tokens manualmente.
    """
    url = f"{url_base.rstrip('/')}/api/dispositivos/{dispositivo_id}/token"
    try:
        resp = requests.post(url, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("token")
        print(f"{YELLOW}[AVISO]{RESET} No se pudo autenticar el hardware {dispositivo_id} ({resp.status_code}): {resp.text}")
    except Exception as exc:
        print(f"{RED}[ERROR CONEXION]{RESET} No se pudo conectar a {url}: {exc}")
    return None


def generar_lectura_sensores(paso: int) -> Dict[str, Any]:
    """
    Genera únicamente las mediciones físicas crudas adquiridas por los sensores.
    No incluye reglas de negocio, etiquetas de estado ni metadatos de diagnóstico.
    """
    now_iso = datetime.datetime.now().isoformat()
    t = paso * 0.15

    # Simulación de señales físicas analógicas de los sensores
    lux = 5000.0 + math.sin(t) * 1500 + random.uniform(-100, 100)
    hum = 45.0 + math.cos(t * 0.6) * 15 + random.uniform(-1.5, 1.5)
    temp = 23.5 + math.sin(t * 0.4) * 4.0 + random.uniform(-0.5, 0.5)

    return {
        "timestamp": now_iso,
        "luminosidad": round(max(0.0, lux), 1),
        "humedad": round(max(0.0, min(100.0, hum)), 1),
        "temperatura": round(temp, 1),
    }


def enviar_lectura(
    url_base: str,
    dispositivo_id: str,
    token: str,
    lectura: Dict[str, Any],
) -> None:
    """
    Envía únicamente los datos de telemetría física al puerto HTTP del servidor.
    El simulador no interpreta la salud de la planta ni evalúa diagnósticos.
    """
    url = f"{url_base.rstrip('/')}/api/dispositivos/{dispositivo_id}/lecturas"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        inicio = time.time()
        resp = requests.post(url, json=lectura, headers=headers, timeout=5)
        duracion_ms = (time.time() - inicio) * 1000
        hora = datetime.datetime.now().strftime("%H:%M:%S")

        if resp.status_code == 201:
            print(
                f"[{hora}] {CYAN}{dispositivo_id}{RESET} -> "
                f"Lectura enviada -> "
                f"Luz: {lectura['luminosidad']} lux | "
                f"Humedad: {lectura['humedad']}% | "
                f"Temp: {lectura['temperatura']}°C "
                f"| HTTP {GREEN}{resp.status_code} Creado{RESET} ({duracion_ms:.0f}ms)"
            )
        elif resp.status_code == 202:
            print(
                f"[{hora}] {CYAN}{dispositivo_id}{RESET} -> "
                f"Lectura enviada -> "
                f"HTTP {YELLOW}202 Aceptado{RESET} (Sensor en red pero desvinculado / sin planta asignada)"
            )
        elif resp.status_code == 400:
            print(
                f"[{hora}] {CYAN}{dispositivo_id}{RESET} -> "
                f"HTTP {YELLOW}{resp.status_code} Rechazado por Servidor{RESET} ({resp.json().get('error', 'Error')})"
            )
        elif resp.status_code in (401, 403):
            print(
                f"[{hora}] {RED}[AUTENTICACION HARDWARE {resp.status_code}]{RESET} {resp.json().get('mensaje')}"
            )
        else:
            print(f"[{hora}] {dispositivo_id} -> HTTP {resp.status_code}: {resp.text}")

    except Exception as exc:
        print(f"{RED}[ERROR TRANSMISION]{RESET} {dispositivo_id} error de red: {exc}")


def main():
    parser = argparse.ArgumentParser(
        description="Simulador de Hardware ESP32 para Plantol (Capa de Sensores IoT)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python simulador_esp32.py --intervalo 3
  python simulador_esp32.py --dispositivo ESP32-A7F9 --intervalo 2
  python simulador_esp32.py --multi --intervalo 3
  python simulador_esp32.py --conteo 5
        """,
    )
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="URL base de la API Flask")
    parser.add_argument("--dispositivo", default="ESP32-A7F9", help="ID del dispositivo a emular")
    parser.add_argument("--token", default=None, help="Token JWT de dispositivo (obtenido automáticamente si se omite)")
    parser.add_argument("--intervalo", type=float, default=3.0, help="Segundos entre lecturas (default: 3.0)")
    parser.add_argument("--multi", action="store_true", help="Simula todos los dispositivos ESP32 registrados")
    parser.add_argument("--conteo", type=int, default=0, help="Cantidad de lecturas a enviar (0 = continuo)")

    args = parser.parse_args()

    dispositivos: List[str] = (
        DISPOSITIVOS_HARDWARE if args.multi else [args.dispositivo.strip().upper()]
    )

    print("=" * 65)
    print("Plantol - Simulador de Hardware ESP32 (Capa de Sensores IoT)")
    print(f"API Destino:        {args.url}")
    print(f"Intervalo de envío: {args.intervalo} segundos")
    print(f"Dispositivos:       {', '.join(dispositivos)}")
    print("Arquitectura:       El hardware solo envía datos crudos al puerto.")
    print("                    Toda regla de negocio y salud reside en el Modelo.")
    print("=" * 65)

    tokens = {}
    for dev_id in dispositivos:
        token = args.token or obtener_token_dispositivo(args.url, dev_id)
        if not token:
            print(
                f"[ERROR CRÍTICO] No se pudo autenticar el dispositivo '{dev_id}'. "
                "Asegúrate de que el servidor esté activo (`python app.py`)."
            )
            sys.exit(1)
        tokens[dev_id] = token
        print(f"[*] Hardware '{dev_id}' conectado y autenticado automáticamente.")

    print("\n[+] Transmitiendo telemetría de sensores a la API... (Ctrl+C para detener)\n")

    paso = 0
    enviados = 0
    try:
        while True:
            paso += 1
            for dev_id in dispositivos:
                lectura = generar_lectura_sensores(paso)
                enviar_lectura(args.url, dev_id, tokens[dev_id], lectura)
                enviados += 1
                if args.conteo > 0 and enviados >= args.conteo:
                    print(f"\n[OK] Finalizado el envío de {enviados} lecturas.")
                    return

            time.sleep(args.intervalo)

    except KeyboardInterrupt:
        print(f"\n[STOP] Simulador detenido por el usuario. Total lecturas enviadas: {enviados}")


if __name__ == "__main__":
    main()
