/**
 * Plantol — Lógica Asíncrona del Frontend (app.js)
 * Cumple los Requisitos:
 * - R1: Diagnóstico manual consumiendo POST /api/diagnostico
 * - R4: Identificación visual de la fuente activa (CSV o BD) desde /api/config/fuente
 * - R5: Consulta y visualización del historial de lecturas por planta (/api/plantas/<id>/historial)
 * - R6: Actualización periódica en vivo (polling cada 3.5s) sin recargar toda la página
 * - R7: Manejo de autenticación JWT de usuario (localStorage, cabecera Bearer, scopes)
 */

const API_BASE = ""; // Rutas relativas para funcionar en cualquier host/puerto
let authToken = localStorage.getItem("plantol_token") || null;
let currentUser = JSON.parse(localStorage.getItem("plantol_user") || "null");
let especiesDisponibles = [];
let pollingTimer = null;
let currentModalPlantaId = null;
let dispositivoBleSeleccionado = null;

// ==========================================================================
// 1. Inicialización y Navegación
// ==========================================================================

document.addEventListener("DOMContentLoaded", async () => {
  // 1. Si no hay sesión previa, autenticar automáticamente al usuario demo 'felipe'
  if (!authToken || !currentUser) {
    await autoLoginDemo();
  } else {
    actualizarVistaUsuario();
  }

  // 2. Cargar metadatos iniciales
  await cargarFuenteConfig();
  await cargarEspecies();
  await cargarDispositivosSelect();

  // 3. Sincronizar dashboard y arrancar el ciclo de actualización asíncrona (R6)
  await sincronizarDashboard();
  iniciarPollingAsincrono();
});

function navegar(paginaId) {
  // Actualizar botones de navegación
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.page === paginaId);
  });

  // Actualizar secciones visibles
  document.querySelectorAll(".page-section").forEach(sec => {
    sec.classList.toggle("active", sec.id === `page-${paginaId}`);
  });

  // Títulos dinámicos de cabecera
  const titulos = {
    "dashboard": ["Mis Plantas", "Supervisión en tiempo real de tu invernadero"],
    "nueva-planta": ["Agregar Planta", "Registra un nuevo ejemplar en tu colección"],
    "vincular": ["Aprovisionar y Vincular ESP32", "Conexión Bluetooth GATT y vinculación de sensores en red"],
    "cuenta": ["Cuenta y Acceso", "Administración de identidad y reglas de propiedad"],
  };

  if (titulos[paginaId]) {
    document.getElementById("pageTitle").textContent = titulos[paginaId][0];
    document.getElementById("pageSubtitle").textContent = titulos[paginaId][1];
  }

  if (paginaId === "vincular") {
    actualizarSelectPlantasVincular();
    cargarDispositivosDisponibles();
  }
}

// ==========================================================================
// 2. Peticiones HTTP Asíncronas con JWT (R7)
// ==========================================================================

async function apiFetch(endpoint, opciones = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(opciones.headers || {}),
  };

  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  try {
    const respuesta = await fetch(`${API_BASE}${endpoint}`, {
      ...opciones,
      headers,
    });

    const data = await respuesta.json().catch(() => ({}));
    return {
      ok: respuesta.ok,
      status: respuesta.status,
      data,
    };
  } catch (error) {
    console.error(`Error de red al conectar con ${endpoint}:`, error);
    actualizarIndicadorConexion(false);
    return { ok: false, status: 0, data: { mensaje: "Error de conexión con el servidor Flask" } };
  }
}

// ==========================================================================
// 3. Autenticación y Cuentas (R7)
// ==========================================================================

async function autoLoginDemo() {
  const res = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username: "felipe", password: "plantol123" }),
  });

  if (res.ok) {
    guardarSesion(res.data.token, res.data.usuario);
  }
}

function guardarSesion(token, usuario) {
  authToken = token;
  currentUser = usuario;
  localStorage.setItem("plantol_token", token);
  localStorage.setItem("plantol_user", JSON.stringify(usuario));
  actualizarVistaUsuario();
  actualizarIndicadorConexion(true);
}

function cerrarSesion() {
  authToken = null;
  currentUser = null;
  localStorage.removeItem("plantol_token");
  localStorage.removeItem("plantol_user");
  mostrarToast("Sesión cerrada.");
  navegar("cuenta");
  actualizarVistaUsuario();
}

function actualizarVistaUsuario() {
  if (currentUser) {
    document.getElementById("userNameDisplay").textContent = currentUser.nombre || currentUser.username;
    document.getElementById("userRoleDisplay").textContent = currentUser.rol || "Usuario";
    document.getElementById("userInitial").textContent = (currentUser.nombre || currentUser.username).charAt(0).toUpperCase();

    document.getElementById("profileNombre").textContent = currentUser.nombre;
    document.getElementById("profileUsername").textContent = currentUser.username;
    document.getElementById("profileId").textContent = currentUser.id;
    document.getElementById("tokenTextarea").value = authToken || "";
  } else {
    document.getElementById("userNameDisplay").textContent = "Sin autenticar";
    document.getElementById("userRoleDisplay").textContent = "Invitado";
    document.getElementById("userInitial").textContent = "?";
    document.getElementById("profileNombre").textContent = "--";
    document.getElementById("profileUsername").textContent = "--";
    document.getElementById("profileId").textContent = "--";
    document.getElementById("tokenTextarea").value = "";
  }
}

async function iniciarSesion(event) {
  event.preventDefault();
  const username = document.getElementById("inputAuthUser").value.trim();
  const password = document.getElementById("inputAuthPass").value.trim();

  const res = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

  if (res.ok) {
    guardarSesion(res.data.token, res.data.usuario);
    mostrarToast(`¡Bienvenido de nuevo, ${res.data.usuario.nombre}!`);
    await sincronizarDashboard();
    navegar("dashboard");
  } else {
    mostrarToast(`Error: ${res.data.mensaje || "Credenciales incorrectas"}`, "error");
  }
}

async function registrarNuevoUsuario() {
  const username = document.getElementById("inputAuthUser").value.trim();
  const password = document.getElementById("inputAuthPass").value.trim();

  if (!username || !password) {
    mostrarToast("Ingresa un usuario y contraseña para registrarte.", "warning");
    return;
  }

  const res = await apiFetch("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username,
      password,
      nombre: username.toUpperCase(),
      email: `${username}@ejemplo.com`,
    }),
  });

  if (res.ok) {
    guardarSesion(res.data.token, res.data.usuario);
    mostrarToast(`Cuenta creada para ${username}.`);
    await sincronizarDashboard();
    navegar("dashboard");
  } else {
    mostrarToast(`Error al registrar: ${res.data.mensaje}`, "error");
  }
}

function copiarToken() {
  const textarea = document.getElementById("tokenTextarea");
  if (!textarea.value) return;
  navigator.clipboard.writeText(textarea.value);
  mostrarToast("Token JWT copiado al portapapeles.");
}

// ==========================================================================
// 4. Configuración y Especies (R4)
// ==========================================================================

async function cargarFuenteConfig() {
  const res = await apiFetch("/api/config/fuente");
  if (res.ok) {
    const fuente = res.data.fuente_referencia.toUpperCase();
    document.getElementById("sourceName").textContent = fuente;
  }
}

async function cargarEspecies() {
  const res = await apiFetch("/api/especies");
  if (res.ok) {
    especiesDisponibles = res.data;
    const selectPlanta = document.getElementById("selectEspeciePlanta");
    if (!selectPlanta) return;

    selectPlanta.innerHTML = '<option value="">Selecciona una especie...</option>';
    especiesDisponibles.forEach(e => {
      const opt = document.createElement("option");
      opt.value = e.nombre;
      opt.textContent = e.nombre;
      selectPlanta.appendChild(opt);
    });
  }
}

async function cargarDispositivosSelect() {
  if (!authToken) return;
  const res = await apiFetch("/api/dispositivos/disponibles");
  if (res.ok) {
    const select = document.getElementById("selectDispositivoPlanta");
    if (!select) return;
    select.innerHTML = '<option value="">Sin dispositivo vinculado por ahora</option>';
    res.data.forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = `${d.id} · Wi-Fi (Disponible en Red)`;
      select.appendChild(opt);
    });
  }
}

// ==========================================================================
// 5. Sincronización y Actualización en Vivo (R6)
// ==========================================================================

function iniciarPollingAsincrono() {
  if (pollingTimer) clearInterval(pollingTimer);
  pollingTimer = setInterval(async () => {
    // Solo realiza polling si hay token y la página visible es el dashboard
    if (authToken && document.getElementById("page-dashboard").classList.contains("active")) {
      await sincronizarDashboard(false); // sin toast para no saturar
    }
  }, 3500);
}

async function sincronizarDashboard(notificar = false) {
  if (!authToken) return;

  const res = await apiFetch("/api/dashboard");
  if (!res.ok) {
    actualizarIndicadorConexion(false);
    return;
  }

  actualizarIndicadorConexion(true);
  const data = res.data;

  // Actualizar Métricas Globales (KPIs)
  document.getElementById("statTotalPlantas").textContent = data.stats.total_plantas;
  document.getElementById("statSensores").textContent = data.stats.sensores_conectados;
  document.getElementById("statSaludables").textContent = data.stats.en_buen_estado;
  document.getElementById("statAlertas").textContent = data.stats.alertas_pendientes;

  // Actualizar Saldo de Puntos en la barra superior
  const elPts = document.getElementById("topbarPuntosVal");
  if (elPts && data.stats && data.stats.saldo_puntos !== undefined) {
    elPts.textContent = data.stats.saldo_puntos;
  }

  // Actualizar Alertas
  renderizarAlertas(data.alertas || []);

  // Actualizar Tarjetas de Plantas
  renderizarPlantas(data.plantas || []);

  if (notificar) {
    mostrarToast("Dashboard actualizado.");
  }
}

function renderizarAlertas(alertas) {
  const container = document.getElementById("alertsContainer");
  if (!alertas || alertas.length === 0) {
    container.style.display = "none";
    container.innerHTML = "";
    return;
  }

  container.style.display = "flex";
  container.innerHTML = alertas.map(a => {
    const esCritico = a.tipo === "CRITICO";
    return `
      <div class="alert-banner ${esCritico ? 'critical' : ''}">
        <div class="alert-content">
          <strong>Alerta en ${a.planta} (${a.especie}): ${a.parametro} fuera de rango</strong>
          <p>Valor detectado: ${a.valor} · Recomendación: ${a.recomendacion}</p>
        </div>
      </div>
    `;
  }).join("");
}

function renderizarPlantas(plantas) {
  const grid = document.getElementById("plantsGrid");
  if (!plantas || plantas.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon"></span>
        <h3>No tienes plantas registradas</h3>
        <p>Ve a "Agregar Planta" para registrar tu primera planta en el sistema.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = plantas.map(p => {
    const estado = p.estado_global || "SIN_DATOS";
    const badgeClase = `badge-${estado.toLowerCase().replace("_", "-")}`;
    const lect = p.ultima_lectura || {};
    const diag = p.diagnostico || {};
    const parametros = diag.parametros || [];

    // Mapeo de estados de parámetros
    const getClsParam = (nombre) => {
      const match = parametros.find(x => x.nombre.toLowerCase() === nombre.toLowerCase());
      return match ? match.clasificacion.toLowerCase() : "optimo";
    };

    const tieneLectura = lect.luminosidad !== undefined && lect.luminosidad !== null;
    const horaFormateada = lect.timestamp ? formatearFecha(lect.timestamp) : "Sin lecturas aún";

    // Gamificación: HP y Emoción
    const hp = p.hp !== undefined ? p.hp : (diag.hp !== undefined ? diag.hp : 100);
    const hpClass = hp >= 70 ? "hp-high" : (hp >= 30 ? "hp-mid" : "hp-low");

    const emocion = p.estado_emocional || diag.estado_emocional || "RADIANTE";
    const emocionIconos = {
      "RADIANTE": "😊 Radiante",
      "SEDIENTA": "💧 Sedienta",
      "ACALORADA": "🥵 Acalorada",
      "CON FRÍO": "🥶 Con Frío",
      "DURMIENDO": "🌙 Durmiendo",
      "EN PELIGRO": "🥀 En Peligro"
    };
    const emocionTexto = emocionIconos[emocion] || `🌱 ${emocion}`;
    const emocionClase = `emocion-${emocion.toLowerCase().replace(/\s+/g, "-")}`;

    const tieneSuelo = lect.humedad_suelo !== undefined && lect.humedad_suelo !== null;

    return `
      <div class="plant-card">
        <div class="plant-card-top">
          <div class="plant-title">
            <h4>${p.nombre}</h4>
            <span class="plant-species">${p.especie}</span>
            <span class="plant-location">${p.ubicacion || "Ubicación general"}</span>
            <span class="badge-emocion ${emocionClase}" title="Estado Emocional">${emocionTexto}</span>
          </div>
          <span class="badge ${badgeClase}">${estado.replace("_", " ")}</span>
        </div>

        <!-- Barra de Salud (HP) -->
        <div class="hp-gauge">
          <div class="hp-info">
            <span>Salud Vital (HP)</span>
            <strong>${hp} / 100</strong>
          </div>
          <div class="hp-progress">
            <div class="hp-fill ${hpClass}" style="width: ${hp}%"></div>
          </div>
        </div>

        <div class="telemetry-row">
          <div class="telemetry-item">
            <span class="tel-label">Luz</span>
            <span class="tel-value">${tieneLectura ? Math.round(lect.luminosidad) : "--"}</span>
            <span class="tel-unit">lux</span>
            ${tieneLectura ? `<span class="tel-status ${getClsParam('luminosidad')}">${getClsParam('luminosidad').toUpperCase()}</span>` : ''}
          </div>
          <div class="telemetry-item">
            <span class="tel-label">Suelo</span>
            <span class="tel-value">${tieneSuelo ? lect.humedad_suelo.toFixed(0) : (tieneLectura ? "--" : "--")}</span>
            <span class="tel-unit">%</span>
            ${tieneSuelo ? `<span class="tel-status ${getClsParam('humedad_suelo')}">${getClsParam('humedad_suelo').toUpperCase()}</span>` : ''}
          </div>
          <div class="telemetry-item">
            <span class="tel-label">Temp</span>
            <span class="tel-value">${tieneLectura ? lect.temperatura.toFixed(1) : "--"}</span>
            <span class="tel-unit">°C</span>
            ${tieneLectura ? `<span class="tel-status ${getClsParam('temperatura')}">${getClsParam('temperatura').toUpperCase()}</span>` : ''}
          </div>
        </div>

        <div class="plant-card-footer">
          <span class="device-tag">
            Sensor: ${p.dispositivo_id ? p.dispositivo_id : "Sin ESP32"}
            ${p.dispositivo_id ? `<button type="button" class="btn-unlink-mini" title="Desvincular sensor" onclick="desvincularDispositivo(${p.id}, '${p.dispositivo_id}')">Desvincular</button>` : ''}
          </span>
          <span>${horaFormateada}</span>
        </div>

        <div class="plant-card-actions">
          ${p.ya_saludado_hoy
            ? `<button class="btn btn-sm btn-saludo-done" disabled title="Ya saludaste a esta planta hoy">✓ Saludada hoy</button>`
            : `<button class="btn btn-sm btn-saludo" onclick="saludarPlanta(${p.id})">👋 Saludar (+1 pt)</button>`
          }
          <button class="btn btn-secondary btn-sm" onclick="abrirModalHistorial(${p.id}, '${p.nombre}')">
            Historial
          </button>
          <button class="btn btn-sm btn-outline-danger" title="Eliminar planta de la base de datos" onclick="eliminarPlanta(${p.id}, '${p.nombre}')">
            Eliminar
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function actualizarIndicadorConexion(activo) {
  const dot = document.getElementById("liveDot");
  const text = document.getElementById("liveText");
  if (activo) {
    dot.className = "status-dot live";
    text.textContent = "Sincronización activa (3.5s)";
  } else {
    dot.className = "status-dot offline";
    text.textContent = "Conexión interrumpida";
  }
}

// ==========================================================================
// 6. Gestión de Plantas y Eliminación
// ==========================================================================

async function eliminarPlanta(plantaId, nombre) {
  if (!confirm(`¿Estás seguro de que deseas eliminar permanentemente la planta "${nombre}"?\n\n- Se eliminará su registro y lecturas de la base de datos.\n- Si tiene un sensor ESP32 vinculado, quedará desvinculado y libre en la red.`)) {
    return;
  }

  const res = await apiFetch(`/api/plantas/${plantaId}`, {
    method: "DELETE",
  });

  if (res.ok) {
    mostrarToast(`Planta "${nombre}" eliminada exitosamente.`);
    await sincronizarDashboard();
    await cargarDispositivosDisponibles();
    await cargarDispositivosSelect();
    await actualizarSelectPlantasVincular();
  } else {
    mostrarToast(`Error al eliminar planta: ${res.data.mensaje}`, "error");
  }
}

// ==========================================================================
// 7. Gestión de Plantas y Vinculación ESP32
// ==========================================================================

async function crearPlanta(event) {
  event.preventDefault();
  const nombre = document.getElementById("inputNombrePlanta").value.trim();
  const especie = document.getElementById("selectEspeciePlanta").value;
  const ubicacion = document.getElementById("inputUbicacionPlanta").value.trim();
  const dispositivo_id = document.getElementById("selectDispositivoPlanta").value || null;

  const res = await apiFetch("/api/plantas", {
    method: "POST",
    body: JSON.stringify({ nombre, especie, ubicacion, dispositivo_id }),
  });

  if (res.ok) {
    mostrarToast(`¡Planta '${nombre}' creada exitosamente!`);
    document.getElementById("formNuevaPlanta").reset();
    await sincronizarDashboard();
    navegar("dashboard");
  } else {
    mostrarToast(`Error al crear planta: ${res.data.mensaje}`, "error");
  }
}

async function actualizarSelectPlantasVincular() {
  if (!authToken) return;
  const res = await apiFetch("/api/plantas");
  if (res.ok) {
    const select = document.getElementById("selectPlantaVincular");
    if (select) {
      select.innerHTML = '<option value="">Selecciona tu Planta...</option>';
      res.data.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.nombre} (${p.especie}) - Actual: ${p.dispositivo_id || "Sin sensor"}`;
        select.appendChild(opt);
      });
    }

    const listaVinculados = document.getElementById("listaSensoresVinculados");
    if (listaVinculados) {
      const vinculadas = res.data.filter(p => p.dispositivo_id);
      if (vinculadas.length === 0) {
        listaVinculados.innerHTML = '<p class="text-muted text-sm">No tienes sensores vinculados a ninguna planta.</p>';
      } else {
        listaVinculados.innerHTML = vinculadas.map(p => `
          <div class="linked-device-item">
            <div>
              <strong>${p.nombre}</strong> <span class="text-muted">(${p.especie})</span>
              <div class="text-muted text-sm">Sensor: <code>${p.dispositivo_id}</code></div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm btn-danger-hover" onclick="desvincularDispositivo(${p.id}, '${p.dispositivo_id}')">
              Desvincular
            </button>
          </div>
        `).join("");
      }
    }
  }
}

async function desvincularDispositivo(plantaId, dispositivoId) {
  if (!confirm(`¿Deseas desvincular el sensor ${dispositivoId || ''} de esta planta? El dispositivo volverá a estar disponible en la red.`)) {
    return;
  }

  const res = await apiFetch("/api/dispositivos/desvincular", {
    method: "POST",
    body: JSON.stringify({ planta_id: plantaId, dispositivo_id: dispositivoId }),
  });

  if (res.ok) {
    mostrarToast(`Sensor ${dispositivoId || ''} desvinculado con éxito. Ahora está disponible en la red.`);
    await sincronizarDashboard();
    await cargarDispositivosDisponibles();
    await cargarDispositivosSelect();
    await actualizarSelectPlantasVincular();
  } else {
    mostrarToast(`Error al desvincular: ${res.data.mensaje}`, "error");
  }
}

// ==========================================================================
// 7. Bluetooth BLE real (Web Bluetooth API) — Aprovisionamiento GATT
// ==========================================================================

// UUIDs del servicio y característica GATT — deben coincidir con Planta_Inteligente
const BLE_SERVICE_UUID     = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
const BLE_CHAR_UUID        = "beb5483e-36e1-4688-b7f5-ea07361b26a8";
const BLE_CHAR_STATUS_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a9";
const BLE_DEVICE_NAME      = "Planta-Sensor-Config";

// Objeto de dispositivo BLE conectado (mantiene la conexión GATT activa)
let bleDevice     = null;
let bleServer     = null;
let bleCaracteristica = null;
let bleProvisioningCompletado = false;
let bleEnviandoCredenciales   = false;

/**
 * Verifica si el navegador soporta Web Bluetooth y si el contexto es seguro.
 * Web Bluetooth requiere Chrome/Edge y HTTPS (o http://localhost).
 */
function verificarSoporteBluetooth() {
  if (!navigator.bluetooth) {
    mostrarToast(
      "Tu navegador no soporta Web Bluetooth. Usa Google Chrome o Microsoft Edge.",
      "error"
    );
    return false;
  }
  if (location.protocol !== "https:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
    mostrarToast(
      "Web Bluetooth requiere HTTPS. Abre la aplicación en http://localhost:5000",
      "error"
    );
    return false;
  }
  return true;
}

/**
 * Lanza el diálogo nativo del sistema operativo para escanear y seleccionar
 * un dispositivo ESP32 BLE cercano. El usuario elige el dispositivo desde
 * la ventana del navegador (Chrome/Edge muestran los dispositivos visibles).
 *
 * Reemplaza la llamada simulada anterior a /api/dispositivos/bluetooth.
 */
async function iniciarEscaneoBluetooth() {
  if (!verificarSoporteBluetooth()) return;

  const btn        = document.getElementById("btnScanBle");
  const statusText = document.getElementById("bleScanStatus");
  const container  = document.getElementById("bleDevicesContainer");
  const list       = document.getElementById("bleDevicesList");

  btn.disabled    = true;
  btn.textContent = "Abriendo diálogo Bluetooth...";
  statusText.textContent = "Esperando que selecciones el dispositivo ESP32...";

  try {
    // Abre el diálogo nativo del SO para buscar dispositivos BLE.
    // Filtra por nombre exacto o por el UUID del servicio GATT del ESP32.
    bleDevice = await navigator.bluetooth.requestDevice({
      filters: [
        { name: BLE_DEVICE_NAME },
        { services: [BLE_SERVICE_UUID] }
      ],
      optionalServices: [BLE_SERVICE_UUID]
    });

    statusText.textContent = `Dispositivo seleccionado: ${bleDevice.name}`;
    mostrarToast(`ESP32 "${bleDevice.name}" seleccionado. Conectando...`);

    bleProvisioningCompletado = false;
    bleEnviandoCredenciales   = false;

    // Escuchar si el dispositivo se desconecta
    bleDevice.addEventListener("gattserverdisconnected", () => {
      if (bleProvisioningCompletado) {
        statusText.textContent = "✓ Wi-Fi configurado. Bluetooth cerrado automáticamente; ahora vincula tu planta a la derecha.";
        const listEl = document.getElementById("bleDevicesList");
        if (listEl) {
          const badge = listEl.querySelector(".badge");
          if (badge) badge.textContent = "En Red Wi-Fi";
        }
        bleDevice = null;
        bleServer = null;
        bleCaracteristica = null;
        return;
      }
      if (bleEnviandoCredenciales) {
        // El ESP32 cerró BLE para usar la antena en Wi-Fi mientras verificamos red
        statusText.textContent = "ESP32 conectando al Wi-Fi (BLE cerrado para liberar antena)...";
        bleDevice = null;
        bleServer = null;
        bleCaracteristica = null;
        return;
      }
      statusText.textContent = "Conexión Bluetooth perdida.";
      mostrarToast("El ESP32 se desconectó del Bluetooth.", "warning");
      ocultarPanelGatt();
    });

    // Conectar al servidor GATT del ESP32
    statusText.textContent = "Estableciendo conexión GATT...";
    bleServer = await bleDevice.gatt.connect();

    // Obtener el servicio y la característica de aprovisionamiento
    const servicio = await bleServer.getPrimaryService(BLE_SERVICE_UUID);
    bleCaracteristica = await servicio.getCharacteristic(BLE_CHAR_UUID);

    // Escuchar notificaciones de estado GATT del firmware ESP32
    try {
      const charStatus = await servicio.getCharacteristic(BLE_CHAR_STATUS_UUID);
      await charStatus.startNotifications();
      charStatus.addEventListener("characteristicvaluechanged", (e) => {
        const notif = new TextDecoder().decode(e.target.value);
        console.log(`[BLE GATT Notificación] ${notif}`);
        if (notif === "ERROR_WIFI") {
          mostrarToast("El ESP32 no pudo conectar a Wi-Fi. Verifica SSID y contraseña.", "error");
        } else if (notif === "CONECTANDO_WIFI") {
          mostrarToast("ESP32: Conectando a la red Wi-Fi...", "info");
        } else if (notif === "VINCULADO") {
          mostrarToast("¡ESP32: Conexión exitosa y vinculado en red!", "success");
        }
      });
    } catch (e) {
      console.warn("[BLE] Notificaciones GATT opcionales no suscritas:", e);
    }

    // Mostrar el ESP32 seleccionado en la lista de la UI
    container.style.display = "block";
    list.innerHTML = "";
    const item = document.createElement("div");
    item.className = "ble-device-item";
    item.innerHTML = `
      <div class="ble-device-info">
        <div class="ble-device-title">
          <strong>${bleDevice.name}</strong>
          <span class="badge badge-saludable">Conectado</span>
        </div>
        <div class="ble-device-meta">
          <span>Servicio GATT activo</span>
          <span class="rssi-pill">Listo para provisionar</span>
        </div>
      </div>
      <button type="button" class="btn btn-primary btn-sm" onclick="mostrarPanelGatt()">
        Enviar Credenciales Wi-Fi
      </button>
    `;
    list.appendChild(item);

    statusText.textContent = `✓ Conexión GATT establecida con "${bleDevice.name}"`;
    mostrarToast(`¡Conectado por Bluetooth a ${bleDevice.name}! Ahora envía las credenciales Wi-Fi.`);

  } catch (err) {
    if (err.name === "NotFoundError") {
      statusText.textContent = "Ningún dispositivo seleccionado.";
      mostrarToast("No se seleccionó ningún ESP32.", "warning");
    } else if (err.name === "SecurityError") {
      mostrarToast("Se necesita un contexto seguro (HTTPS o localhost).", "error");
    } else {
      statusText.textContent = `Error: ${err.message}`;
      mostrarToast(`Error Bluetooth: ${err.message}`, "error");
      console.error("[BLE] Error al escanear:", err);
    }
  } finally {
    btn.disabled    = false;
    btn.textContent = "Escanear Dispositivos Bluetooth (BLE)";
  }
}

/** Muestra el panel de envío de credenciales GATT */
function mostrarPanelGatt() {
  const panel = document.getElementById("panelGattConfig");
  const lbl   = document.getElementById("lblBleDevConectado");
  if (bleDevice) lbl.textContent = `${bleDevice.name}`;
  document.getElementById("statusGatt").style.display = "none";
  panel.style.display = "block";
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/** Oculta el panel GATT al perder conexión */
function ocultarPanelGatt() {
  document.getElementById("panelGattConfig").style.display = "none";
  bleDevice = null;
  bleServer = null;
  bleCaracteristica = null;
}

// Alias de compatibilidad (llamado desde el botón "Conectar por Bluetooth")
function conectarDispositivoBle() {
  mostrarPanelGatt();
}

/**
 * Envía las credenciales Wi-Fi DIRECTAMENTE al ESP32 mediante BLE GATT.
 *
 * Escribe en la característica de aprovisionamiento la cadena:
 *   SSID|PASSWORD|TOKEN_PAIRING
 *
 * El ESP32 recibe esto en su callback onWrite y:
 *   1. Apaga BLE
 *   2. Conecta al Wi-Fi
 *   3. Llama al backend para vincularse con el token
 *
 * Esta función NO llama a ningún endpoint del servidor — la escritura
 * es punto a punto entre el navegador y el ESP32 vía Bluetooth.
 */
async function enviarCredencialesGatt(event) {
  if (event) event.preventDefault();

  if (!bleCaracteristica || !bleDevice || !bleDevice.gatt.connected) {
    mostrarToast("No hay conexión BLE activa. Escanea y selecciona el ESP32 primero.", "warning");
    return;
  }

  const ssid      = document.getElementById("inputWifiSsid").value.trim();
  const password  = document.getElementById("inputWifiPass").value.trim();
  const btn       = document.getElementById("btnEnviarGatt");
  const statusBox = document.getElementById("statusGatt");

  if (!ssid) {
    mostrarToast("Ingresa el nombre de la red Wi-Fi (SSID).", "warning");
    return;
  }

  // 1. Obtener host sugerido del servidor y token de pairing
  statusBox.style.display = "block";
  statusBox.className = "gatt-status-box loading";
  statusBox.innerHTML = "<p>Detectando servidor y obteniendo token seguro...</p>";

  let backendHost = "";
  try {
    const resInfo = await apiFetch("/api/servidor/info");
    if (resInfo.ok && resInfo.data && resInfo.data.host_sugerido) {
      backendHost = resInfo.data.host_sugerido;
    }
  } catch (e) {
    console.warn("No se pudo obtener host del servidor vía /api/servidor/info:", e);
  }

  let pairingToken = "";
  try {
    const resToken = await apiFetch("/api/dispositivos/generar-token-pairing", {
      method: "POST"
    });
    if (resToken.ok && resToken.data.token) {
      pairingToken = resToken.data.token;
    } else {
      pairingToken = "PLANTOL-" + Date.now().toString(36).toUpperCase();
    }
  } catch {
    pairingToken = "PLANTOL-" + Date.now().toString(36).toUpperCase();
  }

  btn.disabled    = true;
  btn.textContent = "Transmitiendo por GATT...";
  statusBox.className = "gatt-status-box loading";
  statusBox.innerHTML = `
    <p>1. Transmitiendo credenciales Wi-Fi y host del backend (${backendHost || 'local'})...</p>
    <p>2. El ESP32 apagará Bluetooth y se conectará a '${ssid}'...</p>
    <p>3. Esperando confirmación de conexión...</p>
  `;

  try {
    // Construir el payload JSON completo para el ESP32
    const payloadObj = {
      ssid: ssid,
      pass: password,
      token: pairingToken,
      host: backendHost || window.location.origin
    };
    const payload = JSON.stringify(payloadObj);
    const encoder  = new TextEncoder();
    const dataView = encoder.encode(payload);

    // Escribir directamente en la característica GATT del ESP32 (BLE real con confirmación)
    bleEnviandoCredenciales = true;
    const tInicioProvisioning = Date.now() - 2000;
    if (typeof bleCaracteristica.writeValueWithResponse === "function") {
      await bleCaracteristica.writeValueWithResponse(dataView);
    } else {
      await bleCaracteristica.writeValue(dataView);
    }

    console.log(`[BLE] Configuración transmitida al ESP32: SSID=${ssid}, Host=${payloadObj.host}`);

    statusBox.className = "gatt-status-box loading";
    statusBox.innerHTML = `
      <p>✓ Configuración enviada al ESP32 vía GATT.</p>
      <p>El dispositivo se está conectando a '${ssid}'...</p>
      <p>Cuando el LED deje de parpadear y quede fijo, estará en red.</p>
    `;

    mostrarToast("Credenciales enviadas al ESP32. Conectando a Wi-Fi...");

    // Esperar a que el ESP32 se conecte al Wi-Fi y aparezca en la red
    await esperarDispositivoEnRed(pairingToken, ssid, tInicioProvisioning);

  } catch (err) {
    bleEnviandoCredenciales = false;
    statusBox.className = "gatt-status-box error";
    statusBox.innerHTML = `<strong>Error GATT:</strong> ${err.message}`;
    mostrarToast(`No se pudo escribir en el ESP32: ${err.message}`, "error");
    console.error("[BLE] Error al escribir característica:", err);
  } finally {
    btn.disabled    = false;
    btn.textContent = "Enviar Credenciales por GATT";
  }
}

/**
 * Espera con polling a que el ESP32 aparezca en la red local
 * (es decir, llame a /api/dispositivos/reclamar con el token).
 * Reintenta cada 3 segundos durante máximo 30 segundos.
 */
async function esperarDispositivoEnRed(token, ssid, tInicioMs = 0) {
  const statusBox = document.getElementById("statusGatt");
  const maxIntentos = 12;
  let intento = 0;

  statusBox.innerHTML += "<p>Verificando conexión del ESP32 en la red...</p>";

  while (intento < maxIntentos) {
    intento++;
    await new Promise(r => setTimeout(r, 3000));

    // Consultar dispositivos disponibles en red y verificar que alguno sea reciente
    const res = await apiFetch("/api/dispositivos/disponibles");
    const recienConectados = (res.ok && Array.isArray(res.data))
      ? res.data.filter(d => !tInicioMs || !d.ultimo_contacto || Date.parse(d.ultimo_contacto) >= tInicioMs)
      : [];

    if (recienConectados.length > 0) {
      statusBox.className = "gatt-status-box success";
      statusBox.innerHTML = `
        <strong>✓ ESP32 conectado a la red Wi-Fi '${ssid}'</strong>
        <p>El dispositivo ya está disponible en la red local y listo para vincular a una planta.</p>
      `;
      bleProvisioningCompletado = true;
      bleEnviandoCredenciales   = false;
      mostrarToast(`¡ESP32 conectado a ${ssid} y disponible en red!`);

      // Desconectar BLE (ya no es necesario — el ESP32 lo hace solo al recibir credenciales)
      if (bleDevice && bleDevice.gatt.connected) {
        bleDevice.gatt.disconnect();
      }

      await cargarDispositivosDisponibles();
      await cargarDispositivosSelect();
      return;
    }

    statusBox.innerHTML += `<p>Intento ${intento}/${maxIntentos}... esperando que el ESP32 aparezca en red.</p>`;
  }

  // Si después de 30 s no aparece
  bleEnviandoCredenciales = false;
  statusBox.className = "gatt-status-box error";
  statusBox.innerHTML = `
    <strong>Tiempo de espera agotado</strong>
    <p>El ESP32 no apareció en la red. Verifica que el SSID y la contraseña sean correctos y vuelve a intentarlo.</p>
  `;
  mostrarToast("El ESP32 no se conectó al Wi-Fi. Verifica las credenciales.", "error");
}

async function cargarDispositivosDisponibles() {
  if (!authToken) return;
  const res = await apiFetch("/api/dispositivos/disponibles");
  const select = document.getElementById("selectDispositivoDisponible");
  const countBadge = document.getElementById("countDispositivosDisponibles");

  if (!select) return;

  if (res.ok) {
    const disponibles = res.data || [];
    if (countBadge) countBadge.textContent = disponibles.length;
    select.innerHTML = '<option value="">Selecciona un sensor disponible...</option>';

    if (disponibles.length === 0) {
      select.innerHTML = '<option value="">No hay sensores disponibles en red (aprovisiona uno por Bluetooth)</option>';
    } else {
      disponibles.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = `${d.id} · MAC: ${d.mac || "Wi-Fi"} (Disponible en red)`;
        select.appendChild(opt);
      });
    }
  }
}

async function vincularDispositivoDirecto(event) {
  if (event) event.preventDefault();
  const planta_id = document.getElementById("selectPlantaVincular").value;
  const dispositivo_id = document.getElementById("selectDispositivoDisponible").value;

  if (!planta_id) {
    mostrarToast("Selecciona la planta a la que deseas asignar el sensor.", "warning");
    return;
  }
  if (!dispositivo_id) {
    mostrarToast("Selecciona un sensor ESP32 disponible en la red.", "warning");
    return;
  }

  const btn = document.getElementById("btnVincularDirecto");
  btn.disabled = true;

  const res = await apiFetch("/api/dispositivos/vincular", {
    method: "POST",
    body: JSON.stringify({ planta_id, dispositivo_id }),
  });

  btn.disabled = false;

  if (res.ok) {
    mostrarToast(`¡Dispositivo ${dispositivo_id} vinculado a la planta con éxito!`);
    document.getElementById("formVincularDirecto").reset();
    await cargarDispositivosDisponibles();
    await cargarDispositivosSelect();
    await sincronizarDashboard();
    navegar("dashboard");
  } else {
    mostrarToast(`Error de vinculación: ${res.data.mensaje}`, "error");
  }
}

// Mantener compatibilidad con llamadas anteriores
async function vincularDispositivo(event) {
  await vincularDispositivoDirecto(event);
}

// ==========================================================================
// 8. Modal de Historial de Lecturas (Requisito R5)
// ==========================================================================

async function abrirModalHistorial(plantaId, nombrePlanta) {
  currentModalPlantaId = plantaId;
  const modal = document.getElementById("modalHistorial");
  const titulo = document.getElementById("modalHistorialTitulo");
  const sub = document.getElementById("modalHistorialSub");
  const tbody = document.getElementById("modalHistorialBody");

  titulo.textContent = `Historial: ${nombrePlanta}`;
  sub.textContent = "Lecturas persistidas en la tabla 'historial_lecturas' (SQLite)";
  tbody.innerHTML = '<tr><td colspan="5" class="text-center">Consultando registros históricos...</td></tr>';
  modal.style.display = "flex";

  const res = await apiFetch(`/api/plantas/${plantaId}/historial`);
  if (!res.ok) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error: ${res.data.mensaje || "No se pudo cargar el historial"}</td></tr>`;
    return;
  }

  const historial = res.data;
  if (!historial || historial.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center">No hay lecturas registradas para esta planta.</td></tr>';
    return;
  }

  tbody.innerHTML = historial.map(item => {
    const estado = item.estado_global || "SIN_DATOS";
    const badgeClase = `badge-${estado.toLowerCase().replace("_", "-")}`;
    return `
      <tr>
        <td>${formatearFecha(item.timestamp)}</td>
        <td><strong>${Math.round(item.luminosidad)}</strong> lux</td>
        <td><strong>${item.humedad.toFixed(1)}</strong>%</td>
        <td><strong>${item.temperatura.toFixed(1)}</strong>°C</td>
        <td><span class="badge ${badgeClase}">${estado.replace("_", " ")}</span></td>
      </tr>
    `;
  }).join("");
}

function cerrarModalHistorial(event) {
  if (event && event.target && event.target.className !== "modal-backdrop" && event.target.className !== "modal-close") {
    return;
  }
  document.getElementById("modalHistorial").style.display = "none";
  currentModalPlantaId = null;
}

// ==========================================================================
// 9. Utilidades y Notificaciones
// ==========================================================================

function formatearFecha(isoString) {
  if (!isoString) return "--";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " (" + d.toLocaleDateString() + ")";
  } catch {
    return isoString;
  }
}

function mostrarToast(mensaje, tipo = "normal") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${tipo === 'error' ? 'toast-error' : (tipo === 'warning' ? 'toast-warning' : '')}`;
  toast.innerHTML = `<span class="toast-indicator">${tipo === 'error' ? '[!]' : '[OK]'}</span> <span>${mensaje}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

// ==========================================================================
// 10. Gamificación: Saludo Diario y Modal de Puntos
// ==========================================================================

async function saludarPlanta(plantaId) {
  if (!authToken) {
    mostrarToast("Debes iniciar sesión para saludar a tus plantas.", "warning");
    return;
  }

  const res = await apiFetch(`/api/plantas/${plantaId}/saludar`, {
    method: "POST"
  });

  if (res.ok) {
    mostrarToast(res.data.mensaje || "¡Has saludado a tu planta! Ganaste +1 punto de cuidado.");
    if (res.data.saldo_actual !== undefined) {
      const elPts = document.getElementById("topbarPuntosVal");
      if (elPts) elPts.textContent = res.data.saldo_actual;
    }
    await sincronizarDashboard(false);
  } else {
    mostrarToast(res.data.mensaje || "No se pudo saludar a la planta.", "warning");
  }
}

async function mostrarModalPuntos() {
  if (!authToken) {
    mostrarToast("Inicia sesión para ver tu billetera de puntos.", "warning");
    return;
  }

  const modal = document.getElementById("modalPuntos");
  const saldoVal = document.getElementById("modalSaldoPuntosVal");
  const tbody = document.getElementById("modalPuntosBody");

  modal.style.display = "flex";
  tbody.innerHTML = '<tr><td colspan="3" class="text-center">Consultando historial de recompensas...</td></tr>';

  const res = await apiFetch("/api/gamificacion/historial");
  if (res.ok && res.data) {
    saldoVal.textContent = `${res.data.saldo_puntos} pts`;
    const items = res.data.historial || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Aún no tienes movimientos registrados. Cuida o saluda a tus plantas para ganar puntos.</td></tr>';
      return;
    }

    tbody.innerHTML = items.map(t => {
      const esPos = t.cantidad > 0;
      return `
        <tr>
          <td>${formatearFecha(t.fecha)}</td>
          <td>
            <strong>${t.evento}</strong>
            <br>
            <small class="text-muted">${t.motivo}</small>
          </td>
          <td>
            <span class="puntos-badge-delta ${esPos ? 'pos' : 'neg'}">
              ${esPos ? '+' : ''}${t.cantidad} pts
            </span>
          </td>
        </tr>
      `;
    }).join("");
  } else {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">No se pudo cargar el historial de puntos.</td></tr>';
  }
}

function cerrarModalPuntos(event) {
  if (event && event.target && event.target.className !== "modal-backdrop" && event.target.className !== "modal-close") {
    return;
  }
  document.getElementById("modalPuntos").style.display = "none";
}


