# utils/decorators.py
from functools import wraps
from flask import flash, redirect, url_for, session, current_app
from flask_login import current_user
import json
from supabase import create_client, Client
import os
import time

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from functools import wraps
import json
from datetime import datetime
from urllib.parse import unquote

from routes.auth import get_utc_now, send_email_async 
import html


user_roles_bp = Blueprint('user_roles', __name__, url_prefix='/admin/users-roles')



# Import config directly
try:
    from config import Config
    config = Config()
except ImportError:
    # Fallback to environment variables
    config = type('Config', (), {
        'SUPABASE_URL': os.getenv('SUPABASE_URL'),
        'SUPABASE_KEY': os.getenv('SUPABASE_KEY'),
        'MAIL_SERVER': os.getenv('MAIL_SERVER'),
        'MAIL_PORT': int(os.getenv('MAIL_PORT', 587)),
        'MAIL_USERNAME': os.getenv('MAIL_USERNAME'),
        'MAIL_PASSWORD': os.getenv('MAIL_PASSWORD'),
        'CLOUDINARY_CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
        'CLOUDINARY_API_KEY': os.getenv('CLOUDINARY_API_KEY'),
        'CLOUDINARY_API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
        'APP_URL': os.getenv('APP_URL', 'http://localhost:5000')
    })()

# Performance cache for frequent operations
_supabase_client = None
_supabase_last_init = 0
_cache_duration = 300  # 5 minutes cache


def role_required(roles):
    """Decorator to require specific role(s)"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('auth.login'))
            
            # Get user role from session or database
            user_role = session.get('user_role', 'employee')
            
            if isinstance(roles, str):
                required_roles = [roles]
            else:
                required_roles = roles
            
            if user_role not in required_roles:
                flash('You do not have permission to access this page', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_supabase() -> Client:
    """Optimized Supabase client with connection pooling"""
    global _supabase_client, _supabase_last_init
    
    current_time = time.time()
    if _supabase_client is None or (current_time - _supabase_last_init) > _cache_duration:
        try:
            # Try to get from Flask app context first
            from flask import current_app
            if current_app and hasattr(current_app, 'config'):
                supabase_url = current_app.config.get('SUPABASE_URL')
                supabase_key = current_app.config.get('SUPABASE_KEY')
            else:
                # Fall back to direct config
                supabase_url = config.SUPABASE_URL
                supabase_key = config.SUPABASE_KEY
        except RuntimeError:
            # No app context, use direct config
            supabase_url = config.SUPABASE_URL
            supabase_key = config.SUPABASE_KEY
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase credentials not configured")
        
        _supabase_client = create_client(supabase_url, supabase_key)
        _supabase_last_init = current_time
    
    return _supabase_client



# Decorator to check if user is admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('auth.login'))
        
        if not session.get('is_admin') and session.get('user_role') != 'admin':
            flash('Administrator access required', 'error')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

# Log audit trail
def log_audit_action(action, target_type=None, target_id=None, old_values=None, new_values=None):
    try:
        supabase = get_supabase()
        supabase.table('role_audit_logs').insert({
            'user_id': session.get('user_id'),
            'action': action,
            'target_type': target_type,
            'target_id': target_id,
            'old_values': old_values,
            'new_values': new_values,
            'ip_address': request.remote_addr,
            'user_agent': request.user_agent.string,
            'created_at': get_utc_now().isoformat()
        }).execute()
    except Exception as e:
        print(f"⚠️ Failed to log audit action: {str(e)}")

def send_welcome_email_async(to_email, first_name, temp_password, business_name, admin_name):
    """Send welcome email to new employee using the standard email format"""
    
   
    
    subject = f"Welcome to {business_name} - Your Account Details"
    
    # Create HTML email content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Welcome to {html.escape(business_name)}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333333;
                margin: 0;
                padding: 0;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #ffffff;
            }}
            .header {{
                background: linear-gradient(135deg, #dc2626, #ef4444);
                color: white;
                padding: 40px 20px;
                text-align: center;
                border-radius: 10px 10px 0 0;
            }}
            .header h1 {{
                margin: 0;
                font-size: 28px;
                font-weight: 700;
            }}
            .header p {{
                margin: 10px 0 0 0;
                opacity: 0.9;
                font-size: 16px;
            }}
            .content {{
                padding: 30px;
                background-color: #f9fafb;
                border-radius: 0 0 10px 10px;
            }}
            .greeting {{
                font-size: 18px;
                margin-bottom: 25px;
                color: #374151;
            }}
            .info-card {{
                background: white;
                border-radius: 8px;
                padding: 25px;
                margin: 20px 0;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                border-left: 4px solid #dc2626;
            }}
            .password-box {{
                background: #fef2f2;
                border: 2px dashed #dc2626;
                padding: 25px;
                margin: 25px 0;
                text-align: center;
                font-family: 'Courier New', monospace;
                font-size: 24px;
                font-weight: bold;
                letter-spacing: 2px;
                border-radius: 8px;
                color: #dc2626;
            }}
            .warning-box {{
                background: #fffbeb;
                border-left: 4px solid #f59e0b;
                padding: 20px;
                margin: 25px 0;
                border-radius: 8px;
            }}
            .warning-box h3 {{
                color: #d97706;
                margin-top: 0;
                font-size: 16px;
            }}
            .cta-button {{
                display: inline-block;
                background: linear-gradient(135deg, #dc2626, #ef4444);
                color: white !important;
                padding: 14px 32px;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 16px;
                text-align: center;
                margin: 20px auto;
                transition: all 0.3s ease;
            }}
            .cta-button:hover {{
                background: linear-gradient(135deg, #b91c1c, #dc2626);
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(220, 38, 38, 0.2);
            }}
            .steps {{
                background: white;
                border-radius: 8px;
                padding: 20px;
                margin: 25px 0;
            }}
            .step {{
                display: flex;
                align-items: flex-start;
                margin-bottom: 15px;
                padding-bottom: 15px;
                border-bottom: 1px solid #e5e7eb;
            }}
            .step:last-child {{
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }}
            .step-number {{
                background: #dc2626;
                color: white;
                width: 30px;
                height: 30px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                margin-right: 15px;
                flex-shrink: 0;
            }}
            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #e5e7eb;
                color: #6b7280;
                font-size: 14px;
                text-align: center;
            }}
            .footer p {{
                margin: 5px 0;
            }}
            .highlight {{
                color: #dc2626;
                font-weight: 600;
            }}
            @media (max-width: 600px) {{
                .container {{
                    padding: 10px;
                }}
                .header h1 {{
                    font-size: 24px;
                }}
                .password-box {{
                    font-size: 20px;
                    padding: 20px;
                }}
                .cta-button {{
                    padding: 12px 24px;
                    font-size: 14px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to {html.escape(business_name)}!</h1>
                <p>Your account has been created by {html.escape(admin_name)}</p>
            </div>
            
            <div class="content">
                <div class="greeting">
                    Hi <span class="highlight">{html.escape(first_name)}</span>,
                </div>
                
                <div class="info-card">
                    <p>Welcome to the team! We're excited to have you join us. Your account has been set up on our ThriveOS platform, where you'll find everything you need to get started.</p>
                </div>
                
                <div class="info-card">
                    <h3 style="margin-top: 0; color: #374151;">Your Login Details:</h3>
                    <p><strong>Email:</strong> {html.escape(to_email)}</p>
                    <p><strong>Temporary Password:</strong></p>
                    
                    <div class="password-box">
                        {html.escape(temp_password)}
                    </div>
                    
                    <p style="text-align: center; font-size: 14px; color: #6b7280;">
                        Copy this password to use during your first login
                    </p>
                </div>
                
                <div class="warning-box">
                    <h3>⚠️ Important Security Notice</h3>
                    <p>For your security, please follow these steps on your first login:</p>
                </div>
                
                <div class="steps">
                    <div class="step">
                        <div class="step-number">1</div>
                        <div>
                            <strong>Click the login button below</strong>
                            <p>Access your account using the button provided</p>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-number">2</div>
                        <div>
                            <strong>Use your temporary password</strong>
                            <p>Enter the password shown above</p>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-number">3</div>
                        <div>
                            <strong>Change your password immediately</strong>
                            <p>Set a strong, unique password after logging in</p>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-number">4</div>
                        <div>
                            <strong>Verify your email address</strong>
                            <p>Complete the email verification process</p>
                        </div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{request.host_url}login" class="cta-button">
                        Login to Your Account
                    </a>
                    <p style="color: #6b7280; font-size: 14px; margin-top: 10px;">
                        Or visit: {request.host_url}login
                    </p>
                </div>
                
                <div class="info-card">
                    <h3 style="margin-top: 0; color: #374151;">Need Help?</h3>
                    <p>If you encounter any issues or have questions:</p>
                    <ul style="color: #4b5563;">
                        <li>Contact your manager: {html.escape(admin_name)}</li>
                        <li>Reach out to your HR department</li>
                        <li>Check your spam folder if you don't see this email</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p><strong>Best regards,</strong></p>
                    <p>The {html.escape(business_name)} Team</p>
                    <p style="margin-top: 20px; font-size: 12px; color: #9ca3af;">
                        This is an automated message. Please do not reply to this email.<br>
                        If you believe you received this email in error, please contact your administrator.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Create plain text version
    text_content = f"""
    Welcome to {business_name}!
    
    Hi {first_name},
    
    Welcome to the team! Your account has been created by {admin_name}.
    
    LOGIN DETAILS:
    Email: {to_email}
    Temporary Password: {temp_password}
    
    IMPORTANT:
    1. Go to {request.host_url}login
    2. Use your email and the temporary password above
    3. Change your password immediately after login
    4. Verify your email address
    
    Need help? Contact {admin_name} or your HR department.
    
    This is an automated message. Please do not reply.
    """
    
    # Send the email using the existing async function
    send_email_async(to_email, subject, html_content, text_content)
    
    
# Routes
@user_roles_bp.route('/')
@admin_required
def index():
    """Main dashboard for Users & Roles management"""
    try:
        supabase = get_supabase()
        
        # Get statistics
        users_count = supabase.table('users').select('id', count='exact').execute().count or 0
        active_users = supabase.table('users').select('id', count='exact').eq('is_active', True).execute().count or 0
        roles_count = supabase.table('user_roles').select('id', count='exact').execute().count or 0
        
        # Get recent audit logs
        audit_logs = supabase.table('role_audit_logs')\
            .select('*, users(first_name, last_name, email)')\
            .order('created_at', desc=True)\
            .limit(10)\
            .execute()
        
        # Get users with roles
        users = supabase.table('users')\
            .select('*, user_roles(name)')\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()
        
        return render_template('admin/user_roles/index.html',
                             users_count=users_count,
                             active_users=active_users,
                             roles_count=roles_count,
                             audit_logs=audit_logs.data if audit_logs.data else [],
                             users=users.data if users.data else [])
    
    except Exception as e:
        print(f"❌ Error loading user roles dashboard: {str(e)}")
        flash('Error loading dashboard. Please try again.', 'error')
        return redirect(url_for('dashboard'))
    
    
@user_roles_bp.route('/employees')
@admin_required
def employees():
    """Employee management page"""
    try:
        supabase = get_supabase()
        
        # Get admin's business
        admin_id = session.get('user_id')
        admin_business = supabase.table('businesses')\
            .select('id, business_name')\
            .eq('user_id', admin_id)\
            .limit(1)\
            .execute()
        
        if not admin_business.data:
            flash('Please create a business first to manage employees', 'error')
            return redirect(url_for('dashboard'))  # Redirect to dashboard to create business
        
        business_id = admin_business.data[0]['id']
        business_name = admin_business.data[0]['business_name']
        
        # Get all users from the same business with their roles
        users = supabase.table('users')\
            .select('*, user_roles(name, is_admin)')\
            .eq('business_id', business_id)\
            .order('created_at', desc=True)\
            .execute()
        
        # Get all roles for dropdown
        roles = supabase.table('user_roles')\
            .select('*')\
            .order('name')\
            .execute()
        
        # Get users in same business for reports_to dropdown (excluding current user)
        managers = supabase.table('users')\
            .select('id, first_name, last_name, position')\
            .eq('business_id', business_id)\
            .eq('is_active', True)\
            .neq('id', admin_id)\
            .order('first_name')\
            .execute()
        
        return render_template('admin/user_roles/employees.html',
                             users=users.data if users.data else [],
                             roles=roles.data if roles.data else [],
                             managers=managers.data if managers.data else [],
                             business_name=business_name,
                             business_id=business_id)
    
    except Exception as e:
        print(f"❌ Error loading employees: {str(e)}")
        flash('Error loading employees. Please try again.', 'error')
        return redirect(url_for('user_roles.index'))
    
@user_roles_bp.route('/employees/add', methods=['POST'])
@admin_required
def add_employee():
    """Add a new employee"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'first_name', 'last_name', 'role_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'message': f'{field.replace("_", " ").title()} is required'})
        
        supabase = get_supabase()
        
        # Check if email already exists
        existing_user = supabase.table('users')\
            .select('id')\
            .eq('email', data['email'].strip().lower())\
            .limit(1)\
            .execute()
        
        if existing_user.data:
            return jsonify({'success': False, 'message': 'Email already registered'})
        
        # Get admin's business
        admin_id = session.get('user_id')
        admin_business = supabase.table('businesses')\
            .select('id, business_name')\
            .eq('user_id', admin_id)\
            .limit(1)\
            .execute()
        
        if not admin_business.data:
            return jsonify({'success': False, 'message': 'Admin does not have a business. Please create a business first.'})
        
        admin_business_data = admin_business.data[0]
        business_id = admin_business_data['id']
        business_name = admin_business_data['business_name']
        
        # Validate role_id is a valid UUID
        import uuid
        try:
            role_uuid = uuid.UUID(data['role_id'])
        except (ValueError, AttributeError):
            return jsonify({'success': False, 'message': 'Invalid role selected'})
        
        # Validate reports_to if provided
        reports_to = data.get('reports_to')
        if reports_to:
            try:
                reports_to_uuid = uuid.UUID(reports_to)
                # Check if the manager exists and is in the same business
                manager_exists = supabase.table('users')\
                    .select('id')\
                    .eq('id', reports_to)\
                    .eq('business_id', business_id)\
                    .limit(1)\
                    .execute()
                if not manager_exists.data:
                    return jsonify({'success': False, 'message': 'Selected manager does not exist in your business'})
            except (ValueError, AttributeError):
                return jsonify({'success': False, 'message': 'Invalid manager selected'})
        
        # Generate a temporary password
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        # Hash the password
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(temp_password)
        
        # Prepare user data - AUTO VERIFY admin-created employees
        user_data = {
            'email': data['email'].strip().lower(),
            'first_name': data['first_name'].strip(),
            'last_name': data['last_name'].strip(),
            'password_hash': password_hash,
            'role_id': data['role_id'],
            'business_id': business_id,  # Assign to admin's business
            'is_active': data.get('is_active', True),
            'email_verified': True,  # AUTO VERIFY admin-created employees
            'verified_at': get_utc_now().isoformat(),  # Set verification timestamp
            'created_at': get_utc_now().isoformat(),
            'updated_at': get_utc_now().isoformat()
        }
        
        # Only add optional fields if they have values
        optional_fields = ['department', 'position', 'hire_date', 'reports_to']
        for field in optional_fields:
            if data.get(field):
                if field == 'reports_to' and data[field]:
                    user_data[field] = data[field]
                elif field != 'reports_to':
                    user_data[field] = data[field].strip() if isinstance(data[field], str) else data[field]
        
        # Insert new employee
        result = supabase.table('users').insert(user_data).execute()
        
        if result.data:
            user_id = result.data[0]['id']
            
            # Get role details
            role = supabase.table('user_roles')\
                .select('name, is_admin')\
                .eq('id', data['role_id'])\
                .single()\
                .execute()
            
            # Update user's role and is_admin based on role
            if role.data:
                update_role_data = {
                    'role': role.data['name'],
                    'is_admin': role.data['is_admin'],
                    'updated_at': get_utc_now().isoformat()
                }
                supabase.table('users').update(update_role_data).eq('id', user_id).execute()
            
            # Log the action
            log_audit_action('create_employee', 'user', user_id, 
                           None, {
                               'email': user_data['email'],
                               'role_id': user_data['role_id'],
                               'business_id': business_id,
                               'first_name': user_data['first_name'],
                               'last_name': user_data['last_name'],
                               'auto_verified': True
                           })
            
            # Send welcome email
            send_welcome_email_async(
                user_data['email'],
                user_data['first_name'],
                temp_password,
                business_name,
                session.get('user_name', 'Administrator')
            )
            
            return jsonify({
                'success': True,
                'message': f'Employee {user_data["first_name"]} {user_data["last_name"]} added successfully to {business_name}',
                'data': {
                    'id': user_id,
                    'email': user_data['email'],
                    'name': f"{user_data['first_name']} {user_data['last_name']}",
                    'business': business_name,
                    'temp_password': temp_password
                }
            })
        
        return jsonify({'success': False, 'message': 'Failed to add employee'})
    
    except Exception as e:
        print(f"❌ Error adding employee: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Internal server error: {str(e)}'})
@user_roles_bp.route('/employees/<user_id>', methods=['GET', 'PUT', 'DELETE'])
@admin_required
def manage_employee(user_id):
    """Get, update, or delete an employee"""
    try:
        supabase = get_supabase()
        
        if request.method == 'GET':
            # Get employee details WITHOUT business join initially
            user = supabase.table('users')\
                .select('*, user_roles(name, is_admin)')\
                .eq('id', user_id)\
                .single()\
                .execute()
            
            if user.data:
                # Get business information separately
                business_id = user.data.get('business_id')
                if business_id:
                    business = supabase.table('businesses')\
                        .select('business_name')\
                        .eq('id', business_id)\
                        .single()\
                        .execute()
                    
                    if business.data:
                        user.data['business'] = business.data
                    else:
                        user.data['business'] = {'business_name': 'Business not found'}
                else:
                    user.data['business'] = {'business_name': 'No business assigned'}
                
                return jsonify({'success': True, 'data': user.data})
            return jsonify({'success': False, 'message': 'Employee not found'})
        
        elif request.method == 'PUT':
            # Update employee
            data = request.get_json()
            
            # Get old values for audit log
            old_user = supabase.table('users')\
                .select('*')\
                .eq('id', user_id)\
                .single()\
                .execute()
            
            update_data = {}
            for key in ['first_name', 'last_name', 'department', 'position', 
                       'hire_date', 'reports_to', 'is_active']:
                if key in data:
                    if key == 'reports_to':
                        # Handle empty reports_to (set to null)
                        if data[key] == '' or data[key] is None:
                            update_data[key] = None
                        else:
                            update_data[key] = data[key]
                    elif key in ['is_active']:
                        update_data[key] = bool(data[key])
                    else:
                        update_data[key] = data[key].strip() if isinstance(data[key], str) else data[key]
            
            # Handle role change
            if 'role_id' in data and data['role_id']:
                import uuid
                try:
                    # Validate UUID
                    uuid.UUID(data['role_id'])
                    update_data['role_id'] = data['role_id']
                    
                    # Get new role details
                    role = supabase.table('user_roles')\
                        .select('name, is_admin')\
                        .eq('id', data['role_id'])\
                        .single()\
                        .execute()
                    
                    if role.data:
                        update_data['role'] = role.data['name']
                        update_data['is_admin'] = role.data['is_admin']
                except (ValueError, AttributeError):
                    return jsonify({'success': False, 'message': 'Invalid role selected'})
            
            if update_data:
                update_data['updated_at'] = get_utc_now().isoformat()
                result = supabase.table('users').update(update_data).eq('id', user_id).execute()
                
                if result.data:
                    # Log the action
                    log_audit_action('update_employee', 'user', user_id,
                                   old_user.data if old_user.data else {},
                                   update_data)
                    
                    return jsonify({'success': True, 'message': 'Employee updated successfully'})
            
            return jsonify({'success': False, 'message': 'No changes to update'})
        
        elif request.method == 'DELETE':
            # Soft delete employee (deactivate)
            result = supabase.table('users')\
                .update({
                    'is_active': False, 
                    'updated_at': get_utc_now().isoformat(),
                    'deleted_at': get_utc_now().isoformat()
                })\
                .eq('id', user_id)\
                .execute()
            
            if result.data:
                # Log the action
                log_audit_action('deactivate_employee', 'user', user_id)
                return jsonify({'success': True, 'message': 'Employee deactivated successfully'})
            
            return jsonify({'success': False, 'message': 'Failed to deactivate employee'})
    
    except Exception as e:
        print(f"❌ Error managing employee: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Internal server error: {str(e)}'})
    
    
@user_roles_bp.route('/roles')
@admin_required
def roles():
    """Roles management page"""
    try:
        supabase = get_supabase()
        
        # Get all roles
        roles = supabase.table('user_roles')\
            .select('*')\
            .order('created_at', desc=True)\
            .execute()
        
        # Get user count for each role
        roles_with_count = []
        for role in roles.data:
            # Count users with this role
            user_count = supabase.table('users')\
                .select('id', count='exact')\
                .eq('role_id', role['id'])\
                .execute()
            
            role['users_count'] = user_count.count or 0
            roles_with_count.append(role)
        
        return render_template('admin/user_roles/roles.html',
                             roles=roles_with_count)
    
    except Exception as e:
        print(f"❌ Error loading roles: {str(e)}")
        flash('Error loading roles. Please try again.', 'error')
        return redirect(url_for('user_roles.index'))

@user_roles_bp.route('/roles/add', methods=['POST'])
@admin_required
def add_role():
    """Add a new role"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if 'name' not in data or not data['name']:
            return jsonify({'success': False, 'message': 'Role name is required'})
        
        supabase = get_supabase()
        
        # Check if role name already exists
        existing_role = supabase.table('user_roles')\
            .select('id')\
            .eq('name', data['name'].strip())\
            .limit(1)\
            .execute()
        
        if existing_role.data:
            return jsonify({'success': False, 'message': 'Role name already exists'})
        
        # Prepare role data
        role_data = {
            'name': data['name'].strip(),
            'description': data.get('description', '').strip(),
            'is_admin': data.get('is_admin', False),
            'can_manage_users': data.get('can_manage_users', False),
            'can_manage_roles': data.get('can_manage_roles', False),
            'can_view_analytics': data.get('can_view_analytics', False),
            'can_manage_settings': data.get('can_manage_settings', False),
            'is_default': data.get('is_default', False),
            'created_at': get_utc_now().isoformat()
        }
        
        # Insert new role
        result = supabase.table('user_roles').insert(role_data).execute()
        
        if result.data:
            role_id = result.data[0]['id']
            
            # Log the action
            log_audit_action('create_role', 'role', role_id, None, {'name': role_data['name']})
            
            return jsonify({
                'success': True,
                'message': 'Role created successfully',
                'data': result.data[0]
            })
        
        return jsonify({'success': False, 'message': 'Failed to create role'})
    
    except Exception as e:
        print(f"❌ Error adding role: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@user_roles_bp.route('/roles/<role_id>', methods=['GET', 'PUT', 'DELETE'])
@admin_required
def manage_role(role_id):
    """Get, update, or delete a role"""
    try:
        supabase = get_supabase()
        
        if request.method == 'GET':
            # Get role details
            role = supabase.table('user_roles')\
                .select('*')\
                .eq('id', role_id)\
                .single()\
                .execute()
            
            if role.data:
                return jsonify({'success': True, 'data': role.data})
            return jsonify({'success': False, 'message': 'Role not found'})
        
        elif request.method == 'PUT':
            # Update role
            data = request.get_json()
            
            # Get old values for audit log
            old_role = supabase.table('user_roles')\
                .select('*')\
                .eq('id', role_id)\
                .single()\
                .execute()
            
            update_data = {}
            for key in ['name', 'description', 'is_admin', 'can_manage_users', 
                       'can_manage_roles', 'can_view_analytics', 'can_manage_settings', 'is_default']:
                if key in data:
                    update_data[key] = data[key]
            
            if update_data:
                update_data['updated_at'] = get_utc_now().isoformat()
                result = supabase.table('user_roles').update(update_data).eq('id', role_id).execute()
                
                if result.data:
                    # Log the action
                    log_audit_action('update_role', 'role', role_id,
                                   old_role.data if old_role.data else {},
                                   update_data)
                    
                    return jsonify({'success': True, 'message': 'Role updated successfully'})
            
            return jsonify({'success': False, 'message': 'No changes to update'})
        
        elif request.method == 'DELETE':
            # Check if role is in use
            users_with_role = supabase.table('users')\
                .select('id', count='exact')\
                .eq('role_id', role_id)\
                .execute()
            
            if users_with_role.count and users_with_role.count > 0:
                return jsonify({
                    'success': False, 
                    'message': f'Cannot delete role. {users_with_role.count} users are assigned to this role.'
                })
            
            # Get role info for audit log
            role = supabase.table('user_roles')\
                .select('name')\
                .eq('id', role_id)\
                .single()\
                .execute()
            
            # Delete role
            result = supabase.table('user_roles').delete().eq('id', role_id).execute()
            
            if result.data:
                # Log the action
                log_audit_action('delete_role', 'role', role_id,
                               {'name': role.data['name'] if role.data else 'Unknown'}, None)
                
                return jsonify({'success': True, 'message': 'Role deleted successfully'})
            
            return jsonify({'success': False, 'message': 'Failed to delete role'})
    
    except Exception as e:
        print(f"❌ Error managing role: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@user_roles_bp.route('/login-settings')
@admin_required
def login_settings():
    """Login and biometric settings page"""
    try:
        supabase = get_supabase()
        
        # Get current security settings
        users_with_2fa = supabase.table('users')\
            .select('id', count='exact')\
            .eq('two_factor_enabled', True)\
            .execute()
        
        users_with_biometric = supabase.table('users')\
            .select('id', count='exact')\
            .eq('biometric_enabled', True)\
            .execute()
        
        # Get recent login attempts
        recent_logins = supabase.table('auth_logs')\
            .select('*, users(first_name, last_name)')\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()
        
        return render_template('admin/user_roles/login_settings.html',
                             users_with_2fa=users_with_2fa.count or 0,
                             users_with_biometric=users_with_biometric.count or 0,
                             recent_logins=recent_logins.data if recent_logins.data else [])
    
    except Exception as e:
        print(f"❌ Error loading login settings: {str(e)}")
        flash('Error loading login settings. Please try again.', 'error')
        return redirect(url_for('user_roles.index'))

@user_roles_bp.route('/audit-logs')
@admin_required
def audit_logs():
    """Audit logs page"""
    try:
        supabase = get_supabase()
        
        # Get filter parameters
        action = request.args.get('action', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query
        query = supabase.table('role_audit_logs')\
            .select('*, users(first_name, last_name, email)')\
            .order('created_at', desc=True)
        
        if action:
            query = query.eq('action', action)
        
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00Z')
        
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59Z')
        
        logs = query.limit(100).execute()
        
        # Get unique actions for filter dropdown
        unique_actions = supabase.table('role_audit_logs')\
            .select('action')\
            .order('action')\
            .execute()
        
        actions = sorted(set([log['action'] for log in unique_actions.data])) if unique_actions.data else []
        
        return render_template('admin/user_roles/audit_logs.html',
                             logs=logs.data if logs.data else [],
                             actions=actions,
                             current_action=action,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        print(f"❌ Error loading audit logs: {str(e)}")
        flash('Error loading audit logs. Please try again.', 'error')
        return redirect(url_for('user_roles.index'))
    
    
@user_roles_bp.route('/search-users')
@admin_required
def search_users():
    """Search users for autocomplete"""
    try:
        query = request.args.get('q', '')
        
        if not query or len(query) < 2:
            return jsonify({'results': []})
        
        supabase = get_supabase()

        users = (
            supabase.table('users')
            .select('id, first_name, last_name, email, position, department')
            .or_(f"first_name.ilike.*{query}*,last_name.ilike.*{query}*,email.ilike.*{query}*")
            .limit(10)
            .execute()
        )

        results = [
            {
                'id': u['id'],
                'text': f"{u['first_name']} {u['last_name']} ({u['email']})",
                'email': u['email'],
                'position': u.get('position', ''),
                'department': u.get('department', '')
            }
            for u in users.data
        ]

        return jsonify({'results': results})

    except Exception as e:
        print(f"❌ Error searching users: {str(e)}")
      


@user_roles_bp.route('/audit-logs/<log_id>/details')
@admin_required
def audit_log_details(log_id):
    """Get detailed information for a specific audit log"""
    try:
        supabase = get_supabase()
        
        # Get the audit log with user information
        log_response = supabase.table('role_audit_logs')\
            .select('*, users(first_name, last_name, email)')\
            .eq('id', log_id)\
            .single()\
            .execute()
        
        if not log_response.data:
            return jsonify({'success': False, 'message': 'Audit log not found'})
        
        log_data = log_response.data
        
        # Format the data for display
        formatted_log = {
            'id': log_data['id'],
            'created_at': log_data['created_at'],
            'action': log_data['action'],
            'target_type': log_data['target_type'],
            'target_id': log_data['target_id'],
            'ip_address': log_data['ip_address'],
            'user_agent': log_data['user_agent'],
            'old_values': log_data.get('old_values'),
            'new_values': log_data.get('new_values'),
            'users': log_data.get('users')
        }
        
        return jsonify({
            'success': True,
            'data': formatted_log
        })
    
    except Exception as e:
        print(f"❌ Error fetching audit log details: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to load audit log details'})
    
    
@user_roles_bp.route('/audit-logs/export')
@admin_required
def export_audit_logs():
    """Export audit logs as CSV"""
    try:
        import csv
        import io
        from flask import Response
        
        supabase = get_supabase()
        
        # Get filter parameters
        action = request.args.get('action', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query
        query = supabase.table('role_audit_logs')\
            .select('*, users(first_name, last_name, email)')\
            .order('created_at', desc=True)
        
        if action:
            query = query.eq('action', action)
        
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00Z')
        
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59Z')
        
        logs = query.limit(1000).execute()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Timestamp', 'User', 'Email', 'Action', 'Target Type', 
            'Target ID', 'IP Address', 'User Agent', 'Old Values', 'New Values'
        ])
        
        # Write data
        for log in logs.data if logs.data else []:
            user = log.get('users', {})
            writer.writerow([
                log.get('created_at', ''),
                f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                user.get('email', ''),
                log.get('action', ''),
                log.get('target_type', ''),
                log.get('target_id', ''),
                log.get('ip_address', ''),
                log.get('user_agent', ''),
                str(log.get('old_values', '')),
                str(log.get('new_values', ''))
            ])
        
        # Return CSV file
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=audit_logs.csv"}
        )
    
    except Exception as e:
        print(f"❌ Error exporting audit logs: {str(e)}")
        flash('Failed to export audit logs', 'error')
        return redirect(url_for('user_roles.audit_logs'))