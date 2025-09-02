#!/usr/bin/env python3
"""
Get available products from RMBB Health API using the documented endpoint
"""
import requests
import json

def get_available_products():
    """Get available products using the documented endpoint"""
    print("🔍 Getting Available Products from RMBB Health")
    print("=" * 60)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Use the documented products endpoint
    products_url = f"{base_url}/team/{team_id}/setting/product"
    print(f"🔗 GET {products_url}")
    
    try:
        response = requests.get(products_url, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                products = response.json()
                print(f"✅ SUCCESS! Found available products:")
                print(json.dumps(products, indent=2))
                
                if isinstance(products, list) and len(products) > 0:
                    print(f"\n📋 Available Product IDs:")
                    for i, product in enumerate(products):
                        product_id = product.get('id', 'Unknown')
                        product_name = product.get('name', 'Unknown')
                        print(f"   {i+1}. ID: {product_id} - Name: {product_name}")
                    
                    # Return the first valid product ID
                    first_product_id = products[0].get('id')
                    print(f"\n🎯 Will use first product ID: {first_product_id}")
                    return first_product_id
                else:
                    print(f"⚠️ No products found in response")
                    return None
                    
            except json.JSONDecodeError:
                print(f"📄 Raw response: {response.text}")
                return None
        else:
            try:
                error = response.json()
                print(f"❌ Error: {error}")
            except:
                print(f"❌ Error (raw): {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return None

def test_case_with_valid_product(product_id):
    """Test case creation with a valid product ID"""
    print(f"\n🧪 Testing Case Creation with Valid Product ID: {product_id}")
    print("=" * 60)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Use the most recent patient ID from our workflow test
    patient_id = 47188
    
    # Case data with valid product ID
    case_data = {
        "tid": team_id,
        "account_location_id": 4195,
        "physician_id": 8077,
        "patient_id": patient_id,
        "product_id": product_id,  # Use the valid product ID
        "external_id": f"valid_product_test_{product_id}"
    }
    
    print(f"📋 Case data with valid product ID:")
    print(json.dumps(case_data, indent=2))
    
    case_url = f"{base_url}/team/{team_id}/case"
    print(f"\n🔗 POST {case_url}")
    
    try:
        response = requests.post(case_url, headers=headers, json=case_data)
        print(f"\n📊 Response Status: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"📄 Response Body: {json.dumps(response_json, indent=2)}")
            
            if response.status_code == 200:
                case_id = response_json.get('id')
                print(f"✅ SUCCESS! Case created with ID: {case_id}")
                print(f"🎯 Valid product ID {product_id} works!")
                return True, case_id
            else:
                error_code = response_json.get('error', 'Unknown')
                print(f"❌ Case creation failed with error: {error_code}")
                return False, None
                
        except json.JSONDecodeError:
            print(f"📄 Raw response: {response.text}")
            return False, None
            
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False, None

if __name__ == "__main__":
    # Get available products
    valid_product_id = get_available_products()
    
    if valid_product_id:
        # Test case creation with valid product ID
        success, case_id = test_case_with_valid_product(valid_product_id)
        
        if success:
            print(f"\n✅ RMBB Health case creation with valid product: SUCCESS!")
            print(f"🎯 Case ID: {case_id}")
            print(f"🎯 Valid Product ID: {valid_product_id}")
        else:
            print(f"\n❌ Case creation still failed even with valid product ID")
    else:
        print(f"\n❌ Could not get valid product ID from RMBB Health API")