from odoo import models, fields, api

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    shift_id = fields.Many2one('zkteco.shift', string='Assigned Shift')
    attendance_record_id = fields.Many2one(
        'zkteco.attendance.record',
        string='Daily Attendance Record',
        ondelete='set null',
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.check_in and record.employee_id:
                # Convert UTC check_in to employee local date if possible
                timezone = record.employee_id.tz or self.env.user.tz or 'UTC'
                import pytz
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.UTC
                    
                local_dt = pytz.utc.localize(record.check_in).astimezone(tz)
                punch_date = local_dt.date()
                
                att_record = self.env['zkteco.attendance.record'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('date', '=', punch_date)
                ], limit=1)
                
                if not att_record:
                    # Find shift for this day
                    shift = self.env['zkteco.employee.shift'].sudo().search([
                        ('employee_id', '=', record.employee_id.id),
                        ('date_start', '<=', punch_date),
                        ('date_end', '>=', punch_date),
                    ], limit=1)
                    
                    att_record = self.env['zkteco.attendance.record'].create({
                        'employee_id': record.employee_id.id,
                        'date': punch_date,
                        'shift_id': shift.shift_id.id if shift else False,
                    })
                
                record.attendance_record_id = att_record.id
                
        return records
