# Informe del trabajo nocturno (01/11/2026)

| Prueba | Resultado |
|---|---|
| Restaurar el respaldo en una base temporal | Correcto: mismas cantidades en manuales, imágenes, páginas, índice y usuarios |
| Examen, 100 preguntas, página correcta | Antes 85, después 89. Mejoran 8, empeoran 4 |
| Bienvenida indebida en respuestas directas | Antes 15, después 0 |
| Tiempo promedio de respuesta en el examen | Antes 3,6 s, después 3,2 s |
| Prueba rápida (`examen/prueba_rapida.py`) | 29 de 29 |

## Carga simultánea

Una sola ronda por nivel, medida directamente contra el asistente y sin pasar por el inicio de sesión ni el portal.

| Preguntas a la vez | Correctas | Mediana | Máximo |
|---|---|---|---|
| 3 | 3 | 3,6 s | 4,7 s |
| 5 | 5 | 4,7 s | 6,1 s |
| 10 | 10 | 7,7 s | 10,0 s |
| 15 | 15 | 10,0 s | 12,6 s |

No se probó por encima de 15 ni de forma sostenida. Tampoco mide los límites de cuota de Gemini y Groq a largo plazo.

## Cambios

- Búsqueda: ventaja al fragmento cuyo título de sección aparece completo en la pregunta (`PESO_SECCION`).
- Respuestas: se quita la bienvenida si el cliente no saludó.
- Pruebas: 6 controles nuevos de seguridad y portal; `analisis/evaluar_nube.py` y `migracion/examen_nube.ps1`.
- Respaldos: solo root puede leerlos.

## Límites conocidos

- "Registro de comprobantes de percepción y detracción" no parece tener contenido propio en el manual de caja y
  bancos: el índice los ubica en la página 21, junto con otros temas. Conviene revisarlo con quien mantiene el manual.
- El examen mide si se citó la página correcta, no si cada paso de la respuesta es correcto.
- Sin probar: laptop apagada, reinicio real del servidor y micrófono tras los últimos cambios.

## Revisión posterior (mañana del 01/11/2026)

Cambio publicado: la búsqueda lee también la página anterior a la encontrada, porque una sección que empieza a media
página queda etiquetada con la sección previa.

| Prueba | Antes | Después |
|---|---|---|
| Examen, 100 preguntas, página correcta | 89 | 92 (mejoran 4, empeora 1) |
| "Anular cotización" (3 redacciones, 4 veces cada una): cita el Manual de Ventas | 9 de 12 | 12 de 12 |
| "Anular cotización": cita la página 28, donde están los pasos 1 y 2 | Sin medir | 8 de 12 |
| Prueba rápida | 29 de 29 | 29 de 29 |

Parte de esas mejoras puede ser variación de la IA: el examen es una sola pasada por pregunta. Empeoró "En Notas de
ingreso, ¿cómo modifico un registro?" (dijo que no tiene la información); no se repitió para saber si es variación.

- **Backup:** corrección a lo informado antes. El cambio de búsqueda no lo causó: los resultados son iguales con y
  sin él. La guía `BACKUP` no trae un procedimiento: son capturas de SQL Server con nombres de clientes (secciones como
  FRUTARON o PROASSA), usuarios y direcciones de servidor. Decir que no hay información es correcto. Por ese riesgo se
  retiró de la nube (fragmentos, índice, imágenes y páginas) y quedó excluida en `leer_manuales.py`. El PDF sigue en
  la laptop y en los respaldos del servidor de hasta 7 días.
- **Percepción y detracción:** hueco confirmado. El manual de caja y bancos remite a documentos externos
  (`PROC-COMPROB. PERCEPCION PROVEEDOR.DOC` y `PROC-COMPROB. DETRACCION PROVEEDOR.DOC`). Falta conseguirlos y cargarlos.
- **Error en el manual:** en Cotizaciones, 2.4 Anular (página 28), el paso 2 dice pulsar **[Modificar]**. Conviene
  que lo revise quien lo mantiene.

Decisiones pendientes: ver `migracion/PENDIENTES_INGENIERO.md`.
