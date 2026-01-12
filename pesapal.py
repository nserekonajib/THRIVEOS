#pesapal.py
import os
import json
import uuid
import requests
import urllib3
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# In your pesapal.py or wherever your PesaPal class is defined
from flask import session
from supabase import create_client
from config import Config

class PesaPal:
    def __init__(self, business_id=None):
        self.auth_url = "https://pay.pesapal.com/v3/api/Auth/RequestToken"
        self.api_url = "https://pay.pesapal.com/v3/api/"
        self.token = None
        
        # Get Supabase client
        self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        
        # Get business_id from parameter or session
        self.business_id = business_id or session.get('business_id')
        
        # Get credentials from database
        self.consumer_key, self.consumer_secret, self.ipn_url = self._get_pesapal_credentials()
        
        # Register IPN only after authentication
        self.ipn_id = None

    def _get_pesapal_credentials(self):
        """Get PesaPal credentials from database for the current business"""
        try:
            response = self.supabase.table('business_settings').select(
                'pesapal_consumer_key, pesapal_consumer_secret, pesapal_ipn_url'
            ).eq('business_id', self.business_id).limit(1).execute()
            
            if response.data:
                settings = response.data[0]
                consumer_key = settings.get('pesapal_consumer_key')
                consumer_secret = settings.get('pesapal_consumer_secret')
                ipn_url = settings.get('pesapal_ipn_url') or Config.PESAPAL_IPN_URL
                
                # Debug logging
                print(f"🔍 PesaPal Credentials Loaded:")
                print(f"   Consumer Key: {consumer_key[:10]}..." if consumer_key else "   Consumer Key: NOT SET")
                print(f"   Consumer Secret: {'***SET***' if consumer_secret else 'NOT SET'}")
                print(f"   IPN URL: {ipn_url}")
                
                return consumer_key, consumer_secret, ipn_url
            
            print("❌ No PesaPal settings found in database")
            return None, None, Config.PESAPAL_IPN_URL
            
        except Exception as e:
            print(f"❌ Error loading PesaPal credentials: {e}")
            return None, None, Config.PESAPAL_IPN_URL

    def _validate_credentials(self):
        """Validate that required credentials are set"""
        if not self.consumer_key or not self.consumer_secret:
            print(f"❌ Missing PesaPal credentials:")
            print(f"   Consumer Key: {'SET' if self.consumer_key else 'MISSING'}")
            print(f"   Consumer Secret: {'SET' if self.consumer_secret else 'MISSING'}")
            return False
        return True

    def authenticate(self):
        """Authenticate with PesaPal API"""
        print(f"🔄 Authenticating with PesaPal...")
        print(f"   Using Consumer Key: {self.consumer_key[:10]}..." if self.consumer_key else "   Consumer Key: NOT SET")
        
        # Validate credentials first
        if not self._validate_credentials():
            return None
            
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            data = {
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret
            }
            
            response = requests.post(self.auth_url, json=data, headers=headers)
            response.raise_for_status()
            
            auth_data = response.json()
            self.token = auth_data.get("token")
            
            print(f"✅ Authentication successful")
            print(f"   Token: {self.token[:20]}..." if self.token else "   Token: NOT RECEIVED")
            
            return self.token
            
        except requests.exceptions.RequestException as e:
            print(f"❌ PesaPal authentication failed: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"   Error response: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   Response text: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error during authentication: {str(e)}")
            return None


    def authenticate(self):
        """Authenticate with PesaPal and get access token"""
        try:
            payload = json.dumps({
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret
            })
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json',
                'User-Agent': 'CapitalCollege/1.0'
            }

            print("🔄 Authenticating with PesaPal...")
            response = requests.post(
                self.auth_url, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            if 'token' in data:
                self.token = data['token']
                print("✅ PesaPal authentication successful")
                
                # Register IPN after getting token
                self.ipn_id = self.register_ipn_url()
                return self.token
            else:
                print(f"❌ Authentication failed. Response: {data}")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ PesaPal authentication failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error during authentication: {e}")
            return None

    def register_ipn_url(self):
        """Register IPN URL with PesaPal"""
        try:
            endpoint = "URLSetup/RegisterIPN"
            payload = json.dumps({
                "url": self.ipn_url, 
                "ipn_notification_type": "GET"
            })
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json', 
                'Authorization': f"Bearer {self.token}",
                'User-Agent': 'CapitalCollege/1.0'
            }
            
            print("🔄 Registering IPN URL...")
            response = requests.post(
                self.api_url + endpoint, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            if 'ipn_id' in data:
                print(f"✅ IPN registered successfully: {data['ipn_id']}")
                return data['ipn_id']
            else:
                print(f"❌ IPN registration failed. Response: {data}")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ IPN Registration failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in IPN registration: {e}")
            return None

    def submit_order(self, amount, reference_id, callback_url, email, first_name, last_name):
        """Submit order to PesaPal for payment processing"""
        if not self.token:
            if not self.authenticate():
                return None

        try:
            endpoint = "Transactions/SubmitOrderRequest"
            payload = json.dumps({
                "id": reference_id,
                "currency": "UGX",
                "amount": str(amount),
                "description": "Membership Fee - LUNSERK SACCO",
                "callback_url": callback_url,
                "notification_id": self.ipn_id,
                "billing_address": {
                    "email_address": email,
                    "phone_number": "",  # Optional
                    "country_code": "UG",
                    "first_name": first_name,
                    "middle_name": "",
                    "last_name": last_name,
                    "line_1": "LUNSERK SACCO",
                    "line_2": "",
                    "city": "Kampala",
                    "state": "",
                    "postal_code": "",
                    "zip_code": ""
                }
            })
            
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json', 
                'Authorization': f"Bearer {self.token}",
                'User-Agent': 'LUNSERK-SACCO/1.0'
            }

            print(f"🔄 Submitting order to PesaPal: UGX {amount}, Ref: {reference_id}")
            response = requests.post(
                self.api_url + endpoint, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ PesaPal API Response: {data}")
            
            # Check for different possible response keys
            if 'order_tracking_id' in data:
                order_id = data['order_tracking_id']
            elif 'orderTrackingId' in data:
                order_id = data['orderTrackingId']
            elif 'reference' in data:
                order_id = data['reference']
            else:
                print(f"❌ No order tracking ID found in response: {data}")
                return None
            
            print(f"✅ Order submitted successfully. Order ID: {order_id}")
            
            # Return standardized response
            return {
                'order_tracking_id': order_id,
                'redirect_url': data.get('redirect_url') or data.get('paymentUrl') or data.get('url'),
                'reference_id': reference_id,
                'raw_response': data  # Keep original response for debugging
            }
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Order submission failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in order submission: {e}")
            import traceback
            traceback.print_exc()
            return None

    def verify_transaction_status(self, order_tracking_id):
        """Verify transaction status with PesaPal"""
        if not self.token:
            if not self.authenticate():
                return None

        try:
            endpoint = f"Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json', 
                'Authorization': f"Bearer {self.token}",
                'User-Agent': 'LUNSERK-SACCO/1.0'
            }

            print(f"🔄 Verifying transaction status: {order_tracking_id}")
            response = requests.get(
                self.api_url + endpoint, 
                headers=headers, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Transaction status response: {data}")
            
            # Standardize response keys
            standardized_data = {
                'order_tracking_id': data.get('order_tracking_id') or data.get('orderTrackingId') or order_tracking_id,
                'status': data.get('status', 'UNKNOWN'),
                'payment_status_description': data.get('payment_status_description') or data.get('paymentStatusDescription') or data.get('message', ''),
                'payment_method': data.get('payment_method') or data.get('paymentMethod', ''),
                'amount': data.get('amount'),
                'currency': data.get('currency', 'UGX'),
                'payment_date': data.get('payment_date') or data.get('paymentDate', ''),
                'raw_response': data  # Keep original for debugging
            }
            
            return standardized_data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Transaction verification failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in transaction verification: {e}")
            import traceback
            traceback.print_exc()
            return None