#!/usr/bin/env python3
"""
Test GHL API with proper Version headers as used in the GHL MCP
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

def test_with_version_headers():
    """Test GHL conversation API with proper Version headers"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    print(f"Testing with Contact ID: {contact_id}, Location ID: {location_id}")
    
    # Test different versions and base URLs as used in GHL MCP
    test_configs = [
        {
            'base_url': 'https://rest.gohighlevel.com/v1',
            'version': '2021-07-28',
            'description': 'GHL MCP Default (Contacts version)'
        },
        {
            'base_url': 'https://rest.gohighlevel.com/v1',
            'version': '2021-04-15',
            'description': 'GHL MCP Conversations version'
        },
        {
            'base_url': 'https://services.leadconnectorhq.com',
            'version': '2021-07-28',
            'description': 'LeadConnector Default'
        },
        {
            'base_url': 'https://services.leadconnectorhq.com',
            'version': '2021-04-15',
            'description': 'LeadConnector Conversations'
        }
    ]
    
    for config in test_configs:
        print(f"\n🧪 Testing: {config['description']}")
        print(f"   Base URL: {config['base_url']}")
        print(f"   Version: {config['version']}")
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Version': config['version']
        }
        
        # Test conversation listing
        conversations_url = f"{config['base_url']}/conversations"
        params = {
            'contactId': contact_id,
            'locationId': location_id
        }
        
        try:
            response = requests.get(conversations_url, headers=headers, params=params, timeout=30)
            print(f"   GET conversations: HTTP {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ SUCCESS! Found working endpoint")
                data = response.json()
                print(f"   Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict'}")
                
                if isinstance(data, dict) and 'conversations' in data:
                    conversations = data['conversations']
                    print(f"   Found {len(conversations)} conversations")
                    if conversations:
                        print(f"   First conversation ID: {conversations[0].get('id')}")
                        return config, conversations[0].get('id')
                elif isinstance(data, list):
                    print(f"   Found {len(data)} conversations (list format)")
                    if data:
                        print(f"   First conversation ID: {data[0].get('id')}")
                        return config, data[0].get('id')
                        
            elif response.status_code == 401:
                print(f"   ❌ Unauthorized")
            elif response.status_code == 404:
                print(f"   ❌ Not found")
            else:
                print(f"   ❌ HTTP {response.status_code}: {response.text[:150]}...")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    return None, None

def test_conversation_creation_with_config(config):
    """Test conversation creation with working config"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Version': config['version']
    }
    
    print(f"\n📝 Testing conversation creation with: {config['description']}")
    
    conversations_url = f"{config['base_url']}/conversations"
    conversation_data = {
        'contactId': contact_id,
        'locationId': location_id,
        'type': 'SMS'
    }
    
    try:
        response = requests.post(conversations_url, json=conversation_data, headers=headers, timeout=30)
        print(f"   POST conversation: HTTP {response.status_code}")
        
        if response.status_code in [200, 201]:
            data = response.json()
            conversation_id = data.get('conversation', {}).get('id') or data.get('id')
            print(f"   ✅ Created conversation: {conversation_id}")
            return conversation_id
        else:
            print(f"   ❌ Failed: {response.text[:150]}...")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return None

if __name__ == "__main__":
    print("🧪 Testing GHL API with Version Headers")
    print("=" * 50)
    
    working_config, conversation_id = test_with_version_headers()
    
    if working_config and conversation_id:
        print(f"\n✅ Found working configuration and existing conversation!")
        print(f"   Config: {working_config['description']}")
        print(f"   Conversation ID: {conversation_id}")
    elif working_config:
        print(f"\n⚠️ Found working endpoint but no existing conversations")
        conversation_id = test_conversation_creation_with_config(working_config)
        if conversation_id:
            print(f"✅ Successfully created new conversation: {conversation_id}")
    else:
        print(f"\n❌ No working configurations found")