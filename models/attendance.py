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

    # Employee History Metrics (Computed for the form view)
    emp_present_days = fields.Integer(string='Present Days', compute='_compute_emp_history')
    emp_absent_days = fields.Integer(string='Absent Days', compute='_compute_emp_history')
    emp_worked_hours = fields.Float(string='Total Worked Hours', compute='_compute_emp_history')
    emp_overtime_hours = fields.Float(string='Total Overtime', compute='_compute_emp_history')
    
    daily_status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Incomplete'),
        ('on_leave', 'On Leave'),
    ], string='Attendance Status', compute='_compute_daily_status')

    @api.depends('employee_id', 'punch_date')
    def _compute_daily_status(self):
        for log in self:
            if not log.employee_id or not log.punch_date:
                log.daily_status = False
                continue
            
            record = self.env['zkteco.attendance.record'].search([
                ('employee_id', '=', log.employee_id.id),
                ('date', '=', log.punch_date)
            ], limit=1)
            
            if record:
                log.daily_status = record.status
            else:
                log.daily_status = False

    @api.depends('employee_id')
    def _compute_emp_history(self):
        for log in self:
            if not log.employee_id:
                log.emp_present_days = 0
                log.emp_absent_days = 0
                log.emp_worked_hours = 0.0
                log.emp_overtime_hours = 0.0
                continue
                
            records = self.env['zkteco.attendance.record'].search([('employee_id', '=', log.employee_id.id)])
            log.emp_present_days = len(records.filtered(lambda r: r.status in ['present', 'on_leave']))
            log.emp_absent_days = len(records.filtered(lambda r: r.status == 'absent'))
            log.emp_worked_hours = sum(records.mapped('worked_hours'))
            log.emp_overtime_hours = sum(records.mapped('overtime_hours'))

    def _compute_punch_date(self):
        for log in self:
            log.punch_date = log.timestamp.date() if log.timestamp else False

    def action_process_logs(self):
        """Processes draft logs and creates hr.attendance records in batches."""
        batch_size = 100
        while True:
            draft_logs = self.search([('state', '=', 'draft')], order='timestamp asc', limit=batch_size)
            if not draft_logs:
                break

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

        # Fuzzy matching duplicate check: +/- 60 seconds
        from datetime import timedelta
        time_min = timestamp - timedelta(seconds=60)
        time_max = timestamp + timedelta(seconds=60)
        duplicate = attendance_obj.search([
            ('employee_id', '=', employee.id),
            '|',
            '&', ('check_in', '>=', time_min), ('check_in', '<=', time_max),
            '&', ('check_out', '>=', time_min), ('check_out', '<=', time_max)
        ], limit=1)

        if duplicate:
            _logger.info("Duplicate check-in/out detected for employee %s at %s (within +/- 60s of existing record). Skipping.", employee.name, timestamp)
            return

        # 1. Find the active shift for this employee on this date
        shift = self.env['zkteco.employee.shift'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', timestamp.date()),
            ('date_end', '>=', timestamp.date()),
        ], limit=1)
        shift_id = shift.shift_id.id if shift else False

        # Find any currently open attendance for this employee
        open_attendance = attendance_obj.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        if open_attendance:
            from datetime import timedelta
            time_diff = timestamp - open_attendance.check_in
            
            # If the punch is within 20 hours of check-in, treat it as the check-out
            # This correctly handles night shifts that cross midnight
            if time_diff < timedelta(hours=20):
                open_attendance.write({
                    'check_out': timestamp,
                    'shift_id': shift_id or open_attendance.shift_id,
                })
                return
            else:
                # They missed their check-out on a previous day.
                # Auto-close it to 8 hours after check-in so this new punch can succeed.
                auto_checkout = open_attendance.check_in + timedelta(hours=8)
                open_attendance.write({
                    'check_out': auto_checkout
                })
                # Fall through to create the new check-in

        # Create a new check-in
        attendance_obj.create({
            'employee_id': employee.id,
            'check_in': timestamp,
            'shift_id': shift_id,
        })

