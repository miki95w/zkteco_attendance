from odoo import models, fields, api

class ZKTecoWorkPolicy(models.Model):
    _name = 'zkteco.work.policy'
    _description = 'ZKTeco Work Policy'

    name = fields.Char(string='Policy Name', required=True)
    policy_type = fields.Selection([
        ('regular', 'Regular Shift'),
        ('night', 'Night Shift'),
        ('flexible', 'Flexible Contract'),
        ('other', 'Other Shift')
    ], string='Policy Type', default='regular', required=True)
    
    # Hours (in float decimal hours, e.g., 8.5 for 08:30)
    start_time = fields.Float(string='Work Start Time', default=9.0, help="Standard work start time (decimal hours)")
    end_time = fields.Float(string='Work End Time', default=17.0, help="Standard work end time (decimal hours)")
    overtime_begin_time = fields.Float(string='Overtime Begins Time', default=18.0, help="Decimal hour after which overtime starts accumulating")
    grace_in = fields.Integer(string='Grace In (Mins)', default=15, help="Minutes allowed after start time before marked as late")
    grace_out = fields.Integer(string='Grace Out (Mins)', default=30, help="Minutes allowed before end time before marked as early leave")
    
    # Shift and Employee Associations
    shift_ids = fields.One2many('zkteco.shift', 'work_policy_id', string='Associated Shifts')
    employee_ids = fields.One2many('hr.employee', 'work_policy_id', string='Assigned Employees')
