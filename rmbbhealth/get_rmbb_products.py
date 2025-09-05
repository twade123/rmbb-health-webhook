#!/usr/bin/env python3
"""
Get available products from RMBB Health API
"""
import requests
import json

def get_rmbb_products():
    """Get list of available products from RMBB Health"""
    print("🔍 Getting RMBB Health Available Products")
    print("=" * 60)
    
    # API Configuration
    api_key = 'b6XGPVd0MpxXOAtvqZqEdP5gwoa7wha0'
    team_id = 85
    base_url = 'https://connect.production.backend.rmbbhealth.com'
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Try to get products - common endpoints might be:
    endpoints_to_try = [
        f"/team/{team_id}/products",
        f"/team/{team_id}/product", 
        f"/products",
        f"/product",
        f"/team/{team_id}/options/products",
        f"/options/products"
    ]
    
    for endpoint in endpoints_to_try:
        url = f"{base_url}{endpoint}"
        print(f"\n🔗 GET {url}")
        
        try:
            response = requests.get(url, headers=headers)
            print(f"📊 Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"✅ SUCCESS! Found products endpoint")
                    print(f"📄 Response: {json.dumps(data, indent=2)}")
                    return data
                except:
                    print(f"📄 Response (raw): {response.text}")
            else:
                try:
                    error = response.json()
                    print(f"❌ Error: {error}")
                except:
                    print(f"❌ Error (raw): {response.text}")
                    
        except Exception as e:
            print(f"❌ Request error: {e}")
    
    print(f"\n⚠️ No products endpoint found. Let's check if there are any documentation endpoints...")
    
    # Try some documentation/info endpoints
    info_endpoints = [
        f"/team/{team_id}/info",
        f"/team/{team_id}/schema",
        f"/api/docs",
        f"/docs"
    ]
    
    for endpoint in info_endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n🔗 GET {url}")
        
        try:
            response = requests.get(url, headers=headers)
            print(f"📊 Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ Found info endpoint")
                print(f"📄 Response: {response.text[:1000]}...")  # First 1000 chars
                
        except Exception as e:
            print(f"❌ Request error: {e}")

if __name__ == "__main__":
    get_rmbb_products()