FROM python:3.11-slim

# Не буферизовать stdout — логи сразу видны в Render
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Сначала только зависимости (кэшируется если код не менялся)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY progrev_bot.py .

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "progrev_bot:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info", "--workers", "1"]
