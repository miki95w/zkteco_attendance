from odoo import models, fields, api

class ZKTecoSyncReport(models.Model):
    _name = 'zkteco.sync.report'
    _description = 'ZKTeco Sync Report'
    _auto = False

    device_id = fields.Many2one('zkteco.device', string='Device', readonly=True)
    raw_logs_count = fields.Integer(string='Raw Logs', readonly=True)
    processed_records_count = fields.Integer(string='Processed Records', readonly=True)
    sync_rate = fields.Float(string='Sync Rate (%)', readonly=True)
    error_count = fields.Integer(string='Error Logs', readonly=True)

    def init(self):
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW zkteco_sync_report AS (
                SELECT
                    d.id as id,
                    d.id as device_id,
                    (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id) as raw_logs_count,
                    (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id AND state = 'processed') as processed_records_count,
                    (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id AND state = 'error') as error_count,
                    CASE
                        WHEN (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id) = 0 THEN 0
                        ELSE (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id AND state = 'processed')::float /
                             (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id)::float * 100
                    END as sync_rate
                FROM
                    zkteco_device d
            )
        """)
