# pfSense Configuration Backup Tool

**Automatically backup multiple pfSense configurations with Docker**

A secure, production-ready Docker container that automatically backs up pfSense configurations from multiple instances with monitoring, notifications, and comprehensive error handling.

![pfSense Backup](https://img.shields.io/badge/pfSense-Backup-blue) ![Docker](https://img.shields.io/badge/Docker-Ready-green) ![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-orange)

## 🚀 Quick Start

**Get up and running in 5 minutes:**

```bash
# 1. Clone or download the project
git clone <your-repo-url> pfsense-backup
cd pfsense-backup

# 2. Copy the environment template
cp .env.example .env

# 3. Edit your credentials (see configuration section below)
nano .env

# 4. Start the backup service
docker-compose up -d

# 5. Check logs to verify everything is working
docker-compose logs -f
```

That's it! Your pfSense configurations will be automatically backed up daily at 2 AM.

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Monitoring & Notifications](#-monitoring--notifications)
- [Security](#-security)
- [Troubleshooting](#-troubleshooting)
- [Advanced Usage](#-advanced-usage)

## ✨ Features

### Core Features
- **🔄 Multi-instance Support** - Backup multiple pfSense firewalls simultaneously
- **⏰ Flexible Scheduling** - Daily, hourly, or weekly automated backups
- **🔐 Secure Credentials** - Environment variable-based credential management
- **📁 Smart File Management** - Automatic cleanup with configurable retention
- **🗜️ Compression Support** - Optional gzip compression to save space

### Monitoring & Alerting
- **📊 Prometheus Metrics** - Complete operational metrics on port 8000
- **🔔 Multi-webhook Notifications** - Discord, Slack, email, and health checks
- **📈 Success/Failure Tracking** - Detailed backup statistics and timing
- **🎯 Customizable Alerts** - Success-only, failure-only, or all notifications

### Enterprise Features
- **🐳 Docker Native** - Production-ready containerized deployment
- **🛡️ SSL/TLS Support** - Works with self-signed certificates
- **📝 Comprehensive Logging** - Detailed operation logs with configurable levels
- **🔧 Flexible Configuration** - YAML-based configuration with environment overrides

## 🔧 Installation

### Prerequisites
- Docker and Docker Compose installed
- Access to pfSense web interface (HTTPS)
- Network connectivity from container to pfSense instances

### Method 1: Docker Compose (Recommended)

1. **Download the project files:**
```bash
mkdir pfsense-backup && cd pfsense-backup
# Copy all provided files to this directory
```

2. **Set up your environment:**
```bash
cp .env.example .env
```

3. **Configure your credentials in `.env`:**
```bash
# pfSense Instance Credentials
POSEIDON_USERNAME=admin
POSEIDON_PASSWORD=your_secure_password_here
PROTEUS_USERNAME=admin
PROTEUS_PASSWORD=another_secure_password
```

4. **Start the service:**
```bash
docker-compose up -d
```

### Method 2: Docker Run

```bash
docker run -d \
  --name pfsense-backup \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/backups:/backups \
  -e POSEIDON_USERNAME=admin \
  -e POSEIDON_PASSWORD=password \
  -p 8000:8000 \
  pfsense-backup
```

## ⚙️ Configuration

### 1. pfSense Instance Configuration

Edit `config/config.yaml` to define your pfSense instances:

```yaml
pfsense_instances:
  - name: "main-firewall"                    # Unique name for this instance
    url: "https://192.168.1.1"              # pfSense web interface URL
    username_env: "MAIN_FW_USERNAME"         # Environment variable for username
    password_env: "MAIN_FW_PASSWORD"         # Environment variable for password
    subfolder: "main-fw"                     # Optional: organize backups in subfolders
    backup_prefix: "daily"                   # Optional: custom filename prefix
    verify_ssl: false                        # Set to true for valid SSL certificates
    timeout: 30                              # Connection timeout in seconds

  - name: "guest-firewall"
    url: "https://192.168.2.1"
    username_env: "GUEST_FW_USERNAME"
    password_env: "GUEST_FW_PASSWORD"
    subfolder: "guest-fw"
    backup_prefix: "daily"
    verify_ssl: false
    timeout: 30
```

### 2. Backup Settings

```yaml
backup:
  directory: "/backups"                      # Where to store backup files
  filename_format: "{prefix}_{instance_name}_{timestamp}.xml"
  timestamp_format: "%Y-%m-%d_%H-%M-%S"     # 2024-12-01_14-30-00
  retention_count: 30                       # Keep last 30 backups per instance
  compress: true                            # Enable gzip compression
```

### 3. Scheduling

```yaml
schedule:
  enabled: true                             # Enable automatic scheduling
  frequency: "daily"                        # Options: daily, hourly, weekly
```

### 4. Environment Variables (.env file)

```bash
# pfSense Credentials (match the *_env values in config.yaml)
MAIN_FW_USERNAME=admin
MAIN_FW_PASSWORD=your_password_here
GUEST_FW_USERNAME=admin
GUEST_FW_PASSWORD=another_password

# Optional: Override default paths
CONFIG_FILE=/app/config/config.yaml
BACKUP_DIR=/backups
```

## 🎯 Usage

### Basic Operations

```bash
# Start the backup service
docker-compose up -d

# Run backup once (no scheduling)
docker-compose run --rm pfsense-backup python src/backup_manager.py --once

# View logs
docker-compose logs -f pfsense-backup

# Stop the service
docker-compose down

# Check backup files
ls -la backups/
```

### Verify Your Setup

```bash
# Test connectivity to your pfSense instances
docker-compose run --rm pfsense-backup curl -k https://192.168.1.1

# Check configuration syntax
docker-compose run --rm pfsense-backup python -c "
import yaml
with open('/app/config/config.yaml') as f:
    config = yaml.safe_load(f)
print('Configuration is valid!')
"
```

## 📊 Monitoring & Notifications

### Prometheus Metrics

Access metrics at `http://localhost:8000/metrics` for monitoring:

- `pfsense_backup_total` - Total backup attempts
- `pfsense_backup_success_total` - Successful backups
- `pfsense_backup_duration_seconds` - Backup timing
- `pfsense_backup_file_size_bytes` - Backup file sizes
- Many more detailed metrics...

### Notification Setup

Configure multiple notification channels in `config.yaml`:

#### Discord Webhook
```yaml
notifications:
  enabled: true
  webhooks:
    - name: "discord_alerts"
      url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
      trigger: "always"  # success, failure, or always
      message_format: "🔄 pfSense Backup: {status} - {details}"
```

#### Health Checks (Uptime Monitoring)
```yaml
    - name: "healthcheck"
      url: "https://hc-ping.com/your-check-id"
      trigger: "success"
```

#### Slack Webhook
```yaml
    - name: "slack_alerts"
      url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
      trigger: "failure"
      payload_template:
        text: "{message}"
        channel: "#alerts"
```

## 🔒 Security

### Best Practices Implemented

- **No hardcoded credentials** - All passwords via environment variables
- **Non-root container** - Runs as unprivileged user
- **SSL support** - Handles self-signed certificates properly
- **CSRF protection** - Automatic CSRF token handling
- **Read-only configs** - Configuration files mounted read-only

### Recommended Security Measures

1. **Use strong passwords** for pfSense accounts
2. **Restrict network access** - Only allow backup container IPs
3. **Enable pfSense firewall rules** for management interface
4. **Regularly rotate credentials**
5. **Monitor backup logs** for unauthorized access attempts

## 🐛 Troubleshooting

### Common Issues and Solutions

#### 1. 403 Forbidden Errors

**Most common causes:**
- **Wrong credentials** - Double-check username/password in `.env`
- **IP blocking** - pfSense firewall blocking container IP
- **Rate limiting** - Too many failed login attempts

**Solutions:**
```bash
# Test credentials manually
docker-compose run --rm pfsense-backup curl -k -d "login=Login&usernamefld=admin&passwordfld=password" https://192.168.1.1/index.php

# Check pfSense logs
# In pfSense: Status → System Logs → System

# Enable debug logging
# Set logging level to DEBUG in config.yaml
```

#### 2. Connection Refused/Timeout

**Check network connectivity:**
```bash
# Test basic connectivity
docker-compose run --rm pfsense-backup ping 192.168.1.1

# Test HTTPS port
docker-compose run --rm pfsense-backup curl -k -m 10 https://192.168.1.1
```

**pfSense Configuration Checklist:**
- ✅ HTTPS web interface enabled (System → Advanced → Admin Access)
- ✅ Web interface accessible from backup server IP
- ✅ Firewall rules allow HTTPS (port 443) from backup server
- ✅ Anti-lockout rule enabled (System → Advanced → Admin Access)

#### 3. Authentication Issues

```bash
# Test with debug mode
docker-compose run --rm pfsense-backup python src/backup_manager.py --once --debug

# Check if login page is accessible
docker-compose run --rm pfsense-backup curl -k -v https://192.168.1.1/index.php | grep -i login
```

#### 4. Permission Errors

```bash
# Check backup directory permissions
ls -la backups/

# Fix permissions if needed
sudo chown -R 1000:1000 backups/
sudo chmod 755 backups/
```

### Enable Debug Mode

Add to `config.yaml`:
```yaml
logging:
  level: "DEBUG"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### Getting Help

1. **Check logs first:**
   ```bash
   docker-compose logs -f pfsense-backup
   ```

2. **Test individual components:**
   ```bash
   # Test config loading
   docker-compose run --rm pfsense-backup python -c "
   import src.backup_manager
   mgr = src.backup_manager.PfSenseBackupManager('/app/config/config.yaml')
   print('Config loaded successfully')
   "
   ```

3. **Manual backup test:**
   ```bash
   docker-compose run --rm pfsense-backup python src/backup_manager.py --once
   ```

## 🔧 Advanced Usage

### Custom Scheduling with Cron

Instead of built-in scheduling, use host cron for more control:

```bash
# Disable scheduling in config.yaml
schedule:
  enabled: false

# Add to host crontab
# Backup every day at 2 AM
0 2 * * * cd /path/to/pfsense-backup && docker-compose run --rm pfsense-backup python src/backup_manager.py --once

# Backup every 6 hours
0 */6 * * * cd /path/to/pfsense-backup && docker-compose run --rm pfsense-backup python src/backup_manager.py --once
```

### Integration with Monitoring Stack

**Grafana Dashboard:**
Import metrics from Prometheus endpoint for visualization.

**Alertmanager Rules:**
```yaml
# Example alert for backup failures
- alert: PfSenseBackupFailed
  expr: increase(pfsense_backup_failed_total[1h]) > 0
  for: 5m
  annotations:
    summary: "pfSense backup failed for {{ $labels.instance }}"
```

### Backup to Remote Storage

Mount cloud storage or network shares:

```yaml
# docker-compose.yml
volumes:
  - "/mnt/nfs-backup:/backups"  # NFS mount
  - "/mnt/s3fs:/backups"        # S3 filesystem
```

### Multiple Environment Setup

**Production:**
```bash
cp config.yaml config-prod.yaml
CONFIG_FILE=/app/config/config-prod.yaml docker-compose up -d
```

**Development:**
```bash
cp config.yaml config-dev.yaml
CONFIG_FILE=/app/config/config-dev.yaml docker-compose up -d
```

## 📁 File Structure

```
pfsense-backup/
├── 📄 README.md                 # This documentation
├── 🐳 Dockerfile               # Container definition
├── 🐳 docker-compose.yml       # Service orchestration
├── 📦 requirements.txt         # Python dependencies
├── 🔐 .env.example             # Environment template
├── 📁 config/
│   └── ⚙️ config.yaml         # Main configuration
├── 📁 src/
│   ├── 🐍 backup_manager.py   # Main backup logic
│   └── 📊 prometheus_metrics.py # Metrics collection
└── 📁 backups/                 # Backup storage (created automatically)
    ├── 📄 main-fw_main-firewall_2024-12-01_14-30-00.xml.gz
    └── 📄 guest-fw_guest-firewall_2024-12-01_14-30-00.xml.gz
```