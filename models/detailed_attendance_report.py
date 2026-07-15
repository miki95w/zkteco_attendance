import logging
from odoo import models, fields, api, tools

_logger = logging.getLogger(__name__)


class DetailedAttendanceReport(models.Model):
    """Detailed attendance report with all punch details."""
    
    _name = 'zkteco.detailed.attendance.report'
    _description = 'Detailed Attendance Report'
    _auto = False
    _order = 'date desc, employee_id'
    
    # Employee Information
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)
    
    # Date and Status
    date = fields.Date(string='Date', readonly=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('incomplete', 'Incomplete'),
        ('on_leave', 'On Leave'),
    ], string='Attendance', readonly=True)
    
    # Punch Times
    first_checkin = fields.Datetime(string='First Check-in', readonly=True)
    last_checkout = fields.Datetime(string='Last Check-out', readonly=True)
    
    # Working Hours
    work_hours = fields.Float(string='Work Min', readonly=True, help='Worked minutes')
    late_minutes = fields.Float(string='Late', readonly=True, help='Late arrival in minutes')
    early_leave_minutes = fields.Float(string='Early Leave', readonly=True, help='Early departure in minutes')
    
    # Late/Early Flags
    late_min = fields.Integer(string='Late (min)', readonly=True)
    early_min = fields.Integer(string='Early (min)', readonly=True)
    
    # Overtime
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)
    
    # Approval Status
    approval_status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Status', readonly=True, default='draft')
    
    # Shift Information
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)
    expected_hours = fields.Float(string='Expected Hours', readonly=True)
    
    # Remarks
    remarks = fields.Text(string='Remarks', readonly=True)
    
    def init(self):
        """Create the view that powers this model."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    ar.id AS id,
                    ar.employee_id AS employee_id,
                    ar.department_id AS department_id,
                    ar.job_id AS job_id,
                    ar.date AS date,
                    CASE 
                        WHEN ar.status = 'present' THEN 'present'
                        WHEN ar.status = 'absent' THEN 'absent'
                        WHEN ar.status = 'missed_punch' THEN 'incomplete'
                        WHEN ar.status = 'on_leave' THEN 'on_leave'
                        ELSE 'absent'
                    END AS status,
                    ar.first_checkin AS first_checkin,
                    ar.last_checkout AS last_checkout,
                    ar.worked_hours * 60 AS work_hours,
                    COALESCE(ar.late_minutes, 0)::float AS late_minutes,
                    COALESCE(ar.early_leave_minutes, 0)::float AS early_leave_minutes,
                    COALESCE(ar.late_minutes, 0)::integer AS late_min,
                    COALESCE(ar.early_leave_minutes, 0)::integer AS early_min,
                    CASE 
                        WHEN ar.worked_hours > ar.expected_hours 
                        THEN (ar.worked_hours - ar.expected_hours)
                        ELSE 0
                    END AS overtime_hours,
                    'draft' AS approval_status,
                    ar.shift_id AS shift_id,
                    ar.expected_hours AS expected_hours,
                    ar.remarks AS remarks
                FROM 
                    zkteco_attendance_record ar
                WHERE 
                    ar.employee_id IS NOT NULL
            )
        """ % self._table
        self.env.cr.execute(query)
