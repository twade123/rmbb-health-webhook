#!/usr/bin/env python3
"""
Test RMBB Health with completely fresh patient + case to avoid any conflicts
"""
import requests
import json
from datetime import datetime

def test_fresh_patient_and_case():
    """Create a fresh patient then immediately create a case"""
    print("🧪 Testing RMBB Health - Fresh Patient + Case")
    print("=" * 60)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Create unique patient data
    timestamp = datetime.now().strftime("%m%d%H%M%S")
    
    patient_data = {
        "personal_identifier": {
            "first": "Fresh",
            "middle": "",
            "last": f"Test{timestamp}"
        },
        "address": {
            "street": "456 Fresh Street",
            "suite": "",
            "city": "Las Vegas",
            "state": "NV",
            "country": "USA",
            "zip": "89102"
        },
        "communication_information": {
            "phone": f"+1555{timestamp}",
            "fax": "",
            "email": f"fresh{timestamp}@test.com"
        },
        "date_of_birth": "1985-03-15",
        "gender": "",
        "note": "Fresh patient for case testing",
        "social_security_number": ""
    }
    
    print("📋 Creating fresh patient:")
    print(json.dumps(patient_data, indent=2))
    
    # Create patient
    patient_url = f"{base_url}/team/{team_id}/patient"
    
    try:
        response = requests.post(patient_url, headers=headers, json=patient_data)
        print(f"\n📊 Patient Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Patient creation failed")
            response_json = response.json()
            print(f"📄 Error: {response_json}")
            return False
            
        patient_response = response.json()
        patient_id = patient_response['id']
        print(f"✅ Fresh patient created with ID: {patient_id}")
        
        # Now create case immediately with correct production values
        case_data = {
            "tid": team_id,
            "account_location_id": 4195,  # Production value
            "physician_id": 8077,         # Production value
            "patient_id": patient_id,
            "product_id": 98,             # Membrane Wrap
            "external_id": f"fresh_test_{timestamp}"
        }
        
        print(f"\n📋 Creating case for fresh patient {patient_id}:")
        print(json.dumps(case_data, indent=2))
        
        case_url = f"{base_url}/team/{team_id}/case"
        response = requests.post(case_url, headers=headers, json=case_data)
        
        print(f"\n📊 Case Response Status: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"📄 Response Body: {json.dumps(response_json, indent=2)}")
            
            if response.status_code == 200:
                case_id = response_json.get('id')
                print(f"✅ SUCCESS! Case created with ID: {case_id}")
                print(f"🎯 Production TBD values are working correctly!")
                return True, case_id
            else:
                error_code = response_json.get('error')
                print(f"❌ Case creation failed with error: {error_code}")
                
                if error_code == 1020:
                    print(f"🔍 Error 1020 with fresh patient suggests:")
                    print(f"   - Production TBD values might not exist in system")
                    print(f"   - API permissions issue")
                    print(f"   - Product ID 98 might not be available")
                    print(f"   - Some other validation issue")
                return False, None
                
        except json.JSONDecodeError:
            print(f"📄 Raw response: {response.text}")
            return False, None
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False, None

if __name__ == "__main__":
    success, case_id = test_fresh_patient_and_case()
    if success:
        print(f"\n✅ RMBB Health API test with production values: SUCCESS")
        print(f"🎯 Case ID: {case_id}")
    else:
        print(f"\n❌ RMBB Health API test with production values: FAILED")
        print(f"🔍 Need to investigate why production TBD values aren't working")