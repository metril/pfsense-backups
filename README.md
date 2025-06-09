# pfSense Configuration Backup Docker Container

A secure Docker container solution for automatically backing up pfSense configurations from multiple instances.

## Features

- **Multi-instance support**: Backup configurations from multiple pfSense instances
- **Secure credential management**: Uses environment variables for credentials
- **Flexible scheduling**: Support for scheduled backups (daily, hourly, weekly)
- **Configurable retention**: Automatic cleanup of old backup files
- **Compression support**: Optional gzip compression of backup files
- **Notification support**: Webhook notifications for backup status
- **SSL/TLS support**: Works with self-signed certificates
- **Docker-based**: Easy deployment and management

## Quick Start

1. **Clone or create the project structure**:
```bash
mkdir pfsense-backup && cd pfsense-backup
# Copy all the provided files into this directory
```

2. **Configure your instances** by editing `config/config.yaml`:
```yaml
pfsense_instances:
  - name: "main-firewall"
    url: "https://192.168.1.1"
    username_env: "PFSENSE_MAIN_FIREWALL_USERNAME"
    password_env: "PFSENSE_MAIN_FIREWALL_PASSWORD"
    backup_prefix: "main-fw"
```

3. **Set up credentials**:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

4. **Build and run**:
```bash
docker-compose up -d
```

## Configuration

### Instance Configuration (`config/config.yaml`)

Each pfSense instance requires:
- `name`: Unique identifier for the instance
- `url`: Full URL to the pfSense web interface
- `username_env`: Environment variable name containing the username
- `password_env`: Environment variable name containing the password

Optional settings:
- `backup_prefix`: Custom prefix for backup filenames
- `verify_ssl`: Whether to verify SSL certificates (default: false)
- `timeout`: Connection timeout in seconds (default: 30)

### Backup Configuration

Configure backup behavior:
```yaml
backup:
  directory: "/backups"
  filename_format: "{prefix}_{instance_name}_{timestamp}.xml"
  timestamp_format: "%Y%m%d_%H%M%S"
  retention_count: 10  # Keep last 10 backups per instance
  compress: true       # Gzip compression
```

### Scheduling

Enable automatic backups:
```yaml
schedule:
  enabled: true
  frequency: "daily"  # daily, hourly, weekly
```

### Notifications

Get notified of backup status:
```yaml
notifications:
  enabled: true
  webhook_url: "https://hooks.slack.com/your/webhook/url"
  notify_success: true
  notify_failure: true
```

## Security Features

- **Environment-based credentials**: Passwords are never stored in configuration files
- **Non-root container**: Runs as unprivileged user for security
- **Read-only configuration**: Config files can be mounted read-only
- **SSL verification**: Optional SSL certificate verification
- **Secure authentication**: Proper CSRF token handling

## Usage Examples

### Run once (no scheduling):
```bash
docker-compose run --rm pfsense-backup python src/backup_manager.py --once
```

### Run with custom configuration:
```bash
docker run --rm \
  -v /path/to/config.yaml:/app/config/config.yaml:ro \
  -v /path/to/backups:/backups \
  -e PFSENSE_MAIN_FIREWALL_USERNAME=admin \
  -e PFSENSE_MAIN_FIREWALL_PASSWORD=password \
  pfsense-backup python src/backup_manager.py --once
```

### Check logs:
```bash
docker-compose logs -f pfsense-backup
```

## File Structure

```
pfsense-backup/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── config/
│   └── config.yaml
├── src/
│   └── backup_manager.py
└── backups/          # Created automatically
    ├── main-fw_main-firewall_20241201_120000.xml.gz
    └── guest-fw_guest-firewall_20241201_120000.xml.gz
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `PFSENSE_*_USERNAME` | Username for pfSense instance | Yes |
| `PFSENSE_*_PASSWORD` | Password for pfSense instance | Yes |
| `CONFIG_FILE` | Path to configuration file | No |
| `BACKUP_DIR` | Backup directory path | No |

## Backup Filename Format

Backups are saved with customizable filenames:
- Default: `{prefix}_{instance_name}_{timestamp}.xml`
- With compression: `{prefix}_{instance_name}_{timestamp}.xml.gz`
- Timestamp format: `YYYYMMDD_HHMMSS`

## Troubleshooting

### 403 Forbidden Errors

If you're getting 403 errors during login, try these steps:

1. **Test connectivity first**:
```bash
docker-compose run --rm pfsense-backup python src/backup_manager.py --test
```

2. **Enable debug mode**:
```bash
docker-compose run --rm pfsense-backup python src/backup_manager.py --debug
```

3. **Common causes of 403 errors**:
   - **Incorrect credentials**: Double-check username/password
   - **IP-based restrictions**: pfSense may have firewall rules blocking the container's IP
   - **Login attempt rate limiting**: pfSense may temporarily block after failed attempts
   - **CSRF token issues**: The script handles multiple CSRF patterns automatically
   - **Web interface disabled**: Ensure HTTPS web interface is enabled in pfSense

4. **pfSense configuration checklist**:
   - System → Advanced → Admin Access: Ensure "WebGUI" protocol is HTTPS
   - System → Advanced → Admin Access: Check "WebGUI redirect" settings  
   - Firewall → Rules: Ensure management interface allows HTTPS from backup container
   - System → Advanced → Admin Access: Verify "Anti-lockout rule" is enabled

5. **Network troubleshooting**:
```bash
# Test from container
docker-compose run --rm pfsense-backup curl -k https://192.168.1.1

# Check if pfSense login page is accessible
docker-compose run --rm pfsense-backup curl -k -v https://192.168.1.1/index.php
```

### Common Issues

1. **Authentication failures**: Verify credentials and pfSense URL
2. **SSL certificate errors**: Set `verify_ssl: false` for self-signed certificates
3. **Permission denied**: Ensure backup directory is writable
4. **Network connectivity**: Check firewall rules and network access

### Debug Mode

Enable debug logging in config:
```yaml
logging:
  level: "DEBUG"
```

Or run with debug flag:
```bash
docker-compose run --rm pfsense-backup python src/backup_manager.py --debug
```

### Testing Individual Components

```bash
# Test connectivity only
docker-compose run --rm pfsense-backup python src/backup_manager.py --test

# Test configuration loading
docker-compose run --rm pfsense-backup python -c "import src.backup_manager; print('Config OK')"

# Test single instance backup
docker-compose run --rm pfsense-backup python src/backup_manager.py --once
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is released under the MIT License.

## Security Notice

- Keep your `.env` file secure and never commit it to version control
- Use strong passwords for pfSense instances
- Regularly rotate credentials
- Monitor backup logs for any security issues
- Consider using network segmentation for backup access