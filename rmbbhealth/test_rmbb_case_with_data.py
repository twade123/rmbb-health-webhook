#!/usr/bin/env python3
"""
Test RMBB Health case creation with populated required fields
"""
import os
import sys
import json
import requests

def test_rmbb_case_with_required_fields():
    """Test RMBB Health case creation with all required fields populated"""
    print("🧪 Testing RMBB Health Case API with Required Fields")
    print("=" * 60)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Use patient ID from successful creation
    patient_id = 47104
    
    # Case data with POPULATED required fields based on webhook data
    case_data = {
        "tid": team_id,
        "account_location_id": 4195,
        "physician_id": 8077,
        "patient_id": patient_id,
        "product_id": 98,  # Membrane Wrap (known good product ID)
        "external_id": "test_external_id_with_fields_456",
        # POPULATED FIELDS (instead of empty strings)
        "place_of_service": "Physician Office - 11",
        "wound_size": "2x3cm",
        "total_wound_size": "6 cm2",
        "wound_type": "Diabetic Foot Ulcer",
        "is_in_skilled_nursing_facility": 0,
        "is_in_surgical_nursing_facility": 0,
        "cpt_surgery_code": "11042",  # Common debridement code
        "surgery_date": "2025-08-26",  # Today's date
        "icd_10_code": "E11.621",  # Type 2 diabetes with foot ulcer
        "product_cpt_code": "15271-8"  # Skin substitute application
    }
    
    print("📋 Case data with required fields:")
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
                case_id = response_json.get('id')
                print(f"🎯 Case ID: {case_id}")
                return True, case_id
            else:
                print(f"❌ Case creation failed: {response.status_code}")
                if 'error' in response_json:
                    print(f"🔍 Error code: {response_json['error']}")
                return False, None
                
        except json.JSONDecodeError:
            print(f"📄 Response Body (raw): {response.text}")
            return False, None
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False, None

if __name__ == "__main__":
    success, case_id = test_rmbb_case_with_required_fields()
    if success:
        print(f"\n✅ RMBB Health case creation: SUCCESS with case ID {case_id}")
    else:
        print(f"\n❌ RMBB Health case creation: FAILED")
    sys.exit(0 if success else 1)