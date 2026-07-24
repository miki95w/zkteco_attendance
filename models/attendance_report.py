from odoo import models, fields, api, tools

class AttendanceReportLine(models.Model):
    _name = 'attendance.report.line'
    _description = 'Attendance Report Line'
    _auto = False
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    check_in = fields.Datetime(string='Check In', readonly=True)
    check_out = fields.Datetime(string='Check Out', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    work_hours = fields.Float(string='Worked Hours', readonly=True)
    late_minutes = fields.Float(string='Late Minutes', readonly=True)
    early_departure_minutes = fields.Float(string='Early Departure Minutes', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)

    status = fields.Char(string='Status', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'attendance_report_line')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW attendance_report_line AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.date as date,
                    ar.first_checkin as check_in,
                    ar.last_checkout as check_out,
                    ar.shift_id as shift_id,
                    ar.worked_hours as work_hours,
                    ar.late_minutes as late_minutes,
                    ar.early_leave_minutes as early_departure_minutes,
                    ar.overtime_hours as overtime_hours,
                    CASE
                        WHEN ar.status = 'absent' THEN 'Absent'
                        WHEN ar.status = 'on_leave' THEN 'On Leave'
                        WHEN ar.status = 'missed_punch' THEN 'Missing Punch'
                        WHEN ar.is_late THEN 'Late'
                        WHEN ar.is_early_leave THEN 'Early Departure'
                        ELSE 'Normal'
                    END as status
                FROM
                    zkteco_attendance_record ar
                WHERE
                    ar.employee_id IS NOT NULL
            )
        """)
