#!/usr/bin/env python3
"""
Test RMBB Health case creation with minimal fields to isolate the issue
"""
import requests
import json

def test_minimal_case():
    """Test with absolute minimal case data"""
    print("🧪 Testing RMBB Health Case API - Minimal Fields")
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
    
    # Minimal case data - only absolutely required fields
    case_data = {
        "tid": team_id,
        "account_location_id": 4195,
        "physician_id": 8077,
        "patient_id": patient_id,
        "product_id": 98,
        "external_id": "test_minimal_789"
    }
    
    print("📋 Minimal case data:")
    print(json.dumps(case_data, indent=2))
    
    # Try case creation
    case_url = f"{base_url}/team/{team_id}/case"
    print(f"\n🔗 POST {case_url}")
    
    try:
        response = requests.post(case_url, headers=headers, json=case_data)
        print(f"\n📊 Response Status: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"📄 Response Body: {json.dumps(response_json, indent=2)}")
            
            if response.status_code == 200:
                print("✅ Minimal case creation successful!")
                case_id = response_json.get('id')
                print(f"🎯 Case ID: {case_id}")
                return True
            else:
                print(f"❌ Even minimal case creation failed: {response.status_code}")
                if 'error' in response_json:
                    error_code = response_json['error']
                    print(f"🔍 Error code: {error_code}")
                    
                    # Try to understand the error
                    if error_code == 1020:
                        print("🔍 Error 1020 might indicate:")
                        print("   - Invalid account_location_id (4195)")
                        print("   - Invalid physician_id (8077)")
                        print("   - Invalid product_id (98)")
                        print("   - Patient already has a case")
                        print("   - Team permissions issue")
                return False
                
        except json.JSONDecodeError:
            print(f"📄 Response Body (raw): {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False

if __name__ == "__main__":
    test_minimal_case()