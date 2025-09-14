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

# Import the wound calculation integration
from wound_calculation_integration import process_webhook_case_data

# Import for GHL API access
import requests

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
def update_ghl_contact_direct(contact_id, location_id, sub_account_api_key, custom_fields_update):
    """
    Update GHL contact custom fields using direct API v1 call with sub account API key
    
    Args:
        contact_id: GHL contact ID
        location_id: GHL location ID  
        sub_account_api_key: Manually entered sub account API key
        custom_fields_update: Custom fields data in format {"customField": [{"id": "field_id", "value": "val"}]}
        
    Returns:
        dict: {"success": bool, "error": str}
    """
    try:
        # GHL API v1 endpoint for contact update
        url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
        
        # Headers with sub account API key
        headers = {
            "Authorization": f"Bearer {sub_account_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # Ensure correct format: customField (singular) with id/value pairs
        if isinstance(custom_fields_update, list):
            # Convert list format to correct API format
            custom_fields_update = {"customField": custom_fields_update}
        
        # Make direct API call
        response = requests.put(url, headers=headers, json=custom_fields_update)
        
        if response.status_code == 200:
            logging.info(f"✅ Successfully updated contact {contact_id} using sub account API key")
            return {"success": True}
        else:
            error_msg = f"GHL API error {response.status_code}: {response.text}"
            logging.error(f"❌ Failed to update contact {contact_id}: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        error_msg = f"Direct GHL API call failed: {str(e)}"
        logging.error(f"❌ {error_msg}")
        return {"success": False, "error": error_msg}

def _analyze_status_trigger(case_data, approval_analysis):
    """
    Analyze which specific status field triggered this webhook and determine appropriate document processing action.
    
    Args:
        case_data (dict): Complete case data from RMBB Health
        approval_analysis (dict): Result from analyze_rmbb_approval_status()
        
    Returns:
        dict: Analysis of what triggered this status update and what action to take
    """
    # Extract status fields
    case_status = case_data.get('status', '').upper()
    external_status = case_data.get('external_status', '').upper()
    overall_result = case_data.get('overall_insurance_result', '').upper()
    primary_status = case_data.get('primary_insurance', {}).get('status', '').upper()
    secondary_status = case_data.get('secondary_insurance', {}).get('status', '').upper()
    primary_result = case_data.get('primary_insurance', {}).get('result', '').upper()
    secondary_result = case_data.get('secondary_insurance', {}).get('result', '').upper()
    
    # Define trigger patterns for each status type
    approval_triggers = ['APPROVED', 'ACCEPTED', 'AUTHORIZED', 'COVERED', 'QUALIFIED', 'COMPLETED', 'VERIFIED']
    denial_triggers = ['DENIED', 'REJECTED', 'DECLINED', 'NOT COVERED', 'NOT_COVERED', 'DISQUALIFIED', 'FAILED']
    pending_triggers = ['PENDING', 'UNDER REVIEW', 'PROCESSING', 'SUBMITTED', 'IN PROGRESS']
    
    # Analyze what type of status change occurred
    determining_field = approval_analysis.get('determining_field', 'unknown')
    determining_value = approval_analysis.get('determining_value', '')
    
    # Map status changes to document processing actions
    # Check denials FIRST to avoid "NOT COVERED" matching "COVERED" 
    if any(trigger in determining_value for trigger in denial_triggers):
        return {
            'trigger_type': 'DENIAL_STATUS',
            'status_field': determining_field,
            'action_needed': 'PROCESS_DENIAL_DOCUMENTS',
            'document_priority': 'DENIAL_NOTICE',
            'workflow_tags': ['rmbb-denial-received', 'rmbb-appeal-eligible']
        }
    elif any(trigger in determining_value for trigger in approval_triggers):
        if 'PRIMARY' in determining_field.upper() or 'primary_insurance' in determining_field.lower():
            return {
                'trigger_type': 'PRIMARY_INSURANCE_APPROVAL',
                'status_field': determining_field,
                'action_needed': 'PROCESS_IVR_APPROVAL_DOCUMENTS',
                'document_priority': 'IVR_APPROVAL',
                'workflow_tags': ['rmbb-ivr-approved']
            }
        elif 'SECONDARY' in determining_field.upper() or 'secondary_insurance' in determining_field.lower():
            return {
                'trigger_type': 'SECONDARY_INSURANCE_APPROVAL', 
                'status_field': determining_field,
                'action_needed': 'PROCESS_SECONDARY_APPROVAL_DOCUMENTS',
                'document_priority': 'SECONDARY_APPROVAL',
                'workflow_tags': ['rmbb-ivr-approved']
            }
        elif 'OVERALL' in determining_field.upper() or 'overall' in determining_field.lower():
            return {
                'trigger_type': 'OVERALL_CASE_APPROVAL',
                'status_field': determining_field,
                'action_needed': 'PROCESS_FINAL_APPROVAL_DOCUMENTS',
                'document_priority': 'FINAL_APPROVAL',
                'workflow_tags': ['rmbb-final-approved', 'rmbb-case-complete']
            }
        else:
            return {
                'trigger_type': 'GENERAL_APPROVAL',
                'status_field': determining_field,
                'action_needed': 'PROCESS_APPROVAL_DOCUMENTS',
                'document_priority': 'GENERAL_APPROVAL',
                'workflow_tags': ['rmbb-final-approved']
            }
    
    elif any(trigger in determining_value for trigger in pending_triggers):
        return {
            'trigger_type': 'PENDING_STATUS',
            'status_field': determining_field,
            'action_needed': 'PROCESS_PENDING_DOCUMENTS',
            'document_priority': 'PROCESSING_UPDATE',
            'workflow_tags': ['rmbb-pending-update']
        }
    
    else:
        return {
            'trigger_type': 'STATUS_CHANGE',
            'status_field': determining_field,
            'action_needed': 'PROCESS_STATUS_DOCUMENTS',
            'document_priority': 'STATUS_UPDATE',
            'workflow_tags': ['rmbb-status-update']
        }

def build_wound_calculation_ghl_updates(wound_calculation_result):
    """
    Build GHL custom field updates from wound calculation results.
    
    Args:
        wound_calculation_result (dict): Results from wound coverage calculation
        
    Returns:
        list: List of GHL custom field updates for product size quantities
    """
    if not wound_calculation_result or not wound_calculation_result.get('success'):
        return []
    
    ghl_updates = []
    
    # Get the calculated size-specific field updates from the wound calculator
    if 'ghl_field_updates' in wound_calculation_result:
        for field_update in wound_calculation_result['ghl_field_updates']:
            ghl_updates.append({
                "id": field_update['id'],
                "value": field_update['value']
            })
            
            logging.info(f"   🔗 Size-specific update: {field_update['product']} {field_update['size']} = {field_update['units']} units")
    
    logging.info(f"   ✅ Built {len(ghl_updates)} size-specific GHL field updates from wound calculation")
    return ghl_updates

def analyze_rmbb_approval_status(status_data):
    """
    Analyze RMBB Health case status data to determine approval state.
    
    Args:
        status_data (dict): Dictionary containing all status fields from RMBB Health case
        
    Returns:
        dict: Analysis result with status, message, and confidence level
    """
    case_status = (status_data.get('case_status') or '').upper()
    external_status = (status_data.get('external_status') or '').upper()
    overall_result = (status_data.get('overall_insurance_result') or '').upper()
    primary_status = (status_data.get('primary_insurance_status') or '').upper()
    secondary_status = (status_data.get('secondary_insurance_status') or '').upper()
    tertiary_status = (status_data.get('tertiary_insurance_status') or '').upper()
    primary_result = (status_data.get('primary_insurance_result') or '').upper()
    secondary_result = (status_data.get('secondary_insurance_result') or '').upper()
    last_fax = (status_data.get('last_fax_status') or '').upper()
    
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

def populate_subaccount_cache_from_agency():
    """
    Auto-populate provider location cache with all Cell Products sub-accounts.
    
    Uses agency-level GHL API to query all locations under Cell Products agency
    and populate the provider cache before webhook processing begins.
    
    Based on complete_subaccount_creation.py API patterns.
    
    Returns:
        dict: Result with success status and cache statistics
    """
    from services.provider_location_cache import get_provider_cache
    
    # Get agency API key - try dual token mode first, fallback to legacy
    ghl_agency_key = WebhookConfig.GHL_AGENCY_API_KEY or WebhookConfig.GHL_API_KEY
    base_url = WebhookConfig.GHL_BASE_URL
    
    if not ghl_agency_key:
        logging.error("❌ GHL agency API key required for sub-account discovery")
        logging.error("   Set GHL_API_KEY_AGENCY or GHL_API_KEY environment variable")
        return {
            'success': False,
            'error': 'GHL agency API key not configured'
        }
    
    try:
        # API headers for agency-level access (from complete_subaccount_creation.py)
        headers = {
            'Authorization': f'Bearer {ghl_agency_key}',
            'Content-Type': 'application/json',
            'Version': '2021-07-28'
        }
        
        logging.info("🔍 Querying GHL agency for all sub-accounts...")
        
        # Query all locations under Cell Products agency
        response = requests.get(f"{base_url}/locations/", headers=headers)
        
        if response.status_code == 200:
            locations_data = response.json()
            locations = locations_data.get('locations', []) if isinstance(locations_data, dict) else locations_data
            
            logging.info(f"📊 Found {len(locations)} sub-accounts under agency")
            
            provider_cache = get_provider_cache()
            
            # Use incremental update method (no deletion, only add/update)
            update_stats = provider_cache.incremental_provider_update(locations)
            
            # Get final cache statistics
            cache_stats = provider_cache.get_cache_stats()
            
            result = {
                'success': True,
                'total_locations_found': len(locations),
                'new_providers_added': update_stats['new_providers'],
                'existing_providers_updated': update_stats['updated_providers'],
                'unchanged_providers': update_stats['unchanged_providers'],
                'cache_stats': {
                    'total_providers': cache_stats['total_providers'],
                    'total_cases': cache_stats['total_cases'],
                    'cache_file': cache_stats['cache_file']
                }
            }
            
            logging.info(f"✅ Incremental sub-account cache update completed:")
            logging.info(f"   🆕 New providers: {update_stats['new_providers']}")
            logging.info(f"   🔄 Updated providers: {update_stats['updated_providers']}")
            logging.info(f"   ⏸️ Unchanged providers: {update_stats['unchanged_providers']}")
            logging.info(f"   📊 Total cached: {cache_stats['total_providers']} providers, {cache_stats['total_cases']} cases")
            
            return result
            
        else:
            error_msg = f"GHL locations API failed: {response.status_code} - {response.text}"
            logging.error(f"❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }
            
    except Exception as e:
        error_msg = f"Sub-account cache population failed: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'error': error_msg
        }

# Configuration from environment variables
class WebhookConfig:
    """Configuration for webhook server using environment variables"""
    
    # RMBB Health API Configuration
    RMBB_API_KEY = os.environ.get('RMBB_API_KEY', None)
    RMBB_TEAM_ID = os.environ.get('RMBB_TEAM_ID', None)
    
    # GHL V1 API Configuration - Dual Token Support
    GHL_AGENCY_API_KEY = os.environ.get('GHL_API_KEY_AGENCY', None)  # For sub-account creation and locations/cache refresh
    GHL_LOCATION_API_KEY = os.environ.get('GHL_LOCATION_API_KEY', None)  # For contact operations
    GHL_API_KEY = os.environ.get('GHL_API_KEY', None)  # Fallback/legacy support
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
    required_vars = ['RMBB_API_KEY', 'RMBB_TEAM_ID']
    missing_vars = []
    
    for var in required_vars:
        if not getattr(WebhookConfig, var):
            missing_vars.append(var)
    
    # Check for GHL API keys - either dual tokens OR legacy single token
    has_dual_tokens = WebhookConfig.GHL_AGENCY_API_KEY and WebhookConfig.GHL_LOCATION_API_KEY
    has_legacy_token = WebhookConfig.GHL_API_KEY
    
    if not has_dual_tokens and not has_legacy_token:
        missing_vars.append('GHL_API_KEY_AGENCY and GHL_LOCATION_API_KEY (or GHL_API_KEY for legacy)')
    
    if missing_vars:
        logging.error(f"❌ Missing required environment variables: {missing_vars}")
        logging.error("Set these variables before starting the server:")
        for var in missing_vars:
            if 'GHL' in var:
                logging.error(f"  # Dual token mode (recommended):")
                logging.error(f"  export GHL_API_KEY_AGENCY='agency_token_here'")
                logging.error(f"  export GHL_LOCATION_API_KEY='location_token_here'")
                logging.error(f"  # OR legacy single token mode:")
                logging.error(f"  export GHL_API_KEY='single_token_here'")
                break
            else:
                logging.error(f"  export {var}='your_value_here'")
        return False
    
    # Log which mode we're using
    if has_dual_tokens:
        logging.info("✅ Using dual token mode (agency + location tokens)")
    else:
        logging.info("✅ Using legacy single token mode")
    
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
        
        # CRITICAL TIMING: Auto-populate provider cache FIRST (before any processing)
        # This ensures fresh cache data before creating cases and mapping
        logging.info("⏰ STEP 1: Auto-populating provider cache from GHL agency...")
        cache_result = populate_subaccount_cache_from_agency()
        
        if cache_result['success']:
            logging.info(f"✅ Provider cache refreshed: {cache_result['new_providers_added']} new, "
                        f"{cache_result['existing_providers_updated']} updated, "
                        f"{cache_result['cache_stats']['total_providers']} total providers")
        else:
            logging.warning(f"⚠️ Cache population failed (continuing anyway): {cache_result['error']}")
        
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
        
        # Get location API key for contact operations
        ghl_location_key = WebhookConfig.GHL_LOCATION_API_KEY or WebhookConfig.GHL_API_KEY
        ghl_agency_key = WebhookConfig.GHL_AGENCY_API_KEY or WebhookConfig.GHL_API_KEY
        
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=WebhookConfig.RMBB_API_KEY,
            rmbb_team_id=rmbb_team_id,
            ghl_api_key=ghl_agency_key,
            ghl_location_api_key=ghl_location_key
        )
        
        logging.info("🚀 Starting complete GHL → RMBB Health → GHL workflow...")
        
        # Process the complete workflow
        result = workflow_handler.run_complete_workflow(payload)
        
        # DEBUG: Log result type and content
        logging.info(f"🔍 DEBUG - Result type: {type(result)}")
        logging.info(f"🔍 DEBUG - Result: {result}")
        
        # 🔥 NEW: Document Processing After Case Creation - Process initial case documents
        document_processing_result = None
        if result["success"] and result.get("rmbb_case_id"):
            case_id = result.get("rmbb_case_id")
            contact_id = result["contact_id"]
            location_id = result["location_id"]
            provider_name = result["provider_name"]
            
            logging.info(f"📄 Processing initial case documents for newly created case {case_id}")
            
            # 🆕 NEW: Store case_id in GHL contact custom field
            try:
                logging.info(f"💾 Storing case_id {case_id} in GHL contact custom field")
                workflow_handler.update_contact_case_id(contact_id, location_id, case_id)
            except Exception as case_id_error:
                logging.error(f"❌ Failed to update case_id custom field: {str(case_id_error)}")
                # Don't fail the entire workflow if this fails
            
            try:
                # For initial case creation, process all available documents
                initial_status_context = {
                    'trigger_type': 'INITIAL_CASE_CREATION',
                    'status_field': 'case_created',
                    'action_needed': 'PROCESS_INITIAL_DOCUMENTS',
                    'document_priority': 'INITIAL_SUBMISSION',
                    'workflow_tags': ['rmbb-case-created', 'rmbb-documents-processed']
                }
                
                document_processing_result = workflow_handler.process_approval_document_with_extraction(
                    case_id=str(case_id),
                    contact_id=contact_id,
                    location_id=location_id,
                    provider_name=provider_name,
                    status_context=initial_status_context
                )
                
                if document_processing_result.get("success"):
                    logging.info(f"✅ Initial document processing completed:")
                    logging.info(f"   📋 Files processed: {document_processing_result.get('files_processed', 0)}")
                    logging.info(f"   📄 Document type: {document_processing_result.get('document_type', 'N/A')}")
                    logging.info(f"   🏷️ Tags added: {document_processing_result.get('workflow_tags', [])}")
                else:
                    logging.warning(f"⚠️ Initial document processing had warnings: {document_processing_result.get('message', 'Unknown')}")
                    
            except Exception as e:
                logging.error(f"❌ Initial document processing failed: {str(e)}")
                logging.error(traceback.format_exc())
                # Continue with normal workflow - document processing is supplementary
                document_processing_result = {
                    "success": False,
                    "error": str(e),
                    "files_processed": 0
                }
        
        if result["success"]:
            response_data = {
                "success": True,
                "message": "GHL → RMBB Health → GHL workflow completed successfully",
                "external_id": result["external_id"],
                "case_id": result.get("rmbb_case_id"),
                "contact_id": result["contact_id"],
                "location_id": result["location_id"],
                "provider_name": result["provider_name"],
                "submission_status": result["submission_status"],
                "completed_at": result["completed_at"],
                "timestamp": datetime.now().isoformat()
            }
            
            # Add document processing results to response
            if document_processing_result:
                response_data["document_processing"] = {
                    "success": document_processing_result.get("success", False),
                    "files_processed": document_processing_result.get("files_processed", 0),
                    "document_type": document_processing_result.get("document_type"),
                    "workflow_tags": document_processing_result.get("workflow_tags", []),
                    "message": document_processing_result.get("message")
                }
                
                if not document_processing_result.get("success"):
                    response_data["document_processing"]["error"] = document_processing_result.get("error")
            
            logging.info(f"✅ Workflow completed successfully")
            logging.info(f"🆔 External ID: {result['external_id']}")
            logging.info(f"📋 Submission Status: {result['submission_status']}")
            logging.info(f"🏥 Case ID: {result.get('rmbb_case_id')}")
            logging.info(f"📧 Contact ID: {result['contact_id']}")
            
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
        provider_name = payload.get('provider_name')  # May not be present
        
        # STEP 1: Try to get routing info from case_id mapping (preferred method)
        case_mapping = None
        if case_id:
            from services.provider_location_cache import get_provider_cache
            provider_cache = get_provider_cache()
            case_mapping = provider_cache.get_case_mapping(str(case_id))
            
            if case_mapping:
                logging.info(f"✅ Found case mapping for {case_id}: {case_mapping['provider_name']} → {case_mapping.get('location_id')}")
                # Use mapped values as primary source
                provider_name = case_mapping['provider_name']
                external_id = case_mapping.get('external_id', external_id)
            else:
                logging.warning(f"⚠️ No case mapping found for case_id {case_id} - falling back to webhook data")
        
        # ADAPTIVE: Handle both complete case data OR minimal webhook + API call
        case_data = None
        
        # Check if webhook contains complete case data OR is just a simple status update (Option 1)
        case_status = payload.get('status', '').upper()
        if (payload.get('primary_insurance') or payload.get('overall_insurance_result') is not None or
            case_status in ['CASE CREATED']):
            logging.info(f"📦 Simple status update ({case_status}) - using webhook data directly")
            case_data = payload
        else:
            # Complex status that needs additional case data - fetch via API (Option 2)
            logging.info(f"📡 Minimal webhook received - fetching case {case_id} via API")
            
            if not case_id:
                return jsonify({"error": "Missing case_id - cannot fetch case data"}), 400
                
            try:
                # Import services for API call
                from services.case_service import CaseService
                case_service = CaseService()
                
                # Fetch complete case data
                case_data = case_service.get_case(case_id)
                
                if not case_data:
                    return jsonify({"error": f"Could not fetch case data for case_id {case_id}"}), 404
                    
                logging.info(f"✅ Fetched complete case data via API: {len(case_data)} fields")
                
            except Exception as e:
                logging.error(f"❌ Failed to fetch case data via API: {str(e)}")
                return jsonify({
                    "error": "Failed to fetch case data from RMBB Health API",
                    "case_id": case_id,
                    "details": str(e)
                }), 500
        
        # ENHANCED: Extract status fields from case_data (whether from webhook or API)
        case_status = case_data.get('status')                           # Primary status field
        external_status = case_data.get('external_status')             # External-facing status
        overall_insurance_result = case_data.get('overall_insurance_result', '')  # Final approval result
        
        # Insurance-specific status monitoring
        primary_insurance_status = case_data.get('primary_insurance', {}).get('status', '')
        secondary_insurance_status = case_data.get('secondary_insurance', {}).get('status', '')
        tertiary_insurance_status = case_data.get('tertiary_insurance', {}).get('status', '')
        
        # Extract insurance results for detailed tracking
        primary_insurance_result = case_data.get('primary_insurance', {}).get('result', '')
        secondary_insurance_result = case_data.get('secondary_insurance', {}).get('result', '')
        
        # Monitor last_fax_status for communication tracking
        last_fax_status = case_data.get('last_fax_status', '')
        
        # Legacy support: Also check ivr_data for backward compatibility
        ivr_data = payload.get('ivr_data', {})  # Legacy data might still be in original payload
        
        # Validate required fields - external_id can come from case mapping
        if not external_id and not case_id:
            return jsonify({"error": "Missing external_id or case_id - cannot route webhook"}), 400
        
        if not provider_name:
            logging.warning(f"⚠️ No provider_name found - checking if case mapping provided it")
            if not case_mapping:
                return jsonify({"error": "Missing provider_name for GHL routing and no case mapping found"}), 400
        
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
        
        # STEP 2: Get location_id for GHL routing
        location_id = None
        contact_id_from_mapping = None
        
        if case_mapping:
            # Use case mapping data (preferred - already has location_id)
            location_id = case_mapping.get('location_id')
            contact_id_from_mapping = case_mapping.get('contact_id')
            logging.info(f"✅ Using case mapping: {provider_name} → {location_id}")
        else:
            # Fallback: lookup provider in cache
            from services.provider_location_cache import get_provider_cache
            provider_cache = get_provider_cache()
            location_id = provider_cache.get_location_id(provider_name)
            logging.info(f"📍 Using provider lookup: {provider_name} → {location_id}")
        
        if not location_id:
            logging.error(f"❌ CRITICAL: Cannot determine location_id for provider '{provider_name}'")
            logging.error(f"   Case mapping: {'Found' if case_mapping else 'Not found'}")
            logging.error(f"   Provider cache: {'Searched' if not case_mapping else 'Not searched'}")
            
            return jsonify({
                "error": "Cannot determine GHL location_id for routing",
                "case_id": case_id,
                "provider_name": provider_name,
                "case_mapping_found": bool(case_mapping)
            }), 404
        
        logging.info(f"✅ Routing determined: {provider_name} → {location_id}")
        
        # Process the status update using the workflow handler
        ghl_location_key = WebhookConfig.GHL_LOCATION_API_KEY or WebhookConfig.GHL_API_KEY
        ghl_agency_key = WebhookConfig.GHL_AGENCY_API_KEY or WebhookConfig.GHL_API_KEY
        
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=WebhookConfig.RMBB_API_KEY,
            rmbb_team_id=int(WebhookConfig.RMBB_TEAM_ID),
            ghl_api_key=ghl_agency_key,
            ghl_location_api_key=ghl_location_key
        )

        # 🔥 ENHANCED: Status-Specific Document Processing - Process documents based on which status triggered this webhook
        document_processing_result = None
        if case_id:
            # Determine what type of status update triggered this webhook
            status_trigger_analysis = _analyze_status_trigger(case_data, approval_analysis)
            
            logging.info(f"📄 Status-triggered document processing for case {case_id}:")
            logging.info(f"   🎯 Trigger type: {status_trigger_analysis['trigger_type']}")
            logging.info(f"   📊 Status field: {status_trigger_analysis['status_field']}")
            logging.info(f"   💡 Action needed: {status_trigger_analysis['action_needed']}")
            
            try:
                # Process documents with status-specific context
                document_processing_result = workflow_handler.process_approval_document_with_extraction(
                    case_id=str(case_id),
                    contact_id=ghl_contact_id,
                    location_id=location_id,
                    provider_name=provider_name,
                    status_context=status_trigger_analysis  # NEW: Pass status context for targeted processing
                )
                
                if document_processing_result.get("success"):
                    logging.info(f"✅ Status-triggered document processing completed:")
                    logging.info(f"   📋 Files processed: {document_processing_result.get('files_processed', 0)}")
                    logging.info(f"   📄 Document type: {document_processing_result.get('document_type', 'N/A')}")
                    logging.info(f"   ✅ Approval status extracted: {document_processing_result.get('approval_status', 'N/A')}")
                    logging.info(f"   🏷️ Tags to add: {document_processing_result.get('workflow_tags', [])}")
                else:
                    logging.warning(f"⚠️ Document processing completed with warnings: {document_processing_result.get('message', 'Unknown')}")
                    
            except Exception as e:
                logging.error(f"❌ Status-triggered document processing failed: {str(e)}")
                logging.error(traceback.format_exc())
                # Continue with normal webhook processing - document processing is supplementary
                document_processing_result = {
                    "success": False,
                    "error": str(e),
                    "files_processed": 0
                }
        
        # 💊 WOUND COVERAGE CALCULATION: Process approved cases for product size optimization
        wound_calculation_result = None
        if approval_analysis['status'] == 'APPROVED':
            logging.info(f"🧮 Approved case detected - processing wound coverage calculation")
            try:
                wound_calculation_result = process_webhook_case_data(case_data)
                
                if wound_calculation_result and wound_calculation_result.get('success'):
                    logging.info(f"✅ Wound coverage calculation completed:")
                    logging.info(f"   📊 {wound_calculation_result['calculation_summary']}")
                    logging.info(f"   🔗 Will update {len(wound_calculation_result['ghl_field_updates'])} product size fields")
                else:
                    logging.warning(f"⚠️ Wound coverage calculation not applicable or failed for this case")
                    
            except Exception as e:
                logging.error(f"❌ Wound coverage calculation error: {str(e)}")
                logging.error(traceback.format_exc())
                # Continue with normal webhook processing - wound calculation is supplementary
        
        # Enhanced GHL contact update with comprehensive status tracking
        # Using CORRECT format: customField (singular) with value
        
        # Build base custom fields list
        custom_fields_list = [
                # Workflow status - using correct GHL field IDs
                {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "ivr_received"},  # rmbb_workflow_status
                {"id": "4AnL32P9rjYcPjbukcok", "value": datetime.now().isoformat()},  # rmbb_ivr_received_date
                {"id": "drfCODR4HhoKeI3eoH6J", "value": "true"},  # rmbb_webhook_processed
                
                # Primary status fields from RMBB Health API - using correct GHL field IDs
                # CORRECTED: Send actual RMBB status data, not approval analysis
                {"id": "A2gqU59iygkmxwUeO2j6", "value": case_status or ""},  # rmbb_case_status
                {"id": "b7odVJaRBRTBQlVaUCF1", "value": external_status or ""},  # rmbb_external_status
                {"id": "NStZu6i6cSflIhmRS7Eg", "value": overall_insurance_result or ""},  # rmbb_overall_result
                
                # Insurance-specific statuses - using correct GHL field IDs
                # Fix: Use insurance results, not status
                {"id": "lek4SmWzewBgvrAXBLWy", "value": primary_insurance_result or primary_insurance_status or ""},  # rmbb_primary_insurance_status
                {"id": "vnZmPnf00xi9ImOLxao9", "value": secondary_insurance_result or secondary_insurance_status or ""},  # rmbb_secondary_insurance_status
                {"id": "JeBBYNNHOWqyYU5FMA1w", "value": tertiary_insurance_status or ""},  # rmbb_tertiary_insurance_status
                
                # Insurance results - using correct GHL field IDs
                {"id": "tXkwLnHu00e9t2MdGarP", "value": primary_insurance_result or ""},  # rmbb_primary_insurance_result
                {"id": "0viEC6QFPlBZIm75N0fE", "value": secondary_insurance_result or ""},  # rmbb_secondary_insurance_result
                
                # DOCUMENT PROCESSING FIELDS - Current Status Fields (4 fields)
                {"id": "XueHehokZYjJSvWGzjfk", "value": ""},  # rmbb_current_patient_info
                {"id": "FoqW1DyrjW6WtsoPflFZ", "value": ""},  # rmbb_current_insurance_info
                {"id": "tLNZ4EYxxXUO9HrDpkl5", "value": ""},  # rmbb_current_notes
                {"id": "CWCMdJsRU4hMEDS32U4s", "value": approval_analysis['status']},  # rmbb_current_status
                
                # DOCUMENT PROCESSING FIELDS - IVR-Specific Extraction Fields (5 fields)
                {"id": "TAA2QAEXDh14bIkYacWW", "value": ""},  # rmbb_ivr_patient_data
                {"id": "VXpnvGzV94MPikiXXrFh", "value": primary_insurance_result or ""},  # rmbb_ivr_primary_insurance
                {"id": "IYWefx90XVJMC3kIJaSz", "value": secondary_insurance_result or ""},  # rmbb_ivr_secondary_insurance
                {"id": "m8Ml4hPPfNgfoURqBsSt", "value": overall_insurance_result or ""},  # rmbb_ivr_coverage_summary
                {"id": "Y2zXVZYUzXLxLRm70J1E", "value": ""},  # rmbb_ivr_authorization_info
                
                # DOCUMENT PROCESSING FIELDS - Document Tracking Fields (3 fields)
                {"id": "dGy54D7hPD0Ydp4c8EsO", "value": ""},  # rmbb_document_history
                {"id": "WGKrQzlaNsK8Y4t5bUYf", "value": ""},  # rmbb_case_summary
                {"id": "DuqFjhMUOv2yKa5qbdyR", "value": ""},  # rmbb_total_documents
                
                # DOCUMENT PROCESSING FIELDS - Legacy Field (1 field)
                {"id": "pbPVNjx7lmzlMkh4QYHs", "value": approval_analysis['status']},  # rmbb_approval_status
                
                # PRODUCT QUANTITY FIELDS - Units/CM2 for each product (9 fields)
                # NOTE: These base fields are kept for backward compatibility
                # Size-specific fields from wound calculation will be added separately
                {"id": "tOGJkZFd2ymaHGKYrVU2", "value": ""},  # AmnioMaxx (Q4239) Units/CM2
                {"id": "f2ahSKCm3LRuN0djazBg", "value": ""},  # AmnioAmp-MP (Q4250) Units/CM2
                {"id": "TIjFjavn2llFCwGizWj2", "value": ""},  # Membrane Wrap Hydro (Q4290) Units/CM2
                {"id": "1hvUvoGbO7rMLSgEFoDz", "value": ""},  # Membrane Wrap (Q4205) Units/CM2
                {"id": "nS8MzgEAKuaGNjxdPGe7", "value": ""},  # Biovance (Q4154) Units/CM2
                {"id": "49vxcOnMCVYPyDdDuH80", "value": ""},  # XCell Amnio Matrix (Q4280) Units/CM2
                {"id": "gN96ValY4BEEzUFBD6Z0", "value": ""},  # Palingen (Q4173) Units/CM2
                {"id": "b5h4W8FSMO1E8KSleixD", "value": ""},  # Amchoplast (Q4316) Units/CM2
                {"id": "lqdbhafh2zTeM23u0OMe", "value": ""},  # Helicoll (Q4164) Units/CM2
                
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
        
        # 💊 ADD WOUND CALCULATION RESULTS: Add size-specific product quantity fields for approved cases
        if wound_calculation_result and wound_calculation_result.get('success'):
            wound_calculation_updates = build_wound_calculation_ghl_updates(wound_calculation_result)
            custom_fields_list.extend(wound_calculation_updates)
            logging.info(f"   🔗 Added {len(wound_calculation_updates)} size-specific product fields from wound calculation")
        
        # Build final update structure
        ivr_tracking_update = {
            "customField": custom_fields_list
        }
        
        # Check for manually entered sub account API key first
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        sub_account_api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
        
        if sub_account_api_key:
            # Use direct GHL API v1 call with sub account API key
            logging.info(f"🔑 Using manually entered sub account API key for location {location_id}")
            contact_update_result = update_ghl_contact_direct(ghl_contact_id, location_id, sub_account_api_key, ivr_tracking_update)
        else:
            # Fallback to current agency-level API
            logging.info(f"⚠️ No sub account API key found - using agency-level API fallback")
            contact_update_result = workflow_handler.update_ghl_contact(ghl_contact_id, ivr_tracking_update)
        
        if not contact_update_result["success"]:
            logging.error(f"❌ Failed to update GHL contact {ghl_contact_id}: {contact_update_result['error']}")
            return jsonify({
                "error": "Failed to update GHL contact",
                "contact_id": ghl_contact_id,
                "details": contact_update_result['error']
            }), 500
        
        logging.info(f"✅ Updated GHL contact {ghl_contact_id} with IVR results")
        
        # 🏷️ ENHANCED: Apply workflow tags based on status analysis
        if status_trigger_analysis and status_trigger_analysis.get('workflow_tags') and sub_account_api_key:
            logging.info(f"🏷️ Applying workflow tags for trigger type: {status_trigger_analysis['trigger_type']}")
            tags_applied = []
            tags_failed = []
            
            for tag in status_trigger_analysis['workflow_tags']:
                # Use the _add_contact_tag method from workflow handler
                tag_success = workflow_handler._add_contact_tag(
                    contact_id=ghl_contact_id,
                    location_id=location_id, 
                    api_key=sub_account_api_key,
                    tag_name=tag
                )
                
                if tag_success:
                    tags_applied.append(tag)
                    logging.info(f"✅ Applied workflow tag: {tag}")
                else:
                    tags_failed.append(tag)
                    logging.warning(f"⚠️ Failed to apply workflow tag: {tag}")
            
            logging.info(f"🏷️ Workflow tags summary: {len(tags_applied)} applied, {len(tags_failed)} failed")
        elif not sub_account_api_key:
            logging.warning(f"⚠️ Cannot apply workflow tags - no sub account API key available")
        else:
            logging.info(f"ℹ️ No workflow tags to apply for this status update")
        
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
            patient_name=patient_name,
            case_id=case_id  # Pass case_id for hierarchical cache lookup
        )
        
        logging.info(f"📧 Provider notification result: {notification_result}")
        
        # Include document processing results in response
        response_data = {
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
        }
        
        # Add document processing results to response
        if document_processing_result:
            response_data["document_processing"] = {
                "success": document_processing_result.get("success", False),
                "files_processed": document_processing_result.get("files_processed", 0),
                "document_type": document_processing_result.get("document_type"),
                "approval_status": document_processing_result.get("approval_status"),
                "message": document_processing_result.get("message")
            }
            
            if not document_processing_result.get("success"):
                response_data["document_processing"]["error"] = document_processing_result.get("error")
        
        # Add wound calculation results to response for approved cases
        if wound_calculation_result:
            response_data["wound_calculation"] = {
                "success": wound_calculation_result.get("success", False),
                "calculation_summary": wound_calculation_result.get("calculation_summary", ""),
                "total_coverage_cm2": wound_calculation_result.get("total_coverage_cm2", 0),
                "actual_waste_percent": wound_calculation_result.get("actual_waste_percent", 0),
                "ghl_fields_updated": len(wound_calculation_result.get("ghl_field_updates", []))
            }
            
            if wound_calculation_result.get("success"):
                # Add original case data context
                if wound_calculation_result.get("original_case_data"):
                    response_data["wound_calculation"]["case_context"] = wound_calculation_result["original_case_data"]
                
                # Add product mapping info
                if wound_calculation_result.get("mapped_product"):
                    response_data["wound_calculation"]["mapped_product"] = wound_calculation_result["mapped_product"]
            else:
                response_data["wound_calculation"]["error"] = wound_calculation_result.get("error", "Unknown wound calculation error")
        
        return jsonify(response_data)
        
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
            "status_update": "/webhook/rmbb-status-update",
            "reorder": "/webhook/ghl-reorder",
            "test": "/webhook/test",
            "test_cache": "/test/populate-cache", 
            "health": "/health"
        }
    })

@app.route('/test/populate-cache', methods=['GET', 'POST'])
def test_populate_subaccount_cache():
    """Test endpoint to manually trigger sub-account cache population"""
    
    try:
        logging.info("🧪 Manual cache population test triggered")
        
        # Get current cache stats before population
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        before_stats = provider_cache.get_cache_stats()
        
        logging.info(f"📊 Cache stats before population: {before_stats['total_providers']} providers")
        
        # Trigger cache population
        result = populate_subaccount_cache_from_agency()
        
        # Get updated cache stats
        after_stats = provider_cache.get_cache_stats()
        
        response_data = {
            "test": "populate_subaccount_cache",
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "before_stats": {
                "total_providers": before_stats['total_providers'],
                "cache_file": before_stats['cache_file']
            },
            "after_stats": {
                "total_providers": after_stats['total_providers'], 
                "cache_file": after_stats['cache_file']
            }
        }
        
        if result['success']:
            logging.info(f"✅ Test cache population completed successfully")
            return jsonify(response_data), 200
        else:
            logging.error(f"❌ Test cache population failed: {result['error']}")
            return jsonify(response_data), 500
            
    except Exception as e:
        error_msg = f"Test cache population error: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        
        return jsonify({
            "test": "populate_subaccount_cache", 
            "timestamp": datetime.now().isoformat(),
            "error": error_msg
        }), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "/webhook/ghl-rmbb-qualification",
            "/webhook/test",
            "/test/populate-cache",
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

@app.route('/webhook/ghl-reorder', methods=['POST'])
def handle_ghl_reorder():
    """
    Handle GHL reorder webhook requests for 10-week reorder system.
    
    Expected payload from GHL form:
    {
        "id": "9ycwwscO60MGHiTTBDzo",              // contact.id
        "rmbb_case_id": "53330",                  // contact.rmbb_case_id  
        "provider_name": "Dr. Smith",             // contact.provider_name
        "contactnew_wound_size": "4.5",          // contact.contactnew_wound_size (in cm2)
        "product_selection": "amniomaxx"          // contact.product_selection (new field)
    }
    """
    try:
        logging.info("🔄 Received GHL reorder webhook request")
        
        # Validate request method and content type
        if request.method != 'POST':
            return jsonify({"error": "Only POST requests are allowed"}), 405
            
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        
        # Parse and validate payload
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Empty JSON payload"}), 400
            
        logging.info(f"📦 GHL reorder payload: {json.dumps(payload, indent=2)}")
        
        # Extract required fields (updated to match GHL payload structure)
        contact_id = payload.get('id')  # GHL sends contact.id as 'id'
        case_id = payload.get('rmbb_case_id')  # GHL sends contact.rmbb_case_id 
        new_wound_size = payload.get('new_wound_size')  # GHL sends new_wound_size
        provider_name = payload.get('provider_name')  # New field: contact.provider_name
        product_selection = payload.get('product_selection')  # New field
        
        # Validate required fields
        missing_fields = []
        if not case_id:
            missing_fields.append('rmbb_case_id')
        if not contact_id:
            missing_fields.append('id')
        if not new_wound_size:
            missing_fields.append('new_wound_size')
            
        if missing_fields:
            return jsonify({
                "error": "Missing required fields",
                "missing_fields": missing_fields,
                "required_fields": ["id", "rmbb_case_id", "new_wound_size"]
            }), 400
        
        # Validate wound size is numeric
        try:
            wound_size_cm2 = float(new_wound_size)
            if wound_size_cm2 <= 0:
                return jsonify({"error": "new_wound_size must be a positive number"}), 400
        except ValueError:
            return jsonify({"error": "new_wound_size must be a valid number"}), 400
        
        logging.info(f"🔄 Processing reorder for case {case_id}: {wound_size_cm2} cm²")
        
        # Step 1: Get original approved product from provider cache
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        
        approved_product = provider_cache.get_approved_product(case_id)
        if not approved_product:
            return jsonify({
                "status": "error",
                "message": f"No approved product found for case {case_id}",
                "case_id": case_id,
                "error": "Case not found in provider cache or missing product info",
                "timestamp": datetime.now().isoformat()
            }), 404
        
        logging.info(f"💊 Found approved product: {approved_product['name']} (ID: {approved_product['product_id']})")
        
        # Step 2: Get case routing information  
        case_mapping = provider_cache.get_case_mapping(case_id)
        if not case_mapping:
            return jsonify({
                "status": "error", 
                "message": f"No routing information found for case {case_id}",
                "case_id": case_id,
                "error": "Case mapping not found in provider cache",
                "timestamp": datetime.now().isoformat()
            }), 404
        
        # Step 2.5: VALIDATE payload data matches stored provider location JSON data
        validation_errors = []
        
        # Validate contact_id matches
        stored_contact_id = case_mapping.get("contact_id")
        if stored_contact_id != contact_id:
            validation_errors.append(f"Contact ID mismatch - payload: {contact_id}, stored: {stored_contact_id}")
        
        # Validate provider_name matches  
        stored_provider_name = case_mapping.get("provider_name")
        if stored_provider_name != provider_name:
            validation_errors.append(f"Provider name mismatch - payload: {provider_name}, stored: {stored_provider_name}")
        
        # Validate product_selection matches approved product (if provided)
        if product_selection:
            approved_product_name = approved_product.get("name", "").lower()
            approved_q_code = approved_product.get("q_code", "").lower()
            product_selection_lower = product_selection.lower()
            
            # Normalize product names for comparison (remove hyphens, spaces)
            normalized_approved = approved_product_name.replace("-", "").replace(" ", "")
            normalized_selection = product_selection_lower.replace("-", "").replace(" ", "")
            
            if (normalized_selection not in normalized_approved and 
                product_selection_lower != approved_q_code and
                normalized_approved not in normalized_selection):
                validation_errors.append(f"Product mismatch - payload: {product_selection}, stored: {approved_product['name']} ({approved_product.get('q_code', '')})")
        
        if validation_errors:
            return jsonify({
                "status": "error",
                "message": "Payload validation failed - data does not match stored provider location JSON",
                "case_id": case_id,
                "validation_errors": validation_errors,
                "stored_data": {
                    "contact_id": stored_contact_id,
                    "provider_name": stored_provider_name, 
                    "approved_product": approved_product["name"]
                },
                "payload_data": {
                    "contact_id": contact_id,
                    "provider_name": provider_name,
                    "product_selection": product_selection
                },
                "timestamp": datetime.now().isoformat()
            }), 400
        
        logging.info(f"✅ Payload validation passed - all data matches provider location JSON")
        
        # Step 3: Create case data structure for wound calculation (reusing existing process)
        reorder_case_data = {
            "id": int(case_id),
            "case_id": case_id,  # CRITICAL: Add case_id for estimate manager (expects 'case_id' not 'id')
            "contact_id": contact_id,  # CRITICAL: Add contact_id for downstream processing
            "location_id": case_mapping["location_id"],  # CRITICAL: Add location_id for estimate manager
            "status": "APPROVED",  # Reorders are by definition approved
            "external_status": "APPROVED",
            "overall_insurance_result": "APPROVED",
            
            # Use new wound size from reorder payload (NOT from GHL)
            "wound_size": f"{wound_size_cm2} cm2",
            "total_wound_size": f"{wound_size_cm2} cm2", 
            "wound_type": "Reorder - Healing Wound",
            
            # Use original approved product
            "product": {
                "id": approved_product["product_id"],
                "name": approved_product["name"],
                "q_code": approved_product["q_code"]
            },
            
            # Approved insurance (reorders assumed approved)
            "primary_insurance": {
                "status": "APPROVED",
                "result": "APPROVED"
            }
        }
        
        logging.info(f"🔄 Reprocessing with new wound size: {wound_size_cm2} cm² for product {approved_product['name']}")
        
        # Step 4: Process using existing wound calculation integration (with field clearing)
        from wound_calculation_integration import WoundCalculationIntegration
        from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
        from ghl_opportunity_estimate_manager import GHLOpportunityEstimateManager
        
        # Initialize workflow handler for GHL operations
        workflow_handler = GHLRMBBWorkflowHandler(
            rmbb_api_key=WebhookConfig.RMBB_API_KEY,
            rmbb_team_id=int(WebhookConfig.RMBB_TEAM_ID), 
            ghl_api_key=WebhookConfig.GHL_API_KEY
        )
        
        integration = WoundCalculationIntegration()
        integration.workflow_handler = workflow_handler
        
        # CRITICAL: Clear existing product fields before recalculating
        clear_result = workflow_handler.clear_all_product_fields(
            contact_id=contact_id,
            location_id=case_mapping["location_id"]
        )
        
        if not clear_result.get("success"):
            logging.warning(f"⚠️ Field clearing had issues: {clear_result.get('message')}")
        else:
            logging.info(f"🧹 Cleared {clear_result.get('fields_cleared', 0)} product fields")
        
        # Process the reorder using existing approved case logic
        reorder_result = integration.process_approved_case(reorder_case_data)
        
        if reorder_result and reorder_result.get('success'):
            logging.info(f"✅ Reorder processed successfully for case {case_id}")
            
            # Step 5: Update rmbb_wound_size_coverage_calculator field with full calculation
            wound_calc_update = {
                "customField": [
                    {"id": "XQLSYwSOodHOBrqv8oz0", "value": reorder_result.get('calculation_summary', '')}  # rmbb_wound_size_coverage_calculator
                ]
            }
            
            field_update_result = workflow_handler.update_ghl_contact(contact_id, wound_calc_update, provider_name=provider_name)
            if field_update_result.get("success"):
                logging.info(f"✅ Updated wound size coverage calculator field with reorder calculation")
            else:
                logging.warning(f"⚠️ Failed to update wound calculation field: {field_update_result.get('error')}")
            
            # Step 6: Create GHL invoice estimate (since already approved)
            # Get the API key and location info for this case
            case_location_id = case_mapping.get("location_id")
            case_api_key = provider_cache.get_sub_account_api_key_by_location_id(case_location_id)
            
            if not case_api_key:
                logging.error(f"❌ No API key found for location {case_location_id}")
                return jsonify({
                    "status": "error",
                    "message": f"No API key found for case location {case_location_id}",
                    "case_id": case_id
                }), 500
            
            estimate_manager = GHLOpportunityEstimateManager(api_key=case_api_key, sub_account_id=case_location_id, location_id=case_location_id)
            estimate_result = estimate_manager.create_wound_product_estimate(reorder_case_data, reorder_result)
            
            if estimate_result.get("success"):
                logging.info(f"📄 Created reorder opportunity estimate successfully: {estimate_result.get('opportunity_id')}")
            else:
                logging.warning(f"⚠️ Failed to create reorder opportunity estimate: {estimate_result.get('error')}")
            
            # Step 7: Apply reorder tag to trigger downstream workflows
            tag_result = workflow_handler.add_reorder_tag(
                contact_id=contact_id,
                location_id=case_mapping["location_id"]
            )
            
            if tag_result.get("success"):
                logging.info(f"🏷️ Reorder tag applied successfully")
            else:
                logging.warning(f"⚠️ Reorder tag application had issues: {tag_result.get('message')}")
            
            response_data = {
                "status": "success",
                "message": "Product reorder processed successfully",
                "case_id": case_id,
                "contact_id": contact_id,
                "new_wound_size_cm2": wound_size_cm2,
                "reorder_calculation": {
                    "product_name": reorder_result.get("product_name"),
                    "calculation_summary": reorder_result.get("calculation_summary"),
                    "total_coverage_cm2": reorder_result.get("total_coverage_cm2"),
                    "actual_waste_percent": reorder_result.get("actual_waste_percent"),
                    "ghl_fields_updated": len(reorder_result.get("ghl_field_updates", []))
                },
                "ghl_contact_updated": reorder_result.get("ghl_contact_updated", False),
                "reorder_tag_applied": tag_result.get("tag_applied", False),
                "fields_cleared": clear_result.get("fields_cleared", 0),
                "estimate_created": estimate_result.get("success", False),
                "estimate_id": estimate_result.get("estimate_id", ""),
                "timestamp": datetime.now().isoformat()
            }
            
            # Add estimate details if successful
            if estimate_result.get("success"):
                response_data["estimate_details"] = {
                    "estimate_id": estimate_result.get("estimate_id"),
                    "total_amount": estimate_result.get("total_amount"),
                    "line_items": estimate_result.get("line_items", [])
                }
            
            return jsonify(response_data), 200
        else:
            error_msg = reorder_result.get('error', 'Unknown reorder processing error')
            logging.error(f"❌ Reorder processing failed: {error_msg}")
            
            return jsonify({
                "status": "error", 
                "message": "Reorder processing failed",
                "case_id": case_id,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }), 500
            
    except Exception as e:
        error_msg = f"GHL reorder webhook processing error: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        
        return jsonify({
            "status": "error",
            "message": error_msg,
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/webhook/provider-onboarding', methods=['POST'])
def handle_provider_onboarding():
    """
    Handle provider onboarding survey webhook from GHL.
    
    This endpoint processes provider signup forms and automatically:
    1. Creates GHL sub-account using survey data
    2. Updates master_registry.json with new provider entry
    3. Creates individual provider JSON file with API key placeholders
    
    Expected payload from GHL survey form:
    {
        "Business name": "Provider Business Name",
        "first_name": "John", 
        "last_name": "Doe",
        "email": "provider@example.com",
        "phone": "+1234567890",
        "address1": "123 Main St",
        "city": "Phoenix",
        "state": "AZ", 
        "postal_code": "85001",
        "ein": "12-3456789",  // Optional - Federal Tax ID
        "npi": "1234567890",  // Optional - National Provider ID
        "locationId": "Sqbexj54nvsxOI4V7SsD"  // Cell Products location
    }
    """
    try:
        logging.info("🏥 Received provider onboarding survey webhook")
        
        # Validate request method and content type
        if request.method != 'POST':
            return jsonify({"error": "Only POST requests are allowed"}), 405
            
        # Parse payload
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Empty JSON payload"}), 400
            
        logging.info(f"📦 Provider onboarding payload: {json.dumps(payload, indent=2)}")
        
        # Extract required provider information from survey data
        business_name = (payload.get('Business name') or     # GHL format
                        payload.get('business name') or 
                        payload.get('business_name') or
                        payload.get('Legal Company Name') or
                        '').strip()
        
        first_name = (payload.get('first_name') or 
                     payload.get('firstName') or '').strip()
        
        last_name = (payload.get('last_name') or 
                    payload.get('lastName') or '').strip()
        
        email = (payload.get('email') or 
                payload.get('emailAddress') or '').strip()
        
        phone = (payload.get('phone') or 
                payload.get('phoneNumber') or '').strip()
        
        # Address fields
        address1 = payload.get('address1', '').strip()
        city = payload.get('city', '').strip()
        state = payload.get('state', '').strip()
        postal_code = payload.get('postal_code', '').strip()
        
        # Business identifiers (for GHL sub-account creation only)
        ein = payload.get('ein', '').strip()
        npi = payload.get('npi', '').strip()
        
        # Source location validation
        source_location_id = payload.get('locationId', '')
        expected_cell_products_id = 'Sqbexj54nvsxOI4V7SsD'
        
        if source_location_id != expected_cell_products_id:
            logging.warning(f"⚠️ Unexpected source location: {source_location_id}, expected: {expected_cell_products_id}")
        
        # Validate required fields
        if not all([business_name, first_name, last_name, email]):
            missing_fields = []
            if not business_name: missing_fields.append('Business name')
            if not first_name: missing_fields.append('first_name')
            if not last_name: missing_fields.append('last_name')
            if not email: missing_fields.append('email')
            
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}",
                "timestamp": datetime.now().isoformat()
            }), 400
        
        logging.info(f"🏢 Processing provider onboarding for: {business_name}")
        logging.info(f"👤 Contact: {first_name} {last_name} ({email})")
        
        # Step 1: Create GHL sub-account using existing workflow handler
        logging.info("🔧 Step 1: Creating GHL sub-account...")
        
        # Prepare sub-account data for GHL API
        clean_phone = phone.replace('+1', '').replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
        
        subaccount_data = {
            "name": f"{business_name} - {first_name} {last_name}",
            "businessName": business_name,
            "address": address1,
            "city": city,
            "state": state,
            "postalCode": postal_code,
            "country": "US",
            "phone": clean_phone,
            "email": email,
            "website": payload.get('website', ''),
            "timezone": "America/Phoenix",  # Cell Products timezone
            "firstName": first_name,
            "lastName": last_name
        }
        
        # Add EIN and NPI if provided (for GHL sub-account creation only)
        if ein:
            subaccount_data["ein"] = ein
        if npi:
            subaccount_data["npi"] = npi
        
        # Create sub-account via GHL API
        headers = {
            "Authorization": f"Bearer {WebhookConfig.GHL_AGENCY_API_KEY}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        ghl_response = requests.post(
            f"{WebhookConfig.GHL_BASE_URL}/locations/",
            headers=headers,
            json=subaccount_data
        )
        
        if ghl_response.status_code not in [200, 201]:
            error_msg = f"GHL sub-account creation failed: {ghl_response.status_code} - {ghl_response.text}"
            logging.error(f"❌ {error_msg}")
            return jsonify({
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }), 500
        
        ghl_result = ghl_response.json()
        new_location_id = ghl_result.get('id')
        
        if not new_location_id:
            error_msg = "GHL API did not return location ID"
            logging.error(f"❌ {error_msg}")
            return jsonify({
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }), 500
        
        logging.info(f"✅ GHL sub-account created successfully - ID: {new_location_id}")
        
        # Step 2: Update provider cache registry with new provider
        logging.info("🔧 Step 2: Updating provider registry...")
        
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        
        # Add provider to registry using existing cache system (maintains correct format)
        cache_result = provider_cache.add_or_update_provider(
            provider_name=business_name,
            location_id=new_location_id,
            increment_submissions=True
        )
        
        if cache_result:
            logging.info(f"✅ Provider registry updated successfully")
        else:
            logging.warning(f"⚠️ Provider registry update failed, but sub-account was created")
        
        # Step 3: Return success response
        response_data = {
            "success": True,
            "message": "Provider onboarding completed successfully",
            "provider_data": {
                "business_name": business_name,
                "contact_name": f"{first_name} {last_name}",
                "email": email,
                "ghl_location_id": new_location_id,
                "registry_updated": cache_result
            },
            "next_steps": [
                "Provider entry created in master registry with 'pending_manual_entry' API key status",
                "Individual provider JSON file created with API key placeholders",
                "Manual API key entry required via provider dashboard or support"
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        logging.info(f"🎉 Provider onboarding successful for {business_name} (Location: {new_location_id})")
        return jsonify(response_data), 200
        
    except Exception as e:
        error_msg = f"Provider onboarding webhook processing error: {str(e)}"
        logging.error(f"❌ {error_msg}")
        logging.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": error_msg,
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
    logging.info(f"📋 RMBB status update: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/webhook/rmbb-status-update")
    logging.info(f"🔄 GHL reorder: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/webhook/ghl-reorder")
    logging.info(f"🏥 Provider onboarding: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/webhook/provider-onboarding")
    logging.info(f"🧪 Test endpoint: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/webhook/test")
    logging.info(f"❤️ Health check: http://{WebhookConfig.HOST}:{WebhookConfig.PORT}/health")
    logging.info("=" * 60)
    
    # Start Flask server
    app.run(
        host=WebhookConfig.HOST,
        port=WebhookConfig.PORT,
        debug=WebhookConfig.DEBUG
    )
