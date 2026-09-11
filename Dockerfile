FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Data directory for SQLite database
RUN mkdir -p /app/data
ENV DATABASE_PATH=/app/data/bot.db

# Run bot
CMD ["python", "bot.py"]
