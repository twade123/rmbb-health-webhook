#!/usr/bin/env python3
"""
Test Direct GHL API Call to verify the correct custom field format
"""

import json
import requests

def test_direct_ghl_api():
    """
    Test a direct GHL API call to see exactly what format works
    """
    print("🧪 TESTING: Direct GHL API Call")
    print("=" * 50)
    
    try:
        # Import the provider cache
        from services.provider_location_cache import get_provider_cache
        
        provider_cache = get_provider_cache()
        case_mapping = provider_cache.get_case_mapping("53330")
        
        contact_id = case_mapping.get('contact_id')
        location_id = case_mapping.get('location_id')
        api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
        
        print(f"📧 Contact ID: {contact_id}")
        print(f"🔑 API Key: {api_key[:20]}...{'*' * 20}")
        
        # Test with just ONE field to make sure the format is right
        url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        # Try with field ID format - using a field that definitely exists
        payload = {
            "customFields": [
                {"id": "2bAsS8HDoo2psDWLJuIC", "value": "UPDATED_VIA_API_TEST"}  # Provider Name field that exists
            ]
        }
        
        print(f"\n📡 TESTING: Field ID format")
        print(f"   🔗 URL: {url}")
        print(f"   📋 Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.put(url, headers=headers, json=payload)
        
        print(f"   📈 Status Code: {response.status_code}")
        print(f"   📄 Response: {response.text}")
        
        if response.status_code == 200:
            print(f"   ✅ SUCCESS: Field ID format works!")
            return True
        else:
            print(f"   ❌ FAILED: Field ID format didn't work")
            
            # Try alternative format with field key/name
            print(f"\n📡 TESTING: Field key format")
            payload_alt = {
                "customFields": [
                    {"key": "rmbb_workflow_status", "value": "test_direct_api_call_key"}
                ]
            }
            
            print(f"   📋 Payload: {json.dumps(payload_alt, indent=2)}")
            
            response_alt = requests.put(url, headers=headers, json=payload_alt)
            
            print(f"   📈 Status Code: {response_alt.status_code}")
            print(f"   📄 Response: {response_alt.text}")
            
            if response_alt.status_code == 200:
                print(f"   ✅ SUCCESS: Field key format works!")
                return True
            else:
                print(f"   ❌ FAILED: Both formats failed")
                return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    test_direct_ghl_api()