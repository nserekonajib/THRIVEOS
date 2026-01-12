# routes/sales.py (Simplified without AJAX)
import concurrent
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, current_app
from functools import cache, wraps
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
import uuid
import time
from urllib.parse import quote

from routes.auth import get_utc_now, role_required, get_supabase
from config import Config
from pesapal import PesaPal
from functools import lru_cache
from datetime import datetime, timedelta
import concurrent.futures
import concurrent.futures
import asyncio
import functools
from datetime import datetime, date, timedelta
from functools import lru_cache
import threading

sales_bp = Blueprint('sales_terminal', __name__, url_prefix='/sales-terminal')

# Sales access decorator
def sales_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('auth.login'))
        
        user_role = session.get('user_role', 'employee')
        allowed_roles = ['admin', 'manager', 'cashier', 'sales', 'employee']
        
        if user_role not in allowed_roles:
            flash('Sales access required', 'error')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


class MemoryCache:
    def __init__(self):
        self._cache = {}
    
    def get(self, key):
        """Get cached data if not expired"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(minutes=5):
                return data
            else:
                del self._cache[key]
        return None
    
    def set(self, key, data, timeout=300):
        """Cache data with expiration"""
        self._cache[key] = (data, datetime.now())

# Initialize cache
memory_cache = MemoryCache()

# Utility functions

# Helper function for template
def get_avatar_color(user_id):
    """Generate consistent avatar color based on user ID"""
    if not user_id:
        return 'bg-gray-200 text-gray-700'
    
    # Simple hash for color selection
    colors = [
        'bg-red-200 text-red-700',
        'bg-blue-200 text-blue-700',
        'bg-green-200 text-green-700',
        'bg-yellow-200 text-yellow-700',
        'bg-purple-200 text-purple-700',
        'bg-pink-200 text-pink-700',
        'bg-indigo-200 text-indigo-700',
        'bg-teal-200 text-teal-700'
    ]
    
    # Simple hash
    hash_val = sum(ord(c) for c in str(user_id))
    return colors[hash_val % len(colors)]

def get_action_badge_class(action):
    """Get CSS class for action badge"""
    action_classes = {
        'login': 'bg-green-100 text-green-800',
        'logout': 'bg-gray-100 text-gray-800',
        'sale': 'bg-blue-100 text-blue-800',
        'refund': 'bg-red-100 text-red-800',
        'create': 'bg-green-100 text-green-800',
        'update': 'bg-yellow-100 text-yellow-800',
        'delete': 'bg-red-100 text-red-800',
        'security': 'bg-purple-100 text-purple-800',
        'system': 'bg-indigo-100 text-indigo-800'
    }
    return action_classes.get(action, 'bg-gray-100 text-gray-800')


def calculate_cart_totals(cart):
    """Calculate cart totals including tax"""
    subtotal = Decimal('0')
    tax_total = Decimal('0')
    
    for item in cart.values():
        quantity = Decimal(str(item['quantity']))
        price = Decimal(str(item['price']))
        tax_rate = Decimal(str(item.get('tax_rate', 0)))
        
        item_subtotal = quantity * price
        subtotal += item_subtotal
        
        if tax_rate > 0:
            item_tax = item_subtotal * (tax_rate / Decimal('100'))
            tax_total += item_tax
    
    total = subtotal + tax_total
    
    return {
        'subtotal': float(subtotal),
        'tax_total': float(tax_total),
        'total': float(total)
    }

def generate_invoice_number(supabase, business_id):
    """Generate unique invoice number"""
    today = datetime.now()
    date_str = today.strftime("%Y%m%d")
    
    start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    
    response = supabase.table('sales') \
        .select('id', count='exact') \
        .eq('business_id', business_id) \
        .gte('created_at', start_of_day) \
        .lte('created_at', end_of_day) \
        .execute()
    
    invoice_count = response.count or 0
    sequence = invoice_count + 1
    
    return f"INV-{date_str}-{sequence:04d}"


def handle_cart_operation(action, supabase, business_id):
    """Handle cart operations efficiently"""
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    cart = session.get('cart', {})
    
    if action == 'clear_cart':
        session['cart'] = {}
        session.modified = True
        flash('Cart cleared', 'success')
        return redirect(url_for('sales_terminal.terminal'))
    
    # For add/update, first check if product exists in cache
    cache_key = f'product_{product_id}_{business_id}'
    product_data = memory_cache.get(cache_key)
    
    if not product_data:
        # Fetch product with minimal fields
        product_response = supabase.table('products') \
            .select('id, name, selling_price, tax_rate, unit') \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .eq('is_active', True) \
            .single() \
            .execute()
        
        if not product_response.data:
            flash('Product not found or inactive', 'error')
            return redirect(url_for('sales_terminal.terminal'))
        
        product = product_response.data
        product_data = {
            'id': product['id'],
            'name': product['name'],
            'price': float(product['selling_price']),
            'tax_rate': float(product.get('tax_rate', 0)),
            'unit': product.get('unit', '')
        }
        memory_cache.set(cache_key, product_data, timeout=300)
    
    # Check stock only when adding new items or increasing quantity
    if action == 'add_to_cart' or (action == 'update_cart' and product_id in cart):
        current_qty = cart.get(product_id, {}).get('quantity', 0)
        new_qty = current_qty + quantity if action == 'add_to_cart' else quantity
        
        if new_qty > current_qty:  # Only check stock if increasing quantity
            stock = get_product_stock_fast(supabase, product_id)
            
            if new_qty > stock:
                flash(f'Insufficient stock. Only {stock} available.', 'error')
                return redirect(url_for('sales_terminal.terminal'))
    
    # Update cart
    if action == 'add_to_cart':
        if product_id in cart:
            cart[product_id]['quantity'] += quantity
        else:
            cart[product_id] = {
                **product_data,
                'quantity': quantity
            }
        flash(f'Added {quantity} {product_data["name"]} to cart', 'success')
    
    elif action == 'update_cart':
        if quantity <= 0 and product_id in cart:
            del cart[product_id]
            flash('Item removed from cart', 'success')
        elif product_id in cart:
            cart[product_id]['quantity'] = quantity
            flash('Cart updated', 'success')
    
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('sales_terminal.terminal'))

def get_product_stock_fast(supabase, product_id):
    """Fast stock check using aggregated query"""
    try:
        # Use single aggregation query
        stock_response = supabase.table('product_lots') \
            .select('quantity') \
            .eq('product_id', product_id) \
            .execute()
        
        return sum(lot['quantity'] for lot in (stock_response.data or []))
    except:
        return 0

def fetch_categories(supabase, business_id):
    """Fetch categories with caching"""
    cache_key = f'categories_{business_id}'
    categories = memory_cache.get(cache_key)
    
    if not categories:
        response = supabase.table('categories') \
            .select('id, name') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        categories = response.data if response.data else []
        memory_cache.set(cache_key, categories, timeout=3600)  # Cache for 1 hour
    
    return categories

def fetch_products_with_stock(supabase, business_id):
    from datetime import datetime
    """Fetch products with stock in a single optimized query"""
    cache_key = f'products_stock_{business_id}_{datetime.now().strftime("%Y%m%d%H")}'
    products = memory_cache.get(cache_key)
    
    if products:
        return products
    
    try:
        # Use a single query with aggregation for better performance
        from datetime import datetime, timedelta
        
        # Get products and categories in one go
        products_response = supabase.rpc(
    'get_product_with_stock',
    {
        'p_business_id': business_id,
        'p_product_id': None
    }
).execute()
        
        # If RPC not available, fall back to optimized query
        if not products_response.data:
            # Get all active products
            products_query = supabase.table('products') \
                .select('id, name, sku, barcode, selling_price, tax_rate, unit, image_url, reorder_level, category_id') \
                .eq('business_id', business_id) \
                .eq('is_active', True) \
                .order('name') \
                .execute()
            
            products_data = products_query.data if products_query.data else []
            
            # Get stock for all products in one query
            product_ids = [p['id'] for p in products_data]
            
            # Use IN query for better performance
            stock_response = supabase.table('product_lots') \
                .select('product_id, quantity') \
                .in_('product_id', product_ids[:100])\
                .execute()
            
            # Create stock dictionary
            stock_dict = {}
            if stock_response.data:
                for lot in stock_response.data:
                    stock_dict.setdefault(lot['product_id'], 0)
                    stock_dict[lot['product_id']] += lot['quantity']
            
            # Get category names in batch
            category_ids = [p['category_id'] for p in products_data if p.get('category_id')]
            categories_dict = {}
            if category_ids:
                cats_response = supabase.table('categories') \
                    .select('id, name') \
                    .in_('id', list(set(category_ids))) \
                    .execute()
                
                if cats_response.data:
                    categories_dict = {cat['id']: cat['name'] for cat in cats_response.data}
            
            # Build products list
            products = []
            for product in products_data:
                stock = stock_dict.get(product['id'], 0)
                category_name = categories_dict.get(product.get('category_id'), "Uncategorized")
                
                products.append({
                    'id': product['id'],
                    'name': product['name'],
                    'sku': product.get('sku'),
                    'barcode': product.get('barcode'),
                    'selling_price': float(product['selling_price']),
                    'tax_rate': float(product.get('tax_rate', 0)),
                    'unit': product.get('unit'),
                    'image_url': product.get('image_url'),
                    'reorder_level': product.get('reorder_level', 0),
                    'stock': stock,
                    'available': stock > 0,
                    'category_name': category_name
                })
        else:
            # Use RPC result
            products = products_response.data
        
        # Cache results
        memory_cache.set(cache_key, products, timeout=300)  # 5 minutes cache
        
        return products
    
    except Exception as e:
        print(f"Error fetching products: {str(e)}")
        return []

def fetch_today_sales(supabase, business_id):
    """Fixed today's sales calculation with proper timezone handling"""
    try:
        from datetime import datetime, date
        
        # Get today's date in UTC
        today = date.today()
        
        # IMPORTANT: Check if your database stores timestamps in UTC or local time
        # If UTC, we need to adjust for timezone
        today_start = datetime.combine(today, datetime.min.time()).isoformat() + "Z"  # UTC
        today_end = datetime.combine(today, datetime.max.time()).isoformat() + "Z"    # UTC
        
        print(f"DEBUG: Querying sales from {today_start} to {today_end}")
        
        # Query sales for today
        sales_res = supabase.table('sales') \
            .select('id, total_amount, payment_status, created_at, invoice_number') \
            .eq('business_id', business_id) \
            .gte('created_at', today_start) \
            .lte('created_at', today_end) \
            .execute()
        
        print(f"DEBUG: Found {len(sales_res.data) if sales_res.data else 0} sales records")
        
        if sales_res.data:
            # Debug: Print all sales found
            for sale in sales_res.data:
                print(f"  - {sale.get('invoice_number')}: {sale.get('total_amount')} ({sale.get('payment_status')}) at {sale.get('created_at')}")
            
            # Filter completed sales
            completed_sales = [
                sale for sale in sales_res.data 
                if sale.get('payment_status') == 'completed'
            ]
            
            today_total = sum(sale['total_amount'] for sale in completed_sales)
            print(f"DEBUG: Total completed sales today: {today_total}")
            
            return today_total
        else:
            print("DEBUG: No sales data found")
            return 0
            
    except Exception as e:
        print(f"ERROR in fetch_today_sales_fixed: {str(e)}")
        return 0

def calculate_cart_totals_fast(cart):
    """Optimized cart total calculation"""
    if not cart:
        return {'subtotal': 0, 'tax_total': 0, 'total': 0}
    
    subtotal = 0
    tax_total = 0
    
    for item in cart.values():
        item_total = item['price'] * item['quantity']
        subtotal += item_total
        tax_total += item_total * (item.get('tax_rate', 0) / 100)
    
    return {
        'subtotal': round(subtotal, 2),
        'tax_total': round(tax_total, 2),
        'total': round(subtotal + tax_total, 2)
    }
# Terminal Routes


@sales_bp.route('/', methods=['GET', 'POST'])
@sales_access_required
def terminal():
    """Sales terminal main page - Optimized for speed"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # POST requests
        if request.method == 'POST':
            action = request.form.get('action')
            
            # Fast path for cart operations using session only
            if action in ['add_to_cart', 'update_cart', 'clear_cart']:
                return handle_cart_operation(action, supabase, business_id)
            
            # Payment redirection
            elif action == 'process_payment':
                return redirect(url_for('sales_terminal.process_payment'))
        
        # GET request - optimized loading
        # Parallel fetching of data
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Fetch all needed data in parallel
            categories_future = executor.submit(fetch_categories, supabase, business_id)
            products_future = executor.submit(fetch_products_with_stock, supabase, business_id)
            today_sales_future = executor.submit(fetch_today_sales, supabase, business_id)
            
            # Get results
            categories = categories_future.result()
            products = products_future.result()
            today_total = today_sales_future.result()
        
        # Get cart from session
        cart = session.get('cart', {})
        
        # Calculate totals (optimized)
        totals = calculate_cart_totals_fast(cart)
        
        # Cache frequently accessed data
        cache_key = f'terminal_data_{business_id}_{datetime.now().strftime("%Y%m%d%H")}'
        cached_data = memory_cache.get(cache_key)
        
        if not cached_data:
            cached_data = {
                'categories': categories,
                'products': products,
                'today_total': today_total
            }
            memory_cache.set(cache_key, cached_data, timeout=300)  # Cache for 5 minutes
           
        
        return render_template('sales/simple_terminal.html', 
                             categories=categories,
                             products=products,
                             cart=cart,
                             totals=totals,
                             today_total=today_total)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        print(f"Error in terminal: {str(e)}")
        return redirect(url_for('dashboard'))
    
    

@sales_bp.route('/payment', methods=['GET', 'POST'])
@sales_access_required
def process_payment():
    """Process payment page"""
    try:
        cart = session.get('cart', {})
        
        if not cart:
            flash('Cart is empty', 'error')
            return redirect(url_for('sales_terminal.terminal'))
        
        if request.method == 'POST':
            # Process the sale
            payment_method = request.form.get('payment_method')
            customer_name = request.form.get('customer_name', '').strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            customer_email = request.form.get('customer_email', '').strip()
            discount_amount = Decimal(request.form.get('discount_amount', '0'))
            notes = request.form.get('notes', '').strip()
            
            if payment_method not in ['cash', 'card', 'mobile_money', 'bank_transfer', 'pesapal', '']:
                
                return redirect(url_for('sales_terminal.process_payment'))
            
            supabase = get_supabase()
            business_id = session.get('business_id')
            user_id = session.get('user_id')
            
            # Calculate totals
            totals = calculate_cart_totals(cart)
            
            # Apply discount
            final_total = Decimal(str(totals['total']))
            discount = Decimal('0')
            
            if discount_amount > 0:
                discount = discount_amount
                final_total = max(0, final_total - discount)
            
            # Generate invoice number
            invoice_number = generate_invoice_number(supabase, business_id)
            
            # Determine payment status
            payment_status = 'completed'
            if payment_method == 'pesapal':
                payment_status = 'pending'
            
            # Start transaction
            sale_id = str(uuid.uuid4())
            
            # Create sale record
            sale_data = {
                'id': sale_id,
                'business_id': business_id,
                'invoice_number': invoice_number,
                'customer_name': customer_name or 'Walk-in Customer',
                'customer_phone': customer_phone,
                'customer_email': customer_email,
                'subtotal': totals['subtotal'],
                'tax_amount': totals['tax_total'],
                'discount_amount': float(discount),
                'total_amount': float(final_total),
                'payment_method': payment_method,
                'payment_status': payment_status,
                'notes': notes,
                'sold_by': user_id,
                'created_at': get_utc_now().isoformat(),
                'updated_at': get_utc_now().isoformat()
            }
            
            # Insert sale
            sale_response = supabase.table('sales').insert(sale_data).execute()
            
            if not sale_response.data:
                flash('Failed to create sale record', 'error')
                return redirect(url_for('sales_terminal.process_payment'))
            
            # Create sale items and update inventory
            for product_id, item in cart.items():
                # Create sale item
                sale_item_id = str(uuid.uuid4())
                sale_item_data = {
                    'id': sale_item_id,
                    'sale_id': sale_id,
                    'product_id': product_id,
                    'product_name': item['name'],
                    'sku': item.get('sku'),
                    'quantity': item['quantity'],
                    'unit_price': item['price'],
                    'tax_rate': item['tax_rate'],
                    'total_price': item['price'] * item['quantity'],
                    'created_at': get_utc_now().isoformat()
                }
                
                supabase.table('sale_items').insert(sale_item_data).execute()
                
                # Update inventory
                quantity_to_deduct = item['quantity']
                lots_response = supabase.table('product_lots') \
                    .select('id, quantity, lot_number') \
                    .eq('product_id', product_id) \
                    .gt('quantity', 0) \
                    .order('created_at') \
                    .execute()
                
                if lots_response.data:
                    for lot in lots_response.data:
                        if quantity_to_deduct <= 0:
                            break
                        
                        lot_quantity = lot['quantity']
                        deduct_quantity = min(quantity_to_deduct, lot_quantity)
                        
                        if deduct_quantity > 0:
                            # Update lot quantity
                            supabase.table('product_lots') \
                                .update({'quantity': lot_quantity - deduct_quantity}) \
                                .eq('id', lot['id']) \
                                .execute()
                            
                            # Record inventory movement
                            movement_id = str(uuid.uuid4())
                            movement_data = {
                                'id': movement_id,
                                'product_id': product_id,
                                'lot_id': lot['id'],
                                'movement_type': 'OUT',
                                'quantity': deduct_quantity,
                                'reference': f'Sale: {invoice_number}',
                                'created_by': user_id,
                                'created_at': get_utc_now().isoformat()
                            }
                            
                            supabase.table('inventory_movements').insert(movement_data).execute()
                            
                            quantity_to_deduct -= deduct_quantity
            
            # Clear cart
            session['cart'] = {}
            session.modified = True
            
            # Handle PesaPal payment
            if payment_method == 'pesapal':
                # Initialize PesaPal
                pesapal = PesaPal()
                
                # Prepare payment details
                reference_id = invoice_number
                amount = float(final_total)
                
                # Extract names for billing
                names = customer_name.split()
                first_name = names[0] if names else "Customer"
                last_name = names[-1] if len(names) > 1 else "User"
                
                # Get callback URL
                callback_url = url_for('sales_terminal.pesapal_callback', _external=True)
                
                # Submit order to PesaPal
                order = pesapal.submit_order(
                    amount=amount,
                    reference_id=reference_id,
                    callback_url=callback_url,
                    email=customer_email or f"customer@{business_id}.com",
                    first_name=first_name,
                    last_name=last_name
                )
                
                if order and order.get('redirect_url'):
                    # Update sale with PesaPal order ID
                    supabase.table('sales') \
                        .update({
                            'pesapal_order_id': order['order_tracking_id'],
                            'payment_status': 'pending',
                            'updated_at': get_utc_now().isoformat()
                        }) \
                        .eq('id', sale_id) \
                        .execute()
                    
                    # Store payment session
                    payment_session_data = {
                        'id': str(uuid.uuid4()),
                        'sale_id': sale_id,
                        'order_tracking_id': order['order_tracking_id'],
                        'reference_id': reference_id,
                        'amount': amount,
                        'created_at': get_utc_now().isoformat()
                    }
                    
                    supabase.table('payment_sessions').insert(payment_session_data).execute()
                    
                    # Redirect to PesaPal
                    return redirect(order['redirect_url'])
                else:
                    flash('Failed to initiate PesaPal payment', 'error')
                    return redirect(url_for('sales_terminal.terminal'))
            
            # For non-PesaPal payments, show success
            flash(f'Sale completed! Invoice: {invoice_number}', 'success')
            return redirect(url_for('sales_terminal.receipt', sale_id=sale_id))
        
        # GET request - show payment form
        cart = session.get('cart', {})
        totals = calculate_cart_totals(cart) if cart else {'total': 0}
        
        return render_template('sales/payment.html', 
                             cart=cart, 
                             totals=totals)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('sales_terminal.terminal'))

# Keep these routes as they are (no changes needed)
@sales_bp.route('/pesapal-callback', methods=['GET'])
def pesapal_callback():
    """Handle PesaPal payment callback"""
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        merchant_reference = request.args.get('OrderMerchantReference')
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('sales_terminal.terminal'))
        
        supabase = get_supabase()
        
        # Get payment session
        payment_session_res = supabase.table('payment_sessions') \
            .select('*') \
            .eq('order_tracking_id', order_tracking_id) \
            .single() \
            .execute()
        
        if not payment_session_res.data:
            flash('Payment session not found', 'error')
            return redirect(url_for('sales_terminal.terminal'))
        
        payment_session = payment_session_res.data
        sale_id = payment_session['sale_id']
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('sales_terminal.terminal'))
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            normalized_status = 'completed'
        elif 'PENDING' in payment_status_desc:
            normalized_status = 'pending'
        else:
            normalized_status = 'failed'
        
        # Update sale status
        supabase.table('sales') \
            .update({
                'payment_status': normalized_status,
                'updated_at': get_utc_now().isoformat()
            }) \
            .eq('id', sale_id) \
            .execute()
        
        if normalized_status == 'completed':
            flash('Payment completed successfully!', 'success')
            # Redirect to receipt
            return redirect(url_for('sales_terminal.receipt', sale_id=sale_id))
        elif normalized_status == 'pending':
            flash('Payment is pending confirmation', 'info')
        else:
            flash('Payment failed', 'error')
        
        return redirect(url_for('sales_terminal.terminal'))
            
    except Exception as e:
        flash(f'Error processing payment: {str(e)}', 'error')
        return redirect(url_for('sales_terminal.terminal'))

@sales_bp.route('/receipt/<sale_id>')
@sales_access_required
def receipt(sale_id):
    """View receipt for a sale"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get sale details
        sale_response = supabase.table('sales') \
            .select('*, users(first_name, last_name)') \
            .eq('id', sale_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if not sale_response.data:
            flash('Sale not found', 'error')
            return redirect(url_for('sales_terminal.terminal'))
        
        sale = sale_response.data[0]
        
        # Get sale items
        items_response = supabase.table('sale_items') \
            .select('*') \
            .eq('sale_id', sale_id) \
            .execute()
        
        items = items_response.data if items_response.data else []
        
        # Get business info
        business_response = supabase.table('businesses') \
            .select('*') \
            .eq('id', business_id) \
            .execute()
            
        print(business_response.data)
        
        business = business_response.data[0] if business_response.data else {}
        current_time = datetime.now()
        auto_print = request.args.get('print') == 'true'
        return render_template('sales/receipt.html',
                             sale=sale,
                             items=items,
                             business=business,
                             current_time=current_time,
                             auto_print=auto_print)
        
        
    except Exception as e:
        flash(f'Error loading receipt: {str(e)}', 'error')
        print(e)
        return redirect(url_for('sales_terminal.terminal'))


# Simple in-memory cache
_sales_cache = {}
_cache_lock = threading.RLock()

def get_cached_sales(business_id, cache_key):
    """Thread-safe cache get"""
    with _cache_lock:
        return _sales_cache.get(cache_key)

def set_cached_sales(business_id, cache_key, data, ttl_minutes=5):
    """Thread-safe cache set with TTL"""
    with _cache_lock:
        _sales_cache[cache_key] = {
            'data': data,
            'expires': datetime.now() + timedelta(minutes=ttl_minutes)
        }

def clear_expired_cache():
    """Clear expired cache entries"""
    with _cache_lock:
        now = datetime.now()
        expired_keys = [
            key for key, value in _sales_cache.items()
            if value['expires'] < now
        ]
        for key in expired_keys:
            del _sales_cache[key]

@sales_bp.route('/history')
@sales_access_required
def sales_history():
    """View sales history - Optimized with concurrency and caching"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Generate cache key based on filters
        cache_key = f"sales_history_{business_id}_{hash(frozenset(request.args.items()))}"
        
        # Try to get from cache first
        cached_data = get_cached_sales(business_id, cache_key)
        if cached_data and cached_data['expires'] > datetime.now():
            return render_template('sales/history.html', **cached_data['data'])
        
        # Get filter parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        payment_method = request.args.get('payment_method')
        status = request.args.get('status')
        
        # Build base query
        query = supabase.table('sales') \
            .select('id, invoice_number, created_at, customer_name, customer_phone, ' +
                   'total_amount, tax_amount, payment_method, payment_status, refund_amount') \
            .eq('business_id', business_id) \
            .order('created_at', desc=True)
        
        # Apply filters
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00')
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59')
        if payment_method:
            query = query.eq('payment_method', payment_method)
        if status:
            query = query.eq('payment_status', status)
        
        # Execute sales query (main data)
        sales_response = query.execute()
        sales = sales_response.data if sales_response.data else []
        
        if not sales:
            # Empty result - cache it anyway
            result_data = {
                'sales': [],
                'today_total': 0,
                'payment_method_counts': [],
                'current_date': date.today().isoformat()
            }
            set_cached_sales(business_id, cache_key, result_data, 1)
            return render_template('sales/history.html', **result_data)
        
        # Parallel fetching of sale items for all sales
        sales_with_items = fetch_sale_items_concurrently(supabase, sales)
        
        # Parallel calculation of statistics
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Submit parallel tasks
            today_total_future = executor.submit(
                fetch_today_sales_total, 
                supabase, 
                business_id
            )
            payment_stats_future = executor.submit(
                calculate_payment_method_stats, 
                sales
            )
            
            # Get results
            today_total = today_total_future.result()
            payment_method_counts = payment_stats_future.result()
        
        # Prepare result data
        result_data = {
            'sales': sales_with_items,
            'today_total': today_total,
            'payment_method_counts': payment_method_counts,
            'current_date': date.today().isoformat()
        }
        
        # Cache the result
        set_cached_sales(business_id, cache_key, result_data, 5)
        
        # Clean up expired cache in background
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(clear_expired_cache)
        executor.shutdown(wait=False)
        
        return render_template('sales/history.html', **result_data)
        
    except Exception as e:
        flash(f'Error loading sales history: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

def fetch_sale_items_concurrently(supabase, sales):
    """Fetch sale items for multiple sales in parallel"""
    if not sales:
        return sales
    
    # Group sales for batch processing
    sale_ids = [sale['id'] for sale in sales]
    
    # Fetch all sale items in one query
    items_response = supabase.table('sale_items') \
        .select('sale_id, product_name, quantity, unit_price') \
        .in_('sale_id', sale_ids[:100])\
        .execute()
    
    sale_items_dict = {}
    if items_response.data:
        for item in items_response.data:
            sale_id = item['sale_id']
            if sale_id not in sale_items_dict:
                sale_items_dict[sale_id] = []
            sale_items_dict[sale_id].append(item)
    
    # Enrich sales with item data
    sales_with_items = []
    for sale in sales:
        sale_items = sale_items_dict.get(sale['id'], [])
        
        # Calculate totals
        item_count = len(sale_items)
        total_quantity = sum(item.get('quantity', 0) for item in sale_items)
        
        # Create enriched sale object
        enriched_sale = dict(sale)
        enriched_sale.update({
            'item_count': item_count,
            'total_quantity': total_quantity,
            'sale_items': sale_items
        })
        
        sales_with_items.append(enriched_sale)
    
    return sales_with_items

@lru_cache(maxsize=128)
def fetch_today_sales_total(supabase, business_id):
    """Fetch today's sales total with caching"""
    try:
        today = date.today()
        today_start = today.isoformat() + "T00:00:00"
        today_end = today.isoformat() + "T23:59:59"
        
        # Use aggregated query for better performance
        response = supabase.table('sales') \
            .select('total_amount', count='exact') \
            .eq('business_id', business_id) \
            .eq('payment_status', 'completed') \
            .gte('created_at', today_start) \
            .lte('created_at', today_end) \
            .execute()
        
        return sum(sale['total_amount'] for sale in (response.data or []))
    except:
        return 0

def calculate_payment_method_stats(sales):
    """Calculate payment method statistics"""
    payment_counts = {}
    for sale in sales:
        method = sale.get('payment_method', 'unknown')
        payment_counts[method] = payment_counts.get(method, 0) + 1
    
    return sorted(payment_counts.items(), key=lambda x: x[1], reverse=True)



@sales_bp.route('/refund/<sale_id>', methods=['GET', 'POST'])
@sales_access_required
def refund_sale(sale_id):
    """Handle sale refunds"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        if request.method == 'GET':
            # Show refund form
            # Get sale details
            sale_response = supabase.table('sales') \
                .select('*') \
                .eq('id', sale_id) \
                .eq('business_id', business_id) \
                .single() \
                .execute()
            
            if not sale_response.data:
                flash('Sale not found', 'error')
                return redirect(url_for('sales_terminal.sales_history'))
            
            sale = sale_response.data
            
            # Get sale items
            items_response = supabase.table('sale_items') \
                .select('*') \
                .eq('sale_id', sale_id) \
                .execute()
            
            sale_items = items_response.data if items_response.data else []
            
            return render_template('sales/refund.html', 
                                 sale=sale,
                                 sale_items=sale_items)
        
        elif request.method == 'POST':
            # Process refund
            action = request.form.get('action')
            
            if action == 'full_refund':
                return process_full_refund(supabase, sale_id, business_id)
            elif action == 'partial_refund':
                return process_partial_refund(supabase, sale_id, business_id)
            
    except Exception as e:
        flash(f'Error processing refund: {str(e)}', 'error')
        return redirect(url_for('sales_terminal.sales_history'))
def process_full_refund(supabase, sale_id, business_id):
    """Process full refund of a sale"""
    try:
        # Get original sale
        sale_response = supabase.table('sales') \
            .select('*') \
            .eq('id', sale_id) \
            .eq('business_id', business_id) \
            .single() \
            .execute()
        
        if not sale_response.data:
            flash('Sale not found', 'error')
            return redirect(url_for('sales_terminal.sales_history'))
        
        sale = sale_response.data
        
        # Get sale items to restock
        items_response = supabase.table('sale_items') \
            .select('*') \
            .eq('sale_id', sale_id) \
            .execute()
        
        sale_items = items_response.data if items_response.data else []
        
        # Start a transaction
        refund_id = str(uuid.uuid4())
        
        # 1. Create refund record - FIXED: use 'payment_method' not 'refund_method'
        refund_data = {
            'id': refund_id,
            'business_id': business_id,
            'sale_id': sale_id,
            'refund_amount': sale['total_amount'],
            'refund_reason': request.form.get('reason', 'Customer request'),
            'refunded_by': session.get('user_id'),
            'payment_method': sale['payment_method'],  # Changed from 'refund_method'
            'status': 'completed',
            'notes': request.form.get('notes', '')
        }
        
        supabase.table('refunds').insert(refund_data).execute()
        
        # 2. Update sale status
        supabase.table('sales') \
            .update({
                'payment_status': 'refunded',
                'refund_id': refund_id,
                'refund_amount': sale['total_amount'],
                'updated_at': datetime.utcnow().isoformat()
            }) \
            .eq('id', sale_id) \
            .execute()
        
        # 3. Restock products
        for item in sale_items:
            # Find product lots and restock
            lots_response = supabase.table('product_lots') \
                .select('*') \
                .eq('product_id', item['product_id']) \
                .order('expiry_date') \
                .execute()
            
            if lots_response.data:
                # Add to first lot (FIFO)
                lot = lots_response.data[0]
                new_quantity = lot['quantity'] + item['quantity']
                
                supabase.table('product_lots') \
                    .update({'quantity': new_quantity}) \
                    .eq('id', lot['id']) \
                    .execute()
            else:
                # Create new lot for returned items
                new_lot = {
                    'id': str(uuid.uuid4()),
                    'business_id': business_id,
                    'product_id': item['product_id'],
                    'quantity': item['quantity'],
                    'purchase_price': item['unit_price'],
                    'selling_price': item['unit_price'],
                    'expiry_date': (datetime.utcnow() + timedelta(days=365)).isoformat(),
                    'batch_number': f'REFUND-{refund_id[:8]}'
                }
                supabase.table('product_lots').insert(new_lot).execute()
        
        # 4. Create audit log
        audit_log = {
            'id': str(uuid.uuid4()),
            'business_id': business_id,
            'user_id': session.get('user_id'),
            'action': 'refund',
            'description': f'Full refund processed for sale {sale["invoice_number"]}',
            'details': {
                'sale_id': sale_id,
                'refund_id': refund_id,
                'amount': sale['total_amount'],
                'reason': request.form.get('reason', 'Customer request')
            },
            'created_at': datetime.utcnow().isoformat()
        }
        supabase.table('audit_logs').insert(audit_log).execute()
        
        flash(f'Successfully refunded UGX {sale["total_amount"]:.2f}', 'success')
        return redirect(url_for('sales_terminal.sales_history'))
        
    except Exception as e:
        flash(f'Error processing refund: {str(e)}', 'error')
        return redirect(url_for('sales_terminal.sales_history'))

def process_partial_refund(supabase, sale_id, business_id):
    """Process partial refund"""
    try:
        # Get form data
        refund_amount = float(request.form.get('refund_amount', 0))
        reason = request.form.get('reason', 'Partial refund - customer request')
        
        # Get original sale
        sale_response = supabase.table('sales') \
            .select('*') \
            .eq('id', sale_id) \
            .eq('business_id', business_id) \
            .single() \
            .execute()
        
        if not sale_response.data:
            flash('Sale not found', 'error')
            return redirect(url_for('sales_terminal.sales_history'))
        
        sale = sale_response.data
        
        if refund_amount <= 0:
            flash('Refund amount must be greater than 0', 'error')
            return redirect(url_for('sales_terminal.refund_sale', sale_id=sale_id))
        
        if refund_amount > sale['total_amount']:
            flash('Refund amount cannot exceed original sale amount', 'error')
            return redirect(url_for('sales_terminal.refund_sale', sale_id=sale_id))
        
        # Create refund record - FIXED: use 'payment_method'
        refund_id = str(uuid.uuid4())
        refund_data = {
            'id': refund_id,
            'business_id': business_id,
            'sale_id': sale_id,
            'refund_amount': refund_amount,
            'refund_reason': reason,
            'refunded_by': session.get('user_id'),
            'payment_method': sale['payment_method'],  # Changed from 'refund_method'
            'status': 'completed',
            'notes': request.form.get('notes', '')
        }
        
        supabase.table('refunds').insert(refund_data).execute()
        
        # Update sale with partial refund info
        supabase.table('sales') \
            .update({
                'payment_status': 'partially_refunded',
                'refund_amount': refund_amount,
                'refund_id': refund_id,
                'updated_at': datetime.utcnow().isoformat()
            }) \
            .eq('id', sale_id) \
            .execute()
        
        # Create audit log
        audit_log = {
            'id': str(uuid.uuid4()),
            'business_id': business_id,
            'user_id': session.get('user_id'),
            'action': 'partial_refund',
            'description': f'Partial refund of UGX {refund_amount:.2f} for sale {sale["invoice_number"]}',
            'details': {
                'sale_id': sale_id,
                'refund_id': refund_id,
                'original_amount': sale['total_amount'],
                'refund_amount': refund_amount,
                'reason': reason
            },
            'created_at': datetime.utcnow().isoformat()
        }
        supabase.table('audit_logs').insert(audit_log).execute()
        
        flash(f'Successfully processed partial refund of UGX {refund_amount:.2f}', 'success')
        return redirect(url_for('sales_terminal.sales_history'))
        
    except Exception as e:
        flash(f'Error processing partial refund: {str(e)}', 'error')
        return redirect(url_for('sales_terminal.refund_sale', sale_id=sale_id))
    
def time_ago(dt_str):
    from datetime import datetime, timezone
    """Return human-readable relative time from ISO string"""
    if not dt_str:
        return ''
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    else:
        return f"{int(seconds // 86400)}d ago"   
    
    
@sales_bp.route('/audit-logs')
@role_required(['admin', 'manager'])  # Only admins and managers can view audit logs
def audit_logs():
    """Display audit logs"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # --- Get filter parameters ---
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        action_filter = request.args.get('action')
        user_id_filter = request.args.get('user_id')
        page = int(request.args.get('page', 1))
        limit = 20
        
        # --- Base query ---
        query = supabase.table('audit_logs').select('*', count='exact').eq('business_id', business_id)
        
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00')
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59')
        if action_filter:
            query = query.eq('action', action_filter)
        if user_id_filter:
            query = query.eq('user_id', user_id_filter)
        
        # Pagination
        start_index = (page - 1) * limit
        end_index = start_index + limit - 1
        query = query.order('created_at', desc=True).range(start_index, end_index)
        
        # Execute query
        response = query.execute()
        logs = response.data if response.data else []
        total_count = response.count or 0
        total_pages = (total_count + limit - 1) // limit
        
        # --- Fetch user info for logs ---
        user_ids = {log['user_id'] for log in logs if log.get('user_id')}
        users_map = {}
        if user_ids:
            users_response = supabase.table('users').select('id, first_name, last_name, role').in_('id', list(user_ids)).execute()
            if users_response.data:
                users_map = {u['id']: u for u in users_response.data}
        
        # Add user info to logs
        for log in logs:
            user_info = users_map.get(log.get('user_id'))
            if user_info:
                log['user_name'] = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                log['user_role'] = user_info.get('role')
        
        # --- Statistics in Python ---
        today_str = datetime.now().date().isoformat()
        today_logs_count = sum(1 for log in logs if log.get('created_at', '').startswith(today_str))
        
        # Top user
        user_counter = {}
        for log in logs:
            uid = log.get('user_id')
            if uid:
                user_counter[uid] = user_counter.get(uid, 0) + 1
        top_user = None
        if user_counter:
            top_user_id = max(user_counter, key=user_counter.get)
            u = users_map.get(top_user_id)
            if u:
                top_user = {'name': f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(), 'role': u.get('role')}
        
        # Most common action
        action_counter = {}
        for log in logs:
            act = log.get('action')
            if act:
                action_counter[act] = action_counter.get(act, 0) + 1
        common_action = max(action_counter, key=action_counter.get) if action_counter else None
        
        # --- Get all users for filter dropdown ---
        all_users_resp = supabase.table('users').select('id, first_name, last_name, role').eq('business_id', business_id).order('first_name').execute()
        users = all_users_resp.data if all_users_resp.data else []
        for u in users:
            u['name'] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        
        return render_template(
            'sales/logs.html',
            logs=logs,
            total_logs=total_count,
            today_logs=today_logs_count,
            top_user=top_user,
            common_action=common_action,
            users=users,
            page=page,
            pages=total_pages,
            current_date=today_str,
            time_ago=time_ago
            
        )
    
    except Exception as e:
        flash(f'Error loading audit logs: {str(e)}', 'error')
        print(f"Error loading audit logs: {str(e)}")
        return redirect(url_for('dashboard'))
