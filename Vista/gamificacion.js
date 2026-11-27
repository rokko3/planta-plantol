/**
 * Plantol — Módulo Frontend de Gamificación Avanzada (gamificacion.js)
 * Gestiona Progresión (XP/Niveles), Misiones, Logros, Tienda, Inventario y Habitación Virtual.
 * Toda validación de saldos, precios, compras y desbloqueos reside exclusivamente en el backend.
 */

let gamificacionResumen = null;

async function cargarGamificacionAvanzada() {
  if (!authToken) return;
  const res = await apiFetch("/api/gamificacion/resumen");
  if (!res.ok) {
    mostrarToast(traducirErrorAmigable(res, "carga de progreso"), "warning");
    return;
  }
  gamificacionResumen = res.data;

  // Sincronizar píldora superior de monedas
  const elPts = document.getElementById("topbarPuntosVal");
  if (elPts && gamificacionResumen.monedas !== undefined) {
    elPts.textContent = gamificacionResumen.monedas;
  }

  renderizarProgresion(gamificacionResumen);
  renderizarMisiones(gamificacionResumen.misiones || []);
  renderizarLogros(gamificacionResumen.logros || []);
  renderizarTienda(gamificacionResumen);
  await renderizarHabitacionVirtual(gamificacionResumen);
}

function renderizarProgresion(data) {
  const prog = data.progresion || {};
  const badge = document.getElementById("progNivelBadge");
  const titulo = document.getElementById("progTitulo");
  const xpTxt = document.getElementById("progXpTexto");
  const xpBar = document.getElementById("progXpBar");
  const monedas = document.getElementById("tiendaMonedasVal");

  if (badge) badge.textContent = `Nivel ${prog.nivel || 1}`;
  if (titulo) titulo.textContent = prog.titulo || "Semilla Curiosa";
  if (xpTxt) xpTxt.textContent = `${prog.xp_en_nivel || 0} / ${prog.xp_siguiente_nivel || 100} XP para el siguiente nivel (Total: ${prog.xp_total || 0} XP)`;
  if (xpBar) xpBar.style.width = `${prog.porcentaje_nivel || 0}%`;
  if (monedas) monedas.textContent = `${data.monedas ?? 0} pts`;
}

function renderizarMisiones(misiones) {
  const cont = document.getElementById("listaMisiones");
  if (!cont) return;
  if (!misiones.length) {
    cont.innerHTML = '<p class="text-muted">No hay misiones activas por ahora.</p>';
    return;
  }
  cont.innerHTML = misiones.map(m => {
    const pct = Math.min(100, Math.round(((m.progreso || 0) / (m.meta || 1)) * 100));
    return `
      <div class="mission-item ${m.completada ? 'completed' : ''}">
        <div class="mission-head">
          <div>
            <strong>${escapeHtml(m.titulo)}</strong>
            <span class="mission-tag">${m.tipo === 'diaria' ? 'Diaria' : 'Progreso'}</span>
          </div>
          <span class="mission-reward">+${m.recompensa_monedas} pts · +${m.recompensa_xp} XP</span>
        </div>
        <p class="text-muted text-sm">${escapeHtml(m.descripcion)}</p>
        <div class="mission-progress-row">
          <div class="hp-progress" style="flex: 1;">
            <div class="hp-fill ${m.completada ? 'hp-high' : 'hp-mid'}" style="width: ${pct}%;"></div>
          </div>
          <span class="text-sm">${m.completada ? '✓ Completada' : `${m.progreso}/${m.meta}`}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderizarLogros(logros) {
  const cont = document.getElementById("listaLogros");
  if (!cont) return;
  cont.innerHTML = `<div class="achievements-grid">${logros.map(l => `
    <div class="achievement-card ${l.desbloqueado ? 'unlocked' : 'locked'}">
      <div class="achievement-icon">${escapeHtml(l.icono || '🏅')}</div>
      <div class="achievement-body">
        <strong>${escapeHtml(l.titulo)}</strong>
        <p class="text-muted text-sm">${escapeHtml(l.descripcion)}</p>
        <span class="text-sm">${l.desbloqueado ? `✓ Desbloqueado (${escapeHtml(formatearFecha(l.fecha_desbloqueo))})` : `Recompensa: +${l.recompensa_monedas} pts · +${l.recompensa_xp} XP`}</span>
      </div>
    </div>
  `).join("")}</div>`;
}

let categoriaTiendaActiva = "todos";
let ultimoObjetoCompradoId = null;

const CATEGORIAS_TIENDA = [
  { id: "todos", label: "Todas" },
  { id: "maceta", label: "Macetas" },
  { id: "mueble", label: "Muebles" },
  { id: "lampara", label: "Iluminación" },
  { id: "alfombra", label: "Alfombras" },
  { id: "fondo", label: "Fondos" },
  { id: "decoracion", label: "Decoración" },
];

const ETIQUETAS_RAREZA = {
  comun: "Común",
  rara: "Rara",
  epica: "Épica",
  legendaria: "Legendaria",
};

function seleccionarCategoriaTienda(catId) {
  categoriaTiendaActiva = catId;
  if (gamificacionResumen) {
    renderizarTienda(gamificacionResumen);
  }
}

function abrirPreviewTienda(objetoId) {
  if (!gamificacionResumen) return;
  const art = (gamificacionResumen.catalogo || []).find(a => a.id === objetoId);
  if (!art) return;

  const modal = document.getElementById("modalPreviewTienda");
  const titulo = document.getElementById("previewTiendaTitulo");
  const sub = document.getElementById("previewTiendaSub");
  const body = document.getElementById("previewTiendaBody");
  if (!modal || !body) return;

  const slots = (gamificacionResumen.habitacion && gamificacionResumen.habitacion.slots) || {};
  const monedas = gamificacionResumen.monedas ?? 0;
  const equipado = slots[art.slot_habitacion] === art.id;
  const rareza = art.rareza || "comun";
  const slotLabel = ETIQUETAS_SLOT[art.slot_habitacion] || art.slot_habitacion;

  if (titulo) titulo.textContent = art.nombre;
  if (sub) sub.textContent = `${ETIQUETAS_RAREZA[rareza] || rareza} · Espacio: ${slotLabel} · Nivel ${art.nivel_requerido}+`;

  let accionHtml = "";
  if (equipado) {
    accionHtml = `<button type="button" class="btn btn-secondary" onclick="cerrarPreviewTienda(); navegar('habitacion');">✓ Equipado · Ver Habitación</button>`;
  } else if (art.poseido) {
    accionHtml = `<button type="button" class="btn btn-primary" onclick="equiparDesdeTienda('${escapeHtml(art.slot_habitacion)}', '${escapeHtml(art.id)}', this, true)">Equipar en Habitación</button>`;
  } else if (!art.desbloqueado_nivel) {
    accionHtml = `<button type="button" class="btn btn-secondary" disabled>Requiere Nivel ${art.nivel_requerido}</button>`;
  } else if (monedas < art.precio) {
    const faltan = art.precio - monedas;
    accionHtml = `<button type="button" class="btn btn-secondary" disabled>Saldo insuficiente (faltan ${faltan} monedas)</button>`;
  } else {
    accionHtml = `<button type="button" class="btn btn-primary" onclick="comprarArticuloTienda('${escapeHtml(art.id)}', this, true)">Comprar por ${art.precio} monedas</button>`;
  }

  body.innerHTML = `
    <div class="shop-preview-layout">
      <div class="shop-preview-stage rarity-frame-${escapeHtml(rareza)}">
        ${obtenerSvgMiniaturaObjeto(art.id)}
      </div>
      <div class="shop-preview-details">
        <div class="shop-preview-badges">
          <span class="rarity-pill rarity-${escapeHtml(rareza)}">${escapeHtml(ETIQUETAS_RAREZA[rareza] || rareza)}</span>
          <span class="shop-level-pill">Nv. ${art.nivel_requerido}</span>
          <span class="shop-slot-pill">Espacio: ${escapeHtml(slotLabel)}</span>
        </div>
        <p>${escapeHtml(art.descripcion)}</p>
        <div class="shop-preview-price-row">
          <span>Precio oficial: <strong>${art.precio} monedas</strong></span>
          <span>Tu saldo: <strong>${monedas} monedas</strong></span>
        </div>
        <div class="shop-preview-actions">${accionHtml}</div>
      </div>
    </div>
  `;
  modal.style.display = "flex";
}

function cerrarPreviewTienda(event) {
  const modal = document.getElementById("modalPreviewTienda");
  if (!modal) return;
  if (!event || event.target === modal) {
    modal.style.display = "none";
  }
}

function renderizarTienda(dataOrCatalogo) {
  const grid = document.getElementById("catalogoTiendaGrid");
  if (!grid) return;

  const data = Array.isArray(dataOrCatalogo)
    ? { catalogo: dataOrCatalogo, monedas: gamificacionResumen?.monedas ?? 0, habitacion: gamificacionResumen?.habitacion ?? { slots: {} } }
    : (dataOrCatalogo || {});

  const catalogo = data.catalogo || [];
  const monedas = data.monedas ?? 0;
  const slots = (data.habitacion && data.habitacion.slots) || {};

  // Actualizar barra de progreso de colección
  const totalCat = catalogo.length;
  const poseidosCount = catalogo.filter(a => a.poseido).length;
  const pctCol = totalCat > 0 ? Math.round((poseidosCount / totalCat) * 100) : 0;
  const countEl = document.getElementById("shopCollectionCount");
  const barEl = document.getElementById("shopCollectionBar");
  const balEl = document.getElementById("shopBalanceChip");
  const tabsEl = document.getElementById("shopCategoryTabs");

  if (countEl) countEl.textContent = `${poseidosCount} / ${totalCat} (${pctCol}%)`;
  if (barEl) barEl.style.width = `${pctCol}%`;
  if (balEl) balEl.innerHTML = `Saldo: <strong>${monedas}</strong> monedas`;

  if (tabsEl) {
    tabsEl.innerHTML = CATEGORIAS_TIENDA.map(cat => `
      <button type="button"
        class="room-cat-tab ${categoriaTiendaActiva === cat.id ? "active" : ""}"
        onclick="seleccionarCategoriaTienda('${cat.id}')">
        ${escapeHtml(cat.label)}
      </button>
    `).join("");
  }

  const filtrados = categoriaTiendaActiva === "todos"
    ? catalogo
    : catalogo.filter(art => art.slot_habitacion === categoriaTiendaActiva);

  if (filtrados.length === 0) {
    grid.innerHTML = '<p class="text-muted">No hay artículos en esta categoría.</p>';
    return;
  }

  grid.innerHTML = filtrados.map(art => {
    const rareza = art.rareza || "comun";
    const equipado = slots[art.slot_habitacion] === art.id;
    const puedePagar = monedas >= art.precio;
    const recienComprado = ultimoObjetoCompradoId === art.id;
    const slotLabel = ETIQUETAS_SLOT[art.slot_habitacion] || art.slot_habitacion;

    let estadoCls = "state-available";
    let estadoTag = "";
    let accionHtml = "";

    if (equipado) {
      estadoCls = "state-equipped";
      estadoTag = '<span class="shop-state-badge equipped">✓ Equipado</span>';
      accionHtml = `<button type="button" class="btn btn-sm btn-secondary" onclick="navegar('habitacion')">Ver en Habitación</button>`;
    } else if (art.poseido) {
      estadoCls = "state-owned";
      estadoTag = '<span class="shop-state-badge owned">En inventario</span>';
      accionHtml = `<button type="button" class="btn btn-sm btn-primary" onclick="equiparDesdeTienda('${escapeHtml(art.slot_habitacion)}', '${escapeHtml(art.id)}', this)">Equipar ahora</button>`;
    } else if (!art.desbloqueado_nivel) {
      estadoCls = "state-locked";
      estadoTag = `<span class="shop-state-badge locked">🔒 Nivel ${art.nivel_requerido}</span>`;
      accionHtml = `<button type="button" class="btn btn-sm btn-secondary" disabled>Requiere Nv. ${art.nivel_requerido}</button>`;
    } else if (!puedePagar) {
      estadoCls = "state-insufficient";
      estadoTag = `<span class="shop-state-badge insufficient">Saldo insuficiente</span>`;
      accionHtml = `<button type="button" class="btn btn-sm btn-secondary" disabled>Faltan ${art.precio - monedas} m</button>`;
    } else {
      estadoCls = "state-available";
      estadoTag = '<span class="shop-state-badge available">Disponible</span>';
      accionHtml = `<button type="button" class="btn btn-sm btn-primary" onclick="comprarArticuloTienda('${escapeHtml(art.id)}', this)">Comprar</button>`;
    }

    return `
      <div class="shop-item-card ${estadoCls} rarity-card-${escapeHtml(rareza)} ${recienComprado ? "shop-unlock-pop" : ""}">
        <div class="shop-card-top">
          <span class="rarity-pill rarity-${escapeHtml(rareza)}">${escapeHtml(ETIQUETAS_RAREZA[rareza] || rareza)}</span>
          ${estadoTag}
        </div>
        <div class="shop-item-stage rarity-frame-${escapeHtml(rareza)}" onclick="abrirPreviewTienda('${escapeHtml(art.id)}')" title="Ver vista previa">
          ${obtenerSvgMiniaturaObjeto(art.id)}
          <span class="shop-preview-hint">Vista previa</span>
        </div>
        <div class="shop-item-info">
          <span class="shop-cat">${escapeHtml(slotLabel)} · Nv. ${art.nivel_requerido}</span>
          <h4>${escapeHtml(art.nombre)}</h4>
          <p class="text-muted text-sm">${escapeHtml(art.descripcion)}</p>
        </div>
        <div class="shop-item-footer">
          <div class="shop-price-tag">
            <strong>${art.precio}</strong>
            <span>monedas</span>
          </div>
          <div class="shop-card-actions">
            ${accionHtml}
          </div>
        </div>
      </div>
    `;
  }).join("");
  ultimoObjetoCompradoId = null;
}

async function equiparDesdeTienda(slot, objetoId, btnEl, cerrarModal = false) {
  if (operacionesEnCurso.has("habitacion")) return;
  operacionesEnCurso.add("habitacion");
  if (btnEl) { btnEl.disabled = true; btnEl.textContent = "Equipando..."; }

  try {
    const res = await apiFetch("/api/gamificacion/habitacion", {
      method: "PUT",
      body: JSON.stringify({ slots: { [slot]: objetoId } }),
    });
    if (res.ok) {
      ultimoSlotAnimado = slot;
      if (cerrarModal) cerrarPreviewTienda();
      mostrarToast("¡Objeto equipado en tu habitación virtual!");
      await cargarGamificacionAvanzada();
    } else {
      mostrarToast(traducirErrorAmigable(res, "equipar objeto"), "warning");
      if (btnEl) btnEl.disabled = false;
    }
  } finally {
    operacionesEnCurso.delete("habitacion");
  }
}

async function comprarArticuloTienda(objetoId, btnEl, cerrarModal = false) {
  const clave = `comprar-${objetoId}`;
  if (operacionesEnCurso.has(clave)) return;
  operacionesEnCurso.add(clave);
  if (btnEl) { btnEl.disabled = true; btnEl.textContent = "Comprando..."; }

  try {
    const res = await apiFetch("/api/gamificacion/tienda/comprar", {
      method: "POST",
      body: JSON.stringify({ objeto_id: objetoId }),
    });
    if (res.ok) {
      ultimoObjetoCompradoId = objetoId;
      if (cerrarModal) cerrarPreviewTienda();
      mostrarToast(res.data.mensaje || "¡Objeto adquirido!");
      await cargarGamificacionAvanzada();
    } else {
      mostrarToast(traducirErrorAmigable(res, "compra en tienda"), "warning");
      if (btnEl) btnEl.disabled = false;
    }
  } finally {
    operacionesEnCurso.delete(clave);
  }
}

let categoriaHabitacionActiva = "todos";
let ultimoSlotAnimado = null;

const CATEGORIAS_HABITACION = [
  { id: "todos", label: "Todos" },
  { id: "fondo", label: "Ventana / Fondo" },
  { id: "mueble", label: "Muebles" },
  { id: "maceta", label: "Macetas" },
  { id: "lampara", label: "Iluminación" },
  { id: "alfombra", label: "Alfombras" },
  { id: "decoracion", label: "Decoración" },
];

const ETIQUETAS_SLOT = {
  fondo: "Fondo",
  mueble: "Mueble",
  maceta: "Maceta",
  lampara: "Iluminación",
  alfombra: "Alfombra",
  decoracion: "Decoración",
};

function obtenerSvgMiniaturaObjeto(objetoId) {
  switch (objetoId) {
    case "maceta_terracota":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><path d="M16 22h32l-4 28H20z" fill="#c96b43"/><rect x="13" y="17" width="38" height="7" rx="3" fill="#df7f55"/><ellipse cx="32" cy="17" rx="16" ry="2.5" fill="#7c462c"/></svg>`;
    case "maceta_ceramica_menta":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><path d="M17 20h30l-3 27H20z" fill="#7dd3b0"/><rect x="15" y="17" width="34" height="5" rx="2.5" fill="#a7f3d0"/><path d="M22 47l-2 7M42 47l2 7" stroke="#9a6b48" stroke-width="3.5" stroke-linecap="round"/><circle cx="27" cy="31" r="1.8" fill="#065f46" opacity="0.35"/><circle cx="36" cy="36" r="1.5" fill="#065f46" opacity="0.35"/></svg>`;
    case "maceta_dorada":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><defs><linearGradient id="gGoldM" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#fde68a"/><stop offset="55%" stop-color="#f59e0b"/><stop offset="100%" stop-color="#b45309"/></linearGradient></defs><path d="M16 21h32l-4 28H20z" fill="url(#gGoldM)"/><rect x="13" y="16" width="38" height="7" rx="3" fill="#fcd34d"/><path d="M24 34l8-6 8 6-8 6z" fill="#fffbeb" opacity="0.7"/></svg>`;
    case "alfombra_yute":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><ellipse cx="32" cy="34" rx="24" ry="13" fill="#d6b384" stroke="#a67c52" stroke-width="2"/><ellipse cx="32" cy="34" rx="17" ry="8.5" fill="none" stroke="#b98e5d" stroke-width="1.5" stroke-dasharray="3 2"/><ellipse cx="32" cy="34" rx="9" ry="4.5" fill="#e5c89e"/></svg>`;
    case "alfombra_bosque":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><ellipse cx="32" cy="34" rx="24" ry="13" fill="#3f8f63" stroke="#225d3e" stroke-width="2"/><ellipse cx="32" cy="34" rx="16" ry="8" fill="#5ab27f"/><path d="M24 34c4-4 12-4 16 0" stroke="#a7f3d0" stroke-width="1.5" fill="none"/></svg>`;
    case "mueble_repisa_roble":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><rect x="10" y="18" width="44" height="5" rx="2" fill="#b47b48"/><rect x="10" y="38" width="44" height="5" rx="2" fill="#9c6536"/><rect x="14" y="16" width="4" height="34" rx="1.5" fill="#7c4d25"/><rect x="46" y="16" width="4" height="34" rx="1.5" fill="#7c4d25"/></svg>`;
    case "mueble_escritorio_botanico":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><rect x="8" y="22" width="48" height="6" rx="2" fill="#8b5a34"/><rect x="12" y="28" width="40" height="10" rx="1.5" fill="#a47148"/><circle cx="24" cy="33" r="1.5" fill="#fde68a"/><circle cx="40" cy="33" r="1.5" fill="#fde68a"/><rect x="13" y="38" width="4" height="15" fill="#6f4524"/><rect x="47" y="38" width="4" height="15" fill="#6f4524"/></svg>`;
    case "lampara_crecimiento":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><line x1="32" y1="6" x2="32" y2="20" stroke="#475569" stroke-width="2.5"/><path d="M18 32c0-8 6-13 14-13s14 5 14 13z" fill="#f59e0b"/><circle cx="32" cy="33" r="5" fill="#fef08a"/><path d="M21 33L13 54h38L43 33z" fill="#fef08a" opacity="0.35"/></svg>`;
    case "deco_regadera_cobre":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><rect x="22" y="26" width="20" height="20" rx="4" fill="#c86d44"/><path d="M42 30c7 0 9 10 1 13" fill="none" stroke="#9e4d2a" stroke-width="3"/><path d="M22 34L10 22" stroke="#c86d44" stroke-width="3.5" stroke-linecap="round"/><ellipse cx="10" cy="21" rx="3" ry="4" fill="#e58f65"/></svg>`;
    case "deco_helecho_colgante":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><path d="M32 8L22 24h20z" fill="none" stroke="#94a3b8" stroke-width="1.5"/><path d="M21 24h22l-3 11H24z" fill="#b47b48"/><path d="M24 30c-7 4-9 13-5 19M32 31c-2 8-1 16 1 22M40 30c7 4 9 13 5 19" stroke="#22c55e" stroke-width="3.2" stroke-linecap="round" fill="none"/></svg>`;
    case "fondo_invernadero_dia":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><path d="M14 52V28a18 18 0 0 1 36 0v24z" fill="#bae6fd" stroke="#475569" stroke-width="3"/><circle cx="38" cy="22" r="6" fill="#fde047"/><path d="M14 36h36M32 10v42" stroke="#475569" stroke-width="2"/></svg>`;
    case "fondo_noche_estrellada":
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><path d="M14 52V28a18 18 0 0 1 36 0v24z" fill="#1e293b" stroke="#334155" stroke-width="3"/><path d="M36 18a8 8 0 1 0 8 10 6.5 6.5 0 1 1-8-10z" fill="#fef08a"/><circle cx="24" cy="24" r="1.5" fill="#fff"/><circle cx="42" cy="34" r="1.2" fill="#fff"/><path d="M14 36h36M32 10v42" stroke="#334155" stroke-width="2"/></svg>`;
    default:
      return `<svg viewBox="0 0 64 64" class="room-mini-svg"><circle cx="32" cy="32" r="18" fill="#e2e8f0"/></svg>`;
  }
}

function renderizarSvgMaceta(macetaId, x, y) {
  switch (macetaId) {
    case "maceta_terracota":
      return `
        <g transform="translate(${x}, ${y})">
          <ellipse cx="0" cy="40" rx="26" ry="5" fill="rgba(15,23,42,0.16)"/>
          <path d="M-24 0h48l-6 38h-36z" fill="#c96b43"/>
          <path d="M-24 0h12l-3 38h-3z" fill="#df7f55" opacity="0.55"/>
          <rect x="-27" y="-7" width="54" height="9" rx="4" fill="#df7f55"/>
          <ellipse cx="0" cy="-7" rx="23" ry="3.5" fill="#6b3e26"/>
        </g>`;
    case "maceta_ceramica_menta":
      return `
        <g transform="translate(${x}, ${y})">
          <ellipse cx="0" cy="41" rx="25" ry="5" fill="rgba(15,23,42,0.16)"/>
          <path d="M-15 33l-4 9M15 33l4 9" stroke="#8b5a34" stroke-width="4" stroke-linecap="round"/>
          <path d="M-23 -2h46l-4 36h-38z" fill="#6ee7b7"/>
          <rect x="-25" y="-7" width="50" height="7" rx="3.5" fill="#a7f3d0"/>
          <circle cx="-8" cy="12" r="2.2" fill="#047857" opacity="0.28"/>
          <circle cx="9" cy="18" r="2" fill="#047857" opacity="0.28"/>
          <ellipse cx="0" cy="-7" rx="21" ry="3.2" fill="#4b3621"/>
        </g>`;
    case "maceta_dorada":
      return `
        <g transform="translate(${x}, ${y})" class="room-gold-pot-glow">
          <ellipse cx="0" cy="40" rx="26" ry="5" fill="rgba(180,83,9,0.22)"/>
          <path d="M-24 0h48l-6 38h-36z" fill="url(#roomGoldPotGrad)"/>
          <rect x="-27" y="-7" width="54" height="9" rx="4" fill="#fde047"/>
          <path d="M0 10l8 8-8 8-8-8z" fill="#fffbeb" opacity="0.72"/>
          <ellipse cx="0" cy="-7" rx="23" ry="3.5" fill="#5c3a21"/>
        </g>`;
    default:
      return `
        <g transform="translate(${x}, ${y})">
          <ellipse cx="0" cy="40" rx="24" ry="5" fill="rgba(15,23,42,0.14)"/>
          <path d="M-21 0h42l-5 37h-32z" fill="#cbd5e1"/>
          <rect x="-23" y="-6" width="46" height="8" rx="3.5" fill="#e2e8f0"/>
          <ellipse cx="0" cy="-6" rx="19" ry="3" fill="#5c3a21"/>
        </g>`;
  }
}

function renderizarSvgFollajePlanta(planta, x, y) {
  const especie = (planta.especie || "").toLowerCase();
  const emo = (planta.estado_emocional || "RADIANTE").toUpperCase();
  const estadoGlobal = (planta.estado_global || "SALUDABLE").toUpperCase();

  let claseEstado = "plant-state-radiante";
  let colorHoja = "#22c55e";
  let colorHojaOsc = "#15803d";
  if (estadoGlobal === "CRITICO" || emo === "EN PELIGRO") {
    claseEstado = "plant-state-critico";
    colorHoja = "#a16207";
    colorHojaOsc = "#713f12";
  } else if (emo === "SEDIENTA") {
    claseEstado = "plant-state-sedienta";
    colorHoja = "#84cc16";
    colorHojaOsc = "#4d7c0f";
  } else if (emo === "ACALORADA") {
    claseEstado = "plant-state-acalorada";
    colorHoja = "#eab308";
    colorHojaOsc = "#ca8a04";
  } else if (emo === "CON FRÍO" || emo === "CON_FRIO") {
    claseEstado = "plant-state-frio";
    colorHoja = "#2dd4bf";
    colorHojaOsc = "#0f766e";
  } else if (emo === "DURMIENDO") {
    claseEstado = "plant-state-durmiendo";
    colorHoja = "#4ade80";
    colorHojaOsc = "#166534";
  }

  let cuerpoSvg = "";
  if (especie.includes("cactus")) {
    cuerpoSvg = `
      <rect x="-10" y="-62" width="20" height="58" rx="10" fill="${colorHoja}"/>
      <path d="M-10 -34c-11 0-14-6-14-16v-4c0-3 6-3 6 0v4c0 5 2 8 8 8" fill="${colorHojaOsc}"/>
      <path d="M10 -42c11 0 14-6 14-14v-3c0-3-6-3-6 0v3c0 4-2 6-8 6" fill="${colorHoja}"/>
      <circle cx="0" cy="-64" r="5" fill="#fb7185"/>
    `;
  } else if (especie.includes("orqu")) {
    cuerpoSvg = `
      <path d="M0 -6C-18 -18 -24 -6 -8 0M0 -6C18 -18 24 -6 8 0" fill="${colorHojaOsc}"/>
      <path d="M0 -6C-4 -36 6 -58 14 -72" fill="none" stroke="#16a34a" stroke-width="3.5" stroke-linecap="round"/>
      <circle cx="14" cy="-72" r="9" fill="#d946ef"/>
      <circle cx="14" cy="-72" r="4" fill="#fde047"/>
      <circle cx="6" cy="-54" r="7.5" fill="#e879f9"/>
      <circle cx="6" cy="-54" r="3" fill="#fde047"/>
    `;
  } else if (especie.includes("helecho")) {
    cuerpoSvg = `
      <path d="M0 -5C-22 -24 -30 -44 -26 -58" fill="none" stroke="${colorHoja}" stroke-width="6" stroke-linecap="round"/>
      <path d="M0 -5C-8 -30 -8 -54 0 -72" fill="none" stroke="${colorHojaOsc}" stroke-width="6.5" stroke-linecap="round"/>
      <path d="M0 -5C22 -24 30 -44 26 -58" fill="none" stroke="${colorHoja}" stroke-width="6" stroke-linecap="round"/>
      <path d="M0 -5C-24 -12 -34 -22 -36 -32" fill="none" stroke="${colorHojaOsc}" stroke-width="5" stroke-linecap="round"/>
      <path d="M0 -5C24 -12 34 -22 36 -32" fill="none" stroke="${colorHojaOsc}" stroke-width="5" stroke-linecap="round"/>
    `;
  } else {
    // Monstera / Hoja ancha tropical
    cuerpoSvg = `
      <path d="M0 -4C-2 -26 -14 -44 -20 -58" stroke="#15803d" stroke-width="3.5" fill="none"/>
      <path d="M0 -4C2 -28 14 -46 20 -60" stroke="#15803d" stroke-width="3.5" fill="none"/>
      <path d="M0 -4V-66" stroke="#16a34a" stroke-width="4" fill="none"/>
      <ellipse cx="-18" cy="-50" rx="14" ry="18" transform="rotate(-24 -18 -50)" fill="${colorHoja}"/>
      <ellipse cx="18" cy="-52" rx="14" ry="18" transform="rotate(24 18 -52)" fill="${colorHojaOsc}"/>
      <ellipse cx="0" cy="-66" rx="15" ry="20" fill="${colorHoja}"/>
    `;
  }

  let indicadorEstado = "";
  if (emo === "SEDIENTA") {
    indicadorEstado = `<path d="M24 -70c4 6 6 10 6 13a6 6 0 1 1-12 0c0-3 2-7 6-13z" fill="#38bdf8" class="room-float-cue"/>`;
  } else if (emo === "DURMIENDO") {
    indicadorEstado = `<text x="18" y="-72" fill="#e2e8f0" font-size="13" font-weight="700" class="room-float-cue">zZz</text>`;
  } else if (emo === "EN PELIGRO" || estadoGlobal === "CRITICO") {
    indicadorEstado = `<circle cx="24" cy="-72" r="8" fill="#ef4444"/><text x="21.5" y="-68" fill="#fff" font-size="11" font-weight="800">!</text>`;
  } else if (emo === "RADIANTE") {
    indicadorEstado = `<path d="M24 -76l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" fill="#fde047" class="room-sparkle-cue"/>`;
  }

  return `
    <g transform="translate(${x}, ${y})">
      <g class="room-plant-sway ${claseEstado}">
        ${cuerpoSvg}
        ${indicadorEstado}
      </g>
    </g>`;
}

function seleccionarCategoriaHabitacion(catId) {
  categoriaHabitacionActiva = catId;
  cargarGamificacionAvanzada();
}

async function renderizarHabitacionVirtual(resumen) {
  const canvas = document.getElementById("virtualRoomCanvas");
  const customizer = document.getElementById("roomCustomizerList");
  const tabsEl = document.getElementById("roomCategoryTabs");
  const slotsOverviewEl = document.getElementById("roomSlotsOverview");
  const summaryPillEl = document.getElementById("roomPlantSummaryPill");
  const legendEl = document.getElementById("roomPlantsLegend");
  if (!canvas || !customizer) return;

  const slots = (resumen.habitacion && resumen.habitacion.slots) || {};
  const inventario = resumen.inventario || [];
  const catalogoMap = Object.fromEntries((resumen.catalogo || []).map(a => [a.id, a]));

  // Obtener plantas reales del usuario para mostrarlas dentro de la habitación
  let plantas = [];
  const resPlantas = await apiFetch("/api/plantas");
  if (resPlantas.ok && Array.isArray(resPlantas.data)) {
    plantas = resPlantas.data;
  }

  if (summaryPillEl) {
    const conSensor = plantas.filter(p => p.dispositivo_id).length;
    summaryPillEl.textContent = plantas.length === 0
      ? "Sin plantas registradas"
      : `${plantas.length} planta${plantas.length === 1 ? "" : "s"} · ${conSensor} con sensor`;
  }

  const fondoId = slots.fondo || "";
  const esNoche = fondoId === "fondo_noche_estrellada";
  const esSoleado = fondoId === "fondo_invernadero_dia";
  const macetaId = slots.maceta || "";
  const muebleId = slots.mueble || "";
  const lamparaId = slots.lampara || "";
  const alfombraId = slots.alfombra || "";
  const decoId = slots.decoracion || "";

  const paredTop = esNoche ? "#1e293b" : (esSoleado ? "#fef9c3" : "#eef6ee");
  const paredBot = esNoche ? "#334155" : (esSoleado ? "#ecfccb" : "#dcebe0");
  const pisoColor = esNoche ? "#3b2c22" : "#c79663";
  const pisoLinea = esNoche ? "#281c15" : "#ab7a47";

  const ventanaContenido = esNoche
    ? `
      <rect x="250" y="38" width="300" height="190" rx="18" fill="#0f172a" stroke="#475569" stroke-width="8"/>
      <circle cx="485" cy="84" r="22" fill="#fef08a" opacity="0.92"/>
      <circle cx="495" cy="78" r="19" fill="#0f172a"/>
      <circle cx="290" cy="72" r="2" fill="#fff"/><circle cx="345" cy="60" r="1.8" fill="#fde047"/>
      <circle cx="410" cy="88" r="2.2" fill="#fff"/><circle cx="320" cy="122" r="1.5" fill="#fff"/>
      <circle cx="445" cy="135" r="2" fill="#fde047"/><circle cx="285" cy="160" r="1.8" fill="#fff"/>
      <line x1="400" y1="38" x2="400" y2="228" stroke="#475569" stroke-width="5"/>
      <line x1="250" y1="133" x2="550" y2="133" stroke="#475569" stroke-width="5"/>
      <polygon points="250,228 550,228 640,420 160,420" fill="rgba(148,163,184,0.12)"/>
    `
    : esSoleado
      ? `
      <path d="M240 230V115a160 115 0 0 1 320 0v115z" fill="url(#roomSunnySky)" stroke="#926239" stroke-width="9"/>
      <circle cx="470" cy="92" r="26" fill="#fde047" opacity="0.95"/>
      <ellipse cx="325" cy="96" rx="34" ry="12" fill="rgba(255,255,255,0.8)"/>
      <line x1="400" y1="2" x2="400" y2="230" stroke="#926239" stroke-width="5"/>
      <line x1="240" y1="138" x2="560" y2="138" stroke="#926239" stroke-width="5"/>
      <polygon points="240,230 560,230 675,435 125,435" fill="rgba(254,240,138,0.22)" class="room-sunbeam-pulse"/>
    `
      : `
      <rect x="265" y="42" width="270" height="184" rx="12" fill="#dbeafe" stroke="#8b5a34" stroke-width="8"/>
      <ellipse cx="335" cy="92" rx="30" ry="11" fill="rgba(255,255,255,0.85)"/>
      <ellipse cx="465" cy="112" rx="24" ry="9" fill="rgba(255,255,255,0.7)"/>
      <line x1="400" y1="42" x2="400" y2="226" stroke="#8b5a34" stroke-width="5"/>
      <line x1="265" y1="134" x2="535" y2="134" stroke="#8b5a34" stroke-width="5"/>
      <polygon points="265,226 535,226 620,420 180,420" fill="rgba(255,255,255,0.14)"/>
    `;

  const alfombraSvg = alfombraId === "alfombra_bosque"
    ? `
      <g class="room-slot-layer ${ultimoSlotAnimado === "alfombra" ? "room-equip-pop" : ""}">
        <ellipse cx="400" cy="438" rx="220" ry="38" fill="#2f7a52" stroke="#1e5638" stroke-width="3"/>
        <ellipse cx="400" cy="438" rx="175" ry="26" fill="#469e6d"/>
        <path d="M300 438c35-14 165-14 200 0" stroke="#a7f3d0" stroke-width="2" fill="none" opacity="0.5"/>
      </g>`
    : alfombraId === "alfombra_yute"
      ? `
      <g class="room-slot-layer ${ultimoSlotAnimado === "alfombra" ? "room-equip-pop" : ""}">
        <ellipse cx="400" cy="438" rx="215" ry="36" fill="#d6b384" stroke="#a67c52" stroke-width="3"/>
        <ellipse cx="400" cy="438" rx="165" ry="25" fill="none" stroke="#b98e5d" stroke-width="2" stroke-dasharray="6 4"/>
        <ellipse cx="400" cy="438" rx="105" ry="15" fill="#e5c89e"/>
      </g>`
      : "";

  let muebleSvg = "";
  let plantasBaseY = 344;
  if (muebleId === "mueble_escritorio_botanico") {
    plantasBaseY = 312;
    muebleSvg = `
      <g class="room-slot-layer ${ultimoSlotAnimado === "mueble" ? "room-equip-pop" : ""}">
        <rect x="175" y="346" width="450" height="16" rx="5" fill="#8b5a34"/>
        <rect x="195" y="362" width="410" height="36" rx="3" fill="#a47148"/>
        <rect x="212" y="370" width="175" height="20" rx="2" fill="#8f5d38"/>
        <rect x="413" y="370" width="175" height="20" rx="2" fill="#8f5d38"/>
        <circle cx="300" cy="380" r="3.5" fill="#fde68a"/>
        <circle cx="500" cy="380" r="3.5" fill="#fde68a"/>
        <rect x="205" y="398" width="16" height="44" rx="2" fill="#6f4524"/>
        <rect x="579" y="398" width="16" height="44" rx="2" fill="#6f4524"/>
      </g>`;
  } else if (muebleId === "mueble_repisa_roble") {
    plantasBaseY = 314;
    muebleSvg = `
      <g class="room-slot-layer ${ultimoSlotAnimado === "mueble" ? "room-equip-pop" : ""}">
        <rect x="190" y="348" width="420" height="14" rx="4" fill="#c08552"/>
        <rect x="190" y="394" width="420" height="12" rx="4" fill="#a56c3d"/>
        <rect x="210" y="344" width="14" height="96" rx="3" fill="#7c4d25"/>
        <rect x="576" y="344" width="14" height="96" rx="3" fill="#7c4d25"/>
      </g>`;
  } else {
    muebleSvg = `
      <g class="room-slot-layer">
        <rect x="210" y="380" width="380" height="12" rx="4" fill="#b48a64"/>
        <rect x="235" y="392" width="12" height="44" rx="2" fill="#8c6340"/>
        <rect x="553" y="392" width="12" height="44" rx="2" fill="#8c6340"/>
      </g>`;
  }

  const lamparaSvg = lamparaId === "lampara_crecimiento"
    ? `
      <g class="room-slot-layer ${ultimoSlotAnimado === "lampara" ? "room-equip-pop" : ""}">
        <line x1="145" y1="0" x2="145" y2="85" stroke="#475569" stroke-width="3.5"/>
        <path d="M110 116c0-20 14-32 35-32s35 12 35 32z" fill="#d97706"/>
        <ellipse cx="145" cy="116" rx="35" ry="6" fill="#fef08a"/>
        <polygon points="112,116 178,116 290,410 45,410" fill="url(#roomLampCone)" class="room-lamp-glow"/>
      </g>`
    : "";

  const decoSvg = decoId === "deco_helecho_colgante"
    ? `
      <g transform="translate(650, 78)" class="room-slot-layer ${ultimoSlotAnimado === "decoracion" ? "room-equip-pop" : ""}">
        <g class="room-plant-sway">
          <line x1="0" y1="-78" x2="0" y2="-16" stroke="#94a3b8" stroke-width="2.5"/>
          <path d="M0 -16L-22 10h44z" fill="none" stroke="#cbd5e1" stroke-width="2"/>
          <path d="M-24 10h48l-6 20h-36z" fill="#b47b48"/>
          <path d="M-20 20c-16 12-18 34-10 48M0 24c-4 18-2 38 2 52M20 20c16 12 18 34 10 48" stroke="#22c55e" stroke-width="6" stroke-linecap="round" fill="none"/>
        </g>
      </g>`
    : decoId === "deco_regadera_cobre"
      ? `
      <g transform="translate(645, 360)" class="room-slot-layer ${ultimoSlotAnimado === "decoracion" ? "room-equip-pop" : ""}">
        <ellipse cx="0" cy="40" rx="22" ry="5" fill="rgba(15,23,42,0.16)"/>
        <rect x="-16" y="4" width="32" height="34" rx="6" fill="#c86d44"/>
        <path d="M16 10c14 0 16 18 2 22" fill="none" stroke="#9e4d2a" stroke-width="5" stroke-linecap="round"/>
        <path d="M-16 18L-36 -2" stroke="#c86d44" stroke-width="6" stroke-linecap="round"/>
        <ellipse cx="-38" cy="-4" rx="5" ry="7" transform="rotate(-35 -38 -4)" fill="#e58f65"/>
      </g>`
      : "";

  const plantasVisibles = plantas.slice(0, 4);
  const posicionesX = plantasVisibles.length === 1
    ? [400]
    : plantasVisibles.length === 2
      ? [330, 470]
      : plantasVisibles.length === 3
        ? [285, 400, 515]
        : [250, 350, 450, 550];

  const plantasSvg = plantasVisibles.length > 0
    ? plantasVisibles.map((p, idx) => {
        const px = posicionesX[idx];
        return `
          <g class="room-plant-spot-svg ${ultimoSlotAnimado === "maceta" ? "room-equip-pop" : ""}">
            ${renderizarSvgFollajePlanta(p, px, plantasBaseY)}
            ${renderizarSvgMaceta(macetaId, px, plantasBaseY)}
          </g>`;
      }).join("")
    : `
      <g transform="translate(400, ${plantasBaseY + 18})">
        <rect x="-125" y="-32" width="250" height="54" rx="12" fill="rgba(255,255,255,0.88)" stroke="#cbd5e1"/>
        <text x="0" y="-8" text-anchor="middle" fill="#334155" font-size="13" font-weight="700">Aún no tienes plantas registradas</text>
        <text x="0" y="10" text-anchor="middle" fill="#64748b" font-size="11">Agrega tu primera planta real para verla aquí</text>
      </g>`;

  canvas.className = `virtual-room-scene ${esNoche ? "scene-night" : "scene-day"}`;
  canvas.innerHTML = `
    <svg viewBox="0 0 800 490" class="virtual-room-svg" role="img" aria-label="Habitación botánica virtual de Plantol">
      <defs>
        <linearGradient id="roomWallGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${paredTop}"/>
          <stop offset="100%" stop-color="${paredBot}"/>
        </linearGradient>
        <linearGradient id="roomSunnySky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#7dd3fc"/>
          <stop offset="100%" stop-color="#fef9c3"/>
        </linearGradient>
        <linearGradient id="roomLampCone" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(253,224,71,0.42)"/>
          <stop offset="100%" stop-color="rgba(253,224,71,0)"/>
        </linearGradient>
        <linearGradient id="roomGoldPotGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#fde68a"/>
          <stop offset="55%" stop-color="#f59e0b"/>
          <stop offset="100%" stop-color="#b45309"/>
        </linearGradient>
      </defs>

      <!-- Pared y Zócalo -->
      <rect x="0" y="0" width="800" height="370" fill="url(#roomWallGrad)"/>
      <rect x="0" y="356" width="800" height="16" fill="${esNoche ? '#1e293b' : '#cbd5e1'}" opacity="0.65"/>

      <!-- Suelo de madera -->
      <rect x="0" y="370" width="800" height="120" fill="${pisoColor}"/>
      <line x1="0" y1="402" x2="800" y2="402" stroke="${pisoLinea}" stroke-width="1.5" opacity="0.45"/>
      <line x1="0" y1="442" x2="800" y2="442" stroke="${pisoLinea}" stroke-width="1.5" opacity="0.45"/>

      <!-- Ventana / Fondo -->
      <g class="room-slot-layer ${ultimoSlotAnimado === "fondo" ? "room-equip-pop" : ""}">
        ${ventanaContenido}
      </g>

      <!-- Alfombra -->
      ${alfombraSvg}

      <!-- Mueble -->
      ${muebleSvg}

      <!-- Plantas reales y macetas -->
      ${plantasSvg}

      <!-- Decoración -->
      ${decoSvg}

      <!-- Lámpara ambiental -->
      ${lamparaSvg}
    </svg>
  `;
  ultimoSlotAnimado = null;

  if (legendEl) {
    if (plantas.length === 0) {
      legendEl.innerHTML = `<p class="text-muted text-sm" style="margin: 8px 0 0;">Registra una planta real en <strong>Agregar Planta</strong> para ver su estado vivo en tu habitación.</p>`;
    } else {
      legendEl.innerHTML = plantas.map(p => {
        const estado = p.estado_global || "SIN_DATOS";
        const emo = p.estado_emocional || "RADIANTE";
        const hp = p.hp !== undefined && p.hp !== null ? `${p.hp}/100 HP` : "Sin lecturas";
        const badgeCls = estado === "CRITICO" ? "critico" : (estado === "EN_RIESGO" ? "riesgo" : "saludable");
        return `
          <div class="room-plant-pill ${badgeCls}">
            <strong>${escapeHtml(p.nombre)}</strong>
            <span>${escapeHtml(emo)} · ${escapeHtml(hp)}</span>
          </div>`;
      }).join("");
    }
  }

  if (tabsEl) {
    tabsEl.innerHTML = CATEGORIAS_HABITACION.map(cat => `
      <button type="button"
        class="room-cat-tab ${categoriaHabitacionActiva === cat.id ? "active" : ""}"
        onclick="seleccionarCategoriaHabitacion('${cat.id}')">
        ${escapeHtml(cat.label)}
      </button>
    `).join("");
  }

  if (slotsOverviewEl) {
    slotsOverviewEl.innerHTML = Object.entries(ETIQUETAS_SLOT).map(([slotKey, slotLabel]) => {
      const objId = slots[slotKey];
      const art = objId ? catalogoMap[objId] : null;
      return `
        <div class="room-slot-chip ${art ? "equipped" : ""}">
          <span class="room-slot-chip-label">${escapeHtml(slotLabel)}:</span>
          <span class="room-slot-chip-val">${art ? escapeHtml(art.nombre) : "Vacío"}</span>
          ${art ? `<button type="button" class="room-slot-clear" title="Retirar ${escapeHtml(art.nombre)}" onclick="toggleObjetoHabitacion('${slotKey}', '', this)">✕</button>` : ""}
        </div>`;
    }).join("");
  }

  if (inventario.length === 0) {
    customizer.innerHTML = `
      <div class="room-empty-inv">
        <p class="text-muted">Aún no tienes objetos en tu inventario.</p>
        <button type="button" class="btn btn-primary btn-sm" onclick="navegar('tienda')">Ir a la Tienda</button>
      </div>`;
    return;
  }

  const filtrados = categoriaHabitacionActiva === "todos"
    ? inventario
    : inventario.filter(item => item.slot_habitacion === categoriaHabitacionActiva);

  if (filtrados.length === 0) {
    customizer.innerHTML = `<p class="text-muted text-sm">No tienes objetos adquiridos en esta categoría todavía.</p>`;
    return;
  }

  customizer.innerHTML = filtrados.map(item => {
    const colocado = slots[item.slot_habitacion] === item.objeto_id;
    const otroEnSlot = Boolean(slots[item.slot_habitacion] && !colocado);
    const rareza = item.rareza || "comun";
    const accionTxt = colocado ? "Retirar" : (otroEnSlot ? "Cambiar" : "Colocar");
    return `
      <div class="room-inv-item ${colocado ? "is-equipped" : ""}">
        <div class="room-inv-thumb">${obtenerSvgMiniaturaObjeto(item.objeto_id)}</div>
        <div class="room-inv-info">
          <div class="room-inv-title-row">
            <strong>${escapeHtml(item.nombre)}</strong>
            <span class="rarity-pill rarity-${escapeHtml(rareza)}">${escapeHtml(rareza)}</span>
          </div>
          <div class="text-muted text-sm">Espacio: ${escapeHtml(ETIQUETAS_SLOT[item.slot_habitacion] || item.slot_habitacion)}</div>
        </div>
        <button type="button" class="btn btn-sm ${colocado ? "btn-secondary" : "btn-primary"}"
          onclick="toggleObjetoHabitacion('${escapeHtml(item.slot_habitacion)}', '${colocado ? "" : escapeHtml(item.objeto_id)}', this)">
          ${accionTxt}
        </button>
      </div>
    `;
  }).join("");
}

async function toggleObjetoHabitacion(slot, objetoId, btnEl) {
  if (operacionesEnCurso.has("habitacion")) return;
  operacionesEnCurso.add("habitacion");
  if (btnEl) btnEl.disabled = true;

  try {
    const res = await apiFetch("/api/gamificacion/habitacion", {
      method: "PUT",
      body: JSON.stringify({ slots: { [slot]: objetoId || null } }),
    });
    if (res.ok) {
      ultimoSlotAnimado = slot;
      mostrarToast(objetoId ? "Objeto colocado en tu habitación." : "Objeto retirado de tu habitación.");
      await cargarGamificacionAvanzada();
    } else {
      mostrarToast(traducirErrorAmigable(res, "actualización de habitación"), "warning");
    }
  } finally {
    operacionesEnCurso.delete("habitacion");
    if (btnEl) btnEl.disabled = false;
  }
}
