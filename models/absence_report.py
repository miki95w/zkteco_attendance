from odoo import models, fields, tools

class AttendanceAbsenceReport(models.Model):
    _name = 'attendance.absence.report'
    _description = 'Attendance Absence Report'
    _auto = False

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Expected Shift', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'attendance_absence_report')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW attendance_absence_report AS (
                SELECT
                    id,
                    employee_id,
                    date,
                    shift_id
                FROM
                    zkteco_attendance_record
                WHERE
                    status = 'absent'
            )
        """)
