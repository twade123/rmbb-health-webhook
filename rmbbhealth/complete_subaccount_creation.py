#!/usr/bin/env python3
"""
Webhook-driven sub-account creation system for Cell Products account.
Listens for survey completion webhooks and automatically creates sub-accounts.
STANDALONE VERSION - Uses environment variables directly.
"""

import requests
import json
import logging
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify
import traceback

# Configuration using environment variables
CONFIG = {
    # Get API key from environment variable
    'company_api_key': os.environ.get('GHL_API_KEY_AGENCY', ''),
    
    # Cell Products Location ID from environment variable
    'cell_products_location_id': os.environ.get('GHL_LOCATION_ID', 'Sqbexj54nvsxOI4V7SsD'),
    
    # API Configuration
    'base_url': os.environ.get('GHL_BASE_URL', 'https://rest.gohighlevel.com/v1'),
    'webhook_auth_token': 'cell-products-survey-webhook-2025',
    
    # Default timezone for new sub-accounts
    'default_timezone': 'America/Phoenix'  # Cell Products is in Nevada/Arizona timezone
}

# Validate configuration
if not CONFIG['company_api_key']:
    print("❌ ERROR: GHL_API_KEY_AGENCY environment variable is required")
    print("Set it in your Railway dashboard under Variables")
    exit(1)

print("✅ Loaded Cell Products configuration from environment variables")
print(f"🏢 Company: cell_products")
print(f"📍 Location ID: {CONFIG['cell_products_location_id']}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console logging for cloud deployment
    ]
)

app = Flask(__name__)

def validate_webhook_auth(request):
    """Validate webhook authentication for Cell Products only."""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        logging.warning("❌ No Authorization header in webhook request")
        return False
    
    expected_token = f"Bearer {CONFIG['webhook_auth_token']}"
    is_valid = auth_header == expected_token
    
    if not is_valid:
        logging.warning(f"❌ Invalid webhook token. Expected: {expected_token}, Got: {auth_header}")
    
    return is_valid

def validate_cell_products_source(source_location_id):
    """Ensure webhook is coming from Cell Products account only."""
    # TEMPORARY FIX: Allow both location IDs while we debug the mismatch
    valid_location_ids = [
        CONFIG['cell_products_location_id'],  # Original expected ID
        'Sqbexj54nvsxOI4V7SsD'               # Actual incoming ID from GHL
    ]
    
    if source_location_id not in valid_location_ids:
        logging.error(f"❌ Unauthorized source location: {source_location_id}")
        logging.error(f"   Expected Cell Products IDs: {valid_location_ids}")
        return False
    
    if source_location_id != CONFIG['cell_products_location_id']:
        logging.warning(f"⚠️ Using alternate Cell Products location ID: {source_location_id}")
        logging.warning(f"   Expected: {CONFIG['cell_products_location_id']}")
    else:
        logging.info("✅ Webhook confirmed from Cell Products account")
    
    return True

# Import webhook handler functions for unified processing
try:
    # Get the directory where this script is located for imports
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    # Import the existing webhook handler functions
    from webhook_handler import handle_provider_onboarding
    logging.info("✅ Successfully imported webhook_handler functions")
except ImportError as e:
    logging.error(f"❌ Failed to import webhook_handler: {e}")
    handle_provider_onboarding = None

def create_subaccount_from_survey_data(survey_data):
    """
    Create a new sub-account using survey submission data.
    
    NEW APPROACH: Uses the existing webhook handler's provider onboarding functionality
    instead of duplicating code. This ensures consistency and unified GitHub persistence.
    """
    
    try:
        if handle_provider_onboarding is None:
            raise ImportError("Webhook handler not available - falling back to legacy method")
        
        logging.info("🔗 Using integrated webhook handler for sub-account creation")
        
        # The webhook handler expects a Flask request object, but we can simulate it
        # by creating a mock request with the survey data
        from flask import Flask
        from werkzeug.test import Client
        from werkzeug.wrappers import BaseResponse
        
        # Create a test client to simulate the webhook request
        test_app = Flask(__name__)
        test_client = test_app.test_client()
        
        # Prepare the payload in the format expected by the webhook handler
        webhook_payload = {
            'Business name': survey_data.get('Business name', ''),
            'first_name': survey_data.get('first_name', ''),
            'last_name': survey_data.get('last_name', ''),
            'email': survey_data.get('email', ''),
            'phone': survey_data.get('phone', ''),
            'address1': survey_data.get('address1', ''),
            'city': survey_data.get('city', ''),
            'state': survey_data.get('state', ''),
            'postal_code': survey_data.get('postal_code', ''),
            'ein': survey_data.get('ein', ''),
            'npi': survey_data.get('npi', ''),
            'locationId': CONFIG['cell_products_location_id']
        }
        
        # Extract required fields with fallbacks for different naming conventions
        if not webhook_payload['Business name']:
            webhook_payload['Business name'] = (
                survey_data.get('business name') or 
                survey_data.get('business_name') or
                survey_data.get('businessName') or 
                survey_data.get('company') or 
                survey_data.get('companyName') or 
                survey_data.get('Provider Name') or 
                survey_data.get('Legal Company Name') or 
                survey_data.get('legal_company_name') or ''
            ).strip()
        
        # Handle name field variations
        for field in ['first_name', 'last_name', 'email', 'phone']:
            if not webhook_payload[field]:
                webhook_payload[field] = (
                    survey_data.get(field) or
                    survey_data.get(field.replace('_', '')) or
                    survey_data.get(field.title()) or
                    survey_data.get(f'Patient {field.replace("_", " ").title()}') or ''
                ).strip()
        
        # Handle address fields
        for field in ['address1', 'city', 'state', 'postal_code']:
            if not webhook_payload[field]:
                alt_names = {
                    'address1': ['address', 'street_address', 'Address'],
                    'city': ['City'],
                    'state': ['State'],
                    'postal_code': ['zip_code', 'zipcode', 'zip', 'Zip Code']
                }
                for alt_name in alt_names.get(field, []):
                    if survey_data.get(alt_name):
                        webhook_payload[field] = survey_data.get(alt_name).strip()
                        break
        
        # Handle EIN and NPI with variations
        if not webhook_payload['ein']:
            webhook_payload['ein'] = (
                survey_data.get('federal_tax_id__ein') or
                survey_data.get('federal_tax_id') or 
                survey_data.get('tax_id') or 
                survey_data.get('EIN') or 
                survey_data.get('Federal Tax ID') or ''
            ).strip()
            
        if not webhook_payload['npi']:
            webhook_payload['npi'] = (
                survey_data.get('NPI') or 
                survey_data.get('national_provider_id') or 
                survey_data.get('provider_id') or ''
            ).strip()
        
        # Parse combined name field if needed
        if not webhook_payload['first_name'] and not webhook_payload['last_name']:
            full_name = survey_data.get('name', '').strip()
            if full_name:
                name_parts = full_name.replace('Dr. ', '').replace('Mr. ', '').replace('Ms. ', '').replace('Mrs. ', '').strip().split(' ', 1)
                webhook_payload['first_name'] = name_parts[0] if len(name_parts) > 0 else ''
                webhook_payload['last_name'] = name_parts[1] if len(name_parts) > 1 else ''
        
        logging.info(f"📦 Prepared webhook payload: {json.dumps(webhook_payload, indent=2)}")
        
        # Simulate the webhook request using the existing handler
        with test_app.test_request_context('/webhook/provider-onboarding', 
                                         method='POST', 
                                         json=webhook_payload,
                                         content_type='application/json'):
            
            from flask import request
            # Call the existing webhook handler function
            response = handle_provider_onboarding()
            
            # Extract the response data
            if hasattr(response, 'get_json'):
                result_data = response.get_json()
                status_code = response.status_code
            else:
                # Handle tuple response (data, status_code)
                result_data, status_code = response
            
            logging.info(f"📊 Webhook handler response: {status_code}")
            logging.info(f"📊 Response data: {json.dumps(result_data, indent=2)}")
            
            if status_code == 200 and result_data.get('success'):
                # Transform webhook handler response to match expected format
                return {
                    'success': True,
                    'sub_account_id': result_data.get('sub_account_id'),
                    'business_name': result_data.get('business_name'),
                    'contact_name': result_data.get('contact_name'),
                    'email': result_data.get('email'),
                    'created_at': result_data.get('created_at', datetime.now().isoformat())
                }
            else:
                return {
                    'success': False,
                    'error': result_data.get('error', f'Webhook handler returned {status_code}')
                }
        
    except Exception as e:
        error_msg = f"Error using webhook handler for sub-account creation: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        
        # Fallback to a simplified version that at least logs the attempt
        return {
            'success': False,
            'error': f"Integration with webhook handler failed: {error_msg}"
        }

@app.route('/webhook/survey-completion', methods=['POST'])
def handle_survey_completion():
    """Handle survey completion webhook from Cell Products account."""
    
    try:
        # Log incoming webhook
        logging.info("📝 Survey completion webhook received")
        logging.info(f"🔗 Headers: {dict(request.headers)}")
        
        # GHL doesn't send Authorization headers by default - skip auth for now
        # TODO: Implement IP whitelist or webhook signature validation for security
        # if not validate_webhook_auth(request):
        #     return jsonify({"error": "Unauthorized"}), 401
        
        # Get webhook payload
        payload = request.get_json()
        if not payload:
            logging.error("❌ No JSON payload received")
            return jsonify({"error": "No JSON payload"}), 400
        
        logging.info(f"📦 Webhook payload: {json.dumps(payload, indent=2)}")
        
        # GHL webhook payload structure analysis
        logging.info(f"📦 Full webhook payload structure: {json.dumps(payload, indent=2)}")
        
        # Handle different GHL webhook formats
        # GHL sends form submissions, survey responses, etc. in various formats
        event_type = payload.get('type') or payload.get('event') or 'unknown'
        logging.info(f"📋 Webhook event type: {event_type}")
        
        # Extract location ID from various possible fields
        source_location_id = (payload.get('locationId') or 
                            payload.get('location_id') or 
                            payload.get('location', {}).get('id', ''))
        
        if source_location_id and not validate_cell_products_source(source_location_id):
            return jsonify({"error": "Unauthorized source location"}), 403
        
        # Extract survey/form data from various possible structures
        # GHL sends form fields directly at the top level of the payload
        survey_data = payload
        
        survey_id = (payload.get('formId') or 
                    payload.get('survey_id') or 
                    payload.get('id', ''))
        
        # Validate survey data
        if not survey_data:
            logging.error("❌ No survey data in webhook")
            return jsonify({"error": "No survey data"}), 400
        
        # Debug: Log all available field names for troubleshooting
        logging.info(f"📊 Available survey fields: {list(survey_data.keys())}")
        logging.info(f"📊 Survey data sample: {dict(list(survey_data.items())[:10])}")  # First 10 fields
        
        # Debug business name extraction with each candidate (including webhook template fields)
        business_name_candidates = {
            'Business name': survey_data.get('Business name'),           # Capital B (what GHL actually sends)
            'business name': survey_data.get('business name'),           # lowercase b (backup)
            'business_name': survey_data.get('business_name'),
            'businessName': survey_data.get('businessName'),
            'company': survey_data.get('company'),
            'companyName': survey_data.get('companyName'),
            'Provider Name': survey_data.get('Provider Name'),
            'Legal Company Name': survey_data.get('Legal Company Name'),
            'legal_company_name': survey_data.get('legal_company_name')   # From webhook template
        }
        
        logging.info(f"🔍 Business name extraction candidates: {business_name_candidates}")
        
        business_name = (survey_data.get('Business name') or     # Capital B (what GHL actually sends) - CRITICAL FIX
                        survey_data.get('business name') or     # lowercase b (backup)
                        survey_data.get('business_name') or 
                        survey_data.get('businessName') or 
                        survey_data.get('company') or 
                        survey_data.get('companyName') or 
                        survey_data.get('Provider Name') or 
                        survey_data.get('Legal Company Name') or 
                        survey_data.get('legal_company_name') or     # From webhook template
                        '').strip()
        
        logging.info(f"🔍 Extracted business name: '{business_name}'")
        
        if not business_name:
            logging.error("❌ Business name required for sub-account creation")
            return jsonify({"error": "Business name required"}), 400
        
        # Log processing start - extract names properly
        first_name_field = (survey_data.get('first_name') or 
                           survey_data.get('firstName') or 
                           survey_data.get('fname') or 
                           survey_data.get('Patient First Name') or '')
        last_name_field = (survey_data.get('last_name') or 
                          survey_data.get('lastName') or 
                          survey_data.get('lname') or 
                          survey_data.get('Patient Last Name') or '')
        contact_name = f"{first_name_field} {last_name_field}".strip()
        logging.info(f"🚀 Processing survey completion for: {contact_name}")
        logging.info(f"🏢 Business: {business_name}")
        logging.info(f"📝 Survey ID: {survey_id}")
        logging.info(f"📍 Source: Cell Products ({source_location_id})")
        
        # Create sub-account
        result = create_subaccount_from_survey_data(survey_data)
        
        if result['success']:
            response_data = {
                "success": True,
                "message": "Sub-account created successfully from survey",
                "sub_account_id": result['sub_account_id'],
                "business_name": result['business_name'],
                "contact_name": result['contact_name'],
                "email": result['email'],
                "created_at": result['created_at'],
                "timestamp": datetime.now().isoformat()
            }
            
            logging.info(f"✅ Survey webhook processed successfully")
            logging.info(f"🎉 Sub-account {result['sub_account_id']} created for {result['business_name']}")
            
            return jsonify(response_data), 200
        else:
            error_response = {
                "success": False,
                "error": result['error'],
                "timestamp": datetime.now().isoformat()
            }
            
            logging.error(f"❌ Sub-account creation failed: {result['error']}")
            return jsonify(error_response), 500
            
    except Exception as e:
        error_msg = f"Survey webhook processing error: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        
        return jsonify({
            "success": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/webhook/test', methods=['GET', 'POST'])
def test_webhook():
    """Test endpoint for webhook functionality."""
    
    if request.method == 'GET':
        return jsonify({
            "status": "cell_products_survey_webhook_active",
            "timestamp": datetime.now().isoformat(),
            "endpoints": {
                "survey_completion": "/webhook/survey-completion",
                "test": "/webhook/test",
                "health": "/health"
            },
            "account": "Cell Products Only",
            "location_id": CONFIG['cell_products_location_id']
        })
    
    # POST test with sample survey data
    sample_payload = {
        "event": "survey_completion",
        "timestamp": datetime.now().isoformat(),
        "survey_id": "test_survey_123",
        "location_id": CONFIG['cell_products_location_id'],
        "survey_data": {
            "first_name": "Test",
            "last_name": "Business",
            "email": "test@testbusiness.com",
            "phone": "+1234567890",
            "business_name": "Test Business LLC",
            "website": "https://testbusiness.com",
            "address": "123 Business Street",
            "city": "Phoenix",
            "state": "AZ",
            "zip_code": "85001",
            "service_interest": "premium_package"
        }
    }
    
    logging.info("🧪 Test webhook triggered with sample survey data")
    return jsonify({
        "message": "Test webhook received",
        "sample_payload": sample_payload,
        "note": "Use POST /webhook/survey-completion with real survey data for actual processing"
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Cell Products Survey Webhook Handler",
        "account": "Cell Products Only",
        "location_id": CONFIG['cell_products_location_id'],
        "api_key_configured": bool(CONFIG['company_api_key'])
    })

def verify_configuration():
    """Verify Cell Products configuration is valid."""
    logging.info("🔧 Verifying Cell Products configuration...")
    
    # Test API key validity
    headers = {
        "Authorization": f"Bearer {CONFIG['company_api_key']}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }
    
    try:
        response = requests.get(f"{CONFIG['base_url']}/locations/", headers=headers)
        if response.status_code == 200:
            logging.info("✅ Cell Products API key is valid")
            return True
        else:
            logging.error(f"❌ Cell Products API key invalid: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ Configuration verification failed: {e}")
        return False

if __name__ == '__main__':
    # Get port from environment variable (for cloud deployment) or use default
    port = int(os.environ.get('PORT', 8080))
    host = os.environ.get('HOST', '0.0.0.0')  # 0.0.0.0 for cloud deployment
    
    logging.info("🚀 Starting Cell Products Survey Webhook Handler")
    logging.info("=" * 60)
    logging.info(f"🏢 Account: Cell Products (ID: {CONFIG['cell_products_location_id']})")
    logging.info("📡 Listening for survey completion webhooks")
    logging.info(f"🔗 Endpoint: http://{host}:{port}/webhook/survey-completion")
    logging.info(f"🧪 Test endpoint: http://{host}:{port}/webhook/test")
    logging.info(f"❤️ Health check: http://{host}:{port}/health")
    
    # Verify configuration before starting
    if verify_configuration():
        logging.info("✅ Configuration verified - starting server")
        app.run(host=host, port=port, debug=False)  # debug=False for production
    else:
        logging.error("❌ Configuration verification failed - server not started")
