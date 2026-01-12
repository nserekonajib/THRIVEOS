from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from routes.auth import login_required
from datetime import datetime
import uuid
from supabase import create_client
from config import Config

# Create Supabase client
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

customers_bp = Blueprint('customers', __name__)

@customers_bp.route('/customers')
@login_required
def customers_list():
    """Display list of customers with their details"""
    try:
        # Fetch sales data where customer details exist
        response = supabase.table('sales')\
            .select('*')\
            .order('created_at', desc=True)\
            .execute()
        
        # Filter to get unique customers based on available contact info
        customers_map = {}
        for sale in response.data:
            # Skip if no customer info at all
            if not sale.get('customer_name') and not sale.get('customer_phone') and not sale.get('customer_email'):
                continue
            
            # Create a unique key based on available contact info
            customer_key = None
            if sale.get('customer_phone'):
                customer_key = sale.get('customer_phone')
            elif sale.get('customer_email'):
                customer_key = sale.get('customer_email')
            elif sale.get('customer_name'):
                customer_key = sale.get('customer_name')
            
            if customer_key and customer_key not in customers_map:
                customers_map[customer_key] = {
                    'name': sale.get('customer_name', ''),
                    'phone': sale.get('customer_phone', ''),
                    'email': sale.get('customer_email', ''),
                    'total_spent': 0,
                    'total_transactions': 0,
                    'last_purchase': sale.get('created_at'),
                    'last_invoice': sale.get('invoice_number'),
                    'payment_status': sale.get('payment_status', 'pending')
                }
            
            # Update totals for existing customer
            if customer_key in customers_map:
                customers_map[customer_key]['total_spent'] += float(sale.get('total_amount', 0))
                customers_map[customer_key]['total_transactions'] += 1
                # Update last purchase if this is more recent
                if sale.get('created_at') and sale.get('created_at') > customers_map[customer_key]['last_purchase']:
                    customers_map[customer_key]['last_purchase'] = sale.get('created_at')
                    customers_map[customer_key]['last_invoice'] = sale.get('invoice_number')
                    customers_map[customer_key]['payment_status'] = sale.get('payment_status', 'pending')
        
        # Convert map to list for template
        customers = list(customers_map.values())
        
        # Calculate additional stats
        for customer in customers:
            # Format total spent
            customer['total_spent_formatted'] = f"UGX {customer['total_spent']:,.2f}"
            
            # Format last purchase date
            if customer['last_purchase']:
                last_purchase_dt = datetime.fromisoformat(customer['last_purchase'].replace('Z', '+00:00'))
                customer['last_purchase_formatted'] = last_purchase_dt.strftime('%b %d, %Y %I:%M %p')
            else:
                customer['last_purchase_formatted'] = 'N/A'
            
            # Determine status color
            status = customer.get('payment_status', 'pending').lower()
            if status == 'completed' or status == 'paid':
                customer['status_color'] = 'success'
            elif status == 'pending':
                customer['status_color'] = 'warning'
            elif status == 'failed' or status == 'cancelled':
                customer['status_color'] = 'danger'
            else:
                customer['status_color'] = 'secondary'
        
        return render_template('customers/list.html', 
                             customers=customers,
                             title="Customers")
    
    except Exception as e:
        flash(f'Error fetching customers: {str(e)}', 'danger')
        return render_template('customers/list.html', 
                             customers=[], 
                             title="Customers")

@customers_bp.route('/customers/<string:customer_identifier>')
@login_required
def customer_detail(customer_identifier):
    """Display detailed view of a customer and their transaction history"""
    try:
        # Find sales for this customer (by phone, email, or name)
        response = supabase.table('sales')\
            .select('*')\
            .or_(f'customer_phone.eq.{customer_identifier},customer_email.eq.{customer_identifier}')\
            .order('created_at', desc=True)\
            .execute()
        
        if not response.data:
            # Try by name if not found by phone/email
            response = supabase.table('sales')\
                .select('*')\
                .eq('customer_name', customer_identifier)\
                .order('created_at', desc=True)\
                .execute()
        
        if not response.data:
            flash('Customer not found', 'danger')
            return redirect(url_for('customers.customers_list'))
        
        # Get customer info from first sale
        first_sale = response.data[0]
        customer_info = {
            'name': first_sale.get('customer_name', 'Not Provided'),
            'phone': first_sale.get('customer_phone', 'Not Provided'),
            'email': first_sale.get('customer_email', 'Not Provided'),
            'total_sales': len(response.data),
            'total_spent': 0,
            'average_spent': 0
        }
        
        # Process all sales
        sales = []
        for sale in response.data:
            # Calculate totals
            customer_info['total_spent'] += float(sale.get('total_amount', 0))
            
            # Format sale data
            sale_data = {
                'invoice_number': sale.get('invoice_number'),
                'date': sale.get('created_at'),
                'subtotal': float(sale.get('subtotal', 0)),
                'tax': float(sale.get('tax_amount', 0)),
                'discount': float(sale.get('discount_amount', 0)),
                'total': float(sale.get('total_amount', 0)),
                'payment_method': sale.get('payment_method', 'N/A'),
                'payment_status': sale.get('payment_status', 'pending'),
                'notes': sale.get('notes', '')
            }
            
            # Format date
            if sale_data['date']:
                sale_dt = datetime.fromisoformat(sale_data['date'].replace('Z', '+00:00'))
                sale_data['date_formatted'] = sale_dt.strftime('%b %d, %Y %I:%M %p')
            else:
                sale_data['date_formatted'] = 'N/A'
            
            # Format amounts
            sale_data['subtotal_formatted'] = f"UGX {sale_data['subtotal']:,.2f}"
            sale_data['tax_formatted'] = f"UGX {sale_data['tax']:,.2f}"
            sale_data['discount_formatted'] = f"UGX {sale_data['discount']:,.2f}"
            sale_data['total_formatted'] = f"UGX {sale_data['total']:,.2f}"
            
            # Set status color
            status = sale_data['payment_status'].lower()
            if status == 'completed' or status == 'paid':
                sale_data['status_color'] = 'success'
            elif status == 'pending':
                sale_data['status_color'] = 'warning'
            elif status == 'failed' or status == 'cancelled':
                sale_data['status_color'] = 'danger'
            else:
                sale_data['status_color'] = 'secondary'
            
            sales.append(sale_data)
        
        # Calculate average spent
        if customer_info['total_sales'] > 0:
            customer_info['average_spent'] = customer_info['total_spent'] / customer_info['total_sales']
        
        # Format amounts
        customer_info['total_spent_formatted'] = f"UGX {customer_info['total_spent']:,.2f}"
        customer_info['average_spent_formatted'] = f"UGX {customer_info['average_spent']:,.2f}"
        
        return render_template('customers/detail.html',
                             customer=customer_info,
                             sales=sales,
                             title=f"Customer: {customer_info['name']}")
    
    except Exception as e:
        flash(f'Error fetching customer details: {str(e)}', 'danger')
        return redirect(url_for('customers.customers_list'))

@customers_bp.route('/api/customers/stats')
@login_required
def customers_stats():
    """API endpoint for customer statistics"""
    try:
        response = supabase.table('sales')\
            .select('customer_name, customer_phone, customer_email, total_amount, payment_status, created_at')\
            .execute()
        
        stats = {
            'total_customers': 0,
            'active_customers': 0,
            'total_revenue': 0,
            'average_transaction': 0,
            'top_customers': []
        }
        
        customers_map = {}
        total_transactions = 0
        
        for sale in response.data:
            # Skip if no customer info
            if not sale.get('customer_name') and not sale.get('customer_phone') and not sale.get('customer_email'):
                continue
            
            customer_key = sale.get('customer_phone') or sale.get('customer_email') or sale.get('customer_name')
            
            if customer_key not in customers_map:
                customers_map[customer_key] = {
                    'name': sale.get('customer_name', ''),
                    'phone': sale.get('customer_phone', ''),
                    'email': sale.get('customer_email', ''),
                    'total_spent': 0,
                    'transactions': 0
                }
                stats['total_customers'] += 1
            
            customers_map[customer_key]['total_spent'] += float(sale.get('total_amount', 0))
            customers_map[customer_key]['transactions'] += 1
            stats['total_revenue'] += float(sale.get('total_amount', 0))
            total_transactions += 1
        
        # Calculate average transaction value
        if total_transactions > 0:
            stats['average_transaction'] = stats['total_revenue'] / total_transactions
        
        # Get top 5 customers by total spent
        top_customers = sorted(customers_map.values(), key=lambda x: x['total_spent'], reverse=True)[:5]
        stats['top_customers'] = top_customers
        
        # Count active customers (made purchase in last 30 days)
        thirty_days_ago = datetime.now().timestamp() - (30 * 24 * 60 * 60)
        for sale in response.data:
            if sale.get('created_at'):
                sale_time = datetime.fromisoformat(sale['created_at'].replace('Z', '+00:00')).timestamp()
                if sale_time > thirty_days_ago:
                    customer_key = sale.get('customer_phone') or sale.get('customer_email') or sale.get('customer_name')
                    if customer_key and customer_key in customers_map:
                        if 'active' not in customers_map[customer_key]:
                            customers_map[customer_key]['active'] = True
                            stats['active_customers'] += 1
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500