# Use official Python image
FROM python:3.10-slim

# Flush Python stdout immediately so docker logs show print() output
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install cron and set up daily job
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
RUN cp scripts/crontab /etc/cron.d/trading-bot \
    && chmod 0644 /etc/cron.d/trading-bot \
    && mkdir -p /app/logs

RUN chmod +x /app/docker-entrypoint.sh

# Expose port
EXPOSE 8000

CMD ["/app/docker-entrypoint.sh"]
