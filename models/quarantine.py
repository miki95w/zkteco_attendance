import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ZKTecoQuarantine(models.Model):
    """Quarantined attendance records from Flask ADMS."""
    
    _name = 'zkteco.quarantine'
    _description = 'Quarantined Attendance Records'
    _order = 'created_at desc'
    
    # Record data
    user_id = fields.Char(string='User ID', index=True)
    timestamp = fields.Datetime(string='Timestamp')
    event_type = fields.Integer(string='Event Type')
    device_id = fields.Char(string='Device ID')
    raw_data = fields.Binary(string='Raw Data')
    
    # Error information
    error_reason = fields.Text(string='Error Reason', required=True)
    created_at = fields.Datetime(string='Created At', default=fields.Datetime.now, readonly=True)
    
    # Review status
    reviewed = fields.Boolean(string='Reviewed', default=False, index=True)
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    reviewed_at = fields.Datetime(string='Reviewed At', readonly=True)
    resolution_notes = fields.Text(string='Resolution Notes')
    
    # Related records
    employee_id = fields.Many2one('hr.employee', string='Linked Employee')
    zkteco_device_id = fields.Many2one('zkteco.device', string='ZKTeco Device')
    
    # Computed
    can_retry = fields.Boolean(string='Can Retry', compute='_compute_can_retry', store=True)
    
    @api.depends('reviewed', 'error_reason', 'employee_id')
    def _compute_can_retry(self):
        """Determine if record can be retried."""
        for record in self:
            # Can retry if:
            # 1. Not reviewed yet, OR
            # 2. Employee is now linked and error was about missing employee
            record.can_retry = (
                not record.reviewed or
                (record.employee_id and 'user_id' in (record.error_reason or '').lower())
            )
    
    def action_mark_reviewed(self):
        """Mark records as reviewed."""
        for record in self:
            record.write({
                'reviewed': True,
                'reviewed_by': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Records Reviewed'),
                'message': _('Marked %s records as reviewed') % len(self),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_try_process(self):
        """Attempt to process quarantined records."""
        processed = 0
        failed = 0
        
        for record in self:
            if not record.can_retry:
                failed += 1
                continue
            
            try:
                # Find or create mapping
                if not record.employee_id:
                    # Try to find employee by device user ID
                    mapping = self.env['zkteco.user.mapping'].sudo().search([
                        ('device_user_id', '=', record.user_id),
                    ], limit=1)
                    
                    if mapping and mapping.employee_id:
                        record.employee_id = mapping.employee_id
                    else:
                        failed += 1
                        continue
                
                # Find device
                if not record.zkteco_device_id and record.device_id:
                    device = self.env['zkteco.device'].sudo().search([
                        ('serial_number', '=', record.device_id)
                    ], limit=1)
                    if device:
                        record.zkteco_device_id = device
                
                # Create attendance log
                if record.employee_id and record.timestamp:
                    att_log = self.env['zkteco.attendance'].sudo().create({
                        'device_id': record.zkteco_device_id.id if record.zkteco_device_id else False,
                        'device_user_id': record.user_id,
                        'timestamp': record.timestamp,
                        'event_type': record.event_type or 0,
                        'employee_id': record.employee_id.id,
                        'state': 'draft',
                    })
                    
                    # Process the log
                    att_log.action_process_logs()
                    
                    # Mark as reviewed
                    record.write({
                        'reviewed': True,
                        'reviewed_by': self.env.user.id,
                        'reviewed_at': fields.Datetime.now(),
                        'resolution_notes': _('Successfully processed and created attendance record'),
                    })
                    processed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                _logger.error(f"Failed to process quarantined record {record.id}: {e}")
                record.write({
                    'resolution_notes': _('Retry failed: %s') % str(e)
                })
                failed += 1
        
        message = _('Processed: %s\nFailed: %s') % (processed, failed)
        notification_type = 'success' if processed > 0 else 'warning'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Retry Complete'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            }
        }
    
    def action_link_employee(self):
        """Wizard to link employee to quarantined record."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Employee'),
            'res_model': 'zkteco.quarantine.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quarantine_id': self.id,
                'default_user_id': self.user_id,
            }
        }
    
    @api.model
    def action_fetch_from_adms(self):
        """Fetch quarantined records from Flask ADMS."""
        try:
            # Get ADMS config
            config = self.env['zkteco.adms.config'].get_active_config()
            
            # This would require an API endpoint on Flask ADMS to export quarantine data
            # For now, we'll just show a message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Quarantine'),
                    'message': _('Quarantine records are synced automatically from Flask ADMS'),
                    'type': 'info',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_('Failed to fetch quarantine records: %s') % str(e))


class QuarantineLinkWizard(models.TransientModel):
    """Wizard to link employee to quarantined record."""
    
    _name = 'zkteco.quarantine.link.wizard'
    _description = 'Link Employee to Quarantine Record'
    
    quarantine_id = fields.Many2one('zkteco.quarantine', string='Quarantine Record', required=True)
    user_id = fields.Char(string='Device User ID', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    create_mapping = fields.Boolean(string='Create User Mapping', default=True)
    device_id = fields.Many2one('zkteco.device', string='Device')
    
    def action_link(self):
        """Link employee and optionally create mapping."""
        self.ensure_one()
        
        # Update quarantine record
        self.quarantine_id.write({
            'employee_id': self.employee_id.id,
        })
        
        # Create mapping if requested
        if self.create_mapping and self.user_id and self.device_id:
            existing = self.env['zkteco.user.mapping'].sudo().search([
                ('device_user_id', '=', self.user_id),
                ('device_id', '=', self.device_id.id)
            ], limit=1)
            
            if not existing:
                self.env['zkteco.user.mapping'].sudo().create({
                    'device_user_id': self.user_id,
                    'device_user_name': self.employee_id.name,
                    'employee_id': self.employee_id.id,
                    'device_id': self.device_id.id,
                })
        
        # Try to process the record
        return self.quarantine_id.action_try_process()
