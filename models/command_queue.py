from odoo import models, fields, api

class ZKTecoCommandQueue(models.Model):
    _name = 'zkteco.command.queue'
    _description = 'ZKTeco Command Queue'
    _order = 'create_date asc'

    device_id = fields.Many2one('zkteco.device', string='Device', required=True, ondelete='cascade')
    command_string = fields.Char(string='Command', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent')
    ], default='pending', string='Status')
