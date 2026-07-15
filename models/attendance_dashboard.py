import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ZKTecoAttendanceDashboard(models.Model):
    _name = 'zkteco.attendance.dashboard'
    _description = 'ZKTeco Attendance Dashboard'
    _order = 'name'

    name = fields.Char(string='Dashboard', default='Today\'s Attendance', required=True)

    # ── Computed KPI fields ──────────────────────────────────────────────────

    total_expected = fields.Integer(
        string='Total Expected',
        compute='_compute_kpis',
    )
    present_count = fields.Integer(
        string='Present Today',
        compute='_compute_kpis',
    )
    absent_count = fields.Integer(
        string='Absent Today',
        compute='_compute_kpis',
    )
    missed_punch_count = fields.Integer(
        string='Missed Punch',
        compute='_compute_kpis',
    )
    on_leave_count = fields.Integer(
        string='On Leave',
        compute='_compute_kpis',
    )

    @api.depends_context('uid')
    def _compute_kpis(self):
        today = fields.Date.today()
        records = self.env['zkteco.attendance.record'].search([('date', '=', today)])
        total = len(records)
        present = len(records.filtered(lambda r: r.status == 'present'))
        absent = len(records.filtered(lambda r: r.status == 'absent'))
        missed = len(records.filtered(lambda r: r.status == 'missed_punch'))
        on_leave = len(records.filtered(lambda r: r.status == 'on_leave'))
        for rec in self:
            rec.total_expected = total
            rec.present_count = present
            rec.absent_count = absent
            rec.missed_punch_count = missed
            rec.on_leave_count = on_leave

    # ── Action buttons ───────────────────────────────────────────────────────

    def action_view_all_today(self):
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'All Employees Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today)],
        }

    def action_view_present_today(self):
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Present Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'present')],
        }

    def action_view_absent_today(self):
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Absent Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'absent')],
        }

    def action_view_missed_punch_today(self):
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Missed Punch Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'missed_punch')],
        }

    def action_view_on_leave_today(self):
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'On Leave Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'on_leave')],
        }
