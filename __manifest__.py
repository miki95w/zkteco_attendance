{
    'name': 'ZKTeco Attendance Machine',
    'version': '17.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Odoo Integration with ZKTeco for real-time attendance tracking',
    'description': """
        odoo 17 integration with F22 ZktEco Fingerprint Machine.
        
        Features:
        - Real-time attendance synchronization via Flask ADMS middleware
        - Device management and monitoring
        - User mapping between ZKTeco devices and Odoo employees
        - Quarantine management for invalid records
        - Automatic attendance processing
        - Daily attendance records with status tracking (Present/Absent/Missed Punch)
        - Automatic absence marking for employees who fail to punch in
        - Shift management
        - Comprehensive reporting
    """,
    'author': 'Top Tech',
    'website': 'https://www.odoo.com',
    'depends': ['base', 'hr', 'hr_attendance', 'hr_holidays'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.accd cess.csv',
        'data/cron.xml',
        'data/dashboard_data.xml',
        'views/device_views.xml',
        'views/attendance_views.xml',
        'views/mapping_views.xml',
        'views/hr_employee_views.xml',
        'views/shift_views.xml',
        'views/attendance_report_views.xml',
        'views/quarantine_views.xml',
        'views/adms_config_views.xml',
        'views/attendance_record_views.xml',
        'views/detailed_attendance_report_views.xml',
        'views/attendance_dashboard_views.xml',
        'views/cloud_config_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
