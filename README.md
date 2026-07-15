# ZKTeco Attendance Integration for Odoo 17

Complete integration module for ZKTeco F22 biometric attendance devices with Odoo 17, working seamlessly with the Flask ADMS middleware.

## Overview

This module provides a complete attendance management solution for Odoo 17, integrating with ZKTeco F22 biometric devices through a high-performance Flask ADMS middleware. It handles real-time attendance synchronization, user management, device monitoring, and comprehensive reporting.

## Architecture

```
ZKTeco F22 Devices
        ↓
Flask ADMS Middleware (TCP Socket Server)
        ↓
   HTTP REST API
        ↓
Odoo 17 Module (This Module)
        ↓
   HR Attendance
```

## Features

### 1. Device Management
- Auto-discovery and registration of ZKTeco devices
- Real-time device status monitoring
- Online/offline status tracking
- Device configuration and command queue
- Support for multiple devices

### 2. User Synchronization
- Bidirectional user mapping between Odoo employees and device users
- Automatic user enrollment on devices
- Bulk user synchronization
- Device user management interface

### 3. Attendance Processing
- Real-time attendance log ingestion
- Automatic check-in/check-out detection
- Event type processing (check-in, check-out, break)
- Duplicate detection and handling
- Shift-aware attendance tracking

### 4. Flask ADMS Integration
- **NEW**: Direct integration with Flask ADMS middleware
- Connection status monitoring
- Device statistics (connected devices, processed records)
- User push synchronization
- Health check integration

### 5. Quarantine Management
- **NEW**: Quarantine interface for invalid attendance records
- Manual review and correction workflow
- Employee linking wizard
- Retry processing for corrected records
- Error reason tracking

### 6. Reporting
- Attendance reports by employee, device, or date range
- Absence reports
- Synchronization logs
- Device usage statistics

### 7. Shift Management
- Shift definition and scheduling
- Employee shift assignments
- Shift-aware attendance validation

## Installation

### Prerequisites

1. **Odoo 17** installed and running
2. **Flask ADMS middleware** installed and configured (see `/zkteco-adms/README.md`)
3. **Python requests library**: `pip install requests`

### Steps

1. Copy this module to your Odoo addons directory:
   ```bash
   cp -r zkteco_attendance /path/to/odoo/custom-addons/
   ```

2. Update the addons list in Odoo:
   - Go to Apps menu
   - Click "Update Apps List"

3. Install the module:
   - Search for "ZKTeco Attendance Machine"
   - Click Install

4. Configure Flask ADMS connection:
   - Go to Attendance → Flask ADMS Config
   - Create a new configuration
   - Enter Flask ADMS URL (e.g., `http://localhost:8000`)
   - Enter API Key (from Flask ADMS `config.yml`)
   - Click "Test Connection"

## Configuration

### 1. Flask ADMS Configuration

Navigate to **Attendance → Flask ADMS Config**:

- **Configuration Name**: Descriptive name for the configuration
- **Active**: Enable/disable the configuration
- **ADMS URL**: Base URL where Flask ADMS is running
- **API Key**: Authentication key from Flask ADMS configuration

**Actions**:
- **Test Connection**: Verify connectivity to Flask ADMS
- **Refresh Device Status**: Update device connection states
- **Sync Users to Devices**: Push all Odoo employees to connected devices

### 2. Device Management

Navigate to **Attendance → Devices**:

Devices are automatically discovered when they connect to Flask ADMS. You can:
- View device status (online/offline)
- See last sync time
- View enrolled users per device
- Fetch user list from device
- Fetch attendance logs from device

### 3. User Mapping

Navigate to **Attendance → Device Users**:

Map ZKTeco device user IDs to Odoo employees:
- Device User ID: The PIN/ID used on the device
- Device User Name: Name stored on the device
- Employee: Linked Odoo employee
- Device: Associated device

**Bulk Operations**:
- **Fetch All Device Users**: Retrieve user lists from all devices
- **Auto-link**: Automatically map by employee name matching

### 4. Attendance Logs

Navigate to **Attendance → Attendance Logs**:

View raw attendance data from devices:
- Device User ID
- Timestamp
- Event Type
- Processing State (draft/processed/error)
- Linked Employee

**Actions**:
- **Process Logs**: Convert draft logs to HR attendance records
- **View HR Attendance**: See processed attendance for an employee

### 5. Quarantine Management

Navigate to **Attendance → Quarantined Records**:

Review and correct invalid attendance records:
- User ID with no mapping
- Future timestamps
- Missing device information
- Other validation errors

**Workflow**:
1. View quarantined records with error reasons
2. Link missing employees using "Link Employee" button
3. Retry processing with "Retry Processing" button
4. Mark as reviewed when resolved

## Usage

### Adding a New Employee to Devices

1. Create employee in Odoo (HR → Employees)
2. Set "ZKTeco Device User ID" field (optional)
3. Go to Flask ADMS Config
4. Click "Sync Users to Devices"
5. Employee will be enrolled on all connected devices

### Processing Attendance

Attendance is processed automatically via cron job, but can also be triggered manually:

1. Go to Attendance → Attendance Logs
2. Filter by "Draft" status
3. Select records to process
4. Click Action → Process Logs

### Handling Quarantined Records

1. Go to Attendance → Quarantined Records
2. Review error reasons
3. For missing employee mappings:
   - Click "Link Employee"
   - Select the correct employee
   - Optionally create user mapping
   - Click "Link and Retry"
4. For other errors, correct data and click "Retry Processing"
5. Mark as reviewed when resolved

### Monitoring Device Status

1. Go to Flask ADMS Config
2. View statistics:
   - Devices Connected: Number of online devices
   - Records Processed: Total attendance records synced
   - Records Quarantined: Invalid records needing review
3. Click "Refresh Device Status" to update

## API Endpoints

The module exposes HTTP endpoints for Flask ADMS integration:

### Handshake and Registration

- `GET/POST /iclock/registry`: Device registration
- `POST /iclock/push`: Device push notification
- `GET/POST /iclock/ping`: Keepalive

### Command Dispatch

- `GET/POST /iclock/getrequest`: Poll for pending commands
- `POST /iclock/devicecmd`: Receive command acknowledgment

### Data Ingestion

- `POST /iclock/cdata`: Receive attendance logs and user data
- `POST /iclock/querydata`: Receive query responses

## Data Flow

### Attendance Capture Flow

1. Employee scans finger/face on ZKTeco device
2. Device sends rtlog event to Flask ADMS via TCP socket
3. Flask ADMS parses binary protocol
4. Flask ADMS validates and transforms data
5. Flask ADMS batch-inserts to Odoo database (`zkteco.attendance`)
6. Odoo cron job processes draft records
7. Creates/updates `hr.attendance` records

### User Synchronization Flow

1. Admin creates employee in Odoo
2. Admin triggers "Sync Users to Devices" in Flask ADMS Config
3. Flask ADMS calls device protocol to enroll users
4. Device acknowledges enrollment
5. Flask ADMS confirms success
6. User mapping created in Odoo

## Troubleshooting

### Devices Not Appearing

1. Check Flask ADMS is running: `curl http://localhost:8000/health`
2. Verify device can reach Flask ADMS IP address
3. Check Flask ADMS logs: `tail -f /var/log/zkteco-adms/app.log`
4. Ensure firewall allows TCP port 4370

### Attendance Not Syncing

1. Check device status in "Devices" menu
2. Verify user mapping exists in "Device Users"
3. Check quarantine for validation errors
4. Review Flask ADMS logs for sync errors
5. Manually process logs: Attendance → Attendance Logs → Process Logs

### Connection Errors

1. Test connection in Flask ADMS Config
2. Verify ADMS URL is correct
3. Check API key matches Flask ADMS configuration
4. Ensure Flask ADMS is running and accessible

### Quarantined Records

Common reasons and solutions:

- **No mapping found**: Create user mapping in "Device Users"
- **Future timestamp**: Check device clock synchronization
- **Invalid user_id**: Verify user is enrolled on device
- **Database error**: Check Odoo database connection

## Technical Details

### Models

- `zkteco.device`: Device registry
- `zkteco.user.mapping`: User ID mapping
- `zkteco.attendance`: Raw attendance logs
- `zkteco.command.queue`: Device command queue
- `zkteco.shift`: Shift definitions
- `zkteco.employee.shift`: Employee shift assignments
- `zkteco.adms.config`: Flask ADMS configuration **(NEW)**
- `zkteco.quarantine`: Quarantined records **(NEW)**
- `hr.employee`: Extended with device user ID
- `hr.attendance`: Extended with shift tracking

### Controllers

- `ZKTecoController`: HTTP endpoints for device communication

### Cron Jobs

- **Process Attendance Logs**: Runs every 5 minutes, processes draft logs
- **Cleanup Old Logs**: Runs daily, archives old attendance data

## Security

- All device communication authenticated via serial number
- API endpoints use token-based authentication (when integrated with Flask ADMS)
- User mapping prevents unauthorized attendance entries
- Quarantine system isolates invalid data

## Performance

- Supports up to 50 concurrent devices
- Batch processing for high-volume attendance data
- Efficient database indexing for fast queries
- Asynchronous processing via cron jobs

## Support

For issues and questions:
- Module issues: Contact your Odoo administrator
- Flask ADMS issues: See `/zkteco-adms/README.md`
- ZKTeco device issues: Consult ZKTeco documentation

## License

LGPL-3

## Credits

- **Author**: Top Tech
- **Maintainer**: Top Tech
- **Contributors**: [Your Name]

## Changelog

### Version 17.0.1.0.0
- Initial release for Odoo 17
- Flask ADMS integration
- Quarantine management
- Real-time attendance synchronization
- Device monitoring
- Shift management
- Comprehensive reporting
