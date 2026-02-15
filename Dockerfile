# Используем легкий образ Python
FROM python:3.11-slim

# Устанавливаем переменные окружения
# PYTHONDONTWRITEBYTECODE - не создавать .pyc файлы
# PYTHONUNBUFFERED - выводить логи сразу в консоль
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем зависимости системы (нужны для сборки некоторых python пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python-библиотеки
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем остальной код проекта
COPY . .

# Создаем папку для логов
RUN mkdir -p logs

# Открываем порт 8000 (стандартный для Uvicorn/FastAPI)
EXPOSE 8000

# Команда запуска
# --host 0.0.0.0 - важно для доступа извне контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]