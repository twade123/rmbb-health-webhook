#!/usr/bin/env python3
"""
Test script to show raw GHL API response for locations endpoint
"""

import os
import requests
import json

# Set the API key
ghl_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb21wYW55X2lkIjoiall0RmUzeXpzdjlkWWJESmFUUlkiLCJ2ZXJzaW9uIjoxLCJpYXQiOjE3NTQyNDkwMDU3MzQsInN1YiI6IjRMblg5Y2MxcUowR2ZzM3NmWXJjIn0.9UcZ3t8pb94LEAPtOvNhWkvUGlqKwGKgbUie1AY-5q4"
base_url = "https://rest.gohighlevel.com/v1"

headers = {
    'Authorization': f'Bearer {ghl_api_key}',
    'Content-Type': 'application/json',
    'Version': '2021-07-28'
}

print("🔍 Querying GHL /locations/ endpoint...")
print("=" * 60)

try:
    response = requests.get(f"{base_url}/locations/", headers=headers)
    
    print(f"Status Code: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print()
    
    if response.status_code == 200:
        data = response.json()
        print("📊 RAW GHL API RESPONSE:")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print()
        
        # Parse the locations
        locations = data.get('locations', []) if isinstance(data, dict) else data
        
        print("🏢 PARSED LOCATION MAPPINGS:")
        print("=" * 60)
        for i, location in enumerate(locations):
            location_id = location.get('id')
            business_name = location.get('businessName')
            name = location.get('name')
            
            print(f"{i+1}. Location ID: {location_id}")
            print(f"   Business Name: '{business_name}'")
            print(f"   Name: '{name}'")
            print(f"   Available fields: {list(location.keys())}")
            print()
            
    else:
        print(f"❌ API Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()