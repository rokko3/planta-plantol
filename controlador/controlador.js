// controlador.js - Clasificador de Estado de Salud sin almacenamiento de datos

document.addEventListener('DOMContentLoaded', () => {
    const evaluarForm = document.getElementById('evaluarForm');
    const categoryCard = document.getElementById('categoryCard');
    const categoryValue = document.getElementById('categoryValue');
    const evalInfo = document.getElementById('evalInfo');

    evaluarForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const especie = document.getElementById('especie').value;
        const luminosidad = document.getElementById('luminosidad').value.trim();
        const humedad = document.getElementById('humedad').value.trim();
        const temperatura = document.getElementById('temperatura').value.trim();

        if (!especie || luminosidad === '' || humedad === '' || temperatura === '') return;

        try {
            // Enviar petición POST al servidor Flask para clasificar
            const response = await fetch('/procesar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    especie: especie,
                    luminosidad: parseFloat(luminosidad),
                    humedad: parseFloat(humedad),
                    temperatura: parseFloat(temperatura)
                })
            });

            const data = await response.json();
            categoryCard.style.display = 'block';

            if (response.ok && data.success) {
                categoryValue.innerText = data.categoria_estado;

                // Personalizar colores según el estado
                if (data.categoria_estado.includes('Saludable')) {
                    categoryValue.style.background = 'rgba(16, 185, 129, 0.15)';
                    categoryValue.style.color = '#10b981';
                    categoryValue.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                } else if (data.categoria_estado.includes('Moderado')) {
                    categoryValue.style.background = 'rgba(245, 158, 11, 0.15)';
                    categoryValue.style.color = '#f59e0b';
                    categoryValue.style.borderColor = 'rgba(245, 158, 11, 0.3)';
                } else {
                    categoryValue.style.background = 'rgba(239, 68, 68, 0.15)';
                    categoryValue.style.color = '#ef4444';
                    categoryValue.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                }

                evalInfo.innerText = `Evaluado para ${data.datos_evaluados.especie} (${data.datos_evaluados.luminosidad} lm, ${data.datos_evaluados.humedad}%, ${data.datos_evaluados.temperatura}°C)`;
            } else {
                categoryValue.innerText = 'Error';
                categoryValue.style.background = 'rgba(239, 68, 68, 0.15)';
                categoryValue.style.color = '#ef4444';
                evalInfo.innerText = data.error || 'Ocurrió un error al clasificar';
            }
        } catch (err) {
            categoryCard.style.display = 'block';
            categoryValue.innerText = 'Error Servidor';
            categoryValue.style.background = 'rgba(239, 68, 68, 0.15)';
            categoryValue.style.color = '#ef4444';
            evalInfo.innerText = 'No se pudo comunicar con el servidor Flask';
        }
    });
});
