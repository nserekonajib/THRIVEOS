
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from config import Config
import os
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()
def send_email(to_email, subject, html_content, text_content=None, from_email=None):
    """
    Send an email using SMTP
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
        from_email: Sender email address (uses config if None)
    """
    try:
        # Email configuration
        smtp_server = os.getenv('SMTP_SERVER') 
        smtp_port = os.getenv('SMTP_PORT')
        username = os.getenv('EMAIL_ADDRESS')
        password = os.getenv('EMAIL_PASSWORD')
        from_addr = 'nserekonajib3@gmail.com'
        
        if not all([smtp_server, username, password]):
            print("❌ Email configuration missing")
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to_email
        msg['Date'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
        
        # Add text part
        if text_content:
            text_part = MIMEText(text_content, 'plain')
            msg.attach(text_part)
        
        # Add HTML part
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if Config.MAIL_USE_TLS:
                server.starttls()
            server.login(username, password)
            server.send_message(msg)
        
        print(f"✅ Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False

def generate_reorder_alert_email(business_info, low_stock_products, logo_url=None):
    """
    Generate HTML email for reorder alerts
    
    Args:
        business_info: Dict with business information
        low_stock_products: List of products with low stock
        logo_url: URL of business logo
    
    Returns:
        str: HTML email content
    """
    business_name = business_info.get('business_name', 'Your Business')
    business_email = business_info.get('business_email', '')
    business_phone = business_info.get('business_phone', '')
    
    # Calculate totals
    total_low_stock = len(low_stock_products)
    total_critical = sum(1 for p in low_stock_products if p.get('current_stock', 0) == 0)
    
    # HTML email template
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reorder Alert - {business_name}</title>
        <style>
            /* Reset and base styles */
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f5f5f5;
                padding: 20px;
            }}
            
            .email-container {{
                max-width: 800px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            
            /* Header */
            .email-header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            
            .business-logo {{
                max-width: 150px;
                max-height: 60px;
                margin-bottom: 20px;
                border-radius: 8px;
            }}
            
            .header-title {{
                font-size: 24px;
                font-weight: 700;
                margin-bottom: 10px;
            }}
            
            .header-subtitle {{
                font-size: 16px;
                opacity: 0.9;
                margin-bottom: 20px;
            }}
            
            /* Alert Banner */
            .alert-banner {{
                background-color: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 20px;
                margin: 30px;
                border-radius: 8px;
                display: flex;
                align-items: center;
                gap: 15px;
            }}
            
            .alert-icon {{
                font-size: 24px;
                color: #856404;
            }}
            
            .alert-content h3 {{
                color: #856404;
                margin-bottom: 5px;
                font-size: 18px;
            }}
            
            /* Stats Cards */
            .stats-container {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                padding: 0 30px 30px;
            }}
            
            .stat-card {{
                background: white;
                border-radius: 10px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                border-top: 4px solid;
            }}
            
            .stat-card.total {{
                border-color: #667eea;
            }}
            
            .stat-card.critical {{
                border-color: #dc3545;
            }}
            
            .stat-card.attention {{
                border-color: #ffc107;
            }}
            
            .stat-number {{
                font-size: 36px;
                font-weight: 700;
                margin-bottom: 5px;
            }}
            
            .stat-label {{
                color: #666;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            /* Products Table */
            .products-section {{
                padding: 0 30px 30px;
            }}
            
            .section-title {{
                font-size: 20px;
                font-weight: 600;
                margin-bottom: 20px;
                color: #333;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .products-table {{
                width: 100%;
                border-collapse: collapse;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            
            .products-table th {{
                background-color: #f8f9fa;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #dee2e6;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .products-table td {{
                padding: 15px;
                border-bottom: 1px solid #e9ecef;
                vertical-align: middle;
            }}
            
            .products-table tr:last-child td {{
                border-bottom: none;
            }}
            
            .products-table tr:hover {{
                background-color: #f8f9fa;
            }}
            
            .product-name {{
                font-weight: 600;
                color: #333;
            }}
            
            .product-sku {{
                color: #6c757d;
                font-size: 13px;
                margin-top: 3px;
            }}
            
            .stock-badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .stock-out {{
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
            
            .stock-low {{
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
            }}
            
            .stock-warning {{
                background-color: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
            }}
            
            /* Actions */
            .actions-section {{
                padding: 30px;
                background-color: #f8f9fa;
                border-top: 1px solid #e9ecef;
                text-align: center;
            }}
            
            .action-button {{
                display: inline-block;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 14px 32px;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 16px;
                transition: transform 0.2s, box-shadow 0.2s;
                box-shadow: 0 4px 6px rgba(102, 126, 234, 0.2);
            }}
            
            .action-button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 12px rgba(102, 126, 234, 0.3);
                color: white;
                text-decoration: none;
            }}
            
            /* Footer */
            .email-footer {{
                padding: 30px;
                background-color: #f8f9fa;
                text-align: center;
                color: #6c757d;
                font-size: 14px;
                border-top: 1px solid #e9ecef;
            }}
            
            .footer-links {{
                margin-top: 15px;
            }}
            
            .footer-links a {{
                color: #667eea;
                text-decoration: none;
                margin: 0 10px;
            }}
            
            .footer-links a:hover {{
                text-decoration: underline;
            }}
            
            /* Responsive */
            @media (max-width: 600px) {{
                .stats-container {{
                    grid-template-columns: 1fr;
                }}
                
                .products-table {{
                    display: block;
                    overflow-x: auto;
                }}
                
                .email-header {{
                    padding: 20px;
                }}
                
                .header-title {{
                    font-size: 20px;
                }}
                
                .products-section,
                .actions-section,
                .email-footer {{
                    padding: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <!-- Header -->
            <div class="email-header">
                {f'<img src="{logo_url}" alt="{business_name} Logo" class="business-logo">' if logo_url else ''}
                <h1 class="header-title">Reorder Alert</h1>
                <p class="header-subtitle">{business_name} • {datetime.now().strftime('%B %d, %Y')}</p>
            </div>
            
            <!-- Alert Banner -->
            <div class="alert-banner">
                <div class="alert-icon">⚠️</div>
                <div class="alert-content">
                    <h3>Action Required: Low Stock Items</h3>
                    <p>Your inventory has items that need immediate attention. Please review and reorder as soon as possible.</p>
                </div>
            </div>
            
            <!-- Statistics -->
            <div class="stats-container">
                <div class="stat-card total">
                    <div class="stat-number">{total_low_stock}</div>
                    <div class="stat-label">Total Low Stock Items</div>
                </div>
                <div class="stat-card critical">
                    <div class="stat-number">{total_critical}</div>
                    <div class="stat-label">Out of Stock Items</div>
                </div>
                <div class="stat-card attention">
                    <div class="stat-number">{total_low_stock - total_critical}</div>
                    <div class="stat-label">Low Stock Items</div>
                </div>
            </div>
            
            <!-- Products Table -->
            <div class="products-section">
                <h2 class="section-title">📦 Low Stock Products</h2>
                <table class="products-table">
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>SKU</th>
                            <th>Current Stock</th>
                            <th>Reorder Level</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    # Add product rows
    for product in low_stock_products:
        name = product.get('name', 'Unknown Product')
        sku = product.get('sku', 'N/A')
        current_stock = product.get('current_stock', 0)
        reorder_level = product.get('reorder_level', 0)
        
        # Determine status
        if current_stock == 0:
            status = "Out of Stock"
            status_class = "stock-out"
        elif current_stock <= reorder_level * 0.5:
            status = "Critical"
            status_class = "stock-out"
        elif current_stock <= reorder_level:
            status = "Low Stock"
            status_class = "stock-low"
        else:
            status = "Attention Needed"
            status_class = "stock-warning"
        
        html += f"""
                        <tr>
                            <td>
                                <div class="product-name">{name}</div>
                            </td>
                            <td>{sku}</td>
                            <td><strong>{current_stock}</strong></td>
                            <td>{reorder_level}</td>
                            <td><span class="stock-badge {status_class}">{status}</span></td>
                        </tr>
        """
    
    # Close table and continue HTML
    html += """
                    </tbody>
                </table>
            </div>
            
            <!-- Action Button -->
            <div class="actions-section">
                <a href="{{APP_URL}}/products-inventory/low-stock" class="action-button">
                    📋 View Complete Low Stock Report
                </a>
                <p style="margin-top: 15px; color: #6c757d; font-size: 14px;">
                    Click above to view detailed inventory and place orders
                </p>
            </div>
            
            <!-- Footer -->
            <div class="email-footer">
                <p>This is an automated reorder alert from {business_name}'s inventory management system.</p>
                <p>You are receiving this email because you are registered as an administrator.</p>
                <div class="footer-links">
                    <a href="{{APP_URL}}/dashboard">Dashboard</a> •
                    <a href="{{APP_URL}}/products-inventory">Inventory</a> •
                    <a href="mailto:{business_email}">Contact Support</a>
                </div>
                <p style="margin-top: 15px; font-size: 12px; color: #adb5bd;">
                    © {datetime.now().year} {business_name}. All rights reserved.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Replace app URL placeholder
    html = html.replace("{{APP_URL}}", Config.APP_URL)
    
    # Generate plain text version
    text_content = f"""
    REORDER ALERT - {business_name}
    ================================
    
    Date: {datetime.now().strftime('%B %d, %Y')}
    
    ACTION REQUIRED: LOW STOCK ITEMS
    Your inventory has {total_low_stock} items that need immediate attention.
    
    SUMMARY:
    - Total Low Stock Items: {total_low_stock}
    - Out of Stock Items: {total_critical}
    - Low Stock Items: {total_low_stock - total_critical}
    
    LOW STOCK PRODUCTS:
    {''.join([f"• {p.get('name')} (SKU: {p.get('sku', 'N/A')}): {p.get('current_stock', 0)} in stock (Reorder at: {p.get('reorder_level', 0)})\n" for p in low_stock_products])}
    
    ACTION REQUIRED:
    Please log in to your inventory management system to review and reorder these items:
    {Config.APP_URL}/products-inventory/low-stock
    
    This is an automated alert from {business_name}'s inventory system.
    """
    
    return html, text_content