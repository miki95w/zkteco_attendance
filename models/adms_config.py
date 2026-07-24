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
    
    @api.depends('last_sync')
    def _compute_connection_status(self):
        """Check connection status passively based on last polled/received timestamp from Flask ADMS."""
        for config in self:
            if not config.last_sync:
                config.connection_status = 'disconnected'
                continue
            
            # If last_sync (heartbeat) was within 60 seconds, it is connected
            now = fields.Datetime.now()
            diff = now - config.last_sync
            if diff.total_seconds() <= 60:
                config.connection_status = 'connected'
            else:
                config.connection_status = 'disconnected'
    
    def _compute_statistics(self):
        """Compute statistics using Odoo database values instead of requesting Flask."""
        from datetime import timedelta
        for config in self:
            # Connected devices: active device syncs in last 10 minutes
            limit_time = fields.Datetime.now() - timedelta(minutes=10)
            config.devices_connected = self.env['zkteco.device'].search_count([
                ('last_sync', '>=', limit_time)
            ])
            config.records_processed = self.env['zkteco.attendance'].search_count([
                ('state', '=', 'processed')
            ])
            config.records_quarantined = self.env['zkteco.quarantine'].search_count([
                ('reviewed', '=', False)
            ])
    
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
    
    def action_open_historical_sync(self):
        """Open the historical sync wizard."""
        self.ensure_one()
        return {
            'name': _('Historical Sync'),
            'type': 'ir.actions.act_window',
            'res_model': 'zkteco.historical.sync',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id},
        }

    def action_comprehensive_device_test(self):
        """Passive diagnostic tool to test communication between VPS, Relay, and Devices."""
        self.ensure_one()
        from datetime import timedelta
        # Check connection status of Flask Relay
        is_flask_online = False
        if self.last_sync:
            is_flask_online = (fields.Datetime.now() - self.last_sync).total_seconds() <= 60
            
        if not is_flask_online:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Flask Relay Offline'),
                    'message': _('The Flask ADMS middleware is offline or has not polled this VPS in the last 60 seconds.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }
            
        # Check active devices
        limit_time = fields.Datetime.now() - timedelta(minutes=10)
        online_devices = self.env['zkteco.device'].search([
            ('last_sync', '>=', limit_time)
        ])
        
        device_sns = [d.serial_number for d in online_devices]
        
        if not device_sns:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Devices Connected'),
                    'message': _('Flask ADMS is online, but no devices have reported heartbeats in the last 10 minutes.'),
                    'type': 'warning',
                    'sticky': True,
                }
            }
            
        result_message = f"""Device Communication Diagnostic Results:
        
🔗 Flask Relay status: Connected ✓
📱 Connected Devices: {len(device_sns)} ({', '.join(device_sns)})
✅ SUCCESS: The communication pipeline between VPS and local Flask relay is fully operational!
"""
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Diagnostic Report'),
                'message': result_message,
                'type': 'success',
                'sticky': True,
            }
        }
    def action_try_alternative_historical_sync(self):
        """Try alternative approach: request full dump by queueing DATA OPTION commands in Odoo."""
        self.ensure_one()
        devices = self.env['zkteco.device'].search([('is_active', '=', True)])
        for device in devices:
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': 'DATA OPTION rtlog',
            })
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': 'DATA OPTION attlog',
            })
            _logger.info("Device %s: queued DATA OPTION commands.", device.name)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Full Sync Queued'),
                'message': _('Full DATA OPTION sync commands have been queued for all active devices.'),
                'type': 'success',
            }
        }

    def action_diagnose_historical_sync(self):
        """Diagnostic tool under stateless relay. Reuses comprehensive test."""
        return self.action_comprehensive_device_test()

    def action_request_historical_sync(self, start_date, end_date):
        """Request historical logs passively by queueing query commands in the database queue."""
        self.ensure_one()
        devices = self.env['zkteco.device'].search([('is_active', '=', True)])
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        for device in devices:
            # Queue command to fetch historical transactions in the local command queue
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': f"DATA QUERY rtlog start={start_str} end={end_str}",
            })
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': f"DATA QUERY attlog start={start_str} end={end_str}",
            })
            _logger.info("Device %s: queued historical sync commands from %s to %s.", device.name, start_str, end_str)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Historical Sync Queued'),
                'message': _('Historical sync commands for range %s to %s have been queued for active devices.') % (start_str, end_str),
                'type': 'success',
            }
        }

    def action_check_buffer_status(self):
        """Under stateless relay, check the number of draft/quarantined records in Odoo's local database instead of requesting Flask."""
        self.ensure_one()
        draft_count = self.env['zkteco.attendance'].search_count([('state', '=', 'draft')])
        quarantine_count = self.env['zkteco.quarantine'].search_count([('reviewed', '=', False)])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Database Status'),
                'message': _('Odoo has %s draft attendance records and %s unreviewed quarantined records.') % (draft_count, quarantine_count),
                'type': 'info',
            }
        }

    def action_test_connection(self):
        """Test connection to Flask ADMS passively by checking the last sync timestamp."""
        self.ensure_one()
        if self.last_sync:
            now = fields.Datetime.now()
            diff = now - self.last_sync
            if diff.total_seconds() <= 60:
                message = _(
                    'Connection successful!\n\n'
                    'Last Heartbeat: %s seconds ago\n'
                    'Flask Middleware status: Active / Connected'
                ) % int(diff.total_seconds())
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test'),
                        'message': message,
                        'type': 'success',
                    }
                }
                
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection Failed'),
                'message': _('No heartbeat received from the local Flask ADMS middleware in the last 60 seconds. Ensure the Flask server is running locally and polling this VPS.'),
                'type': 'danger',
                'sticky': True,
            }
        }
    
    def action_get_device_status(self):
        """Refresh device status passively by listing active devices in the database."""
        self.ensure_one()
        from datetime import timedelta
        limit_time = fields.Datetime.now() - timedelta(minutes=10)
        online_devices = self.env['zkteco.device'].search([
            ('last_sync', '>=', limit_time)
        ])
        
        message = _('Active devices in the last 10 minutes:\n\n')
        for dev in online_devices:
            message += f"• {dev.name} (SN: {dev.serial_number}) - Online ✓\n"
        if not online_devices:
            message = _('No devices have reported heartbeats in the last 10 minutes.')
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Device Status'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }
    
    def action_sync_users_to_devices(self):
        """Ask connected devices to send their current user list by queueing commands."""
        return self.action_fetch_device_users()
    
    def action_fetch_attendance_data(self):
        """Queue a log fetch command for all active devices in Odoo's local queue."""
        self.ensure_one()
        devices = self.env['zkteco.device'].search([('is_active', '=', True)])
        for device in devices:
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': 'DATA QUERY tablename=transaction',
            })
            _logger.info("Device %s: queued log fetch command locally.", device.name)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Fetch Logs Queued'),
                'message': _('Log fetch commands have been queued. Active devices will send logs shortly.'),
                'type': 'success',
            }
        }

    
    def _process_flask_attendance_data(self, attendance_records):
        """Process attendance data from Flask ADMS using bulk operations."""
        if not attendance_records:
            return 0

        # Step 1: Pre-parse and validate records
        parsed_records = []
        device_sns = set()
        user_ids = set()
        quarantine_vals = []
        
        for record in attendance_records:
            device_sn = record.get('device_id')
            user_id = record.get('user_id')
            timestamp_str = record.get('timestamp')
            event_type = int(record.get('event_type', 0))
            
            if not all([device_sn, user_id, timestamp_str]):
                _logger.warning(f"Incomplete attendance record: {record}")
                continue
                
            try:
                timestamp = self._parse_device_timestamp(timestamp_str)
            except (ValueError, TypeError) as e:
                _logger.warning(f"Invalid timestamp format: {timestamp_str}")
                quarantine_vals.append({
                    'user_id': str(user_id),
                    'timestamp': fields.Datetime.now(),
                    'event_type': event_type,
                    'device_id': str(device_sn),
                    'error_reason': f'Invalid timestamp format: {timestamp_str}',
                    'raw_data': json.dumps(record, default=str),
                    'reviewed': False,
                })
                continue
                
            device_sns.add(str(device_sn))
            user_ids.add(str(user_id))
            parsed_records.append({
                'device_sn': str(device_sn),
                'user_id': str(user_id),
                'timestamp': timestamp,
                'event_type': event_type,
                'record': record
            })
            
        if not parsed_records:
            if quarantine_vals:
                self.env['zkteco.quarantine'].create(quarantine_vals)
            return 0
            
        # Step 2: Load/Create devices
        existing_devices = self.env['zkteco.device'].search([
            ('serial_number', 'in', list(device_sns))
        ])
        device_map = {d.serial_number: d for d in existing_devices}
        
        for sn in device_sns:
            if sn not in device_map:
                new_device = self.env['zkteco.device'].create({
                    'name': f'Auto-created Device {sn}',
                    'ip_address': 'unknown',
                    'serial_number': sn,
                    'is_active': True,
                    'last_sync': fields.Datetime.now(),
                })
                _logger.info(f"Auto-created device: {new_device.name}")
                device_map[sn] = new_device
                
        # Step 3: Load employee mappings
        device_ids = [d.id for d in device_map.values()]
        user_mappings = self.env['zkteco.user.mapping'].search([
            ('device_user_id', 'in', list(user_ids)),
            ('device_id', 'in', device_ids),
        ])
        mapping_map = {(m.device_id.id, m.device_user_id): m for m in user_mappings}
        
        # Step 4: Load existing attendance records in the timestamp range to check for duplicates
        timestamps = [p['timestamp'] for p in parsed_records]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        
        existing_attendance = self.env['zkteco.attendance'].search([
            ('device_id', 'in', device_ids),
            ('device_user_id', 'in', list(user_ids)),
            ('timestamp', '>=', min_ts),
            ('timestamp', '<=', max_ts)
        ])
        existing_map = {(a.device_id.id, a.device_user_id, a.timestamp): a for a in existing_attendance}
        
        # Step 5: Classify records
        vals_to_create = []
        processed_count = 0
        
        for p in parsed_records:
            device = device_map[p['device_sn']]
            user_mapping = mapping_map.get((device.id, p['user_id']))
            
            if not user_mapping:
                quarantine_vals.append({
                    'user_id': p['user_id'],
                    'timestamp': p['timestamp'],
                    'event_type': p['event_type'],
                    'device_id': p['device_sn'],
                    'error_reason': f'No employee mapping found for device {p["device_sn"]} user ID: {p["user_id"]}',
                    'raw_data': json.dumps(p['record'], default=str),
                    'reviewed': False,
                })
                continue
                
            if not user_mapping.employee_id:
                quarantine_vals.append({
                    'user_id': p['user_id'],
                    'timestamp': p['timestamp'],
                    'event_type': p['event_type'],
                    'device_id': p['device_sn'],
                    'error_reason': f'Device user ID {p["user_id"]} is mapped on {p["device_sn"]} but has no linked employee.',
                    'raw_data': json.dumps(p['record'], default=str),
                    'reviewed': False,
                })
                continue
                
            existing = existing_map.get((device.id, p['user_id'], p['timestamp']))
            if existing:
                existing.write({
                    'event_type': p['event_type'],
                    'raw_data': json.dumps(p['record'], default=str),
                    'state': 'draft',
                })
                processed_count += 1
            else:
                vals_to_create.append({
                    'device_id': device.id,
                    'device_user_id': p['user_id'],
                    'timestamp': p['timestamp'],
                    'event_type': p['event_type'],
                    'employee_id': user_mapping.employee_id.id,
                    'state': 'draft',
                    'raw_data': json.dumps(p['record'], default=str),
                })
                processed_count += 1
                
        # Step 6: Bulk create records
        if vals_to_create:
            self.env['zkteco.attendance'].create(vals_to_create)
        if quarantine_vals:
            self.env['zkteco.quarantine'].create(quarantine_vals)
            _logger.warning(f"Quarantined {len(quarantine_vals)} records due to missing mappings or errors")
            
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
            pin = kv.get("pin") or kv.get("uid") or kv.get("userid")
            name = kv.get("name") or kv.get("username") or ""
            
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
