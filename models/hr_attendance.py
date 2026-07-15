from odoo import models, fields

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    shift_id = fields.Many2one('zkteco.shift', string='Assigned Shift')
    attendance_record_id = fields.Many2one(
        'zkteco.attendance.record',
        string='Daily Attendance Record',
        ondelete='set null',
        index=True,
    )
