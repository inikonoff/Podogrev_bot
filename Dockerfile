FROM python:3.11-slim

WORKDIR /app

# Копируем только requirements сначала для лучшего кэширования слоев
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY progrev_bot.py .

# Создаем непривилегированного пользователя
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Запускаем бота
CMD ["python", "progrev_bot.py"]
