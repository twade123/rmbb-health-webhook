#!/usr/bin/env python3
"""
RMBB Health Webhook Handler - GHL Integration Server

This Flask server receives GHL form submission webhooks and processes them through
the complete RMBB Health qualification workflow, returning results to GHL.

Data Flow:
1. GHL Form Submission → Webhook endpoint
2. Extract patient/medical data → RMBB Health API (Patient + Case creation)
3. Poll RMBB Health for IVR/qualification status
4. Update GHL contact + notify provider → GHL V1 API

Based on complete_subaccount_creation.py patterns and rmbbhealth.txt API specification.
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime
from flask import Flask, request, jsonify

# Import our RMBB Health modules using relative imports for Railway
try:
    # Try package import first
    from rmbbhealth import (
        RMBBHealthClient, PatientService, CaseService, 
        FileService, NoteService, AccountService, StatusService
    )
except ImportError:
    # Fallback to direct imports in Railway environment
    from client import RMBBHealthClient
    from services.patient_service import PatientService
    from services.case_service import CaseService
    from services.file_service import FileService
    from services.note_service import NoteService
    from services.account_service import AccountService
    from services.status_service import StatusService

# Import the workflow handler
from ghl_rmbb_workflow import GHLRMBBWorkflowHandler

# Configure logging - Railway compatible
log_handlers = [logging.StreamHandler()]

# Only add file handler if not in Railway environment
if not os.getenv('RAILWAY_ENVIRONMENT'):
    # Local development - use local path
    try:
        log_handlers.append(logging.FileHandler('/Users/timothywade/Jarvis/rmbbhealth/webhook.log'))
    except:
        pass  # If local path doesn't work, just use console logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

# Initialize Flask app
app = Flask(__name__)

# Approval Status Analysis Function
def analyze_rmbb_approval_status(status_data):
    """
    Analyze RMBB Health case status data to determine approval state.
    
    Args:
        status_data (dict): Dictionary containing all status fields from RMBB Health case
        
    Returns:
        dict: Analysis result with status, message, and confidence level
    """
    case_status = status_data.get('case_status', '').upper()
    external_status = status_data.get('external_status', '').upper()
    overall_result = status_data.get('overall_insurance_result', '').upper()
    primary_status = status_data.get('primary_insurance_status', '').upper()
    secondary_status = status_data.get('secondary_insurance_status', '').upper()
    tertiary_status = status_data.get('tertiary_insurance_status', '').upper()
    primary_result = status_data.get('primary_insurance_result', '').upper()
    secondary_result = status_data.get('secondary_insurance_result', '').upper()
    last_fax = status_data.get('last_fax_status', '').upper()
    
    # All status fields for analysis
    all_statuses = [case_status, external_status, overall_result, primary_status, 
                   secondary_status, tertiary_status, primary_result, secondary_result, last_fax]
    all_statuses = [s for s in all_statuses if s]  # Remove empty strings
    
    # Define approval status patterns based on healthcare industry standards
    approved_patterns = ['APPROVED', 'ACCEPTED', 'AUTHORIZED', 'COVERED', 'QUALIFIED', 'COMPLETED', 'SUCCESS']
    denied_patterns = ['DENIED', 'REJECTED', 'DECLINED', 'NOT COVERED', 'DISQUALIFIED', 'FAILED', 'INELIGIBLE']
    pending_patterns = ['PENDING', 'UNDER REVIEW', 'PROCESSING', 'SUBMITTED', 'IN PROGRESS', 'AWAITING']
    created_patterns = ['CASE CREATED', 'CREATED', 'INITIATED', 'RECEIVED']
    
    # Priority order: overall_result > primary_result > case_status > external_status > insurance statuses
    priority_fields = [
        ('overall_result', overall_result),
        ('primary_result', primary_result), 
        ('secondary_result', secondary_result),
        ('case_status', case_status),
        ('external_status', external_status),
        ('primary_status', primary_status),
        ('secondary_status', secondary_status)
    ]
    
    # Check for approval/denial in priority order
    for field_name, field_value in priority_fields:
        if not field_value:
            continue
            
        # Check for approved status
        if any(pattern in field_value for pattern in approved_patterns):
            return {
                'status': 'APPROVED',
                'message': f'Approved based on {field_name}: {field_value}',
                'confidence': 'HIGH',
                'determining_field': field_name,
                'determining_value': field_value,
                'all_statuses': status_data
            }
        
        # Check for denied status  
        if any(pattern in field_value for pattern in denied_patterns):
            return {
                'status': 'DENIED',
                'message': f'Denied based on {field_name}: {field_value}',
                'confidence': 'HIGH',
                'determining_field': field_name,
                'determining_value': field_value,
                'all_statuses': status_data
            }
    
    # Check for pending status
    for field_name, field_value in priority_fields:
        if field_value and any(pattern in field_value for pattern in pending_patterns):
            return {
                'status': 'PENDING',
                'message': f'Pending based on {field_name}: {field_value}',
                'confidence': 'MEDIUM',
                'determining_field': field_name,
                'determining_value': field_value,
                'all_statuses': status_data
            }
    
    # Check for created/initial status
    for field_name, field_value in priority_fields:
        if field_value and any(pattern in field_value for pattern in created_patterns):
            return {
                'status': 'CREATED',
                'message': f'Case created/initiated based on {field_name}: {field_value}',
                'confidence': 'MEDIUM',
                'determining_field': field_name,
                'determining_value': field_value,
                'all_statuses': status_data
            }
    
    # Fallback: Unknown status
    return {
        'status': 'UNKNOWN',
        'message': f'Status unclear from available fields: {", ".join(all_statuses[:3])}',
        'confidence': 'LOW',
        'determining_field': 'multiple',
        'determining_value': ', '.join(all_statuses[:3]),
        'all_statuses': status_data
    }

# Configuration from environment variables
class WebhookConfig:
    """Configuration for webhook server using environment variables"""
    
    # RMBB Health API Configuration
    RMBB_API_KEY = os.environ.get('RMBB_API_KEY', None)
    RMBB_TEAM_ID = os.environ.get('RMBB_TEAM_ID', None)
    
    # GHL V1 API Configuration  
    GHL_API_KEY = os.environ.get('GHL_API_KEY', None)
    GHL_BASE_URL = os.environ.get('GHL_BASE_URL', 'https://rest.gohighlevel.com/v1')
    
    # Webhook Security
    WEBHOOK_AUTH_TOKEN = os.environ.get('WEBHOOK_AUTH_TOKEN', 'rmbb-health-webhook-2025')
    
    # Server Configuration - Railway compatible
    PORT = int(os.environ.get('PORT', 8080))
    HOST = os.environ.get('HOST', '0.0.0.0')
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    # Railway deployment check
    RAILWAY_ENVIRONMENT_ID = os.environ.get('RAILWAY_ENVIRONMENT_ID')
    RAILWAY_SERVICE_ID = os.environ.get('RAILWAY_SERVICE_ID')

# Validate configuration
def validate_configuration():
    """Validate that all required environment variables are set"""
    required_vars = ['RMBB_API_KEY', 'RMBB_TEAM_ID', 'GHL_API_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not getattr(WebhookConfig, var):
            missing_vars.append(var)
    
    if missing_vars:
        logging.error(f"❌ Missing required environment variables: {missing_vars}")
        logging.error("Set these variables before starting the server:")
        for var in missing_vars:
            logging.error(f"  export {var}='your_value_here'")
        return False
    
    logging.info("✅ All required environment variables are configured")
    return True

def validate_webhook_auth(request):
    """Validate webhook authentication"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        logging.warning("❌ No Authorization header in webhook request")
        return False
    
    expected_token = f"Bearer {WebhookConfig.WEBHOOK_AUTH_TOKEN}"
    is_valid = auth_header == expected_token
    
    if not is_valid:
        logging.warning(f"❌ Invalid webhook token. Expected: {expected_token}, Got: {auth_header}")
    
    return is_valid

@app.route('/webhook/ghl-rmbb-qualification', methods=['POST'])
def handle_ghl_qualification_webhook():
    """
    Main webhook endpoint for GHL → RMBB Health → GHL qualification workflow
    
    Receives GHL form submission and processes complete bidirectional workflow:
    1. Extract patient/medical data from GHL payload
    2. Create RMBB Health patient and case  
    3. Poll for IVR/qualification response
    4. Update GHL contact and notify provider
    """
    
    try:
        # Log incoming webhook
        logging.info("📝 GHL → RMBB Health qualification webhook received")
        logging.info(f"🔗 Headers: {dict(request.headers)}")
        
        # Validate authentication (skip for now - implement IP whitelist later)
        # if not validate_webhook_auth(request):
        #     return jsonify({"error": "Unauthorized"}), 401
        
        # Get webhook payload
        payload = request.get_json()
        if not payload:
            logging.error("❌ No JSON payload received")
            return jsonify({"error": "No JSON payload"}), 400
        
        logging.info(f"📦 Webhook payload received: {len(str(payload))} characters")
        logging.info(f"📊 Available fields: {list(payload.keys())[:10]}...")  # First 10 fields
        
        # DEBUG: Log the complete payload to see exact field names
        logging.info(f"🔍 DEBUG - Complete webhook payload: {json.dumps(payload, indent=2)}")
        
        # DEBUG: Check for product fields specifically
        product_fields = [k for k in payload.keys() if 'amniomaxx' in k.lower() or 'palingen' in k.lower() or 'biovance' in k.lower()]
        logging.info(f"🧬 Product fields found: {product_fields}")
        
        # DEBUG: Check date of birth field
        dob_fields = [k for k in payload.keys() if 'dob' in k.lower() or 'birth' in k.lower()]
        logging.info(f"📅 Date fields found: {dob_fields}")
        for field in dob_fields:
            logging.info(f"📅 {field}: '{payload[field]}'")
        
        
        # Initialize workflow handler with environment configuration
        # Add error handling for missing RMBB_TEAM_ID
        try:
            rmbb_team_id = int(WebhookConfig.RMBB_TEAM_ID) if WebhookConfig.RMBB_TEAM_ID else None
        except (ValueError, TypeError) as e:
            logging.error(f"❌ Invalid RMBB_TEAM_ID environment variable: {WebhookConfig.RMBB_TEAM_ID}")
            return jsonify({
                "success": False, 
                "error": f"Invalid RMBB_TEAM_ID configuration: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }), 500
        
        if not rmbb_team_id:
            logging.error(f"❌ RMBB_TEAM_ID not configured properly: {WebhookConfig.RMBB_TEAM_ID}")
            return jsonify({
                "success": False,
                "error": "RMBB_TEAM_ID environment variable not set or invalid",
                "timestamp": datetime.now().isoformat()
            }), 500
        
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=WebhookConfig.RMBB_API_KEY,
            rmbb_team_id=rmbb_team_id,
            ghl_api_key=WebhookConfig.GHL_API_KEY
        )
        
        logging.info("🚀 Starting complete GHL → RMBB Health → GHL workflow...")
        
        # Process the complete workflow
        result = workflow_handler.run_complete_workflow(payload)
        
        if result["success"]:
            response_data = {
                "success": True,
                "message": "GHL → RMBB Health → GHL workflow completed successfully",
                "tracking_id": result["tracking_id"],
                "final_status": result["final_status"],
                "timestamp": datetime.now().isoformat()
            }
            
            logging.info(f"✅ Workflow completed successfully")
            logging.info(f"🆔 Tracking ID: {result['tracking_id']}")
            logging.info(f"📋 Final Status: {result['final_status']}")
            
            return jsonify(response_data), 200
        else:
            error_response = {
                "success": False,
                "error": result["error"],
                "timestamp": datetime.now().isoformat()
            }
            
            logging.error(f"❌ Workflow failed: {result['error']}")
            return jsonify(error_response), 500
            
    except Exception as e:
        error_msg = f"Webhook processing error: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        
        return jsonify({
            "success": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/webhook/test', methods=['GET', 'POST'])
def test_webhook():
    """Test endpoint for webhook functionality"""
    
    if request.method == 'GET':
        return jsonify({
            "status": "rmbb_health_webhook_active",
            "timestamp": datetime.now().isoformat(),
            "endpoints": {
                "qualification_webhook": "/webhook/ghl-rmbb-qualification",
                "test": "/webhook/test",
                "health": "/health"
            },
            "configuration": {
                "rmbb_api_configured": bool(WebhookConfig.RMBB_API_KEY),
                "ghl_api_configured": bool(WebhookConfig.GHL_API_KEY),
                "team_id_configured": bool(WebhookConfig.RMBB_TEAM_ID)
            }
        })
    
    # POST test with sample GHL form data - Updated to match your corrected webhook payload
    sample_ghl_payload = {
        "contact_id": "test_contact_456",  # Updated: contactId → contact_id
        "provider_name": "Test Provider",  # Added: provider_name for routing
        "patient_first_name": "John",
        "patient_last_name": "Smith",  # Fixed: typo corrected
        "patient_dob": "1985-03-15",
        "patient_street_address": "123 Main Street",
        "patient_city": "Anytown",
        "patient_state": "CA",
        "patient_zip_code": "12345",
        "patient_primary_insurance": "Medicare Part B",
        "patient_primary_insurance_": "1234567890A",
        "patient_secondary_insurance": "AARP Medicare Supplement",
        "patient_secondary_insurance_": "SUP987654321",
        "facility_type": "Physician Office",
        "facility_npi_#": "1234567890",
        "expected_date_of_service": "2025-07-01",
        "amniomaxx_(q4239)_units/cm2": "5.0",
        "palingen_(q4173)_units/cm2": "3.0",
        "membrane_wrap_tri-layer_(q4344)_units/cm2": "2.0",
        "amnioamp-mp_(q4250)_units/cm2": "4.0",
        "membrane_wrap_hydro_(q4290)_units/cm2": "1.5",
        "biovance_(q4154)_units/cm2": "6.0",
        "amchoplast_(q4316)_units/cm2": "2.5",
        "helicoll_(q4164)_units/cm2": "3.5",
        "xcell_amnio_matrix_(q4280)_units/cm2": "4.5",
        "icd_-_10_diagnosis_code(s)": "E11.621",
        "email": "john.smith@email.com",
        "formId": "qualification_form_789"
    }
    
    logging.info("🧪 Test webhook triggered with sample GHL qualification data")
    return jsonify({
        "message": "Test webhook received",
        "sample_payload": sample_ghl_payload,
        "note": "Use POST /webhook/ghl-rmbb-qualification with real GHL form data for actual processing"
    })

@app.route('/webhook/rmbb-status-update', methods=['POST'])
def handle_rmbb_status_webhook():
    """
    Enhanced webhook endpoint for RMBB Health to send case status updates.
    This monitors approval status fields: status, external_status, overall_insurance_result
    and insurance-specific statuses for comprehensive IVR qualification tracking.
    """
    
    try:
        # Verify webhook authentication
        auth_token = request.headers.get('Authorization')
        expected_token = f"Bearer {os.getenv('WEBHOOK_AUTH_TOKEN', 'rmbb-health-webhook-2025')}"
        
        if auth_token != expected_token:
            logging.warning(f"🔒 RMBB webhook authentication failed: {auth_token}")
            return jsonify({
                "error": "Authentication failed",
                "message": "Invalid or missing Authorization header"
            }), 401
        
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "No JSON payload provided"}), 400
        
        logging.info(f"📋 RMBB Health webhook received: {json.dumps(payload, indent=2)}")
        
        # Extract critical data from RMBB webhook with enhanced status monitoring
        external_id = payload.get('external_id')
        case_id = payload.get('case_id') 
        provider_name = payload.get('provider_name')
        
        # ENHANCED: Monitor multiple approval status fields based on RMBB Health API structure
        case_status = payload.get('status')                           # Primary status field
        external_status = payload.get('external_status')             # External-facing status
        overall_insurance_result = payload.get('overall_insurance_result', '')  # Final approval result
        
        # Insurance-specific status monitoring
        primary_insurance_status = payload.get('primary_insurance', {}).get('status', '')
        secondary_insurance_status = payload.get('secondary_insurance', {}).get('status', '')
        tertiary_insurance_status = payload.get('tertiary_insurance', {}).get('status', '')
        
        # Extract insurance results for detailed tracking
        primary_insurance_result = payload.get('primary_insurance', {}).get('result', '')
        secondary_insurance_result = payload.get('secondary_insurance', {}).get('result', '')
        
        # Monitor last_fax_status for communication tracking
        last_fax_status = payload.get('last_fax_status', '')
        
        # Legacy support: Also check ivr_data for backward compatibility
        ivr_data = payload.get('ivr_data', {})
        
        # Validate required fields
        if not external_id:
            return jsonify({"error": "Missing external_id in payload"}), 400
        
        if not provider_name:
            logging.warning(f"⚠️ No provider_name in RMBB webhook - routing may fail")
            return jsonify({"error": "Missing provider_name for GHL routing"}), 400
        
        # ENHANCED STATUS ANALYSIS: Determine approval state from multiple fields
        approval_analysis = analyze_rmbb_approval_status({
            'case_status': case_status,
            'external_status': external_status,
            'overall_insurance_result': overall_insurance_result,
            'primary_insurance_status': primary_insurance_status,
            'secondary_insurance_status': secondary_insurance_status,
            'tertiary_insurance_status': tertiary_insurance_status,
            'primary_insurance_result': primary_insurance_result,
            'secondary_insurance_result': secondary_insurance_result,
            'last_fax_status': last_fax_status
        })
        
        logging.info(f"🔗 Processing RMBB status update:")
        logging.info(f"   External ID: {external_id}")
        logging.info(f"   Provider: {provider_name}")
        logging.info(f"   Case Status: {case_status}")
        logging.info(f"   External Status: {external_status}")
        logging.info(f"   Overall Result: {overall_insurance_result}")
        logging.info(f"   Primary Insurance Status: {primary_insurance_status}")
        logging.info(f"   Secondary Insurance Status: {secondary_insurance_status}")
        logging.info(f"   Approval Analysis: {approval_analysis['status']} - {approval_analysis['message']}")
        logging.info(f"   Legacy IVR Data: {ivr_data.get('approval_status', 'N/A')}")
        
        # Extract GHL contact ID from external_id (format: ghl_contact_{contactId}_{timestamp})
        ghl_contact_id = None
        if external_id and external_id.startswith('ghl_contact_'):
            try:
                parts = external_id.split('_')
                if len(parts) >= 3:
                    ghl_contact_id = parts[2]  # contact_id is the 3rd part
                    logging.info(f"📧 Extracted GHL contact ID: {ghl_contact_id}")
            except Exception as e:
                logging.error(f"❌ Failed to extract contact ID from external_id '{external_id}': {e}")
        
        if not ghl_contact_id:
            return jsonify({
                "error": "Cannot extract GHL contact ID from external_id",
                "external_id": external_id
            }), 400
        
        # CRITICAL: Use provider cache to get locationId for GHL routing
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        
        location_id = provider_cache.get_location_id(provider_name)
        if not location_id:
            logging.error(f"❌ CRITICAL: Provider '{provider_name}' not found in cache!")
            logging.error(f"⚠️ Cannot route RMBB response to correct GHL sub-account")
            
            cache_stats = provider_cache.get_cache_stats()
            logging.info(f"📊 Cache contains {cache_stats['total_providers']} providers")
            
            return jsonify({
                "error": "Provider not found in cache",
                "provider_name": provider_name,
                "available_providers": [p['name'] for p in cache_stats['providers']]
            }), 404
        
        logging.info(f"✅ Found provider location mapping: {provider_name} → {location_id}")
        
        # Process the status update using the workflow handler
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=os.getenv('RMBB_API_KEY'),
            rmbb_team_id=int(os.getenv('RMBB_TEAM_ID')),
            ghl_api_key=os.getenv('GHL_API_KEY')
        )
        
        # Enhanced GHL contact update with comprehensive status tracking
        ivr_tracking_update = {
            "customFields": [
                # Workflow status
                {"key": "rmbb_workflow_status", "value": "ivr_received"},
                {"key": "rmbb_ivr_received_date", "value": datetime.now().isoformat()},
                {"key": "rmbb_webhook_processed", "value": "true"},
                
                # Primary status fields from RMBB Health API
                {"key": "rmbb_case_status", "value": case_status or ""},
                {"key": "rmbb_external_status", "value": external_status or ""},
                {"key": "rmbb_overall_result", "value": overall_insurance_result or ""},
                
                # Insurance-specific statuses
                {"key": "rmbb_primary_insurance_status", "value": primary_insurance_status or ""},
                {"key": "rmbb_secondary_insurance_status", "value": secondary_insurance_status or ""},
                {"key": "rmbb_tertiary_insurance_status", "value": tertiary_insurance_status or ""},
                
                # Insurance results
                {"key": "rmbb_primary_insurance_result", "value": primary_insurance_result or ""},
                {"key": "rmbb_secondary_insurance_result", "value": secondary_insurance_result or ""},
                
                # Communication status
                {"key": "rmbb_last_fax_status", "value": last_fax_status or ""},
                
                # Enhanced approval analysis
                {"key": "rmbb_approval_status", "value": approval_analysis['status']},
                {"key": "rmbb_approval_confidence", "value": approval_analysis['confidence']},
                {"key": "rmbb_approval_message", "value": approval_analysis['message']},
                {"key": "rmbb_determining_field", "value": approval_analysis['determining_field']},
                {"key": "rmbb_determining_value", "value": approval_analysis['determining_value']},
                
                # Legacy IVR data support (backward compatibility)
                {"key": "rmbb_legacy_approval", "value": ivr_data.get('approval_status', '')},
                {"key": "rmbb_qualification_level", "value": ivr_data.get('qualification_level', '')},
                {"key": "rmbb_prior_auth", "value": ivr_data.get('prior_authorization_number', '')},
                {"key": "rmbb_effective_date", "value": ivr_data.get('effective_date', '')},
                {"key": "rmbb_coverage_percentage", "value": str(ivr_data.get('coverage_percentage', ''))}
            ]
        }
        
        # Update the GHL contact
        contact_update_result = workflow_handler.update_ghl_contact(ghl_contact_id, ivr_tracking_update)
        
        if not contact_update_result["success"]:
            logging.error(f"❌ Failed to update GHL contact {ghl_contact_id}: {contact_update_result['error']}")
            return jsonify({
                "error": "Failed to update GHL contact",
                "contact_id": ghl_contact_id,
                "details": contact_update_result['error']
            }), 500
        
        logging.info(f"✅ Updated GHL contact {ghl_contact_id} with IVR results")
        
        # Send enhanced provider notification with comprehensive status information
        patient_name = payload.get('patient_name', 'Patient')
        
        # Create enhanced IVR data including approval analysis
        enhanced_ivr_data = {
            # Enhanced approval analysis
            'approval_status': approval_analysis['status'],
            'approval_confidence': approval_analysis['confidence'],
            'approval_message': approval_analysis['message'],
            'determining_field': approval_analysis['determining_field'],
            'determining_value': approval_analysis['determining_value'],
            
            # RMBB Health case status fields
            'case_status': case_status,
            'external_status': external_status, 
            'overall_insurance_result': overall_insurance_result,
            'primary_insurance_status': primary_insurance_status,
            'secondary_insurance_status': secondary_insurance_status,
            'primary_insurance_result': primary_insurance_result,
            'secondary_insurance_result': secondary_insurance_result,
            'last_fax_status': last_fax_status,
            
            # Legacy IVR data (for backward compatibility)
            'qualification_level': ivr_data.get('qualification_level', ''),
            'treatment_authorized': ivr_data.get('treatment_authorized', ''),
            'coverage_percentage': ivr_data.get('coverage_percentage', ''),
            'prior_authorization_number': ivr_data.get('prior_authorization_number', ''),
            'effective_date': ivr_data.get('effective_date', ''),
            'notes': ivr_data.get('notes', '')
        }
        
        notification_result = workflow_handler.notify_provider_in_subaccount(
            contact_id=ghl_contact_id,
            location_id=location_id,
            ivr_data=enhanced_ivr_data,
            patient_name=patient_name
        )
        
        logging.info(f"📧 Provider notification result: {notification_result}")
        
        return jsonify({
            "status": "success",
            "message": "Enhanced RMBB Health status update processed successfully",
            "external_id": external_id,
            "ghl_contact_updated": ghl_contact_id,
            "provider_notified": notification_result.get('success', False),
            "routing_location": location_id,
            "approval_analysis": {
                "status": approval_analysis['status'],
                "confidence": approval_analysis['confidence'],
                "message": approval_analysis['message'],
                "determining_field": approval_analysis['determining_field']
            },
            "monitored_fields": {
                "case_status": case_status,
                "external_status": external_status,
                "overall_insurance_result": overall_insurance_result,
                "primary_insurance_status": primary_insurance_status,
                "secondary_insurance_status": secondary_insurance_status
            },
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logging.error(f"❌ Error processing RMBB Health webhook: {str(e)}")
        logging.error(f"📋 Request data: {request.get_data(as_text=True)}")
        return jsonify({
            "error": "Internal server error processing RMBB webhook",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for deployment monitoring"""
    
    # Test RMBB Health API connectivity
    rmbb_status = "unknown"
    if WebhookConfig.RMBB_API_KEY and WebhookConfig.RMBB_TEAM_ID:
        try:
            from rmbbhealth import StatusService, RMBBHealthClient
            client = RMBBHealthClient(
                api_key=WebhookConfig.RMBB_API_KEY,
                team_id=int(WebhookConfig.RMBB_TEAM_ID)
            )
            status_service = StatusService(client)
            status_response = status_service.get_status()
            rmbb_status = "healthy" if status_response else "error"
        except Exception as e:
            logging.warning(f"RMBB Health connectivity check failed: {e}")
            rmbb_status = "error"
    else:
        rmbb_status = "not_configured"
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "RMBB Health Webhook Handler",
        "version": "1.0.0",
        "configuration": {
            "rmbb_api_configured": bool(WebhookConfig.RMBB_API_KEY),
            "rmbb_team_id_configured": bool(WebhookConfig.RMBB_TEAM_ID),
            "ghl_api_configured": bool(WebhookConfig.GHL_API_KEY),
            "rmbb_connectivity": rmbb_status
        },
        "endpoints": {
            "webhook": "/webhook/ghl-rmbb-qualification",
            "test": "/webhook/test",
            "health": "/health"
        }
    })

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "/webhook/ghl-rmbb-qualification",
            "/webhook/test",
            "/health"
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logging.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "timestamp": datetime.now().isoformat()
    }), 500

if __name__ == '__main__':
    # Validate configuration before starting
    if not validate_configuration():
        logging.error("❌ Configuration validation failed - server not started")
        exit(1)
    
    # Log startup information
    logging.info("🚀 Starting RMBB Health Webhook Handler")
    logging.info("=" * 60)
    
    # Railway environment debugging
    if WebhookConfig.RAILWAY_ENVIRONMENT_ID:
        logging.info(f"🚂 Railway Environment: {WebhookConfig.RAILWAY_ENVIRONMENT_ID}")
        logging.info(f"🚂 Railway Service: {WebhookConfig.RAILWAY_SERVICE_ID}")
        logging.info(f"🌐 Expected Public URL: https://rmbb-health-webhook.railway.app")
    else:
        logging.info("💻 Running in local development mode")
    
    logging.info(f"🏥 RMBB Health Team ID: {WebhookConfig.RMBB_TEAM_ID}")
    logging.info(f"🔗 GHL V1 API Base: {WebhookConfig.GHL_BASE_URL}")
    logging.info(f"⚙️ Server binding: {WebhookConfig.HOST}:{WebhookConfig.PORT}")
    logging.info("📡 Listening for GHL qualification webhooks")
    logging.info(f"🔗 Main endpoint: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/webhook/ghl-rmbb-qualification")
    logging.info(f"🧪 Test endpoint: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/webhook/test")
    logging.info(f"❤️ Health check: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/health")
    logging.info("=" * 60)
    
    # Start Flask server
    app.run(
        host=WebhookConfig.HOST,
        port=WebhookConfig.PORT,
        debug=WebhookConfig.DEBUG
    )
