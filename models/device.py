import logging
from datetime import timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class ZKTecoDevice(models.Model):
    _name = 'zkteco.device'
    _description = 'ZKTeco Device'

    name = fields.Char(string='Device Name', required=True)
    serial_number = fields.Char(string='Serial Number', required=True, copy=False)
    ip_address = fields.Char(string='IP Address')
    last_sync = fields.Datetime(string='Last Sync')

    active = fields.Boolean(string='Active', default=True)
    is_active = fields.Boolean(string='Is Active', default=True)
    is_online = fields.Boolean(
        string='Is Online',
        compute='_compute_is_online',
        search='_search_is_online',
        inverse='_inverse_is_online',
    )

    online_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
    ], string='Status', compute='_compute_online_status', store=False)

    user_mapping_ids = fields.One2many('zkteco.user.mapping', 'device_id', string='Device Users')

    user_count = fields.Integer(
        string='Users',
        compute='_compute_counts',
        store=False,
    )
    attendance_log_count = fields.Integer(
        string='Punches',
        compute='_compute_counts',
        store=False,
    )

    # ── Computed Fields ────────────────────────────────────────────────

    @api.depends('last_sync', 'ip_address')
    def _compute_is_online(self):
        for device in self:
            if device.ip_address == 'cloud':
                device.is_online = True
            elif device.last_sync and fields.Datetime.now() - device.last_sync < timedelta(seconds=60):
                device.is_online = True
            else:
                device.is_online = False

    def _inverse_is_online(self):
        pass

    def _search_is_online(self, operator, value):
        if operator not in ('=', '!='):
            raise ValueError("Unsupported operator")
        limit_time = fields.Datetime.now() - timedelta(seconds=60)
        
        # Build domain
        domain = ['|', ('ip_address', '=', 'cloud'), ('last_sync', '>=', limit_time)]
        
        if (operator == '=' and value) or (operator == '!=' and not value):
            return domain
        else:
            return ['!', '&', ('ip_address', '!=', 'cloud'), ('last_sync', '<', limit_time)]

    @api.depends('last_sync', 'ip_address')
    def _compute_online_status(self):
        for device in self:
            if device.is_online:
                device.online_status = 'online'
            else:
                device.online_status = 'offline'

    @api.depends('user_mapping_ids')
    def _compute_counts(self):
        att_obj = self.env['zkteco.attendance'].sudo()
        for device in self:
            device.user_count = len(device.user_mapping_ids)
            device.attendance_log_count = att_obj.search_count([
                ('device_id', '=', device.id)
            ])

    # ── Constraints ───────────────────────────────────────────────────

    _sql_constraints = [
        ('serial_number_unique', 'unique(serial_number)', 'The serial number must be unique!')
    ]

    # ── Smart Button Actions ───────────────────────────────────────────

    def action_open_users(self):
        """Smart button: open the user mapping list for this device."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Device Users — %s' % self.name,
            'res_model': 'zkteco.user.mapping',
            'view_mode': 'tree,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

    def action_open_attendance(self):
        """Smart button: open all raw attendance logs for this device."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Attendance Logs — %s' % self.name,
            'res_model': 'zkteco.attendance',
            'view_mode': 'tree,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

    # ── Device Command Actions ─────────────────────────────────────────

    def action_fetch_users(self):
        """
        Fetch all enrolled users from the device.
        Proven command: DATA QUERY tablename=user  (result via /iclock/querydata)
        """
        for device in self:
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': 'DATA QUERY tablename=user',
            })
            _logger.info("Device %s: queued user fetch command.", device.name)
        return self._notification_success(_('Command sent — users will appear in the Device Users tab within seconds.'))

    def action_fetch_logs(self):
        """
        Fetch all stored attendance logs from the device.
        Using the transaction table (same proven protocol style as user query).
        """
        for device in self:
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': 'DATA QUERY tablename=transaction',
            })
            _logger.info("Device %s: queued log fetch command.", device.name)
        return self._notification_success(_('Command sent — attendance logs will arrive shortly.'))

    def _notification_success(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Command Queued'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
