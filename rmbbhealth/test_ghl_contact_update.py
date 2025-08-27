#!/usr/bin/env python3
"""
Test GHL Contact Update with Provider Cache Data - REAL TEST
Tests the complete flow using actual rmbbhealth functions:
case lookup → routing data → GHL API call → contact update
"""

import json
import sys
import os

def test_ghl_contact_update():
    """
    Test updating GHL contact using provider cache routing data and REAL rmbbhealth functions
    """
    print("🧪 TESTING: GHL Contact Update via Provider Cache - REAL TEST")
    print("=" * 70)
    
    try:
        # Import the provider cache
        from services.provider_location_cache import get_provider_cache
        
        # Import the actual webhook handler function we'll use in production
        from webhook_handler import update_ghl_contact_direct
        
        # Get the provider cache instance
        provider_cache = get_provider_cache()
        print("✅ Successfully imported provider cache and webhook handler")
        
        # Test case lookup for case 53330
        case_id = "53330"
        print(f"\n🔍 Looking up case mapping for case_id: {case_id}")
        
        case_mapping = provider_cache.get_case_mapping(case_id)
        
        if not case_mapping:
            print(f"❌ NO CASE MAPPING FOUND for case_id: {case_id}")
            return False
            
        print(f"✅ CASE MAPPING FOUND:")
        contact_id = case_mapping.get('contact_id')
        location_id = case_mapping.get('location_id')
        provider_name = case_mapping.get('provider_name')
        external_id = case_mapping.get('external_id')
        
        print(f"   👨‍⚕️ Provider: {provider_name}")
        print(f"   📧 Contact ID: {contact_id}")
        print(f"   📍 Location ID: {location_id}")
        print(f"   🔗 External ID: {external_id}")
        
        # Get API key for the location
        if location_id:
            print(f"\n🔑 Looking up API key for location_id: {location_id}")
            api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
            
            if not api_key:
                print(f"❌ No API key found for location_id: {location_id}")
                return False
                
            print(f"✅ API KEY FOUND: {api_key[:20]}...{'*' * 20}")
            
            # Mock RMBBHealth status update data - using actual field names that would come from RMBBHealth
            status_data = {
                "status": "approved",
                "external_status": "qualified", 
                "overall_insurance_result": "approved",
                "primary_insurance_status": "verified",
                "secondary_insurance_status": "not_applicable",
                "tertiary_insurance_status": "not_applicable",
                "primary_insurance_result": "approved",
                "secondary_insurance_result": "n/a",
                "case_id": case_id
            }
            
            print(f"\n📋 Mock RMBBHealth Status Data:")
            for key, value in status_data.items():
                print(f"      {key}: {value}")
            
            # Create custom fields update using the CORRECT GHL field format
            custom_fields_update = {
                "customField": [
                    {"id": "k9onZaMZVJ5Zwlopf2fi", "value": "status_received"},  # rmbb_workflow_status
                    {"id": "4AnL32P9rjYcPjbukcok", "value": "2025-08-27T18:55:00Z"},  # rmbb_ivr_received_date
                    {"id": "drfCODR4HhoKeI3eoH6J", "value": "true"},  # rmbb_webhook_processed
                    {"id": "A2gqU59iygkmxwUeO2j6", "value": status_data["status"]},  # rmbb_case_status
                    {"id": "b7odVJaRBRTBQlVaUCF1", "value": status_data["external_status"]},  # rmbb_external_status
                    {"id": "NStZu6i6cSflIhmRS7Eg", "value": status_data["overall_insurance_result"]},  # rmbb_overall_result
                    {"id": "lek4SmWzewBgvrAXBLWy", "value": status_data["primary_insurance_status"]},  # rmbb_primary_insurance_status
                    {"id": "vnZmPnf00xi9ImOLxao9", "value": status_data["secondary_insurance_status"]},  # rmbb_secondary_insurance_status
                    {"id": "JeBBYNNHOWqyYU5FMA1w", "value": status_data["tertiary_insurance_status"]},  # rmbb_tertiary_insurance_status
                    {"id": "tXkwLnHu00e9t2MdGarP", "value": status_data["primary_insurance_result"]},  # rmbb_primary_insurance_result
                    {"id": "0viEC6QFPlBZIm75N0fE", "value": status_data["secondary_insurance_result"]}  # rmbb_secondary_insurance_result
                ]
            }
            
            print(f"\n🚀 CALLING REAL WEBHOOK HANDLER FUNCTION:")
            print(f"   📍 Location: {location_id}")
            print(f"   👤 Contact: {contact_id}")
            print(f"   🔑 API Key: {api_key[:20]}...{'*' * 20}")
            print(f"   📋 Custom Fields: {len(custom_fields_update['customField'])} fields")
            print(f"   🏷️ Field IDs: {[field['id'] for field in custom_fields_update['customField']]}")
            
            # Call the actual function that will be used in production
            result = update_ghl_contact_direct(
                contact_id=contact_id,
                location_id=location_id,
                sub_account_api_key=api_key,
                custom_fields_update=custom_fields_update
            )
            
            print(f"\n📊 WEBHOOK HANDLER RESULT:")
            print(f"   📈 Success: {result.get('success', False)}")
            
            if result.get('success'):
                print(f"   ✅ SUCCESS: Contact updated successfully using REAL webhook handler!")
                print(f"   📋 Updated GHL contact with correct field IDs:")
                for field in custom_fields_update['customField']:
                    print(f"      🆔 {field['id']}: {field['value']}")
                
                if 'data' in result:
                    print(f"   📋 GHL Response Data: {json.dumps(result['data'], indent=2)}")
                return True
            else:
                print(f"   ❌ ERROR: {result.get('error', 'Unknown error')}")
                return False
        
        else:
            print(f"❌ No location_id found in case mapping")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_ghl_contact_update()
    
    if success:
        print(f"\n🎉 SUCCESS: Complete flow working with CORRECT GHL field names!")
        print(f"   1. ✅ Found case 53330 in provider cache")
        print(f"   2. ✅ Retrieved routing data (contact_id, location_id, API key)")
        print(f"   3. ✅ Called real webhook handler function")
        print(f"   4. ✅ Updated contact with CORRECT field names:")
        print(f"      - Rmbb_workflow_status")
        print(f"      - Rmbb_ivr_received_date") 
        print(f"      - Rmbb_webhook_processed")
        print(f"      - Rmbb_case_status")
        print(f"      - Rmbb_external_status")
        print(f"      - Rmbb_overall_result")
        print(f"      - Rmbb_primary_insurance_status")
        print(f"      - Rmbb_secondary_insurance_status")
        print(f"      - Rmbb_tertiary_insurance_status")
        print(f"      - Rmbb_primary_insurance_result")
        print(f"      - Rmbb_secondary_insurance_result")
        print(f"\n🚀 Ready for RMBBHealth webhook integration with correct field mapping!")
    else:
        print(f"\n❌ FAILURE: Issues with GHL API call")
        print(f"🔧 Check API key permissions and contact ID validity")