#!/usr/bin/env python3
"""
Get GHL Field ID to Name Mapping
This will help us find the correct field IDs for our RMBB status fields
"""

import json
import requests
import sys
import os

def get_ghl_field_mapping():
    """
    Get the field mapping from GHL to find the correct field IDs for our RMBB fields
    """
    print("🔍 GETTING: GHL Field ID to Name Mapping")
    print("=" * 60)
    
    try:
        # Import the provider cache
        from services.provider_location_cache import get_provider_cache
        
        # Get the provider cache instance
        provider_cache = get_provider_cache()
        case_mapping = provider_cache.get_case_mapping("53330")
        
        contact_id = case_mapping.get('contact_id')
        location_id = case_mapping.get('location_id')
        api_key = provider_cache.get_sub_account_api_key_by_location_id(location_id)
        
        print(f"📧 Contact ID: {contact_id}")
        print(f"📍 Location ID: {location_id}")
        
        # Get the location's custom field definitions
        print(f"\n📡 GETTING CUSTOM FIELD DEFINITIONS:")
        
        # First, try to get custom fields from the location endpoint
        fields_url = f"https://rest.gohighlevel.com/v1/custom-fields/"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        print(f"   🔗 URL: {fields_url}")
        
        response = requests.get(fields_url, headers=headers, timeout=30)
        
        print(f"   📈 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            fields_data = response.json()
            print(f"   ✅ SUCCESS: Custom field definitions retrieved!")
            
            # Look for our RMBB fields - ALL LOWERCASE
            rmbb_field_names = [
                'rmbb_workflow_status',
                'rmbb_ivr_received_date', 
                'rmbb_webhook_processed',
                'rmbb_case_status',
                'rmbb_external_status',
                'rmbb_overall_result',
                'rmbb_primary_insurance_status',
                'rmbb_secondary_insurance_status',
                'rmbb_tertiary_insurance_status',
                'rmbb_primary_insurance_result',
                'rmbb_secondary_insurance_result'
            ]
            
            print(f"\n🔍 SEARCHING FOR RMBB FIELDS (lowercase):")
            found_mappings = {}
            
            if 'customFields' in fields_data:
                for field in fields_data['customFields']:
                    field_name = field.get('name', '')
                    field_id = field.get('id', '')
                    if field_name in rmbb_field_names:
                        found_mappings[field_name] = field_id
                        print(f"   ✅ {field_name} → {field_id}")
            
            if not found_mappings:
                print(f"   ❌ No RMBB fields found in custom field definitions")
                print(f"   📋 Available fields (first 10):")
                if 'customFields' in fields_data:
                    for i, field in enumerate(fields_data['customFields'][:10]):
                        print(f"      {i+1}. {field.get('name', 'no_name')} → {field.get('id', 'no_id')}")
                else:
                    print(f"   📋 Response structure: {list(fields_data.keys())}")
            
            return found_mappings
            
        else:
            print(f"   ❌ ERROR: HTTP {response.status_code}")
            print(f"   📄 Response: {response.text}")
            
            # Try alternative approach - get all contacts fields to find patterns
            print(f"\n🔄 TRYING ALTERNATIVE: Check if fields exist in other contacts")
            
            # This might give us insight into field structure
            contacts_url = f"https://rest.gohighlevel.com/v1/contacts/"
            contacts_response = requests.get(contacts_url, headers=headers, timeout=30)
            
            if contacts_response.status_code == 200:
                contacts_data = contacts_response.json()
                print(f"   ✅ Got contacts data")
                
                if 'contacts' in contacts_data and len(contacts_data['contacts']) > 0:
                    sample_contact = contacts_data['contacts'][0]
                    if 'customField' in sample_contact:
                        print(f"   📋 Sample contact custom fields:")
                        for i, field in enumerate(sample_contact['customField'][:5]):
                            print(f"      {i+1}. ID: {field.get('id')} Value: {field.get('value')}")
            
            return {}
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return {}

if __name__ == "__main__":
    field_mappings = get_ghl_field_mapping()
    
    if field_mappings:
        print(f"\n🎉 SUCCESS: Found {len(field_mappings)} RMBB field mappings!")
        print(f"📋 Field ID Mappings:")
        for field_name, field_id in field_mappings.items():
            print(f"   '{field_name}': '{field_id}',")
    else:
        print(f"\n❌ No RMBB field mappings found")
        print(f"💡 The fields might not exist yet in GHL - they may need to be created first")