FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY --chown=app:app backend backend
COPY --chown=app:app frontend frontend
RUN mkdir -p /opt/dashvanti_fs /tmp/dashvanti_sessions && chown -R app:app /opt/dashvanti_fs /tmp/dashvanti_sessions
USER app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
