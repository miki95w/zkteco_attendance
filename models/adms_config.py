import logging
import requests
import json
from datetime import datetime, timezone
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ADMSConfig(models.Model):
    
    _name = 'zkteco.adms.config'
    _description = 'Flask ADMS Configuration'
    
    name = fields.Char(string='Configuration Name', required=True, default='Flask ADMS')
    active = fields.Boolean(string='Active', default=True)
    
    # Connection settings
    adms_url = fields.Char(
        string='ADMS URL',
        required=True,
        default='http://localhost:8000',
        help='Base URL of the Flask ADMS middleware (e.g., http://localhost:8000)'
    )
    api_key = fields.Char(
        string='API Key',
        required=True,
        help='API authentication key for Flask ADMS'
    )
    
    # Status
    last_sync = fields.Datetime(string='Last Sync', readonly=True)
    last_error = fields.Text(string='Last Error', readonly=True)
    connection_status = fields.Selection([
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
        ('error', 'Error')
    ], string='Connection Status', compute='_compute_connection_status', store=False)
    
    # Statistics
    devices_connected = fields.Integer(string='Devices Connected', compute='_compute_statistics')
    records_processed = fields.Integer(string='Records Processed', compute='_compute_statistics')
    records_quarantined = fields.Integer(string='Records Quarantined', compute='_compute_statistics')
    
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Configuration name must be unique!')
    ]
    
    @api.depends('adms_url', 'api_key')
    def _compute_connection_status(self):
        """Check connection status with Flask ADMS."""
        for config in self:
            if not config.adms_url or not config.api_key:
                config.connection_status = 'disconnected'
                continue
            
            try:
                response = self._make_request(config, '/api/test', method='GET', timeout=5)
                if response and response.status_code == 200:
                    config.connection_status = 'connected'
                else:
                    config.connection_status = 'error'
            except Exception as e:
                _logger.warning(f"ADMS connection check failed: {e}")
                config.connection_status = 'disconnected'
    
    def _compute_statistics(self):
        for config in self:
            try:
                response = self._make_request(config, '/metrics', method='GET', timeout=5)
                if response and response.status_code == 200:
                    metrics = self._parse_prometheus_metrics(response.text)
                    config.devices_connected = metrics.get('adms_devices_connected', 0)
                    config.records_processed = metrics.get('adms_records_processed_total', 0)
                    config.records_quarantined = metrics.get('adms_records_quarantined_total', 0)
                else:
                    config.devices_connected = 0
                    config.records_processed = 0
                    config.records_quarantined = 0
            except Exception:
                config.devices_connected = 0
                config.records_processed = 0
                config.records_quarantined = 0
    
    def _parse_prometheus_metrics(self, text):
        metrics = {}
        for line in text.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0]
                    try:
                        value = int(float(parts[1]))
                        metrics[key] = value
                    except ValueError:
                        pass
        return metrics

    def _parse_device_timestamp(self, timestamp_str):
        """Parse a device timestamp and return an Odoo-safe naive datetime."""
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%d/%m/%Y %H:%M:%S']:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        if timestamp.tzinfo:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        return timestamp

    def _quarantine_record(self, record, reason, timestamp=None):
        """Store a record that cannot safely become attendance yet."""
        self.env['zkteco.quarantine'].sudo().create({
            'user_id': str(record.get('user_id', 'unknown')),
            'timestamp': timestamp or fields.Datetime.now(),
            'event_type': int(record.get('event_type') or 0),
            'device_id': str(record.get('device_id', 'unknown')),
            'error_reason': reason,
            'raw_data': json.dumps(record, default=str),
            'reviewed': False,
        })
    
    def _make_request(self, config, endpoint, method='GET', data=None, timeout=30):
        """Make HTTP request to Flask ADMS."""
        # Ensure URL has proper schema
        base_url = config.adms_url
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'http://' + base_url
        
        url = base_url.rstrip('/') + endpoint
        headers = {
            'Authorization': f'Bearer {config.api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'Odoo-ZKTeco-Integration/1.0'
        }
        
        try:
            _logger.info(f"Making {method} request to: {url}")
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            _logger.info(f"Response status: {response.status_code}")
            return response
            
        except requests.exceptions.Timeout:
            raise UserError(_('Request to Flask ADMS timed out after %s seconds') % timeout)
        except requests.exceptions.ConnectionError as e:
            raise UserError(_('Cannot connect to Flask ADMS at %s. Error: %s') % (url, str(e)))
        except Exception as e:
            raise UserError(_('Error communicating with Flask ADMS: %s') % str(e))
    
    def action_test_connection(self):
        """Test connection to Flask ADMS."""
        self.ensure_one()
        try:
            response = self._make_request(self, '/api/test', method='GET', timeout=10)
            if response.status_code == 200:
                data = response.json()
                message = _(
                    'Connection successful!\n\n'
                    'Status: %(status)s\n'
                    'Authentication: %(authentication)s\n'
                    'Devices Connected: %(devices_connected)s'
                ) % {
                    'status': data.get('status', 'ok'),
                    'authentication': data.get('authentication', 'working'),
                    'devices_connected': data.get('devices_connected', 0),
                }
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test'),
                        'message': message,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Flask ADMS returned status code: %s') % response.status_code)
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_get_device_status(self):
        """Get device status from Flask ADMS."""
        self.ensure_one()
        try:
            response = self._make_request(self, '/api/devices/status', method='GET')
            if response.status_code == 200:
                data = response.json()
                devices = data.get('devices', [])
                
                # Update local device records
                for device_data in devices:
                    sn = device_data.get('device_id')
                    if not sn:
                        continue
                    last_heartbeat = device_data.get('last_heartbeat')
                    try:
                        last_sync = self._parse_device_timestamp(last_heartbeat) if last_heartbeat else fields.Datetime.now()
                    except Exception:
                        last_sync = fields.Datetime.now()
                    device = self.env['zkteco.device'].sudo().search([
                        ('serial_number', '=', sn)
                    ], limit=1)
                    
                    if device:
                        device.write({
                            'ip_address': device_data.get('ip_address'),
                            'last_sync': last_sync,
                        })
                    else:
                        # Auto-create the device in Odoo
                        self.env['zkteco.device'].sudo().create({
                            'name': f'ZKTeco Device {sn}',
                            'serial_number': sn,
                            'ip_address': device_data.get('ip_address'),
                            'is_active': True,
                            'last_sync': last_sync,
                        })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Device Status Updated'),
                        'message': _('Updated status for %s devices') % len(devices),
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            raise UserError(_('Failed to get device status: %s') % str(e))
    
    def action_sync_users_to_devices(self):
        """Ask connected devices to send their current user list via Flask."""
        self.ensure_one()
        try:
            devices = self.env['zkteco.device'].search([('is_active', '=', True)])
            device_sns = [d.serial_number for d in devices if d.serial_number]
            
            sync_data = {
                'employee_ids': [],
                'employee_data': [],
                'device_sn': 'all_devices',
                'target_devices': device_sns
            }
            
            response = self._make_request(
                self,
                '/api/sync/users',
                method='POST',
                data=sync_data
            )
            
            if response.status_code == 200:
                data = response.json()
                message = _(
                    'Device user refresh queued successfully!\n\n'
                    'Status: %(status)s\n'
                    'Devices: %(device_count)s\n'
                    'Message: %(message)s'
                ) % {
                    'status': data.get('status', 'Unknown'),
                    'device_count': data.get('synced', 0),
                    'message': data.get('message', 'No message')
                }
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Device User Refresh Queued'),
                        'message': message,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Flask ADMS returned status code: %s') % response.status_code)
                
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('User Sync Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_fetch_attendance_data(self):
        """Fetch attendance data from Flask ADMS."""
        self.ensure_one()
        try:
            response = self._make_request(self, '/api/attendance/fetch', method='GET')
            
            if response.status_code == 200:
                data = response.json()
                attendance_records = data.get('data', [])
                
                if not attendance_records:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('No New Data'),
                            'message': _('No new attendance records found'),
                            'type': 'info',
                            'sticky': False,
                        }
                    }
                
                processed_count = self._process_flask_attendance_data(attendance_records)
                
                self.write({'last_sync': fields.Datetime.now(), 'last_error': False})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Attendance Sync Successful'),
                        'message': _('Processed %s attendance records') % processed_count,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Flask ADMS returned status code: %s') % response.status_code)
                
        except Exception as e:
            raise UserError(_('Failed to fetch attendance data: %s') % str(e))
    
    def _process_flask_attendance_data(self, attendance_records):
        """Process attendance data from Flask ADMS."""
        processed_count = 0
        quarantine_count = 0
        
        for record in attendance_records:
            try:
                device_id = record.get('device_id')
                user_id = record.get('user_id')
                timestamp_str = record.get('timestamp')
                event_type = int(record.get('event_type', 0))
                
                if not all([device_id, user_id, timestamp_str]):
                    _logger.warning(f"Incomplete attendance record: {record}")
                    continue
                
                try:
                    timestamp = self._parse_device_timestamp(timestamp_str)
                except (ValueError, TypeError) as e:
                    _logger.warning(f"Invalid timestamp format: {timestamp_str}")
                    self._quarantine_record(
                        record,
                        f'Invalid timestamp format: {timestamp_str}',
                    )
                    quarantine_count += 1
                    continue
                
                # Find device
                device = self.env['zkteco.device'].search([
                    ('serial_number', '=', str(device_id))
                ], limit=1)
                
                if not device:
                    # Create device automatically
                    device = self.env['zkteco.device'].create({
                        'name': f'Auto-created Device {device_id}',
                        'ip_address': 'unknown',
                        'serial_number': str(device_id),
                        'is_active': True,
                        'last_sync': fields.Datetime.now(),
                    })
                    _logger.info(f"Auto-created device: {device.name}")
                
                # Find employee mapping
                user_mapping = self.env['zkteco.user.mapping'].search([
                    ('device_user_id', '=', str(user_id)),
                    ('device_id', '=', device.id),
                ], limit=1)
                
                if not user_mapping:
                    self._quarantine_record(
                        record,
                        f'No employee mapping found for device {device.serial_number} user ID: {user_id}',
                        timestamp,
                    )
                    quarantine_count += 1
                    continue

                if not user_mapping.employee_id:
                    self._quarantine_record(
                        record,
                        f'Device user ID {user_id} is mapped on {device.serial_number} but has no linked employee.',
                        timestamp,
                    )
                    quarantine_count += 1
                    continue
                
                # Check for duplicate
                existing = self.env['zkteco.attendance'].search([
                    ('device_user_id', '=', str(user_id)),
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
                    'event_type': event_type,
                    'employee_id': user_mapping.employee_id.id,
                    'state': 'draft',
                    'raw_data': json.dumps(record, default=str),
                })
                
                processed_count += 1
                _logger.info(f"Created attendance record for {user_mapping.employee_id.name}")
                
            except Exception as e:
                _logger.error(f"Error processing attendance record {record}: {e}")
                # Create quarantine record for processing errors
                self._quarantine_record(record, f'Processing error: {str(e)}')
                quarantine_count += 1
                continue
        
        # Auto-process created records
        if processed_count > 0:
            draft_records = self.env['zkteco.attendance'].search([('state', '=', 'draft')])
            if draft_records:
                try:
                    draft_records.action_process_logs()
                    _logger.info(f"Auto-processed {len(draft_records)} draft attendance records")
                except Exception as e:
                    _logger.error(f"Error auto-processing records: {e}")
        
        if quarantine_count > 0:
            _logger.warning(f"Quarantined {quarantine_count} records due to missing mappings or errors")
        
        return processed_count
    
    @api.model
    def get_active_config(self):
        """Get the active ADMS configuration."""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            raise UserError(_(
                'No active Flask ADMS configuration found. '
                'Please configure Flask ADMS connection in Settings.'
            ))
        return config

    def action_open_quarantine(self):
        """Open quarantined records."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quarantined Records'),
            'res_model': 'zkteco.quarantine',
            'view_mode': 'tree,form',
            'domain': [('reviewed', '=', False)],
        }

    def action_open_processed(self):
        """Open processed attendance logs."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Processed Logs'),
            'res_model': 'zkteco.attendance',
            'view_mode': 'tree,form',
            'domain': [('state', '=', 'processed')],
        }

    def action_open_devices(self):
        """Open connected devices."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('ZKTeco Devices'),
            'res_model': 'zkteco.device',
            'view_mode': 'tree,form',
        }
    
    @api.model
    def cron_fetch_attendance_data(self):
        """Cron job to automatically fetch attendance data from Flask ADMS."""
        configs = self.search([('active', '=', True)])
        
        for config in configs:
            try:
                _logger.info(f"Running auto-sync for ADMS config: {config.name}")
                config.action_fetch_attendance_data()
            except Exception as e:
                _logger.error(f"Auto-sync failed for config {config.name}: {e}")
                config.write({
                    'last_error': f'Auto-sync error: {str(e)}'
                })
    
    def action_sync_now(self):
        """Manual sync button action."""
        return self.action_fetch_attendance_data()

    def action_fetch_device_users(self):
        """Fetch device users from Flask ADMS."""
        self.ensure_one()
        try:
            response = self._make_request(self, '/api/users/from-device', method='GET')
            
            if response.status_code == 200:
                data = response.json()
                users_data = data.get('users', [])
                
                if not users_data:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('No Users Found'),
                            'message': _('No device users found on the Flask server buffer.'),
                            'type': 'info',
                            'sticky': False,
                        }
                    }
                
                processed_count = self._process_flask_users_data(users_data)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('User Sync Successful'),
                        'message': _('Processed %s device users from Flask server.') % processed_count,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Flask ADMS returned status code: %s') % response.status_code)
                
        except Exception as e:
            raise UserError(_('Failed to fetch device users: %s') % str(e))

    def _parse_kv_line(self, line):
        """Parse a tab-separated or ampersand-separated key=value line."""
        parts = {}
        tokens = []
        for chunk in line.strip().split("\t"):
            tokens.extend(chunk.split("&"))
        for item in tokens:
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                parts[k.strip().lower()] = v.strip()
        return parts

    def _process_flask_users_data(self, users_data):
        """Process user data fetched from Flask ADMS."""
        mapping_obj = self.env['zkteco.user.mapping'].sudo()
        count = 0
        
        for user_record in users_data:
            device_sn = user_record.get('device_sn')
            raw_line = user_record.get('raw_data', '').strip()
            
            if not device_sn or not raw_line:
                continue
                
            # Find device
            device = self.env['zkteco.device'].sudo().search([
                ('serial_number', '=', str(device_sn))
            ], limit=1)
            
            if not device:
                # Create device automatically
                device = self.env['zkteco.device'].sudo().create({
                    'name': f'Auto-created Device {device_sn}',
                    'ip_address': 'unknown',
                    'serial_number': str(device_sn),
                    'is_active': True,
                    'last_sync': fields.Datetime.now(),
                })
            
            if raw_line.lower().startswith('user '):
                raw_line = raw_line[5:]
                
            kv = self._parse_kv_line(raw_line)
            pin = kv.get("pin")
            name = kv.get("name") or ""
            
            if pin:
                mapping = mapping_obj.search([
                    ('device_user_id', '=', str(pin)),
                    ('device_id', '=', device.id)
                ], limit=1)
                
                if not mapping:
                    mapping_obj.create({
                        'device_user_id': str(pin),
                        'device_user_name': name,
                        'device_id': device.id,
                    })
                    _logger.info(f"[ADMS Config] Created user mapping: Device SN {device_sn} | PIN {pin} | Name {name}")
                else:
                    mapping.write({'device_user_name': name})
                    _logger.info(f"[ADMS Config] Updated user mapping: Device SN {device_sn} | PIN {pin} | Name {name}")
                count += 1
                
        return count
