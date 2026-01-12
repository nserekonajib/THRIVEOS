from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from routes.auth import login_required
from supabase import create_client
from config import Config
import json

# Create Supabase client
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

settings_bp = Blueprint('settings', __name__)

def get_user_business_id():
    """Get the business_id for the current user from session"""
    return session.get('business_id')

def get_pesapal_settings(business_id):
    """Get PesaPal settings for the business"""
    try:
        response = supabase.table('business_settings').select(
            'id, pesapal_consumer_key, pesapal_consumer_secret, pesapal_ipn_url, updated_at'
        ).eq('business_id', business_id).limit(1).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error getting PesaPal settings: {e}")
        return None

def save_pesapal_settings(business_id, consumer_key, consumer_secret, ipn_url):
    """Save PesaPal settings for the business"""
    try:
        # Check if settings already exist
        existing = get_pesapal_settings(business_id)
        
        if existing:
            # Update existing settings
            response = supabase.table('business_settings').update({
                'pesapal_consumer_key': consumer_key,
                'pesapal_consumer_secret': consumer_secret,
                'pesapal_ipn_url': ipn_url,
                'updated_at': 'now()'
            }).eq('id', existing['id']).execute()
        else:
            # Create new settings
            response = supabase.table('business_settings').insert({
                'business_id': business_id,
                'pesapal_consumer_key': consumer_key,
                'pesapal_consumer_secret': consumer_secret,
                'pesapal_ipn_url': ipn_url,
                'created_at': 'now()',
                'updated_at': 'now()'
            }).execute()
        
        return response.data is not None
    except Exception as e:
        print(f"Error saving PesaPal settings: {e}")
        return False

@settings_bp.route('/settings/payment-gateways')
@login_required
def payment_gateways():
    """Payment gateway settings page"""
    business_id = get_user_business_id()
    if not business_id:
        flash('No business found for your account.', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    # Get current settings
    current_settings = get_pesapal_settings(business_id)
    
    return render_template('settings/payment_gateways.html',
                         title="Payment Gateway Settings",
                         current_settings=current_settings)

@settings_bp.route('/settings/payment-gateways/update', methods=['POST'])
@login_required
def update_payment_gateways():
    """Update payment gateway settings"""
    business_id = get_user_business_id()
    if not business_id:
        flash('No business found for your account.', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    # Get form data
    consumer_key = request.form.get('pesapal_consumer_key', '').strip()
    consumer_secret = request.form.get('pesapal_consumer_secret', '').strip()
    ipn_url = request.form.get('pesapal_ipn_url', '').strip()
    
    # Validate required fields
    if not consumer_key or not consumer_secret:
        flash('Consumer Key and Consumer Secret are required.', 'danger')
        return redirect(url_for('settings.payment_gateways'))
    
    # Validate IPN URL format if provided
    if ipn_url and not (ipn_url.startswith('http://') or ipn_url.startswith('https://')):
        flash('IPN URL must start with http:// or https://', 'danger')
        return redirect(url_for('settings.payment_gateways'))
    
    # Save settings
    success = save_pesapal_settings(business_id, consumer_key, consumer_secret, ipn_url)
    
    if success:
        flash('Payment gateway settings updated successfully!', 'success')
    else:
        flash('Failed to update payment gateway settings.', 'danger')
    
    return redirect(url_for('settings.payment_gateways'))

@settings_bp.route('/settings')
@login_required
def settings_index():
    """Main settings page"""
    return render_template('settings/index.html', title="Settings")