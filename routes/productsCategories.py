# routes/productsCategories.py
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, current_app
from functools import wraps
import json
from datetime import datetime, date
from decimal import Decimal
import uuid
from werkzeug.utils import secure_filename
import os
from urllib.parse import unquote

from routes.auth import get_utc_now, admin_required, get_supabase
from config import Config
from cloudinary_utils import upload_to_cloudinary, delete_from_cloudinary, optimize_image_url, get_image_thumbnail

products_bp = Blueprint('products_inventory', __name__, url_prefix='/products-inventory')

# Decorator to require specific role(s)

def require_business_context(f):
    """Decorator to ensure business_id is set"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'business_id' not in session or not session['business_id']:
            flash('Business context required. Please log in again.', 'error')
            return redirect(url_for('auth.logout'))  # Force re-login
        return f(*args, **kwargs)
    return decorated_function


def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('auth.login'))
            
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


# Helper function to create audit log entries
def create_audit_log(product_id, action_type, field_name=None, old_value=None, new_value=None, notes=None):
    """Create an audit log entry"""
    try:
        supabase = get_supabase()
        user_id = session.get('user_id')
        business_id = session.get('business_id')
        
        if not business_id or not product_id:
            return False
        
        audit_data = {
            'id': str(uuid.uuid4()),
            'business_id': business_id,
            'product_id': product_id,
            'user_id': user_id,
            'action_type': action_type,
            'field_name': field_name,
            'old_value': str(old_value)[:500] if old_value is not None else None,  # Limit length
            'new_value': str(new_value)[:500] if new_value is not None else None,  # Limit length
            'notes': notes[:1000] if notes else None,  # Limit length
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.user_agent.string[:500] if request and request.user_agent else None,
            'created_at': get_utc_now().isoformat()
        }
        
        supabase.table('product_audit_logs').insert(audit_data).execute()
        return True
        
    except Exception as e:
        print(f"❌ Error creating audit log: {str(e)}")
        return False
    
    
# Categories Routes
@products_bp.route('/categories')
@admin_required
def categories():
    """Display all categories"""
    try:
        supabase = get_supabase()
        
        # Get categories with business context
        response = supabase.table('categories').select('*').execute()
        categories = response.data if response.data else []
        
        return render_template('products/categories.html', categories=categories)
    except Exception as e:
        flash(f'Error loading categories: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    

@products_bp.route('/categories/create', methods=['GET', 'POST'])
@admin_required
def create_category():
    """Create a new category"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Category name is required', 'error')
                return render_template('products/create_category.html')
            
            supabase = get_supabase()
            user_id = session.get('user_id')
            business_id = session.get('business_id')
            
            # Check if category already exists
            check_response = supabase.table('categories').select('id').eq('name', name).execute()
            if check_response.data:
                flash('Category with this name already exists', 'error')
                return render_template('products/create_category.html')
            
            # Create category
            category_data = {
                'id': str(uuid.uuid4()),
                'name': name,
                'description': description,
                'created_by': user_id,
                'business_id': business_id,
                'created_at': get_utc_now().isoformat(),
                'updated_at': get_utc_now().isoformat()
            }
            
            response = supabase.table('categories').insert(category_data).execute()
            
            if response.data:
                flash('Category created successfully', 'success')
                return redirect(url_for('products_inventory.categories'))
            else:
                flash('Failed to create category', 'error')
                
        except Exception as e:
            flash(f'Error creating category: {str(e)}', 'error')
    
    return render_template('products/create_category.html')

@products_bp.route('/categories/edit/<category_id>', methods=['GET', 'POST'])
@admin_required
def edit_category(category_id):
    """Edit an existing category"""
    try:
        supabase = get_supabase()
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Category name is required', 'error')
                return redirect(url_for('products_inventory.edit_category', category_id=category_id))
            
            # Check if new name conflicts with other categories
            check_response = supabase.table('categories') \
                .select('id') \
                .eq('name', name) \
                .neq('id', category_id) \
                .execute()
            
            if check_response.data:
                flash('Another category with this name already exists', 'error')
                return redirect(url_for('products_inventory.edit_category', category_id=category_id))
            
            # Update category
            update_data = {
                'name': name,
                'description': description,
                'updated_at': get_utc_now().isoformat()
            }
            
            response = supabase.table('categories') \
                .update(update_data) \
                .eq('id', category_id) \
                .execute()
            
            if response.data:
                flash('Category updated successfully', 'success')
                return redirect(url_for('products_inventory.categories'))
            else:
                flash('Failed to update category', 'error')
        
        # GET request - load category data
        response = supabase.table('categories').select('*').eq('id', category_id).execute()
        
        if not response.data:
            flash('Category not found', 'error')
            return redirect(url_for('products_inventory.categories'))
        
        category = response.data[0]
        return render_template('products/edit_category.html', category=category)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('products_inventory.categories'))

@products_bp.route('/categories/delete/<category_id>', methods=['POST'])
@admin_required
def delete_category(category_id):
    """Delete a category"""
    try:
        supabase = get_supabase()
        
        # Check if category is used by any products
        products_response = supabase.table('products') \
            .select('id') \
            .eq('category_id', category_id) \
            .limit(1) \
            .execute()
        
        if products_response.data:
            flash('Cannot delete category that is assigned to products', 'error')
            return redirect(url_for('products_inventory.categories'))
        
        # Delete category
        response = supabase.table('categories') \
            .delete() \
            .eq('id', category_id) \
            .execute()
        
        if response.data:
            flash('Category deleted successfully', 'success')
        else:
            flash('Failed to delete category', 'error')
            
    except Exception as e:
        flash(f'Error deleting category: {str(e)}', 'error')
    
    return redirect(url_for('products_inventory.categories'))

@products_bp.route('/categories/api/list', methods=['GET'])
@admin_required
def get_categories_api():
    """API endpoint to get categories list for dropdowns"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        response = supabase.table('categories') \
            .select('id, name') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        return jsonify({
            'success': True,
            'categories': response.data if response.data else []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Products Routes
@products_bp.route('/dashboard')
@admin_required
def products_dashboards():
    return products_dashboard()


@products_bp.route('/')
@admin_required
def products_dashboard():
    """Products dashboard with overview"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        if not business_id:
            flash('Business not found. Please contact administrator.', 'error')
            return redirect(url_for('dashboard'))
        
        # Get all products
        products_response = supabase.table('products') \
            .select('*') \
            .eq('business_id', business_id) \
            .execute()
        
        products = products_response.data if products_response.data else []
        
        # Calculate stock levels for each product
        for product in products:
            lots_response = supabase.table('product_lots') \
                .select('quantity') \
                .eq('product_id', product['id']) \
                .execute()
            
            total_stock = sum(lot['quantity'] for lot in lots_response.data) if lots_response.data else 0
            product['current_stock'] = total_stock
        
        # Get recent products (last 10)
        recent_products = sorted(products, key=lambda x: x.get('created_at', ''), reverse=True)[:10]
        
        # Get low stock items
        low_stock_items = [
            p for p in products 
            if p['current_stock'] <= p.get('reorder_level', 0) and p['current_stock'] > 0
        ]
        
        # Get out of stock items
        out_of_stock_items = [p for p in products if p['current_stock'] == 0]
        
        # Counts
        total_products = len(products)
        low_stock_count = len(low_stock_items)
        out_of_stock_count = len(out_of_stock_items)
        in_stock_count = total_products - low_stock_count - out_of_stock_count
        
        # Get categories
        categories_response = supabase.table('categories') \
            .select('*') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        categories = categories_response.data[:5] if categories_response.data else []  # Top 5
        
        # Get suppliers
        suppliers_response = supabase.table('suppliers') \
            .select('*') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        suppliers = suppliers_response.data[:5] if suppliers_response.data else []  # Top 5
        
        return render_template('products/dashboard.html', 
                             total_products=total_products,
                             low_stock_count=low_stock_count,
                             total_categories=len(categories_response.data) if categories_response.data else 0,
                             total_suppliers=len(suppliers_response.data) if suppliers_response.data else 0,
                             recent_products=recent_products,
                             low_stock_items=low_stock_items[:5],  # Top 5 low stock
                             categories=categories,
                             suppliers=suppliers,
                             in_stock_count=in_stock_count,
                             out_of_stock_count=out_of_stock_count)
        
    except Exception as e:
        print(f"❌ Error in products_dashboard: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    
@products_bp.route('/list')
@admin_required
def products_list():
    """Display all products"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Check if business_id exists
        if not business_id:
            flash('Business not found. Please contact administrator.', 'error')
            return redirect(url_for('dashboard'))
        
        # Get all products
        products_response = supabase.table('products') \
            .select('*') \
            .eq('business_id', business_id) \
            .order('created_at', desc=True) \
            .execute()
        
        products = products_response.data if products_response.data else []
        
        # Get categories for these products
        category_ids = [p['category_id'] for p in products if p.get('category_id')]
        categories_dict = {}
        
        if category_ids:
            categories_response = supabase.table('categories') \
                .select('*') \
                .in_('id', category_ids) \
                .execute()
            
            if categories_response.data:
                for cat in categories_response.data:
                    categories_dict[cat['id']] = cat
        
        # Get suppliers
        supplier_ids = [p['supplier_id'] for p in products if p.get('supplier_id')]
        suppliers_dict = {}
        
        if supplier_ids:
            suppliers_response = supabase.table('suppliers') \
                .select('*') \
                .in_('id', supplier_ids) \
                .execute()
            
            if suppliers_response.data:
                for sup in suppliers_response.data:
                    suppliers_dict[sup['id']] = sup
        
        # Get stock quantities for all products
        product_ids = [p['id'] for p in products]
        stock_dict = {}
        
        if product_ids:
            # Get all lots for these products
            lots_response = supabase.table('product_lots') \
                .select('product_id, quantity') \
                .in_('product_id', product_ids) \
                .execute()
            
            if lots_response.data:
                # Sum up quantities per product
                for lot in lots_response.data:
                    product_id = lot['product_id']
                    if product_id not in stock_dict:
                        stock_dict[product_id] = 0
                    stock_dict[product_id] += lot['quantity']
        
        # Add category, supplier names, and stock to products
        for product in products:
            # Add category name
            if product.get('category_id') and product['category_id'] in categories_dict:
                product['category_name'] = categories_dict[product['category_id']]['name']
            else:
                product['category_name'] = None
            
            # Add supplier name
            if product.get('supplier_id') and product['supplier_id'] in suppliers_dict:
                product['supplier_name'] = suppliers_dict[product['supplier_id']]['name']
            else:
                product['supplier_name'] = None
            
            # Add stock quantity
            product_id = product['id']
            product['stock_level'] = stock_dict.get(product_id, 0)
            
            # Add product_lots for template compatibility (empty array if none)
            product['product_lots'] = []
        
        return render_template('products/products_list.html', products=products)
        
    except Exception as e:
        print(f"❌ Error in products_list: {str(e)}")
        flash(f'Error loading products: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@products_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_product():
    """Create a new product with image upload"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        user_id = session.get('user_id')
        
        if request.method == 'POST':
            # Get form data
            name = request.form.get('name', '').strip()
            sku = request.form.get('sku', '').strip()
            description = request.form.get('description', '').strip()
            category_id = request.form.get('category_id')
            supplier_id = request.form.get('supplier_id')
            cost_price = request.form.get('cost_price', '0')
            selling_price = request.form.get('selling_price', '0')
            tax_rate = request.form.get('tax_rate', '0')
            unit = request.form.get('unit', '').strip()
            barcode = request.form.get('barcode', '').strip()
            initial_stock = request.form.get('initial_stock', '0')
            reorder_level = request.form.get('reorder_level', '0')
            
            # Validate required fields
            if not name or not selling_price:
                flash('Product name and selling price are required', 'error')
                return redirect(url_for('products_inventory.create_product'))
            
            # Check if SKU already exists
            if sku:
                check_response = supabase.table('products') \
                    .select('id') \
                    .eq('sku', sku) \
                    .eq('business_id', business_id) \
                    .execute()
                
                if check_response.data:
                    flash('Product with this SKU already exists', 'error')
                    return redirect(url_for('products_inventory.create_product'))
            
            # Convert prices to Decimal
            try:
                cost_price_decimal = Decimal(cost_price) if cost_price else Decimal('0')
                selling_price_decimal = Decimal(selling_price) if selling_price else Decimal('0')
                tax_rate_decimal = Decimal(tax_rate) if tax_rate else Decimal('0')
            except:
                flash('Invalid price format', 'error')
                return redirect(url_for('products_inventory.create_product'))
            
            # Handle image upload
            image_url = None
            cloudinary_public_id = None
            
            if 'image' in request.files:
                image_file = request.files['image']
                if image_file and image_file.filename:
                    # Check file size (limit to 10MB)
                    image_file.seek(0, os.SEEK_END)
                    file_size = image_file.tell()
                    image_file.seek(0)
                    
                    if file_size > 10 * 1024 * 1024:  # 10MB
                        flash('Image size should be less than 10MB', 'error')
                        return redirect(url_for('products_inventory.create_product'))
                    
                    # Check file extension
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(image_file.filename)
                    if '.' in filename:
                        ext = filename.rsplit('.', 1)[1].lower()
                        if ext not in allowed_extensions:
                            flash('Allowed image formats: PNG, JPG, JPEG, GIF, WEBP', 'error')
                            return redirect(url_for('products_inventory.create_product'))
                    
                    # Upload to Cloudinary
                    upload_result = upload_to_cloudinary(
                        image_file,
                        folder=f"businesses/{business_id}/products"
                    )
                    
                    if upload_result:
                        image_url = optimize_image_url(upload_result['url'])
                        cloudinary_public_id = upload_result['public_id']
                    else:
                        flash('Failed to upload image. Please try again.', 'error')
                        return redirect(url_for('products_inventory.create_product'))
            
            # Create product
            product_id = str(uuid.uuid4())
            product_data = {
                'id': product_id,
                'business_id': business_id,
                'name': name,
                'sku': sku,
                'description': description,
                'category_id': category_id,
                'supplier_id': supplier_id,
                'cost_price': float(cost_price_decimal),
                'selling_price': float(selling_price_decimal),
                'tax_rate': float(tax_rate_decimal),
                'unit': unit,
                'barcode': barcode,
                'image_url': image_url,
                'cloudinary_public_id': cloudinary_public_id,
                'reorder_level': int(reorder_level) if reorder_level else 0,
                'created_by': user_id,
                'created_at': get_utc_now().isoformat(),
                'updated_at': get_utc_now().isoformat()
            }
            
            # Insert product
            product_response = supabase.table('products').insert(product_data).execute()
            
            if initial_stock and int(initial_stock) > 0:
                # Create initial stock lot
                lot_data = {
                    'id': str(uuid.uuid4()),
                    'product_id': product_id,
                    'lot_number': f'INIT-{datetime.now().strftime("%Y%m%d")}',
                    'quantity': int(initial_stock),
                    'cost_price': float(cost_price_decimal),
                    'created_by': user_id,
                    'created_at': get_utc_now().isoformat()
                }
                
                lot_response = supabase.table('product_lots').insert(lot_data).execute()
                
                # Record inventory movement
                movement_data = {
                    'id': str(uuid.uuid4()),
                    'product_id': product_id,
                    'lot_id': lot_response.data[0]['id'] if lot_response.data else None,
                    'movement_type': 'IN',
                    'quantity': int(initial_stock),
                    'reference': 'Initial Stock',
                    'created_by': user_id,
                    'created_at': get_utc_now().isoformat()
                }
                
                supabase.table('inventory_movements').insert(movement_data).execute()
            
            flash('Product created successfully', 'success')
            return redirect(url_for('products_inventory.products_list'))
        
        # GET request - load form data
        categories_response = supabase.table('categories') \
            .select('id, name') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        suppliers_response = supabase.table('suppliers') \
            .select('id, name') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        categories = categories_response.data if categories_response.data else []
        suppliers = suppliers_response.data if suppliers_response.data else []
        
        return render_template('products/create_product.html', 
                             categories=categories, 
                             suppliers=suppliers)
        
    except Exception as e:
        flash(f'Error creating product: {str(e)}', 'error')
        return redirect(url_for('products_inventory.products_list'))
    
    
@products_bp.route('/edit/<product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    """Edit an existing product with image handling"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        if request.method == 'POST':
            # Get current product data first for audit logging
            current_response = supabase.table('products') \
                .select('*') \
                .eq('id', product_id) \
                .eq('business_id', business_id) \
                .execute()
            
            if not current_response.data:
                flash('Product not found', 'error')
                return redirect(url_for('products_inventory.products_list'))
            
            current_product = current_response.data[0]
            
            # Get form data
            name = request.form.get('name', '').strip()
            sku = request.form.get('sku', '').strip()
            description = request.form.get('description', '').strip()
            category_id = request.form.get('category_id')
            supplier_id = request.form.get('supplier_id')
            cost_price = request.form.get('cost_price', '0')
            selling_price = request.form.get('selling_price', '0')
            tax_rate = request.form.get('tax_rate', '0')
            unit = request.form.get('unit', '').strip()
            barcode = request.form.get('barcode', '').strip()
            reorder_level = request.form.get('reorder_level', '0')
            remove_image = request.form.get('remove_image') == 'true'
            
            # Validate
            if not name or not selling_price:
                flash('Product name and selling price are required', 'error')
                return redirect(url_for('products_inventory.edit_product', product_id=product_id))
            
            # Check SKU uniqueness
            if sku and sku != current_product.get('sku'):
                check_response = supabase.table('products') \
                    .select('id') \
                    .eq('sku', sku) \
                    .eq('business_id', business_id) \
                    .neq('id', product_id) \
                    .execute()
                
                if check_response.data:
                    flash('Another product with this SKU already exists', 'error')
                    return redirect(url_for('products_inventory.edit_product', product_id=product_id))
            
            # Convert prices
            try:
                cost_price_decimal = Decimal(cost_price) if cost_price else Decimal('0')
                selling_price_decimal = Decimal(selling_price) if selling_price else Decimal('0')
                tax_rate_decimal = Decimal(tax_rate) if tax_rate else Decimal('0')
            except:
                flash('Invalid price format', 'error')
                return redirect(url_for('products_inventory.edit_product', product_id=product_id))
            
            # Handle image updates
            current_image_url = current_product.get('image_url')
            current_public_id = current_product.get('cloudinary_public_id')
            
            new_image_url = current_image_url
            new_public_id = current_public_id
            
            if remove_image and current_public_id:
                # Delete old image from Cloudinary
                if delete_from_cloudinary(current_public_id):
                    new_image_url = None
                    new_public_id = None
                    # Audit log for image removal
                    create_audit_log(
                        product_id=product_id,
                        action_type='IMAGE_REMOVED',
                        notes='Product image was removed'
                    )
            
            if 'image' in request.files:
                image_file = request.files['image']
                if image_file and image_file.filename:
                    # Check file size and type
                    image_file.seek(0, os.SEEK_END)
                    file_size = image_file.tell()
                    image_file.seek(0)
                    
                    if file_size > 10 * 1024 * 1024:
                        flash('Image size should be less than 10MB', 'error')
                        return redirect(url_for('products_inventory.edit_product', product_id=product_id))
                    
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = secure_filename(image_file.filename)
                    if '.' in filename:
                        ext = filename.rsplit('.', 1)[1].lower()
                        if ext not in allowed_extensions:
                            flash('Allowed image formats: PNG, JPG, JPEG, GIF, WEBP', 'error')
                            return redirect(url_for('products_inventory.edit_product', product_id=product_id))
                    
                    # Delete old image if exists
                    if current_public_id:
                        delete_from_cloudinary(current_public_id)
                        # Audit log for image deletion
                        create_audit_log(
                            product_id=product_id,
                            action_type='IMAGE_DELETED',
                            notes='Old product image was deleted'
                        )
                    
                    # Upload new image
                    upload_result = upload_to_cloudinary(
                        image_file,
                        folder=f"businesses/{business_id}/products"
                    )
                    
                    if upload_result:
                        new_image_url = optimize_image_url(upload_result['url'])
                        new_public_id = upload_result['public_id']
                        # Audit log for image upload
                        create_audit_log(
                            product_id=product_id,
                            action_type='IMAGE_UPLOADED',
                            notes='New product image was uploaded'
                        )
                    else:
                        flash('Failed to upload image. Please try again.', 'error')
                        return redirect(url_for('products_inventory.edit_product', product_id=product_id))
            
            # Update product
            update_data = {
                'name': name,
                'sku': sku,
                'description': description,
                'category_id': category_id,
                'supplier_id': supplier_id,
                'cost_price': float(cost_price_decimal),
                'selling_price': float(selling_price_decimal),
                'tax_rate': float(tax_rate_decimal),
                'unit': unit,
                'barcode': barcode,
                'image_url': new_image_url,
                'cloudinary_public_id': new_public_id,
                'reorder_level': int(reorder_level) if reorder_level else 0,
                'updated_at': get_utc_now().isoformat()
            }
            
            # Create audit logs for changed fields
            changed_fields = []
            for field, new_value in update_data.items():
                old_value = current_product.get(field)
                if old_value != new_value and field not in ['updated_at', 'cloudinary_public_id']:
                    changed_fields.append(field)
                    create_audit_log(
                        product_id=product_id,
                        action_type='FIELD_UPDATED',
                        field_name=field,
                        old_value=old_value,
                        new_value=new_value,
                        notes=f'{field.replace("_", " ").title()} updated'
                    )
            
            response = supabase.table('products') \
                .update(update_data) \
                .eq('id', product_id) \
                .eq('business_id', business_id) \
                .execute()
            
            if response.data:
                if changed_fields:
                    flash(f'Product updated successfully. {len(changed_fields)} field(s) changed.', 'success')
                else:
                    flash('Product updated successfully', 'success')
                return redirect(url_for('products_inventory.products_list'))
            else:
                flash('Failed to update product', 'error')
        
        # GET request - load product data
        product_response = supabase.table('products') \
            .select('*') \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if not product_response.data:
            flash('Product not found', 'error')
            return redirect(url_for('products_inventory.products_list'))
        
        product = product_response.data[0]
        
        # Load categories and suppliers
        categories_response = supabase.table('categories') \
            .select('id, name') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        suppliers_response = supabase.table('suppliers') \
            .select('id, name') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        categories = categories_response.data if categories_response.data else []
        suppliers = suppliers_response.data if suppliers_response.data else []
        
        return render_template('products/edit_product.html', 
                             product=product, 
                             categories=categories, 
                             suppliers=suppliers)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('products_inventory.products_list'))


@products_bp.route('/delete/<product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    """Delete a product and its image"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get product to delete image
        product_response = supabase.table('products') \
            .select('image_url, cloudinary_public_id') \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .execute()
        
        # Delete image from Cloudinary
        if product_response.data:
            cloudinary_public_id = product_response.data[0].get('cloudinary_public_id')
            if cloudinary_public_id:
                delete_from_cloudinary(cloudinary_public_id)
        
        # Check if product has inventory
        lots_response = supabase.table('product_lots') \
            .select('quantity') \
            .eq('product_id', product_id) \
            .execute()
        
        total_stock = sum(lot['quantity'] for lot in lots_response.data) if lots_response.data else 0
        
        if total_stock > 0:
            flash('Cannot delete product with existing stock. Please adjust stock to zero first.', 'error')
            return redirect(url_for('products_inventory.products_list'))
        
        # Delete product (cascade will handle related records if foreign keys are set up)
        response = supabase.table('products') \
            .delete() \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if response.data:
            flash('Product deleted successfully', 'success')
        else:
            flash('Failed to delete product', 'error')
            
    except Exception as e:
        flash(f'Error deleting product: {str(e)}', 'error')
    
    return redirect(url_for('products_inventory.products_list'))

@products_bp.route('/api/upload-image', methods=['POST'])
@admin_required
def upload_image_api():
    """API endpoint for image upload (for AJAX)"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file'})
        
        image_file = request.files['image']
        if not image_file or not image_file.filename:
            return jsonify({'success': False, 'error': 'No selected file'})
        
        # Validate file size
        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            return jsonify({'success': False, 'error': 'File size exceeds 10MB limit'})
        
        # Check file extension
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        filename = secure_filename(image_file.filename)
        if '.' in filename:
            ext = filename.rsplit('.', 1)[1].lower()
            if ext not in allowed_extensions:
                return jsonify({'success': False, 'error': 'Invalid file type'})
        
        # Upload to Cloudinary
        business_id = session.get('business_id')
        upload_result = upload_to_cloudinary(
            image_file,
            folder=f"businesses/{business_id}/products/temp"
        )
        
        if upload_result:
            return jsonify({
                'success': True,
                'url': optimize_image_url(upload_result['url']),
                'public_id': upload_result['public_id']
            })
        else:
            return jsonify({'success': False, 'error': 'Upload failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Add this helper function to optimize images in templates
def optimize_product_images(products):
    """Add optimized thumbnail URLs to products for display"""
    for product in products:
        if product.get('image_url'):
            product['image_thumbnail'] = get_image_thumbnail(product['image_url'], 200, 200)
            product['image_medium'] = get_image_thumbnail(product['image_url'], 400, 400)
    return products


@products_bp.route('/view/<product_id>')
@admin_required
def view_product(product_id):
    """View product details"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get product
        product_response = supabase.table('products') \
            .select('*') \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if not product_response.data:
            flash('Product not found', 'error')
            return redirect(url_for('products_inventory.products_list'))
        
        product = product_response.data[0]
        
        # Get product lots
        lots_response = supabase.table('product_lots') \
            .select('*') \
            .eq('product_id', product_id) \
            .execute()
        
        product_lots = lots_response.data if lots_response.data else []
        
        # Calculate total stock from ALL lots (including newly created ones)
        total_stock = sum(lot['quantity'] for lot in product_lots)
        
        # Get category details separately
        if product.get('category_id'):
            cat_response = supabase.table('categories') \
                .select('*') \
                .eq('id', product['category_id']) \
                .execute()
            if cat_response.data:
                product['categories'] = cat_response.data[0]
        
        # Get supplier details separately
        if product.get('supplier_id'):
            sup_response = supabase.table('suppliers') \
                .select('*') \
                .eq('id', product['supplier_id']) \
                .execute()
            if sup_response.data:
                product['suppliers'] = sup_response.data[0]
        
        # Get inventory movements
        movements_response = supabase.table('inventory_movements') \
            .select('*') \
            .eq('product_id', product_id) \
            .order('created_at', desc=True) \
            .execute()
        
        inventory_movements = movements_response.data if movements_response.data else []
        
        return render_template('products/view_product.html', 
                             product=product,
                             product_lots=product_lots,
                             inventory_movements=inventory_movements,
                             total_stock=total_stock)
        
    except Exception as e:
        flash(f'Error loading product: {str(e)}', 'error')
        return redirect(url_for('products_inventory.products_list'))
    
    

@products_bp.route('/api/search', methods=['GET'])
@admin_required
def search_products_api():
    """API endpoint to search products"""
    try:
        query = request.args.get('q', '').strip()
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        if not query:
            return jsonify({'success': False, 'error': 'Search query required'})
        
        response = supabase.table('products') \
            .select('id, name, sku, selling_price, image_url') \
            .or_(f'name.ilike.%{query}%,sku.ilike.%{query}%,barcode.ilike.%{query}%') \
            .eq('business_id', business_id) \
            .limit(10) \
            .execute()
        
        return jsonify({
            'success': True,
            'products': response.data if response.data else []
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/api/stock-level/<product_id>', methods=['GET'])
@admin_required
def get_stock_level_api(product_id):
    """API endpoint to get current stock level"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Verify product belongs to business
        product_response = supabase.table('products') \
            .select('id') \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if not product_response.data:
            return jsonify({'success': False, 'error': 'Product not found'})
        
        # Get all lots for this product
        lots_response = supabase.table('product_lots') \
            .select('quantity') \
            .eq('product_id', product_id) \
            .execute()
        
        total_stock = sum(lot['quantity'] for lot in lots_response.data) if lots_response.data else 0
        
        return jsonify({
            'success': True,
            'stock_level': total_stock
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Inventory Management Routes
@products_bp.route('/inventory/adjust', methods=['POST'])
@admin_required
def adjust_inventory():
    """Adjust inventory stock"""
    try:
        product_id = request.form.get('product_id')
        adjustment_type = request.form.get('adjustment_type')  # IN or OUT
        quantity = int(request.form.get('quantity', 0))
        reason = request.form.get('reason', '').strip()
        lot_id = request.form.get('lot_id')
        
        if not product_id or not adjustment_type or quantity <= 0:
            flash('Invalid adjustment data', 'error')
            return redirect(url_for('products_inventory.products_list'))
        
        supabase = get_supabase()
        user_id = session.get('user_id')
        business_id = session.get('business_id')
        
        # Verify product exists and get current cost price
        product_response = supabase.table('products') \
            .select('id, name, cost_price') \
            .eq('id', product_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if not product_response.data:
            flash('Product not found', 'error')
            return redirect(url_for('products_inventory.products_list'))
        
        product = product_response.data[0]
        cost_price = product.get('cost_price', 0)
        
        # Get current total stock for audit log
        lots_response = supabase.table('product_lots') \
            .select('quantity') \
            .eq('product_id', product_id) \
            .execute()
        
        old_stock = sum(lot['quantity'] for lot in lots_response.data) if lots_response.data else 0
        
        # If no lot specified, create a new lot
        if not lot_id:
            lot_data = {
                'id': str(uuid.uuid4()),
                'product_id': product_id,
                'lot_number': f'ADJ-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                'quantity': quantity if adjustment_type == 'IN' else 0,
                'cost_price': cost_price,
                'created_by': user_id,
                'created_at': get_utc_now().isoformat(),
                'updated_at': get_utc_now().isoformat()
            }
            
            lot_response = supabase.table('product_lots').insert(lot_data).execute()
            if not lot_response.data:
                flash('Failed to create lot', 'error')
                return redirect(url_for('products_inventory.view_product', product_id=product_id))
            
            lot_id = lot_response.data[0]['id']
        else:
            # Update existing lot - Check if lot exists and belongs to product
            lot_response = supabase.table('product_lots') \
                .select('quantity') \
                .eq('id', lot_id) \
                .eq('product_id', product_id) \
                .execute()
            
            if not lot_response.data:
                flash('Lot not found', 'error')
                return redirect(url_for('products_inventory.view_product', product_id=product_id))
            
            current_lot_quantity = lot_response.data[0]['quantity']
            
            if adjustment_type == 'IN':
                # Increment lot quantity
                new_quantity = current_lot_quantity + quantity
                update_response = supabase.table('product_lots') \
                    .update({
                        'quantity': new_quantity,
                        'updated_at': get_utc_now().isoformat()
                    }) \
                    .eq('id', lot_id) \
                    .execute()
                
                if not update_response.data:
                    flash('Failed to update lot quantity', 'error')
                    return redirect(url_for('products_inventory.view_product', product_id=product_id))
            else:  # OUT
                # Check if enough stock in this specific lot
                if current_lot_quantity < quantity:
                    flash(f'Insufficient stock in selected lot. Available: {current_lot_quantity}', 'error')
                    return redirect(url_for('products_inventory.view_product', product_id=product_id))
                
                # Decrement lot quantity
                new_quantity = current_lot_quantity - quantity
                if new_quantity == 0:
                    # Delete lot if quantity becomes 0
                    supabase.table('product_lots').delete().eq('id', lot_id).execute()
                else:
                    update_response = supabase.table('product_lots') \
                        .update({
                            'quantity': new_quantity,
                            'updated_at': get_utc_now().isoformat()
                        }) \
                        .eq('id', lot_id) \
                        .execute()
                    
                    if not update_response.data:
                        flash('Failed to update lot quantity', 'error')
                        return redirect(url_for('products_inventory.view_product', product_id=product_id))
        
        # Get new total stock for audit log
        new_lots_response = supabase.table('product_lots') \
            .select('quantity') \
            .eq('product_id', product_id) \
            .execute()
        
        new_stock = sum(lot['quantity'] for lot in new_lots_response.data) if new_lots_response.data else 0
        
        # Record inventory movement
        movement_data = {
            'id': str(uuid.uuid4()),
            'product_id': product_id,
            'lot_id': lot_id,
            'movement_type': adjustment_type,
            'quantity': quantity,
            'reference': reason or 'Manual Adjustment',
            'created_by': user_id,
            'created_at': get_utc_now().isoformat(),
            'updated_at': get_utc_now().isoformat()
        }
        
        supabase.table('inventory_movements').insert(movement_data).execute()
        
        # Create audit log
        create_audit_log(
            product_id=product_id,
            action_type='STOCK_ADJUSTED',
            field_name='stock_quantity',
            old_value=old_stock,
            new_value=new_stock,
            notes=f'Stock {adjustment_type.lower()}: {quantity} units. Reason: {reason or "Manual adjustment"}'
        )
        
        flash(f'Inventory adjusted successfully: {adjustment_type} {quantity} units', 'success')
        return redirect(url_for('products_inventory.view_product', product_id=product_id))
        
    except Exception as e:
        print(f"❌ Error adjusting inventory: {str(e)}")
        flash(f'Error adjusting inventory: {str(e)}', 'error')
        return redirect(url_for('products_inventory.view_product', product_id=product_id))

@products_bp.route('/low-stock')
@admin_required
def low_stock_report():
    """Display products with low stock"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get all products with their stock levels
        products_response = supabase.table('products') \
            .select('*, product_lots(quantity)') \
            .eq('business_id', business_id) \
            .execute()
        
        low_stock_products = []
        
        for product in products_response.data if products_response.data else []:
            # Calculate total stock
            total_stock = sum(lot['quantity'] for lot in product.get('product_lots', []))
            
            # Check if stock is below reorder level
            reorder_level = product.get('reorder_level', 0)
            if total_stock <= reorder_level:
                product['current_stock'] = total_stock
                low_stock_products.append(product)
        
        return render_template('products/low_stock.html', products=low_stock_products)
        
    except Exception as e:
        flash(f'Error loading low stock report: {str(e)}', 'error')
        return redirect(url_for('products_inventory.products_list'))
@products_bp.route('/suppliers')
@admin_required
def suppliers_list():
    """Display all suppliers"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get all suppliers
        response = supabase.table('suppliers') \
            .select('*') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        suppliers = response.data if response.data else []
        
        # Get product count for each supplier
        for supplier in suppliers:
            # Count products for this supplier
            products_response = supabase.table('products') \
                .select('id', count='exact') \
                .eq('supplier_id', supplier['id']) \
                .eq('business_id', business_id) \
                .execute()
            
            supplier['product_count'] = products_response.count if hasattr(products_response, 'count') else 0
        
        return render_template('products/suppliers.html', suppliers=suppliers)
    except Exception as e:
        flash(f'Error loading suppliers: {str(e)}', 'error')
        print(f"❌ Error in suppliers_list: {str(e)}")
        return redirect(url_for('dashboard'))


@products_bp.route('/suppliers/create', methods=['GET', 'POST'])
@admin_required
def create_supplier():
    """Create a new supplier"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            contact = request.form.get('contact', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            address = request.form.get('address', '').strip()
            
            if not name:
                flash('Supplier name is required', 'error')
                return render_template('products/create_supplier.html')
            
            supabase = get_supabase()
            user_id = session.get('user_id')
            business_id = session.get('business_id')
            
            supplier_data = {
                'id': str(uuid.uuid4()),
                'business_id': business_id,
                'name': name,
                'contact': contact,
                'phone': phone,
                'email': email,
                'address': address,
                'created_by': user_id,
                'created_at': get_utc_now().isoformat(),
                'updated_at': get_utc_now().isoformat()
            }
            
            response = supabase.table('suppliers').insert(supplier_data).execute()
            
            if response.data:
                flash('Supplier created successfully', 'success')
                return redirect(url_for('products_inventory.suppliers_list'))
            else:
                flash('Failed to create supplier', 'error')
                
        except Exception as e:
            flash(f'Error creating supplier: {str(e)}', 'error')
    
    return render_template('products/create_supplier.html')

@products_bp.route('/suppliers/delete/<supplier_id>', methods=['POST'])
@admin_required
def delete_supplier(supplier_id):
    """Delete a supplier"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Check if supplier has products
        products_response = supabase.table('products') \
            .select('id') \
            .eq('supplier_id', supplier_id) \
            .eq('business_id', business_id) \
            .limit(1) \
            .execute()
        
        if products_response.data:
            flash('Cannot delete supplier that has products assigned', 'error')
            return redirect(url_for('products_inventory.suppliers_list'))
        
        response = supabase.table('suppliers') \
            .delete() \
            .eq('id', supplier_id) \
            .eq('business_id', business_id) \
            .execute()
        
        if response.data:
            flash('Supplier deleted successfully', 'success')
        else:
            flash('Failed to delete supplier', 'error')
            
    except Exception as e:
        flash(f'Error deleting supplier: {str(e)}', 'error')
    
    return redirect(url_for('products_inventory.suppliers_list'))


@products_bp.route('/audit-logs')
@admin_required
def product_audit_logs():
    """Display product audit logs with filtering"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get filter parameters
        product_id = request.args.get('product_id', '')
        action_type = request.args.get('action_type', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        search_query = request.args.get('search', '')
        
        # Build query
        query = supabase.table('product_audit_logs').select('*, products(name, sku), users(email, first_name, last_name)')
        
        # Apply filters
        if business_id:
            query = query.eq('business_id', business_id)
        
        if product_id:
            query = query.eq('product_id', product_id)
        
        if action_type:
            query = query.eq('action_type', action_type)
        
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00')
        
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59')
        
        if search_query:
            query = query.or_(f'notes.ilike.%{search_query}%,old_value.ilike.%{search_query}%,new_value.ilike.%{search_query}%')
        
        # Order by creation date (newest first)
        query = query.order('created_at', desc=True)
        
        # Execute query
        response = query.execute()
        audit_logs = response.data if response.data else []
        
        # Get products for filter dropdown
        products_response = supabase.table('products') \
            .select('id, name, sku') \
            .eq('business_id', business_id) \
            .order('name') \
            .execute()
        
        products = products_response.data if products_response.data else []
        
        # Get unique action types for filter
        action_types = set()
        for log in audit_logs:
            if log.get('action_type'):
                action_types.add(log['action_type'])
        
        return render_template('products/audit_logs.html',
                             audit_logs=audit_logs,
                             products=products,
                             action_types=sorted(action_types),
                             filters={
                                 'product_id': product_id,
                                 'action_type': action_type,
                                 'start_date': start_date,
                                 'end_date': end_date,
                                 'search': search_query
                             })
        
    except Exception as e:
        print(f"❌ Error loading audit logs: {str(e)}")
        flash(f'Error loading audit logs: {str(e)}', 'error')
        return redirect(url_for('products_inventory.products_dashboard'))


@products_bp.route('/audit-logs/export', methods=['GET'])
@admin_required
def export_audit_logs():
    """Export audit logs to CSV"""
    try:
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Get filter parameters
        product_id = request.args.get('product_id', '')
        action_type = request.args.get('action_type', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query
        query = supabase.table('product_audit_logs').select('*, products(name, sku), users(email, first_name, last_name)')
        
        # Apply filters
        if business_id:
            query = query.eq('business_id', business_id)
        
        if product_id:
            query = query.eq('product_id', product_id)
        
        if action_type:
            query = query.eq('action_type', action_type)
        
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00')
        
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59')
        
        # Order by creation date
        query = query.order('created_at', desc=True)
        
        # Execute query
        response = query.execute()
        audit_logs = response.data if response.data else []
        
        # Create CSV
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Date & Time', 'Product', 'SKU', 'Action Type', 'Field Changed',
            'Old Value', 'New Value', 'User', 'IP Address', 'Notes'
        ])
        
        # Write data
        for log in audit_logs:
            product_name = log.get('products', {}).get('name', 'N/A')
            sku = log.get('products', {}).get('sku', 'N/A')
            user_email = log.get('users', {}).get('email', 'System')
            user_name = f"{log.get('users', {}).get('first_name', '')} {log.get('users', {}).get('last_name', '')}".strip()
            user_display = user_name if user_name else user_email
            
            writer.writerow([
                log.get('created_at', ''),
                product_name,
                sku,
                log.get('action_type', ''),
                log.get('field_name', ''),
                log.get('old_value', '')[:100],  # Limit length
                log.get('new_value', '')[:100],  # Limit length
                user_display,
                log.get('ip_address', ''),
                log.get('notes', '')[:200]  # Limit length
            ])
        
        # Prepare response
        from flask import Response
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment;filename=product_audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
        
    except Exception as e:
        print(f"❌ Error exporting audit logs: {str(e)}")
        flash(f'Error exporting audit logs: {str(e)}', 'error')
        return redirect(url_for('products_inventory.product_audit_logs'))


@products_bp.route('/audit-logs/clear-old', methods=['POST'])
@admin_required
def clear_old_audit_logs():
    """Clear audit logs older than specified days"""
    try:
        days = int(request.form.get('days', 90))
        
        if days < 30:
            flash('Minimum retention period is 30 days', 'error')
            return redirect(url_for('products_inventory.product_audit_logs'))
        
        supabase = get_supabase()
        business_id = session.get('business_id')
        
        # Calculate cutoff date
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Delete old logs
        response = supabase.table('product_audit_logs') \
            .delete() \
            .eq('business_id', business_id) \
            .lt('created_at', cutoff_date.isoformat()) \
            .execute()
        
        deleted_count = len(response.data) if response.data else 0
        
        flash(f'Cleared {deleted_count} audit logs older than {days} days', 'success')
        return redirect(url_for('products_inventory.product_audit_logs'))
        
    except Exception as e:
        print(f"❌ Error clearing audit logs: {str(e)}")
        flash(f'Error clearing audit logs: {str(e)}', 'error')
        return redirect(url_for('products_inventory.product_audit_logs'))

