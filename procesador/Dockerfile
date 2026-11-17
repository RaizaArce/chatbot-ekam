# Procesador de manuales de NAVASOFT (ver app.py). Se construye en el servidor con migracion/desplegar_procesador.ps1
FROM python:3.12-slim

# LibreOffice para pasar los Word a PDF; fuentes para escribir los datos ficticios; librerias que pide el OCR
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-liberation fonts-dejavu-core \
        libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

ENV NAVASOFT_DATOS=/data \
    MANUALES_DIR=/data/originales \
    NAVASOFT_FUENTE=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
    NAVASOFT_FUENTE_RESPALDO=/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

EXPOSE 8080
CMD ["python", "app.py"]
