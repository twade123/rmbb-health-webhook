#!/usr/bin/env python3
"""
Test GHL conversation creation to debug the 404 error
"""

import sys
import os
import requests
import logging
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/Users/timothywade/Jarvis/rmbbhealth')

# Load environment variables from .env file
load_dotenv('/Users/timothywade/Jarvis/rmbbhealth/.env')

from services.provider_location_cache import get_provider_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_ghl_conversation_endpoints():
    """Test GHL conversation endpoints with our cached contact"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    print(f"Testing with:")
    print(f"  Contact ID: {contact_id}")
    print(f"  Location ID: {location_id}")
    print(f"  API Key present: {bool(api_key)}")
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Test 1: Get existing conversations
    print("\n🔍 Testing GET conversations...")
    conversations_url = f"https://rest.gohighlevel.com/v1/conversations"
    params = {
        'contactId': contact_id,
        'locationId': location_id
    }
    
    try:
        response = requests.get(conversations_url, headers=headers, params=params, timeout=30)
        print(f"GET conversations: HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            conversations = data.get('conversations', [])
            print(f"Found {len(conversations)} existing conversations")
            if conversations:
                for conv in conversations:
                    print(f"  Conversation ID: {conv.get('id')}")
                    return conversations[0].get('id')  # Return first conversation
        else:
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error getting conversations: {e}")
    
    # Test 2: Create new conversation
    print("\n📝 Testing POST conversation creation...")
    conversation_data = {
        'contactId': contact_id,
        'locationId': location_id,
        'type': 'SMS'
    }
    
    try:
        response = requests.post(conversations_url, json=conversation_data, headers=headers, timeout=30)
        print(f"POST conversation: HTTP {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code in [200, 201]:
            data = response.json()
            conversation_id = data.get('conversation', {}).get('id') or data.get('id')
            print(f"✅ Created conversation: {conversation_id}")
            return conversation_id
        
    except Exception as e:
        print(f"Error creating conversation: {e}")
    
    return None

def test_contact_exists():
    """Test if the contact actually exists in GHL"""
    
    cache = get_provider_cache()
    case_data = cache.cache["cell products"]["case_mappings"]["53330"]
    
    contact_id = case_data["contact_id"]
    location_id = case_data["location_id"] 
    api_key = cache.cache["cell products"]["sub_account_api_key"]
    
    print(f"\n👤 Testing if contact {contact_id} exists...")
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Get contact details
    contact_url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
    
    try:
        response = requests.get(contact_url, headers=headers, timeout=30)
        print(f"GET contact: HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            contact = data.get('contact', {})
            print(f"✅ Contact exists: {contact.get('firstName')} {contact.get('lastName')}")
            print(f"Contact location: {contact.get('locationId')}")
            return True
        else:
            print(f"❌ Contact not found: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error checking contact: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing GHL Conversation Creation")
    print("=" * 50)
    
    # First, check if contact exists
    contact_exists = test_contact_exists()
    
    if contact_exists:
        # Test conversation endpoints
        conversation_id = test_ghl_conversation_endpoints()
        
        if conversation_id:
            print(f"\n✅ Success! Conversation ID: {conversation_id}")
        else:
            print(f"\n❌ Failed to get/create conversation")
    else:
        print(f"\n❌ Contact doesn't exist - cannot test conversations")