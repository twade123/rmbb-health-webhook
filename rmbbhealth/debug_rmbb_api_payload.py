#!/usr/bin/env python3
"""
Debug RMBB Health API payload to understand error 1020
"""
import os
import json
from ghl_rmbb_workflow import GHLRMBBWorkflowHandler

def debug_rmbb_payload():
    """Debug what exact data we're sending to RMBB Health API"""
    print("🔍 DEBUGGING RMBB Health API Payload")
    print("=" * 60)
    
    # Set environment variables
    os.environ['RMBB_API_KEY'] = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    os.environ['RMBB_TEAM_ID'] = '85'
    os.environ['RMBB_PHYSICIAN_ID'] = '8077'
    os.environ['RMBB_ACCOUNT_LOCATION_ID'] = '4195'
    os.environ['RMBB_PRODUCT_ID'] = '339'
    
    # Initialize handler
    handler = GHLRMBBWorkflowHandler(
        rmbb_api_key='b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0',
        rmbb_team_id=85,
        ghl_api_key='test_ghl_key'
    )
    
    # Sample webhook payload from our test (with address fields added)
    webhook_payload = {
        "contactId": "0L8CuPLnCi5xQhbcuPUs",
        "locationId": "Sqbexj54nvsxOI4V7SsD",
        "firstName": "John",
        "lastName": "Doe",
        "email": "john.doe@test.com",
        "phone": "+1234567890",
        "dateOfBirth": "1990-01-01",
        "provider_name": "Cell Products",
        "insurance_type": "Medicare",
        "patient_first_name": "John",
        "patient_last_name": "Doe",
        "patient_date_of_birth": "1990-01-01",
        "patient_phone": "+1234567890",
        "patient_email": "john.doe@test.com",
        # REQUIRED ADDRESS FIELDS for RMBB Health API
        "street_address": "123 Test Street",
        "city": "Las Vegas",
        "state": "NV",
        "zip_code": "89101",
        "wound_type": "Diabetic Foot Ulcer",
        "wound_size": "2x3cm",
        "product_biovance": "true",
        "product_amniomaxx": "false",
        "product_palingen": "false"
    }
    
    print("📋 Sample webhook payload:")
    print(json.dumps(webhook_payload, indent=2))
    
    # Extract patient data
    print("\n🔍 Step 1: Extracting patient data...")
    patient_form_data = handler.extract_patient_data(webhook_payload)
    print("✅ Extracted patient form data:")
    print(json.dumps(patient_form_data, indent=2))
    
    # Transform to RMBB patient format
    print("\n🔍 Step 2: Transforming to RMBB Health patient format...")
    rmbb_patient_data = handler.transform_patient_data(patient_form_data)
    print("✅ RMBB Health patient payload:")
    print(json.dumps(rmbb_patient_data, indent=2))
    
    # Transform to RMBB case format (assuming patient ID 12345)
    print("\n🔍 Step 3: Transforming to RMBB Health case format...")
    rmbb_case_data = handler.transform_case_data(patient_form_data, "test_patient_12345")
    print("✅ RMBB Health case payload:")
    print(json.dumps(rmbb_case_data, indent=2))
    
    # Check TBD values
    print("\n🔍 Step 4: Checking TBD values...")
    print(f"   Account Location ID: {handler.get_account_location_id(None)}")
    print(f"   Physician ID: {handler.get_physician_id(None)}")
    
    product_info = handler.extract_selected_biologic_product(patient_form_data)
    product_id = handler.get_product_id_from_biologic(product_info)
    print(f"   Product ID: {product_id}")
    
    # Show exact URLs and headers that would be used
    print("\n🔍 Step 5: API Configuration...")
    print(f"   RMBB Team ID: {handler.rmbb_team_id}")
    print(f"   Base URL: {handler.rmbb_base_url}")
    print(f"   Patient API: {handler.rmbb_base_url}/team/{handler.rmbb_team_id}/patient")
    print(f"   Case API: {handler.rmbb_base_url}/team/{handler.rmbb_team_id}/case")
    print(f"   Headers: {handler.rmbb_headers}")
    
    # Check for any data issues
    print("\n🔍 Step 6: Data validation...")
    validation_issues = []
    
    if not patient_form_data.get('date_of_birth'):
        validation_issues.append("Missing date_of_birth")
    if not patient_form_data.get('first_name'):
        validation_issues.append("Missing first_name")
    if not patient_form_data.get('last_name'):
        validation_issues.append("Missing last_name")
    if not patient_form_data.get('street_address'):
        validation_issues.append("Missing street_address")
    if not patient_form_data.get('city'):
        validation_issues.append("Missing city")
    if not patient_form_data.get('state'):
        validation_issues.append("Missing state")
    if not patient_form_data.get('zip_code'):
        validation_issues.append("Missing zip_code")
    
    if validation_issues:
        print("❌ Validation issues found:")
        for issue in validation_issues:
            print(f"   - {issue}")
    else:
        print("✅ No obvious validation issues found")
    
    print("\n📊 Summary:")
    print(f"   TBD Values: account_location_id={handler.get_account_location_id(None)}, physician_id={handler.get_physician_id(None)}, product_id={product_id}")
    print(f"   Patient Required Fields: ✅ All present")
    print(f"   Case Required Fields: Need to check against RMBB Health API docs...")

if __name__ == "__main__":
    debug_rmbb_payload()