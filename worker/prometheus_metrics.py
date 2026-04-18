#!/usr/bin/env python3
"""
Prometheus metrics for pfSense backup operations
"""

import logging
import threading
import time

from prometheus_client import Counter, Gauge, Histogram, Info, start_http_server
from prometheus_client.core import CollectorRegistry


class PrometheusMetrics:
    def __init__(self, port: int = 8000, registry: CollectorRegistry = None):
        self.registry = registry or CollectorRegistry()
        self.port = port
        self.logger = logging.getLogger(__name__)
        
        # Initialize metrics
        self._init_metrics()
        
        # Start HTTP server for metrics
        self._start_server()
    
    def _init_metrics(self):
        """Initialize all Prometheus metrics"""
        
        # Backup operation counters
        self.backup_total = Counter(
            'pfsense_backups_total',
            'Total number of backup attempts',
            ['instance', 'status'],
            registry=self.registry
        )
        
        self.backup_success_total = Counter(
            'pfsense_backups_success_total',
            'Total number of successful backups',
            ['instance'],
            registry=self.registry
        )
        
        self.backup_failed_total = Counter(
            'pfsense_backups_failed_total',
            'Total number of failed backups',
            ['instance', 'error_type'],
            registry=self.registry
        )
        
        # Backup timing metrics
        self.backup_duration_seconds = Histogram(
            'pfsense_backups_duration_seconds',
            'Time spent performing backup operations',
            ['instance', 'operation'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600],
            registry=self.registry
        )
        
        # Backup file metrics
        self.backup_file_size_bytes = Gauge(
            'pfsense_backups_file_size_bytes',
            'Size of backup files in bytes',
            ['instance'],
            registry=self.registry
        )
        
        self.backup_files_retained = Gauge(
            'pfsense_backups_files_retained',
            'Number of backup files currently retained',
            ['instance'],
            registry=self.registry
        )
        
        # Last backup timestamp
        self.last_backup_timestamp = Gauge(
            'pfsense_last_backup_timestamp',
            'Timestamp of last backup attempt',
            ['instance'],
            registry=self.registry
        )
        
        self.last_successful_backup_timestamp = Gauge(
            'pfsense_last_successful_backup_timestamp',
            'Timestamp of last successful backup',
            ['instance'],
            registry=self.registry
        )
        
        # Authentication metrics
        self.auth_attempts_total = Counter(
            'pfsense_auth_attempts_total',
            'Total authentication attempts',
            ['instance', 'status'],
            registry=self.registry
        )
        
        self.auth_duration_seconds = Histogram(
            'pfsense_auth_duration_seconds',
            'Time spent on authentication',
            ['instance'],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
            registry=self.registry
        )
        
        # Network metrics
        self.network_requests_total = Counter(
            'pfsense_network_requests_total',
            'Total network requests made',
            ['instance', 'endpoint', 'status_code'],
            registry=self.registry
        )
        
        self.network_errors_total = Counter(
            'pfsense_network_errors_total',
            'Total network errors encountered',
            ['instance', 'error_type'],
            registry=self.registry
        )
        
        # Application info
        self.app_info = Info(
            'pfsense_backups_info',
            'Information about the pfSense backups application',
            registry=self.registry
        )
        
        # Set application info
        self.app_info.info({
            'version': '1.0.0',
            'component': 'pfsense-backups'
        })
        
        # Instance configuration metrics
        self.configured_instances = Gauge(
            'pfsense_configured_instances',
            'Number of configured pfSense instances',
            registry=self.registry
        )
        
        # Schedule metrics
        self.next_scheduled_backup_timestamp = Gauge(
            'pfsense_next_scheduled_backup_timestamp',
            'Timestamp of next scheduled backup',
            registry=self.registry
        )
        
        # Retention metrics
        self.files_cleaned_total = Counter(
            'pfsense_files_cleaned_total',
            'Total number of old backup files cleaned up',
            ['instance'],
            registry=self.registry
        )
        
        # Compression metrics
        self.compression_ratio = Gauge(
            'pfsense_compression_ratio',
            'Compression ratio for backup files (compressed/original)',
            ['instance'],
            registry=self.registry
        )
        
        # Notification metrics
        self.notifications_sent_total = Counter(
            'pfsense_notifications_sent_total',
            'Total notifications sent',
            ['type', 'status'],
            registry=self.registry
        )
    
    def _start_server(self):
        """Start Prometheus metrics HTTP server"""
        try:
            start_http_server(self.port, registry=self.registry)
            self.logger.info(f"Prometheus metrics server started on port {self.port}")
        except Exception as e:
            self.logger.error(f"Failed to start Prometheus metrics server: {e}")
    
    def record_backup_attempt(self, instance_name: str):
        """Record a backup attempt"""
        self.backup_total.labels(instance=instance_name, status='attempt').inc()
        self.last_backup_timestamp.labels(instance=instance_name).set_to_current_time()
    
    def record_backup_success(self, instance_name: str, duration: float, file_size: int = None):
        """Record a successful backup"""
        self.backup_success_total.labels(instance=instance_name).inc()
        self.backup_total.labels(instance=instance_name, status='success').inc()
        self.backup_duration_seconds.labels(instance=instance_name, operation='total').observe(duration)
        self.last_successful_backup_timestamp.labels(instance=instance_name).set_to_current_time()
        
        if file_size is not None:
            self.backup_file_size_bytes.labels(instance=instance_name).set(file_size)
    
    def record_backup_failure(self, instance_name: str, error_type: str, duration: float = None):
        """Record a failed backup"""
        self.backup_failed_total.labels(instance=instance_name, error_type=error_type).inc()
        self.backup_total.labels(instance=instance_name, status='failed').inc()
        
        if duration is not None:
            self.backup_duration_seconds.labels(instance=instance_name, operation='total').observe(duration)
    
    def record_auth_attempt(self, instance_name: str, success: bool, duration: float):
        """Record authentication attempt"""
        status = 'success' if success else 'failed'
        self.auth_attempts_total.labels(instance=instance_name, status=status).inc()
        self.auth_duration_seconds.labels(instance=instance_name).observe(duration)
    
    def record_network_request(self, instance_name: str, endpoint: str, status_code: int):
        """Record network request"""
        self.network_requests_total.labels(
            instance=instance_name,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
    
    def record_network_error(self, instance_name: str, error_type: str):
        """Record network error"""
        self.network_errors_total.labels(instance=instance_name, error_type=error_type).inc()
    
    def record_operation_duration(self, instance_name: str, operation: str, duration: float):
        """Record duration of specific operations"""
        self.backup_duration_seconds.labels(instance=instance_name, operation=operation).observe(duration)
    
    def set_configured_instances(self, count: int):
        """Set the number of configured instances"""
        self.configured_instances.set(count)
    
    def set_next_scheduled_backup(self, timestamp: float):
        """Set the timestamp of next scheduled backup"""
        self.next_scheduled_backup_timestamp.set(timestamp)
    
    def set_files_retained(self, instance_name: str, count: int):
        """Set the number of files retained for an instance"""
        self.backup_files_retained.labels(instance=instance_name).set(count)
    
    def record_files_cleaned(self, instance_name: str, count: int):
        """Record files cleaned up"""
        self.files_cleaned_total.labels(instance=instance_name).inc(count)
    
    def set_compression_ratio(self, instance_name: str, ratio: float):
        """Set compression ratio for an instance"""
        self.compression_ratio.labels(instance=instance_name).set(ratio)
    
    def record_notification(self, notification_type: str, success: bool):
        """Record notification attempt"""
        status = 'success' if success else 'failed'
        self.notifications_sent_total.labels(type=notification_type, status=status).inc()
    
    def get_registry(self):
        """Get the metrics registry"""
        return self.registry

class MetricsTimer:
    """Context manager for timing operations"""
    
    def __init__(self, metrics: PrometheusMetrics, instance_name: str, operation: str):
        self.metrics = metrics
        self.instance_name = instance_name
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.metrics.record_operation_duration(self.instance_name, self.operation, duration)
    
    def get_duration(self):
        """Get current duration"""
        if self.start_time:
            return time.time() - self.start_time
        return 0

# Global metrics instance
_metrics_instance = None
_metrics_lock = threading.Lock()

def get_metrics_instance(port: int = 8000) -> PrometheusMetrics:
    """Get or create global metrics instance"""
    global _metrics_instance
    
    with _metrics_lock:
        if _metrics_instance is None:
            _metrics_instance = PrometheusMetrics(port=port)
        return _metrics_instance

def reset_metrics_instance():
    """Reset global metrics instance (for testing)"""
    global _metrics_instance
    
    with _metrics_lock:
        _metrics_instance = None