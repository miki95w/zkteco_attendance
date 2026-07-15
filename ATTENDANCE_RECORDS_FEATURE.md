# Attendance Records View - Detailed Report

## Overview

The Attendance Records view provides a comprehensive, detailed table of all employee attendance with check-in/out times, work hours, late arrivals, early leaves, overtime, and approval status - similar to traditional attendance management systems.

## Features

### 1. **Comprehensive Column Display**

The report shows all essential attendance information in a single view:

- **Employee**: Employee name
- **Department**: Employee's department
- **Date**: Attendance date
- **Attendance Status**: 
  - 🟢 **Present**: Complete attendance with check-in and check-out
  - 🔴 **Absent**: No attendance recorded
  - 🟡 **Incomplete**: Checked in but missed check-out
  - 🔵 **On Leave**: Employee has approved leave

### 2. **Time Tracking**

- **First Check-in**: First punch time of the day
- **Last Check-out**: Last punch time of the day
- **Work Min**: Total worked minutes
- **Work Hours**: Calculated working hours

### 3. **Punctuality Tracking**

- **Late**: Minutes late (if arrived after shift start)
- **Early Leave**: Minutes early (if left before shift end)
- **Late (min)**: Detailed late arrival in minutes
- **Early (min)**: Detailed early departure in minutes

### 4. **Overtime Tracking**

- **Overtime Hours**: Hours worked beyond expected hours
- Automatically calculated when worked hours exceed expected hours

### 5. **Approval Workflow**

- **Approval Status**:
  - **Draft**: Not yet submitted for approval
  - **Submitted**: Awaiting approval
  - **Approved**: Attendance approved
  - **Rejected**: Attendance rejected

## Data Source

The report is powered by a **PostgreSQL view** that aggregates data from:
- `zkteco.attendance.record` (Daily attendance records)
- Real-time computation of work hours, late/early time, overtime

## Views Available

### 1. **Tree View (List)**
- Color-coded rows by status
- All columns with optional hide/show
- Sortable columns
- Quick filters

### 2. **Form View (Detail)**
- Complete record details
- Employee information
- Time breakdown
- Punctuality analysis
- Shift information
- Remarks section

### 3. **Pivot View (Analysis)**
- Cross-tabulation by month, department, status
- Aggregate work hours and overtime
- Export to Excel capability

### 4. **Graph View (Charts)**
- Visual representation of attendance patterns
- Weekly/monthly trends
- Status distribution

## Filters and Search

### Status Filters:
- **Present**: Show only present employees
- **Absent**: Show only absent employees
- **Incomplete**: Show incomplete attendance (missed punch)
- **On Leave**: Show employees on leave

### Punctuality Filters:
- **Late Arrivals**: Employees who arrived late
- **Early Leaves**: Employees who left early
- **Overtime**: Employees with overtime hours

### Date Filters:
- **Today**: Current day records
- **Yesterday**: Previous day records
- **This Week**: Current week records
- **This Month**: Current month records
- **Last Month**: Previous month records

### Approval Filters:
- **Draft**: Not submitted
- **Submitted**: Awaiting approval
- **Approved**: Approved records

### Group By:
- Date
- Employee
- Department
- Status
- Shift
- Approval Status

## Access

**Menu Location**: `Attendance → Attendance Records`

**Default Filter**: This Month (shows current month records)

## Use Cases

### For HR Managers:

**Daily Monitoring**:
```
1. Open Attendance → Attendance Records
2. Apply "Today" filter
3. Review all employee attendance at a glance
4. Identify late arrivals (red highlight)
5. Identify early leaves (orange highlight)
6. Check incomplete attendance (yellow)
```

**Monthly Reports**:
```
1. Open Attendance → Attendance Records
2. Apply "This Month" filter
3. Switch to Pivot view
4. Group by Department and Status
5. Export to Excel for reporting
```

**Approval Workflow**:
```
1. Filter by "Submitted" status
2. Review attendance details
3. Approve or reject records
4. Add remarks if needed
```

### For Department Heads:

**Team Monitoring**:
```
1. Open Attendance → Attendance Records
2. Filter by own department
3. Apply "This Week" filter
4. Review team punctuality
5. Identify patterns (consistent late arrivals)
```

### For Payroll:

**Overtime Calculation**:
```
1. Open Attendance → Attendance Records
2. Apply "This Month" + "Overtime" filters
3. Export to Excel
4. Calculate overtime pay
```

**Work Hours Verification**:
```
1. Switch to Pivot view
2. Group by Employee
3. Sum work hours
4. Compare with expected hours
5. Identify discrepancies
```

## Technical Details

### Model: `zkteco.detailed.attendance.report`

**Type**: PostgreSQL View (read-only)

**Base Table**: `zkteco_attendance_record`

**Key Fields**:
- `employee_id`: Many2one to hr.employee
- `date`: Date of attendance
- `status`: Selection (present/absent/incomplete/on_leave)
- `first_checkin`: Datetime
- `last_checkout`: Datetime
- `work_hours`: Float (minutes)
- `late_minutes`: Float
- `early_leave_minutes`: Float
- `overtime_hours`: Float (calculated)
- `approval_status`: Selection

### Permissions:
- **Read**: All users
- **Write**: No (read-only report)
- **Create**: No (auto-generated from attendance records)
- **Delete**: No (managed by system)

## Color Coding

The tree view uses color decorations for quick visual identification:

- **Green rows**: Present employees
- **Red rows**: Absent employees
- **Yellow rows**: Incomplete attendance (missed punch)
- **Blue rows**: On leave

## Integration

### With Daily Attendance Records:
- Data is sourced from `zkteco.attendance.record`
- Updates automatically when attendance records change
- No manual sync required

### With Shift Management:
- Respects shift start/end times for late/early calculations
- Shows assigned shift in details

### With Leave Management:
- Automatically detects approved leaves
- Shows "On Leave" status

## Export Options

All views support export:
- **Excel**: Full data export with formatting
- **CSV**: Raw data for processing
- **PDF**: Printable reports

## Best Practices

1. **Daily Review**: Check attendance records daily at end of day
2. **Weekly Summary**: Review team attendance every Monday
3. **Monthly Reports**: Generate reports before payroll processing
4. **Filter Usage**: Use filters to focus on specific issues (late, absent, overtime)
5. **Export Regularly**: Keep attendance records for audit purposes

## Comparison with Daily Attendance

| Feature | Daily Attendance | Attendance Records |
|---------|-----------------|-------------------|
| Purpose | Real-time monitoring | Detailed reporting |
| Focus | Current day status | Historical analysis |
| Views | 6 views (including Calendar) | 4 views (List, Form, Pivot, Graph) |
| Filters | Status-based (Present/Absent) | Comprehensive (Status + Time + Approval) |
| Editing | Manual corrections possible | Read-only report |
| Use Case | Day-to-day operations | Reporting and analysis |

## Future Enhancements

Potential additions:
- Bulk approval workflow
- Email notifications for late arrivals
- Automatic overtime approval rules
- Integration with payroll module
- Custom report templates
- Manager approval hierarchy
- Biometric photo display
- GPS location tracking

---

## Summary

The Attendance Records view provides a **comprehensive, detailed reporting interface** for attendance management. It complements the Daily Attendance feature by offering:

✅ **Detailed view** of all attendance information  
✅ **Historical analysis** with powerful filters  
✅ **Punctuality tracking** with late/early indicators  
✅ **Overtime calculation** for payroll  
✅ **Approval workflow** for attendance validation  
✅ **Export capabilities** for reporting  
✅ **Read-only** to maintain data integrity  

This feature is ideal for **HR managers, department heads, and payroll administrators** who need detailed attendance reports for analysis, payroll processing, and compliance.

