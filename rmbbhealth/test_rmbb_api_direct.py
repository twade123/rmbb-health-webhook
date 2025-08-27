#!/usr/bin/env python3
"""
Test RMBB Health API directly to get detailed error information
"""
import os
import sys
import json
import requests

def test_rmbb_patient_creation():
    """Test RMBB Health patient creation directly"""
    print("🧪 Testing RMBB Health Patient API Directly")
    print("=" * 60)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Patient data (exactly what our workflow generates)
    patient_data = {
        "personal_identifier": {
            "first": "John",
            "middle": "",
            "last": "Doe"
        },
        "address": {
            "street": "123 Test Street",
            "suite": "",
            "city": "Las Vegas",
            "state": "NV",
            "country": "USA",
            "zip": "89101"
        },
        "communication_information": {
            "phone": "+1234567890",
            "fax": "",
            "email": "john.doe@test.com"
        },
        "date_of_birth": "1990-01-01",
        "gender": "",
        "note": "Patient from GHL form submission",
        "social_security_number": ""
    }
    
    print("📋 Patient data to be sent:")
    print(json.dumps(patient_data, indent=2))
    
    # Try patient creation
    patient_url = f"{base_url}/team/{team_id}/patient"
    print(f"\n🔗 POST {patient_url}")
    print(f"🔑 Headers: {headers}")
    
    try:
        response = requests.post(patient_url, headers=headers, json=patient_data)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📄 Response Headers: {dict(response.headers)}")
        
        try:
            response_json = response.json()
            print(f"📄 Response Body: {json.dumps(response_json, indent=2)}")
            
            if response.status_code == 200:
                print("✅ Patient creation successful!")
                patient_id = response_json.get('id')
                
                # Now test case creation
                print(f"\n🔍 Testing case creation with patient_id: {patient_id}")
                return test_rmbb_case_creation(patient_id, headers, base_url, team_id)
            else:
                print(f"❌ Patient creation failed: {response.status_code}")
                return False
                
        except json.JSONDecodeError:
            print(f"📄 Response Body (raw): {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False

def test_rmbb_case_creation(patient_id, headers, base_url, team_id):
    """Test RMBB Health case creation"""
    print(f"\n🧪 Testing RMBB Health Case API")
    print("=" * 60)
    
    # Case data (exactly what our workflow generates)
    case_data = {
        "tid": team_id,
        "account_location_id": 4195,
        "physician_id": 8077,
        "patient_id": patient_id,
        "product_id": 339,
        "external_id": "test_external_id_123",
        "place_of_service": "",
        "wound_size": "",
        "total_wound_size": "",
        "wound_type": "",
        "is_in_skilled_nursing_facility": 0,
        "is_in_surgical_nursing_facility": 0,
        "cpt_surgery_code": "",
        "surgery_date": "",
        "icd_10_code": "",
        "product_cpt_code": ""
    }
    
    print("📋 Case data to be sent:")
    print(json.dumps(case_data, indent=2))
    
    # Try case creation
    case_url = f"{base_url}/team/{team_id}/case"
    print(f"\n🔗 POST {case_url}")
    
    try:
        response = requests.post(case_url, headers=headers, json=case_data)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📄 Response Headers: {dict(response.headers)}")
        
        try:
            response_json = response.json()
            print(f"📄 Response Body: {json.dumps(response_json, indent=2)}")
            
            if response.status_code == 200:
                print("✅ Case creation successful!")
                return True
            else:
                print(f"❌ Case creation failed: {response.status_code}")
                if response.status_code == 1020:
                    print("🔍 This is the error 1020 we've been seeing!")
                return False
                
        except json.JSONDecodeError:
            print(f"📄 Response Body (raw): {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False

if __name__ == "__main__":
    success = test_rmbb_patient_creation()
    if success:
        print(f"\n✅ RMBB Health API test: PASSED")
    else:
        print(f"\n❌ RMBB Health API test: FAILED - This shows us the exact error")
    sys.exit(0 if success else 1)