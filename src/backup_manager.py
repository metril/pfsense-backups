#!/usr/bin/env python3
"""
pfSense Configuration Backup Manager
Securely backs up pfSense configurations from multiple instances
Enhanced with multiple webhook notification support
"""

import os
import sys
import yaml
import requests
import logging
import gzip
import shutil
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import schedule
import time
from urllib.parse import urljoin
import urllib3
import re
import json

# Import Prometheus metrics
from prometheus_metrics import get_metrics_instance, MetricsTimer

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PfSenseBackupManager:
    def __init__(self, config_file: str):
        self.config = self._load_config(config_file)
        self._setup_logging()
        self.backup_dir = Path(os.getenv('BACKUP_DIR', self.config['backup']['directory']))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Prometheus metrics
        metrics_config = self.config.get('metrics', {})
        metrics_port = metrics_config.get('port', 8000)
        self.metrics = get_metrics_instance(port=metrics_port)
        
        # Set configured instances count
        self.metrics.set_configured_instances(len(self.config['pfsense_instances']))
        
        # Get hostname for notifications
        self.hostname = os.getenv('HOSTNAME', socket.gethostname())
        
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"Error loading config file {config_file}: {e}")
            sys.exit(1)
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_config = self.config.get('logging', {})
        level = getattr(logging, log_config.get('level', 'INFO').upper())
        format_str = log_config.get('format', '%(asctime)s - %(levelname)s - %(message)s')
        
        logging.basicConfig(level=level, format=format_str)
        self.logger = logging.getLogger(__name__)
    
    def _get_credentials(self, instance: Dict) -> tuple:
        """Safely retrieve credentials from environment variables"""
        username = os.getenv(instance['username_env'])
        password = os.getenv(instance['password_env'])
        
        if not username or not password:
            raise ValueError(f"Missing credentials for {instance['name']}. "
                           f"Set {instance['username_env']} and {instance['password_env']} environment variables.")
        
        return username, password
    
    def _get_instance_backup_dir(self, instance: Dict) -> Path:
        """Get the backup directory for a specific instance, creating subdirectory if specified"""
        subfolder = instance.get('subfolder', '')
        
        if subfolder:
            instance_backup_dir = self.backup_dir / subfolder
            instance_backup_dir.mkdir(parents=True, exist_ok=True)
            return instance_backup_dir
        else:
            return self.backup_dir
    
    def _authenticate_pfsense(self, session: requests.Session, instance: Dict) -> bool:
        """Authenticate with pfSense instance"""
        username, password = self._get_credentials(instance)
        instance_name = instance['name']
        
        with MetricsTimer(self.metrics, instance_name, 'auth') as timer:
            try:
                login_url = urljoin(instance['url'], '/index.php')
                response = session.get(
                    login_url, 
                    verify=instance.get('verify_ssl', False),
                    timeout=instance.get('timeout', 30)
                )
                response.raise_for_status()
                
                self.metrics.record_network_request(instance_name, 'login_page', response.status_code)
                
                csrf_token = None
                if '__csrf_magic' in response.text:
                    csrf_match = re.search(r'name=[\'"]__csrf_magic[\'"][^>]*value=[\'"]([^\'"]*)[\'"]', response.text)
                    if csrf_match:
                        csrf_token = csrf_match.group(1)
                
                login_data = {
                    'login': 'Login',
                    'usernamefld': username,
                    'passwordfld': password                    
                }
                
                if csrf_token:
                    login_data['__csrf_magic'] = csrf_token
                
                response = session.post(
                    login_url,
                    data=login_data,
                    verify=instance.get('verify_ssl', False),
                    timeout=instance.get('timeout', 30),
                    allow_redirects=True
                )
                
                self.metrics.record_network_request(instance_name, 'login', response.status_code)
                
                if 'Dashboard' in response.text or 'logout.php' in response.text:
                    self.logger.info(f"Successfully authenticated to {instance['name']}")
                    self.metrics.record_auth_attempt(instance_name, True, timer.get_duration())
                    return True
                else:
                    self.logger.error(f"Authentication failed for {instance['name']}")
                    self.metrics.record_auth_attempt(instance_name, False, timer.get_duration())
                    return False
                    
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"Connection error during authentication for {instance['name']}: {e}")
                self.metrics.record_network_error(instance_name, 'connection_error')
                self.metrics.record_auth_attempt(instance_name, False, timer.get_duration())
                return False
            except requests.exceptions.Timeout as e:
                self.logger.error(f"Timeout error during authentication for {instance['name']}: {e}")
                self.metrics.record_network_error(instance_name, 'timeout_error')
                self.metrics.record_auth_attempt(instance_name, False, timer.get_duration())
                return False
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Network error during authentication for {instance['name']}: {e}")
                self.metrics.record_network_error(instance_name, 'request_error')
                self.metrics.record_auth_attempt(instance_name, False, timer.get_duration())
                return False
            except Exception as e:
                self.logger.error(f"Authentication error for {instance['name']}: {e}")
                self.metrics.record_auth_attempt(instance_name, False, timer.get_duration())
                return False
    
    def _download_config(self, session: requests.Session, instance: Dict) -> Optional[str]:
        """Download configuration backup from pfSense"""
        instance_name = instance['name']
        
        with MetricsTimer(self.metrics, instance_name, 'download'):
            try:
                backup_url = urljoin(instance['url'], '/diag_backup.php')
                
                response = session.get(
                    backup_url,
                    verify=instance.get('verify_ssl', False),
                    timeout=instance.get('timeout', 30)
                )
                response.raise_for_status()
                
                self.metrics.record_network_request(instance_name, 'backup_page', response.status_code)
                
                csrf_token = None
                if '__csrf_magic' in response.text:
                    csrf_match = re.search(r'name=[\'"]__csrf_magic[\'"][^>]*value=[\'"]([^\'"]*)[\'"]', response.text)
                    if csrf_match:
                        csrf_token = csrf_match.group(1)
                
                backup_data = {
                    'download': 'download',
                    'donotbackuprrd': 'yes',
                    'backupssh': 'yes'
                }
                
                if csrf_token:
                    backup_data['__csrf_magic'] = csrf_token
                
                response = session.post(
                    backup_url,
                    data=backup_data,
                    verify=instance.get('verify_ssl', False),
                    timeout=instance.get('timeout', 30)
                )
                response.raise_for_status()
                
                self.metrics.record_network_request(instance_name, 'backup_download', response.status_code)
                
                if response.headers.get('content-type', '').startswith('text/xml') or \
                   response.text.strip().startswith('<?xml'):
                    self.logger.info(f"Successfully downloaded config from {instance['name']}")
                    return response.text
                else:
                    self.logger.error(f"Unexpected response format from {instance['name']}")
                    return None
                    
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"Connection error during config download for {instance['name']}: {e}")
                self.metrics.record_network_error(instance_name, 'connection_error')
                return None
            except requests.exceptions.Timeout as e:
                self.logger.error(f"Timeout error during config download for {instance['name']}: {e}")
                self.metrics.record_network_error(instance_name, 'timeout_error')
                return None
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Network error during config download for {instance['name']}: {e}")
                self.metrics.record_network_error(instance_name, 'request_error')
                return None
            except Exception as e:
                self.logger.error(f"Config download error for {instance['name']}: {e}")
                return None
    
    def _generate_filename(self, instance: Dict) -> str:
        """Generate backup filename"""
        timestamp = datetime.now().strftime(self.config['backup']['timestamp_format'])
        prefix = instance.get('backup_prefix', instance['name'])
        
        filename = self.config['backup']['filename_format'].format(
            prefix=prefix,
            instance_name=instance['name'],
            timestamp=timestamp
        )
        
        return filename
    
    def _save_backup(self, content: str, instance: Dict) -> bool:
        """Save backup content to file"""
        instance_name = instance['name']
        
        try:
            filename = self._generate_filename(instance)
            instance_backup_dir = self._get_instance_backup_dir(instance)
            filepath = instance_backup_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            original_size = filepath.stat().st_size
            
            if self.config['backup'].get('compress', False):
                compressed_filepath = filepath.with_suffix(filepath.suffix + '.gz')
                with open(filepath, 'rb') as f_in:
                    with gzip.open(compressed_filepath, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                compressed_size = compressed_filepath.stat().st_size
                compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
                self.metrics.set_compression_ratio(instance_name, compression_ratio)
                
                filepath.unlink()
                filepath = compressed_filepath
                self.logger.info(f"Compressed backup saved: {filepath}")
                self.metrics.backup_file_size_bytes.labels(instance=instance_name).set(compressed_size)
            else:
                self.logger.info(f"Backup saved: {filepath}")
                self.metrics.backup_file_size_bytes.labels(instance=instance_name).set(original_size)
            
            cleaned_count = self._cleanup_old_backups(instance)
            if cleaned_count > 0:
                self.metrics.record_files_cleaned(instance_name, cleaned_count)
            
            self._update_retained_files_count(instance)
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving backup for {instance['name']}: {e}")
            return False
    
    def _cleanup_old_backups(self, instance: Dict) -> int:
        """Remove old backup files based on retention policy"""
        retention_count = self.config['backup'].get('retention_count', 0)
        if retention_count <= 0:
            return 0
        
        try:
            instance_backup_dir = self._get_instance_backup_dir(instance)
            prefix = instance.get('backup_prefix', instance['name'])
            pattern = f"{prefix}_{instance['name']}_*"
            
            backup_files = list(instance_backup_dir.glob(pattern))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            files_to_remove = backup_files[retention_count:]
            removed_count = 0
            
            for file_path in files_to_remove:
                file_path.unlink()
                self.logger.info(f"Removed old backup: {file_path}")
                removed_count += 1
            
            return removed_count
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old backups for {instance['name']}: {e}")
            return 0
    
    def _update_retained_files_count(self, instance: Dict):
        """Update the count of retained files for metrics"""
        try:
            instance_backup_dir = self._get_instance_backup_dir(instance)
            prefix = instance.get('backup_prefix', instance['name'])
            pattern = f"{prefix}_{instance['name']}_*"
            
            backup_files = list(instance_backup_dir.glob(pattern))
            self.metrics.set_files_retained(instance['name'], len(backup_files))
        except Exception as e:
            self.logger.error(f"Error updating retained files count for {instance['name']}: {e}")
    
    def _format_notification_message(self, webhook_config: Dict, is_success: bool, details: str, failed_instances: List[str] = None) -> str:
        """Format notification message based on webhook configuration"""
        message_settings = self.config.get('notifications', {}).get('message_settings', {})
        
        # Determine status
        status = "SUCCESS" if is_success else "FAILURE"
        
        # Get message format
        message_format = webhook_config.get('message_format', "{status}: pfSense backup completed. {details}")
        
        # Build base message
        message = message_format.format(
            status=status,
            details=details
        )
        
        # Add instance details if requested
        if webhook_config.get('include_instance_details', False) and failed_instances:
            message += f"\nFailed instances: {', '.join(failed_instances)}"
        
        # Add timestamp if requested
        if message_settings.get('include_timestamp', True):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            message += f"\nTimestamp: {timestamp}"
        
        # Add hostname if requested
        if message_settings.get('include_hostname', True):
            message += f"\nHost: {self.hostname}"
        
        # Truncate if too long
        max_length = message_settings.get('max_length', 1000)
        if len(message) > max_length:
            message = message[:max_length - 3] + "..."
        
        return message
    
    def _send_webhook_notification(self, webhook_config: Dict, message: str):
        """Send notification to a single webhook"""
        webhook_name = webhook_config.get('name', 'unnamed')
        webhook_url = webhook_config['url']
        timeout = webhook_config.get('timeout', 10)
        
        try:
            # Expand environment variables in URL
            webhook_url = os.path.expandvars(webhook_url)
            
            # Prepare headers
            headers = {'Content-Type': 'application/json'}
            custom_headers = webhook_config.get('headers', {})
            
            # Expand environment variables in headers
            for key, value in custom_headers.items():
                headers[key] = os.path.expandvars(str(value))
            
            # Prepare payload
            payload_template = webhook_config.get('payload_template')
            if payload_template:
                # Use custom payload template
                payload = {}
                for key, value in payload_template.items():
                    if isinstance(value, str):
                        payload[key] = value.format(message=message)
                    else:
                        payload[key] = value
            else:
                # Detect webhook type and use appropriate payload format
                if 'discord.com/api/webhooks' in webhook_url.lower():
                    # Discord webhook format
                    payload = {"content": message}
                elif 'healthchecks' in webhook_url.lower():
                    # Healthchecks.io format (simple ping, no payload needed)
                    payload = {}
                else:
                    # Generic webhook format
                    payload = {
                        'text': message,
                        'timestamp': datetime.now().isoformat()
                    }
            
            # Send webhook
            if payload:
                response = requests.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
            else:
                # For healthchecks.io - just a simple GET/POST without payload
                response = requests.post(
                    webhook_url,
                    headers={'User-Agent': 'pfSense-Backup-Manager'},
                    timeout=timeout
                )
            
            response.raise_for_status()
            
            self.logger.info(f"Notification sent successfully to {webhook_name}")
            self.metrics.record_notification(webhook_name, True)
            
        except Exception as e:
            self.logger.error(f"Failed to send notification to {webhook_name}: {e}")
            self.metrics.record_notification(webhook_name, False)
    
    def _send_notifications(self, message: str, is_success: bool = True, failed_instances: List[str] = None):
        """Send notifications to configured webhooks based on their trigger settings"""
        notifications_config = self.config.get('notifications', {})
        
        if not notifications_config.get('enabled', False):
            return
        
        webhooks = notifications_config.get('webhooks', [])
        if not webhooks:
            return
        
        for webhook_config in webhooks:
            trigger = webhook_config.get('trigger', 'always').lower()
            
            # Determine if we should send to this webhook
            should_send = False
            if trigger == 'always':
                should_send = True
            elif trigger == 'success' and is_success:
                should_send = True
            elif trigger == 'failure' and not is_success:
                should_send = True
            
            if should_send:
                formatted_message = self._format_notification_message(
                    webhook_config, is_success, message, failed_instances
                )
                self._send_webhook_notification(webhook_config, formatted_message)
    
    def backup_instance(self, instance: Dict) -> bool:
        """Backup a single pfSense instance"""
        self.logger.info(f"Starting backup for {instance['name']}")
        instance_name = instance['name']
        
        self.metrics.record_backup_attempt(instance_name)
        
        session = requests.Session()
        start_time = time.time()
        
        try:
            if not self._authenticate_pfsense(session, instance):
                duration = time.time() - start_time
                self.metrics.record_backup_failure(instance_name, 'authentication_failed', duration)
                return False
            
            config_content = self._download_config(session, instance)
            if not config_content:
                duration = time.time() - start_time
                self.metrics.record_backup_failure(instance_name, 'download_failed', duration)
                return False
            
            if not self._save_backup(config_content, instance):
                duration = time.time() - start_time
                self.metrics.record_backup_failure(instance_name, 'save_failed', duration)
                return False
            
            duration = time.time() - start_time
            self.metrics.record_backup_success(instance_name, duration)
            
            self.logger.info(f"Backup completed successfully for {instance['name']}")
            return True
            
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error for {instance['name']}: {e}")
            duration = time.time() - start_time
            self.metrics.record_backup_failure(instance_name, 'connection_error', duration)
            return False
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Timeout error for {instance['name']}: {e}")
            duration = time.time() - start_time
            self.metrics.record_backup_failure(instance_name, 'timeout_error', duration)
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error for {instance['name']}: {e}")
            duration = time.time() - start_time
            self.metrics.record_backup_failure(instance_name, 'request_error', duration)
            return False
        except Exception as e:
            self.logger.error(f"Backup failed for {instance['name']}: {e}")
            duration = time.time() - start_time
            self.metrics.record_backup_failure(instance_name, 'unexpected_error', duration)
            return False
        
        finally:
            session.close()
    
    def backup_all_instances(self):
        """Backup all configured pfSense instances"""
        self.logger.info("Starting backup process for all instances")
        
        success_count = 0
        total_count = len(self.config['pfsense_instances'])
        failed_instances = []
        
        for instance in self.config['pfsense_instances']:
            try:
                if self.backup_instance(instance):
                    success_count += 1
                else:
                    failed_instances.append(instance['name'])
            except Exception as e:
                self.logger.error(f"Unexpected error backing up {instance['name']}: {e}")
                failed_instances.append(instance['name'])
        
        # Send notifications
        if failed_instances:
            message = f"Backup completed with failures ({success_count}/{total_count} successful)"
            self.logger.warning(message)
            self._send_notifications(message, is_success=False, failed_instances=failed_instances)
        else:
            message = f"All {total_count} instance(s) backed up successfully"
            self.logger.info(message)
            self._send_notifications(message, is_success=True)
    
    def run_scheduled(self):
        """Run scheduled backups"""
        schedule_config = self.config.get('schedule', {})
        if not schedule_config.get('enabled', False):
            self.logger.info("Scheduled backups not enabled, running once and exiting")
            self.backup_all_instances()
            return
        
        frequency = schedule_config.get('frequency', 'daily')
        
        if frequency == 'daily':
            schedule.every().day.at("02:00").do(self.backup_all_instances)
        elif frequency == 'hourly':
            schedule.every().hour.do(self.backup_all_instances)
        elif frequency == 'weekly':
            schedule.every().week.do(self.backup_all_instances)
        else:
            self.logger.warning(f"Custom cron scheduling not fully implemented, using daily default")
            schedule.every().day.at("02:00").do(self.backup_all_instances)
        
        self.logger.info(f"Scheduled backups enabled with frequency: {frequency}")
        
        next_run = schedule.next_run()
        if next_run:
            next_run_timestamp = next_run.timestamp()
            self.metrics.set_next_scheduled_backup(next_run_timestamp)
            self.logger.info("Next scheduled backup: " + str(next_run))
        
        # Run once immediately
        self.backup_all_instances()
        
        # Keep running scheduled jobs
        while True:
            schedule.run_pending()
            time.sleep(60)
            
            next_run = schedule.next_run()
            if next_run:
                next_run_timestamp = next_run.timestamp()
                self.metrics.set_next_scheduled_backup(next_run_timestamp)

def main():
    config_file = os.getenv('CONFIG_FILE', '/app/config/config.yaml')
    
    if not os.path.exists(config_file):
        print(f"Configuration file not found: {config_file}")
        sys.exit(1)
    
    backup_manager = PfSenseBackupManager(config_file)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        backup_manager.backup_all_instances()
    else:
        backup_manager.run_scheduled()

if __name__ == '__main__':
    main()