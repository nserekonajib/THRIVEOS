from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session, make_response
from routes.auth import login_required
from datetime import datetime, date, timedelta
from decimal import Decimal
import uuid
from supabase import create_client
from config import Config
import io
from xhtml2pdf import pisa
import tempfile
import os
import json
import urllib.request
import ssl
import urllib.parse

# Create Supabase client
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

reports_bp = Blueprint('reports', __name__)

# Create a custom SSL context to ignore certificate verification for PDF generation
def create_ssl_context():
    """Create SSL context that ignores certificate verification for PDF generation"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context

def get_user_business_id():
    """Get the business_id for the current user from session or businesses table"""
    try:
        # First, check if business_id is already in session
        if 'business_id' in session:
            return session['business_id']
        
        # Get user_id from session
        user_id = session.get('user_id')
        if not user_id:
            return None
        
        # Try businesses table first
        response = supabase.table('businesses').select(
            'id, business_name, business_email, business_phone, address, city, country, logo_url'
        ).eq('user_id', user_id).limit(1).execute()
        
        if response.data:
            business = response.data[0]
            session['business_id'] = business['id']
            session['business_info'] = business  # Store full business info
            return business['id']
        
        return None
        
    except Exception as e:
        print(f"Error getting user business: {e}")
        return None

def get_business_info(business_id):
    """Get detailed business information"""
    try:
        response = supabase.table('businesses').select(
            'business_name, business_email, business_phone, address, city, country, logo_url'
        ).eq('id', business_id).limit(1).execute()
        
        if response.data:
            return response.data[0]
        return {
            'business_name': 'Your Business',
            'business_email': '',
            'business_phone': '',
            'address': '',
            'city': '',
            'country': '',
            'logo_url': None
        }
    except Exception as e:
        print(f"Error getting business info: {e}")
        return {
            'business_name': 'Your Business',
            'business_email': '',
            'business_phone': '',
            'address': '',
            'city': '',
            'country': '',
            'logo_url': None
        }

def get_sales_summary(business_id, start_date, end_date):
    """Get sales summary for the given period"""
    try:
        # Get sales data
        sales_response = supabase.table('sales').select(
            'invoice_number, customer_name, total_amount, tax_amount, discount_amount, subtotal, payment_status, created_at'
        ).eq('business_id', business_id)\
         .gte('created_at', start_date)\
         .lte('created_at', end_date)\
         .order('created_at', desc=True).execute()
        
        sales = sales_response.data if sales_response.data else []
        
        # Calculate totals
        total_sales = len(sales)
        total_revenue = sum(float(sale.get('total_amount', 0)) for sale in sales)
        total_tax = sum(float(sale.get('tax_amount', 0)) for sale in sales)
        total_discount = sum(float(sale.get('discount_amount', 0)) for sale in sales)
        total_subtotal = sum(float(sale.get('subtotal', 0)) for sale in sales)
        
        # Get payment status breakdown
        payment_statuses = {}
        for sale in sales:
            status = sale.get('payment_status', 'pending')
            amount = float(sale.get('total_amount', 0))
            if status not in payment_statuses:
                payment_statuses[status] = {'count': 0, 'amount': 0}
            payment_statuses[status]['count'] += 1
            payment_statuses[status]['amount'] += amount
        
        # Get daily sales trend
        daily_trend_response = supabase.table('sales').select(
            'created_at, total_amount'
        ).eq('business_id', business_id)\
         .gte('created_at', start_date)\
         .lte('created_at', end_date)\
         .execute()
        
        daily_trend = {}
        daily_counts = {}
        for sale in daily_trend_response.data if daily_trend_response.data else []:
            try:
                sale_date_str = sale['created_at']
                if isinstance(sale_date_str, str):
                    # Parse ISO date string
                    if 'T' in sale_date_str:
                        sale_date = datetime.fromisoformat(sale_date_str.replace('Z', '+00:00')).date()
                    else:
                        # Try parsing as simple date
                        sale_date = datetime.strptime(sale_date_str, '%Y-%m-%d').date()
                else:
                    # If it's already a date object
                    sale_date = sale_date_str
                
                amount = float(sale.get('total_amount', 0))
                date_key = sale_date.isoformat() if hasattr(sale_date, 'isoformat') else str(sale_date)
                
                if date_key not in daily_trend:
                    daily_trend[date_key] = 0
                    daily_counts[date_key] = 0
                
                daily_trend[date_key] += amount
                daily_counts[date_key] += 1
            except Exception as date_error:
                print(f"Error parsing date in sales: {date_error}")
                continue
        
        # Sort daily trend by date
        sorted_dates = sorted(daily_trend.keys())
        sorted_daily_trend = []
        for date_key in sorted_dates:
            sorted_daily_trend.append({
                'date': date_key,
                'amount': daily_trend[date_key],
                'count': daily_counts.get(date_key, 0)
            })
        
        return {
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_tax': total_tax,
            'total_discount': total_discount,
            'total_subtotal': total_subtotal,
            'payment_statuses': payment_statuses,
            'daily_trend': sorted_daily_trend,
            'sales_list': sales[-20:] if sales else [],  # Last 20 sales
            'average_sale': total_revenue / total_sales if total_sales > 0 else 0
        }
    
    except Exception as e:
        print(f"Error getting sales summary: {e}")
        return {
            'total_sales': 0,
            'total_revenue': 0,
            'total_tax': 0,
            'total_discount': 0,
            'total_subtotal': 0,
            'payment_statuses': {},
            'daily_trend': [],
            'sales_list': [],
            'average_sale': 0
        }

def get_expenses_summary(business_id, start_date, end_date):
    """Get expenses summary for the given period"""
    try:
        # Get expenses data
        expenses_response = supabase.table('expenses').select(
            'expense_date, vendor, description, category, amount, payment_method, status'
        ).eq('business_id', business_id)\
         .gte('expense_date', start_date)\
         .lte('expense_date', end_date)\
         .order('expense_date', desc=True).execute()
        
        expenses = expenses_response.data if expenses_response.data else []
        
        # Calculate totals
        total_expenses = len(expenses)
        total_amount = sum(float(expense.get('amount', 0)) for expense in expenses)
        
        # Get category breakdown
        categories = {}
        for expense in expenses:
            category = expense.get('category', 'Uncategorized')
            amount = float(expense.get('amount', 0))
            if category not in categories:
                categories[category] = {'count': 0, 'amount': 0}
            categories[category]['count'] += 1
            categories[category]['amount'] += amount
        
        # Get status breakdown
        statuses = {}
        for expense in expenses:
            status = expense.get('status', 'approved')
            amount = float(expense.get('amount', 0))
            if status not in statuses:
                statuses[status] = {'count': 0, 'amount': 0}
            statuses[status]['count'] += 1
            statuses[status]['amount'] += amount
        
        return {
            'total_expenses': total_expenses,
            'total_amount': total_amount,
            'categories': categories,
            'statuses': statuses,
            'expenses_list': expenses[-20:] if expenses else [],  # Last 20 expenses
            'average_expense': total_amount / total_expenses if total_expenses > 0 else 0
        }
    
    except Exception as e:
        print(f"Error getting expenses summary: {e}")
        return {
            'total_expenses': 0,
            'total_amount': 0,
            'categories': {},
            'statuses': {},
            'expenses_list': [],
            'average_expense': 0
        }

def get_profit_loss_summary(business_id, start_date, end_date):
    """Get profit and loss summary for the given period"""
    try:
        # Get sales summary
        sales_summary = get_sales_summary(business_id, start_date, end_date)
        
        # Get expenses summary
        expenses_summary = get_expenses_summary(business_id, start_date, end_date)
        
        # Calculate profit/loss
        total_revenue = sales_summary['total_revenue']
        total_expenses = expenses_summary['total_amount']
        gross_profit = total_revenue
        net_profit = gross_profit - total_expenses
        
        # Calculate profit margin
        profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'revenue': {
                'total': total_revenue,
                'average_sale': sales_summary['average_sale'],
                'total_sales': sales_summary['total_sales']
            },
            'expenses': {
                'total': total_expenses,
                'average_expense': expenses_summary['average_expense'],
                'total_expenses': expenses_summary['total_expenses']
            },
            'profit_loss': {
                'gross_profit': gross_profit,
                'net_profit': net_profit,
                'profit_margin': profit_margin
            },
            'sales_summary': sales_summary,
            'expenses_summary': expenses_summary
        }
    
    except Exception as e:
        print(f"Error getting profit/loss summary: {e}")
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'revenue': {
                'total': 0,
                'average_sale': 0,
                'total_sales': 0
            },
            'expenses': {
                'total': 0,
                'average_expense': 0,
                'total_expenses': 0
            },
            'profit_loss': {
                'gross_profit': 0,
                'net_profit': 0,
                'profit_margin': 0
            },
            'sales_summary': None,
            'expenses_summary': None
        }

@reports_bp.route('/reports')
@login_required
def reports_dashboard():
    """Reports dashboard showing different report options"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            flash('No business found for your account.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Get default date ranges
        today = date.today()
        first_day_of_month = today.replace(day=1)
        first_day_of_year = today.replace(month=1, day=1)
        
        return render_template('reports/dashboard.html',
                             title="Reports Dashboard",
                             today=today,
                             first_day_of_month=first_day_of_month,
                             first_day_of_year=first_day_of_year)
    
    except Exception as e:
        flash(f'Error loading reports dashboard: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@reports_bp.route('/reports/sales', methods=['GET', 'POST'])
@login_required
def sales_report():
    """Generate sales report"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            flash('No business found for your account.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_info = get_business_info(business_id)
        
        # Default to current month
        today = date.today()
        default_start = today.replace(day=1)
        default_end = today
        
        # Get date range from request
        start_date = request.args.get('start_date') or request.form.get('start_date') or default_start.strftime('%Y-%m-%d')
        end_date = request.args.get('end_date') or request.form.get('end_date') or default_end.strftime('%Y-%m-%d')
        
        # Get sales summary
        sales_summary = get_sales_summary(business_id, start_date, end_date)
        
        if not sales_summary or sales_summary['total_sales'] == 0:
            flash('No sales data found for the selected period.', 'info')
        
        if request.method == 'POST' and request.form.get('export') == 'pdf':
            return generate_sales_pdf(business_info, sales_summary, start_date, end_date)
        
        return render_template('reports/sales.html',
                             title="Sales Report",
                             business=business_info,
                             sales_summary=sales_summary,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        flash(f'Error generating sales report: {str(e)}', 'danger')
        return redirect(url_for('reports.reports_dashboard'))

@reports_bp.route('/reports/expenses', methods=['GET', 'POST'])
@login_required
def expenses_report():
    """Generate expenses report"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            flash('No business found for your account.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_info = get_business_info(business_id)
        
        # Default to current month
        today = date.today()
        default_start = today.replace(day=1)
        default_end = today
        
        # Get date range from request
        start_date = request.args.get('start_date') or request.form.get('start_date') or default_start.strftime('%Y-%m-%d')
        end_date = request.args.get('end_date') or request.form.get('end_date') or default_end.strftime('%Y-%m-%d')
        
        # Get expenses summary
        expenses_summary = get_expenses_summary(business_id, start_date, end_date)
        
        if not expenses_summary or expenses_summary['total_expenses'] == 0:
            flash('No expenses data found for the selected period.', 'info')
        
        if request.method == 'POST' and request.form.get('export') == 'pdf':
            return generate_expenses_pdf(business_info, expenses_summary, start_date, end_date)
        
        return render_template('reports/expenses.html',
                             title="Expenses Report",
                             business=business_info,
                             expenses_summary=expenses_summary,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        flash(f'Error generating expenses report: {str(e)}', 'danger')
        return redirect(url_for('reports.reports_dashboard'))

@reports_bp.route('/reports/profit-loss', methods=['GET', 'POST'])
@login_required
def profit_loss_report():
    """Generate profit and loss report"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            flash('No business found for your account.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_info = get_business_info(business_id)
        
        # Default to current month
        today = date.today()
        default_start = today.replace(day=1)
        default_end = today
        
        # Get date range from request
        start_date = request.args.get('start_date') or request.form.get('start_date') or default_start.strftime('%Y-%m-%d')
        end_date = request.args.get('end_date') or request.form.get('end_date') or default_end.strftime('%Y-%m-%d')
        
        # Get profit/loss summary
        profit_loss_summary = get_profit_loss_summary(business_id, start_date, end_date)
        
        if not profit_loss_summary or (profit_loss_summary['revenue']['total'] == 0 and profit_loss_summary['expenses']['total'] == 0):
            flash('No data found for the selected period.', 'info')
        
        if request.method == 'POST' and request.form.get('export') == 'pdf':
            return generate_profit_loss_pdf(business_info, profit_loss_summary)
        
        return render_template('reports/profit_loss.html',
                             title="Profit & Loss Report",
                             business=business_info,
                             profit_loss_summary=profit_loss_summary,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        flash(f'Error generating profit/loss report: {str(e)}', 'danger')
        return redirect(url_for('reports.reports_dashboard'))

@reports_bp.route('/api/reports/sales-summary')
@login_required
def api_sales_summary():
    """API endpoint for sales summary data"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        # Get date range
        start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
        
        sales_summary = get_sales_summary(business_id, start_date, end_date)
        
        if not sales_summary:
            return jsonify({'error': 'No data found'}), 404
        
        return jsonify(sales_summary)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/api/reports/expenses-summary')
@login_required
def api_expenses_summary():
    """API endpoint for expenses summary data"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        # Get date range
        start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
        
        expenses_summary = get_expenses_summary(business_id, start_date, end_date)
        
        if not expenses_summary:
            return jsonify({'error': 'No data found'}), 404
        
        return jsonify(expenses_summary)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/api/reports/profit-loss-summary')
@login_required
def api_profit_loss_summary():
    """API endpoint for profit/loss summary data"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        # Get date range
        start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
        
        profit_loss_summary = get_profit_loss_summary(business_id, start_date, end_date)
        
        if not profit_loss_summary:
            return jsonify({'error': 'No data found'}), 404
        
        return jsonify(profit_loss_summary)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def format_currency(amount):
    """Format amount as currency"""
    try:
        return f"UGX {float(amount):,.2f}"
    except:
        return f"UGX 0.00"

def format_date(date_str):
    """Format date string"""
    try:
        if isinstance(date_str, str):
            if 'T' in date_str:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d/%m/%Y')
        return str(date_str)
    except:
        return str(date_str)

def fetch_image_data_uri(url):
    """Fetch image and convert to data URI for PDF generation"""
    if not url:
        return None
    
    try:
        # Create SSL context that ignores certificate verification
        ssl_context = create_ssl_context()
        
        # Try to fetch the image
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
            image_data = response.read()
            
        # Get content type
        content_type = response.info().get('Content-Type', 'image/jpeg')
        
        # Convert to data URI
        import base64
        encoded = base64.b64encode(image_data).decode('ascii')
        return f"data:{content_type};base64,{encoded}"
    
    except Exception as e:
        print(f"Error fetching image {url}: {e}")
        return None

def generate_sales_pdf(business_info, sales_summary, start_date, end_date):
    """Generate PDF for sales report"""
    try:
        # Convert logo URL to data URI if it exists
        logo_data_uri = None
        if business_info and business_info.get('logo_url'):
            logo_data_uri = fetch_image_data_uri(business_info['logo_url'])
        
        # Create HTML content for PDF
        html_content = render_template('reports/pdf/sales_pdf.html',
                                      business=business_info,
                                      sales_summary=sales_summary,
                                      start_date=start_date,
                                      end_date=end_date,
                                      format_currency=format_currency,
                                      format_date=format_date,
                                      generated_date=datetime.now(),
                                      logo_data_uri=logo_data_uri)
        
        # Create PDF
        pdf = generate_pdf(html_content)
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=sales_report_{date.today()}.pdf'
        
        return response
    
    except Exception as e:
        print(f"Error generating sales PDF: {e}")
        flash(f'Error generating PDF: {str(e)}', 'danger')
        return redirect(url_for('reports.sales_report'))

def generate_expenses_pdf(business_info, expenses_summary, start_date, end_date):
    """Generate PDF for expenses report"""
    try:
        # Convert logo URL to data URI if it exists
        logo_data_uri = None
        if business_info and business_info.get('logo_url'):
            logo_data_uri = fetch_image_data_uri(business_info['logo_url'])
        
        # Create HTML content for PDF
        html_content = render_template('reports/pdf/expenses_pdf.html',
                                      business=business_info,
                                      expenses_summary=expenses_summary,
                                      start_date=start_date,
                                      end_date=end_date,
                                      format_currency=format_currency,
                                      format_date=format_date,
                                      generated_date=datetime.now(),
                                      logo_data_uri=logo_data_uri)
        
        # Create PDF
        pdf = generate_pdf(html_content)
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=expenses_report_{date.today()}.pdf'
        
        return response
    
    except Exception as e:
        print(f"Error generating expenses PDF: {e}")
        flash(f'Error generating PDF: {str(e)}', 'danger')
        return redirect(url_for('reports.expenses_report'))

def generate_profit_loss_pdf(business_info, profit_loss_summary):
    """Generate PDF for profit/loss report"""
    try:
        # Convert logo URL to data URI if it exists
        logo_data_uri = None
        if business_info and business_info.get('logo_url'):
            logo_data_uri = fetch_image_data_uri(business_info['logo_url'])
        
        # Create HTML content for PDF
        html_content = render_template('reports/pdf/profit_loss_pdf.html',
                                      business=business_info,
                                      profit_loss_summary=profit_loss_summary,
                                      format_currency=format_currency,
                                      format_date=format_date,
                                      generated_date=datetime.now(),
                                      logo_data_uri=logo_data_uri)
        
        # Create PDF
        pdf = generate_pdf(html_content)
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=profit_loss_report_{date.today()}.pdf'
        
        return response
    
    except Exception as e:
        print(f"Error generating profit/loss PDF: {e}")
        flash(f'Error generating PDF: {str(e)}', 'danger')
        return redirect(url_for('reports.profit_loss_report'))

def generate_pdf(html_content):
    """Generate PDF from HTML content"""
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            temp_pdf_path = tmp_file.name
        
        # Generate PDF with SSL context that ignores certificate verification
        ssl_context = create_ssl_context()
        
        with open(temp_pdf_path, 'w+b') as result_file:
            pisa_status = pisa.CreatePDF(
                html_content,
                dest=result_file,
                encoding='UTF-8',
                link_callback=None,
                default_css='''
                    img { max-height: 50px; }
                    @page { margin: 20mm; }
                '''
            )
        
        # Read the PDF content
        with open(temp_pdf_path, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
        
        # Clean up temporary file
        os.unlink(temp_pdf_path)
        
        return pdf_content
    
    except Exception as e:
        print(f"Error generating PDF: {e}")
        raise

# Helper functions for templates
@reports_bp.app_template_filter('currency')
def currency_filter(amount):
    """Currency filter for templates"""
    return format_currency(amount)

@reports_bp.app_template_filter('date_format')
def date_format_filter(date_str):
    """Date format filter for templates"""
    return format_date(date_str)

@reports_bp.app_template_filter('percentage')
def percentage_filter(value):
    """Percentage filter for templates"""
    try:
        return f"{float(value):.1f}%"
    except:
        return "0.0%"