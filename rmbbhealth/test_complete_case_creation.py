#!/usr/bin/env python3
"""
Test case creation with complete required fields from RMBB Health documentation
"""
import requests
import json

def create_patient_first():
    """Create a fresh patient for testing"""
    print("🏥 Creating Fresh Patient")
    print("=" * 50)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Patient data with correct field names from documentation
    patient_data = {
        "personal_identifier": {
            "first": "Test",
            "middle": "",
            "last": "Patient"
        },
        "address": {
            "street": "123 Test Street",
            "suite": "",
            "city": "Las Vegas",
            "state": "NV",
            "country": "US",
            "zip": "89101"
        },
        "communication_information": {
            "phone": "7025551234",
            "fax": "",
            "email": "test@example.com"
        },
        "date_of_birth": "1980-01-01",
        "social_security_number": "123456789",
        "gender": "Male",
        "ethnicity": "Hispanic or Latino",
        "race": "White",
        "external_id": f"complete_test_patient_{int(__import__('time').time())}",
        "tid": team_id,
        "account_location_id": 4195,
        "physician_id": 8077
    }
    
    patient_url = f"{base_url}/team/{team_id}/patient"
    print(f"🔗 POST {patient_url}")
    
    try:
        response = requests.post(patient_url, headers=headers, json=patient_data)
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                patient = response.json()
                patient_id = patient.get('id')
                print(f"✅ Patient created successfully! ID: {patient_id}")
                return patient_id
            except json.JSONDecodeError:
                print(f"📄 Raw response: {response.text}")
                return None
        else:
            try:
                error = response.json()
                print(f"❌ Patient creation failed: {error}")
            except:
                print(f"❌ Error (raw): {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return None

def create_case_with_complete_fields(patient_id):
    """Create case with complete required fields from documentation"""
    print(f"\n🧪 Creating Case with Complete Required Fields")
    print(f"Patient ID: {patient_id}")
    print("=" * 50)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Complete case data with EXACT format from documentation
    case_data = {
        "tid": team_id,
        "account_location_id": 4195,
        "physician_id": 8077,
        "patient_id": patient_id,
        "product_id": 339,
        "external_id": f"complete_test_case_{int(__import__('time').time())}",
        "place_of_service": "Physician Office - 11",
        "wound_size": "3x4 cm",
        "total_wound_size": "12 cm2",
        "wound_type": "Diabetic Ulcer",
        "is_in_skilled_nursing_facility": 1,
        "is_in_surgical_nursing_facility": 0,
        "cpt_surgery_code": "12345",
        "surgery_date": "2023-04-01",
        "icd_10_code": "E11.621",
        "product_cpt_code": "67890",
        "primary_insurance": {
            "full_name": "MEDICARE PART B",
            "type": "ORIGINAL MEDICARE",
            "mac": "",
            "parent_company": "Insurance Co",
            "participating_status": "Participating",
            "policy_number": "POL123456",
            "preferred_provider_organization": "Yes",
            "health_maintenance_organization": "No",
            "prior_authorization": "Auth123"
        },
        "secondary_insurance": {
            "full_name": "AARP MEDICARE SUPPLEMENT PLAN F",
            "type": "MEDICARE SUPPLEMENT",
            "mac": "",
            "parent_company": "Another Insurance Co",
            "participating_status": "Non-participating",
            "policy_number": "POL654321",
            "preferred_provider_organization": "No",
            "health_maintenance_organization": "Yes",
            "prior_authorization": "Auth456"
        }
    }
    
    print(f"📋 Complete case data:")
    print(json.dumps(case_data, indent=2))
    
    case_url = f"{base_url}/team/{team_id}/case"
    print(f"\n🔗 POST {case_url}")
    
    try:
        response = requests.post(case_url, headers=headers, json=case_data)
        print(f"\n📊 Response Status: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"📄 Response Body:")
            print(json.dumps(response_json, indent=2))
            
            if response.status_code == 200:
                case_id = response_json.get('id')
                print(f"\n✅ SUCCESS! Case created with ID: {case_id}")
                return True, case_id
            else:
                error_code = response_json.get('error', 'Unknown')
                print(f"\n❌ Case creation failed with error: {error_code}")
                
                # Show which fields might be missing
                if error_code == 1020:
                    print(f"💡 Error 1020 typically means validation failed")
                    print(f"💡 Check if all required fields are valid")
                elif error_code == 1010:
                    print(f"💡 Error 1010 typically means missing required fields")
                    
                return False, None
                
        except json.JSONDecodeError:
            print(f"📄 Raw response: {response.text}")
            return False, None
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False, None

if __name__ == "__main__":
    print("🚀 Testing Complete RMBB Health Case Creation")
    print("=" * 60)
    
    # Step 1: Create a fresh patient
    patient_id = create_patient_first()
    
    if patient_id:
        # Step 2: Create case with all required fields
        success, case_id = create_case_with_complete_fields(patient_id)
        
        if success:
            print(f"\n🎉 COMPLETE SUCCESS!")
            print(f"✅ Patient ID: {patient_id}")
            print(f"✅ Case ID: {case_id}")
            print(f"🎯 All required fields working correctly!")
        else:
            print(f"\n❌ Case creation failed even with complete fields")
            print(f"✅ Patient created: {patient_id}")
            print(f"❌ Case creation: Failed")
    else:
        print(f"\n❌ Could not create patient - cannot test case creation")