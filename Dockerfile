FROM python:3.11-slim

# Install required system packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY src/ ./src/
COPY config/ ./config/

# Create backup directory
RUN mkdir -p /backups

# Create non-root user for security
RUN useradd -m -u 1000 pfsense-backup && \
    chown -R pfsense-backup:pfsense-backup /app /backups
USER pfsense-backup

# Set environment variables
ENV PYTHONPATH=/app
ENV CONFIG_FILE=/app/config/config.yaml
ENV BACKUP_DIR=/backups

# Default command
CMD ["python", "src/backup_manager.py"]