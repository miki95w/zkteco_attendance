import requests
from odoo import http, fields
from odoo.http import request, Response
import logging
import json

_logger = logging.getLogger(__name__)

_cmd_id_counter = 1000


def _next_cmd_id():
    global _cmd_id_counter
    _cmd_id_counter += 1
    return _cmd_id_counter


class ZKTecoController(http.Controller):

    def _get_or_create_device(self, sn):
        """Find or auto-create a device record by serial number."""
        device = request.env['zkteco.device'].sudo().search(
            [('serial_number', '=', sn)], limit=1
        )
        if not device:
            device = request.env['zkteco.device'].sudo().create({
                'name': f'ZKTeco {sn}',
                'serial_number': sn,
                'last_sync': fields.Datetime.now(),
            })
            _logger.warning(f"[ZKTeco] 🆕 Auto-created device for SN: {sn}")
        else:
            device.write({'last_sync': fields.Datetime.now()})
        return device

    def _parse_timestamp(self, ts_str):
        """Robustly parse timestamp strings from ZKTECO devices."""
        if not ts_str:
            return False

        # Try common ZKTECO formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
        ]

        for fmt in formats:
            try:
                from datetime import datetime
                return fields.Datetime.to_datetime(datetime.strptime(ts_str.strip(), fmt))
            except (ValueError, TypeError):
                continue

        # Fallback to Odoo's from_string
        try:
            return fields.Datetime.from_string(ts_str)
        except Exception:
            return False

    def _parse_kv_line(self, line):
        """Parse a tab-separated OR &-separated key=value line into a lowercase dict."""
        parts = {}
        # Split by tab first, then by &
        tokens = []
        for chunk in line.strip().split('\t'):
            for item in chunk.split('&'):
                tokens.append(item.strip())
        for item in tokens:
            if '=' in item:
                k, v = item.split('=', 1)
                parts[k.strip().lower()] = v.strip()
        return parts

    # ------------------------------------------------------------------
    # LEGACY RAW DEVICE ENDPOINTS (RESTRICTED UNDER RELAY ARCHITECTURE)
    # ------------------------------------------------------------------
    @http.route('/iclock/registry', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def adms_registry(self, **kwargs):
        return Response("Forbidden: Direct public access to raw ADMS registry is disabled on the VPS.", status=403, content_type='text/plain')

    @http.route('/iclock/push', type='http', auth='none', methods=['POST'], csrf=False)
    def adms_push(self, **kwargs):
        return Response("Forbidden: Direct public access to raw ADMS push is disabled on the VPS.", status=403, content_type='text/plain')

    @http.route('/iclock/ping', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def adms_ping(self, **kwargs):
        return Response("Forbidden: Direct public access to raw ADMS ping is disabled on the VPS.", status=403, content_type='text/plain')

    @http.route('/iclock/getrequest', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def poll_commands(self, **kwargs):
        return Response("Forbidden: Direct public access to raw ADMS command polling is disabled on the VPS.", status=403, content_type='text/plain')

    @http.route('/iclock/devicecmd', type='http', auth='none', methods=['POST'], csrf=False)
    def receive_command_result(self, **kwargs):
        return Response("Forbidden: Direct public access to raw ADMS command results is disabled on the VPS.", status=403, content_type='text/plain')

    @http.route(['/iclock/cdata', '/iclock/querydata'], type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def receive_data(self, **kwargs):
        return Response("Forbidden: Direct public access to raw ADMS data ingestion is disabled on the VPS.", status=403, content_type='text/plain')

    # ------------------------------------------------------------------
    # FLASK MIDDLEWARE COMMAND POLLING & ACK
    # ------------------------------------------------------------------
    @http.route('/zkteco/api/commands', type='http', auth='public', methods=['GET'], csrf=False)
    def flask_poll_commands(self, **kwargs):
        """
        Flask ADMS calls this endpoint to poll pending commands from Odoo.
        Returns a list of commands for the middleware to forward to the devices.
        Authentication: api_key query parameter or Authorization header.
        """
        try:
            api_key = request.params.get('api_key') or request.httprequest.headers.get('Authorization')
            if api_key and api_key.startswith('Bearer '):
                api_key = api_key[7:]
            
            if not api_key:
                return Response('{"status":"error","message":"Unauthorized: Missing API Key"}', content_type='application/json', status=401)
                
            config = request.env['zkteco.adms.config'].sudo().search([
                ('api_key', '=', api_key),
                ('active', '=', True)
            ], limit=1)
            
            if not config:
                return Response('{"status":"error","message":"Unauthorized"}', content_type='application/json', status=401)
            
            # Find all pending commands in the queue
            pending_cmds = request.env['zkteco.command.queue'].sudo().search([
                ('state', '=', 'pending')
            ], order='create_date asc')
            
            # Group by device
            cmds_data = []
            for cmd in pending_cmds:
                cmds_data.append({
                    'id': cmd.id,
                    'device_sn': cmd.device_id.serial_number,
                    'command_string': cmd.command_string
                })
                
            # Update passive last_sync for the config since Flask is calling us
            config.write({'last_sync': fields.Datetime.now()})
            
            return Response(json.dumps({
                'status': 'ok',
                'commands': cmds_data
            }), content_type='application/json')
            
        except Exception as e:
            _logger.error(f"[ZKTeco] Flask command poll error: {e}")
            return Response(json.dumps({
                'status': 'error',
                'message': str(e)
            }), content_type='application/json', status=500)

    @http.route('/zkteco/api/commands/ack', type='http', auth='public', methods=['POST'], csrf=False)
    def flask_ack_commands(self, **kwargs):
        """
        Flask ADMS calls this to acknowledge that commands have been received/processed.
        Marks them as 'sent' in the Odoo database.
        """
        try:
            import json as _json
            raw = request.httprequest.get_data()
            body = _json.loads(raw.decode('utf-8', errors='ignore'))
            api_key = body.get('api_key', '')
            
            if not api_key:
                return Response('{"status":"error","message":"Unauthorized: Missing API Key"}', content_type='application/json', status=401)

            config = request.env['zkteco.adms.config'].sudo().search([
                ('api_key', '=', api_key),
                ('active', '=', True)
            ], limit=1)
            
            if not config:
                return Response('{"status":"error","message":"Unauthorized"}', content_type='application/json', status=401)
                
            command_ids = body.get('command_ids', [])
            if command_ids:
                commands = request.env['zkteco.command.queue'].sudo().browse(command_ids)
                commands.write({'state': 'sent'})
                
            return Response('{"status":"ok"}', content_type='application/json')
            
        except Exception as e:
            _logger.error(f"[ZKTeco] Flask command ack error: {e}")
            return Response(json.dumps({
                'status': 'error',
                'message': str(e)
            }), content_type='application/json', status=500)

    # ------------------------------------------------------------------
    # FLASK ADMS PUSH ENDPOINT (Flask calls this to push attendance to Odoo)
    # ------------------------------------------------------------------
    @http.route('/zkteco/push/attendance', type='http', auth='public', methods=['POST'], csrf=False)
    def flask_push_attendance(self, **kwargs):
        """
        Flask ADMS calls this endpoint to push attendance records directly into Odoo.
        This makes the integration real-time without relying on polling.
        Payload format:
        {
            "api_key": "...",
            "records": [
                {"device_id": "SN123", "user_id": "5", "timestamp": "2026-07-16 10:54:12", "event_type": 0}
            ]
        }
        """
        try:
            import json as _json
            raw = request.httprequest.get_data()
            body = _json.loads(raw.decode('utf-8', errors='ignore'))
            api_key = body.get('api_key', '')

            if not api_key:
                return Response('{"status":"error","message":"Unauthorized: Missing API Key"}', content_type='application/json', status=401)

            # Validate API key against any active ADMS config
            config = request.env['zkteco.adms.config'].sudo().search([
                ('api_key', '=', api_key),
                ('active', '=', True)
            ], limit=1)

            if not config:
                _logger.warning(f"[ZKTeco] Push rejected — invalid API key")
                return Response('{"status":"error","message":"Unauthorized"}', content_type='application/json', status=401)

            records = body.get('records', [])
            if not records:
                return Response('{"status":"ok","processed":0}', content_type='application/json')

            processed = config._process_flask_attendance_data(records)
            _logger.info(f"[ZKTeco] 📤 Flask push: processed {processed} records")
            return Response(f'{{"status":"ok","processed":{processed}}}', content_type='application/json')

        except Exception as e:
            _logger.error(f"[ZKTeco] Flask push error: {e}")
            return Response(f'{{"status":"error","message":"{str(e)}"}}', content_type='application/json', status=500)

    @http.route('/zkteco/push/users', type='http', auth='public', methods=['POST'], csrf=False)
    def flask_push_users(self, **kwargs):
        """
        Flask ADMS calls this endpoint to push user data directly into Odoo.
        Payload format:
        {
            "api_key": "...",
            "device_sn": "SN123",
            "users": [{"pin": "5", "name": "John"}]
        }
        """
        try:
            import json as _json
            raw = request.httprequest.get_data()
            body = _json.loads(raw.decode('utf-8', errors='ignore'))
            api_key = body.get('api_key', '')

            if not api_key:
                return Response('{"status":"error","message":"Unauthorized: Missing API Key"}', content_type='application/json', status=401)

            config = request.env['zkteco.adms.config'].sudo().search([
                ('api_key', '=', api_key),
                ('active', '=', True)
            ], limit=1)

            if not config:
                return Response('{"status":"error","message":"Unauthorized"}', content_type='application/json', status=401)

            device_sn = body.get('device_sn', '')
            users = body.get('users', [])

            device = request.env['zkteco.device'].sudo().search([
                ('serial_number', '=', device_sn)
            ], limit=1)

            if not device:
                # Auto-create the device
                device = request.env['zkteco.device'].sudo().create({
                    'name': f'ZKTeco {device_sn}',
                    'serial_number': device_sn,
                    'last_sync': fields.Datetime.now(),
                })

            count = 0
            mapping_obj = request.env['zkteco.user.mapping'].sudo()
            for user in users:
                pin = str(user.get('pin', '')).strip()
                name = user.get('name', '')
                if not pin:
                    continue
                mapping = mapping_obj.search([
                    ('device_user_id', '=', pin),
                    ('device_id', '=', device.id)
                ], limit=1)
                if not mapping:
                    mapping_obj.create({
                        'device_user_id': pin,
                        'device_user_name': name,
                        'device_id': device.id,
                    })
                    count += 1
                else:
                    mapping.write({'device_user_name': name})

            return Response(f'{{"status":"ok","processed":{count}}}', content_type='application/json')

        except Exception as e:
            _logger.error(f"[ZKTeco] Flask user push error: {e}")
            return Response(f'{{"status":"error","message":"{str(e)}"}}', content_type='application/json', status=500)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _process_users(self, device, data):
        """
        Parse user table records. Handles two formats:
        1. DATA QUERY tablename=user response:
           'user uid=2\tcardno=\tpin=2\tpassword=\tgroup=1\t...name=Ff\t...'
        2. Legacy format: bare key=value tab-separated lines
        """
        mapping_obj = request.env['zkteco.user.mapping'].sudo()
        new_mappings = []
        updates = {}
        
        # 1. Parse all lines first
        parsed_users = {}
        for line in data.split("\n"):
            line = line.strip()
            if not line or any(line.startswith(x) for x in ["ID=", "Return=", "OK"]):
                continue

            if line.lower().startswith('user '):
                line = line[5:]

            kv = self._parse_kv_line(line)
            pin = kv.get("pin") or kv.get("uid") or kv.get("userid")
            name = kv.get("name") or kv.get("username") or ""

            if pin:
                parsed_users[pin] = name

        if not parsed_users:
            return

        # 2. Bulk search existing
        existing = mapping_obj.search([
            ('device_id', '=', device.id),
            ('device_user_id', 'in', list(parsed_users.keys()))
        ])
        
        existing_map = {m.device_user_id: m for m in existing}

        # 3. Categorize into creates and updates
        for pin, name in parsed_users.items():
            if pin in existing_map:
                if existing_map[pin].device_user_name != name:
                    existing_map[pin].write({'device_user_name': name})
            else:
                new_mappings.append({
                    'device_user_id': pin,
                    'device_user_name': name,
                    'device_id': device.id,
                })

        # 4. Bulk create
        if new_mappings:
            mapping_obj.create(new_mappings)

        _logger.warning(f"[ZKTeco] ✅ User sync done — {len(parsed_users)} users processed. {len(new_mappings)} created.")

    def _process_attendance(self, device, data, stamp=None):
        """
        Parse F22 attendance lines.
        F22 rtlog format (key=value, tab-separated):
          time=2026-07-08 16:00:19\tpin=5\tcardno=0\teventaddr=1\tevent=101\tinoutstatus=0\t...
        Legacy format fallback (positional):
          PIN\tDateTime\tState\tVerify\tWorkCode
        """
        att_obj = request.env['zkteco.attendance'].sudo()
        new_records = []
        parsed_punches = []

        # 1. Parse all lines
        for line in data.split("\n"):
            line = line.strip()
            if not line or line.startswith("Stamp="):
                continue

            kv = self._parse_kv_line(line)
            timestamp_str = kv.get("time")
            pin = kv.get("pin")
            state_raw = kv.get("inoutstatus") or kv.get("event") or "0"

            if not timestamp_str or not pin:
                parts = line.split("\t")
                if len(parts) >= 2:
                    pin = parts[0].strip()
                    timestamp_str = parts[1].strip()
                    state_raw = parts[2].strip() if len(parts) >= 3 else "0"
                else:
                    continue

            try:
                state = int(state_raw)
            except (ValueError, TypeError):
                state = 0

            try:
                timestamp = self._parse_timestamp(timestamp_str)
                if timestamp:
                    parsed_punches.append({
                        'pin': pin,
                        'timestamp': timestamp,
                        'state': state,
                        'line': line
                    })
            except Exception as e:
                _logger.error(f"[ZKTeco] ❌ Error parsing line: '{line}' | {e}")

        if not parsed_punches:
            return

        # 2. Bulk check for existing records to prevent duplicates
        pins = list(set(p['pin'] for p in parsed_punches))
        timestamps = list(set(p['timestamp'] for p in parsed_punches))

        existing = att_obj.search([
            ('device_id', '=', device.id),
            ('device_user_id', 'in', pins),
            ('timestamp', 'in', timestamps)
        ])
        
        # Create a fast lookup set: (device_user_id, timestamp)
        existing_set = {(r.device_user_id, r.timestamp) for r in existing}
        
        # 3. Filter duplicates and prepare creates
        for p in parsed_punches:
            if (p['pin'], p['timestamp']) not in existing_set:
                new_records.append({
                    'device_id': device.id,
                    'device_user_id': p['pin'],
                    'timestamp': p['timestamp'],
                    'event_type': p['state'],
                    'raw_data': p['line'],
                    'state': 'draft',
                })
                # Add to set so we don't insert duplicates within the same payload
                existing_set.add((p['pin'], p['timestamp']))

        # 4. Bulk create
        if new_records:
            att_obj.create(new_records)
            _logger.warning(f"[ZKTeco] ✅ Attendance done — {len(new_records)} new records stored in Draft state.")
        else:
            _logger.info(f"[ZKTeco] ✅ Attendance done — 0 new records (all duplicates).")

        # NOTE: We DO NOT auto-process drafts synchronously here.
        # This prevents the worker timeout (120s limit) shown in the logs.
        # Drafts will be picked up asynchronously by the ir.cron job.

        if stamp is not None:
            device.write({'last_stamp': stamp})
            _logger.info(f"[ZKTeco] Updated last_stamp to {stamp} for device {device.name}")
