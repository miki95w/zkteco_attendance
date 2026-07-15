from odoo import models, fields, api

class ZKTecoUserMapping(models.Model):
    _name = 'zkteco.user.mapping'
    _description = 'ZKTeco User Mapping'
    _order = 'device_user_id asc'

    device_user_id = fields.Char(string='Device User ID', required=True, index=True)
    device_user_name = fields.Char(string='Device User Name')
    employee_id = fields.Many2one('hr.employee', string='Employee', ondelete='set null')
    device_id = fields.Many2one('zkteco.device', string='Device', ondelete='cascade')

    attendance_count = fields.Integer(
        string='Punches',
        compute='_compute_attendance_count',
        store=False,
    )
    last_punch = fields.Datetime(
        string='Last Punch',
        compute='_compute_attendance_count',
        store=False,
    )

    @api.depends('device_user_id', 'device_id')
    def _compute_attendance_count(self):
        att_obj = self.env['zkteco.attendance'].sudo()
        for rec in self:
            domain = [('device_user_id', '=', rec.device_user_id)]
            if rec.device_id:
                domain.append(('device_id', '=', rec.device_id.id))
            logs = att_obj.search(domain, order='timestamp desc')
            rec.attendance_count = len(logs)
            rec.last_punch = logs[0].timestamp if logs else False

    def action_view_attendance(self):
        """Open raw attendance logs for this device user."""
        self.ensure_one()
        domain = [('device_user_id', '=', self.device_user_id)]
        if self.device_id:
            domain.append(('device_id', '=', self.device_id.id))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Attendance Logs — %s' % (self.device_user_name or self.device_user_id),
            'res_model': 'zkteco.attendance',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {'default_device_user_id': self.device_user_id},
        }

    def action_view_hr_attendance(self):
        """Open hr.attendance records for the linked employee."""
        self.ensure_one()
        if not self.employee_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': 'HR Attendance — %s' % self.employee_id.name,
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.employee_id.id)],
        }

    @api.model
    def action_fetch_all_device_users(self):
        """Queue a user fetch command for all registered devices."""
        devices = self.env['zkteco.device'].search([])
        for device in devices:
            self.env['zkteco.command.queue'].create({
                'device_id': device.id,
                'command_string': 'DATA QUERY tablename=user',
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Command Sent',
                'message': 'Queued user sync command for all connected devices.',
                'type': 'success',
                'sticky': False,
            }
        }

    _sql_constraints = [
        ('device_user_unique', 'unique(device_id, device_user_id)',
         'This Device User ID already exists on this device!')
    ]
