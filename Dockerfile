FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Overridden per-service (bot/web/scheduler) by the `command:` in docker-compose.yml.
CMD ["python", "bot.py"]
