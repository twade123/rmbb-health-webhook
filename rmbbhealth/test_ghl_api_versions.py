#!/usr/bin/env python3
"""
Test different GHL API versions and endpoints to find working conversation API
"""

import sys
import os
import requests
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

# Load environment variables from .env file
load_dotenv('/Users/timothywade/Jarvis/rmbbhealth/.env')

from services.provider_location_cache import get_provider_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_api_endpoints():
    """Test different API versions and endpoints"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    print(f"Testing with Contact ID: {contact_id}, Location ID: {location_id}")
    
    # Test different endpoint variations
    test_endpoints = [
        # V1 endpoints
        f"https://rest.gohighlevel.com/v1/conversations",
        f"https://rest.gohighlevel.com/v1/conversations/search",
        f"https://rest.gohighlevel.com/v1/locations/{location_id}/conversations",
        f"https://rest.gohighlevel.com/v1/contacts/{contact_id}/conversations",
        
        # V2 endpoints
        f"https://rest.gohighlevel.com/v2/conversations",
        f"https://rest.gohighlevel.com/v2/locations/{location_id}/conversations",
        f"https://rest.gohighlevel.com/v2/contacts/{contact_id}/conversations",
        
        # Services endpoints
        f"https://services.leadconnectorhq.com/conversations",
        f"https://services.leadconnectorhq.com/conversations/search",
    ]
    
    params = {
        'contactId': contact_id,
        'locationId': location_id
    }
    
    for endpoint in test_endpoints:
        try:
            print(f"\n🔍 Testing: {endpoint}")
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            print(f"HTTP {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ SUCCESS! Endpoint works")
                data = response.json()
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}")
                if 'conversations' in str(data):
                    conversations = data.get('conversations', data)
                    print(f"Found conversations: {len(conversations) if isinstance(conversations, list) else 'Not a list'}")
                return endpoint
            elif response.status_code == 401:
                print(f"❌ Unauthorized - API key issue")
            elif response.status_code == 404:
                print(f"❌ Not found - endpoint doesn't exist")
            else:
                print(f"❌ HTTP {response.status_code}: {response.text[:100]}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    return None

def test_message_endpoints():
    """Test message-related endpoints that might work for file uploads"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    print(f"\n📱 Testing message-related endpoints...")
    
    # Test message endpoints that might exist
    message_endpoints = [
        f"https://rest.gohighlevel.com/v1/conversations/messages/upload",
        f"https://rest.gohighlevel.com/v2/conversations/messages/upload", 
        f"https://services.leadconnectorhq.com/conversations/messages/upload",
        f"https://rest.gohighlevel.com/v1/messages/upload",
        f"https://rest.gohighlevel.com/v2/messages/upload",
    ]
    
    for endpoint in message_endpoints:
        try:
            print(f"\n📤 Testing upload endpoint: {endpoint}")
            
            # Create dummy form data to test the endpoint
            import io
            files = {
                'file': ('test.txt', io.BytesIO(b'test content'), 'text/plain')
            }
            
            data = {
                'conversationId': 'test_conversation_id',  # Dummy ID
                'locationId': location_id,
                'contactId': contact_id
            }
            
            headers_multipart = {
                'Authorization': f'Bearer {api_key}'
                # Don't set Content-Type for multipart
            }
            
            response = requests.post(endpoint, files=files, data=data, headers=headers_multipart, timeout=30)
            print(f"HTTP {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ Upload endpoint works!")
                return endpoint
            elif response.status_code == 400:
                print(f"⚠️ Bad request - endpoint exists but needs valid conversation ID")
                print(f"Response: {response.text[:200]}")
                return endpoint  # Endpoint exists, just needs valid data
            elif response.status_code == 401:
                print(f"❌ Unauthorized")
            elif response.status_code == 404:
                print(f"❌ Not found")
            else:
                print(f"❌ HTTP {response.status_code}: {response.text[:100]}")
                
        except Exception as e:
            print(f"❌ Error testing upload endpoint: {e}")
    
    return None

if __name__ == "__main__":
    print("🧪 Testing GHL API Versions and Endpoints")
    print("=" * 50)
    
    working_endpoint = test_api_endpoints()
    
    if working_endpoint:
        print(f"\n✅ Found working conversation endpoint: {working_endpoint}")
    else:
        print(f"\n❌ No working conversation endpoints found")
        print(f"\n📤 Testing upload endpoints instead...")
        upload_endpoint = test_message_endpoints()
        
        if upload_endpoint:
            print(f"\n✅ Found working upload endpoint: {upload_endpoint}")
        else:
            print(f"\n❌ No working upload endpoints found either")