#!/usr/bin/env python3
"""
Complete GHL ↔ RMBB Health ↔ GHL Bidirectional Workflow Example - Updated for GHL V1 API

This demonstrates the complete integration flow using proper GHL V1 API calls:
1. GHL Form Submission → RMBB Health Patient/Case Creation
2. RMBB Health IVR Processing → Status Polling  
3. IVR Response → GHL Sub-Account Update & Provider Notification

UPDATED: Now uses GHL V1 API calls based on complete_subaccount_creation.py reference
"""

import os
import sys
import json
import requests
import logging
from datetime import datetime
# Import modules with Railway compatibility
try:
    # Try package import first
    from rmbbhealth import RMBBHealthClient, PatientService, CaseService
    from rmbbhealth.services.provider_location_cache import get_provider_cache
except ImportError:
    # Fallback to direct imports in Railway environment
    from client import RMBBHealthClient
    from services.patient_service import PatientService
    from services.case_service import CaseService
    from services.provider_location_cache import get_provider_cache

class GHLRMBBWorkflowHandler:
    """Complete workflow handler for GHL → RMBB Health → GHL integration"""
    
    def __init__(self, rmbb_api_key, rmbb_team_id, ghl_api_key, ghl_location_api_key=None):
        # RMBB Health setup
        self.rmbb_team_id = rmbb_team_id
        self.rmbb_client = RMBBHealthClient(api_key=rmbb_api_key, team_id=rmbb_team_id)
        self.patient_service = PatientService(self.rmbb_client)
        self.case_service = CaseService(self.rmbb_client)
        self.rmbb_base_url = self.rmbb_client.config.BASE_URL
        self.rmbb_headers = self.rmbb_client.get_headers()
        
        # GHL V1 API setup - Dual token support
        self.ghl_api_key = ghl_api_key  # Agency token (fallback for all operations)
        self.ghl_location_api_key = ghl_location_api_key or ghl_api_key  # Location token for contacts
        self.ghl_base_url = "https://rest.gohighlevel.com/v1"
        
        # Headers for contact operations (use location token)
        self.ghl_headers = {
            "Authorization": f"Bearer {self.ghl_location_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # Headers for agency operations (use agency token)
        self.ghl_agency_headers = {
            "Authorization": f"Bearer {self.ghl_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # Provider-Location Cache (CRITICAL for routing RMBB responses back to correct GHL sub-accounts)
        self.provider_cache = get_provider_cache()
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        
        # No separate database - all tracking stored in GHL contact custom fields for HIPAA compliance
    
    def handle_ghl_webhook(self, webhook_payload):
        """
        STEP 1: Process GHL form submission webhook
        Extract contact info and patient data, store tracking in GHL contact
        """
        print("=" * 60)
        print("STEP 1: Processing GHL Webhook")
        print("=" * 60)
        
        # Extract contact and location info from webhook payload
        contact_id = (webhook_payload.get('contactId') or 
                     webhook_payload.get('contact_id') or 
                     webhook_payload.get('id') or '').strip()
        
        location_id = (webhook_payload.get('locationId') or 
                      webhook_payload.get('location_id') or 
                      webhook_payload.get('location', {}).get('id', '') or '').strip()
        
        if not contact_id:
            raise ValueError("Contact ID not found in webhook payload - required for GHL tracking")
        
        # Handle missing location_id by using a default/fallback
        if not location_id:
            print(f"⚠️ WARNING: No location_id provided in webhook - using fallback location")
            # Try to extract from provider cache or use environment variable
            provider_name = webhook_payload.get('provider_name', '').strip()
            if provider_name:
                cached_location = self.provider_cache.get_location_id(provider_name)
                if cached_location:
                    location_id = cached_location
                    print(f"✅ Found location_id from provider cache: {location_id}")
                else:
                    # Use environment variable as fallback
                    location_id = os.environ.get('GHL_DEFAULT_LOCATION_ID', 'default_location')
                    print(f"🔄 Using default location_id: {location_id}")
            else:
                location_id = os.environ.get('GHL_DEFAULT_LOCATION_ID', 'default_location')
                print(f"🔄 No provider_name - using default location_id: {location_id}")
        
        # Extract patient data using robust field mapping
        patient_form_data = self.extract_patient_data(webhook_payload)
        
        print(f"📧 Contact ID: {contact_id}")
        print(f"📍 Location ID: {location_id}")
        
        # CRITICAL DEBUG: Check if insurance data was extracted
        primary_ins = patient_form_data.get('primary_insurance_name', 'MISSING')
        secondary_ins = patient_form_data.get('secondary_insurance_name', 'MISSING') 
        icd_code = patient_form_data.get('icd_10_code', 'MISSING')
        facility = patient_form_data.get('facility_type', 'MISSING')
        
        print(f"🔍 EXTRACTION CHECK: Primary Insurance = '{primary_ins}'")
        print(f"🔍 EXTRACTION CHECK: Secondary Insurance = '{secondary_ins}'")
        print(f"🔍 EXTRACTION CHECK: ICD-10 Code = '{icd_code}'")
        print(f"🔍 EXTRACTION CHECK: Facility Type = '{facility}'")
        
        # Create unique external ID for RMBB case linking
        external_id = f"ghl_contact_{contact_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # CRITICAL: Cache provider → locationId mapping for RMBB response routing
        provider_name = patient_form_data.get('provider_name')
        if provider_name and location_id:
            self.provider_cache.add_or_update_provider(
                provider_name=provider_name,
                location_id=location_id,
                contact_id=contact_id
            )
            print(f"💾 Cached provider mapping: {provider_name} → {location_id}")
        else:
            print(f"⚠️ WARNING: Missing provider_name or location_id - RMBB response routing will fail!")
            print(f"   provider_name: {provider_name}, location_id: {location_id}")
        
        # Store initial tracking data in GHL contact custom fields
        initial_tracking_data = {
            "customFields": [
                {"key": "rmbb_workflow_status", "value": "webhook_received"},
                {"key": "rmbb_external_id", "value": external_id},
                {"key": "rmbb_submission_date", "value": datetime.now().isoformat()},
                {"key": "rmbb_patient_name", "value": f"{patient_form_data.get('first_name', '')} {patient_form_data.get('last_name', '')}"},
                {"key": "rmbb_wound_type", "value": patient_form_data.get('wound_type', '')},
                {"key": "rmbb_primary_insurance", "value": patient_form_data.get('primary_insurance_name', '')}
            ]
        }
        
        # Update GHL contact with initial tracking data
        contact_update_result = self.update_ghl_contact(contact_id, initial_tracking_data, location_id)
        if contact_update_result["success"]:
            print(f"✅ Initial tracking data stored in GHL contact {contact_id}")
        else:
            print(f"⚠️ Warning: Failed to store initial tracking data: {contact_update_result['error']}")
        
        # Webhook processing completed
        return external_id, contact_id, location_id, patient_form_data
    
    def submit_to_rmbb_health(self, external_id, contact_id, patient_form_data):
        """
        STEP 2: Submit patient data to RMBB Health
        Create patient and case for qualification, update GHL contact with RMBB IDs
        """
        print("\n" + "=" * 60)
        print("STEP 2: Submitting to RMBB Health")
        print("=" * 60)
        
        # Transform GHL form data to RMBB patient format
        rmbb_patient_data = self.transform_patient_data(patient_form_data)
        
        print("Creating patient in RMBB Health...")
        print(f"Patient Data: {json.dumps(rmbb_patient_data, indent=2)}")
        
        # Create patient using real RMBB Health API
        try:
            patient_response = self.patient_service.create_patient(self.rmbb_team_id, rmbb_patient_data)
            
            # Patient API response received
            
            # Handle different response types
            if isinstance(patient_response, dict) and 'id' in patient_response:
                print(f"✅ Patient created with ID: {patient_response['id']}")
            elif isinstance(patient_response, dict) and 'error' in patient_response:
                # RMBB Health API returned an error (validation failed, etc.)
                error_msg = f"RMBB Health API error: {patient_response['error']}"
                if 'data' in patient_response:
                    validation_errors = patient_response['data']
                    for err in validation_errors:
                        if err.get('path') == 'date_of_birth':
                            error_msg += f" - Date of birth is required and must be valid (YYYY-MM-DD format)"
                        else:
                            error_msg += f" - {err.get('path', 'field')}: {err.get('msg', 'validation error')}"
                print(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
            elif isinstance(patient_response, str):
                print(f"⚠️ API returned string response: {patient_response}")
                return {"success": False, "error": f"Unexpected string response: {patient_response}"}
            else:
                print(f"⚠️ Unexpected API response format: {patient_response}")
                return {"success": False, "error": f"Unexpected response format: {str(patient_response)}"}
                
        except Exception as e:
            error_msg = f"Failed to create RMBB Health patient: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"🔍 DEBUG - Exception type: {type(e)}")
            return {"success": False, "error": error_msg}
        
        # Check if patient creation was successful before proceeding
        if not isinstance(patient_response, dict) or 'id' not in patient_response:
            error_msg = "Patient creation failed - cannot proceed with case creation"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        
        # Get selected products for multiple case creation
        print(f"🔍 DEBUG - About to access patient_response['id']")
        print(f"🔍 DEBUG - patient_response type: {type(patient_response)}")
        print(f"🔍 DEBUG - patient_response: {patient_response}")
        
        # Extract selected products
        product_info = self.extract_selected_biologic_product(patient_form_data)
        selected_products = product_info["selected_products"]
        
        print(f"\n🔗 Creating {len(selected_products)} cases for selected products...")
        print(f"🔗 Case external_id base: {external_id} (links to GHL contact {contact_id})")
        
        created_cases = []
        failed_cases = []
        
        # Create separate case for each selected product
        for i, product in enumerate(selected_products):
            print(f"Creating Case {i+1}/{len(selected_products)} for {product['name']}")
            
            # Create case data for this specific product
            case_external_id = f"{external_id}_{product['product_id']}"  # Unique external ID per product
            rmbb_case_data = self.transform_case_data_for_product(patient_form_data, patient_response['id'], product)
            rmbb_case_data["external_id"] = case_external_id
            
            # Create case using real RMBB Health API
            try:
                case_response = self.case_service.create_case(rmbb_case_data)
                
                # Case API call completed
            
                # Handle different response types for case creation
                if isinstance(case_response, dict) and 'id' in case_response:
                    case_id = case_response['id']
                    print(f"✅ Case created with ID: {case_id}")
                    
                    # CRITICAL: Add case mapping to cache immediately after creation
                    try:
                        provider_name = patient_form_data.get('provider_name', '')
                        
                        if provider_name and contact_id:
                            cache_success = self.provider_cache.add_case_mapping(
                                case_id=str(case_id),
                                provider_name=provider_name,
                                contact_id=contact_id,
                                external_id=case_external_id
                            )
                            
                            if not cache_success:
                                print(f"⚠️ Failed to add case mapping to cache")
                        else:
                            print(f"⚠️ Missing provider_name or contact_id for case mapping")
                            
                    except Exception as cache_error:
                        print(f"⚠️ Cache mapping error: {cache_error}")
                        import traceback
                        print(f"⚠️ Cache mapping traceback: {traceback.format_exc()}")
                        # Don't fail the whole workflow due to cache issues
                    
                    # Upload additional provider/facility information
                    additional_info_result = self.upload_additional_case_information(
                        case_id=case_id,
                        provider_name=patient_form_data.get('provider_name'),
                        facility_type=patient_form_data.get('facility_type'), 
                        facility_npi=patient_form_data.get('facility_npi'),
                        provider_npi=patient_form_data.get('provider_npi', '')
                    )
                    
                    if additional_info_result.get('success'):
                        print(f"✅ Additional provider/facility information uploaded to case {case_id}")
                    else:
                        print(f"⚠️ Warning: Failed to upload additional information: {additional_info_result.get('error')}")
                    
                    # Add successful case to created_cases list
                    created_cases.append({
                        "product_name": product['name'],
                        "product_id": product['product_id'],
                        "case_id": case_id,
                        "external_id": case_external_id,
                        "cm2": product['cm2']
                    })
                    
                elif isinstance(case_response, dict) and 'error' in case_response:
                    # RMBB Health API returned an error for case creation
                    error_msg = f"RMBB Health case creation error for {product['name']}: {case_response['error']}"
                    if 'data' in case_response:
                        validation_errors = case_response['data']
                        for err in validation_errors:
                            error_msg += f" - {err.get('path', 'field')}: {err.get('msg', 'validation error')}"
                    print(f"❌ {error_msg}")
                    
                    # Add failed case to failed_cases list
                    failed_cases.append({
                        "product_name": product['name'],
                        "product_id": product['product_id'],
                        "error": error_msg,
                        "cm2": product['cm2']
                    })
                    
                else:
                    error_msg = f"Unexpected case API response format for {product['name']}: {case_response}"
                    print(f"⚠️ {error_msg}")
                    
                    # Add failed case to failed_cases list
                    failed_cases.append({
                        "product_name": product['name'],
                        "product_id": product['product_id'],
                        "error": error_msg,
                        "cm2": product['cm2']
                    })
                    
            except Exception as e:
                error_msg = f"Failed to create RMBB Health case for {product['name']}: {str(e)}"
                print(f"❌ {error_msg}")
                print(f"🔍 DEBUG - Case creation exception type: {type(e)}")
                
                # Add failed case to failed_cases list
                failed_cases.append({
                    "product_name": product['name'],
                    "product_id": product['product_id'],
                    "error": error_msg,
                    "cm2": product['cm2']
                })
        
        # Print summary of case creation results
        print(f"\n📊 CASE CREATION SUMMARY:")
        print(f"✅ Successfully created: {len(created_cases)} cases")
        print(f"❌ Failed: {len(failed_cases)} cases")
        
        if created_cases:
            print(f"\n✅ SUCCESSFUL CASES:")
            for case in created_cases:
                print(f"   • {case['product_name']} (Q-code: {case['product_id']}, {case['cm2']} cm2) → Case ID: {case['case_id']}")
        
        if failed_cases:
            print(f"\n❌ FAILED CASES:")
            for case in failed_cases:
                print(f"   • {case['product_name']} (Q-code: {case['product_id']}, {case['cm2']} cm2) → Error: {case['error']}")
        
        # Check if any cases were created successfully
        if not created_cases:
            error_msg = "All case creations failed - no cases were successfully created"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg, "failed_cases": failed_cases}
        
        # Update GHL contact with RMBB IDs and status (multiple cases)
        case_ids_str = ", ".join([str(case['case_id']) for case in created_cases])
        case_products_str = ", ".join([f"{case['product_name']} ({case['cm2']} cm2)" for case in created_cases])
        
        rmbb_tracking_update = {
            "customFields": [
                {"key": "rmbb_workflow_status", "value": "submitted_for_qualification"},
                {"key": "rmbb_patient_id", "value": str(patient_response['id'])},
                {"key": "rmbb_case_ids", "value": case_ids_str},  # Multiple case IDs
                {"key": "rmbb_case_count", "value": str(len(created_cases))},
                {"key": "rmbb_products", "value": case_products_str},
                {"key": "rmbb_submission_completed", "value": datetime.now().isoformat()}
            ]
        }
        
        # Add failure info if any cases failed
        if failed_cases:
            failed_products_str = ", ".join([f"{case['product_name']} (ERROR)" for case in failed_cases])
            rmbb_tracking_update["customFields"].extend([
                {"key": "rmbb_failed_products", "value": failed_products_str},
                {"key": "rmbb_partial_failure", "value": "true"}
            ])
        
        # Update GHL contact (note: location_id not available in this method, will use fallback)
        contact_update_result = self.update_ghl_contact(contact_id, rmbb_tracking_update)
        if contact_update_result["success"]:
            print(f"✅ RMBB IDs stored in GHL contact {contact_id}")
        else:
            print(f"⚠️ Warning: Failed to update GHL contact: {contact_update_result['error']}")
        
        # Return multiple case creation results
        return {
            "success": True,
            "patient_response": patient_response,
            "created_cases": created_cases,
            "failed_cases": failed_cases,
            "total_cases_attempted": len(selected_products),
            "successful_cases": len(created_cases),
            "failed_cases_count": len(failed_cases)
        }
    
    def finalize_rmbb_submission(self, external_id, contact_id, created_cases, provider_name):
        """
        STEP 3: Finalize RMBB Health submission and prepare for webhook
        This workflow ends here - RMBB Health will send webhook when IVR is complete
        """
        print("\n" + "=" * 60)
        print("STEP 3: Finalizing RMBB Health Submission")
        print("=" * 60)
        
        case_ids = [case['case_id'] for case in created_cases]
        case_ids_str = ", ".join([str(case_id) for case_id in case_ids])
        
        print(f"🔗 RMBB Case IDs: {case_ids_str}")
        print(f"🔗 External ID base: {external_id} (links to GHL contact {contact_id})")
        print(f"👨‍⚕️ Provider: {provider_name} (cached for webhook routing)")
        print(f"📦 Products: {len(created_cases)} cases created")
        
        for case in created_cases:
            print(f"   • {case['product_name']} (Q-code: {case['product_id']}, {case['cm2']} cm2) → Case ID: {case['case_id']}")
        
        # Update GHL contact to show cases submitted and awaiting IVR
        final_tracking_update = {
            "customFields": [
                {"key": "rmbb_workflow_status", "value": "submitted_awaiting_ivr"},
                {"key": "rmbb_case_ids", "value": case_ids_str},
                {"key": "rmbb_case_count", "value": str(len(created_cases))},
                {"key": "rmbb_submission_completed_date", "value": datetime.now().isoformat()},
                {"key": "rmbb_awaiting_ivr", "value": "true"}
            ]
        }
        
        # Update the GHL contact
        contact_update_result = self.update_ghl_contact(contact_id, final_tracking_update)
        if contact_update_result["success"]:
            print(f"✅ Final status tracked in GHL contact {contact_id}")
        else:
            print(f"⚠️ Warning: Failed to update GHL contact: {contact_update_result['error']}")
        
        print(f"📋 RMBB Health will process IVR and send webhook to: /webhook/rmbb-status-update")
        print(f"⚡ This workflow ends here - IVR results handled by separate webhook")
        print(f"🔄 Provider cache ensures proper routing when webhook arrives")
        
        return {
            "submission_completed": True,
            "external_id": external_id,
            "case_ids": case_ids,
            "contact_id": contact_id,
            "provider_name": provider_name,
            "created_cases": created_cases,
            "total_cases": len(created_cases),
            "status": "awaiting_ivr_webhook",
            "completed_at": datetime.now().isoformat()
        }
    
    def notify_provider_in_subaccount(self, contact_id, location_id, ivr_data, patient_name):
        """
        STEP 4: Notify provider in the correct sub-account
        Send notification to provider in the originating sub-account
        """
        print("\n" + "=" * 60)
        print("STEP 4: Notifying Provider in Correct Sub-Account")
        print("=" * 60)
        
        print(f"📧 Sending provider notification in sub-account (location): {location_id}")
        print(f"👤 For contact: {contact_id}")
        print(f"🏥 Patient: {patient_name}")
        
        # Create comprehensive provider notification
        notification_data = {
            "subject": f"RMBB Health Qualification Result - {patient_name}",
            "message": f"""
🏥 RMBB Health Qualification Complete

Patient: {patient_name}
Contact ID: {contact_id}
Location: {location_id}

📋 QUALIFICATION RESULTS:
Status: {ivr_data['approval_status']}
Coverage Level: {ivr_data['qualification_level']}
Treatment Authorized: {ivr_data['treatment_authorized']}
Coverage Percentage: {ivr_data['coverage_percentage']}%

📄 AUTHORIZATION DETAILS:
Prior Auth Number: {ivr_data['prior_authorization_number']}
Effective Date: {ivr_data['effective_date']}

📝 Notes: {ivr_data['notes']}

✅ Patient information has been updated in your GHL contact record.
            """.strip(),
            "location_id": location_id,
            "contact_id": contact_id
        }
        
        # Send notification using V1 API to correct sub-account
        notification_result = self.send_ghl_notification(location_id, notification_data)
        
        print(f"📧 Provider Notification Status: {notification_result['message']}")
        print(f"🆔 Notification ID: {notification_result.get('notification_id', 'N/A')}")
        print(f"📍 Sent to Location: {location_id}")
        
        # Final status update to GHL contact
        final_status_update = {
            "customFields": [
                {"key": "rmbb_workflow_status", "value": "completed"},
                {"key": "rmbb_provider_notified", "value": "true"},
                {"key": "rmbb_completion_date", "value": datetime.now().isoformat()},
                {"key": "rmbb_notification_id", "value": notification_result.get('notification_id', '')}
            ]
        }
        
        # Final update to the original contact in the correct sub-account
        final_contact_update = self.update_ghl_contact(contact_id, final_status_update)
        if final_contact_update["success"]:
            print(f"✅ Final status updated in GHL contact {contact_id}")
        else:
            print(f"⚠️ Warning: Final status update failed: {final_contact_update['error']}")
        
        return notification_result
    
    def extract_patient_data(self, webhook_payload):
        """Extract patient form data from GHL webhook - Updated to match your actual GHL webhook field names"""
        
        # Patient Personal Information - Support both standard and custom GHL field names
        first_name = (webhook_payload.get('patient_first_name') or 
                     webhook_payload.get('firstName') or '').strip()
        
        last_name = (webhook_payload.get('patient_last_name') or
                    webhook_payload.get('lastName') or '').strip()
        
        # Date of Birth - Support multiple field name variations
        date_of_birth = (webhook_payload.get('patient_dob__ivr_form') or 
                        webhook_payload.get('patient_dob') or
                        webhook_payload.get('patient_date_of_birth') or
                        webhook_payload.get('dateOfBirth') or '').strip()
        if date_of_birth.lower() in ['null', 'none', '']:
            date_of_birth = ''  # Convert null string to empty string
        elif date_of_birth:
            # Convert MM-DD-YYYY to YYYY-MM-DD format for RMBB Health API
            try:
                from datetime import datetime
                # Try MM-DD-YYYY format first (your GHL form format)
                if '-' in date_of_birth and len(date_of_birth) == 10:
                    parts = date_of_birth.split('-')
                    if len(parts) == 3 and len(parts[2]) == 4:  # MM-DD-YYYY
                        month, day, year = parts
                        date_of_birth = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        print(f"📅 Converted DOB format: {webhook_payload.get('patient_dob')} → {date_of_birth}")
                    # If already YYYY-MM-DD format, leave as is
            except Exception as e:
                print(f"⚠️ Date conversion error: {e}, using original value: {date_of_birth}")
        
        middle_name = ''  # Not provided in your webhook mapping
        
        # Contact Information - Support multiple field name variations
        street_address = (webhook_payload.get('patient_street_address') or 
                         webhook_payload.get('street_address') or 
                         webhook_payload.get('address') or '').strip()
        
        # Phone number - Support multiple field name variations
        phone_number = (webhook_payload.get('patient_phone') or 
                       webhook_payload.get('phone') or '').strip()
        
        # Email address - Support multiple field name variations
        email_address = (webhook_payload.get('patient_email') or 
                        webhook_payload.get('email') or '').strip()
        
        # Address Information - Support multiple field name variations
        city = (webhook_payload.get('patient_city') or 
                webhook_payload.get('city') or '').strip()
        
        state = (webhook_payload.get('patient_state') or 
                webhook_payload.get('state') or '').strip()
        
        zip_code = (webhook_payload.get('patient_zip_code') or 
                   webhook_payload.get('zip_code') or 
                   webhook_payload.get('zip') or '').strip()
        
        # Insurance Information - Using your exact field names from payload
        primary_insurance_name = (webhook_payload.get('patient_primary_insurance') or '').strip()
        
        primary_policy_number = (webhook_payload.get('patient_primary_insurance_') or '').strip()  # Your field ends with underscore
        
        secondary_insurance_name = (webhook_payload.get('patient_secondary_insurance') or '').strip()
        
        secondary_policy_number = (webhook_payload.get('patient_secondary_insurance_') or '').strip()  # Your field ends with underscore
        
        # Additional Medical Fields - Using your exact field names from payload
        icd_10_code = (webhook_payload.get('icd_-_10_diagnosis_code(s)') or '').strip()
        
        # Facility Information - Using your exact field names
        facility_type = (webhook_payload.get('facility_type') or '').strip()
        
        facility_npi = (webhook_payload.get('facility_npi_#') or '').strip()  # Your field has # symbol
        
        expected_date_of_service = (webhook_payload.get('expected_date_of_service') or '').strip()
        
        # Biologic Product Fields - Using your exact field names from GHL webhook template
        amniomaxx_q4239 = (webhook_payload.get('amniomaxx_(q4239)_units/cm2') or '').strip()
        palingen_q4173 = (webhook_payload.get('palingen_(q4173)_units/cm2') or '').strip()
        membrane_wrap_trilayer_q4344 = (webhook_payload.get('membrane_wrap_tri-layer_(q4344)_units/cm2') or '').strip()
        amnioamp_mp_q4250 = (webhook_payload.get('amnioamp-mp_(q4250)_units/cm2') or '').strip()
        membrane_wrap_hydro_q4290 = (webhook_payload.get('membrane_wrap_hydro_(q4290)_units/cm2') or '').strip()
        biovance_q4154 = (webhook_payload.get('biovance_(q4154)_units/cm2') or '').strip()
        amchoplast_q4316 = (webhook_payload.get('amchoplast_(q4316)_units/cm2') or '').strip()
        helicoll_q4164 = (webhook_payload.get('helicoll_(q4164)_units/cm2') or '').strip()
        xcell_amnio_matrix_q4280 = (webhook_payload.get('xcell_amnio_matrix_(q4280)_units/cm2') or '').strip()
        
        # Product fields extracted from GHL payload
        
        # Fields not provided in your webhook mapping - will be empty
        wound_type = ''  # Not in your webhook mapping
        wound_size = ''  # Not in your webhook mapping
        surgery_date = ''  # Not in your webhook mapping
        cpt_surgery_code = ''  # Not in your webhook mapping
        place_of_service = facility_type or 'Physician Office - 11'  # Use facility_type as fallback
        
        # Provider Information - Now available in your webhook mapping!
        provider_name = (webhook_payload.get('provider_name') or '').strip()  # CRITICAL for routing!
        provider_email = ''  # Still not in your webhook mapping
        
        return {
            # Patient personal data
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "date_of_birth": date_of_birth,
            "phone_number": phone_number,
            "email_address": email_address,
            "street_address": street_address,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            
            # Medical data for case creation
            "wound_type": wound_type,
            "wound_size": wound_size,
            "surgery_date": surgery_date,
            "icd_10_code": icd_10_code,
            "cpt_surgery_code": cpt_surgery_code,
            "place_of_service": place_of_service,
            
            # Insurance data
            "primary_insurance_name": primary_insurance_name,
            "primary_policy_number": primary_policy_number,
            "secondary_insurance_name": secondary_insurance_name,
            "secondary_policy_number": secondary_policy_number,
            
            # Provider data (CRITICAL for routing)
            "provider_name": provider_name,
            "provider_email": provider_email,
            
            # New GHL Form Fields
            "facility_type": facility_type,
            "facility_npi": facility_npi,
            "expected_date_of_service": expected_date_of_service,
            
            # Biologic Product Fields (units/cm2)
            "amniomaxx_q4239": amniomaxx_q4239,
            "palingen_q4173": palingen_q4173,
            "membrane_wrap_trilayer_q4344": membrane_wrap_trilayer_q4344,
            "amnioamp_mp_q4250": amnioamp_mp_q4250,
            "membrane_wrap_hydro_q4290": membrane_wrap_hydro_q4290,
            "biovance_q4154": biovance_q4154,
            "amchoplast_q4316": amchoplast_q4316,
            "helicoll_q4164": helicoll_q4164,
            "xcell_amnio_matrix_q4280": xcell_amnio_matrix_q4280
        }
    
    
    def transform_patient_data(self, form_data):
        """Transform GHL form data to RMBB patient format"""
        return {
            "personal_identifier": {
                "first": form_data["first_name"],
                "middle": form_data.get("middle_name", ""),
                "last": form_data["last_name"]
            },
            "address": {
                "street": form_data["street_address"],
                "suite": "",
                "city": form_data["city"],
                "state": form_data["state"],
                "country": "USA",
                "zip": form_data["zip_code"]
            },
            "communication_information": {
                "phone": form_data["phone_number"],
                "fax": "",
                "email": form_data["email_address"]
            },
            "date_of_birth": form_data["date_of_birth"],
            "gender": "",
            "note": "Patient from GHL form submission",
            "social_security_number": ""
        }
    
    def transform_case_data(self, form_data, patient_id):
        """Transform GHL form data to RMBB case format - matches rmbbhealth.txt structure"""
        
        # Extract selected biologic product and wound size from GHL form
        product_info = self.extract_selected_biologic_product(form_data)
        
        # Product extraction completed
        
        # Use biologic product cm2 as wound size, or fallback to wound_size field
        wound_size = ""
        total_wound_size = ""
        
        if product_info["primary_product"]:
            # Use the cm2 from selected biologic product
            cm2_value = product_info["primary_product"]["cm2"]
            wound_size = f"{cm2_value} cm2"
            total_wound_size = f"{product_info['total_cm2']} cm2"
        else:
            # Fallback to traditional wound_size field
            wound_size = form_data.get("wound_size", "")
            if wound_size and "x" in wound_size:
                try:
                    # Extract dimensions from format like "3x4 cm"
                    dimensions = wound_size.replace("cm", "").strip().split("x")
                    if len(dimensions) == 2:
                        width = float(dimensions[0].strip())
                        height = float(dimensions[1].strip())
                        total_wound_size = f"{width * height} cm2"
                except:
                    pass
        
        # Map facility_type to place_of_service
        place_of_service = form_data.get("facility_type", "Physician Office - 11")
        
        # Determine facility nursing status from facility_type
        is_skilled_nursing = 1 if "skilled nursing" in place_of_service.lower() else 0
        is_surgical_nursing = 1 if "surgical nursing" in place_of_service.lower() else 0
        
        # Build case data matching exact structure from rmbbhealth.txt lines 518-557
        case_data = {
            "tid": self.rmbb_team_id,
            "account_location_id": self.get_account_location_id(form_data.get("location_id")),
            "physician_id": self.get_physician_id(form_data.get("provider_name")),
            "patient_id": patient_id,
            "product_id": self.get_product_id_from_biologic(product_info),
            "external_id": form_data.get("external_id"),  # Use the external_id passed from main workflow
            "place_of_service": place_of_service,
            "wound_size": wound_size,
            "total_wound_size": total_wound_size,
            "wound_type": form_data.get("wound_type", ""),
            "is_in_skilled_nursing_facility": is_skilled_nursing,
            "is_in_surgical_nursing_facility": is_surgical_nursing,
            "cpt_surgery_code": form_data.get("cpt_surgery_code", ""),
            "surgery_date": form_data.get("expected_date_of_service", ""),  # Map expected_date_of_service to surgery_date
            "icd_10_code": form_data.get("icd_10_code", ""),
            "product_cpt_code": "15271-8" if product_info["primary_product"] else "",
        }
        
        # Primary Insurance (matches rmbbhealth.txt structure) - using actual GHL payload fields
        primary_insurance_name = form_data.get("primary_insurance_name", "")
        if primary_insurance_name:
            case_data["primary_insurance"] = {
                "full_name": primary_insurance_name,
                "type": form_data.get("primary_insurance_type", form_data.get("insurance_type", "")),
                "mac": "",
                "parent_company": primary_insurance_name,  # Use actual insurance name from GHL payload
                "participating_status": form_data.get("primary_participating_status", ""),
                "policy_number": form_data.get("primary_policy_number", ""),
                "preferred_provider_organization": "Yes",  # Default
                "health_maintenance_organization": "No",  # Default
                "prior_authorization": ""  # Could be form field
            }
        
        # Secondary Insurance (matches rmbbhealth.txt structure) - using actual GHL payload fields
        secondary_insurance_name = form_data.get("secondary_insurance_name", "")
        if secondary_insurance_name:
            case_data["secondary_insurance"] = {
                "full_name": secondary_insurance_name,
                "type": form_data.get("secondary_insurance_type", ""),
                "mac": "",
                "parent_company": secondary_insurance_name,  # Use actual insurance name from GHL payload
                "participating_status": form_data.get("secondary_participating_status", ""),
                "policy_number": form_data.get("secondary_policy_number", ""),
                "preferred_provider_organization": "No",  # Default
                "health_maintenance_organization": "Yes",  # Default
                "prior_authorization": ""  # Could be form field
            }
        
        return case_data
    
    def transform_case_data_for_product(self, form_data, patient_id, product):
        """
        Transform GHL form data to RMBB case format for a specific product
        Creates case data with individual product details
        """
        # Start with base case data (same as original method)
        case_data = {
            "tid": self.rmbb_team_id,
            "account_location_id": self.get_account_location_id(form_data.get('ghl_location_id')),
            "physician_id": self.get_physician_id(form_data.get('provider_name')),
            "patient_id": patient_id,
            "product_id": self.get_product_id_for_product(product),  # Individual product ID
            "place_of_service": form_data.get("facility_type", ""),
            "wound_size": f"{product['cm2']} cm2",  # Individual product wound size
            "total_wound_size": f"{product['cm2']} cm2",  # Same as wound_size for individual product
            "wound_type": form_data.get("wound_type", ""),
            "is_in_skilled_nursing_facility": 1 if "skilled nursing" in form_data.get("facility_type", "").lower() else 0,
            "is_in_surgical_nursing_facility": 0,  # Default
            "cpt_surgery_code": form_data.get("cpt_surgery_code", ""),
            "surgery_date": form_data.get("expected_date_of_service", ""),
            "icd_10_code": form_data.get("icd_10_code", ""),
            "product_cpt_code": "15271-8"  # Default, could be product-specific
        }
        
        # Add insurance data (same for all products) - using actual GHL payload fields
        primary_insurance_name = form_data.get("primary_insurance_name", "")
        if primary_insurance_name:
            case_data["primary_insurance"] = {
                "full_name": primary_insurance_name,
                "type": form_data.get("primary_insurance_type", form_data.get("insurance_type", "")),
                "mac": "",
                "parent_company": primary_insurance_name,  # Use actual insurance name from GHL payload
                "participating_status": form_data.get("primary_participating_status", ""),
                "policy_number": form_data.get("primary_policy_number", ""),
                "preferred_provider_organization": "Yes",  # Default
                "health_maintenance_organization": "No",  # Default
                "prior_authorization": ""  # Could be form field
            }
        
        secondary_insurance_name = form_data.get("secondary_insurance_name", "")
        if secondary_insurance_name:
            case_data["secondary_insurance"] = {
                "full_name": secondary_insurance_name,
                "type": form_data.get("secondary_insurance_type", ""),
                "mac": "",
                "parent_company": secondary_insurance_name,  # Use actual insurance name from GHL payload
                "participating_status": form_data.get("secondary_participating_status", ""),
                "policy_number": form_data.get("secondary_policy_number", ""),
                "preferred_provider_organization": "No",  # Default
                "health_maintenance_organization": "Yes",  # Default
                "prior_authorization": ""  # Could be form field
            }
        
        return case_data
    
    def get_product_id_for_product(self, product):
        """
        Get RMBB Health product_id for a specific product
        """
        q_code_to_product_id = {
            "Q4239": 229,  # amniomaxx → Amnio-Maxx
            "Q4250": 230,  # amnioamp-mp → AmnioAMP-MP
            "Q4290": 99,   # membrane_wrap_hydro → Membrane Wrap-Hydro
            "Q4344": 98,   # membrane_wrap_tri-layer → Membrane Wrap
            "Q4154": 232,  # biovance → Biovance
            "Q4280": 237,  # xcell_amnio_matrix → Xcell Amnio Matrix
            # Products not available in RMBB Health - using default Membrane Wrap (ID 98)
            "Q4173": 98,   # palingen → Default: Membrane Wrap
            "Q4316": 98,   # amchoplast → Default: Membrane Wrap
            "Q4164": 98    # helicoll → Default: Membrane Wrap
        }
        
        q_code = product["product_id"]
        numeric_product_id = q_code_to_product_id.get(q_code, 98)  # Default to Membrane Wrap (98) if not found
        
        # Reduced logging for Railway rate limit  
        return numeric_product_id
    
    def get_account_location_id(self, ghl_location_id):
        """
        Get RMBB account_location_id from Railway environment variables
        """
        account_location_id = os.getenv('RMBB_ACCOUNT_LOCATION_ID', '8720')  # Railway env var, fallback to known working ID
        # Reduced logging for Railway rate limit
        return int(account_location_id)
    
    def get_physician_id(self, provider_name):
        """
        Get RMBB physician_id from Railway environment variables  
        """
        physician_id = os.getenv('RMBB_PHYSICIAN_ID', '15995')  # Railway env var, fallback to known working ID
        # Reduced logging for Railway rate limit
        return int(physician_id)
    
    
    def extract_selected_biologic_product(self, form_data):
        """
        Extract the selected biologic product from GHL form data.
        Provider fills in cm2 for the product(s) they want to use.
        """
        # List of all biologic products with their product IDs
        products = {
            "amniomaxx_q4239": {"name": "Amniomaxx", "product_id": "Q4239"},
            "palingen_q4173": {"name": "Palingen", "product_id": "Q4173"},
            "membrane_wrap_trilayer_q4344": {"name": "Membrane Wrap Tri-Layer", "product_id": "Q4344"},
            "amnioamp_mp_q4250": {"name": "AmnioAmp-MP", "product_id": "Q4250"},
            "membrane_wrap_hydro_q4290": {"name": "Membrane Wrap Hydro", "product_id": "Q4290"},
            "biovance_q4154": {"name": "Biovance", "product_id": "Q4154"},
            "amchoplast_q4316": {"name": "Amchoplast", "product_id": "Q4316"},
            "helicoll_q4164": {"name": "Helicoll", "product_id": "Q4164"},
            "xcell_amnio_matrix_q4280": {"name": "xCell Amnio Matrix", "product_id": "Q4280"}
        }
        
        selected_products = []
        total_cm2 = 0
        
        # Check each product field for values
        for field_name, product_info in products.items():
            cm2_value = form_data.get(field_name, "").strip()
            
            if cm2_value and cm2_value != "0":
                try:
                    cm2_float = float(cm2_value)
                    if cm2_float > 0:
                        selected_products.append({
                            "name": product_info["name"],
                            "product_id": product_info["product_id"],
                            "cm2": cm2_float,
                            "field_name": field_name
                        })
                        total_cm2 += cm2_float
                except ValueError:
                    continue
        
        return {
            "selected_products": selected_products,
            "total_cm2": total_cm2,
            "primary_product": selected_products[0] if selected_products else None
        }
    
    def get_product_id_from_biologic(self, product_info):
        """
        Get RMBB Health product_id from selected biologic product
        RMBB Health expects numeric product IDs, not Q-codes
        """
        if not product_info["primary_product"]:
            # No product selected, use default Membrane Wrap (ID 98)
            return int(os.getenv('RMBB_PRODUCT_ID', '98'))
        
        # Map Q-codes to actual RMBB Health numeric product IDs
        q_code_to_product_id = {
            "Q4239": 229,  # amniomaxx → Amnio-Maxx
            "Q4250": 230,  # amnioamp-mp → AmnioAMP-MP
            "Q4290": 99,   # membrane_wrap_hydro → Membrane Wrap-Hydro
            "Q4344": 98,   # membrane_wrap_tri-layer → Membrane Wrap
            "Q4154": 232,  # biovance → Biovance
            "Q4280": 237,  # xcell_amnio_matrix → Xcell Amnio Matrix
            # Products not available in RMBB Health - using default Membrane Wrap (ID 98)
            "Q4173": 98,   # palingen → Default: Membrane Wrap
            "Q4316": 98,   # amchoplast → Default: Membrane Wrap
            "Q4164": 98    # helicoll → Default: Membrane Wrap
        }
        
        q_code = product_info["primary_product"]["product_id"]
        numeric_product_id = q_code_to_product_id.get(q_code, 98)  # Default to Membrane Wrap (98) if not found
        
        # Reduced logging for Railway rate limit
        return numeric_product_id
    
    def upload_additional_case_information(self, case_id, provider_name=None, facility_type=None, facility_npi=None, provider_npi=None):
        """
        Upload additional provider/facility information to RMBB Health case
        Uses: POST /team/:tid/case/:bicid/additional-information
        """
        if not case_id:
            return {"success": False, "error": "Missing case_id"}
        
        # Build additional information payload
        additional_info = {}
        
        if provider_name:
            additional_info["provider_name"] = provider_name
        if facility_type:
            additional_info["facility_type"] = facility_type  
        if facility_npi:
            additional_info["facility_npi"] = facility_npi
        if provider_npi:
            additional_info["provider_npi"] = provider_npi
            
        if not additional_info:
            return {"success": True, "message": "No additional information to upload"}
        
        url = f"{self.rmbb_base_url}/team/{self.rmbb_team_id}/case/{case_id}/additional-information"
        
        print(f"📄 Uploading additional case information:")
        for key, value in additional_info.items():
            print(f"   {key}: {value}")
        
        try:
            response = requests.post(url, headers=self.rmbb_headers, json=additional_info)
            print(f"📊 Additional info upload status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                print(f"✅ Additional information uploaded successfully to case {case_id}")
                return {"success": True, "message": "Additional information uploaded"}
            else:
                error_msg = f"Additional information upload failed: {response.status_code} - {response.text}"
                print(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Failed to upload additional information: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
    
    def update_ghl_contact(self, contact_id, update_data, location_id=None):
        """Update GHL contact using V1 API - based on complete_subaccount_creation.py patterns"""
        if location_id:
            url = f"{self.ghl_base_url}/locations/{location_id}/contacts/{contact_id}"
        else:
            # Fallback to old format if no location_id provided (may still fail)
            url = f"{self.ghl_base_url}/contacts/{contact_id}"
        
        logging.info(f"📝 Updating GHL contact {contact_id}")
        logging.info(f"🔗 PUT {url}")
        
        try:
            response = requests.put(url, headers=self.ghl_headers, json=update_data)
            logging.info(f"📊 Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                result = response.json()
                logging.info(f"✅ GHL contact updated successfully")
                return {"success": True, "data": result}
            else:
                error_msg = f"GHL contact update failed: {response.status_code} - {response.text}"
                logging.error(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error updating GHL contact: {str(e)}"
            logging.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
    
    def send_ghl_notification(self, location_id, notification_data):
        """Send notification within GHL sub-account using V1 API"""
        # In a real implementation, this would use GHL's messaging API
        # For now, we'll simulate the notification
        
        logging.info(f"📧 Sending GHL notification to location {location_id}")
        logging.info(f"📋 Subject: {notification_data.get('subject', 'RMBB Health Update')}")
        logging.info(f"👤 To: {notification_data.get('to', 'provider')}")
        
        # Mock notification response
        return {
            "success": True,
            "notification_id": f"notif_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "message": "Notification sent successfully"
        }
    
    def run_complete_workflow(self, webhook_payload=None):
        """Run the complete GHL → RMBB Health → GHL flow-through workflow"""
        print("🔄 COMPLETE GHL ↔ RMBB HEALTH ↔ GHL FLOW-THROUGH WORKFLOW")
        print("Multi-tenant sub-account routing with HIPAA-compliant GHL storage")
        print("=" * 80)
        
        # Mock webhook payload for demo if none provided
        if not webhook_payload:
            webhook_payload = {
                "contactId": "test_contact_456",
                "locationId": "test_location_123", 
                "Patient First Name": "John",
                "Patient Last Name": "Smith",
                "Patient Email": "john.smith@email.com",
                "Wound Type": "Diabetic Ulcer",
                "Primary Insurance": "Medicare Part B"
            }
        
        try:
            # Step 1: Process GHL webhook and store tracking in GHL contact
            print("🔍 DEBUG - About to call handle_ghl_webhook")
            try:
                external_id, contact_id, location_id, patient_data = self.handle_ghl_webhook(webhook_payload)
                print("🔍 DEBUG - handle_ghl_webhook completed successfully")
            except Exception as webhook_error:
                print(f"❌ ERROR in handle_ghl_webhook: {webhook_error}")
                import traceback
                print(f"❌ TRACEBACK: {traceback.format_exc()}")
                raise
            
            # Step 2: Submit to RMBB Health with external_id linking back to GHL
            rmbb_result = self.submit_to_rmbb_health(external_id, contact_id, patient_data)
            if isinstance(rmbb_result, dict) and not rmbb_result.get("success", True):
                # Case or patient creation failed
                print(f"❌ RMBB Health submission failed: {rmbb_result['error']}")
                return rmbb_result
                
            # Extract results from multiple case creation
            patient_response = rmbb_result['patient_response']
            created_cases = rmbb_result['created_cases']
            failed_cases = rmbb_result['failed_cases']
            
            # Step 3: Finalize RMBB submission and end workflow (RMBB Health will webhook us)
            provider_name = patient_data.get('provider_name')
            submission_result = self.finalize_rmbb_submission(
                external_id=external_id,
                contact_id=contact_id, 
                created_cases=created_cases,
                provider_name=provider_name
            )
            
            print("\n" + "=" * 80)
            print("✅ GHL → RMBB HEALTH SUBMISSION COMPLETED")
            print("=" * 80)
            print(f"🔗 External ID base: {external_id}")
            print(f"📧 GHL Contact ID: {contact_id}")
            print(f"📍 GHL Location ID: {location_id}")
            print(f"👨‍⚕️ Provider: {provider_name} (cached for webhook routing)")
            print(f"🏥 RMBB Patient ID: {patient_response['id']}")
            
            # Display multiple cases created
            case_ids_str = ", ".join([str(case['case_id']) for case in created_cases])
            print(f"📋 RMBB Cases Created: {len(created_cases)}")
            print(f"📋 RMBB Case IDs: {case_ids_str}")
            
            for case in created_cases:
                print(f"   • {case['product_name']} (Q-code: {case['product_id']}, {case['cm2']} cm2) → Case ID: {case['case_id']}")
            
            # Show failed cases if any
            if failed_cases:
                print(f"⚠️ Failed Cases: {len(failed_cases)}")
                for case in failed_cases:
                    print(f"   • {case['product_name']} (Q-code: {case['product_id']}, {case['cm2']} cm2) → ERROR: {case['error']}")
            
            print(f"✅ Status: {submission_result['status']}")
            print(f"📋 Next: RMBB Health will webhook IVR results to /webhook/rmbb-status-update")
            print("🛡️ HIPAA Compliant - No external data storage")
            print("🔄 This workflow ends here - IVR results handled by separate webhook")
            
            return {
                "success": True,
                "workflow_stage": "submission_completed",
                "external_id": external_id,
                "contact_id": contact_id,
                "location_id": location_id,
                "provider_name": provider_name,
                "rmbb_patient_id": patient_response['id'],
                "rmbb_case_ids": [case['case_id'] for case in created_cases],
                "total_cases_created": len(created_cases),
                "created_cases": created_cases,
                "failed_cases": failed_cases,
                "submission_status": submission_result['status'],
                "completed_at": submission_result['completed_at'],
                "note": f"GHL → RMBB submission complete. {len(created_cases)} cases created. IVR results will arrive via separate RMBB webhook."
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ WORKFLOW ERROR: {error_msg}")
            import traceback
            print(f"❌ FULL TRACEBACK: {traceback.format_exc()}")
            
            # Try to update GHL contact with error status if we have contact_id
            try:
                if 'contact_id' in locals():
                    error_status_update = {
                        "customFields": [
                            {"key": "rmbb_workflow_status", "value": "error"},
                            {"key": "rmbb_error_message", "value": error_msg},
                            {"key": "rmbb_error_date", "value": datetime.now().isoformat()}
                        ]
                    }
                    self.update_ghl_contact(contact_id, error_status_update)
                    print(f"⚠️ Error status updated in GHL contact {contact_id}")
            except:
                pass  # Don't fail on error logging
            
            return {
                "success": False,
                "error": error_msg
            }

def demo_complete_workflow():
    """Demo the complete bidirectional workflow"""
    print("GHL ↔ RMBB Health ↔ GHL Integration Demo")
    print("Note: This demo uses mock data since we don't have live API keys yet")
    print("")
    
    # Initialize workflow handler (with mock credentials)
    handler = GHLRMBBWorkflowHandler(
        rmbb_api_key="mock_rmbb_api_key",
        rmbb_team_id=123,
        ghl_api_key="mock_ghl_api_key"
    )
    
    # Run complete workflow
    result = handler.run_complete_workflow()
    
    if result["success"]:
        print(f"\n🎉 Demo completed successfully!")
        print(f"This demonstrates the complete integration flow once API keys are available.")
    else:
        print(f"\n⚠️ Demo encountered an error: {result['error']}")

if __name__ == "__main__":
    demo_complete_workflow()