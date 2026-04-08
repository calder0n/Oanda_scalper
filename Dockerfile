FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código fuente
COPY src/ ./src/

# Usuario no root
RUN useradd --create-home --shell /bin/bash trader
USER trader

CMD ["python", "-m", "src.main"]
