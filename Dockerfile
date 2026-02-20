# Используем официальный Python
FROM python:3.11-slim

# Устанавливаем рабочую папку
WORKDIR /app

# Копируем все файлы
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python", "bot.py"]