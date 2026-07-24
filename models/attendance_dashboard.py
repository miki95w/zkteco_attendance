"""
Attendance Dashboard Model
"""

import logging
from datetime import datetime, date, timedelta
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AttendanceDashboard(models.Model):
    """Attendance Dashboard for overview and statistics."""
    
    _name = 'zkteco.attendance.dashboard'
    _description = 'Attendance Dashboard'
    _rec_name = 'name'
    
    name = fields.Char(string='Dashboard Name', default='Attendance Overview')
    
    # Dashboard Statistics (computed in real-time)
    total_employees = fields.Integer(string='Total Employees', compute='_compute_dashboard_stats')
    present_today = fields.Integer(string='Present Today', compute='_compute_dashboard_stats')
    absent_today = fields.Integer(string='Absent Today', compute='_compute_dashboard_stats')
    missed_punch_today = fields.Integer(string='Missed Punch Today', compute='_compute_dashboard_stats')
    on_leave_today = fields.Integer(string='On Leave Today', compute='_compute_dashboard_stats')
    late_arrivals_today = fields.Integer(string='Late Arrivals Today', compute='_compute_dashboard_stats')
    early_leaves_today = fields.Integer(string='Early Leaves Today', compute='_compute_dashboard_stats')
    
    # Device Statistics
    total_devices = fields.Integer(string='Total Devices', compute='_compute_device_stats')
    online_devices = fields.Integer(string='Online Devices', compute='_compute_device_stats')
    
    # Weekly/Monthly Stats
    attendance_this_week = fields.Float(string='Attendance Rate This Week (%)', compute='_compute_weekly_stats')
    attendance_this_month = fields.Float(string='Attendance Rate This Month (%)', compute='_compute_monthly_stats')
    
    @api.depends()
    def _compute_dashboard_stats(self):
        """Compute today's attendance statistics."""
        for dashboard in self:
            today = fields.Date.today()
            
            # Get all active employees
            total_employees = self.env['hr.employee'].search_count([('active', '=', True)])
            
            # Get today's attendance records
            records_today = self.env['zkteco.attendance.record'].search([
                ('date', '=', today)
            ])
            
            present_count = len(records_today.filtered(lambda r: r.status == 'present'))
            absent_count = len(records_today.filtered(lambda r: r.status == 'absent'))
            missed_punch_count = len(records_today.filtered(lambda r: r.status == 'missed_punch'))
            on_leave_count = len(records_today.filtered(lambda r: r.status == 'on_leave'))
            late_arrivals = len(records_today.filtered(lambda r: r.is_late))
            early_leaves = len(records_today.filtered(lambda r: r.is_early_leave))
            
            dashboard.total_employees = total_employees
            dashboard.present_today = present_count
            dashboard.absent_today = absent_count
            dashboard.missed_punch_today = missed_punch_count
            dashboard.on_leave_today = on_leave_count
            dashboard.late_arrivals_today = late_arrivals
            dashboard.early_leaves_today = early_leaves
    
    @api.depends()
    def _compute_device_stats(self):
        """Compute device statistics."""
        for dashboard in self:
            # Check if device model exists
            if 'zkteco.device' in self.env:
                total_devices = self.env['zkteco.device'].search_count([])
                online_devices = self.env['zkteco.device'].search_count([('is_online', '=', True)])
            else:
                total_devices = 0
                online_devices = 0
            
            dashboard.total_devices = total_devices
            dashboard.online_devices = online_devices
    
    @api.depends()
    def _compute_weekly_stats(self):
        """Compute this week's attendance rate."""
        for dashboard in self:
            # Get start of week (Monday)
            today = fields.Date.today()
            start_of_week = today - timedelta(days=today.weekday())
            
            # Count records for this week
            total_possible = dashboard.total_employees * 5  # 5 working days
            if total_possible == 0:
                dashboard.attendance_this_week = 0
                return
            
            present_records = self.env['zkteco.attendance.record'].search_count([
                ('date', '>=', start_of_week),
                ('date', '<=', today),
                ('status', 'in', ['present', 'on_leave'])
            ])
            
            dashboard.attendance_this_week = (present_records / total_possible) * 100 if total_possible > 0 else 0
    
    @api.depends()
    def _compute_monthly_stats(self):
        """Compute this month's attendance rate."""
        for dashboard in self:
            # Get start of month
            today = fields.Date.today()
            start_of_month = today.replace(day=1)
            
            # Count working days in month (rough estimate: 22 days)
            working_days = 22  # You can make this more accurate
            total_possible = dashboard.total_employees * working_days
            
            if total_possible == 0:
                dashboard.attendance_this_month = 0
                return
            
            present_records = self.env['zkteco.attendance.record'].search_count([
                ('date', '>=', start_of_month),
                ('date', '<=', today),
                ('status', 'in', ['present', 'on_leave'])
            ])
            
            dashboard.attendance_this_month = (present_records / total_possible) * 100 if total_possible > 0 else 0
    
    def action_view_present_today(self):
        """Open present employees today."""
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Present Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'present')],
            'target': 'current',
        }
    
    def action_view_absent_today(self):
        """Open absent employees today."""
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Absent Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'absent')],
            'target': 'current',
        }
    
    def action_view_missed_punch_today(self):
        """Open missed punch employees today."""
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Missed Punch Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'missed_punch')],
            'target': 'current',
        }
    
    def action_view_late_arrivals_today(self):
        """Open late arrivals today."""
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Late Arrivals Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('is_late', '=', True)],
            'target': 'current',
        }
    
    def action_view_detailed_attendance(self):
        """Open detailed attendance records."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Attendance Records',
            'res_model': 'zkteco.detailed.attendance.report',
            'view_mode': 'tree,form,pivot,graph',
            'target': 'current',
        }
    
    def action_refresh_dashboard(self):
        """Refresh dashboard statistics."""
        # Force recomputation of all computed fields
        self._compute_dashboard_stats()
        self._compute_device_stats()
        self._compute_weekly_stats()
        self._compute_monthly_stats()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Dashboard Refreshed',
                'message': 'All statistics have been updated.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_on_leave_today(self):
        """Open employees on leave today."""
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'On Leave Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('status', '=', 'on_leave')],
            'target': 'current',
        }

    def action_view_early_leaves_today(self):
        """Open employees who left early today."""
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Early Departures Today',
            'res_model': 'zkteco.attendance.record',
            'view_mode': 'tree,form',
            'domain': [('date', '=', today), ('early_departure', '=', True)],
            'target': 'current',
        }


class AttendanceDashboardWizard(models.TransientModel):
    """Wizard to display attendance dashboard."""
    
    _name = 'zkteco.attendance.dashboard.wizard'
    _description = 'Attendance Dashboard Wizard'
    
    def get_dashboard_data(self):
        """Get dashboard data for display."""
        dashboard = self.env['zkteco.attendance.dashboard'].create({})
        return {
            'total_employees': dashboard.total_employees,
            'present_today': dashboard.present_today,
            'absent_today': dashboard.absent_today,
            'missed_punch_today': dashboard.missed_punch_today,
            'on_leave_today': dashboard.on_leave_today,
            'late_arrivals_today': dashboard.late_arrivals_today,
            'early_leaves_today': dashboard.early_leaves_today,
            'total_devices': dashboard.total_devices,
            'online_devices': dashboard.online_devices,
            'attendance_this_week': dashboard.attendance_this_week,
            'attendance_this_month': dashboard.attendance_this_month,
        }