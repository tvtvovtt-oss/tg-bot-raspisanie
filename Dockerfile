FROM python:3.11-slim

WORKDIR /app

RUN addgroup --system bot && adduser --system --ingroup bot bot

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Часовой пояс техникума. По умолчанию контейнер живёт в UTC, из-за чего рассылки по времени
# уходили бы со сдвигом. Значение можно переопределить переменной TIMEZONE в .env.
ENV TZ=Europe/Moscow
ENV TIMEZONE=Europe/Moscow

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files without changing ownership at runtime
COPY --chown=bot:bot . .

# Data directory for SQLite database
RUN mkdir -p /app/data && chown -R bot:bot /app/data
ENV DATABASE_PATH=/app/data/bot.db

USER bot

# Run bot
CMD ["python", "bot.py"]
