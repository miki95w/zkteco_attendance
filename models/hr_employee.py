from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    zkteco_device_id = fields.Char(string='ZKTeco Device User ID', help="The User ID used on the ZKTeco device.")
    attendance_record_ids = fields.One2many('zkteco.attendance.record', 'employee_id', string='Attendance History')
