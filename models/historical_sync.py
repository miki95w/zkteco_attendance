from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, timedelta

class ZKtecoHistoricalSync(models.TransientModel):
    _name = 'zkteco.historical.sync'
    _description = 'ZKTeco Historical Sync Wizard'

    config_id = fields.Many2one('zkteco.adms.config', string='Configuration', required=True)
    range_type = fields.Selection([
        ('today', 'Today'),
        ('yesterday', 'Yesterday'),
        ('last_7_days', 'Last 7 Days'),
        ('custom', 'Custom Date Range')
    ], string='Range Type', default='today', required=True)

    start_date = fields.Date(string='Start Date', required=True, default=lambda self: fields.Date.today())
    end_date = fields.Date(string='End Date', required=True, default=lambda self: fields.Date.today())

    @api.onchange('range_type')
    def onchange_range_type(self):
        today = date.today()
        if self.range_type == 'today':
            self.start_date = today
            self.end_date = today
        elif self.range_type == 'yesterday':
            self.start_date = today - timedelta(days=1)
            self.end_date = today - timedelta(days=1)
        elif self.range_type == 'last_7_days':
            self.start_date = today - timedelta(days=7)
            self.end_date = today
        # For 'custom', we leave the dates for user input

    def action_sync(self):
        """Execute historical sync with progress indication."""
        self.ensure_one()
        if self.start_date > self.end_date:
            raise UserError(_("The start date cannot be after the end date."))

        # Show initial progress message
        context = self.env.context.copy()
        context.update({
            'sync_start_date': str(self.start_date),
            'sync_end_date': str(self.end_date),
            'sync_config_name': self.config_id.name
        })
        
        # Execute the sync (which now includes automatic collection)
        return self.config_id.action_request_historical_sync(self.start_date, self.end_date)
