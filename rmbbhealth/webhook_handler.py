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
    approval_triggers = ['APPROVED', 'ACCEPTED', 'AUTHORIZED', 'COVERED', 'QUALIFIED', 'COMPLETED']
    denial_triggers = ['DENIED', 'REJECTED', 'DECLINED', 'NOT COVERED', 'DISQUALIFIED', 'FAILED']
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
        if 'PRIMARY' in determining_field.upper():
            return {
                'trigger_type': 'PRIMARY_INSURANCE_APPROVAL',
                'status_field': determining_field,
                'action_needed': 'PROCESS_IVR_APPROVAL_DOCUMENTS',
                'document_priority': 'IVR_APPROVAL',
                'workflow_tags': ['rmbb-ivr-approved']
            }
        elif 'SECONDARY' in determining_field.upper():
            return {
                'trigger_type': 'SECONDARY_INSURANCE_APPROVAL', 
                'status_field': determining_field,
                'action_needed': 'PROCESS_SECONDARY_APPROVAL_DOCUMENTS',
                'document_priority': 'SECONDARY_APPROVAL',
                'workflow_tags': ['rmbb-ivr-approved']
            }
        elif 'OVERALL' in determining_field.upper():
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
        logging.error("   Set GHL_AGENCY_API_KEY or GHL_API_KEY environment variable")
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
    GHL_AGENCY_API_KEY = os.environ.get('GHL_AGENCY_API_KEY', None)  # For locations/cache refresh
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
        missing_vars.append('GHL_AGENCY_API_KEY and GHL_LOCATION_API_KEY (or GHL_API_KEY for legacy)')
    
    if missing_vars:
        logging.error(f"❌ Missing required environment variables: {missing_vars}")
        logging.error("Set these variables before starting the server:")
        for var in missing_vars:
            if 'GHL' in var:
                logging.error(f"  # Dual token mode (recommended):")
                logging.error(f"  export GHL_AGENCY_API_KEY='agency_token_here'")
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
        
        # Check if webhook contains complete case data (Option 1)
        if payload.get('primary_insurance') or payload.get('overall_insurance_result') is not None:
            logging.info("📦 Webhook contains complete case data - using directly")
            case_data = payload
        else:
            # Minimal webhook - need to fetch case data via API (Option 2)
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
        
        # Enhanced GHL contact update with comprehensive status tracking
        # Using CORRECT format: customField (singular) with value
        ivr_tracking_update = {
            "customField": [
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
                
                # DOCUMENT PROCESSING FIELDS - Current Status Fields (5 fields)
                {"id": "XueHehokZYjJSvWGzjfk", "value": ""},  # rmbb_current_patient_info
                {"id": "FoqW1DyrjW6WtsoPflFZ", "value": ""},  # rmbb_current_insurance_info
                {"id": "XQLSYwSOodHOBrqv8oz0", "value": approval_analysis['message'][:500]},  # rmbb_current_decision_summary
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
        
        # Check for manually entered sub account API key first
        from services.provider_location_cache import get_provider_cache
        provider_cache = get_provider_cache()
        sub_account_api_key = provider_cache.get_sub_account_api_key_by_location_id(ghl_location_id)
        
        if sub_account_api_key:
            # Use direct GHL API v1 call with sub account API key
            logging.info(f"🔑 Using manually entered sub account API key for location {ghl_location_id}")
            contact_update_result = update_ghl_contact_direct(ghl_contact_id, ghl_location_id, sub_account_api_key, ivr_tracking_update)
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
                    location_id=ghl_location_id, 
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
            patient_name=patient_name
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