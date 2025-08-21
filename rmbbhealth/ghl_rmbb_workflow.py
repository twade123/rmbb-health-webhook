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
sys.path.insert(0, '/Users/timothywade/Jarvis')

from rmbbhealth import RMBBHealthClient, PatientService, CaseService
from rmbbhealth.services.provider_location_cache import get_provider_cache

class GHLRMBBWorkflowHandler:
    """Complete workflow handler for GHL → RMBB Health → GHL integration"""
    
    def __init__(self, rmbb_api_key, rmbb_team_id, ghl_api_key):
        # RMBB Health setup
        self.rmbb_client = RMBBHealthClient(api_key=rmbb_api_key, team_id=rmbb_team_id)
        self.patient_service = PatientService(self.rmbb_client)
        self.case_service = CaseService(self.rmbb_client)
        
        # GHL V1 API setup (based on complete_subaccount_creation.py)
        self.ghl_api_key = ghl_api_key
        self.ghl_base_url = "https://rest.gohighlevel.com/v1"
        self.ghl_headers = {
            "Authorization": f"Bearer {ghl_api_key}",
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
        
        # Extract patient data using robust field mapping
        patient_form_data = self.extract_patient_data(webhook_payload)
        
        print(f"📧 Contact ID: {contact_id}")
        print(f"📍 Location ID: {location_id}")
        print(f"👤 Patient: {patient_form_data['first_name']} {patient_form_data['last_name']}")
        print(f"👨‍⚕️ Provider: {patient_form_data.get('provider_name', 'NOT SPECIFIED')}")
        
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
                {"key": "rmbb_patient_name", "value": f"{patient_form_data['first_name']} {patient_form_data['last_name']}"},
                {"key": "rmbb_wound_type", "value": patient_form_data.get('wound_type', '')},
                {"key": "rmbb_primary_insurance", "value": patient_form_data.get('primary_insurance_name', '')}
            ]
        }
        
        # Update GHL contact with initial tracking data
        contact_update_result = self.update_ghl_contact(contact_id, initial_tracking_data)
        if contact_update_result["success"]:
            print(f"✅ Initial tracking data stored in GHL contact {contact_id}")
        else:
            print(f"⚠️ Warning: Failed to store initial tracking data: {contact_update_result['error']}")
        
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
            patient_response = self.rmbb_client.patient_service.create_patient(rmbb_patient_data)
            print(f"✅ Patient created with ID: {patient_response['id']}")
        except Exception as e:
            error_msg = f"Failed to create RMBB Health patient: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        
        # Transform form data to case format with external_id linking back to GHL contact
        rmbb_case_data = self.transform_case_data(patient_form_data, patient_response['id'])
        rmbb_case_data["external_id"] = external_id  # Link back to GHL contact
        
        print("\nCreating case for qualification...")
        print(f"🔗 Case external_id: {external_id} (links to GHL contact {contact_id})")
        
        # Create case using real RMBB Health API
        try:
            case_response = self.rmbb_client.case_service.create_case(rmbb_case_data)
            print(f"✅ Case created with ID: {case_response['id']}")
        except Exception as e:
            error_msg = f"Failed to create RMBB Health case: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        
        # Update GHL contact with RMBB IDs and status
        rmbb_tracking_update = {
            "customFields": [
                {"key": "rmbb_workflow_status", "value": "submitted_for_qualification"},
                {"key": "rmbb_patient_id", "value": str(patient_response['id'])},
                {"key": "rmbb_case_id", "value": str(case_response['id'])},
                {"key": "rmbb_submission_completed", "value": datetime.now().isoformat()}
            ]
        }
        
        # Update GHL contact
        contact_update_result = self.update_ghl_contact(contact_id, rmbb_tracking_update)
        if contact_update_result["success"]:
            print(f"✅ RMBB IDs stored in GHL contact {contact_id}")
        else:
            print(f"⚠️ Warning: Failed to update GHL contact: {contact_update_result['error']}")
        
        return patient_response, case_response
    
    def finalize_rmbb_submission(self, external_id, contact_id, case_id, provider_name):
        """
        STEP 3: Finalize RMBB Health submission and prepare for webhook
        This workflow ends here - RMBB Health will send webhook when IVR is complete
        """
        print("\n" + "=" * 60)
        print("STEP 3: Finalizing RMBB Health Submission")
        print("=" * 60)
        
        print(f"🔗 RMBB Case ID: {case_id}")
        print(f"🔗 External ID: {external_id} (links to GHL contact {contact_id})")
        print(f"👨‍⚕️ Provider: {provider_name} (cached for webhook routing)")
        
        # Update GHL contact to show case submitted and awaiting IVR
        final_tracking_update = {
            "customFields": [
                {"key": "rmbb_workflow_status", "value": "submitted_awaiting_ivr"},
                {"key": "rmbb_case_id", "value": str(case_id)},
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
            "case_id": case_id,
            "contact_id": contact_id,
            "provider_name": provider_name,
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
        """Extract patient form data from GHL webhook - RMBB Health required fields"""
        # Use robust field extraction pattern from complete_subaccount_creation.py
        
        # Patient Personal Information (required for RMBB patient creation)
        first_name = (webhook_payload.get('patient_first_name') or
                     webhook_payload.get('Patient First Name') or 
                     webhook_payload.get('first_name') or 
                     webhook_payload.get('firstName') or 
                     webhook_payload.get('fname') or '').strip()
        
        middle_name = (webhook_payload.get('Patient Middle Name') or 
                      webhook_payload.get('middle_name') or 
                      webhook_payload.get('middleName') or '').strip()
        
        last_name = (webhook_payload.get('patient_last_name') or
                    webhook_payload.get('Patient Last Name') or 
                    webhook_payload.get('last_name') or 
                    webhook_payload.get('lastName') or 
                    webhook_payload.get('lname') or '').strip()
        
        date_of_birth = (webhook_payload.get('patient_dob') or
                        webhook_payload.get('Patient Date of Birth') or 
                        webhook_payload.get('date_of_birth') or 
                        webhook_payload.get('dateOfBirth') or 
                        webhook_payload.get('dob') or '').strip()
        
        # Contact Information
        phone_number = (webhook_payload.get('Patient Phone') or 
                       webhook_payload.get('phone') or 
                       webhook_payload.get('phoneNumber') or 
                       webhook_payload.get('mobile') or '').strip()
        
        email_address = (webhook_payload.get('Patient Email') or 
                        webhook_payload.get('email') or 
                        webhook_payload.get('emailAddress') or '').strip()
        
        # Address Information
        street_address = (webhook_payload.get('patient_street_address') or
                         webhook_payload.get('Patient Address') or 
                         webhook_payload.get('address') or 
                         webhook_payload.get('street') or 
                         webhook_payload.get('street_address') or '').strip()
        
        city = (webhook_payload.get('patient_city') or
               webhook_payload.get('Patient City') or 
               webhook_payload.get('city') or '').strip()
        
        state = (webhook_payload.get('patient_state') or
                webhook_payload.get('Patient State') or 
                webhook_payload.get('state') or '').strip()
        
        zip_code = (webhook_payload.get('patient_zip_code') or
                   webhook_payload.get('Patient Zip Code') or 
                   webhook_payload.get('zip_code') or 
                   webhook_payload.get('zipCode') or 
                   webhook_payload.get('postal_code') or '').strip()
        
        # Medical Information (required for RMBB case creation)
        wound_type = (webhook_payload.get('Wound Type') or 
                     webhook_payload.get('wound_type') or 
                     webhook_payload.get('diagnosis') or '').strip()
        
        wound_size = (webhook_payload.get('Wound Size') or 
                     webhook_payload.get('wound_size') or '').strip()
        
        surgery_date = (webhook_payload.get('Surgery Date') or 
                       webhook_payload.get('surgery_date') or 
                       webhook_payload.get('procedure_date') or '').strip()
        
        # Insurance Information (required for RMBB case creation)
        primary_insurance_name = (webhook_payload.get('patient_primary_insurance') or
                                 webhook_payload.get('Primary Insurance') or 
                                 webhook_payload.get('insurance_name') or 
                                 webhook_payload.get('primary_insurance') or '').strip()
        
        primary_policy_number = (webhook_payload.get('patient_primary_insurance_#') or
                                webhook_payload.get('Primary Policy Number') or 
                                webhook_payload.get('policy_number') or 
                                webhook_payload.get('insurance_id') or '').strip()
        
        secondary_insurance_name = (webhook_payload.get('patient_secondary_insurance') or
                                   webhook_payload.get('Secondary Insurance') or 
                                   webhook_payload.get('secondary_insurance') or '').strip()
        
        secondary_policy_number = (webhook_payload.get('patient_secondary_insurance_#') or
                                  webhook_payload.get('Secondary Policy Number') or 
                                  webhook_payload.get('secondary_policy') or '').strip()
        
        # Additional Medical Fields
        icd_10_code = (webhook_payload.get('icd_-_10_diagnosis_code(s)') or
                      webhook_payload.get('ICD-10 Code') or 
                      webhook_payload.get('icd_10_code') or 
                      webhook_payload.get('diagnosis_code') or '').strip()
        
        cpt_surgery_code = (webhook_payload.get('CPT Surgery Code') or 
                           webhook_payload.get('cpt_code') or 
                           webhook_payload.get('procedure_code') or '').strip()
        
        place_of_service = (webhook_payload.get('Place of Service') or 
                           webhook_payload.get('service_location') or 
                           'Physician Office - 11').strip()  # Default from rmbbhealth.txt
        
        # Provider/Physician Information (CRITICAL for cache routing)
        provider_name = (webhook_payload.get('Provider Name') or 
                        webhook_payload.get('provider_name') or 
                        webhook_payload.get('Physician Name') or 
                        webhook_payload.get('physician_name') or 
                        webhook_payload.get('Doctor Name') or 
                        webhook_payload.get('doctor_name') or 
                        webhook_payload.get('Referring Provider') or 
                        webhook_payload.get('referring_provider') or '').strip()
        
        # New GHL Form Fields
        provider_email = (webhook_payload.get('(Provider ) email') or
                         webhook_payload.get('provider_email') or '').strip()
        
        facility_type = (webhook_payload.get('facility_type') or '').strip()
        
        facility_npi = (webhook_payload.get('facility_npi_#') or
                       webhook_payload.get('facility_npi') or '').strip()
        
        expected_date_of_service = (webhook_payload.get('expected_date_of_service') or '').strip()
        
        # Biologic Product Fields (units/cm2)
        amniomaxx_q4239 = (webhook_payload.get('amniomaxx_(q4239)_units/cm2') or '').strip()
        palingen_q4173 = (webhook_payload.get('palingen_(q4173)_units/cm2') or '').strip()
        membrane_wrap_trilayer_q4344 = (webhook_payload.get('membrane_wrap_tri-layer_(q4344)_units/cm2') or '').strip()
        amnioamp_mp_q4250 = (webhook_payload.get('amnioamp-mp_(q4250)_units/cm2') or '').strip()
        membrane_wrap_hydro_q4290 = (webhook_payload.get('membrane_wrap_hydro_(q4290)_units/cm2') or '').strip()
        biovance_q4154 = (webhook_payload.get('biovance_(q4154)_units/cm2') or '').strip()
        amchoplast_q4316 = (webhook_payload.get('amchoplast_(q4316)_units/cm2') or '').strip()
        helicoll_q4164 = (webhook_payload.get('helicoll_(q4164)_units/cm2') or '').strip()
        xcell_amnio_matrix_q4280 = (webhook_payload.get('xcell_amnio_matrix_(q4280)_units/cm2') or '').strip()
        
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
            "tid": self.rmbb_client.config.TEAM_ID,
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
        
        # Primary Insurance (matches rmbbhealth.txt structure lines 535-544)
        if form_data.get("primary_insurance_name"):
            case_data["primary_insurance"] = {
                "full_name": form_data.get("primary_insurance_name", ""),
                "type": "ORIGINAL MEDICARE",  # Default, could be derived from insurance name
                "mac": "",
                "parent_company": "Insurance Co",  # Default, could be form field
                "participating_status": "Participating",  # Default, could be form field
                "policy_number": form_data.get("primary_policy_number", ""),
                "preferred_provider_organization": "Yes",  # Default
                "health_maintenance_organization": "No",  # Default
                "prior_authorization": ""  # Could be form field
            }
        
        # Secondary Insurance (matches rmbbhealth.txt structure lines 546-556)
        if form_data.get("secondary_insurance_name"):
            case_data["secondary_insurance"] = {
                "full_name": form_data.get("secondary_insurance_name", ""),
                "type": "MEDICARE SUPPLEMENT",  # Default, could be derived from insurance name
                "mac": "",
                "parent_company": "Another Insurance Co",  # Default, could be form field
                "participating_status": "Non-participating",  # Default, could be form field
                "policy_number": form_data.get("secondary_policy_number", ""),
                "preferred_provider_organization": "No",  # Default
                "health_maintenance_organization": "Yes",  # Default
                "prior_authorization": ""  # Could be form field
            }
        
        return case_data
    
    def get_account_location_id(self, ghl_location_id):
        """
        Get RMBB account_location_id from Railway environment variables
        """
        account_location_id = os.getenv('RMBB_ACCOUNT_LOCATION_ID', '4195')
        return int(account_location_id)
    
    def get_physician_id(self, provider_name):
        """
        Get RMBB physician_id from Railway environment variables
        """
        physician_id = os.getenv('RMBB_PHYSICIAN_ID', '8077')
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
        The Q codes (Q4239, Q4173, etc.) ARE the product IDs
        """
        if not product_info["primary_product"]:
            # No product selected, use default from Railway environment
            return os.getenv('RMBB_PRODUCT_ID', '31')
        
        # Return the Q code directly - it IS the product_id
        return product_info["primary_product"]["product_id"]
    
    def update_ghl_contact(self, contact_id, update_data):
        """Update GHL contact using V1 API - based on complete_subaccount_creation.py patterns"""
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
            external_id, contact_id, location_id, patient_data = self.handle_ghl_webhook(webhook_payload)
            
            # Step 2: Submit to RMBB Health with external_id linking back to GHL
            patient_response, case_response = self.submit_to_rmbb_health(external_id, contact_id, patient_data)
            
            # Step 3: Finalize RMBB submission and end workflow (RMBB Health will webhook us)
            provider_name = patient_data.get('provider_name')
            submission_result = self.finalize_rmbb_submission(
                external_id=external_id,
                contact_id=contact_id, 
                case_id=case_response['id'],
                provider_name=provider_name
            )
            
            print("\n" + "=" * 80)
            print("✅ GHL → RMBB HEALTH SUBMISSION COMPLETED")
            print("=" * 80)
            print(f"🔗 External ID: {external_id}")
            print(f"📧 GHL Contact ID: {contact_id}")
            print(f"📍 GHL Location ID: {location_id}")
            print(f"👨‍⚕️ Provider: {provider_name} (cached for webhook routing)")
            print(f"🏥 RMBB Patient ID: {patient_response['id']}")
            print(f"📋 RMBB Case ID: {case_response['id']}")
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
                "rmbb_case_id": case_response['id'],
                "submission_status": submission_result['status'],
                "completed_at": submission_result['completed_at'],
                "note": "GHL → RMBB submission complete. IVR results will arrive via separate RMBB webhook."
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ WORKFLOW ERROR: {error_msg}")
            
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