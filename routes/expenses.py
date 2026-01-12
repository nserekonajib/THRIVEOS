from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from routes.auth import login_required
from datetime import datetime, date
import uuid
from supabase import create_client
from config import Config

# Create Supabase client
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

expenses_bp = Blueprint('expenses', __name__)

def get_user_business_id():
    """Get the business_id for the current user from session or businesses table"""
    try:
        # First, check if business_id is already in session
        if 'business_id' in session:
            return session['business_id']
        
        # Get user_id from session
        user_id = session.get('user_id')
        if not user_id:
            print(f"❌ No user_id found in session")
            return None
        
        print(f"🔍 Looking up business for user_id: {user_id}")
        
        # First, try businesses table (since you showed that's where the business is created)
        response = supabase.table('businesses').select(
            'id'
        ).eq('user_id', user_id).limit(1).execute()
        
        if response.data:
            business_id = response.data[0]['id']
            print(f"✅ Found business in businesses table: {business_id}")
            session['business_id'] = business_id
            return business_id
        
        # If not found, try business_users table
        response = supabase.table('business_users').select(
            'business_id'
        ).eq('user_id', user_id).limit(1).execute()
        
        if response.data:
            business_id = response.data[0]['business_id']
            print(f"✅ Found business in business_users table: {business_id}")
            session['business_id'] = business_id
            return business_id
        
        print(f"❌ No business found for user_id: {user_id}")
        return None
        
    except Exception as e:
        print(f"Error getting user business: {e}")
        return None

def get_current_user_id():
    """Get current user ID from session"""
    return session.get('user_id')

@expenses_bp.route('/expenses')
@login_required
def expenses_list():
    """Display list of expenses with filtering options"""
    try:
        # Get user's business_id
        business_id = get_user_business_id()
        print(f"🔍 Using business_id: {business_id}")
        
        if not business_id:
            flash('No business found for your account. Please set up your business first.', 'danger')
            return render_template('expenses/list.html', expenses=[], title="Expenses")
        
        # Get filter parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        category = request.args.get('category')
        payment_method = request.args.get('payment_method')
        
        # Build query
        query = supabase.table('expenses')\
            .select('*')\
            .eq('business_id', business_id)
        
        # Apply filters
        if start_date:
            query = query.gte('expense_date', start_date)
        if end_date:
            query = query.lte('expense_date', end_date)
        if category:
            query = query.eq('category', category)
        if payment_method:
            query = query.eq('payment_method', payment_method)
        
        # Execute query
        print(f"📊 Querying expenses for business_id: {business_id}")
        response = query.order('expense_date', desc=True).execute()
        expenses = response.data
        
        print(f"✅ Found {len(expenses)} expenses")
        
        # Get totals
        total_amount = 0
        if expenses:
            total_amount = sum(float(expense.get('amount', 0)) for expense in expenses)
        
        print(f"💰 Total amount: {total_amount}")
        
        # Get unique categories for filter dropdown
        categories_response = supabase.table('expenses')\
            .select('category')\
            .eq('business_id', business_id)\
            .execute()
        
        categories = []
        if categories_response.data:
            categories = list(set([exp.get('category', 'Uncategorized') for exp in categories_response.data]))
        
        # Get unique payment methods
        payment_methods_response = supabase.table('expenses')\
            .select('payment_method')\
            .eq('business_id', business_id)\
            .execute()
        
        payment_methods = []
        if payment_methods_response.data:
            payment_methods = list(set([exp.get('payment_method', 'Cash') for exp in payment_methods_response.data]))
        
        # Format expense data for template
        formatted_expenses = []
        for expense in expenses:
            try:
                formatted_expense = {
                    'id': expense.get('id'),
                    'expense_date': expense.get('expense_date'),
                    'vendor': expense.get('vendor', 'N/A'),
                    'description': expense.get('description', ''),
                    'category': expense.get('category', 'Uncategorized'),
                    'amount': float(expense.get('amount', 0)),
                    'payment_method': expense.get('payment_method', 'Cash'),
                    'receipt_url': expense.get('receipt_url'),
                    'status': expense.get('status', 'approved'),
                    'notes': expense.get('notes', ''),
                    'created_by': expense.get('created_by')
                }
                
                print(f"📝 Processing expense: {formatted_expense['vendor']} - {formatted_expense['amount']}")
                
                # Format date
                if formatted_expense['expense_date']:
                    try:
                        if isinstance(formatted_expense['expense_date'], str):
                            if 'T' in formatted_expense['expense_date']:
                                expense_date = datetime.fromisoformat(formatted_expense['expense_date'].replace('Z', '+00:00'))
                            else:
                                expense_date = datetime.strptime(formatted_expense['expense_date'], '%Y-%m-%d')
                            formatted_expense['date_formatted'] = expense_date.strftime('%b %d, %Y')
                            formatted_expense['date_iso'] = expense_date.strftime('%Y-%m-%d')
                        else:
                            formatted_expense['date_formatted'] = str(formatted_expense['expense_date'])
                            formatted_expense['date_iso'] = str(formatted_expense['expense_date'])
                    except Exception as date_error:
                        print(f"⚠️ Date formatting error: {date_error}")
                        formatted_expense['date_formatted'] = str(formatted_expense['expense_date'])
                        formatted_expense['date_iso'] = str(formatted_expense['expense_date'])
                
                # Format amount
                formatted_expense['amount_formatted'] = f"UGX {formatted_expense['amount']:,.2f}"
                
                # Set status color
                status = formatted_expense['status'].lower()
                if status == 'approved':
                    formatted_expense['status_color'] = 'success'
                elif status == 'pending':
                    formatted_expense['status_color'] = 'warning'
                elif status == 'rejected':
                    formatted_expense['status_color'] = 'danger'
                else:
                    formatted_expense['status_color'] = 'secondary'
                
                formatted_expenses.append(formatted_expense)
            except Exception as exp_error:
                print(f"⚠️ Error processing expense: {exp_error}")
                continue
        
        # Get monthly totals for chart
        monthly_totals = get_monthly_expense_totals(business_id)
        
        # Get category totals for chart
        category_totals = get_category_totals(business_id)
        
        # Calculate average expense
        average_expense = 0
        if len(formatted_expenses) > 0:
            average_expense = total_amount / len(formatted_expenses)
        
        return render_template('expenses/list.html', 
                             expenses=formatted_expenses,
                             total_amount=total_amount,
                             total_amount_formatted=f"UGX {total_amount:,.2f}",
                             average_expense=average_expense,
                             average_expense_formatted=f"UGX {average_expense:,.2f}",
                             categories=categories,
                             payment_methods=payment_methods,
                             monthly_totals=monthly_totals,
                             category_totals=category_totals,
                             title="Expenses",
                             current_year=datetime.now().year)
    
    except Exception as e:
        print(f"❌ Error fetching expenses: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error fetching expenses: {str(e)}', 'danger')
        return render_template('expenses/list.html', 
                             expenses=[], 
                             title="Expenses")


@expenses_bp.route('/expenses/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    """Add a new expense"""
    # Get user's business_id
    business_id = get_user_business_id()
    if not business_id:
        flash('No business found for your account. Please set up your business first.', 'danger')
        return redirect(url_for('expenses.expenses_list'))
    
    if request.method == 'POST':
        try:
            expense_data = {
                'business_id': business_id,
                'expense_date': request.form.get('expense_date'),
                'vendor': request.form.get('vendor', '').strip(),
                'description': request.form.get('description', '').strip(),
                'category': request.form.get('category', 'Uncategorized'),
                'amount': float(request.form.get('amount', 0)),
                'payment_method': request.form.get('payment_method', 'Cash'),
                'receipt_url': request.form.get('receipt_url', '').strip(),
                'status': request.form.get('status', 'approved'),
                'notes': request.form.get('notes', '').strip(),
                'created_by': get_current_user_id(),
                'created_at': datetime.now().isoformat()
            }
            
            # Insert expense
            response = supabase.table('expenses').insert(expense_data).execute()
            
            if response.data:
                flash('Expense added successfully!', 'success')
                return redirect(url_for('expenses.expenses_list'))
            else:
                flash('Failed to add expense', 'danger')
        
        except Exception as e:
            flash(f'Error adding expense: {str(e)}', 'danger')
    
    # Get categories for dropdown
    categories = get_expense_categories()
    
    return render_template('expenses/add.html', 
                         categories=categories,
                         title="Add Expense",
                         now=datetime.now()
                         
                         ) 
                         

@expenses_bp.route('/expenses/edit/<uuid:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    """Edit an existing expense"""
    # Get user's business_id
    business_id = get_user_business_id()
    if not business_id:
        flash('No business found for your account. Please set up your business first.', 'danger')
        return redirect(url_for('expenses.expenses_list'))
    
    try:
        # Fetch expense
        response = supabase.table('expenses')\
            .select('*')\
            .eq('id', str(expense_id))\
            .eq('business_id', business_id)\
            .execute()
        
        if not response.data:
            flash('Expense not found or access denied', 'danger')
            return redirect(url_for('expenses.expenses_list'))
        
        expense = response.data[0]
        
        if request.method == 'POST':
            try:
                update_data = {
                    'expense_date': request.form.get('expense_date'),
                    'vendor': request.form.get('vendor', '').strip(),
                    'description': request.form.get('description', '').strip(),
                    'category': request.form.get('category', 'Uncategorized'),
                    'amount': float(request.form.get('amount', 0)),
                    'payment_method': request.form.get('payment_method', 'Cash'),
                    'receipt_url': request.form.get('receipt_url', '').strip(),
                    'status': request.form.get('status', 'approved'),
                    'notes': request.form.get('notes', '').strip(),
                    'updated_at': datetime.now().isoformat()
                }
                
                # Update expense
                update_response = supabase.table('expenses')\
                    .update(update_data)\
                    .eq('id', str(expense_id))\
                    .eq('business_id', business_id)\
                    .execute()
                
                if update_response.data:
                    flash('Expense updated successfully!', 'success')
                    return redirect(url_for('expenses.expenses_list'))
                else:
                    flash('Failed to update expense', 'danger')
            
            except Exception as e:
                flash(f'Error updating expense: {str(e)}', 'danger')
        
        # Get categories for dropdown
        categories = get_expense_categories()
        
        # Format date for input field
        if expense.get('expense_date'):
            expense_date = datetime.fromisoformat(expense['expense_date'].replace('Z', '+00:00'))
            expense['expense_date_formatted'] = expense_date.strftime('%Y-%m-%d')
        
        return render_template('expenses/edit.html',
                             expense=expense,
                             categories=categories,
                             title="Edit Expense")
    
    except Exception as e:
        flash(f'Error fetching expense: {str(e)}', 'danger')
        return redirect(url_for('expenses.expenses_list'))

@expenses_bp.route('/expenses/delete/<uuid:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    """Delete an expense"""
    # Get user's business_id
    business_id = get_user_business_id()
    if not business_id:
        flash('No business found for your account. Please set up your business first.', 'danger')
        return redirect(url_for('expenses.expenses_list'))
    
    try:
        # Delete expense
        response = supabase.table('expenses')\
            .delete()\
            .eq('id', str(expense_id))\
            .eq('business_id', business_id)\
            .execute()
        
        if response.data:
            flash('Expense deleted successfully!', 'success')
        else:
            flash('Failed to delete expense', 'danger')
    
    except Exception as e:
        flash(f'Error deleting expense: {str(e)}', 'danger')
    
    return redirect(url_for('expenses.expenses_list'))

@expenses_bp.route('/api/expenses/stats')
@login_required
def expenses_stats():
    """API endpoint for expense statistics"""
    try:
        # Get user's business_id
        business_id = get_user_business_id()
        if not business_id:
            return jsonify({'error': 'No business found'}), 400
        
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build query
        query = supabase.table('expenses')\
            .select('*')\
            .eq('business_id', business_id)
        
        if start_date:
            query = query.gte('expense_date', start_date)
        if end_date:
            query = query.lte('expense_date', end_date)
        
        response = query.execute()
        expenses = response.data
        
        # Calculate statistics
        stats = {
            'total_expenses': len(expenses),
            'total_amount': 0,
            'average_expense': 0,
            'by_category': {},
            'by_payment_method': {},
            'by_status': {},
            'recent_expenses': []
        }
        
        # Process expenses
        for expense in expenses:
            amount = float(expense.get('amount', 0))
            
            # Update totals
            stats['total_amount'] += amount
            
            # Group by category
            category = expense.get('category', 'Uncategorized')
            if category not in stats['by_category']:
                stats['by_category'][category] = 0
            stats['by_category'][category] += amount
            
            # Group by payment method
            payment_method = expense.get('payment_method', 'Cash')
            if payment_method not in stats['by_payment_method']:
                stats['by_payment_method'][payment_method] = 0
            stats['by_payment_method'][payment_method] += amount
            
            # Group by status
            status = expense.get('status', 'approved')
            if status not in stats['by_status']:
                stats['by_status'][status] = 0
            stats['by_status'][status] += amount
        
        # Calculate average
        if stats['total_expenses'] > 0:
            stats['average_expense'] = stats['total_amount'] / stats['total_expenses']
        
        # Get recent expenses (last 5)
        recent_response = supabase.table('expenses')\
            .select('*')\
            .eq('business_id', business_id)\
            .order('created_at', desc=True)\
            .limit(5)\
            .execute()
        
        stats['recent_expenses'] = recent_response.data[:5]
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_monthly_expense_totals(business_id):
    """Get monthly expense totals for the current year"""
    try:
        current_year = datetime.now().year
        start_date = f"{current_year}-01-01"
        end_date = f"{current_year}-12-31"
        
        response = supabase.table('expenses')\
            .select('expense_date, amount')\
            .eq('business_id', business_id)\
            .gte('expense_date', start_date)\
            .lte('expense_date', end_date)\
            .execute()
        
        # Initialize monthly totals
        monthly_totals = {month: 0 for month in range(1, 13)}
        
        for expense in response.data:
            try:
                expense_date = datetime.fromisoformat(expense['expense_date'].replace('Z', '+00:00'))
                month = expense_date.month
                amount = float(expense.get('amount', 0))
                monthly_totals[month] += amount
            except:
                continue
        
        # Format for chart
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        chart_data = {
            'labels': months,
            'data': [monthly_totals[i] for i in range(1, 13)]
        }
        
        return chart_data
    
    except Exception as e:
        print(f"Error getting monthly totals: {e}")
        return {'labels': [], 'data': []}

def get_category_totals(business_id):
    """Get expense totals by category"""
    try:
        response = supabase.table('expenses')\
            .select('category, amount')\
            .eq('business_id', business_id)\
            .execute()
        
        category_totals = {}
        
        for expense in response.data:
            category = expense.get('category', 'Uncategorized')
            amount = float(expense.get('amount', 0))
            
            if category not in category_totals:
                category_totals[category] = 0
            
            category_totals[category] += amount
        
        # Sort by amount descending
        sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        
        # Format for chart
        chart_data = {
            'labels': [cat for cat, _ in sorted_categories],
            'data': [amount for _, amount in sorted_categories]
        }
        
        return chart_data
    
    except Exception as e:
        print(f"Error getting category totals: {e}")
        return {'labels': [], 'data': []}

def get_expense_categories():
    """Get list of expense categories"""
    return [
        'Office Supplies',
        'Rent',
        'Utilities',
        'Salaries',
        'Marketing',
        'Travel',
        'Equipment',
        'Software',
        'Maintenance',
        'Insurance',
        'Taxes',
        'Professional Fees',
        'Entertainment',
        'Shipping',
        'Other'
    ]