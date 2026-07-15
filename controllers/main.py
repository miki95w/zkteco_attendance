from odoo import http, fields
from odoo.http import request, Response
import logging

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

    def _parse_kv_line(self, line):
        """Parse a tab-separated key=value line into a lowercase dict."""
        parts = {}
        for item in line.strip().split("\t"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                parts[k.strip().lower()] = v.strip()
        return parts

    # ------------------------------------------------------------------
    # HANDSHAKE
    # ------------------------------------------------------------------
    @http.route('/iclock/registry', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def adms_registry(self, **kwargs):
        sn = request.params.get("SN", "")
        _logger.info(f"[ZKTeco] 🔄 REGISTRY from SN: {sn}")
        if sn:
            self._get_or_create_device(sn)
        response_text = (
            "RegistryCode=1\n"
            "ServerVersion=3.1.2\n"
            "ServerName=OdooADMS\n"
            "PushVersion=3.1.2\n"
            "ErrorDelay=60\n"
            "Delay=10\n"
            "TransTimes=00:00;23:59\n"
            "TransInterval=1\n"
            "TransFlag=1111111111\n"
            "TimeZone=1\n"
            "OK\n"
        )
        return Response(response_text, content_type='text/plain')

    @http.route('/iclock/push', type='http', auth='none', methods=['POST'], csrf=False)
    def adms_push(self, **kwargs):
        return Response(
            "ServerVersion=3.1.2\nServerName=OdooADMS\nPushVersion=3.1.2\nRegistryCode=1\nOK\n",
            content_type='text/plain'
        )

    @http.route('/iclock/ping', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def adms_ping(self, **kwargs):
        return Response("OK\n", content_type='text/plain')

    # ------------------------------------------------------------------
    # HEARTBEAT & COMMAND DISPATCH
    # ------------------------------------------------------------------
    @http.route('/iclock/getrequest', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def poll_commands(self, **kwargs):
        sn = request.params.get("SN", "")
        if not sn:
            return Response("OK\n", content_type='text/plain')

        device = self._get_or_create_device(sn)

        pending_cmd = request.env['zkteco.command.queue'].sudo().search([
            ('device_id', '=', device.id),
            ('state', '=', 'pending')
        ], order='create_date asc', limit=1)

        if pending_cmd:
            cmd_id = _next_cmd_id()
            cmd_payload = f"C:{cmd_id}:{pending_cmd.command_string}\n"
            _logger.warning(f"[ZKTeco] 🚀 DISPATCHING to SN {sn}: {cmd_payload.strip()}")
            pending_cmd.write({'state': 'sent'})
            return Response(cmd_payload, content_type='text/plain')

        return Response("OK\n", content_type='text/plain')

    # ------------------------------------------------------------------
    # COMMAND ACKNOWLEDGEMENT (device confirms command was received)
    # ------------------------------------------------------------------
    @http.route('/iclock/devicecmd', type='http', auth='none', methods=['POST'], csrf=False)
    def receive_command_result(self, **kwargs):
        sn = request.params.get("SN", "")
        raw_body = request.httprequest.get_data()
        decoded_data = raw_body.decode("utf-8", errors="ignore")
        _logger.info(
            f"[ZKTeco] 📬 DEVICECMD ACK from SN: {sn} | {decoded_data[:300].strip()}"
        )
        return Response("OK\n", content_type='text/plain')

    # ------------------------------------------------------------------
    # DATA INGESTION (all push data comes here)
    # ------------------------------------------------------------------
    @http.route(['/iclock/cdata', '/iclock/querydata'], type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def receive_data(self, **kwargs):
        if request.httprequest.method == 'GET':
            return Response("OK\n", content_type='text/plain')

        sn = request.params.get("SN", "")
        # The /iclock/querydata endpoint uses 'tablename=', while /iclock/cdata uses 'table='
        table = (request.params.get("table") or request.params.get("tablename") or "").lower()
        raw_body = request.httprequest.get_data()
        decoded_data = raw_body.decode("utf-8", errors="ignore")

        _logger.warning(
            f"[ZKTeco] 📥 CDATA — SN: {sn} | table: '{table}' | {len(decoded_data)} bytes\n"
            f"--- PAYLOAD ---\n{decoded_data[:600].strip()}\n---------------"
        )

        # Ignore door/sensor state events — not attendance
        if table == 'rtstate':
            return Response("OK\n", content_type='text/plain')

        device = request.env['zkteco.device'].sudo().search(
            [('serial_number', '=', sn)], limit=1
        )
        if not device:
            _logger.warning(f"[ZKTeco] ⚠️ No device record for SN: {sn}")
            return Response("OK\n", content_type='text/plain')

        device.write({'last_sync': fields.Datetime.now()})

        # ── USER TABLE ──────────────────────────────────────────────────
        if 'user' in table:
            self._process_users(device, decoded_data)

        # ── ATTENDANCE LOGS (rtlog / attlog / transaction) ──────────────
        elif 'log' in table or 'att' in table or 'transaction' in table:
            self._process_attendance(device, decoded_data)

        else:
            _logger.info(f"[ZKTeco] ℹ️ Unhandled table '{table}' — payload logged above.")

        return Response("OK\n", content_type='text/plain')

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _process_users(self, device, data):
        """
        Parse user table records. Handles two formats:
        1. DATA QUERY tablename=user response (from /iclock/querydata):
           'user uid=2\tcardno=\tpin=2\tpassword=\tgroup=1\t...\tname=Ff\t...'
        2. Legacy format: bare key=value tab-separated lines
        """
        mapping_obj = request.env['zkteco.user.mapping'].sudo()
        count = 0
        for line in data.split("\n"):
            line = line.strip()
            if not line or any(line.startswith(x) for x in ["ID=", "Return=", "OK"]):
                continue

            # Format 1: lines start with 'user ' followed by tab-separated key=value pairs
            # e.g. 'user uid=2\tcardno=\tpin=2\tpassword=\tname=Ff\t...'
            if line.lower().startswith('user '):
                line = line[5:]  # strip leading 'user '

            kv = self._parse_kv_line(line)
            pin = kv.get("pin")
            name = kv.get("name") or ""

            _logger.info(f"[ZKTeco] 👤 User — PIN={pin} NAME={name}")

            if pin:
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
                    _logger.info(f"[ZKTeco]   ✅ Created mapping PIN={pin}")
                else:
                    mapping.write({'device_user_name': name})
                    _logger.info(f"[ZKTeco]   ♻️  Updated mapping PIN={pin}")
                count += 1

        _logger.warning(f"[ZKTeco] ✅ User sync done — {count} users processed.")

    def _process_attendance(self, device, data):
        """
        Parse F22 attendance lines.
        F22 rtlog format (key=value, tab-separated):
          time=2026-07-08 16:00:19\tpin=5\tcardno=0\teventaddr=1\tevent=101\tinoutstatus=0\t...
        Legacy format fallback (positional):
          PIN\tDateTime\tState\tVerify\tWorkCode
        """
        att_obj = request.env['zkteco.attendance'].sudo()
        count = 0

        for line in data.split("\n"):
            line = line.strip()
            if not line or line.startswith("Stamp="):
                continue

            kv = self._parse_kv_line(line)

            # F22 key=value format
            timestamp_str = kv.get("time")
            pin = kv.get("pin")
            state_raw = kv.get("inoutstatus") or kv.get("event") or "0"

            # Legacy positional format fallback
            if not timestamp_str or not pin:
                parts = line.split("\t")
                if len(parts) >= 2:
                    pin = parts[0].strip()
                    timestamp_str = parts[1].strip()
                    state_raw = parts[2].strip() if len(parts) >= 3 else "0"
                else:
                    _logger.warning(f"[ZKTeco] ⚠️ Cannot parse line: {line}")
                    continue

            try:
                state = int(state_raw)
            except (ValueError, TypeError):
                state = 0

            try:
                timestamp = fields.Datetime.from_string(timestamp_str)
                existing = att_obj.search([
                    ('device_id', '=', device.id),
                    ('device_user_id', '=', pin),
                    ('timestamp', '=', timestamp),
                ], limit=1)

                if not existing:
                    att_obj.create({
                        'device_id': device.id,
                        'device_user_id': pin,
                        'timestamp': timestamp,
                        'event_type': state,
                        'raw_data': line,
                        'state': 'draft',
                    })
                    count += 1
                    _logger.info(f"[ZKTeco] ⏰ Punch — PIN:{pin} | {timestamp_str} | state:{state}")

            except Exception as e:
                _logger.error(f"[ZKTeco] ❌ Error on line: '{line}' | {e}")

        _logger.warning(f"[ZKTeco] ✅ Attendance done — {count} new records stored.")
