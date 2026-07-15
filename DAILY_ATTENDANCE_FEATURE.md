# Daily Attendance Records Feature

## Overview

The Daily Attendance Records feature provides comprehensive tracking of employee attendance with automatic status determination and absence marking. It gives managers a real-time view of who is present, absent, or has missed a punch.

## Key Features

### 1. **Automatic Daily Record Generation**
- System automatically generates attendance records for all active employees every day
- Records are created at 6:00 AM daily via scheduled job
- Each employee gets one record per day

### 2. **Real-Time Status Tracking**

The system automatically determines employee status based on their punch activity:

#### Status Types:

- **🟢 Present**: Employee has punched in at least once and all punches are complete (has check-out)
- **🔴 Absent**: Employee has not punched in at all during the day
- **🟡 Missed Punch**: Employee punched in but forgot to punch out (incomplete attendance)
- **🔵 On Leave**: Employee has approved leave for the day

### 3. **Automatic Absence Marking**
- **Automatic Process**: System automatically marks employees as absent if they fail to punch in at least once during the day
- **Schedule**: Runs daily at 11:00 PM (23:00) to mark the previous day's absences
- **Grace Period**: 1-day grace period before marking absent (marks yesterday's absences)
- **Notes**: Automatically adds a remark: "Automatically marked absent - No punch recorded on [DATE]"

### 4. **Comprehensive Information Display**

Each attendance record shows:
- **Employee**: Name, department, job position
- **Date**: Record date
- **Status**: Color-coded status badge
- **First Check-in**: First punch time of the day
- **Last Check-out**: Last punch time of the day
- **Total Punches**: Number of check-ins during the day
- **Worked Hours**: Total hours worked
- **Expected Hours**: Expected working hours (default: 8.0)
- **Shift**: Assigned shift if applicable
- **Punctuality**: Late arrival and early leave tracking
- **Remarks**: Notes and system messages

### 5. **Late/Early Leave Tracking**

The system tracks:
- **Late Arrival**: If first check-in is after shift start time
- **Late Minutes**: How many minutes late
- **Early Leave**: If last check-out is before shift end time
- **Early Leave Minutes**: How many minutes early

### 6. **Multiple Views**

#### Tree View (List)
- Color-coded rows based on status
- Quick overview of multiple employees
- Sortable and filterable columns
- Shows key information at a glance

#### Kanban View (Cards)
- Mobile-friendly card layout
- Color-coded cards by status
- Quick status overview
- Perfect for dashboards

#### Form View (Detail)
- Complete employee attendance details
- View all punch records for the day
- Add remarks
- Manual status correction buttons

#### Calendar View
- Monthly calendar overview
- Color-coded by status
- Quick date navigation
- Visual attendance patterns

#### Pivot View (Analysis)
- Cross-tabulation of data
- Group by month, department, status
- Aggregate worked hours
- Export to Excel

#### Graph View (Charts)
- Bar charts of attendance statistics
- Weekly/monthly trends
- Status distribution
- Visual insights

## Menu Structure

```
Attendance (Main Menu)
├── Daily Attendance (Main View)
│   └── All daily attendance records
│
├── Present Today
│   └── Employees who are present today
│
├── Absent Today
│   └── Employees who are absent today
│
└── Missed Punch Today
    └── Employees who forgot to punch out
```

## Automated Jobs (Cron)

### 1. Generate Daily Attendance Records
- **Name**: Generate Daily Attendance Records
- **Frequency**: Daily at 6:00 AM
- **Action**: Creates attendance records for all active employees
- **Model**: `zkteco.attendance.record`
- **Method**: `_cron_generate_daily_records()`

### 2. Auto-Mark Absent Employees
- **Name**: Auto-Mark Absent Employees
- **Frequency**: Daily at 11:00 PM (23:00)
- **Action**: Marks employees as absent if no punch recorded
- **Model**: `zkteco.attendance.record`
- **Method**: `_cron_auto_mark_absent()`
- **Grace Period**: Marks yesterday's absences (1-day buffer)

### 3. Process ZKTeco Attendance Logs
- **Name**: Process ZKTeco Attendance Logs
- **Frequency**: Every 1 minute
- **Action**: Processes raw attendance logs from devices
- **Model**: `zkteco.attendance`
- **Method**: `action_process_logs()`

## Search Filters

### Quick Filters:
- **Present**: Show only present employees
- **Absent**: Show only absent employees
- **Missed Punch**: Show employees who forgot to punch out
- **On Leave**: Show employees on approved leave

### Date Filters:
- **Today**: Current day's records
- **Yesterday**: Previous day's records
- **This Week**: Current week
- **This Month**: Current month

### Special Filters:
- **Late Arrivals**: Employees who arrived late
- **Early Leaves**: Employees who left early

### Group By:
- Date
- Employee
- Department
- Status
- Shift

## Manual Actions

### On Individual Records:

1. **View Punch Records**: Opens all check-in/check-out records for that day
2. **Mark Present**: Manually create a default attendance record (9 AM - 5 PM)
3. **Mark Absent**: Manually mark employee as absent with note

### Bulk Actions:
- Process multiple records simultaneously
- Export to Excel/CSV
- Generate reports

## Data Flow

```
Employee Punches In/Out
        ↓
ZKTeco Device captures biometric
        ↓
Device sends to Flask ADMS
        ↓
Flask ADMS validates and syncs to Odoo
        ↓
Creates/updates hr.attendance record
        ↓
System links to zkteco.attendance.record
        ↓
Status automatically computed
        ↓
Real-time update in Daily Attendance view
```

## Integration with Existing Features

### 1. HR Attendance (Standard Odoo)
- Daily records automatically link to `hr.attendance`
- Each punch creates/updates standard attendance records
- Worked hours calculated automatically
- Compatible with all Odoo HR features

### 2. Shift Management
- Assigns shift to daily records
- Calculates late/early based on shift times
- Supports multiple shift schedules

### 3. Leave Management
- Automatically detects approved leaves
- Marks as "On Leave" instead of "Absent"
- Integrates with Odoo's leave system

### 4. Device Management
- Links to device data
- Shows which device recorded attendance
- Tracks device-specific attendance

## Use Cases

### For HR Managers:

**Daily Monitoring**:
1. Open "Daily Attendance" menu
2. View today's attendance
3. See at a glance: Present (green), Absent (red), Missed Punch (yellow)
4. Click on any employee for details

**Monthly Review**:
1. Open "Daily Attendance"
2. Filter by "This Month"
3. Switch to Pivot or Graph view
4. Analyze attendance patterns
5. Export report

**Handling Exceptions**:
1. Go to "Missed Punch Today"
2. Review employees who forgot to punch out
3. Contact employees or manually correct
4. Add remarks for record

### For Employees (Self-Service):
1. Check own attendance record
2. See punch times
3. View worked hours
4. Check punctuality status

### For Department Heads:
1. Filter by department
2. Monitor team attendance
3. Identify patterns
4. Generate department reports

## Technical Details

### Models

**Main Model**: `zkteco.attendance.record`
- One record per employee per day
- Stores computed status and statistics
- Links to multiple `hr.attendance` records

**Extended Model**: `hr.attendance`
- Added field: `attendance_record_id`
- Automatically links to daily record
- Triggers status recomputation

### Fields

**Stored Fields** (computed and stored for performance):
- `status`: Current attendance status
- `first_checkin`: First punch time
- `last_checkout`: Last punch time
- `total_punches`: Count of punches
- `worked_hours`: Total hours worked
- `is_late`: Late arrival flag
- `is_early_leave`: Early departure flag
- `late_minutes`: Minutes late
- `early_leave_minutes`: Minutes early

**Computed Fields** (real-time):
- `display_name`: Readable record name
- `color`: UI color code based on status
- `attendance_count`: Number of punch records

### Business Logic

**Status Computation**:
```python
IF employee has approved leave THEN
    status = 'on_leave'
ELSE IF total_punches == 0 THEN
    status = 'absent'
ELSE IF any punch missing check-out THEN
    status = 'missed_punch'
ELSE
    status = 'present'
```

**Automatic Absence**:
```python
FOR each employee WITH active = True:
    IF no attendance_record exists for target_date:
        CREATE attendance_record
    
    IF status == 'absent' AND remarks is empty:
        SET remarks = "Automatically marked absent"
```

## Configuration

### Adjusting Cron Schedules:

1. Go to Settings → Technical → Automation → Scheduled Actions
2. Find the cron job:
   - "Generate Daily Attendance Records"
   - "Auto-Mark Absent Employees"
3. Modify schedule as needed
4. Save

### Expected Hours:

Default is 8.0 hours. To customize:
1. Can be set per shift
2. Can be adjusted per employee
3. Can be modified in attendance record

## Troubleshooting

### Records Not Generated:
- Check if cron "Generate Daily Attendance Records" is active
- Verify employees have `active = True`
- Check server timezone

### Employees Not Marked Absent:
- Ensure cron "Auto-Mark Absent Employees" is running
- Verify it runs after working hours
- Check if employees have punches recorded

### Wrong Status Showing:
- Verify punch data is processed (check hr.attendance)
- Check if employee has approved leave
- Manually refresh record or recompute

### Missing Punch Records:
- Check device connectivity
- Verify Flask ADMS is running
- Review quarantine for validation errors

## Best Practices

1. **Generate Records Early**: Run generation at 6 AM before work starts
2. **Mark Absent Late**: Run absence marking at 11 PM after work ends
3. **Review Daily**: HR should review daily attendance every morning
4. **Handle Missed Punches**: Address missed punches same day if possible
5. **Monthly Analysis**: Use pivot/graph views for monthly reviews
6. **Export Reports**: Regular export for payroll integration
7. **Document Exceptions**: Always add remarks for manual changes

## Reports

### Available Reports:

1. **Daily Attendance Summary**: Present/Absent/Missed Punch counts
2. **Department Attendance**: By department breakdown
3. **Punctuality Report**: Late arrivals and early leaves
4. **Monthly Attendance**: Month-over-month trends
5. **Employee Attendance History**: Individual employee records

### Exporting:

All views support:
- Excel export
- CSV export
- PDF export (via print)

## Future Enhancements

Potential improvements:
- Geolocation tracking for remote workers
- Mobile app for punch-in
- Biometric photo capture
- Advanced analytics dashboard
- Predictive absence alerts
- Integration with payroll
- Custom status types
- Email notifications for absences

---

## Summary

The Daily Attendance Records feature provides a comprehensive, automated solution for tracking employee attendance with minimal manual intervention. It automatically:

✅ Generates daily records for all employees
✅ Tracks punch-in/out times
✅ Computes attendance status in real-time
✅ Marks absent employees automatically
✅ Tracks punctuality
✅ Provides multiple views for analysis
✅ Integrates with existing Odoo HR features

This feature saves HR significant time while providing accurate, real-time attendance data for decision-making.
