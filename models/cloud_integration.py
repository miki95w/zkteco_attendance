"""
ZKTeco Cloud Server Integration
"""

import logging
import requests
import json
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ZKTecoCloudConfig(models.Model):
    """Configuration for ZKTeco Cloud Server Integration."""
    
    _name = 'zkteco.cloud.config'
    _description = 'ZKTeco Cloud Server Configuration'
    
    name = fields.Char(string='Configuration Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    
    # Cloud Server Connection
    cloud_server_url = fields.Char(string='Cloud Server URL', required=True, 
                                   help='e.g., http://cloud-server-ip:port')
    api_endpoint = fields.Char(string='API Endpoint', 
                               help='e.g., /api/v1/attendance or /zktecoapi')
    
    # Authentication
    auth_type = fields.Selection([
        ('none', 'No Authentication'),
        ('basic', 'Basic Auth'),
        ('token', 'Token/API Key'),
        ('custom', 'Custom Headers'),
    ], string='Authentication Type', default='token', required=True)
    
    username = fields.Char(string='Username')
    password = fields.Char(string='Password')
    api_token = fields.Char(string='API Token/Key')
    custom_headers = fields.Text(string='Custom Headers (JSON format)',
                                help='{"Authorization": "Bearer token", "X-API-Key": "key"}')
    
    # Connection Status
    connection_status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], string='Connection Status', default='disconnected', readonly=True)
    
    last_sync = fields.Datetime(string='Last Sync', readonly=True)
    last_error = fields.Text(string='Last Error', readonly=True)
    
    # Sync Settings
    sync_interval = fields.Integer(string='Sync Interval (minutes)', default=5,
                                   help='How often to pull data from cloud server')
    auto_sync_enabled = fields.Boolean(string='Enable Auto Sync', default=True)
    
    # Data Mapping
    device_id_field = fields.Char(string='Device ID Field', default='device_id',
                                  help='Field name for device ID in cloud data')
    user_id_field = fields.Char(string='User ID Field', default='user_id',
                                help='Field name for user ID in cloud data')
    timestamp_field = fields.Char(string='Timestamp Field', default='timestamp',
                                  help='Field name for punch timestamp')
    event_type_field = fields.Char(string='Event Type Field', default='event_type',
                                   help='Field name for punch type (in/out)')
    
    def _get_headers(self):
        """Get HTTP headers for API requests."""
        headers = {'Content-Type': 'application/json'}
        
        if self.auth_type == 'basic' and self.username and self.password:
            import base64
            credentials = base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
            headers['Authorization'] = f'Basic {credentials}'
        
        elif self.auth_type == 'token' and self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
            # Also try X-API-Key format (common alternative)
            headers['X-API-Key'] = self.api_token
        
        elif self.auth_type == 'custom' and self.custom_headers:
            try:
                custom = json.loads(self.custom_headers)
                headers.update(custom)
            except json.JSONDecodeError:
                _logger.warning("Invalid JSON in custom headers")
        
        return headers
    
    def action_test_connection(self):
        """Test connection to cloud server."""
        try:
            if not self.cloud_server_url:
                raise UserError(_('Please configure Cloud Server URL first'))
            
            # Try different common endpoints
            test_endpoints = [
                '/health',
                '/status', 
                '/api/status',
                '/ping',
                self.api_endpoint or '/api/attendance'
            ]
            
            headers = self._get_headers()
            session = requests.Session()
            session.headers.update(headers)
            
            connection_success = False
            response_info = ""
            
            for endpoint in test_endpoints:
                try:
                    url = self.cloud_server_url.rstrip('/') + endpoint
                    _logger.info(f"Testing connection to: {url}")
                    
                    response = session.get(url, timeout=10)
                    
                    if response.status_code in [200, 401, 403]:  # 401/403 means server is responding
                        connection_success = True
                        response_info = f"Status: {response.status_code}, Endpoint: {endpoint}"
                        if response.status_code == 200:
                            break  # Successful response, use this endpoint
                    
                except requests.exceptions.RequestException as e:
                    _logger.debug(f"Endpoint {endpoint} failed: {e}")
                    continue
            
            if connection_success:
                self.write({
                    'connection_status': 'connected',
                    'last_error': False,
                    'last_sync': fields.Datetime.now(),
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': f'Connected to cloud server. {response_info}',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Could not connect to cloud server. Check URL and authentication.'))
                
        except Exception as e:
            error_msg = str(e)
            self.write({
                'connection_status': 'error',
                'last_error': error_msg,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': error_msg,
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_fetch_attendance_data(self):
        """Fetch attendance data from cloud server."""
        try:
            if not self.cloud_server_url or not self.api_endpoint:
                raise UserError(_('Please configure Cloud Server URL and API Endpoint'))
            
            headers = self._get_headers()
            url = self.cloud_server_url.rstrip('/') + self.api_endpoint
            
            # Try different methods to get data
            methods_to_try = [
                ('GET', {}),
                ('POST', {'action': 'get_attendance'}),
                ('POST', {'method': 'fetch_logs'}),
            ]
            
            attendance_data = []
            
            for method, payload in methods_to_try:
                try:
                    if method == 'GET':
                        response = requests.get(url, headers=headers, timeout=30)
                    else:
                        response = requests.post(url, headers=headers, json=payload, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Handle different response formats
                        if isinstance(data, list):
                            attendance_data = data
                        elif isinstance(data, dict):
                            # Try common keys
                            for key in ['data', 'attendance', 'records', 'logs', 'result']:
                                if key in data and isinstance(data[key], list):
                                    attendance_data = data[key]
                                    break
                        
                        if attendance_data:
                            break
                            
                except requests.exceptions.RequestException as e:
                    _logger.debug(f"Method {method} failed: {e}")
                    continue
            
            if not attendance_data:
                raise UserError(_('No attendance data received from cloud server'))
            
            # Process the attendance data
            processed_count = self._process_attendance_data(attendance_data)
            
            self.write({
                'connection_status': 'connected',
                'last_sync': fields.Datetime.now(),
                'last_error': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Successful'),
                    'message': f'Processed {processed_count} attendance records',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            self.write({
                'connection_status': 'error',
                'last_error': error_msg,
            })
            raise UserError(error_msg)
    
    def _process_attendance_data(self, attendance_data):
        """Process attendance data from cloud server."""
        processed_count = 0
        
        for record in attendance_data:
            try:
                # Extract fields based on configuration
                device_id = record.get(self.device_id_field, record.get('device_id'))
                user_id = record.get(self.user_id_field, record.get('user_id'))
                timestamp_str = record.get(self.timestamp_field, record.get('timestamp'))
                event_type = record.get(self.event_type_field, record.get('event_type', 0))
                
                if not all([user_id, timestamp_str]):
                    _logger.warning(f"Incomplete record: {record}")
                    continue
                
                # Parse timestamp
                try:
                    # Try common timestamp formats
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%d/%m/%Y %H:%M:%S']:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        # Try parsing as ISO format
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except (ValueError, TypeError) as e:
                    _logger.warning(f"Invalid timestamp format: {timestamp_str}")
                    continue
                
                # Find or create device
                device = self.env['zkteco.device'].search([
                    ('serial_number', '=', str(device_id))
                ], limit=1)
                
                if not device:
                    device = self.env['zkteco.device'].create({
                        'name': f'Cloud Device {device_id}',
                        'ip_address': 'cloud',
                        'serial_number': str(device_id),
                        'is_online': True,
                    })
                
                # Find employee mapping
                user_mapping = self.env['zkteco.user.mapping'].search([
                    ('device_user_id', '=', str(user_id))
                ], limit=1)
                
                if not user_mapping:
                    # Create quarantine record
                    self.env['zkteco.quarantine'].create({
                        'user_id': str(user_id),
                        'timestamp': timestamp,
                        'event_type': int(event_type) if event_type else 0,
                        'device_id': str(device_id),
                        'error_reason': f'No employee mapping found for user ID: {user_id}',
                        'raw_data': json.dumps(record),
                    })
                    continue
                
                # Check for duplicate
                existing = self.env['zkteco.attendance'].search([
                    ('employee_id', '=', user_mapping.employee_id.id),
                    ('timestamp', '=', timestamp),
                    ('device_id', '=', device.id),
                ], limit=1)
                
                if existing:
                    continue  # Skip duplicate
                
                # Create attendance record
                self.env['zkteco.attendance'].create({
                    'device_id': device.id,
                    'device_user_id': str(user_id),
                    'timestamp': timestamp,
                    'event_type': int(event_type) if event_type else 0,
                    'employee_id': user_mapping.employee_id.id,
                    'state': 'draft',
                })
                
                processed_count += 1
                
            except Exception as e:
                _logger.error(f"Error processing record {record}: {e}")
                continue
        
        # Auto-process the created records
        if processed_count > 0:
            draft_records = self.env['zkteco.attendance'].search([('state', '=', 'draft')])
            draft_records.action_process_logs()
        
        return processed_count
    
    @api.model
    def cron_sync_cloud_data(self):
        """Cron job to sync data from cloud server."""
        configs = self.search([('active', '=', True), ('auto_sync_enabled', '=', True)])
        
        for config in configs:
            try:
                config.action_fetch_attendance_data()
                _logger.info(f"Successfully synced data for config: {config.name}")
            except Exception as e:
                _logger.error(f"Failed to sync data for config {config.name}: {e}")
    
    @api.model_create_multi
    def create(self, vals_list):
        """Set default API endpoint based on URL."""
        for vals in vals_list:
            if vals.get('cloud_server_url') and not vals.get('api_endpoint'):
                # Set common default endpoints
                vals['api_endpoint'] = '/api/attendance'
        return super().create(vals_list)