import logging
import requests
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
                response = self._make_request(config, '/health', method='GET', timeout=5)
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
    
    def _make_request(self, config, endpoint, method='GET', data=None, timeout=30):
        """Make HTTP request to Flask ADMS."""
        url = config.adms_url.rstrip('/') + endpoint
        headers = {
            'Authorization': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return response
        except requests.exceptions.Timeout:
            raise UserError(_('Request to Flask ADMS timed out'))
        except requests.exceptions.ConnectionError:
            raise UserError(_('Cannot connect to Flask ADMS at %s') % url)
        except Exception as e:
            raise UserError(_('Error communicating with Flask ADMS: %s') % str(e))
    
    def action_test_connection(self):
        """Test connection to Flask ADMS."""
        self.ensure_one()
        try:
            response = self._make_request(self, '/health', method='GET', timeout=10)
            if response.status_code == 200:
                data = response.json()
                message = _(
                    'Connection successful!\n\n'
                    'Status: %(status)s\n'
                    'Database: %(database)s\n'
                    'Devices Connected: %(devices_connected)s'
                ) % data
                
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
                    device = self.env['zkteco.device'].sudo().search([
                        ('serial_number', '=', device_data.get('device_id'))
                    ], limit=1)
                    
                    if device:
                        device.write({
                            'ip_address': device_data.get('ip_address'),
                            'last_sync': device_data.get('last_heartbeat'),
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
        """Trigger user synchronization to all devices."""
        self.ensure_one()
        try:
            # Get all employees with device IDs
            employees = self.env['hr.employee'].sudo().search([
                ('zkteco_device_id', '!=', False)
            ])
            
            employee_ids = employees.ids
            
            response = self._make_request(
                self,
                '/api/sync/users',
                method='POST',
                data={'employee_ids': employee_ids}
            )
            
            if response.status_code == 200:
                data = response.json()
                message = _(
                    'User sync triggered!\n\n'
                    'Status: %(status)s\n'
                    'Synced: %(synced)s\n'
                    'Failed: %(failed)s'
                ) % data
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('User Sync'),
                        'message': message,
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            raise UserError(_('Failed to sync users: %s') % str(e))
    
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
