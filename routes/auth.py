# routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import pyotp
from datetime import datetime, timezone, timedelta  # Added timezone
import cloudinary
import cloudinary.uploader
from supabase import create_client, Client
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time
import json
import os
from dateutil import parser  # Added for parsing ISO datetime
from functools import wraps

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

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


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

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

def role_required(required_roles):
    """
    Decorator to require specific role(s) for access.
    
    Args:
        required_roles: Can be a string (single role) or list of strings (multiple roles)
    
    Examples:
        @role_required('admin')  # Requires admin role
        @role_required(['admin', 'manager'])  # Requires either admin or manager
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is logged in
            if 'user_id' not in session:
                flash('Please login to access this page', 'warning')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('user_role', 'employee')
            
            # Normalize required_roles to a list
            if isinstance(required_roles, str):
                roles_list = [required_roles]
            elif isinstance(required_roles, list):
                roles_list = required_roles
            else:
                flash('Invalid role configuration', 'error')
                return redirect(url_for('dashboard'))
            
            # Check if user has required role
            if user_role not in roles_list:
                # Create friendly error message
                if len(roles_list) == 1:
                    role_display = roles_list[0].capitalize()
                    error_msg = f'{role_display} access required'
                else:
                    # Format: "Admin, Manager, or Cashier access required"
                    formatted_roles = [r.capitalize() for r in roles_list[:-1]]
                    if len(formatted_roles) > 1:
                        formatted_roles = ', '.join(formatted_roles)
                    else:
                        formatted_roles = formatted_roles[0] if formatted_roles else ''
                    
                    last_role = roles_list[-1].capitalize()
                    if formatted_roles:
                        error_msg = f'{formatted_roles} or {last_role} access required'
                    else:
                        error_msg = f'{last_role} access required'
                
                flash(error_msg, 'error')
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

def get_config_value(key, default=None):
    """Safely get config value from Flask app or direct config"""
    try:
        from flask import current_app
        if current_app and hasattr(current_app, 'config'):
            value = current_app.config.get(key)
            if value is not None:
                return value
    except RuntimeError:
        pass  # No app context
    
    # Fall back to direct config
    return getattr(config, key, default)

def get_utc_now():
    """Get current UTC datetime with timezone awareness"""
    return datetime.now(timezone.utc)

def parse_iso_datetime(iso_string):
    """Parse ISO datetime string to timezone-aware datetime"""
    if not iso_string:
        return None
    # Use dateutil.parser for robust ISO datetime parsing
    try:
        return parser.isoparse(iso_string)
    except (ValueError, AttributeError):
        # Fallback for simple ISO format
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

def send_email_async(to_email, subject, html_content, text_content=None):
    """Send email in background thread for performance"""
    def send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"ThriveOS - {subject}"
            
            # Get email credentials
            mail_username = get_config_value('MAIL_USERNAME')
            mail_password = get_config_value('MAIL_PASSWORD')
            
            # Remove spaces from password if present
            if mail_password:
                mail_password = mail_password.replace(' ', '')
            
            msg['From'] = mail_username
            msg['To'] = to_email
            
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            mail_server = get_config_value('MAIL_SERVER', 'smtp.gmail.com')
            mail_port = get_config_value('MAIL_PORT', 587)
            
            print(f"📧 Attempting to send email to {to_email}")
            print(f"   Using server: {mail_server}:{mail_port}")
            
            with smtplib.SMTP(mail_server, mail_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(mail_username, mail_password)
                server.send_message(msg)
            
            print(f"✅ Email sent to {to_email}")
            
        except Exception as e:
            print(f"❌ Email sending failed: {str(e)}")
            import traceback
            traceback.print_exc()
    
    thread = threading.Thread(target=send)
    thread.daemon = True
    thread.start()

def generate_otp_email_html(otp_code, user_name=None):
    """Generate beautiful OTP email template"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #dc2626; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }}
            .otp-box {{ background: #fff; border: 2px dashed #dc2626; padding: 20px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 10px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ThriveOS</h1>
                <p>Your Verification Code</p>
            </div>
            <div class="content">
                <p>Hello{f' {user_name}' if user_name else ''},</p>
                <p>Thank you for registering with ThriveOS. Use the following OTP to verify your email address:</p>
                
                <div class="otp-box">{otp_code}</div>
                
                <p>This code will expire in 10 minutes.</p>
                <p>If you didn't request this, please ignore this email.</p>
                
                <p>Best regards,<br>The ThriveOS Team</p>
            </div>
            <div class="footer">
                <p>© {datetime.now().year} LUNSERK Technologies. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        start_time = time.time()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please fill in all fields', 'error')
            return render_template('auth/login.html')
        
        try:
            supabase = get_supabase()
            
            # Include business_id in the select
            response = supabase.table('users').select(
                'id,email,password_hash,email_verified,first_name,last_login,login_count,role,is_admin,business_id'
            ).eq('email', email).limit(1).execute()
            
            if response.data:
                user = response.data[0]
                
                # Verify password
                if check_password_hash(user['password_hash'], password):
                    if user['email_verified']:
                        # Update login stats
                        supabase.table('users').update({
                            'last_login': get_utc_now().isoformat(),
                            'login_count': (user.get('login_count') or 0) + 1
                        }).eq('id', user['id']).execute()
                        
                        # Set session with all required information
                        session['user_id'] = user['id']
                        session['user_email'] = user['email']
                        session['user_name'] = f"{user.get('first_name', '')}"
                        session['user_role'] = user.get('role', 'user')
                        session['is_admin'] = user.get('is_admin', False)
                        session['business_id'] = user.get('business_id')  # THIS IS CRITICAL
                        
                        # If business_id is not in users table, try to get it from businesses table
                        if not session['business_id']:
                            # Try to find user's business
                            business_response = supabase.table('business_users').select(
                                'business_id'
                            ).eq('user_id', user['id']).limit(1).execute()
                            
                            if business_response.data:
                                session['business_id'] = business_response.data[0]['business_id']
                        
                        # Log login
                        supabase.table('auth_logs').insert({
                            'user_id': user['id'],
                            'ip_address': request.remote_addr,
                            'user_agent': request.user_agent.string,
                            'action': 'login',
                            'status': 'success',
                            'created_at': get_utc_now().isoformat()
                        }).execute()
                        
                        processing_time = round((time.time() - start_time) * 1000, 2)
                        print(f"✅ Login successful for {email} in {processing_time}ms")
                        print(f"✅ Session set: user_id={session['user_id']}, business_id={session.get('business_id')}, role={session['user_role']}")
                        
                        flash(f'Welcome back! Login successful in {processing_time}ms', 'success')
                        return redirect(url_for('dashboard'))
                    else:
                        # Send new OTP if not verified
                        otp_secret = pyotp.random_base32()
                        otp = pyotp.TOTP(otp_secret)
                        otp_code = otp.now()
                        
                        supabase.table('users').update({
                            'otp_secret': otp_secret,
                            'otp_expiry': (get_utc_now() + timedelta(minutes=10)).isoformat()
                        }).eq('id', user['id']).execute()
                        
                        # Send verification email
                        send_email_async(
                            email,
                            "Verify Your Email",
                            generate_otp_email_html(otp_code, user.get('first_name'))
                        )
                        
                        flash('Please verify your email first. A new verification code has been sent.', 'warning')
                        return redirect(url_for('auth.verify_email'))
                else:
                    # Log failed attempt
                    supabase.table('auth_logs').insert({
                        'ip_address': request.remote_addr,
                        'user_agent': request.user_agent.string,
                        'action': 'login',
                        'status': 'failed',
                        'details': json.dumps({'email': email}),
                        'created_at': get_utc_now().isoformat()
                    }).execute()
                    
                    flash('Invalid credentials. Please try again.', 'error')
            else:
                flash('Invalid credentials. Please try again.', 'error')
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            flash(f'An error occurred. Please try again.', 'error')
        
        return render_template('auth/login.html')
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        start_time = time.time()
        
        # Extract form data
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        business_name = request.form.get('business_name', '').strip()
        logo = request.files.get('business_logo')
        
        # Validation
        if not all([email, password, confirm_password, first_name, last_name, business_name]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('auth/register.html')
        
        try:
            supabase = get_supabase()
            
            # Check if user already exists
            existing_user = supabase.table('users').select('id').eq('email', email).limit(1).execute()
            if existing_user.data:
                flash('Email already registered. Please login instead.', 'error')
                return redirect(url_for('auth.login'))
            
            # Hash password
            password_hash = generate_password_hash(password)
            
            # Generate OTP
            otp_secret = pyotp.random_base32()
            otp = pyotp.TOTP(otp_secret)
            otp_code = otp.now()
            
            # Upload logo to Cloudinary if provided
            logo_url = None
            cloudinary_public_id = None
            if logo and logo.filename:
                cloudinary_cloud_name = get_config_value('CLOUDINARY_CLOUD_NAME')
                cloudinary_api_key = get_config_value('CLOUDINARY_API_KEY')
                cloudinary_api_secret = get_config_value('CLOUDINARY_API_SECRET')
                
                if cloudinary_cloud_name and cloudinary_api_key and cloudinary_api_secret:
                    cloudinary.config(
                        cloud_name=cloudinary_cloud_name,
                        api_key=cloudinary_api_key,
                        api_secret=cloudinary_api_secret
                    )
                    upload_result = cloudinary.uploader.upload(
                        logo,
                        folder="thriveos/logos",
                        public_id=f"business_{int(time.time())}",
                        overwrite=True
                    )
                    logo_url = upload_result['secure_url']
                    cloudinary_public_id = upload_result['public_id']
            
            # Insert user into database with ADMIN role
            user_data = {
                'email': email,
                'password_hash': password_hash,
                'first_name': first_name,
                'last_name': last_name,
                'otp_secret': otp_secret,
                'otp_expiry': (get_utc_now() + timedelta(minutes=10)).isoformat(),
                'created_at': get_utc_now().isoformat(),
                'role': 'admin',  # Set default role as admin for business registrant
                'is_admin': True  # Set admin flag
            }
            
            user_response = supabase.table('users').insert(user_data).execute()
            
            if user_response.data:
                user_id = user_response.data[0]['id']
                
                # Create business profile
                business_data = {
                    'user_id': user_id,
                    'business_name': business_name,
                    'logo_url': logo_url,
                    'cloudinary_public_id': cloudinary_public_id,
                    'created_at': get_utc_now().isoformat()
                }
                supabase.table('businesses').insert(business_data).execute()
                
                # Send OTP email
                send_email_async(
                    email,
                    "Verify Your Email Address",
                    generate_otp_email_html(otp_code, first_name)
                )
                
                # Set session for verification (temporary)
                session['verify_email'] = email
                session['user_id_temp'] = user_id
                
                processing_time = round((time.time() - start_time) * 1000, 2)
                print(f"✅ Registration completed for {email} in {processing_time}ms")
                
                flash(f'Registration successful! Verification code sent to your email. ({processing_time}ms)', 'success')
                return redirect(url_for('auth.verify_email'))
            
        except Exception as e:
            print(f"❌ Registration error: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'error')
        
        return render_template('auth/register.html')
    
    return render_template('auth/register.html')
@auth_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    if 'verify_email' not in session and 'user_id_temp' not in session:
        flash('Please register first', 'error')
        return redirect(url_for('auth.register'))
    
    if request.method == 'POST':
        otp_code = request.form.get('otp', '').strip()
        email = session.get('verify_email')
        user_id = session.get('user_id_temp')
        
        print(f"\n🔍 VERIFICATION ATTEMPT:")
        print(f"   Email: {email}")
        print(f"   User ID: {user_id}")
        print(f"   OTP entered: {otp_code}")
        
        if not otp_code or len(otp_code) != 6:
            print("❌ Invalid OTP format")
            flash('Please enter a valid 6-digit OTP', 'error')
            return render_template('auth/verify_email.html')
        
        try:
            supabase = get_supabase()
            
            # Get user OTP secret with role information
            print(f"📊 Fetching user data from database...")
            user_response = supabase.table('users').select(
                'otp_secret,otp_expiry,email_verified,first_name,last_name,role,is_admin'
            ).eq('id', user_id).limit(1).execute()
            
            if not user_response.data:
                print("❌ User not found in database")
                flash('User not found. Please register again.', 'error')
                return redirect(url_for('auth.register'))
            
            user = user_response.data[0]
            print(f"✅ User found: {user.get('first_name', 'No name')}")
            print(f"   Role: {user.get('role', 'Not set')}")
            print(f"   Is Admin: {user.get('is_admin', False)}")
            print(f"   OTP Secret: {user['otp_secret'][:8]}... (first 8 chars)")
            print(f"   Already verified? {user.get('email_verified', False)}")
            
            # Check if OTP expired
            otp_expiry = parse_iso_datetime(user['otp_expiry'])
            current_time = get_utc_now()
            
            if not otp_expiry:
                print("❌ OTP expiry time not found")
                flash('OTP expiry time not found. Please request a new OTP.', 'error')
                return render_template('auth/verify_email.html')
            
            print(f"⏰ OTP expiry: {otp_expiry}")
            print(f"⏰ Current time: {current_time}")
            print(f"⏰ Time difference: {(otp_expiry - current_time).total_seconds():.0f} seconds")
            
            if otp_expiry < current_time:
                print("❌ OTP has expired")
                flash('OTP has expired. Please request a new one.', 'error')
                return render_template('auth/verify_email.html')
            
            # Generate current OTP for debugging
            totp = pyotp.TOTP(user['otp_secret'])
            current_valid_otp = totp.now()
            print(f"🔑 Current valid OTP should be: {current_valid_otp}")
            
            # Also show OTPs in valid window
            print(f"\n🔍 OTPs in valid window (current ±30 seconds):")
            for i in range(-1, 2):
                time_offset = current_time + timedelta(seconds=i*30)
                otp_at_time = totp.at(time_offset.timestamp())
                indicator = "← CURRENT" if i == 0 else ""
                print(f"   {i*30:+3d} seconds: {otp_at_time} {indicator}")
            
            # Verify OTP
            print(f"\n✅ Verifying OTP '{otp_code}'...")
            is_valid = totp.verify(otp_code, valid_window=1)
            print(f"   Verification result: {is_valid}")
            
            if is_valid:
                print("🎉 OTP VERIFIED SUCCESSFULLY!")
                
                # Prepare update data
                update_data = {
                    'email_verified': True,
                    'otp_secret': None,
                    'otp_expiry': None,
                    'verified_at': get_utc_now().isoformat()
                }
                
                print(f"📝 Updating user in database...")
                result = supabase.table('users').update(update_data).eq('id', user_id).execute()
                print(f"   Database update successful: {bool(result.data)}")
                
                # Clear temporary session data
                session.pop('verify_email', None)
                session.pop('user_id_temp', None)
                
                # Set full user session with role information
                session['user_id'] = user_id
                session['user_email'] = email
                session['user_name'] = user.get('first_name', '')
                session['user_full_name'] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                session['user_role'] = user.get('role', 'user')
                session['is_admin'] = user.get('is_admin', False)
                
                print(f"\n📱 SESSION SETUP COMPLETE:")
                print(f"   user_id: {session.get('user_id')}")
                print(f"   user_email: {session.get('user_email')}")
                print(f"   user_name: {session.get('user_name')}")
                print(f"   user_role: {session.get('user_role')}")
                print(f"   is_admin: {session.get('is_admin')}")
                
                # Log successful verification
                try:
                    supabase.table('auth_logs').insert({
                        'user_id': user_id,
                        'ip_address': request.remote_addr,
                        'user_agent': request.user_agent.string,
                        'action': 'email_verification',
                        'status': 'success',
                        'created_at': get_utc_now().isoformat()
                    }).execute()
                    print("📝 Verification logged in auth_logs")
                except Exception as log_error:
                    print(f"⚠️ Failed to log verification: {str(log_error)}")
                
                flash('🎉 Email verified successfully! Welcome to ThriveOS.', 'success')
                return redirect(url_for('dashboard'))
            else:
                print("❌ OTP verification failed")
                
                # Log failed verification attempt
                try:
                    supabase.table('auth_logs').insert({
                        'user_id': user_id,
                        'ip_address': request.remote_addr,
                        'user_agent': request.user_agent.string,
                        'action': 'email_verification',
                        'status': 'failed',
                        'details': json.dumps({'otp_attempt': otp_code}),
                        'created_at': get_utc_now().isoformat()
                    }).execute()
                except Exception as log_error:
                    print(f"⚠️ Failed to log failed attempt: {str(log_error)}")
                
                flash('Invalid verification code. Please try again.', 'error')
                
        except Exception as e:
            print(f"❌ OTP verification error: {str(e)}")
            import traceback
            traceback.print_exc()
            flash('An error occurred. Please try again.', 'error')
        
        return render_template('auth/verify_email.html')
    
    # GET request - show verification page
    email = session.get('verify_email', 'your email')
    user_id = session.get('user_id_temp')
    
    print(f"\n📄 Showing verification page for:")
    print(f"   Email: {email}")
    print(f"   User ID: {user_id}")
    
    # Check if user is already verified (prevent re-verification)
    if user_id:
        try:
            supabase = get_supabase()
            user_response = supabase.table('users').select('email_verified').eq('id', user_id).limit(1).execute()
            if user_response.data and user_response.data[0].get('email_verified'):
                print("⚠️ User already verified, redirecting to dashboard")
                flash('Your email is already verified. Please login.', 'info')
                return redirect(url_for('auth.login'))
        except Exception as e:
            print(f"⚠️ Error checking verification status: {str(e)}")
    
    return render_template('auth/verify_email.html')

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('verify_email')
    user_id = session.get('user_id_temp')
    
    print(f"\n🔄 RESEND OTP REQUEST:")
    print(f"   Email: {email}")
    print(f"   User ID: {user_id}")
    
    if not email or not user_id:
        print("❌ No email or user_id in session")
        return jsonify({'success': False, 'message': 'Session expired. Please register again.'})
    
    try:
        supabase = get_supabase()
        
        # First, get user's first name for personalized email
        user_response = supabase.table('users').select('first_name').eq('id', user_id).limit(1).execute()
        first_name = user_response.data[0].get('first_name', '') if user_response.data else ''
        
        # Generate new OTP
        otp_secret = pyotp.random_base32()
        otp = pyotp.TOTP(otp_secret)
        otp_code = otp.now()
        
        # Update user with new OTP
        update_result = supabase.table('users').update({
            'otp_secret': otp_secret,
            'otp_expiry': (get_utc_now() + timedelta(minutes=10)).isoformat()
        }).eq('id', user_id).execute()
        
        print(f"✅ New OTP generated: {otp_code}")
        print(f"   OTP Secret (first 8): {otp_secret[:8]}...")
        print(f"   Database update successful: {bool(update_result.data)}")
        
        # Send new OTP email with personalized content
        send_email_async(
            email,
            "Your New Verification Code - ThriveOS",
            generate_otp_email_html(otp_code, first_name)
        )
        
        print(f"📧 OTP email sent to {email}")
        
        # Log OTP resend
        try:
            supabase.table('auth_logs').insert({
                'user_id': user_id,
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string,
                'action': 'otp_resend',
                'status': 'success',
                'created_at': get_utc_now().isoformat()
            }).execute()
            print("📝 OTP resend logged in auth_logs")
        except Exception as log_error:
            print(f"⚠️ Failed to log OTP resend: {str(log_error)}")
        
        return jsonify({
            'success': True, 
            'message': 'A new verification code has been sent to your email!'
        })
        
    except Exception as e:
        print(f"❌ Resend OTP error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Log failed resend attempt
        try:
            supabase = get_supabase()
            supabase.table('auth_logs').insert({
                'user_id': user_id,
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string,
                'action': 'otp_resend',
                'status': 'failed',
                'details': json.dumps({'error': str(e)}),
                'created_at': get_utc_now().isoformat()
            }).execute()
        except Exception as log_error:
            print(f"⚠️ Failed to log failed resend: {str(log_error)}")
        
        return jsonify({
            'success': False, 
            'message': 'Failed to send new verification code. Please try again.'
        })
        
        
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address', 'error')
            return render_template('auth/forgot_password.html')
        
        try:
            supabase = get_supabase()
            
            # Check if user exists
            user_response = supabase.table('users').select('id,first_name').eq('email', email).limit(1).execute()
            
            if user_response.data:
                user = user_response.data[0]
                
                # Generate secure reset token
                reset_token = secrets.token_urlsafe(64)
                reset_expiry = (get_utc_now() + timedelta(hours=1)).isoformat()
                
                # Update user with reset token
                supabase.table('users').update({
                    'reset_token': reset_token,
                    'reset_token_expiry': reset_expiry
                }).eq('id', user['id']).execute()
                
                # Create reset link
                app_url = get_config_value('APP_URL', 'http://localhost:5000')
                reset_link = f"{app_url}/auth/reset-password/{reset_token}"
                
                # Send password reset email
                reset_email_html = f"""
                <!DOCTYPE html>
                <html>
                <body>
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #dc2626;">Password Reset Request</h2>
                        <p>Hello{'' if not user['first_name'] else ' ' + user['first_name']},</p>
                        <p>We received a request to reset your password for your ThriveOS account.</p>
                        <p>Click the link below to reset your password:</p>
                        <p><a href="{reset_link}" style="background: #dc2626; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Reset Password</a></p>
                        <p>This link will expire in 1 hour.</p>
                        <p>If you didn't request this, please ignore this email.</p>
                        <p>Best regards,<br>The ThriveOS Team</p>
                    </div>
                </body>
                </html>
                """
                
                send_email_async(
                    email,
                    "Password Reset Request",
                    reset_email_html
                )
                
                flash('Password reset instructions have been sent to your email.', 'success')
            else:
                # Still show success for security (don't reveal if email exists)
                flash('If an account exists with this email, reset instructions have been sent.', 'info')
            
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            print(f"❌ Forgot password error: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
        
        return render_template('auth/forgot_password.html')
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        supabase = get_supabase()
        
        # Verify token
        user_response = supabase.table('users').select('id,reset_token_expiry').eq('reset_token', token).limit(1).execute()
        
        if not user_response.data:
            print(f"❌ Invalid reset token: {token}")
            flash('Invalid or expired reset token.', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        user = user_response.data[0]
        
        # Check if token expired
        token_expiry = parse_iso_datetime(user['reset_token_expiry'])
        current_time = get_utc_now()
        
        if not token_expiry:
            print(f"❌ No expiry date for token: {token}")
            flash('Token expiry time not found. Please request a new reset link.', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        print(f"🔍 Token expiry: {token_expiry}")
        print(f"🔍 Current time: {current_time}")
        print(f"🔍 Is token expired? {token_expiry < current_time}")
        
        if token_expiry < current_time:
            print(f"❌ Token expired: {token}")
            flash('Reset token has expired. Please request a new one.', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        if request.method == 'POST':
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            print(f"🔍 Password reset attempt for user {user['id']}")
            print(f"   Password provided: {'Yes' if password else 'No'}")
            print(f"   Confirm password: {'Yes' if confirm_password else 'No'}")
            
            if not password or not confirm_password:
                flash('Please fill in all fields', 'error')
                return render_template('auth/reset_password.html', token=token)
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('auth/reset_password.html', token=token)
            
            if len(password) < 8:
                flash('Password must be at least 8 characters long', 'error')
                return render_template('auth/reset_password.html', token=token)
            
            # Update password and clear reset token
            password_hash = generate_password_hash(password)
            
            print(f"📝 Updating password for user {user['id']}...")
            
            update_result = supabase.table('users').update({
                'password_hash': password_hash,
                'reset_token': None,
                'reset_token_expiry': None,
                'updated_at': get_utc_now().isoformat()
            }).eq('id', user['id']).execute()
            
            print(f"✅ Password update result: {update_result.data}")
            
            if update_result.data:
                # Log password reset
                supabase.table('auth_logs').insert({
                    'user_id': user['id'],
                    'ip_address': request.remote_addr,
                    'user_agent': request.user_agent.string,
                    'action': 'password_reset',
                    'status': 'success',
                    'created_at': get_utc_now().isoformat()
                }).execute()
                
                print(f"✅ Password reset successful for user {user['id']}")
                flash('Password reset successful! Please login with your new password.', 'success')
                return redirect(url_for('auth.login'))
            else:
                print(f"❌ Failed to update password for user {user['id']}")
                flash('Failed to reset password. Please try again.', 'error')
                return render_template('auth/reset_password.html', token=token)
        
        # GET request - show reset form
        print(f"✅ Showing reset form for valid token: {token}")
        return render_template('auth/reset_password.html', token=token)
        
    except Exception as e:
        print(f"❌ Reset password error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    
@auth_bp.route('/logout')
def logout():
    if 'user_id' in session:
        try:
            supabase = get_supabase()
            supabase.table('auth_logs').insert({
                'user_id': session['user_id'],
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string,
                'action': 'logout',
                'status': 'success',
                'created_at': get_utc_now().isoformat()
            }).execute()
        except Exception as e:
            print(f"❌ Logout logging error: {str(e)}")
    
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))