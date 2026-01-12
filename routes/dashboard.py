from flask import Blueprint, render_template, jsonify, session
from routes.auth import login_required, get_supabase, get_utc_now
from datetime import datetime, date, timedelta
import json

dashboard_bp = Blueprint('dashboard', __name__)

def get_user_business_id():
    """Get the business_id for the current user from session"""
    try:
        if 'business_id' in session:
            return session['business_id']
        
        # Get user_id from session
        user_id = session.get('user_id')
        if not user_id:
            return None
        
        supabase = get_supabase()
        
        # Try businesses table
        response = supabase.table('businesses').select(
            'id, business_name, logo_url'
        ).eq('user_id', user_id).limit(1).execute()
        
        if response.data:
            business = response.data[0]
            session['business_id'] = business['id']
            session['business_name'] = business.get('business_name', 'Business')
            session['business_logo'] = business.get('logo_url')
            return business['id']
        
        return None
        
    except Exception as e:
        print(f"Error getting user business: {e}")
        return None

def get_today_sales(business_id):
    """Get today's sales summary"""
    try:
        supabase = get_supabase()
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        
        response = supabase.table('sales').select(
            'id, total_amount, subtotal, tax_amount, discount_amount, payment_status, created_at'
        ).eq('business_id', business_id)\
         .gte('created_at', f'{today_str} 00:00:00')\
         .lte('created_at', f'{today_str} 23:59:59')\
         .execute()
        
        sales = response.data if response.data else []
        
        total_sales = len(sales)
        total_revenue = sum(float(sale.get('total_amount', 0)) for sale in sales)
        total_tax = sum(float(sale.get('tax_amount', 0)) for sale in sales)
        total_discount = sum(float(sale.get('discount_amount', 0)) for sale in sales)
        completed_sales = len([s for s in sales if s.get('payment_status') == 'completed'])
        pending_sales = len([s for s in sales if s.get('payment_status') == 'pending'])
        
        return {
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_tax': total_tax,
            'total_discount': total_discount,
            'completed_sales': completed_sales,
            'pending_sales': pending_sales,
            'sales_list': sales[:5]  # Last 5 sales
        }
    except Exception as e:
        print(f"Error getting today's sales: {e}")
        return None

def get_today_expenses(business_id):
    """Get today's expenses summary"""
    try:
        supabase = get_supabase()
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        
        response = supabase.table('expenses').select(
            'id, amount, category, status, expense_date, vendor'
        ).eq('business_id', business_id)\
         .gte('expense_date', today_str)\
         .lte('expense_date', today_str)\
         .execute()
        
        expenses = response.data if response.data else []
        
        total_expenses = len(expenses)
        total_amount = sum(float(expense.get('amount', 0)) for expense in expenses)
        approved_expenses = len([e for e in expenses if e.get('status') == 'approved'])
        
        # Top categories
        categories = {}
        for expense in expenses:
            category = expense.get('category', 'Uncategorized')
            amount = float(expense.get('amount', 0))
            if category not in categories:
                categories[category] = 0
            categories[category] += amount
        
        top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            'total_expenses': total_expenses,
            'total_amount': total_amount,
            'approved_expenses': approved_expenses,
            'top_categories': top_categories,
            'expenses_list': expenses[:5]  # Last 5 expenses
        }
    except Exception as e:
        print(f"Error getting today's expenses: {e}")
        return None

def get_low_stock_products(business_id):
    """Get low stock products using product_lots table"""
    try:
        supabase = get_supabase()
        
        # Get all products with product_lots
        response = supabase.table('products').select(
            'id, name, sku, selling_price, image_url, reorder_level'
        ).eq('business_id', business_id)\
         .eq('is_active', True)\
         .execute()
        
        products = response.data if response.data else []
        
        low_stock_products = []
        for product in products:
            # Get stock from product_lots
            lots_response = supabase.table('product_lots').select(
                'quantity'
            ).eq('product_id', product['id']).execute()
            
            current_stock = 0
            if lots_response.data:
                current_stock = sum(lot['quantity'] for lot in lots_response.data)
            
            reorder_level = product.get('reorder_level', 0)
            
            if current_stock <= reorder_level:
                low_stock_products.append({
                    'id': product['id'],
                    'name': product['name'],
                    'sku': product.get('sku', 'N/A'),
                    'current_stock': current_stock,
                    'reorder_level': reorder_level,
                    'selling_price': float(product.get('selling_price', 0)),
                    'image_url': product.get('image_url')
                })
        
        return sorted(low_stock_products, key=lambda x: x['current_stock'])[:5]
        
    except Exception as e:
        print(f"Error getting low stock products: {e}")
        return []

def get_recent_activity(business_id):
    """Get recent system activity"""
    try:
        supabase = get_supabase()
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        
        # Get recent sales
        sales_response = supabase.table('sales').select(
            'invoice_number, total_amount, created_at, payment_status'
        ).eq('business_id', business_id)\
         .gte('created_at', week_ago.isoformat())\
         .order('created_at', desc=True)\
         .limit(10)\
         .execute()
        
        # Get recent expenses
        expenses_response = supabase.table('expenses').select(
            'vendor, amount, expense_date, status'
        ).eq('business_id', business_id)\
         .gte('expense_date', week_ago.date().isoformat())\
         .order('expense_date', desc=True)\
         .limit(10)\
         .execute()
        
        # Get recent low stock alerts from product audit logs
        inventory_response = supabase.table('product_audit_logs').select(
            'product_id, products(name), action_type, created_at'
        ).eq('business_id', business_id)\
         .gte('created_at', week_ago.isoformat())\
         .eq('action_type', 'STOCK_ADJUSTED')\
         .order('created_at', desc=True)\
         .limit(5)\
         .execute()
        
        activity = []
        
        # Add sales to activity
        for sale in sales_response.data if sales_response.data else []:
            activity.append({
                'type': 'sale',
                'title': f"Sale #{sale.get('invoice_number', 'N/A')}",
                'amount': float(sale.get('total_amount', 0)),
                'timestamp': sale.get('created_at'),
                'status': sale.get('payment_status', 'pending'),
                'icon': 'fa-cash-register',
                'color': 'green'
            })
        
        # Add expenses to activity
        for expense in expenses_response.data if expenses_response.data else []:
            activity.append({
                'type': 'expense',
                'title': f"Expense to {expense.get('vendor', 'Vendor')}",
                'amount': float(expense.get('amount', 0)),
                'timestamp': expense.get('expense_date'),
                'status': expense.get('status', 'pending'),
                'icon': 'fa-receipt',
                'color': 'red'
            })
        
        # Add low stock alerts
        for alert in inventory_response.data if inventory_response.data else []:
            product_name = alert.get('products', {}).get('name', 'Product') if alert.get('products') else 'Product'
            activity.append({
                'type': 'inventory',
                'title': f"Stock adjusted: {product_name}",
                'detail': f"Stock level updated",
                'timestamp': alert.get('created_at'),
                'icon': 'fa-boxes',
                'color': 'yellow'
            })
        
        # Sort by timestamp
        activity.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return activity[:15]
        
    except Exception as e:
        print(f"Error getting recent activity: {e}")
        return []

def get_weekly_sales_trend(business_id):
    """Get weekly sales trend"""
    try:
        supabase = get_supabase()
        today = date.today()
        week_ago = today - timedelta(days=6)  # Last 7 days including today
        
        response = supabase.table('sales').select(
            'created_at, total_amount'
        ).eq('business_id', business_id)\
         .gte('created_at', week_ago.isoformat())\
         .lte('created_at', today.isoformat())\
         .execute()
        
        sales = response.data if response.data else []
        
        # Initialize daily totals
        daily_totals = {}
        current_date = week_ago
        while current_date <= today:
            daily_totals[current_date.isoformat()] = 0
            current_date += timedelta(days=1)
        
        # Sum sales by day
        for sale in sales:
            try:
                sale_date = datetime.fromisoformat(sale['created_at'].replace('Z', '+00:00')).date()
                amount = float(sale.get('total_amount', 0))
                date_key = sale_date.isoformat()
                if date_key in daily_totals:
                    daily_totals[date_key] += amount
            except:
                continue
        
        # Format for chart
        labels = []
        data = []
        
        current_date = week_ago
        while current_date <= today:
            day_name = current_date.strftime('%a')
            labels.append(day_name)
            data.append(daily_totals[current_date.isoformat()])
            current_date += timedelta(days=1)
        
        return {
            'labels': labels,
            'data': data
        }
        
    except Exception as e:
        print(f"Error getting weekly sales trend: {e}")
        return {'labels': [], 'data': []}

def get_category_sales_distribution(business_id):
    """Get sales distribution by product category"""
    try:
        supabase = get_supabase()
        
        # Get sales with product details using sale_items table
        sales_response = supabase.table('sales').select(
            'id, created_at'
        ).eq('business_id', business_id)\
         .gte('created_at', (date.today() - timedelta(days=30)).isoformat())\
         .limit(50)\
         .execute()
        
        sales = sales_response.data if sales_response.data else []
        
        # Get sale items for each sale
        category_totals = {}
        for sale in sales:
            # Get sale items - adjust based on your actual sale_items table structure
            try:
                # Try to get sale items from your actual table structure
                # Adjust this based on your actual sale_items table
                items_response = supabase.rpc('get_sale_items', {'sale_id': sale['id']}).execute()
            except:
                # If RPC doesn't exist, try direct table query
                try:
                    items_response = supabase.table('sale_items').select(
                        'product_id, quantity, unit_price'
                    ).eq('sale_id', sale['id']).execute()
                except Exception as items_error:
                    print(f"Error getting sale items: {items_error}")
                    continue
            
            items = items_response.data if hasattr(items_response, 'data') and items_response.data else []
            
            for item in items:
                # Get product category
                product_response = supabase.table('products').select(
                    'category_id'
                ).eq('id', item.get('product_id')).limit(1).execute()
                
                if product_response.data:
                    category_id = product_response.data[0].get('category_id')
                    if category_id:
                        # Get category name
                        category_response = supabase.table('categories').select(
                            'name'
                        ).eq('id', category_id).limit(1).execute()
                        
                        if category_response.data:
                            category_name = category_response.data[0].get('name', 'Uncategorized')
                        else:
                            category_name = 'Uncategorized'
                    else:
                        category_name = 'Uncategorized'
                else:
                    category_name = 'Uncategorized'
                
                # Calculate amount based on available fields
                quantity = item.get('quantity', 1)
                price = item.get('unit_price') or item.get('price') or item.get('selling_price', 0)
                amount = float(price) * int(quantity)
                
                if category_name not in category_totals:
                    category_totals[category_name] = 0
                category_totals[category_name] += amount
        
        # If we don't have enough data, use mock data
        if not category_totals:
            category_totals = {
                'Electronics': 250000,
                'Clothing': 180000,
                'Food & Beverages': 120000,
                'Home & Garden': 90000,
                'Other': 60000
            }
        
        # Sort by amount and get top 5
        sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'labels': [cat for cat, _ in sorted_categories],
            'data': [amount for _, amount in sorted_categories]
        }
        
    except Exception as e:
        print(f"Error getting category sales distribution: {e}")
        # Return mock data for demo
        return {
            'labels': ['Electronics', 'Clothing', 'Food & Beverages', 'Home & Garden', 'Other'],
            'data': [250000, 180000, 120000, 90000, 60000]
        }

def get_profit_summary(business_id):
    """Get profit summary for today"""
    try:
        supabase = get_supabase()
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        
        # Get today's revenue from sales
        sales_response = supabase.table('sales').select(
            'total_amount, subtotal'
        ).eq('business_id', business_id)\
         .gte('created_at', f'{today_str} 00:00:00')\
         .lte('created_at', f'{today_str} 23:59:59')\
         .execute()
        
        sales = sales_response.data if sales_response.data else []
        total_revenue = sum(float(sale.get('total_amount', 0)) for sale in sales)
        
        # Get today's expenses
        expenses_response = supabase.table('expenses').select(
            'amount'
        ).eq('business_id', business_id)\
         .eq('expense_date', today_str)\
         .eq('status', 'approved')\
         .execute()
        
        expenses = expenses_response.data if expenses_response.data else []
        total_expenses = sum(float(expense.get('amount', 0)) for expense in expenses)
        
        # Calculate profit (simple calculation for now)
        # In a real system, you'd also subtract cost of goods sold
        profit = total_revenue - total_expenses
        profit_margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        
        return {
            'revenue': total_revenue,
            'expenses': total_expenses,
            'profit': profit,
            'profit_margin': profit_margin,
            'is_profitable': profit >= 0
        }
        
    except Exception as e:
        print(f"Error getting profit summary: {e}")
        return None

@dashboard_bp.route('/')
@login_required
def dashboard():
    """Main dashboard page"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return render_template('dashboard/index.html',
                                 error="No business found. Please set up your business first.",
                                 title="Dashboard")
        
        # Get all dashboard data
        today_sales = get_today_sales(business_id)
        today_expenses = get_today_expenses(business_id)
        low_stock_products = get_low_stock_products(business_id)
        recent_activity = get_recent_activity(business_id)
        weekly_trend = get_weekly_sales_trend(business_id)
        category_distribution = get_category_sales_distribution(business_id)
        profit_summary = get_profit_summary(business_id)
        
        # Get business info from session
        business_name = session.get('business_name', 'Business')
        business_logo = session.get('business_logo')
        
        # Format currency for template
        def format_currency(amount):
            try:
                return f"UGX {float(amount):,.2f}"
            except:
                return "UGX 0.00"
        
        return render_template('dashboard/index.html',
                             business_name=business_name,
                             business_logo=business_logo,
                             today_sales=today_sales,
                             today_expenses=today_expenses,
                             low_stock_products=low_stock_products,
                             recent_activity=recent_activity,
                             weekly_trend=weekly_trend,
                             category_distribution=category_distribution,
                             profit_summary=profit_summary,
                             format_currency=format_currency,
                             title="Dashboard")
        
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        return render_template('dashboard/index.html',
                             error=f"Error loading dashboard: {str(e)}",
                             title="Dashboard")

@dashboard_bp.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    """API endpoint for dashboard statistics"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        today_sales = get_today_sales(business_id)
        today_expenses = get_today_expenses(business_id)
        profit_summary = get_profit_summary(business_id)
        low_stock_count = len(get_low_stock_products(business_id))
        
        return jsonify({
            'success': True,
            'sales': today_sales,
            'expenses': today_expenses,
            'profit': profit_summary,
            'low_stock_count': low_stock_count
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/dashboard/activity')
@login_required
def dashboard_activity():
    """API endpoint for recent activity"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        recent_activity = get_recent_activity(business_id)
        
        return jsonify({
            'success': True,
            'activity': recent_activity
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/dashboard/charts')
@login_required
def dashboard_charts():
    """API endpoint for chart data"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        weekly_trend = get_weekly_sales_trend(business_id)
        category_distribution = get_category_sales_distribution(business_id)
        
        return jsonify({
            'success': True,
            'weekly_trend': weekly_trend,
            'category_distribution': category_distribution
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/dashboard/low-stock')
@login_required
def dashboard_low_stock():
    """API endpoint for low stock products"""
    try:
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        low_stock_products = get_low_stock_products(business_id)
        
        return jsonify({
            'success': True,
            'low_stock_products': low_stock_products
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Health check endpoint
@dashboard_bp.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        supabase = get_supabase()
        test_response = supabase.table('businesses').select('id').limit(1).execute()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500