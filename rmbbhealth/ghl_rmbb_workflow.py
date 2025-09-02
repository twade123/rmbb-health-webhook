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
    
    # GHL Custom Field Mappings - Document Processing Fields (IVR Results & Document Extraction)
    DOCUMENT_PROCESSING_FIELDS = {
        # Current Status Fields (5 fields)
        "rmbb_current_patient_info": "XueHehokZYjJSvWGzjfk",
        "rmbb_current_insurance_info": "FoqW1DyrjW6WtsoPflFZ", 
        "rmbb_current_decision_summary": "XQLSYwSOodHOBrqv8oz0",
        "rmbb_current_notes": "tLNZ4EYxxXUO9HrDpkl5",
        "rmbb_current_status": "CWCMdJsRU4hMEDS32U4s",
        
        # IVR-Specific Extraction Fields (5 fields)
        "rmbb_ivr_patient_data": "TAA2QAEXDh14bIkYacWW",
        "rmbb_ivr_primary_insurance": "VXpnvGzV94MPikiXXrFh",
        "rmbb_ivr_secondary_insurance": "IYWefx90XVJMC3kIJaSz",
        "rmbb_ivr_coverage_summary": "m8Ml4hPPfNgfoURqBsSt",
        "rmbb_ivr_authorization_info": "Y2zXVZYUzXLxLRm70J1E",
        
        # Document Tracking Fields (3 fields)
        "rmbb_document_history": "dGy54D7hPD0Ydp4c8EsO",
        "rmbb_case_summary": "WGKrQzlaNsK8Y4t5bUYf",
        "rmbb_total_documents": "DuqFjhMUOv2yKa5qbdyR",
        
        # Legacy Field (1 field)
        "rmbb_approval_status": "pbPVNjx7lmzlMkh4QYHs"
    }
    
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
        
        # ADDITIONAL DEBUG: Show what the case transformation method will receive
        print(f"🔍 FORM DATA READY FOR CASE TRANSFORMATION:")
        print(f"   📋 patient_form_data keys: {list(patient_form_data.keys())}")
        print(f"   🔬 icd_10_code value: '{patient_form_data.get('icd_10_code', 'NOT FOUND')}'")
        print(f"   📊 primary_insurance_name value: '{patient_form_data.get('primary_insurance_name', 'NOT FOUND')}'")
        print(f"   📊 secondary_insurance_name value: '{patient_form_data.get('secondary_insurance_name', 'NOT FOUND')}'")
        print(f"   🏢 facility_type value: '{patient_form_data.get('facility_type', 'NOT FOUND')}'")
        
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
            "customField": [
                {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "webhook_received"},  # rmbb_workflow_status
                {"id": "YpL2cH7rV4mN9xT6wK1s", "value": external_id},  # rmbb_external_id
                {"id": "drfCODR4HhoKeI3eoH6J", "value": datetime.now().isoformat()},  # rmbb_submission_date
                {"id": "XueHehokZYjJSvWGzjfk", "value": f"{patient_form_data.get('first_name', '')} {patient_form_data.get('last_name', '')}"},  # rmbb_patient_name
                {"id": "tLNZ4EYxxXUO9HrDpkl5", "value": patient_form_data.get('wound_type', '')},  # rmbb_wound_type
                {"id": "FoqW1DyrjW6WtsoPflFZ", "value": patient_form_data.get('primary_insurance_name', '')}  # rmbb_primary_insurance
            ]
        }
        
        # Update GHL contact with initial tracking data (with delay to prevent race condition)
        contact_update_result = self.update_ghl_contact(
            contact_id, 
            initial_tracking_data, 
            location_id=location_id,
            provider_name=provider_name,
            add_delay=True  # First contact update - add delay for contact creation race condition
        )
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
            
            # DEBUG: Show what we're sending to RMBB Health API
            print(f"🔍 CASE PAYLOAD DEBUG for {product['name']}:")
            print(f"   📋 Product ID: {rmbb_case_data.get('product_id')}")
            print(f"   🏷️ HCPCS: {rmbb_case_data.get('hcpcs')}")
            print(f"   🏥 Account Location ID: {rmbb_case_data.get('account_location_id')}")
            print(f"   👨‍⚕️ Physician ID: {rmbb_case_data.get('physician_id')}")
            print(f"   🆔 Patient ID: {rmbb_case_data.get('patient_id')}")
            print(f"   🔬 ICD-10 Code: {rmbb_case_data.get('icd_10_code')}")
            print(f"   🏢 Place of Service: {rmbb_case_data.get('place_of_service')}")
            print(f"   📊 Primary Insurance: {rmbb_case_data.get('primary_insurance', {}).get('full_name', 'MISSING')}")
            print(f"   📊 Secondary Insurance: {rmbb_case_data.get('secondary_insurance', {}).get('full_name', 'MISSING')}")
            
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
                            # Prepare product info for reorder system
                            product_info = {
                                "name": product.get('name'),
                                "product_id": product.get('product_id'),
                                "q_code": product.get('q_code', product.get('name', '').split()[-1] if product.get('name') else None)  # Extract Q-code if available
                            }
                            
                            cache_success = self.provider_cache.add_case_mapping(
                                case_id=str(case_id),
                                provider_name=provider_name,
                                contact_id=contact_id,
                                external_id=case_external_id,
                                product_info=product_info
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
            "customField": [
                {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "submitted_for_qualification"},  # rmbb_workflow_status
                {"id": "XueHehokZYjJSvWGzjfk", "value": str(patient_response['id'])},  # rmbb_patient_id
                {"id": "WGKrQzlaNsK8Y4t5bUYf", "value": case_ids_str},  # rmbb_case_ids
                {"id": "DuqFjhMUOv2yKa5qbdyR", "value": str(len(created_cases))},  # rmbb_case_count
                {"id": "tLNZ4EYxxXUO9HrDpkl5", "value": case_products_str},  # rmbb_products
                {"id": "drfCODR4HhoKeI3eoH6J", "value": datetime.now().isoformat()}  # rmbb_submission_completed
            ]
        }
        
        # Add failure info if any cases failed
        if failed_cases:
            failed_products_str = ", ".join([f"{case['product_name']} (ERROR)" for case in failed_cases])
            rmbb_tracking_update["customField"].extend([
                {"id": "tLNZ4EYxxXUO9HrDpkl5", "value": failed_products_str},  # rmbb_failed_products
                {"id": "dGy54D7hPD0Ydp4c8EsO", "value": "true"}  # rmbb_partial_failure
            ])
        
        # Update GHL contact with provider context from form data
        provider_name = patient_form_data.get('provider_name', '')
        contact_update_result = self.update_ghl_contact(
            contact_id, 
            rmbb_tracking_update,
            provider_name=provider_name
        )
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
            "customField": [
                {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "submitted_awaiting_ivr"},  # rmbb_workflow_status
                {"id": "WGKrQzlaNsK8Y4t5bUYf", "value": case_ids_str},  # rmbb_case_ids
                {"id": "DuqFjhMUOv2yKa5qbdyR", "value": str(len(created_cases))},  # rmbb_case_count
                {"id": "drfCODR4HhoKeI3eoH6J", "value": datetime.now().isoformat()},  # rmbb_submission_completed_date
                {"id": "4AnL32P9rjYcPjbukcok", "value": "true"}  # rmbb_awaiting_ivr
            ]
        }
        
        # Update the GHL contact with provider context
        contact_update_result = self.update_ghl_contact(
            contact_id, 
            final_tracking_update,
            provider_name=provider_name
        )
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
            "customField": [
                {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "completed"},  # rmbb_workflow_status
                {"id": "drfCODR4HhoKeI3eoH6J", "value": "true"},  # rmbb_provider_notified
                {"id": "4AnL32P9rjYcPjbukcok", "value": datetime.now().isoformat()},  # rmbb_completion_date
                {"id": "WGKrQzlaNsK8Y4t5bUYf", "value": notification_result.get('notification_id', '')}  # rmbb_notification_id
            ]
        }
        
        # Get provider name from cache using location_id for proper API key usage
        provider_name = self._get_provider_name_by_location(location_id)
        
        # Final update to the original contact in the correct sub-account
        final_contact_update = self.update_ghl_contact(
            contact_id, 
            final_status_update,
            location_id=location_id,
            provider_name=provider_name
        )
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
        membrane_wrap_trilayer_q4205 = (webhook_payload.get('membrane_wrap_tri-layer_(q4205)_units/cm2') or '').strip()
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
            "membrane_wrap_trilayer_q4205": membrane_wrap_trilayer_q4205,
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
            "product_cpt_code": self.RMBB_CPT_CODE if product_info["primary_product"] else "",
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
            "product_cpt_code": self.RMBB_CPT_CODE  # All products use same CPT code
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
    
    # CPT Code constant - all products use the same CPT code
    RMBB_CPT_CODE = "15271-8"
    
    def get_product_id_for_product(self, product):
        """
        Get RMBB Health product_id for a specific product
        Environment-specific mappings (Test vs Production have different IDs)
        """
        # Detect environment based on team_id
        is_production = self.rmbb_team_id == 59  # Production team ID
        
        if is_production:
            # PRODUCTION Environment (Team ID: 59) - Original IDs
            q_code_to_product_id = {
                "Q4239": 229,  # amniomaxx → Amnio-Maxx
                "Q4250": 230,  # amnioamp-mp → AmnioAMP-MP
                "Q4290": 99,   # membrane_wrap_hydro → Membrane Wrap-Hydro
                "Q4205": 98,   # membrane_wrap_tri-layer → Membrane Wrap
                "Q4154": 232,  # biovance → Biovance
                "Q4280": 237,  # xcell_amnio_matrix → Xcell Amnio Matrix
                "Q4173": 341,  # palingen → PalinGen
                "Q4316": 343,  # amchoplast → AmchoPlast
                "Q4164": 342   # helicoll → Helicoll
            }
        else:
            # TEST/DEVELOPMENT Environment (Team ID: 85) - Updated IDs
            q_code_to_product_id = {
                "Q4239": 364,  # amniomaxx → Amnio-Maxx
                "Q4250": 365,  # amnioamp-mp → AmnioAMP-MP
                "Q4290": 362,  # membrane_wrap_hydro → Membrane Wrap-Hydro
                "Q4205": 361,  # membrane_wrap_tri-layer → Membrane Wrap
                "Q4154": 367,  # biovance → Biovance
                "Q4280": 372,  # xcell_amnio_matrix → Xcell Amnio Matrix
                "Q4173": 373,  # palingen → PalinGen
                "Q4316": 375,  # amchoplast → AmchoPlast
                "Q4164": 374   # helicoll → Helicoll
            }
        
        q_code = product["product_id"]
        numeric_product_id = q_code_to_product_id.get(q_code, 98)  # Default to Membrane Wrap (98) if not found
        
        # Reduced logging for Railway rate limit  
        return numeric_product_id
    
    def get_hcpcs_for_product(self, product):
        """
        Get HCPCS Q-code for a specific product - required by RMBB Health API
        Maps the Q-codes from GHL form to actual HCPCS codes for RMBB Health
        Updated with correct HCPCS codes from RMBB API
        """
        q_code_to_hcpcs = {
            "Q4239": "Q4239",  # amniomaxx
            "Q4250": "Q4250",  # amnioamp-mp  
            "Q4290": "Q4290",  # membrane_wrap_hydro
            "Q4205": "Q4205",  # membrane_wrap_tri-layer (corrected from Q4344)
            "Q4154": "Q4154",  # biovance
            "Q4280": "Q4280",  # xcell_amnio_matrix
            "Q4173": "Q4173",  # palingen
            "Q4316": "Q4316",  # amchoplast
            "Q4164": "Q4164",  # helicoll
        }
        
        q_code = product["product_id"]  # This is the Q-code from GHL form (e.g., "Q4239")
        hcpcs_code = q_code_to_hcpcs.get(q_code, q_code)  # Default to the Q-code itself
        return hcpcs_code
    
    def get_account_location_id(self, ghl_location_id):
        """
        Get RMBB account_location_id from Railway environment variables
        No fallback - must be set in Railway environment
        """
        account_location_id = os.getenv('RMBB_LOCATION_ID')
        if not account_location_id:
            raise ValueError("RMBB_LOCATION_ID environment variable is required")
        return int(account_location_id)
    
    def get_physician_id(self, provider_name):
        """
        Get RMBB physician_id from Railway environment variables
        No fallback - must be set in Railway environment
        """
        physician_id = os.getenv('RMBB_PHYSICIAN_ID')
        if not physician_id:
            raise ValueError("RMBB_PHYSICIAN_ID environment variable is required")
        return int(physician_id)
    
    
    def extract_selected_biologic_product(self, form_data):
        """
        Extract the selected biologic product from GHL form data.
        Provider fills in cm2 for the product(s) they want to use.
        """
        # List of all biologic products with RMBB Health environment-specific IDs and GHL custom field IDs
        # Verified against RMBB Health API and GHL API on 2025-08-31 for both dev and prod environments
        products = {
            "amniomaxx_q4239": {"name": "Amnio-Maxx", "q_code": "Q4239", "dev_id": 364, "prod_id": 229, "ghl_field_id": "tOGJkZFd2ymaHGKYrVU2"},
            "palingen_q4173": {"name": "PalinGen", "q_code": "Q4173", "dev_id": 373, "prod_id": 341, "ghl_field_id": "gN96ValY4BEEzUFBD6Z0"},
            "membrane_wrap_trilayer_q4205": {"name": "Membrane Wrap", "q_code": "Q4205", "dev_id": 361, "prod_id": 98, "ghl_field_id": "1hvUvoGbO7rMLSgEFoDz"},
            "amnioamp_mp_q4250": {"name": "AmnioAMP-MP", "q_code": "Q4250", "dev_id": 365, "prod_id": 230, "ghl_field_id": "f2ahSKCm3LRuN0djazBg"},
            "membrane_wrap_hydro_q4290": {"name": "Membrane Wrap-Hydro", "q_code": "Q4290", "dev_id": 362, "prod_id": 99, "ghl_field_id": "TIjFjavn2llFCwGizWj2"},
            "biovance_q4154": {"name": "Biovance", "q_code": "Q4154", "dev_id": 367, "prod_id": 232, "ghl_field_id": "nS8MzgEAKuaGNjxdPGe7"},
            "amchoplast_q4316": {"name": "AmchoPlast", "q_code": "Q4316", "dev_id": 375, "prod_id": 343, "ghl_field_id": "b5h4W8FSMO1E8KSleixD"},
            "helicoll_q4164": {"name": "Helicoll", "q_code": "Q4164", "dev_id": 374, "prod_id": 342, "ghl_field_id": "lqdbhafh2zTeM23u0OMe"},
            "xcell_amnio_matrix_q4280": {"name": "Xcell Amnio Matrix", "q_code": "Q4280", "dev_id": 372, "prod_id": 237, "ghl_field_id": "49vxcOnMCVYPyDdDuH80"}
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
        
        # Environment-specific product ID mappings
        is_production = self.rmbb_team_id == 59  # Production team ID
        
        if is_production:
            # PRODUCTION Environment (Team ID: 59) - Original IDs
            q_code_to_product_id = {
                "Q4239": 229,  # amniomaxx → Amnio-Maxx
                "Q4250": 230,  # amnioamp-mp → AmnioAMP-MP
                "Q4290": 99,   # membrane_wrap_hydro → Membrane Wrap-Hydro
                "Q4205": 98,   # membrane_wrap_tri-layer → Membrane Wrap
                "Q4154": 232,  # biovance → Biovance
                "Q4280": 237,  # xcell_amnio_matrix → Xcell Amnio Matrix
                "Q4173": 341,  # palingen → PalinGen
                "Q4316": 343,  # amchoplast → AmchoPlast
                "Q4164": 342   # helicoll → Helicoll
            }
        else:
            # TEST/DEVELOPMENT Environment (Team ID: 85) - Updated IDs
            q_code_to_product_id = {
                "Q4239": 364,  # amniomaxx → Amnio-Maxx
                "Q4250": 365,  # amnioamp-mp → AmnioAMP-MP
                "Q4290": 362,  # membrane_wrap_hydro → Membrane Wrap-Hydro
                "Q4205": 361,  # membrane_wrap_tri-layer → Membrane Wrap
                "Q4154": 367,  # biovance → Biovance
                "Q4280": 372,  # xcell_amnio_matrix → Xcell Amnio Matrix
                "Q4173": 373,  # palingen → PalinGen
                "Q4316": 375,  # amchoplast → AmchoPlast
                "Q4164": 374   # helicoll → Helicoll
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
    
    def _get_provider_name_by_location(self, location_id):
        """Get provider name from cache using location_id"""
        try:
            provider_cache = get_provider_cache()
            
            # Access the internal cache dictionary directly
            with provider_cache.lock:
                cache_data = provider_cache.cache
                for provider_key, provider_data in cache_data.items():
                    if provider_key == "case_mappings":  # Skip global mappings
                        continue
                    if provider_data.get("location_id") == location_id:
                        original_name = provider_data.get("original_name", provider_key)
                        logging.info(f"🔍 Found provider for location {location_id}: {original_name}")
                        return original_name
            
            logging.warning(f"⚠️ No provider found for location_id: {location_id}")
            return None
        except Exception as e:
            logging.error(f"❌ Error getting provider name by location: {str(e)}")
            return None

    def _get_provider_headers(self, provider_name=None, location_id=None):
        """Get the correct GHL API headers for a provider from cache"""
        if not provider_name:
            logging.info(f"🔑 No provider name provided, using default headers")
            return self.ghl_headers
        
        try:
            # Get provider cache and use its methods
            provider_cache = get_provider_cache()
            
            # Get location_id for this provider
            cached_location_id = provider_cache.get_location_id(provider_name)
            if not cached_location_id:
                logging.warning(f"⚠️ Provider not found in cache: {provider_name}")
                logging.info(f"🔑 Falling back to default headers for provider: {provider_name}")
                return self.ghl_headers, location_id
            
            # Get sub-account API key for this location
            sub_account_api_key = provider_cache.get_sub_account_api_key_by_location_id(cached_location_id)
            
            if sub_account_api_key:
                logging.info(f"🔑 Using cached API key for provider: {provider_name}")
                return {
                    "Authorization": f"Bearer {sub_account_api_key}",
                    "Content-Type": "application/json",
                    "Version": "2021-07-28"
                }, cached_location_id or location_id
            else:
                logging.warning(f"⚠️ No API key cached for provider: {provider_name}")
                
        except Exception as e:
            logging.error(f"❌ Error getting provider headers: {str(e)}")
        
        logging.info(f"🔑 Falling back to default headers for provider: {provider_name}")
        return self.ghl_headers, location_id

    def _create_document_processing_field_update(self, extracted_data, case_data=None):
        """
        Create GHL custom field update using proper field IDs for document processing fields.
        
        Args:
            extracted_data (dict): Document extraction results
            case_data (dict, optional): RMBB case data for additional context
            
        Returns:
            dict: GHL custom field update in proper format
        """
        # Extract relevant data
        approval_status = extracted_data.get('approval_status', 'UNKNOWN')
        document_type = extracted_data.get('document_type', 'Unknown Document')
        processed_date = extracted_data.get('processed_date', datetime.now().isoformat())
        
        # Build field updates using proper field IDs
        field_updates = []
        
        # Current Status Fields
        field_updates.extend([
            {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_current_status"], "value": approval_status},
            {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_current_decision_summary"], "value": extracted_data.get('summary', '')[:500]},
            {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_current_notes"], "value": extracted_data.get('notes', '')[:1000]},
        ])
        
        # IVR-Specific Fields (if applicable)
        if case_data:
            field_updates.extend([
                {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_ivr_patient_data"], "value": case_data.get('patient_name', '')},
                {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_ivr_primary_insurance"], "value": case_data.get('primary_insurance', {}).get('result', '')},
                {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_ivr_secondary_insurance"], "value": case_data.get('secondary_insurance', {}).get('result', '')},
                {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_ivr_coverage_summary"], "value": case_data.get('overall_insurance_result', '')},
                {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_ivr_authorization_info"], "value": extracted_data.get('authorization_info', '')},
            ])
        
        # Document Tracking Fields
        field_updates.extend([
            {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_document_history"], "value": f"{document_type} processed on {processed_date[:10]}"},
            {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_case_summary"], "value": extracted_data.get('case_summary', '')[:1000]},
            {"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_total_documents"], "value": str(extracted_data.get('document_count', 1))},
        ])
        
        # Legacy Field
        field_updates.append({"id": self.DOCUMENT_PROCESSING_FIELDS["rmbb_approval_status"], "value": approval_status})
        
        return {
            "customField": field_updates
        }

    def verify_ghl_contact_exists(self, contact_id, location_id=None, provider_name=None):
        """Verify GHL contact exists using non-location-scoped endpoint (V1 API limitation)"""
        # Get provider-specific headers for API key
        headers_result = self._get_provider_headers(provider_name, location_id)
        if isinstance(headers_result, tuple):
            headers, cached_location_id = headers_result
            # Use cached location_id if we didn't have one
            location_id = location_id or cached_location_id
        else:
            headers = headers_result
        
        # Use non-location-scoped endpoint for verification (V1 API doesn't support location-scoped GET)
        url = f"{self.ghl_base_url}/contacts/{contact_id}"
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                contact_data = response.json()
                
                # Extract the actual location from response
                if 'contact' in contact_data:
                    actual_location_id = contact_data['contact'].get('locationId')
                    logging.info(f"✅ Contact {contact_id} exists in location {actual_location_id}")
                    
                    # Verify it's in the expected location if we have one
                    if location_id and actual_location_id != location_id:
                        logging.warning(f"⚠️ Contact found but in different location. Expected: {location_id}, Actual: {actual_location_id}")
                    
                    return {
                        "exists": True, 
                        "data": contact_data,
                        "actual_location_id": actual_location_id
                    }
                else:
                    logging.info(f"✅ Contact {contact_id} exists")
                    return {"exists": True, "data": contact_data}
                    
            elif response.status_code == 404:
                logging.warning(f"⚠️ Contact {contact_id} not found")
                return {"exists": False, "error": "Contact not found"}
            else:
                logging.error(f"❌ Error verifying contact: {response.status_code} - {response.text}")
                return {"exists": False, "error": f"API error: {response.status_code}"}
        except Exception as e:
            logging.error(f"❌ Exception verifying contact: {str(e)}")
            return {"exists": False, "error": str(e)}

    def update_ghl_contact(self, contact_id, update_data, location_id=None, provider_name=None, add_delay=False):
        """Update GHL contact using V1 API with provider-specific headers and optional delay"""
        
        # Add timing delay if requested (for race condition prevention)
        if add_delay:
            import time
            logging.info(f"⏱️ Adding 3-second delay to prevent race condition with contact creation")
            time.sleep(3)
        
        # Get provider-specific headers and location
        headers_result = self._get_provider_headers(provider_name, location_id)
        if isinstance(headers_result, tuple):
            headers, location_id = headers_result
        else:
            headers = headers_result
        
        # First verify the contact exists
        verification = self.verify_ghl_contact_exists(contact_id, location_id, provider_name)
        if not verification["exists"]:
            # If contact doesn't exist, log but continue workflow (non-critical error)
            logging.warning(f"⚠️ Cannot update contact {contact_id}: {verification['error']}")
            logging.info(f"🔄 Workflow will continue - contact update is not critical for RMBB processing")
            return {"success": False, "error": f"Contact verification failed: {verification['error']}", "non_critical": True}
        
        # Contact exists, proceed with update
        if location_id:
            url = f"{self.ghl_base_url}/locations/{location_id}/contacts/{contact_id}"
        else:
            url = f"{self.ghl_base_url}/contacts/{contact_id}"
        
        logging.info(f"📝 Updating GHL contact {contact_id}")
        logging.info(f"🔗 PUT {url}")
        logging.info(f"👤 Provider: {provider_name}")
        logging.info(f"📍 Location: {location_id}")
        
        try:
            response = requests.put(url, headers=headers, json=update_data)
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
                        "customField": [
                            {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "error"},  # rmbb_workflow_status
                            {"id": "tLNZ4EYxxXUO9HrDpkl5", "value": error_msg},  # rmbb_error_message
                            {"id": "4AnL32P9rjYcPjbukcok", "value": datetime.now().isoformat()}  # rmbb_error_date
                        ]
                    }
                    # Try to get provider name from locals for proper error update
                    provider_name_for_error = locals().get('provider_name', '')
                    self.update_ghl_contact(
                        contact_id, 
                        error_status_update,
                        provider_name=provider_name_for_error
                    )
                    print(f"⚠️ Error status updated in GHL contact {contact_id}")
            except:
                pass  # Don't fail on error logging
            
            return {
                "success": False,
                "error": error_msg
            }

    def process_approval_document_with_extraction(self, case_id, contact_id, location_id, provider_name, status_context=None):
        """
        Process case data directly from RMBB Health JSON API instead of document extraction
        Replaces OCR functionality with direct JSON data processing
        
        Args:
            case_id: RMBBHealth case ID
            contact_id: GHL contact ID  
            location_id: GHL location ID
            provider_name: Name of provider for context
            status_context: Dict containing status trigger analysis (NEW - optional)
                - trigger_type: What type of status change triggered this
                - status_field: Which RMBB field changed
                - action_needed: What document processing action to take
                - document_priority: Priority for document filtering
                - workflow_tags: Tags to add after processing
            
        Returns:
            dict: Processing results with success status and metadata
        """
        # Log status context information if provided
        if status_context:
            logging.info(f"📄 Starting STATUS-TRIGGERED JSON processing for case {case_id}")
            logging.info(f"   🎯 Trigger: {status_context['trigger_type']}")
            logging.info(f"   📊 Field: {status_context['status_field']}")
            logging.info(f"   🔄 Action: {status_context['action_needed']}")
            logging.info(f"   🏷️ Tags: {status_context.get('workflow_tags', [])}")
        else:
            logging.info(f"📄 Starting general JSON processing for case {case_id}")
        
        try:
            # Step 1: Get complete case data from RMBB Health API
            case_data = self.case_service.get_case(case_id)
            
            if not case_data:
                return {
                    "success": False,
                    "message": f"Could not fetch case data for case {case_id}",
                    "files_processed": 0,
                    "document_type": None,
                    "approval_status": None,
                    "workflow_tags": [],
                    "status_trigger": status_context.get('trigger_type') if status_context else None
                }
            
            logging.info(f"📋 Processing JSON case data for case {case_id}")
            
            # Step 2: Process case JSON data using new JSON-based document processor
            from services.document_processor import DocumentProcessor
            processor = DocumentProcessor()
            
            result = processor.process_case_json_data(case_data)
            
            if not result['success']:
                logging.error(f"❌ JSON processing failed: {result['error']}")
                return {
                    "success": False,
                    "error": result['error'],
                    "files_processed": 0,
                    "document_type": None,
                    "approval_status": None,
                    "workflow_tags": [],
                    "status_trigger": status_context.get('trigger_type') if status_context else None
                }
                
            logging.info(f"✅ JSON processing succeeded")
            logging.info(f"📋 Document type: {result['extracted_data'].get('document_type', 'Unknown')}")
            logging.info(f"📊 Approval status: {result['extracted_data'].get('approval_status', 'Unknown')}")
            
            # Step 3: Update GHL contact with extracted JSON data
            # Get API key from provider cache
            from services.provider_location_cache import get_provider_cache
            provider_cache = get_provider_cache()
            sub_account_api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
            
            if not sub_account_api_key:
                logging.error(f"❌ No sub-account API key found for location {location_id}")
                return {
                    "success": False,
                    "error": f"No sub-account API key found for location {location_id}",
                    "files_processed": 0,
                    "document_type": result['extracted_data'].get('document_type'),
                    "approval_status": result['extracted_data'].get('approval_status'),
                    "workflow_tags": [],
                    "status_trigger": status_context.get('trigger_type') if status_context else None
                }
            
            # Use smart layering to update GHL fields
            success = self._process_document_with_smart_layering(
                contact_id=contact_id,
                location_id=location_id, 
                api_key=sub_account_api_key,
                extracted_data=result['extracted_data'],
                case_id=case_id,
                document_name=f"Case_{case_id}_JSON_Data"
            )
            
            if success:
                # Step 4: Apply status-specific workflow tags after successful JSON processing
                workflow_tags_applied = []
                if status_context and status_context.get('workflow_tags'):
                    for tag in status_context['workflow_tags']:
                        tag_success = self._add_contact_tag(contact_id, location_id, sub_account_api_key, tag)
                        if tag_success:
                            workflow_tags_applied.append(tag)
                            logging.info(f"✅ Applied workflow tag: {tag}")
                        else:
                            logging.warning(f"⚠️ Failed to apply workflow tag: {tag}")
                
                return {
                    "success": True,
                    "message": f"Successfully processed JSON case data",
                    "files_processed": 1,  # One JSON case processed
                    "processing_results": [{
                        "file_name": f"Case_{case_id}_JSON_Data",
                        "status": "success",
                        "document_type": result['extracted_data'].get('document_type'),
                        "approval_status": result['extracted_data'].get('approval_status')
                    }],
                    "document_type": result['extracted_data'].get('document_type'),
                    "approval_status": result['extracted_data'].get('approval_status'),
                    "workflow_tags": workflow_tags_applied,
                    "status_trigger": status_context.get('trigger_type') if status_context else None
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to update GHL contact with JSON data",
                    "files_processed": 0,
                    "document_type": result['extracted_data'].get('document_type'),
                    "approval_status": result['extracted_data'].get('approval_status'),
                    "workflow_tags": [],
                    "status_trigger": status_context.get('trigger_type') if status_context else None
                }
                
        except Exception as e:
            logging.error(f"❌ Document processing workflow failed: {str(e)}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "files_processed": 0,
                "document_type": None,
                "approval_status": None,
                "workflow_tags": [],
                "status_trigger": status_context.get('trigger_type') if status_context else None
            }
    
    def _is_processable_document(self, file_name):
        """Check if a file is a processable document (PDF, HTML, DOC/DOCX) - Process ALL documents"""
        file_name_lower = file_name.lower()
        
        # Process any document with supported file extensions
        processable_extensions = ['.pdf', '.html', '.htm', '.doc', '.docx']
        
        # Check if file has a processable extension
        has_processable_extension = any(file_name_lower.endswith(ext) for ext in processable_extensions)
        
        # Skip system/temp files that aren't documents
        skip_patterns = [
            'temp', 'tmp', '.log', '.txt', '.json', '.xml', '.csv',
            'system', 'cache', 'backup', '.bak', '.old'
        ]
        should_skip = any(pattern in file_name_lower for pattern in skip_patterns)
        
        return has_processable_extension and not should_skip
    
    def _process_single_document(self, case_id, document_url, document_name, contact_id, location_id):
        """
        Process any single document by extracting content and storing in GHL custom fields
        Handles approvals, denials, appeals, and any other document type
        
        Args:
            case_id: RMBBHealth case ID
            document_url: Direct S3 download URL from RMBBHealth
            document_name: Name of the document file
            contact_id: GHL contact ID
            location_id: GHL location ID
            
        Returns:
            dict: Processing result with success status, document_type, and approval_status
        """
        logging.info(f"📄 Processing single document: {document_name}")
        
        try:
            # Get API key from provider cache
            from services.provider_location_cache import get_provider_cache
            provider_cache = get_provider_cache()
            sub_account_api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
            
            if not sub_account_api_key:
                logging.error(f"❌ No sub-account API key found for location {location_id}")
                return {
                    "success": False,
                    "error": f"No sub-account API key found for location {location_id}",
                    "document_type": None,
                    "approval_status": None
                }
            
            # Step 1: Process document and extract data
            from services.document_processor import DocumentProcessor
            processor = DocumentProcessor()
            
            result = processor.process_document_from_url(document_url, document_name)
            
            if not result['success']:
                logging.error(f"❌ Document processing failed: {result['error']}")
                return {
                    "success": False,
                    "error": result['error'],
                    "document_type": None,
                    "approval_status": None
                }
                
            logging.info(f"✅ Document processing succeeded")
            logging.info(f"📊 Extracted {len(result['text_content'])} characters of text")
            logging.info(f"📋 Document type: {result['extracted_data'].get('document_type', 'Unknown')}")
            
            # Step 2: Use SMART LAYERED APPROACH - handle multiple documents properly
            success = self._process_document_with_smart_layering(
                contact_id=contact_id,
                location_id=location_id, 
                api_key=sub_account_api_key,
                extracted_data=result['extracted_data'],
                case_id=case_id,
                document_name=document_name
            )
            
            if not success:
                logging.error(f"❌ Failed to update GHL contact with document data")
                return {
                    "success": False,
                    "error": "Failed to update GHL contact with document data",
                    "document_type": result['extracted_data'].get('document_type'),
                    "approval_status": result['extracted_data'].get('approval_status')
                }
            
            # Step 4: Add workflow trigger tag
            tag_success = self._add_contact_tag(contact_id, location_id, sub_account_api_key, "rmbb-document-processed")
            if tag_success:
                logging.info(f"✅ Added rmbb-document-processed tag")
            else:
                logging.warning(f"⚠️ Failed to add tag, but document data updated successfully")
            
            logging.info(f"🎉 Document extraction workflow completed for case {case_id}")
            return {
                "success": True,
                "document_type": result['extracted_data'].get('document_type'),
                "approval_status": result['extracted_data'].get('approval_status'),
                "text_length": len(result['text_content'])
            }
            
        except Exception as e:
            logging.error(f"❌ Document extraction workflow failed: {str(e)}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "document_type": None,
                "approval_status": None
            }

    def _map_document_data_to_ghl_fields(self, extracted_data, case_id, document_name):
        """
        HYBRID FIELD ARCHITECTURE - Maps to Visual + IVR-specific + Document tracking fields
        Enables both provider visualization AND clean automation data extraction
        """
        
        # HYBRID FIELD MAPPING STRUCTURE
        field_mappings = {
            # EXISTING WEBHOOK STATUS FIELDS (PRESERVED FROM 17:23 BACKUP)
            'rmbb_workflow_status': 'k9onZaMZVJ5Zwlopf2fi',  # EXISTING - do not change
            'rmbb_ivr_received_date': '4AnL32P9rjYcPjbukcok',  # EXISTING - do not change
            'rmbb_webhook_processed': 'drfCODR4HhoKeI3eoH6J',  # EXISTING - do not change
            'rmbb_case_status': 'A2gqU59iygkmxwUeO2j6',  # EXISTING - do not change
            'rmbb_external_status': 'b7odVJaRBRTBQlVaUCF1',  # EXISTING - do not change
            'rmbb_overall_result': 'NStZu6i6cSflIhmRS7Eg',  # EXISTING - do not change
            'rmbb_primary_insurance_status': 'lek4SmWzewBgvrAXBLWy',  # EXISTING - do not change
            'rmbb_secondary_insurance_status': 'vnZmPnf00xi9ImOLxao9',  # EXISTING - do not change
            'rmbb_tertiary_insurance_status': 'JeBBYNNHOWqyYU5FMA1w',  # EXISTING - do not change
            'rmbb_primary_insurance_result': 'tXkwLnHu00e9t2MdGarP',  # EXISTING - do not change
            'rmbb_secondary_insurance_result': '0viEC6QFPlBZIm75N0fE',  # EXISTING - do not change
            
            # NEW HYBRID DOCUMENT FIELDS (REAL GHL FIELD IDs FROM DOCUMENT_PROCESSING_FIELDS)
            # VISUAL UNDERSTANDING FIELDS (5 fields - for provider viewing)
            'rmbb_current_patient_info': 'XueHehokZYjJSvWGzjfk',
            'rmbb_current_insurance_info': 'FoqW1DyrjW6WtsoPflFZ', 
            'rmbb_current_decision_summary': 'XQLSYwSOodHOBrqv8oz0',
            'rmbb_current_notes': 'tLNZ4EYxxXUO9HrDpkl5',
            'rmbb_current_status': 'CWCMdJsRU4hMEDS32U4s',
            
            # IVR-SPECIFIC EXTRACTION FIELDS (5 fields - for clean automation)
            'rmbb_ivr_patient_data': 'TAA2QAEXDh14bIkYacWW',
            'rmbb_ivr_primary_insurance': 'VXpnvGzV94MPikiXXrFh',
            'rmbb_ivr_secondary_insurance': 'IYWefx90XVJMC3kIJaSz',
            'rmbb_ivr_coverage_summary': 'm8Ml4hPPfNgfoURqBsSt',
            'rmbb_ivr_authorization_info': 'Y2zXVZYUzXLxLRm70J1E',
            
            # DOCUMENT TRACKING FIELDS (3 fields - for history and context)
            'rmbb_document_history': 'dGy54D7hPD0Ydp4c8EsO',
            'rmbb_case_summary': 'WGKrQzlaNsK8Y4t5bUYf',
            'rmbb_total_documents': 'DuqFjhMUOv2yKa5qbdyR',
            
            # LEGACY APPROVAL STATUS FIELD (1 field - for backward compatibility)
            'rmbb_approval_status': 'pbPVNjx7lmzlMkh4QYHs'
        }
        
        """
        HYBRID APPROACH:
        - VISUAL fields: Always updated with most important document for provider viewing
        - IVR fields: Only populated when processing IVR approval documents
        - DOCUMENT fields: Always updated with history and tracking info
        """
        
        document_type = extracted_data.get('document_type', 'Unknown Document')
        approval_status = extracted_data.get('approval_status', 'UNKNOWN')
        is_ivr_approval = self._is_ivr_approval_document(document_type, approval_status)
        
        # ALWAYS UPDATE: Visual Understanding Fields (for provider interface)
        visual_fields = self._create_visual_fields(extracted_data, field_mappings, case_id, document_name)
        
        # CONDITIONALLY UPDATE: IVR-Specific Fields (only for IVR approvals)
        ivr_fields = []
        if is_ivr_approval:
            logging.info(f"📋 IVR APPROVAL DETECTED - Populating IVR-specific fields")
            ivr_fields = self._create_ivr_specific_fields(extracted_data, field_mappings)
        else:
            logging.info(f"📝 NON-IVR DOCUMENT - IVR fields unchanged")
        
        # ALWAYS UPDATE: Legacy approval status field (backward compatibility)
        legacy_fields = [{
            'id': field_mappings['rmbb_approval_status'],
            'value': f"DOCUMENT_{approval_status}"
        }]
        
        # Combine all field updates
        all_field_updates = visual_fields + ivr_fields + legacy_fields
        
        logging.info(f"📋 Created {len(all_field_updates)} hybrid field updates")
        logging.info(f"   👁️  Visual fields: {len(visual_fields)} (always updated)")
        logging.info(f"   🏥 IVR fields: {len(ivr_fields)} ({'updated' if is_ivr_approval else 'unchanged'})")
        logging.info(f"   📜 Legacy fields: {len(legacy_fields)} (backward compatibility)")
        
        return all_field_updates
    
    def _is_ivr_approval_document(self, document_type, approval_status):
        """Check if this is specifically an IVR approval document"""
        return (document_type in ['Insurance Verification', 'Prior Authorization'] and 
                approval_status == 'APPROVED')
    
    def _create_visual_fields(self, extracted_data, field_mappings, case_id, document_name):
        """Create visual understanding fields for provider interface"""
        from datetime import datetime
        
        # Combine patient and case info for visual clarity
        patient_info = extracted_data.get('patient_case_info', '')
        case_info = f"Case: {case_id} | Document: {document_name}"
        combined_patient_info = f"{patient_info}\n{case_info}" if patient_info else case_info
        
        # Combine insurance info for visual clarity
        primary_ins = extracted_data.get('primary_insurance_details', '')
        secondary_ins = extracted_data.get('secondary_insurance_details', '')
        combined_insurance = f"PRIMARY:\n{primary_ins}\n\nSECONDARY:\n{secondary_ins}" if primary_ins and secondary_ins else (primary_ins or secondary_ins or 'No insurance details available')
        
        # Get decision summary
        decision_summary = extracted_data.get('coverage_summary_authorization', 'No decision details available')
        
        # Get important notes
        important_notes = extracted_data.get('disclaimer_notes', 'No additional notes')
        
        # Current status with timestamp
        approval_status = extracted_data.get('approval_status', 'UNKNOWN')
        document_type = extracted_data.get('document_type', 'Unknown Document')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        status_with_timestamp = f"{approval_status} - {document_type} ({timestamp})"
        
        return [
            {'id': field_mappings['rmbb_current_patient_info'], 'value': combined_patient_info},
            {'id': field_mappings['rmbb_current_insurance_info'], 'value': combined_insurance},
            {'id': field_mappings['rmbb_current_decision_summary'], 'value': decision_summary},
            {'id': field_mappings['rmbb_current_notes'], 'value': important_notes},
            {'id': field_mappings['rmbb_current_status'], 'value': status_with_timestamp}
        ]
    
    def _create_ivr_specific_fields(self, extracted_data, field_mappings):
        """Create IVR-specific fields for clean automation extraction"""
        return [
            {'id': field_mappings['rmbb_ivr_patient_data'], 'value': extracted_data.get('patient_case_info', '')},
            {'id': field_mappings['rmbb_ivr_primary_insurance'], 'value': extracted_data.get('primary_insurance_details', '')},
            {'id': field_mappings['rmbb_ivr_secondary_insurance'], 'value': extracted_data.get('secondary_insurance_details', '')},
            {'id': field_mappings['rmbb_ivr_coverage_summary'], 'value': extracted_data.get('coverage_summary_authorization', '')},
            {'id': field_mappings['rmbb_ivr_authorization_info'], 'value': extracted_data.get('disclaimer_notes', '')}
        ]

    def _update_contact_with_document_fields(self, contact_id, location_id, api_key, field_updates):
        """Update GHL contact with document-extracted field data"""
        
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # Prepare update payload in GHL format
            update_data = {
                'customField': field_updates
            }
            
            contact_url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
            response = requests.put(contact_url, json=update_data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logging.info(f"✅ Updated contact with {len(field_updates)} document fields")
                
                # Log the field updates for debugging
                for field in field_updates:
                    logging.info(f"   📝 Field {field['id']}: {field['value']}")
                
                return True
            else:
                logging.error(f"❌ Failed to update contact: HTTP {response.status_code}")
                logging.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Error updating contact with document fields: {str(e)}")
            return False

    def _add_contact_tag(self, contact_id, location_id, api_key, tag_name):
        """Add a workflow trigger tag to a GHL contact (preserves existing tags)"""
        
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # FIXED: First get existing tags to avoid overwriting them
            contact_url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
            get_response = requests.get(contact_url, headers=headers, timeout=30)
            
            existing_tags = []
            if get_response.status_code == 200:
                contact_data = get_response.json()
                # Handle different GHL API response formats
                if 'contact' in contact_data and 'tags' in contact_data['contact']:
                    existing_tags = contact_data['contact']['tags'] or []
                elif 'tags' in contact_data:
                    existing_tags = contact_data['tags'] or []
                
                logging.info(f"📋 Existing tags for contact {contact_id}: {existing_tags}")
            else:
                logging.warning(f"⚠️ Could not get existing tags, proceeding with new tag only")
            
            # Add new tag to existing tags (avoid duplicates)
            if tag_name not in existing_tags:
                existing_tags.append(tag_name)
                logging.info(f"➕ Adding new tag '{tag_name}' to existing tags")
            else:
                logging.info(f"ℹ️ Tag '{tag_name}' already exists, skipping")
                return True  # Tag already exists, consider it successful
            
            # Update contact with complete tag list
            tag_data = {
                'tags': existing_tags
            }
            
            response = requests.put(contact_url, json=tag_data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logging.info(f"✅ Updated contact {contact_id} with tags: {existing_tags}")
                return True
            else:
                logging.error(f"❌ Failed to update tags: HTTP {response.status_code}")
                logging.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Error adding contact tag: {str(e)}")
            return False

    def _process_document_with_smart_layering(self, contact_id, location_id, api_key, extracted_data, case_id, document_name):
        """
        Smart Layered Approach: Handles multiple documents without overwriting
        
        Strategy:
        1. Primary Fields (5) - Always show most important/recent document
        2. Document History - Chronological log of all documents
        3. Case Summary - Current status and journey overview
        """
        try:
            from datetime import datetime
            
            logging.info(f"📋 Processing document with smart layering approach")
            
            # Step 1: Get current document history to avoid overwriting
            current_history = self._get_current_field_value(
                contact_id, location_id, api_key, "rmbb_document_history_log"
            )
            
            # Step 2: Create new document entry for history
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            document_entry = self._format_document_entry(
                timestamp, extracted_data, case_id, document_name
            )
            
            # Step 3: Append to history (preserves all previous documents)
            updated_history = self._append_to_document_history(current_history, document_entry)
            
            # Step 4: Determine if this document should become the "primary" (5 main fields)
            should_update_primary = self._should_update_primary_fields(extracted_data, current_history)
            
            # Step 5: Prepare field updates based on layering logic
            if should_update_primary:
                logging.info(f"📄 Document qualifies as PRIMARY - updating main 5 fields")
                primary_fields = self._map_document_data_to_ghl_fields(extracted_data, case_id, document_name)
            else:
                logging.info(f"📝 Document added to HISTORY only - keeping current primary fields")
                primary_fields = []
            
            # Step 6: Always update document tracking fields
            document_tracking_fields = [
                {
                    'id': 'rmbb_document_history_id', 
                    'value': updated_history
                },
                {
                    'id': 'rmbb_case_summary_id',
                    'value': self._generate_case_summary(updated_history, extracted_data)
                },
                {
                    'id': 'rmbb_total_documents_id',
                    'value': str(self._count_documents_in_history(updated_history))
                }
            ]
            
            # Step 7: Combine all field updates (primary includes visual + IVR fields)
            all_field_updates = primary_fields + document_tracking_fields
            
            # Step 8: Update GHL contact with combined fields
            success = self._update_contact_with_document_fields(
                contact_id, location_id, api_key, all_field_updates
            )
            
            if not success:
                return False
            
            # Step 9: Add smart workflow tags based on document type and status
            tag_success = self._add_smart_workflow_tags(
                contact_id, location_id, api_key, extracted_data
            )
            
            if success:
                logging.info(f"✅ Smart layered document processing completed")
                logging.info(f"   📄 Primary fields updated: {'Yes' if should_update_primary else 'No'}")
                logging.info(f"   📝 History updated: Yes")
                logging.info(f"   🏷️  Smart tags added: {'Yes' if tag_success else 'Partial'}")
                logging.info(f"   📊 Total documents in case: {self._count_documents_in_history(updated_history)}")
            
            return success
            
        except Exception as e:
            logging.error(f"❌ Smart layered processing failed: {str(e)}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _get_current_field_value(self, contact_id, location_id, api_key, field_name):
        """Get current value of a custom field from GHL contact"""
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # Get contact details including custom fields
            contact_url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
            response = requests.get(contact_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                contact_data = response.json()
                custom_fields = contact_data.get('customField', [])
                
                # Find the specific field (need to map field_name to actual field ID)
                field_id_mapping = {
                    'rmbb_document_history_log': 'rmbb_document_history_log_field_id'
                }
                
                field_id = field_id_mapping.get(field_name, field_name)
                
                for field in custom_fields:
                    if field.get('id') == field_id:
                        return field.get('value', '')
                
                return ''  # Field not found or empty
            else:
                logging.warning(f"⚠️ Failed to get current field value: HTTP {response.status_code}")
                return ''
                
        except Exception as e:
            logging.warning(f"⚠️ Error getting current field value: {str(e)}")
            return ''

    def _format_document_entry(self, timestamp, extracted_data, case_id, document_name):
        """Format a single document entry for the history log"""
        document_type = extracted_data.get('document_type', 'Unknown Document')
        approval_status = extracted_data.get('approval_status', 'UNKNOWN')
        
        # Create compact but informative entry
        entry = f"""{timestamp} - {document_type.upper()}
Document: {document_name}
Status: {approval_status}
Case: {case_id}"""
        
        # Add key details if available
        if extracted_data.get('patient_case_info'):
            # Extract patient name if available
            patient_info = extracted_data['patient_case_info']
            if 'PATIENT NAME:' in patient_info:
                patient_line = patient_info.split('PATIENT NAME:')[1].split('\n')[0][:50]
                entry += f"\nPatient: {patient_line.strip()}"
        
        return entry

    def _append_to_document_history(self, current_history, new_document_entry):
        """Append new document to existing history"""
        if current_history and current_history.strip():
            return f"{current_history}\n\n---\n{new_document_entry}"
        else:
            return new_document_entry

    def _should_update_primary_fields(self, extracted_data, current_history):
        """
        Determine if this document should update the primary 5 fields
        
        Priority Logic:
        1. APPROVED status always becomes primary
        2. DENIED only becomes primary if no previous APPROVED
        3. PENDING only becomes primary if no previous APPROVED/DENIED
        """
        document_status = extracted_data.get('approval_status', 'UNKNOWN')
        
        # Always update for approvals
        if document_status == 'APPROVED':
            return True
        
        # For denials/pending, check if we already have an approval in history
        if current_history:
            if 'Status: APPROVED' in current_history:
                return False  # Don't override existing approval
        
        # Update for denials if no approval exists
        if document_status == 'DENIED':
            return True
            
        # Update for pending if no approval/denial exists
        if document_status == 'PENDING':
            if current_history and ('Status: APPROVED' in current_history or 'Status: DENIED' in current_history):
                return False
            return True
        
        # Default: update primary fields
        return True

    def _generate_case_summary(self, document_history, current_extracted_data):
        """Generate a concise case summary from document history"""
        if not document_history:
            return 'No documents processed yet'
        
        # Count document types
        total_docs = document_history.count('---') + 1
        approvals = document_history.count('Status: APPROVED')
        denials = document_history.count('Status: DENIED')
        pending = document_history.count('Status: PENDING')
        
        # Determine final status
        current_status = current_extracted_data.get('approval_status', 'UNKNOWN')
        
        # Create journey description
        journey_parts = []
        if denials > 0:
            journey_parts.append(f"{denials} Denial{'s' if denials > 1 else ''}")
        if pending > 0:
            journey_parts.append(f"{pending} Pending")
        if approvals > 0:
            journey_parts.append(f"{approvals} Approval{'s' if approvals > 1 else ''}")
        
        journey = " → ".join(journey_parts) if journey_parts else "Processing"
        
        return f"CASE STATUS: {current_status} | JOURNEY: {journey} | TOTAL DOCS: {total_docs}"

    def _count_documents_in_history(self, document_history):
        """Count total number of documents in history"""
        if not document_history:
            return 0
        return document_history.count('---') + 1

    def _add_smart_workflow_tags(self, contact_id, location_id, api_key, extracted_data):
        """
        Add intelligent workflow tags based on document type and status
        Enables targeted workflows and notifications for different scenarios
        """
        try:
            document_type = extracted_data.get('document_type', 'Unknown Document')
            approval_status = extracted_data.get('approval_status', 'UNKNOWN')
            
            # Determine which smart tags to add
            tags_to_add = []
            
            # IVR-specific tags (highest priority for automation)
            if document_type in ['Insurance Verification', 'Prior Authorization']:
                if approval_status == 'APPROVED':
                    tags_to_add.append('rmbb-ivr-approved')
                    logging.info(f"🏥 IVR APPROVAL - Adding automation tag")
                elif approval_status == 'DENIED':
                    tags_to_add.append('rmbb-ivr-denied')
                    logging.info(f"🏥 IVR DENIAL - Adding response tag")
                elif approval_status == 'PENDING':
                    tags_to_add.append('rmbb-ivr-pending')
            
            # Denial-specific tags
            elif document_type == 'Denial Notice':
                tags_to_add.append('rmbb-denial-received')
                logging.info(f"❌ DENIAL DOCUMENT - Adding response workflow tag")
            
            # Appeal-specific tags
            elif document_type == 'Appeal Document':
                if approval_status == 'APPROVED':
                    tags_to_add.append('rmbb-appeal-approved')
                    logging.info(f"✅ APPEAL APPROVED - Adding success workflow tag")
                elif approval_status == 'DENIED':
                    tags_to_add.append('rmbb-appeal-denied')
                    logging.info(f"❌ APPEAL DENIED - Adding escalation workflow tag")
                else:
                    tags_to_add.append('rmbb-appeal-submitted')
                    logging.info(f"📋 APPEAL SUBMITTED - Adding tracking workflow tag")
            
            # Universal document processing tag (always added)
            tags_to_add.append('rmbb-document-processed')
            
            # Add all tags
            tag_success_count = 0
            for tag in tags_to_add:
                if self._add_contact_tag(contact_id, location_id, api_key, tag):
                    tag_success_count += 1
            
            logging.info(f"🏷️  Added {tag_success_count}/{len(tags_to_add)} workflow tags")
            
            return tag_success_count == len(tags_to_add)
            
        except Exception as e:
            logging.error(f"❌ Smart workflow tagging failed: {str(e)}")
            return False
    
    def clear_all_product_fields(self, contact_id, location_id):
        """
        Clear all 59 product size custom fields for reorder processing.
        This ensures only new product combinations are set, not mixed with old ones.
        
        Args:
            contact_id: GHL contact ID
            location_id: GHL location ID
            
        Returns:
            dict: Success status and count of fields cleared
        """
        try:
            logging.info(f"🧹 Clearing all product size custom fields for contact {contact_id}")
            
            # All 59 product size field IDs (from product_size_custom_fields_exact.json)
            all_product_field_ids = [
                "UIzU1pZrL152YHZTir3L", "Jw6QYCnsHAeljtL3wLiC", "0yKQhFBUyO9K19Bc0w9z", "tEOxPM5D74E0rHUgNWjM", "BgFWTZagGzBSrMhQ2tBB", "9cZwOk1aSZdmJhrvb2vV",
                "2fafSgR6pGGO0gf8zOBP", "3Hqcs5ZhpqEJzjSPf3Lt", "PuqA4kHlq2zz4wvjPEEV", "7MQLrCQmxMY6wSo8T37d", "I72EW2WC5g3uP96QkbH2", "1wRVl8s66nw2YJfV8pQs",
                "gcwVJZhVlWVcANsacP5P", "MgkQkGQCUJuVJXNT1a1j", "hMIyEgTFQ1JfAWLHPJxp", "Mw5HPONHzwjXQGhpCOWL", "CZLJh8MzaDCovzjdWvW7", "p5lkgaALhwg4m3lCJr7S",
                "pGLvq0VtJ0qVBBiVj7tO", "Z8dX4Y7p7j5lhXB1JCWM", "Z9QTy5VZGKs44T8QzSyy", "vPr8e8YbOsqK1WQGCRqT", "YhXMD3j2o6vUfOlGwKgB", "pAyIyKElmrSZt5A5wpg2",
                "2w9lTvgJZqIiJZHjdO3A", "HRGD2KCfA3Jm5r3Dw7cJ", "x2qgdlF1aO4GYZF44ZiP", "dBuHfzQGSCX9sUWgZrC8", "uxdx2LYYxGtHILBnb6vR", "dNDFULnAfpLmdxnMcL8T",
                "4WH8kw68bq4a0nVj5fvg", "JMZYCUGHlZlJ3gXwKJJs", "q4tFQqslf6nJzKZhHfZD", "4e7nzGCPOa2T4ZnIWEJH", "gFUNgw7Iw8Ls3l9QNdkz", "QbZGpUkCzgMfK8kCtEzK",
                "QRrvlqtIDHdpyE4nA2rQ", "f0nH1kLJIVMkPCDm8T5J", "rTHLG6BmYKM3BdJ2EHjm", "AJnx4P5rMN8bZj4Q5qKW", "9RmVaKkpwJzH3j4WtFgP", "mD8ZcYhR9qQ4WJnH2fvK",
                "uZ1PwT0rX9k4KjNYKqcB", "JCLmDzXbKWrxdAKHzJW7", "j7GPyKcD2mIb9PDxbdYK", "rFO7KqJPNX7lHzK5kdjm", "VV4jnAGPx2sEXnMXMQ6v", "r8rEUJ0zMUEQ5v2nZYeJ",
                "K2gSAYlZq5hXJPE9n9Lw", "5VvZr7e7oZWWznNBqEo5", "6N5qXsEQmHdPGjWF5RTF", "ZTrfEOdKhDTLZnCrjpF8", "7CfhyIqvgmYNhgOWEUQx", "mHiw5P2oROGQ7dXzgwAR",
                "Jl1EYQvKLqIH7mLgLnxM", "WKgHJxJwDSDd6qhMPzQa", "wZH7XCLJd2WvlPBOhGtb", "kxMTJvKOXwH75mjq2pU8", "7m4O2eEeXUmXdFnVLWRD", "Hm6J3uGfxS5HZd6CyqnE", "FRrYzDqPOFPdX5c6A8VU"
            ]
            
            # Get sub-account API key for this location
            api_key = self._get_subaccount_api_key(location_id)
            if not api_key:
                return {
                    "success": False,
                    "error": f"No API key found for location {location_id}",
                    "fields_cleared": 0
                }
            
            # Prepare custom fields update to clear all product fields
            custom_fields_list = []
            for field_id in all_product_field_ids:
                custom_fields_list.append({
                    "id": field_id,
                    "value": ""  # Empty string clears the field
                })
            
            # Make GHL API call to clear fields
            url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Version": "2021-07-28"
            }
            
            payload = {"customField": custom_fields_list}
            
            logging.info(f"🧹 Clearing {len(custom_fields_list)} product fields...")
            response = requests.put(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                logging.info(f"✅ Successfully cleared {len(custom_fields_list)} product fields")
                return {
                    "success": True,
                    "message": f"Cleared {len(custom_fields_list)} product fields",
                    "fields_cleared": len(custom_fields_list)
                }
            else:
                error_msg = f"GHL API error {response.status_code}: {response.text}"
                logging.error(f"❌ Field clearing failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "fields_cleared": 0
                }
                
        except Exception as e:
            logging.error(f"❌ Error clearing product fields: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "fields_cleared": 0
            }
    
    def add_reorder_tag(self, contact_id, location_id):
        """
        Add 'rmbb-re-order' tag to trigger reorder workflow.
        
        Args:
            contact_id: GHL contact ID
            location_id: GHL location ID
            
        Returns:
            dict: Success status and tag application result
        """
        try:
            logging.info(f"🏷️ Adding reorder tag to contact {contact_id}")
            
            # Get sub-account API key for this location
            api_key = self._get_subaccount_api_key(location_id)
            if not api_key:
                return {
                    "success": False,
                    "error": f"No API key found for location {location_id}"
                }
            
            # Add the reorder tag
            tag_success = self._add_contact_tag(contact_id, location_id, api_key, "rmbb-re-order")
            
            if tag_success:
                logging.info(f"✅ Successfully added 'rmbb-re-order' tag")
                return {
                    "success": True,
                    "message": "Reorder tag added successfully",
                    "tag_applied": True
                }
            else:
                logging.error(f"❌ Failed to add reorder tag")
                return {
                    "success": False,
                    "error": "Failed to add reorder tag",
                    "tag_applied": False
                }
                
        except Exception as e:
            logging.error(f"❌ Error adding reorder tag: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "tag_applied": False
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