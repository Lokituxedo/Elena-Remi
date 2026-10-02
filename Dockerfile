FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema.sql perfil.txt elena_app.py import_memoria.py ./
RUN mkdir -p /app/audio /app/data

ENV ELENA_PORT=8099 \
    ELENA_BIND=0.0.0.0 \
    ELENA_DB=/app/data/elena.db \
    ELENA_AUDIO=/app/audio \
    ELENA_VOZ=es-AR-ElenaNeural \
    ELENA_SILENCIO_SEG=90

EXPOSE 8099
VOLUME ["/app/data", "/app/audio"]
CMD ["python", "-u", "elena_app.py"]
