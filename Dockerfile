FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

WORKDIR /app

RUN useradd --create-home --uid 10001 agent

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents ./agents
COPY core ./core
COPY tools ./tools
COPY config ./config
COPY main.py .
COPY pyproject.toml .

RUN mkdir -p /app/workspace /app/sandbox /app/memory /app/logs \
    && chown -R agent:agent /app

USER agent

CMD ["tail", "-f", "/dev/null"]
