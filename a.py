# app.py
from flask import Flask, render_template, session, g, request, redirect, url_for
from datetime import datetime
import time
from routes.auth import auth_bp
import os
from dotenv import load_dotenv
from routes.userRolesPermissions import user_roles_bp
from routes.productsCategories import products_bp
from routes.salesTerminal import sales_bp
from routes.customers import customers_bp
from routes.expenses import expenses_bp
from routes.reports import reports_bp
from routes.dashboard import dashboard_bp
from routes.settings import settings_bp

load_dotenv()

app = Flask(__name__)

from datetime import datetime


def datetime_format(value, format='%Y-%m-%d %H:%M'):
    """Format a datetime object or ISO string"""
    if value is None:
        return ''
    

    if isinstance(value, datetime):
        return value.strftime(format)
    

    try:
 
        if isinstance(value, str):
            # Remove timezone info for parsing
            dt_str = value.replace('Z', '+00:00')
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime(format)
    except (ValueError, AttributeError):
        pass
    
    # Return original if can't parse
    return str(value)

# Register the filter with Jinja2
app.jinja_env.filters['datetime_format'] = datetime_format

try:
    from config import Config
    app.config.from_object(Config)
except ImportError:
    # Fallback to environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
    app.config['SUPABASE_URL'] = os.getenv('SUPABASE_URL')
    app.config['SUPABASE_KEY'] = os.getenv('SUPABASE_KEY')
    app.config['SUPABASE_SERVICE_KEY'] = os.getenv('SUPABASE_SERVICE_KEY')
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['CLOUDINARY_CLOUD_NAME'] = os.getenv('CLOUDINARY_CLOUD_NAME')
    app.config['CLOUDINARY_API_KEY'] = os.getenv('CLOUDINARY_API_KEY')
    app.config['CLOUDINARY_API_SECRET'] = os.getenv('CLOUDINARY_API_SECRET')
    app.config['APP_NAME'] = os.getenv('APP_NAME', 'ThriveOS')
    app.config['APP_URL'] = os.getenv('APP_URL', 'http://localhost:5000')
    app.config['PESAPAL_CONSUMER_KEY'] = os.getenv('PESAPAL_CONSUMER_KEY')
    app.config['PESAPAL_CONSUMER_SECRET'] = os.getenv('PESAPAL_CONSUMER_SECRET')
    app.config['PESAPAL_IPN_URL'] = os.getenv('PESAPAL_IPN_URL')




# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(user_roles_bp)
app.register_blueprint(products_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(customers_bp)
app.register_blueprint(expenses_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(settings_bp)


@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    """Format a datetime object or ISO string."""
    if value is None:
        return ''
    
    if isinstance(value, str):
        try:
            # Try to parse ISO format
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    
    if isinstance(value, datetime):
        return value.strftime(format)
    
    return str(value)
# Main landing page
@app.route('/')
def index():
    return render_template('index.html')

# Dashboard (placeholder)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return redirect(url_for('dashboard.dashboard'))

# Context processors
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Request timing middleware
@app.before_request
def before_request():
    g.start_time = time.time()
    # Inject performance stats for templates
    g.performance_mode = "high-speed"
    g.system_status = "operational"

@app.after_request
def after_request(response):
    if hasattr(g, 'start_time'):
        processing_time = round((time.time() - g.start_time) * 1000, 2)
        app.logger.info(f"{request.method} {request.path} - {response.status_code} - {processing_time}ms")
        response.headers['X-Processing-Time'] = str(processing_time)
        response.headers['X-ThriveOS-Version'] = '1.0.0'
        response.headers['X-Performance-Mode'] = 'turbo'
    return response

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal error: {str(error)}")
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    # Verify environment variables are loaded
    print("Starting ThriveOS...")
    print(f"App URL: {app.config.get('APP_URL')}")
    print(f"Supabase URL configured: {'Yes' if app.config.get('SUPABASE_URL') else 'No'}")
    print(f"Mail Server configured: {'Yes' if app.config.get('MAIL_SERVER') else 'No'}")
    
    from waitress import serve

    serve(app, host='0.0.0.0', port=5555)