FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root (optionnel)
RUN useradd -m portal && chown -R portal:portal /app
USER portal

EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "wsgi:app"]