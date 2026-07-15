from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ZKTecoAttendance(models.Model):
    _name = 'zkteco.attendance'
    _description = 'ZKTeco Attendance Log'
    _order = 'timestamp desc'

    device_id = fields.Many2one('zkteco.device', string='Device', required=True)
    device_user_id = fields.Char(string='Device User ID', required=True, index=True)
    timestamp = fields.Datetime(string='Timestamp', required=True)
    punch_date = fields.Date(string='Punch Date', compute='_compute_punch_date', store=True)
    event_type = fields.Integer(string='Event Type')

    raw_data = fields.Text(string='Raw Data')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('error', 'Error')
    ], string='Status', default='draft', index=True)
    employee_id = fields.Many2one('hr.employee', string='Employee')
    error_message = fields.Text(string='Error Message')

    def _compute_punch_date(self):
        for log in self:
            log.punch_date = log.timestamp.date() if log.timestamp else False

    def action_process_logs(self):

        """Processes draft logs and creates hr.attendance records."""
        draft_logs = self.search([('state', '=', 'draft')])
        for log in draft_logs:
            try:
                with self.env.cr.savepoint():
                    # 1. Find mapping
                    mapping = self.env['zkteco.user.mapping'].search([
                        ('device_user_id', '=', log.device_user_id),
                        ('device_id', '=', log.device_id.id)
                    ], limit=1)

                    if not mapping:
                        log.write({
                            'state': 'error',
                            'error_message': f'No mapping found for Device User ID {log.device_user_id}'
                        })
                        continue

                    employee = mapping.employee_id
                    if not employee:
                        log.write({
                            'state': 'error',
                            'error_message': f'Device User ID {log.device_user_id} mapping exists but has no linked Employee.'
                        })
                        continue

                    log.employee_id = employee

                    # 2. Create or update hr.attendance record
                    self._create_or_update_hr_attendance(employee, log.timestamp)
                    log.write({
                        'state': 'processed',
                        'error_message': False
                    })
            except Exception as e:
                _logger.error(f"Error processing ZKTeco log {log.id}: {str(e)}")
                # Outer write to update state in case of savepoint rollback
                try:
                    with self.env.cr.savepoint():
                        log.write({
                            'state': 'error',
                            'error_message': str(e)
                        })
                except Exception as inner_e:
                    _logger.critical(f"Failed to write error state for log {log.id}: {inner_e}")

    def _create_or_update_hr_attendance(self, employee, timestamp):
        """Helper to integrate with Odoo's standard hr.attendance."""
        attendance_obj = self.env['hr.attendance']

        # 1. Find the active shift for this employee on this date
        shift = self.env['zkteco.employee.shift'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', timestamp.date()),
            ('date_end', '>=', timestamp.date()),
        ], limit=1)
        shift_id = shift.shift_id.id if shift else False

        # Find the last attendance for the employee today
        date_start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = timestamp.replace(hour=23, minute=59, second=59, microsecond=999999)

        last_attendance = attendance_obj.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', date_start),
            ('check_in', '<=', date_end),
        ], order='check_in desc', limit=1)

        if last_attendance and not last_attendance.check_out:
            # If there's an open attendance, this is a check-out
            last_attendance.write({
                'check_out': timestamp,
                'shift_id': shift_id or last_attendance.shift_id,
            })
        else:
            # Otherwise, create a new check-in
            attendance_obj.create({
                'employee_id': employee.id,
                'check_in': timestamp,
                'shift_id': shift_id,
            })

