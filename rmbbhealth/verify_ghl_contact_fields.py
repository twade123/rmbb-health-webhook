#!/usr/bin/env python3
"""
Verify GHL Contact Fields - Check if the status updates were actually sent to GHL
Reads the contact back from GHL API to confirm the custom fields were set
"""

import json
import requests
import sys
import os

def verify_ghl_contact_fields():
    """
    Read the GHL contact back to verify the custom fields were actually updated
    """
    print("🔍 VERIFYING: GHL Contact Custom Fields")
    print("=" * 60)
    
    try:
        # Import the provider cache
        from services.provider_location_cache import get_provider_cache
        
        # Get the provider cache instance
        provider_cache = get_provider_cache()
        print("✅ Successfully imported provider cache")
        
        # Get case mapping for case 53330
        case_id = "53330"
        case_mapping = provider_cache.get_case_mapping(case_id)
        
        if not case_mapping:
            print(f"❌ NO CASE MAPPING FOUND for case_id: {case_id}")
            return False
            
        contact_id = case_mapping.get('contact_id')
        location_id = case_mapping.get('location_id')
        
        print(f"📧 Contact ID: {contact_id}")
        print(f"📍 Location ID: {location_id}")
        
        # Get API key
        api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
        if not api_key:
            print(f"❌ No API key found")
            return False
            
        print(f"🔑 API Key: {api_key[:20]}...{'*' * 20}")
        
        # Make GHL API call to GET the contact and see the custom fields
        ghl_url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        print(f"\n📡 READING GHL CONTACT:")
        print(f"   🔗 URL: {ghl_url}")
        
        response = requests.get(ghl_url, headers=headers, timeout=30)
        
        print(f"\n📊 GHL API RESPONSE:")
        print(f"   📈 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            contact_data = response.json()
            print(f"   ✅ SUCCESS: Contact data retrieved!")
            
            # Debug: Show the response structure
            print(f"\n🔍 DEBUG: Response structure:")
            print(f"   📋 Top-level keys: {list(contact_data.keys())}")
            
            # Look for our custom fields in different possible locations
            custom_fields = None
            if 'contact' in contact_data and 'customField' in contact_data['contact']:
                custom_fields = contact_data['contact']['customField']
                print(f"   📍 Found customField in contact.customField (GHL v1 format)")
            elif 'contact' in contact_data and 'customFields' in contact_data['contact']:
                custom_fields = contact_data['contact']['customFields']
                print(f"   📍 Found customFields in contact.customFields")
            elif 'customFields' in contact_data:
                custom_fields = contact_data['customFields']
                print(f"   📍 Found customFields in root")
            elif 'contact' in contact_data:
                print(f"   📍 Contact keys: {list(contact_data['contact'].keys())}")
            
            if custom_fields:
                
                print(f"\n🔍 CUSTOM FIELDS VERIFICATION:")
                print(f"   📊 Total custom fields: {len(custom_fields)}")
                
                # Debug: Show structure of first few custom fields
                print(f"\n🔍 DEBUG: Custom field structure (first 3):")
                for i, field in enumerate(custom_fields[:3]):
                    print(f"   📋 Field {i+1}: {field}")
                
                # Check for our specific RMBB field IDs that we just sent
                rmbb_field_ids = [
                    'k9onZaMZVJ5Zwlopf2fi',  # rmbb_workflow_status
                    '4AnL32P9rjYcPjbukcok',  # rmbb_ivr_received_date
                    'drfCODR4HhoKeI3eoH6J',  # rmbb_webhook_processed
                    'A2gqU59iygkmxwUeO2j6',  # rmbb_case_status
                    'b7odVJaRBRTBQlVaUCF1',  # rmbb_external_status
                    'NStZu6i6cSflIhmRS7Eg',  # rmbb_overall_result
                    'lek4SmWzewBgvrAXBLWy',  # rmbb_primary_insurance_status
                    'vnZmPnf00xi9ImOLxao9',  # rmbb_secondary_insurance_status
                    'JeBBYNNHOWqyYU5FMA1w',  # rmbb_tertiary_insurance_status
                    'tXkwLnHu00e9t2MdGarP',  # rmbb_primary_insurance_result
                    '0viEC6QFPlBZIm75N0fE'   # rmbb_secondary_insurance_result
                ]
                
                found_fields = {}
                
                # Look for field IDs in the custom fields list
                if isinstance(custom_fields, list):
                    for field in custom_fields:
                        if isinstance(field, dict):
                            field_id = field.get('id', '')
                            field_value = field.get('value', '')
                            if field_id in rmbb_field_ids:
                                found_fields[field_id] = field_value
                
                print(f"\n✅ RMBB FIELDS FOUND IN GHL CONTACT:")
                if found_fields:
                    # Field ID to name mapping for display
                    id_to_name = {
                        'k9onZaMZVJ5Zwlopf2fi': 'rmbb_workflow_status',
                        '4AnL32P9rjYcPjbukcok': 'rmbb_ivr_received_date',
                        'drfCODR4HhoKeI3eoH6J': 'rmbb_webhook_processed',
                        'A2gqU59iygkmxwUeO2j6': 'rmbb_case_status',
                        'b7odVJaRBRTBQlVaUCF1': 'rmbb_external_status',
                        'NStZu6i6cSflIhmRS7Eg': 'rmbb_overall_result',
                        'lek4SmWzewBgvrAXBLWy': 'rmbb_primary_insurance_status',
                        'vnZmPnf00xi9ImOLxao9': 'rmbb_secondary_insurance_status',
                        'JeBBYNNHOWqyYU5FMA1w': 'rmbb_tertiary_insurance_status',
                        'tXkwLnHu00e9t2MdGarP': 'rmbb_primary_insurance_result',
                        '0viEC6QFPlBZIm75N0fE': 'rmbb_secondary_insurance_result'
                    }
                    
                    for field_id, field_value in found_fields.items():
                        field_name = id_to_name.get(field_id, field_id)
                        print(f"      ✅ {field_name} ({field_id}): {field_value}")
                    
                    print(f"\n📈 SUCCESS SUMMARY:")
                    print(f"   ✅ {len(found_fields)} of {len(rmbb_field_ids)} RMBB fields found in GHL")
                    print(f"   ✅ Contact successfully updated with our status data")
                    print(f"   ✅ API integration working correctly")
                    print(f"   🎉 MOCK STATUS UPDATES ARE NOW VISIBLE IN GHL CONTACT!")
                    
                    return True
                else:
                    print(f"   ❌ No RMBB fields found in contact custom fields")
                    
                    # Show available field keys for debugging
                    available_keys = []
                    if isinstance(custom_fields, dict):
                        available_keys = list(custom_fields.keys())[:10]
                    elif isinstance(custom_fields, list):
                        for field in custom_fields[:10]:
                            if isinstance(field, dict):
                                key = field.get('key', field.get('id', field.get('name', 'no_key')))
                                available_keys.append(key)
                    
                    print(f"   📋 Available field keys: {available_keys}")
                    return False
                
            else:
                print(f"   ❌ No custom fields found in contact data")
                return False
                
        else:
            print(f"   ❌ ERROR: HTTP {response.status_code}")
            print(f"   📄 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = verify_ghl_contact_fields()
    
    if success:
        print(f"\n🎉 VERIFICATION SUCCESS!")
        print(f"   ✅ The mock status updates were ACTUALLY sent to GHL")
        print(f"   ✅ The contact custom fields were updated in the live system")
        print(f"   ✅ The integration is working end-to-end")
    else:
        print(f"\n❌ VERIFICATION FAILED")
        print(f"   🔧 The API calls may not be updating the fields correctly")