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
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW attendance_report_line AS (
                SELECT
                    ha.id as id,
                    ha.employee_id as employee_id,
                    CAST(ha.check_in AS DATE) as date,
                    ha.check_in as check_in,
                    ha.check_out as check_out,
                    ha.shift_id as shift_id,

                    -- Worked Hours
                    EXTRACT(EPOCH FROM (ha.check_out - ha.check_in)) / 3600 as work_hours,

                    -- Late Minutes
                    GREATEST(0,
                        (EXTRACT(EPOCH FROM (ha.check_in - (date_trunc('day', ha.check_in) + (s.start_time * interval '1 hour')))) / 60)
                        - s.grace_in
                    ) as late_minutes,

                    -- Early Departure Minutes
                    GREATEST(0,
                        (EXTRACT(EPOCH FROM ((date_trunc('day', ha.check_in) + (s.end_time * interval '1 hour')) - ha.check_out)) / 60)
                        - s.grace_out
                    ) as early_departure_minutes,

                    -- Overtime Hours
                    GREATEST(0,
                        EXTRACT(EPOCH FROM (ha.check_out - (date_trunc('day', ha.check_in) + (s.end_time * interval '1 hour')))) / 3600
                    ) as overtime_hours,

                    CASE
                        WHEN (EXTRACT(EPOCH FROM (ha.check_in - (date_trunc('day', ha.check_in) + (s.start_time * interval '1 hour')))) / 60) > s.grace_in THEN 'Late'
                        WHEN (EXTRACT(EPOCH FROM ((date_trunc('day', ha.check_in) + (s.end_time * interval '1 hour')) - ha.check_out)) / 60) > s.grace_out THEN 'Early Departure'
                        WHEN ha.check_out IS NULL THEN 'Missing Punch'
                        ELSE 'Normal'
                    END as status

                FROM
                    hr_attendance ha
                LEFT JOIN
                    zkteco_shift s ON ha.shift_id = s.id
                WHERE
                    ha.employee_id IS NOT NULL
            )
        """)
