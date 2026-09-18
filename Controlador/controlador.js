const API_BASE = "http://127.0.0.1:5000";

async function cargarEspecies() {
    const select = document.getElementById("especie");
    try {
        const resp = await fetch(`${API_BASE}/api/especies`);
        if (!resp.ok) throw new Error("No se pudo cargar el listado de especies.");
        const especies = await resp.json();

        select.innerHTML = '<option value="" disabled selected>-- Selecciona una especie --</option>';
        especies.forEach(e => {
            const opt = document.createElement("option");
            opt.value = e.nombre;
            opt.dataset.rangos = JSON.stringify(e.rangos);
            opt.textContent = e.nombre;
            select.appendChild(opt);
        });
    } catch (err) {
        select.innerHTML = '<option value="" disabled selected>Error al cargar especies</option>';
        console.error(err);
    }
}

function mostrarRangos(select) {
    const rangosInfo = document.getElementById("rangosInfo");
    const rangosNombre = document.getElementById("rangosNombre");
    const rangosTexto = document.getElementById("rangosTexto");

    const opt = select.options[select.selectedIndex];
    if (!opt || !opt.dataset.rangos) {
        rangosInfo.style.display = "none";
        return;
    }

    const r = JSON.parse(opt.dataset.rangos);
    rangosNombre.textContent = opt.value;
    rangosTexto.textContent =
        `Luz: ${r.luminosidad.min}–${r.luminosidad.max} lux · ` +
        `Humedad: ${r.humedad.min}–${r.humedad.max}% · ` +
        `Temperatura: ${r.temperatura.min}–${r.temperatura.max}°C`;
    rangosInfo.style.display = "block";
}

document.addEventListener("DOMContentLoaded", () => {
    cargarEspecies();

    const selectEspecie = document.getElementById("especie");
    selectEspecie.addEventListener("change", () => mostrarRangos(selectEspecie));

    const form = document.getElementById("evaluarForm");
    const resultCard = document.getElementById("resultCard");
    const errorCard = document.getElementById("errorCard");

    form.addEventListener("submit", async (e) => {
        e.preventDefault(); // Evita recargar la pagina para mantener la navegacion asincrona
        resultCard.style.display = "none";
        errorCard.style.display = "none";

        const especie = document.getElementById("especie").value;
        const luminosidad = parseFloat(document.getElementById("luminosidad").value);
        const humedad = parseFloat(document.getElementById("humedad").value);
        const temperatura = parseFloat(document.getElementById("temperatura").value);

        const btn = document.getElementById("btnEvaluar");
        btn.disabled = true;

        try {
            const resp = await fetch(`${API_BASE}/api/diagnostico`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ especie, luminosidad, humedad, temperatura }),
            });

            const data = await resp.json();

            if (resp.ok && data.success) {
                mostrarResultado(data);
            } else {
                mostrarError(data);
            }
        } catch (err) {
            mostrarError({
                error: "ERROR_RED",
                mensaje: "No se pudo comunicar con el servidor. Verifica que el backend esté corriendo.",
            });
        } finally {
            btn.disabled = false;
        }
    });
});

function mostrarResultado(data) {
    const resultCard = document.getElementById("resultCard");
    const estadoBadge = document.getElementById("estadoBadge");
    const parametrosGrid = document.getElementById("parametrosGrid");

    estadoBadge.textContent = data.estado_global;
    estadoBadge.className = "estado-badge estado-" + data.estado_global.toLowerCase().replace(/_/g, "_");

    parametrosGrid.innerHTML = "";
    (data.parametros || []).forEach(p => {
        const cls = p.clasificacion.toLowerCase();
        const row = document.createElement("div");
        row.className = "param-row";
        row.innerHTML = `
            <span class="param-nombre">${p.nombre}</span>
            <span class="param-valor">${p.valor}</span>
            <span class="param-cls cls-${cls}">${p.clasificacion}</span>
            <span class="param-reco">${p.recomendacion || "✓ En rango óptimo"}</span>
        `;
        parametrosGrid.appendChild(row);
    });

    resultCard.style.display = "flex";
}

function mostrarError(data) {
    document.getElementById("errorCodigo").textContent = data.error || "ERROR";
    document.getElementById("errorMensaje").textContent = data.mensaje || "Ocurrió un error inesperado.";
    document.getElementById("errorCard").style.display = "block";
}
