import logging
from datetime import datetime, time, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AttendanceRecord(models.Model):
    """Daily attendance record with status tracking."""
    
    _name = 'zkteco.attendance.record'
    _description = 'Daily Attendance Record'
    _order = 'date desc, employee_id'
    _rec_name = 'display_name'
    
    # Basic Information
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade', index=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, index=True)
    department_id = fields.Many2one('hr.department', string='Department', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', string='Job Position', related='employee_id.job_id', store=True)
    
    # Status
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Missed Punch'),
        ('on_leave', 'On Leave'),
    ], string='Status', compute='_compute_status', store=True, index=True)
    
    # Punch Times
    first_checkin = fields.Datetime(string='First Check-in', compute='_compute_punch_times', store=True)
    last_checkout = fields.Datetime(string='Last Check-out', compute='_compute_punch_times', store=True)
    total_punches = fields.Integer(string='Total Punches', compute='_compute_punch_times', store=True)
    
    # Attendance Records
    attendance_ids = fields.One2many('hr.attendance', 'attendance_record_id', string='Attendance Records')
    attendance_count = fields.Integer(string='Attendance Count', compute='_compute_attendance_count')
    
    # Working Hours
    worked_hours = fields.Float(string='Worked Hours', compute='_compute_worked_hours', store=True)
    expected_hours = fields.Float(string='Expected Hours', default=8.0)
    
    # Shift Information
    shift_id = fields.Many2one('zkteco.shift', string='Assigned Shift')
    shift_start = fields.Float(string='Shift Start', related='shift_id.start_time', store=True)
    shift_end = fields.Float(string='Shift End', related='shift_id.end_time', store=True)
    
    # Late/Early
    is_late = fields.Boolean(string='Late Arrival', compute='_compute_late_early', store=True)
    is_early_leave = fields.Boolean(string='Early Leave', compute='_compute_late_early', store=True)
    late_minutes = fields.Integer(string='Late Minutes', compute='_compute_late_early', store=True)
    early_leave_minutes = fields.Integer(string='Early Leave Minutes', compute='_compute_late_early', store=True)
    
    # Notes
    remarks = fields.Text(string='Remarks')
    
    # Display
    display_name = fields.Char(string='Display Name', compute='_compute_display_name')
    
    # Colors for UI
    color = fields.Integer(string='Color', compute='_compute_color')

    employee_history_ids = fields.One2many(
        'zkteco.attendance.record', 'employee_id',
        string='Employee History',
        compute='_compute_employee_history_ids'
    )

    def _compute_employee_history_ids(self):
        """Compute other attendance records for the same employee."""
        for record in self:
            if record.employee_id:
                record.employee_history_ids = self.env['zkteco.attendance.record'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('id', '!=', record.id)
                ])
            else:
                record.employee_history_ids = self.env['zkteco.attendance.record']

    _sql_constraints = [

        ('employee_date_unique', 'unique(employee_id, date)', 
         'An attendance record already exists for this employee on this date!')
    ]
    
    @api.depends('employee_id', 'date', 'status')
    def _compute_display_name(self):
        """Compute display name."""
        for record in self:
            if record.employee_id and record.date:
                record.display_name = f"{record.employee_id.name} - {record.date} ({record.status or 'Unknown'})"
            else:
                record.display_name = "New Attendance Record"
    
    @api.depends('status')
    def _compute_color(self):
        """Compute color for kanban/tree view."""
        color_map = {
            'present': 10,      # Green
            'absent': 1,        # Red
            'missed_punch': 3,  # Yellow
            'on_leave': 4,      # Blue
        }
        for record in self:
            record.color = color_map.get(record.status, 0)
    
    @api.depends('attendance_ids', 'attendance_ids.check_in', 'attendance_ids.check_out')
    def _compute_punch_times(self):
        """Compute first check-in, last check-out, and total punches."""
        for record in self:
            attendances = record.attendance_ids.sorted(key=lambda a: a.check_in)
            
            if attendances:
                record.first_checkin = attendances[0].check_in
                # Last check-out from the last attendance record
                last_att = attendances[-1]
                record.last_checkout = last_att.check_out if last_att.check_out else False
                # Count total check-ins (punches)
                record.total_punches = len(attendances)
            else:
                record.first_checkin = False
                record.last_checkout = False
                record.total_punches = 0
    
    @api.depends('attendance_ids')
    def _compute_attendance_count(self):
        """Count attendance records."""
        for record in self:
            record.attendance_count = len(record.attendance_ids)
    
    @api.depends('attendance_ids', 'attendance_ids.worked_hours')
    def _compute_worked_hours(self):
        """Compute total worked hours."""
        for record in self:
            record.worked_hours = sum(record.attendance_ids.mapped('worked_hours'))
    
    @api.depends('first_checkin', 'last_checkout', 'total_punches', 'date')
    def _compute_status(self):
        """
        Compute attendance status:
        - Present: At least one check-in
        - Missed Punch: Check-in but no check-out
        - Absent: No punches at all
        - On Leave: Has approved leave
        """
        for record in self:
            # Check for approved leave (if hr_holidays module is installed)
            leave = False
            if 'hr.leave' in self.env:
                leave = self.env['hr.leave'].sudo().search([
                    ('employee_id', '=', record.employee_id.id),
                    ('state', '=', 'validate'),
                    ('date_from', '<=', record.date),
                    ('date_to', '>=', record.date),
                ], limit=1)
            
            if leave:
                record.status = 'on_leave'
            elif record.total_punches == 0:
                record.status = 'absent'
            elif record.total_punches > 0:
                # Check if all attendances have check-out
                incomplete = record.attendance_ids.filtered(lambda a: not a.check_out)
                if incomplete:
                    record.status = 'missed_punch'
                else:
                    record.status = 'present'
            else:
                record.status = 'absent'
    
    @api.depends('first_checkin', 'last_checkout', 'shift_start', 'shift_end')
    def _compute_late_early(self):
        """Compute if employee is late or left early."""
        for record in self:
            record.is_late = False
            record.is_early_leave = False
            record.late_minutes = 0
            record.early_leave_minutes = 0
            
            if not record.shift_id:
                continue
            
            # Convert shift times (float hours) to datetime
            if record.first_checkin and record.shift_start:
                shift_start_dt = datetime.combine(
                    record.date,
                    time(hour=int(record.shift_start), minute=int((record.shift_start % 1) * 60))
                )
                
                if record.first_checkin > shift_start_dt:
                    record.is_late = True
                    delta = record.first_checkin - shift_start_dt
                    record.late_minutes = int(delta.total_seconds() / 60)
            
            # Check early leave
            if record.last_checkout and record.shift_end:
                shift_end_dt = datetime.combine(
                    record.date,
                    time(hour=int(record.shift_end), minute=int((record.shift_end % 1) * 60))
                )
                
                if record.last_checkout < shift_end_dt:
                    record.is_early_leave = True
                    delta = shift_end_dt - record.last_checkout
                    record.early_leave_minutes = int(delta.total_seconds() / 60)
    
    def action_view_attendances(self):
        """Open attendance records for this day."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendance Records - %s') % self.display_name,
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.attendance_ids.ids)],
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_check_in': datetime.combine(self.date, time(9, 0)),
            },
        }
    
    def action_mark_absent(self):
        """Manually mark as absent."""
        for record in self:
            if record.status != 'absent':
                record.remarks = (record.remarks or '') + '\n' + _('Manually marked absent on %s') % fields.Datetime.now()
            # Status will be recomputed based on attendance_ids
    
    def action_mark_present(self):
        """Manually create attendance record."""
        self.ensure_one()
        
        # Create a default attendance record
        self.env['hr.attendance'].create({
            'employee_id': self.employee_id.id,
            'check_in': datetime.combine(self.date, time(9, 0)),
            'check_out': datetime.combine(self.date, time(17, 0)),
            'attendance_record_id': self.id,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Attendance Created'),
                'message': _('Default attendance record created for %s') % self.employee_id.name,
                'type': 'success',
                'sticky': False,
            }
        }
    
    @api.model
    def generate_daily_records(self, target_date=None):
        """
        Generate attendance records for all active employees for a given date.
        Called by cron job daily. Optimized to prevent N+1 queries.
        """
        if not target_date:
            target_date = fields.Date.today()
        
        # Get all active employees
        employees = self.env['hr.employee'].search([
            ('active', '=', True),
        ])
        
        # Find already existing attendance records for the target date to avoid duplicates
        existing_records = self.search([('date', '=', target_date)])
        existing_employee_ids = set(existing_records.mapped('employee_id.id'))
        
        # Find active employees who don't have an attendance record for this day
        missing_employees = employees.filtered(lambda e: e.id not in existing_employee_ids)
        
        if not missing_employees:
            _logger.info(f"All active employees already have attendance records for {target_date}")
            return 0
        
        # Batch search all shift assignments overlapping with target_date
        shift_assignments = self.env['zkteco.employee.shift'].sudo().search([
            ('employee_id', 'in', missing_employees.ids),
            ('date_start', '<=', target_date),
            ('date_end', '>=', target_date),
        ])
        employee_shift_map = {sa.employee_id.id: sa.shift_id.id for sa in shift_assignments}
        
        vals_list = []
        for employee in missing_employees:
            vals_list.append({
                'employee_id': employee.id,
                'date': target_date,
                'shift_id': employee_shift_map.get(employee.id, False),
            })
            
        if vals_list:
            self.create(vals_list)
            
        created = len(vals_list)
        _logger.info(f"Generated {created} attendance records for {target_date}")
        return created
    
    @api.model
    def auto_mark_absent(self, target_date=None):
        """
        Automatically mark employees as absent if they didn't punch in.
        Called by cron job at end of day.
        """
        if not target_date:
            target_date = fields.Date.today()
        
        # Find all records for the date with no punches and not on leave
        absent_records = self.search([
            ('date', '=', target_date),
            ('status', '=', 'absent'),
        ])
        
        for record in absent_records:
            if not record.remarks:
                record.remarks = _('Automatically marked absent - No punch recorded on %s') % target_date
        
        _logger.info(f"Auto-marked {len(absent_records)} employees as absent for {target_date}")
        return len(absent_records)
    
    @api.model
    def _cron_generate_daily_records(self):
        """Cron job to generate daily records."""
        return self.generate_daily_records()
    
    @api.model
    def _cron_auto_mark_absent(self):
        """Cron job to auto-mark absent employees."""
        # Mark yesterday's absences (give a grace period)
        yesterday = fields.Date.today() - timedelta(days=1)
        return self.auto_mark_absent(yesterday)





