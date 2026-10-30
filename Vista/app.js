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
    "diagnostico": ["Diagnóstico Manual", "Evaluación ambiental directa de especies (Fase 1)"],
    "nueva-planta": ["Agregar Planta", "Registra un nuevo ejemplar en tu colección"],
    "vincular": ["Vincular Sensor ESP32", "Asocia un dispositivo físico mediante código temporal"],
    "cuenta": ["Cuenta y Acceso", "Administración de identidad y reglas de propiedad"],
  };

  if (titulos[paginaId]) {
    document.getElementById("pageTitle").textContent = titulos[paginaId][0];
    document.getElementById("pageSubtitle").textContent = titulos[paginaId][1];
  }

  if (paginaId === "vincular") {
    actualizarSelectPlantasVincular();
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
    const selectManual = document.getElementById("selectEspecieManual");
    const selectPlanta = document.getElementById("selectEspeciePlanta");

    selectManual.innerHTML = '<option value="">Selecciona una especie...</option>';
    selectPlanta.innerHTML = '<option value="">Selecciona una especie...</option>';

    especiesDisponibles.forEach(e => {
      const opt1 = document.createElement("option");
      opt1.value = e.nombre;
      opt1.textContent = e.nombre;
      selectManual.appendChild(opt1);

      const opt2 = document.createElement("option");
      opt2.value = e.nombre;
      opt2.textContent = e.nombre;
      selectPlanta.appendChild(opt2);
    });
  }
}

async function cargarDispositivosSelect() {
  if (!authToken) return;
  const res = await apiFetch("/api/dispositivos");
  if (res.ok) {
    const select = document.getElementById("selectDispositivoPlanta");
    select.innerHTML = '<option value="">Sin dispositivo vinculado por ahora</option>';
    res.data.forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.id;
      const estado = d.planta_id ? "(Ocupado)" : "(Libre)";
      opt.textContent = `${d.id} · ${d.mac || "Wi-Fi"} ${estado}`;
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

    return `
      <div class="plant-card">
        <div class="plant-card-top">
          <div class="plant-title">
            <h4>${p.nombre}</h4>
            <span class="plant-species">${p.especie}</span>
            <span class="plant-location">${p.ubicacion || "Ubicación general"}</span>
          </div>
          <span class="badge ${badgeClase}">${estado.replace("_", " ")}</span>
        </div>

        <div class="telemetry-row">
          <div class="telemetry-item">
            <span class="tel-label">Luz</span>
            <span class="tel-value">${tieneLectura ? Math.round(lect.luminosidad) : "--"}</span>
            <span class="tel-unit">lux</span>
            ${tieneLectura ? `<span class="tel-status ${getClsParam('luminosidad')}">${getClsParam('luminosidad').toUpperCase()}</span>` : ''}
          </div>
          <div class="telemetry-item">
            <span class="tel-label">Humedad</span>
            <span class="tel-value">${tieneLectura ? lect.humedad.toFixed(1) : "--"}</span>
            <span class="tel-unit">%</span>
            ${tieneLectura ? `<span class="tel-status ${getClsParam('humedad')}">${getClsParam('humedad').toUpperCase()}</span>` : ''}
          </div>
          <div class="telemetry-item">
            <span class="tel-label">Temperatura</span>
            <span class="tel-value">${tieneLectura ? lect.temperatura.toFixed(1) : "--"}</span>
            <span class="tel-unit">°C</span>
            ${tieneLectura ? `<span class="tel-status ${getClsParam('temperatura')}">${getClsParam('temperatura').toUpperCase()}</span>` : ''}
          </div>
        </div>

        <div class="plant-card-footer">
          <span class="device-tag">
            Sensor: ${p.dispositivo_id ? p.dispositivo_id : "Sin ESP32"}
          </span>
          <span>${horaFormateada}</span>
        </div>

        <button class="btn btn-secondary btn-sm" onclick="abrirModalHistorial(${p.id}, '${p.nombre}')">
          Ver Historial Completo
        </button>
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
// 6. Diagnóstico Manual (Requisito R1)
// ==========================================================================

function actualizarRangosEspecie() {
  const select = document.getElementById("selectEspecieManual");
  const box = document.getElementById("boxRangosReferencia");
  const nombre = select.value;

  if (!nombre) {
    box.style.display = "none";
    return;
  }

  const esp = especiesDisponibles.find(e => e.nombre === nombre);
  if (esp && esp.rangos) {
    document.getElementById("refLux").textContent = `Luz: ${esp.rangos.luminosidad.min}–${esp.rangos.luminosidad.max} lux`;
    document.getElementById("refHum").textContent = `Humedad: ${esp.rangos.humedad.min}–${esp.rangos.humedad.max} %`;
    document.getElementById("refTemp").textContent = `Temperatura: ${esp.rangos.temperatura.min}–${esp.rangos.temperatura.max} °C`;
    box.style.display = "block";
  }
}

async function ejecutarDiagnosticoManual(event) {
  event.preventDefault();
  const especie = document.getElementById("selectEspecieManual").value;
  const luminosidad = parseFloat(document.getElementById("inputLuxManual").value);
  const humedad = parseFloat(document.getElementById("inputHumManual").value);
  const temperatura = parseFloat(document.getElementById("inputTempManual").value);

  const res = await apiFetch("/api/diagnostico", {
    method: "POST",
    body: JSON.stringify({ especie, luminosidad, humedad, temperatura }),
  });

  const card = document.getElementById("resultadoDiagnosticoCard");
  if (!res.ok) {
    mostrarToast(`Error: ${res.data.mensaje || "Datos inválidos"}`, "error");
    card.style.display = "none";
    return;
  }

  const d = res.data;
  card.style.display = "block";

  const badge = document.getElementById("resultadoBadgeGlobal");
  badge.textContent = d.estado_global;
  badge.className = `badge badge-${d.estado_global.toLowerCase().replace("_", "-")}`;

  document.getElementById("resultadoEspecieText").textContent = `Especie evaluada: ${d.especie}`;

  const lista = document.getElementById("resultadoParametrosList");
  lista.innerHTML = d.parametros.map(p => `
    <div class="param-item">
      <div class="param-item-header">
        <span class="param-item-name">${p.nombre}: ${p.valor}</span>
        <span class="badge badge-${p.clasificacion === 'OPTIMO' ? 'saludable' : (p.clasificacion === 'BAJO' ? 'en-riesgo' : 'critico')}">
          ${p.clasificacion}
        </span>
      </div>
      <p class="param-item-reco">${p.recomendacion ? p.recomendacion : "Condición ambiental óptima."}</p>
    </div>
  `).join("");

  mostrarToast("Evaluación manual completada con éxito.");
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
    select.innerHTML = '<option value="">Selecciona tu Planta...</option>';
    res.data.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.nombre} (${p.especie}) - Actual: ${p.dispositivo_id || "Ninguno"}`;
      select.appendChild(opt);
    });
  }
}

async function generarCodigoPrueba() {
  const devId = document.getElementById("inputGenDevId").value.trim().toUpperCase();
  if (!devId) {
    mostrarToast("Ingresa el ID del ESP32 a autorizar.", "warning");
    return;
  }

  const res = await apiFetch("/api/dispositivos/codigo", {
    method: "POST",
    body: JSON.stringify({ dispositivo_id: devId }),
  });

  if (res.ok) {
    const box = document.getElementById("boxCodigoGenerado");
    const val = document.getElementById("valCodigoGenerado");
    val.textContent = res.data.codigo_temporal;
    box.style.display = "block";

    // Rellena automáticamente los campos del formulario de vinculación
    document.getElementById("inputDispositivoIdVincular").value = devId;
    document.getElementById("inputCodigoVinculacion").value = res.data.codigo_temporal;

    mostrarToast(`Código temporal para ${devId} generado.`);
  } else {
    mostrarToast(`Error: ${res.data.mensaje}`, "error");
  }
}

async function vincularDispositivo(event) {
  event.preventDefault();
  const planta_id = document.getElementById("selectPlantaVincular").value;
  const dispositivo_id = document.getElementById("inputDispositivoIdVincular").value.trim().toUpperCase();
  const codigo = document.getElementById("inputCodigoVinculacion").value.trim().toUpperCase();

  const res = await apiFetch("/api/dispositivos/vincular", {
    method: "POST",
    body: JSON.stringify({ planta_id, dispositivo_id, codigo }),
  });

  if (res.ok) {
    mostrarToast(`Dispositivo ${dispositivo_id} vinculado con éxito.`);
    document.getElementById("formVincular").reset();
    document.getElementById("boxCodigoGenerado").style.display = "none";
    await sincronizarDashboard();
    navegar("dashboard");
  } else {
    mostrarToast(`Error de vinculación: ${res.data.mensaje}`, "error");
  }
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

