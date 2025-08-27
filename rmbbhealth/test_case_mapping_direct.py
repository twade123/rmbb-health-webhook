#!/usr/bin/env python3
"""
Direct test for case mapping fix - bypasses GHL/RMBB API calls to test just the cache mapping logic
"""
import os
import sys
from unittest.mock import Mock, patch

# Mock the RMBB Health API response for successful case creation
def mock_successful_case_creation():
    """Mock RMBB Health services to return successful responses"""
    
    # Mock patient response
    mock_patient_response = {'id': 'test_patient_12345'}
    
    # Mock case response  
    mock_case_response = {'id': 52999}  # Test case ID
    
    return mock_patient_response, mock_case_response

def test_case_mapping_fix():
    """
    Test the case mapping fix directly by mocking successful RMBB responses
    and verifying the case mapping is saved to provider cache
    """
    print("🧪 Testing Case Mapping Fix Directly")
    print("=" * 60)
    
    # Set up test environment
    os.environ['RMBB_API_KEY'] = 'test_key'
    os.environ['RMBB_TEAM_ID'] = '85'
    os.environ['RMBB_PHYSICIAN_ID'] = '8077'
    os.environ['RMBB_ACCOUNT_LOCATION_ID'] = '4195'
    os.environ['RMBB_PRODUCT_ID'] = '339'
    
    # Import after setting environment variables
    from ghl_rmbb_workflow import GHLRMBBWorkflowHandler
    from services.provider_location_cache import get_provider_cache
    
    # Initialize handler
    handler = GHLRMBBWorkflowHandler(
        rmbb_api_key='test_key',
        rmbb_team_id=85,
        ghl_api_key='test_ghl_key'
    )
    
    # Mock patient data
    patient_form_data = {
        'first_name': 'Jane',
        'last_name': 'Test',
        'provider_name': 'Cell Products',
        'date_of_birth': '1985-05-15',
        'street_address': '123 Test St',
        'city': 'Test City',
        'state': 'NV',
        'zip_code': '12345',
        'phone_number': '555-123-4567',
        'email_address': 'jane.test@email.com',
        'primary_insurance_name': 'Test Insurance'
    }
    
    test_contact_id = 'test_contact_mapping_999'
    test_external_id = 'ghl_contact_test_mapping_999_20250826'
    
    print(f"📋 Test Data:")
    print(f"   Contact ID: {test_contact_id}")
    print(f"   External ID: {test_external_id}")
    print(f"   Provider: {patient_form_data['provider_name']}")
    print(f"   Patient: {patient_form_data['first_name']} {patient_form_data['last_name']}")
    
    # Mock the RMBB Health API calls to return successful responses
    with patch.object(handler.patient_service, 'create_patient') as mock_create_patient, \
         patch.object(handler.case_service, 'create_case') as mock_create_case, \
         patch.object(handler, 'upload_additional_case_information') as mock_upload_info:
        
        # Set up mocks for successful responses
        mock_create_patient.return_value = {'id': 'test_patient_12345'}
        mock_create_case.return_value = {'id': 52999}
        mock_upload_info.return_value = {'success': True}
        
        print("\n🔬 Calling submit_to_rmbb_health with mocked successful responses...")
        
        # Call the method that contains our case mapping fix
        result = handler.submit_to_rmbb_health(
            external_id=test_external_id,
            contact_id=test_contact_id, 
            patient_form_data=patient_form_data
        )
        
        print(f"🔍 Result type: {type(result)}")
        print(f"🔍 Result: {result}")
        
        # Check if the result indicates success
        if isinstance(result, tuple) and len(result) == 2:
            patient_response, case_response = result
            case_id = case_response.get('id')
            
            print(f"✅ RMBB Health calls successful!")
            print(f"   Patient ID: {patient_response.get('id')}")
            print(f"   Case ID: {case_id}")
            
            # Now test if the case mapping was saved
            print(f"\n🔍 Checking if case mapping {case_id} was saved to provider cache...")
            
            cache = get_provider_cache()
            case_mapping = cache.get_case_mapping(str(case_id))
            
            if case_mapping:
                print(f"✅ SUCCESS: Case mapping found!")
                print(f"   Case ID: {case_mapping['case_id']}")
                print(f"   Provider: {case_mapping['provider_name']}")
                print(f"   Contact ID: {case_mapping['contact_id']}")
                print(f"   External ID: {case_mapping['external_id']}")
                print(f"\n🎉 CASE MAPPING FIX VERIFIED - Working correctly!")
                return True
            else:
                print(f"❌ FAILURE: Case mapping NOT found for case {case_id}")
                print(f"❌ The case mapping fix is NOT working")
                return False
                
        else:
            print(f"❌ RMBB Health submission failed: {result}")
            return False

if __name__ == "__main__":
    success = test_case_mapping_fix()
    if success:
        print(f"\n✅ Case mapping fix verification: PASSED")
    else:
        print(f"\n❌ Case mapping fix verification: FAILED")
    sys.exit(0 if success else 1)