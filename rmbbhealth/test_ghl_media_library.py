#!/usr/bin/env python3
"""
Test GHL Media Library endpoints as an alternative to conversation uploads
"""

import sys
import os
import requests
import logging
import io
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

# Load environment variables from .env file
load_dotenv('/Users/timothywade/Jarvis/rmbbhealth/.env')

from services.provider_location_cache import get_provider_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_media_library_endpoints():
    """Test GHL Media Library endpoints for file uploads"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    print(f"Testing Media Library with Location ID: {location_id}")
    
    # Test different media endpoints
    media_endpoints = [
        # V1 Media endpoints
        'https://rest.gohighlevel.com/v1/media/upload-file',
        'https://rest.gohighlevel.com/v1/medias/upload-file',
        'https://rest.gohighlevel.com/v1/media/upload',
        'https://rest.gohighlevel.com/v1/media',
        
        # Services endpoints  
        'https://services.leadconnectorhq.com/media/upload-file',
        'https://services.leadconnectorhq.com/media/upload',
        'https://services.leadconnectorhq.com/medias/upload-file',
    ]
    
    # Create test file content
    test_content = b"Test document content for RMBBHealth approval"
    
    for endpoint in media_endpoints:
        print(f"\n📤 Testing: {endpoint}")
        
        # Test with different header combinations
        test_headers = [
            {
                'Authorization': f'Bearer {api_key}',
                'Version': '2021-07-28'
            },
            {
                'Authorization': f'Bearer {api_key}',
                'Version': '2021-04-15'
            },
            {
                'Authorization': f'Bearer {api_key}'
                # No version header
            }
        ]
        
        for i, headers in enumerate(test_headers):
            version_info = headers.get('Version', 'No version')
            print(f"   📋 Headers {i+1}: {version_info}")
            
            try:
                # Prepare multipart form data
                files = {
                    'file': ('rmbb_approval_document.pdf', io.BytesIO(test_content), 'application/pdf')
                }
                
                data = {
                    'locationId': location_id,
                    'name': 'RMBB Approval Document',
                    'altType': 'location',
                    'altId': location_id
                }
                
                response = requests.post(endpoint, files=files, data=data, headers=headers, timeout=30)
                print(f"   HTTP {response.status_code}")
                
                if response.status_code == 200:
                    print(f"   ✅ SUCCESS! Media upload works!")
                    data = response.json()
                    print(f"   Response: {data}")
                    return endpoint, headers
                elif response.status_code == 400:
                    print(f"   ⚠️ Bad request - endpoint exists but needs different parameters")
                    print(f"   Response: {response.text[:200]}...")
                elif response.status_code == 401:
                    print(f"   ❌ Unauthorized")
                elif response.status_code == 404:
                    print(f"   ❌ Not found")
                    break  # No need to test other headers for 404 endpoints
                else:
                    print(f"   ❌ HTTP {response.status_code}: {response.text[:100]}...")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    return None, None

def test_contact_notes_endpoint():
    """Test adding notes to contacts as an alternative document delivery method"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    print(f"\n📝 Testing Contact Notes as alternative...")
    print(f"Contact ID: {contact_id}")
    
    # Test different note endpoints
    note_endpoints = [
        f'https://rest.gohighlevel.com/v1/contacts/{contact_id}/notes',
        f'https://rest.gohighlevel.com/v1/contacts/{contact_id}',  # Update contact
        f'https://services.leadconnectorhq.com/contacts/{contact_id}/notes',
    ]
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'
    }
    
    for endpoint in note_endpoints:
        print(f"\n📋 Testing: {endpoint}")
        
        try:
            if endpoint.endswith('/notes'):
                # Add note
                note_data = {
                    'body': 'RMBB Health Approval Document Available - Case #53330\n\nApproval document has been processed and is ready for review.',
                    'userId': contact_id  # or could be a user ID
                }
                response = requests.post(endpoint, json=note_data, headers=headers, timeout=30)
            else:
                # Update contact  
                update_data = {
                    'notes': 'RMBB Health Approval Document Available - Case #53330\n\nApproval document has been processed and is ready for review.'
                }
                response = requests.put(endpoint, json=update_data, headers=headers, timeout=30)
            
            print(f"   HTTP {response.status_code}")
            
            if response.status_code in [200, 201]:
                print(f"   ✅ SUCCESS! Note endpoint works!")
                print(f"   Response: {response.text[:200]}...")
                return endpoint
            elif response.status_code == 400:
                print(f"   ⚠️ Bad request: {response.text[:150]}...")
            elif response.status_code == 401:
                print(f"   ❌ Unauthorized")
            elif response.status_code == 404:
                print(f"   ❌ Not found")
            else:
                print(f"   ❌ HTTP {response.status_code}: {response.text[:100]}...")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    return None

if __name__ == "__main__":
    print("🧪 Testing GHL Media Library and Alternative Approaches")
    print("=" * 60)
    
    # Test media library first
    working_endpoint, working_headers = test_media_library_endpoints()
    
    if working_endpoint:
        print(f"\n✅ Found working media upload endpoint!")
        print(f"   Endpoint: {working_endpoint}")
        print(f"   Headers: {working_headers}")
    else:
        print(f"\n❌ No working media endpoints found")
        
        # Test contact notes as alternative
        note_endpoint = test_contact_notes_endpoint()
        
        if note_endpoint:
            print(f"\n✅ Found working notes endpoint as alternative!")
            print(f"   Endpoint: {note_endpoint}")
        else:
            print(f"\n❌ No alternative approaches found")