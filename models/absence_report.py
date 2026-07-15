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
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW attendance_absence_report AS (
                WITH RECURSIVE date_range AS (
                    SELECT MIN(date_start) as d_date, MAX(date_end) as max_date FROM zkteco_employee_shift
                    UNION ALL
                    SELECT d_date + 1, max_date FROM date_range WHERE d_date < max_date
                ),
                expected_work AS (
                    SELECT
                        es.employee_id,
                        dr.d_date as work_date,
                        es.shift_id
                    FROM
                        date_range dr
                    JOIN
                        zkteco_employee_shift es ON dr.d_date BETWEEN es.date_start AND es.date_end
                )
                SELECT
                    row_number() over (order by ew.employee_id, ew.work_date) as id,
                    ew.employee_id as employee_id,
                    ew.work_date as date,
                    ew.shift_id as shift_id
                FROM
                    expected_work ew
                LEFT JOIN
                    hr_attendance ha ON ha.employee_id = ew.employee_id AND CAST(ha.check_in AS DATE) = ew.work_date
                WHERE
                    ha.id IS NULL
            )
        """)
